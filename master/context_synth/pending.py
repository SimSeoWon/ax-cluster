"""거부된 합성을 **보류로 남긴다** — 다음 실행이 다시 시도한다 (`#377` ⓑ).

## 왜 필요한가 (실측 2026-09-06)

사실 게이트가 문서를 거부하면 **기존 파일이 남고 갱신만 죽는다.** 그런데 커서는 전진하므로
(`#375`) 그 그룹을 다시 만들 계기가 **영영 없다.** 파일이 있으니 아무도 모른다 — RAG 는 어제
내용을 오늘 것으로 답한다. `NSPlayerController` 가 그 자리였다(주석에만 있는 `IMC` 를 심볼처럼
서술 → 거부 → 02:31 자 옛 문서가 그대로).

## 🔴 [중요] 무한 재시도는 **이미 태워 본 사고**다

리포트 51: 색인기가 **같은 커밋을 하루 종일 다시 걷고 있었다**(사용자가 팬 소리로 찾았다).
그래서 이 보류는 **상한이 있는 재시도**다 — `MAX_ATTEMPTS` 를 넘으면 자동으로는 더 시도하지
않고 **「포기」로 드러낸다.** 조용히 지우지도, 영원히 돌지도 않는다.

    1~3회차   다음 합성 실행이 그 그룹을 **변경이 없어도** 다시 만든다
    4회차부터  `given_up` — 목록에 남아 보이지만 **자동 재시도는 멈춘다**

## [주의] 저장 위치는 트윈 루트다 — `context/` 안이 아니다

`context/` 에 두면 색인·태그 클라우드·문서 목록이 그것을 **문서로 센다**(`#288` 이 값을 치른
자리다). 트윈 루트의 작은 JSON 이고 커밋되지 않는다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

FILE = "synth_pending.json"
MAX_ATTEMPTS = 3          # 이 횟수까지만 자동 재시도한다 (리포트 51 의 그 사고를 만들지 않는다)
RETRY_CAP = 20            # 한 실행에서 끌어올 보류 그룹 수 상한 — 한 배치가 부풀지 않게


def _path(paths) -> Path:
    return Path(paths.root) / FILE


def load(paths) -> dict:
    try:
        data = json.loads(_path(paths).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(paths, data: dict) -> None:
    """[주의] 실패해도 삼킨다 — 보류 기록 때문에 합성이 죽으면 본말이 뒤집힌다."""
    try:
        _path(paths).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    except OSError:
        pass


def record(paths, key: str, files: list, reason: str, commit: str = "") -> dict:
    """거부/실패를 적는다. 같은 그룹이 또 실패하면 `attempts` 가 오른다."""
    data = load(paths)
    prev = data.get(key) or {}
    entry = {
        "files": list(files),
        "reason": reason,
        "commit": commit or prev.get("commit", ""),
        "attempts": int(prev.get("attempts") or 0) + 1,
        "first_seen": prev.get("first_seen") or time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_try": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    entry["given_up"] = entry["attempts"] >= MAX_ATTEMPTS
    data[key] = entry
    save(paths, data)
    return entry


def clear(paths, key: str) -> bool:
    """성공했으면 지운다. 지운 것이 있으면 True."""
    data = load(paths)
    if key not in data:
        return False
    data.pop(key, None)
    save(paths, data)
    return True


def due(paths, *, cap: int = RETRY_CAP) -> list:
    """이번 실행에서 **다시 시도할** 그룹들 — `(key, files)`. 포기한 것은 빠진다."""
    out = []
    for key, e in sorted(load(paths).items()):
        if e.get("given_up") or int(e.get("attempts") or 0) >= MAX_ATTEMPTS:
            continue
        out.append((key, list(e.get("files") or [])))
        if len(out) >= cap:
            break
    return out


def given_up(paths) -> list:
    """자동 재시도를 멈춘 것들 — **사람이 봐야 하는 목록**이다. 조용히 사라지지 않는다."""
    return sorted(k for k, e in load(paths).items()
                  if e.get("given_up") or int(e.get("attempts") or 0) >= MAX_ATTEMPTS)


def summary(paths) -> str:
    """한 줄 요약 — 합성 결과 줄에 붙인다. 없으면 빈 문자열(조용하다)."""
    data = load(paths)
    if not data:
        return ""
    up = [k for k, e in data.items()
          if e.get("given_up") or int(e.get("attempts") or 0) >= MAX_ATTEMPTS]
    waiting = len(data) - len(up)
    bits = []
    if waiting:
        bits.append(f"보류 {waiting}건(다음 실행에 재시도)")
    if up:
        bits.append(f"[중요] 포기 {len(up)}건 — 사람이 봐야 한다: " + ", ".join(sorted(up)[:3]))
    return " · ".join(bits)
