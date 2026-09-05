"""본문 작성 레인 A/B — **agy vs Codex CLI**, 같은 골조·같은 프롬프트로.

사용자 요청 2026-09-05: *"본문 작성 레인 A/B 재보자"*.

## 왜 골조 A/B 보다 이쪽이 깨끗한가

골조 단계는 **계약을 새로 만드는** 일이라 「무엇이 좋은 골조인가」에 판단이 섞인다(표본 1로
결론 내면 안 되는 이유). 본문 작성은 다르다 — **계약이 이미 동결돼 있고**, 판정이 결정적이다:

    층1 (`layer1.check`)   동결 위반 · `[PSEUDO]` 잔재 · `[FEEDBACK]` · 펜스 잔재 — LLM 0
    파일 수                요구한 파일을 다 냈나 (`=== FILE:` 블록)

즉 **같은 입력 · 같은 판정자**로 두 모델을 잰다.

## 무엇을 입력으로 쓰나

골조 A/B(2026-09-05)에서 Claude(Opus)가 낸 골조 — 동결 선언 20개 · `[PSEUDO]` 6개.
**두 레인에 같은 것**을 준다. (Codex 골조는 동결 선언이 5개뿐이라 본문 작성의 입력으로 쓰면
과제 자체가 달라진다.)

실행: `.venv/bin/python master/bench_lane_codex.py [--only agy|codex]`
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import layer1 as L1                              # noqa: E402
from master.work import lanes as LN                               # noqa: E402

REQUESTER = ("user", "192.168.0.33")
SKELETON_SRC = {
    "Source/NS/UI/NSInteractionPromptWidget.h":
        Path("/tmp/ax_bench_claude_opus_NSInteractionPromptWidget.h"),
    "Source/NS/UI/NSInteractionPromptWidget.cpp":
        Path("/tmp/ax_bench_claude_opus_NSInteractionPromptWidget.cpp"),
}
# [주의] **저장소 루트에 두지 않는다** — 루트 신규 파일은 유닛의 `ReadOnlyPaths`
#    목록과 어긋나 `test_sandbox` 가 잡고, 맞추려면 살아 있는 큐를 재기동해야 한다.
#    수치의 정본은 레드마인 노트와 리포트다. 이 파일은 그 사이의 원본일 뿐이다.
OUT = Path("/tmp/bench_lane_codex_result.json")


def _codex(prompt: str, timeout: int = 1800) -> str:
    """`.33` 의 codex CLI. 함정 넷은 `bench_skeleton_codex.py` 머리말에 적혀 있다."""
    user, host = REQUESTER
    tmp = Path("/tmp/ax_codex_lane_prompt.txt")
    tmp.write_text(prompt, encoding="utf-8")
    scp = subprocess.run(["scp", "-o", "ConnectTimeout=15", str(tmp),
                          f"{user}@{host}:C:/Users/USER/AppData/Local/Temp/ax_codex_lane.txt"],
                         capture_output=True, text=True, timeout=180)
    if scp.returncode != 0:
        raise RuntimeError(f"scp 실패: {scp.stderr[:200]}")
    cmd = ('cmd /c "cd %TEMP% && type ax_codex_lane.txt | '
           'codex exec --skip-git-repo-check 2>&1"')
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=15", f"{user}@{host}", cmd],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr)[-400:])
    return r.stdout


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["agy", "codex"], default="")
    args = ap.parse_args(argv)

    missing = [str(p) for p in SKELETON_SRC.values() if not p.is_file()]
    if missing:
        print(f"[중요] 골조 입력이 없다: {missing} — `bench_skeleton_codex.py` 를 먼저 돌린다")
        return 2
    skeleton = {k: v.read_text(encoding="utf-8") for k, v in SKELETON_SRC.items()}
    base_pseudo = sum(t.count("[PSEUDO") for t in skeleton.values())
    print(f"입력 골조: 파일 {len(skeleton)} · [PSEUDO] {base_pseudo}개 "
          f"(동결 선언은 헤더가 계약)")

    result = {"input_pseudo": base_pseudo, "runs": {}}
    for lane in ("agy", "codex"):
        if args.only and lane != args.only:
            continue
        print(f"\n── {lane} …", flush=True)
        gen = (lambda prompt, _l: _codex(prompt)) if lane == "codex" else None
        t0 = time.time()
        r = LN.run_one(skeleton, lane, generator=gen, timeout=1800)
        sec = time.time() - t0
        row = {"ok": r.ok, "seconds": round(sec, 1), "chars": r.chars,
               "files_got": sorted(f.split("/")[-1] for f in (r.files or {})),
               "missing": list(r.missing or []), "reason": r.reason}
        if r.files:
            # 🔴 판정은 **층1** 이 한다 — 사람이 눈으로 고르지 않는다.
            #    baseline 은 골조 자신이다(동결 대조 대상).
            got = L1.check(r.files, baseline=lambda p: skeleton.get(p))
            row["layer1_ok"] = got.ok
            row["layer1_problems"] = [p[:160] for p in (got.problems or [])][:6]
            row["pseudo_left"] = sum(t.count("[PSEUDO") for t in r.files.values())
            for path_, text in r.files.items():
                (Path(f"/tmp/ax_lane_{lane}_{path_.split('/')[-1]}")
                 .write_text(text, encoding="utf-8"))
        result["runs"][lane] = row
        print("  " + json.dumps(row, ensure_ascii=False)[:500], flush=True)

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
