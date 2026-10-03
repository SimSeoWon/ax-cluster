"""대화 세션 사용량 수집기 (`#713` ②, 2026-10-03) — Claude Code·Codex 세션 jsonl → 토큰 숫자.

🔴 [중요] **왜 지금 있나.** 지휘 세션(마스터)·요청자 세션(`.33`)의 비용은 어디에도 집계되지 않는다.
   그런데 두 도구는 **이미 세션마다 사용량을 로컬에 남긴다** — 새 기록기를 심을 필요가 없다
   (사용자 결정 2026-10-03: *".33 도 로컬에 저장해뒀다가 나중에 가져오는건 어때?"*).
   🔴 다만 Claude Code 는 기본 `cleanupPeriodDays`=30 으로 **30일 지난 기록을 지운다** — `.33` 의
   가장 오래된 기록이 정확히 30일 전이었다(실측 2026-10-03). 그래서 **주기적으로** 가져와 적립한다.

[중요] **숫자만 남긴다.** 대화 본문·도구 출력은 읽어 넘기기만 하고 저장하지 않는다. 원격은
   `tar` 스트림으로 읽는다 — 원격 디스크에 아무것도 쓰지 않는다(`.33` 손님 규칙: 읽기 전용).
[중요] **멱등이다.** 세션 하나 = 적립 파일 하나(`<저장소>/<host>/<tool>/<session>.json`)로
   통째로 덮어쓴다. 자라는 세션을 다시 읽어도 중복되지 않는다.
[주의] **표시는 토큰만**(사용자 결정) — 이 기록에 금액 칸은 없다. CLI 구독은 금액을 모른다.

중복 규칙 (실측):
- Claude: 한 응답이 콘텐츠 블록마다 **같은 `message.id`·같은 usage** 로 여러 줄 찍힌다 → id 로 한 번만
- Codex: `token_count` 이벤트가 같은 누적값으로 **반복**될 수 있다 → `total_token_usage` 가 바뀔 때만
  그 턴의 `last_token_usage` 를 센다
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_STORE = Path.home() / "ax-state" / "usage" / "sessions"

# 원격 기계 → (ssh 대상, 윈도우인가). 마스터 자신은 "local".
HOSTS = {
    "192.168.0.33": ("user@192.168.0.33", True),
    "192.168.0.2": ("janus@192.168.0.2", True),
    "192.168.0.43": ("sim@192.168.0.43", False),
}
SOURCES = (("claude", ".claude", "projects"), ("codex", ".codex", "sessions"))


def _log(msg: str) -> None:
    print(f"[session-usage] {msg}", file=sys.stderr, flush=True)


@dataclass
class Session:
    tool: str
    session_id: str
    records: list = field(default_factory=list)


def parse_claude(lines) -> Session | None:
    """Claude Code 세션 jsonl → 응답(message.id)마다 한 레코드."""
    seen: set = set()
    sid, recs = "", []
    for raw in lines:
        try:
            d = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if d.get("type") != "assistant":
            continue
        m = d.get("message") or {}
        u = m.get("usage") or {}
        mid = m.get("id") or d.get("requestId") or ""
        if not u or not mid or mid in seen:
            continue
        seen.add(mid)
        sid = sid or d.get("sessionId") or ""
        recs.append({
            "ts": d.get("timestamp", ""), "model": m.get("model", ""),
            "input": int(u.get("input_tokens") or 0),
            "output": int(u.get("output_tokens") or 0),
            "cache_read": int(u.get("cache_read_input_tokens") or 0),
            "cache_create": int(u.get("cache_creation_input_tokens") or 0),
            "reasoning": int((u.get("output_tokens_details") or {}).get("thinking_tokens") or 0),
        })
    return Session("claude", sid, recs) if recs else None


def parse_codex(lines) -> Session | None:
    """Codex 세션 jsonl → 누적값이 바뀐 `token_count` 마다 한 레코드(그 턴의 사용량)."""
    sid, model, prev, recs = "", "", None, []
    for raw in lines:
        try:
            d = json.loads(raw)
        except (ValueError, TypeError):
            continue
        p = d.get("payload") or {}
        t = d.get("type")
        if t == "session_meta":
            sid = sid or p.get("id") or p.get("session_id") or ""
        elif t == "turn_context":
            model = p.get("model") or model
        elif t == "event_msg" and p.get("type") == "token_count":
            info = p.get("info") or {}
            total, last = info.get("total_token_usage"), info.get("last_token_usage")
            if not total or not last or total == prev:
                continue
            prev = total
            recs.append({
                "ts": d.get("timestamp", ""), "model": model,
                "input": int(last.get("input_tokens") or 0),
                "output": int(last.get("output_tokens") or 0),
                "cache_read": int(last.get("cached_input_tokens") or 0),
                "cache_create": int(last.get("cache_write_input_tokens") or 0),
                "reasoning": int(last.get("reasoning_output_tokens") or 0),
            })
    return Session("codex", sid, recs) if recs else None


PARSERS = {"claude": parse_claude, "codex": parse_codex}


def _store(store: Path, host: str, s: Session, origin: str) -> Path:
    # [주의] 이름은 **원본 경로**에서 만든다 — Claude 서브에이전트 기록은 부모와 같은 `sessionId` 를
    #    써서, 세션 id 로 이름을 지으면 서로 덮는다(실측 `.33`: 306 세션 → 297 파일).
    name = origin.replace("\\", "/").removesuffix(".jsonl").replace("/", "__")
    out = store / host / s.tool / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps({"host": host, "tool": s.tool, "session_id": s.session_id,
                               "origin": origin, "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                               "records": s.records}, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)                       # 원자적 교체 — 반쯤 쓴 파일을 남기지 않는다
    return out


def _tar_stream(host: str, base: str, sub: str):
    """원격 `<home>/<base>/<sub>` 를 tar 로 읽는다. 원격에는 아무것도 쓰지 않는다."""
    target, windows = HOSTS[host]
    remote = (f'tar -cf - -C "%USERPROFILE%\\{base}" {sub}' if windows
              else f'tar -cf - -C "$HOME/{base}" {sub}')
    return subprocess.Popen(["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", target, remote],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def collect(host: str, *, store: Path = DEFAULT_STORE) -> dict:
    """한 기계의 두 도구 세션을 모두 읽어 적립한다. 반환: 도구별 세션·레코드·토큰 합."""
    out: dict = {}
    for tool, base, sub in SOURCES:
        t0 = time.monotonic()
        st = {"files": 0, "sessions": 0, "records": 0, "input": 0, "output": 0, "error": ""}
        parse = PARSERS[tool]
        if host == "local":
            root = Path.home() / base / sub
            members = ((str(p.relative_to(root.parent)), p.open("rb"))
                       for p in sorted(root.rglob("*.jsonl"))) if root.is_dir() else iter(())
            proc = None
        else:
            proc = _tar_stream(host, base, sub)
            tf = tarfile.open(fileobj=proc.stdout, mode="r|")
            members = ((m.name, tf.extractfile(m)) for m in tf
                       if m.isfile() and m.name.endswith(".jsonl"))
        try:
            for name, fh in members:
                if fh is None:
                    continue
                st["files"] += 1
                # [주의] tar 스트림의 파일 객체는 seek 를 못 한다 — 감싸지 말고 통째로 읽는다
                with fh:
                    s = parse(fh.read().decode("utf-8", "replace").splitlines())
                if s is None:
                    continue
                _store(store, host, s, name)
                st["sessions"] += 1
                st["records"] += len(s.records)
                st["input"] += sum(r["input"] for r in s.records)
                st["output"] += sum(r["output"] for r in s.records)
        except (tarfile.TarError, OSError) as e:
            st["error"] = f"{type(e).__name__}: {e}"
        if proc is not None:
            err = proc.stderr.read().decode("utf-8", "replace").strip()
            rc = proc.wait()
            if rc != 0 and not st["files"]:
                # 도구가 그 기계에 없으면(디렉토리 없음) 실패가 아니라 「없음」이다
                st["error"] = st["error"] or f"ssh/tar rc={rc}: {err[:160]}"
        st["seconds"] = round(time.monotonic() - t0, 1)
        _log(f"{host} {tool} — 파일 {st['files']} · 세션 {st['sessions']} · 레코드 {st['records']}"
             f" · 입력 {st['input']} · 출력 {st['output']} · {st['seconds']}초"
             + (f" · [주의] {st['error']}" if st["error"] else ""))
        out[tool] = st
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="대화 세션 사용량 수집 (#713 ②) — 숫자만 적립한다")
    ap.add_argument("hosts", nargs="*", default=["local"],
                    help="local 또는 " + " · ".join(HOSTS))
    ap.add_argument("--store", default=str(DEFAULT_STORE))
    a = ap.parse_args(argv)
    bad = [h for h in a.hosts if h != "local" and h not in HOSTS]
    if bad:
        ap.error(f"모르는 기계: {bad}")
    failed = False
    for h in a.hosts:
        res = collect(h, store=Path(a.store))
        failed |= any(v["error"] and not v["files"] for v in res.values()
                      if "No such file" not in v["error"] and "Cannot open" not in v["error"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
