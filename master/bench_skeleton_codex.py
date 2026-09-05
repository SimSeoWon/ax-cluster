"""골조 A/B — **Claude(Opus) vs Codex CLI**, 같은 프롬프트·같은 grounding 으로.

사용자 요청 2026-09-05: *"골조 A/B 재보자"*. 근거는 그날 실측이다 — 첫 end-to-end 완주 48분 중
**골조 작성이 31분(65%)** 이었고 워커 추론은 2.4분(5%)이었다. 줄일 데가 있다면 여기다.

## [중요] 이것은 **측정**이지 파이프라인이 아니다

`#339` 이후 **마스터는 골조를 만들지 않는다**(요청자 `.33` 의 몫). 이 스크립트는 그 결정을
바꾸지 않는다 — 같은 프롬프트를 두 모델에 주고 **누가 더 나은 골조를 내는지만** 잰다.
결과는 `#368`(오케스트레이터 선택 레이어 아이디어)의 판단 재료다.

## 무엇을 재나

    시간          호출 시작~응답 (초)
    파일 수        `=== FILE:` 블록이 요구한 파일을 다 냈나
    [PSEUDO]/[DOC] 작업지시서가 실제로 들어갔나 (0이면 골조가 아니라 완성본을 쓴 것 —
                   사전 훑기가 「할 일 없음」으로 걷어낸다)
    금지 마커      `[FEEDBACK]` 은 골조에 쓰면 안 된다 (등재 게이트가 막는다)

[주의] **UHT 게이트(실 빌드)는 여기서 안 돌린다** — `.2` 의 UE5 트리를 만지는 일이라 사람 승인
자리다. 여기서는 텍스트 계약까지만 재고, 통과분만 나중에 게이트에 태운다.

## 호출 형태 (실측 2026-09-05 — 함정 넷을 밟고 얻은 것)

    Claude   마스터의 `synth.generate(prompt, "claude:opus")` — 기존 레인 규약 그대로
    Codex    `.33` 에만 있다(마스터엔 node 가 없다). SSH 로 부른다:
             ssh user@.33 'cmd /c "cd %TEMP% && type p.txt | codex exec --skip-git-repo-check"'
             ① 프롬프트는 **파일로** (인용부호가 SSH→PowerShell→cmd 에서 깨진다)
             ② `codex exec` 는 **stdin 을 읽는다** — 파이프로 넣는다
             ③ `--skip-git-repo-check` 없으면 *"Not inside a trusted directory"* 로 거절
             ④ PowerShell 은 `< NUL` 을 못 쓴다 → `cmd /c`

실행: `.venv/bin/python master/bench_skeleton_codex.py [--only claude|codex]`
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.context_search.paths import resolve                  # noqa: E402
from master.work import skeleton as SK                           # noqa: E402

PROJECT = "NS"
REQUESTER = ("user", "192.168.0.33")
# [주의] **저장소 루트에 두지 않는다** — 루트 신규 파일은 유닛의 `ReadOnlyPaths`
#    목록과 어긋나 `test_sandbox` 가 잡고, 맞추려면 살아 있는 큐를 재기동해야 한다.
#    수치의 정본은 레드마인 노트와 리포트다. 이 파일은 그 사이의 원본일 뿐이다.
OUT = Path("/tmp/bench_skeleton_codex_result.json")

# [중요] **아직 저장소에 없는 것**을 시킨다 — 이미 있는 클래스를 시키면 모델이 기억이나 문맥에서
#    베껴 와 「골조를 얼마나 잘 쓰나」가 아니라 「얼마나 잘 찾나」를 재게 된다.
SPEC = SK.SkeletonSpec(
    stem="NSInteractionPromptWidget",
    files=["Source/NS/UI/NSInteractionPromptWidget.h",
           "Source/NS/UI/NSInteractionPromptWidget.cpp"],
    classes=["UNSInteractionPromptWidget"],
    instruction=(
        "상호작용 대상이 포커스되면 화면에 「E 키로 열기」 같은 프롬프트를 띄우는 UMG 위젯이다. "
        "UNSInteractionWorldSubsystem 이 포커스 변화를 알려 주면 표시/숨김을 바꾸고, "
        "대상이 주는 표시 문구와 입력 키 이름을 받아 갱신한다. "
        "위젯 자체는 대상 판정을 하지 않는다 — 받은 것만 그린다."),
)


def _codex(prompt: str, timeout: int = 1800) -> str:
    """`.33` 의 codex CLI 를 **레인처럼** 부른다 — `synth.generate` 자리에 끼운다.

    [중요] **프롬프트는 파일로 보낸다** (실측 함정 ①: 인용부호가 SSH→PowerShell→cmd 에서 깨진다).
    `codex exec` 는 stdin 을 읽고(②), `--skip-git-repo-check` 가 없으면 거절한다(③),
    PowerShell 은 `< NUL` 을 못 써서 `cmd /c` 를 탄다(④).
    """
    user, host = REQUESTER
    tmp = Path("/tmp/ax_codex_prompt.txt")
    tmp.write_text(prompt, encoding="utf-8")
    scp = subprocess.run(["scp", "-o", "ConnectTimeout=15", str(tmp),
                          f"{user}@{host}:C:/Users/USER/AppData/Local/Temp/ax_codex_prompt.txt"],
                         capture_output=True, text=True, timeout=180)
    if scp.returncode != 0:
        raise RuntimeError(f"scp 실패: {scp.stderr[:200]}")
    cmd = ('cmd /c "cd %TEMP% && type ax_codex_prompt.txt | '
           'codex exec --skip-git-repo-check 2>&1"')
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", f"{user}@{host}", cmd],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr)[-400:])
    return r.stdout


def run_lane(paths, model: str) -> dict:
    """`skeleton.build` 를 **그대로** 쓴다 — grounding·파싱·판정이 실물과 같아야 A/B 다.

    codex 는 마스터에 없으므로(node 없음) `synth.generate` 를 그 호출에 한해 갈아 끼운다.
    [주의] 프롬프트 조립은 건드리지 않는다 — 두 모델이 **같은 프롬프트**를 받는 것이 전제다.
    """
    from master.ontology import synth
    t0 = time.time()
    saved = synth.generate
    if model == "codex":
        synth.generate = lambda prompt, m, **kw: _codex(prompt, timeout=kw.get("timeout", 1800))
    try:
        sk = SK.build(paths, SPEC, model=("claude:opus" if model != "codex" else "codex"),
                      ground=True)
        return {"ok": True, "seconds": time.time() - t0, "sk": sk}
    except Exception as e:                                       # noqa: BLE001
        return {"ok": False, "seconds": time.time() - t0, "error": f"{type(e).__name__}: {e}"}
    finally:
        synth.generate = saved


def measure(text: str) -> dict:
    """텍스트 계약을 잰다 — **모델을 믿지 않고 산출물을 센다**."""
    files = dict(re.findall(r"===\s*FILE:\s*(\S+)\s*===\n(.*?)(?=\n===\s*FILE:|\Z)",
                            text or "", re.S))
    want = [f.split("/")[-1] for f in SPEC.files]
    got = [k.split("/")[-1] for k in files]
    return {
        "files_expected": want,
        "files_got": got,
        "files_ok": all(w in got for w in want),
        "chars": len(text or ""),
        "pseudo": (text or "").count("[PSEUDO"),
        "doc": (text or "").count("[DOC]"),
        "feedback_banned": (text or "").count("[FEEDBACK]"),   # 골조에 있으면 등재가 거절한다
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["claude", "codex"], default="")
    args = ap.parse_args(argv)

    paths = resolve(PROJECT)
    print(f"대상 {SPEC.stem} — 저장소에 없는 클래스 (베끼기가 아니라 작성을 잰다)")

    result = {"spec": SPEC.stem, "runs": {}}
    for name in ("claude:opus", "codex"):
        if args.only and not name.startswith(args.only):
            continue
        print(f"\n── {name} …", flush=True)
        r = run_lane(paths, "codex" if name == "codex" else "claude")
        row = {"ok": r["ok"], "seconds": round(r["seconds"], 1)}
        if r["ok"]:
            sk = r["sk"]
            body = "\n".join(sk.files.values())
            row.update({
                "files_got": sorted(f.split("/")[-1] for f in sk.files),
                "files_ok": len(sk.files) == len(SPEC.files),
                "chars": len(body),
                "pseudo": sk.pseudo,
                "frozen_decls": len(sk.frozen),
                "questions": len(sk.questions or []),
                "feedback_banned": body.count("[FEEDBACK]"),
                "notes": [n[:120] for n in (sk.notes or [])][:6],
            })
            for path_, text in sk.files.items():
                out = Path(f"/tmp/ax_bench_{name.replace(':', '_')}_{path_.split('/')[-1]}")
                out.write_text(text, encoding="utf-8")
        else:
            row["error"] = r.get("error", "")[:400]
        result["runs"][name] = row
        print("  " + json.dumps(row, ensure_ascii=False)[:500], flush=True)

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
