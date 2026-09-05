"""열린 이슈 전수 감사 — **Codex 에 위임하고, 근거는 내가 검증한다** (사용자 지시 2026-09-05).

## 왜 위임인가

열린 `[AX]` 이슈 56건 중 18건이 오래된 축(온보딩·드리프트)이라 **한 건씩 실물 확인**이 필요하다.
사람(과 내) 시간으로는 비싸고, **판정 근거가 `file:line`** 이라 위임에 맞는 모양이다 —
받은 답을 **싸게 검증**할 수 있기 때문이다.

[중요] **위임한 결과를 그대로 믿지 않는다** (`~/CLAUDE.md`: *"Never trust a delegated backend's
done"* — 2026-08-07 실측: `agy` 가 `status:SUCCESS` 를 내고 파일을 안 썼다). 그래서 이 스크립트는
**판정과 근거를 받아 오기만** 하고, 근거의 진위는 호출자가 `grep` 으로 확인한다.

## 판정 셋 (사용자 질문 그대로)

    fixed      이미 고쳐졌다 — 코드가 그렇게 돼 있다
    valid      아직 유효하다 — 해야 할 일이 남았다
    changed    전제가 바뀌었다 — 대상이 사라졌거나 다른 결정으로 대체됐다

실행: `.venv/bin/python master/audit_issues_codex.py --ids 227,229,233 [--reasoning medium]`
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPO = Path(__file__).resolve().parent.parent
QUEUE = "http://127.0.0.1:8101"
TOKEN = Path.home() / ".config/ax-cluster/token"
OUT = Path("/tmp/ax_issue_audit.json")

PROMPT = """당신은 이 저장소(AX 클러스터, 파이썬)의 코드를 읽고 **레드마인 이슈가 아직 유효한지**만 판정합니다.

## 이슈 #{iid}
제목: {subject}

설명:
{body}

## 할 일

저장소를 실제로 읽고(grep/파일 열기) 아래 셋 중 **하나**로 판정하세요:

- `fixed`   : 이미 고쳐져 있다 (코드가 그 이슈가 요구한 상태다)
- `valid`   : 아직 유효하다 (해야 할 일이 남아 있다)
- `changed` : 전제가 바뀌었다 (대상 파일/기능이 사라졌거나 다른 결정으로 대체됐다)

## 출력 형식 — **이 JSON 한 덩어리만** 출력하세요. 다른 말은 쓰지 마세요.

{{"verdict": "fixed|valid|changed",
  "confidence": "high|medium|low",
  "evidence": ["경로:줄번호 — 무엇을 확인했는지", "..."],
  "reason": "한국어 두 문장 이내"}}

## 규칙

- **근거는 반드시 실제 파일 경로와 줄 번호**로 적으세요. 지어내지 마세요.
- 파일을 못 찾으면 그 사실 자체가 근거입니다 (`changed` 후보).
- 확신이 없으면 `confidence: low` 로 정직하게 적으세요.
- 코드를 **고치지 마세요**. 읽기만 하세요.
"""


def _issue(iid: int) -> dict:
    tok = TOKEN.read_text(encoding="utf-8").strip()
    req = urllib.request.Request(f"{QUEUE}/api/v1/redmine/issue/{iid}",
                                 headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d.get("issue") or d


def _codex(prompt: str, *, reasoning: str, timeout: int) -> tuple:
    """`(본문, 사유)`. [중요] **읽기 전용 샌드박스로 돌린다** — 코드를 고치지 못하게."""
    pf = Path("/tmp/ax_audit_prompt.txt")
    pf.write_text(prompt, encoding="utf-8")
    out = Path("/tmp/ax_audit_last.txt")
    cmd = ["codex", "exec", "-C", str(REPO), "--sandbox", "read-only",
           "-c", f'model_reasoning_effort="{reasoning}"', "-o", str(out), prompt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "", f"시간 초과({timeout}초)"
    if r.returncode != 0:
        return "", ((r.stderr or "") + (r.stdout or ""))[-300:]
    return (out.read_text(encoding="utf-8", errors="replace") if out.is_file() else ""), ""


def _parse(text: str) -> dict:
    """JSON 한 덩어리를 뽑는다. [주의] 모델이 앞뒤로 말을 붙여도 견딘다."""
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j <= i:
        return {"verdict": "?", "reason": "JSON 을 못 찾았다", "raw": text[:200]}
    try:
        return json.loads(text[i:j + 1])
    except ValueError as e:
        return {"verdict": "?", "reason": f"JSON 파싱 실패: {e}", "raw": text[i:i + 200]}


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="쉼표로 구분한 이슈 번호")
    ap.add_argument("--reasoning", default="medium")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args(argv)

    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    got = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
    for iid in ids:
        issue = _issue(iid)
        subject = issue.get("subject", "")
        body = (issue.get("description") or "")[:6000]
        print(f"\n── #{iid} {subject[:60]} …", flush=True)
        t0 = time.time()
        text, why = _codex(PROMPT.format(iid=iid, subject=subject, body=body),
                           reasoning=args.reasoning, timeout=args.timeout)
        sec = round(time.time() - t0, 1)
        if why:
            row = {"verdict": "?", "reason": why[:200], "seconds": sec}
        else:
            row = _parse(text)
            row["seconds"] = sec
        row["subject"] = subject
        got[str(iid)] = row
        print(f"   {row.get('verdict')} ({row.get('confidence','?')}) · {sec}초 · "
              f"{str(row.get('reason'))[:120]}", flush=True)
        for e in (row.get("evidence") or [])[:4]:
            print(f"     · {e}", flush=True)
        OUT.write_text(json.dumps(got, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
