"""포팅 모드 (소 1.3.5).

[중요] 지키는 계약은 셋이다:

    ① **못 찾으면 붙이지 않는다** — 관계없는 원본은 원본이 없는 것보다 나쁘다
    ② **어떻게 맞췄는지 말한다** (`exact` / `prefix`) — 사람이 가늠할 근거
    ③ [중요] **원본이 대상 목록으로 새지 않는다** — 새면 워커가 읽기 전용 모듈을 고친다

`.venv/bin/python master/test_porting.py`
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.work import infer as I         # noqa: E402
from master.work import porting as P       # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def tree(files: list):
    """`Source/` 아래에 빈 파일들을 만든 임시 트리. [중요] 내용은 안 본다 — 이름만 본다."""
    root = Path(tempfile.mkdtemp(prefix="axport"))
    src = root / "Source"
    for f in files:
        p = src / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")

    class Paths:
        name = "T"
        source = src
    P._INDEX_CACHE.clear()          # 캐시가 테스트끼리 새지 않게
    return Paths(), root


REAL_SHAPE = [
    # 실측된 대응 형태 넷 (2026-08-12)
    "Project_Alpha/Tables/tabledata/AlphaTableEnum.h",           # 접두사 Alpha
    "Project_Alpha/UI/Components/Hexagon/Alpha_HexagonTileItem.h",   # 그대로 옮긴 것
    "Project_Alpha/Manager/AlphaManager_Mission.h",
    "Project_Alpha/Character/AlphaCharacter.h",
    "ModularStage/Table/TableEnum.h",
    "ModularStage/UI/HexGrid/Alpha_HexagonTileItem.h",
    "ModularStage/Manager/Manager_Mission.h",
    "ModularStage/ModularStageCharacter.h",
    "ModularStage/Mission/MSMissionTask.h",                      # [중요] 원본이 없는 신규 코드
]


def test_normalize_strips_measured_prefixes_once() -> None:
    check("Alpha 접두사", P.normalize_stem("AlphaTableEnum") == "tableenum")
    check("Alpha_ 접두사", P.normalize_stem("Alpha_HexagonTileItem") == "hexagontileitem")
    check("ModularStage 접두사", P.normalize_stem("ModularStageCharacter") == "character")
    check("MS 접두사", P.normalize_stem("MSMissionTask") == "missiontask")
    # [중요] 한 번만 뗀다 — 두 번 떼면 없는 대응을 만든다
    check("두 번 떼지 않는다", P.normalize_stem("AlphaAlphaFoo") == "alphafoo",
          P.normalize_stem("AlphaAlphaFoo"))
    check("접두사가 전부인 이름은 안 건드린다", P.normalize_stem("MS") == "ms")


def test_exact_match_is_preferred() -> None:
    paths, root = tree(REAL_SHAPE)
    try:
        p = P.counterparts(paths, ["Source/ModularStage/UI/HexGrid/Alpha_HexagonTileItem.h"])
        check("찾았다", len(p.matches) == 1, p.summary())
        m = p.matches[0]
        check("exact 규칙", m.rule == P.EXACT, m.rule)
        check("confident", m.confident)
        check("원본 경로가 맞다",
              m.sources == ["Source/Project_Alpha/UI/Components/Hexagon/"
                            "Alpha_HexagonTileItem.h"], str(m.sources))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_prefix_match_is_found_but_flagged() -> None:
    """[중요] 실측: 접두사 정규화가 대응을 9 → 21쌍으로 늘렸다. 다만 확신은 낮다고 말한다."""
    paths, root = tree(REAL_SHAPE)
    try:
        p = P.counterparts(paths, ["Source/ModularStage/Table/TableEnum.h",
                                   "Source/ModularStage/Manager/Manager_Mission.h",
                                   "Source/ModularStage/ModularStageCharacter.h"])
        check("셋 다 찾았다", len(p.matches) == 3, p.summary())
        check("전부 prefix 규칙", all(m.rule == P.PREFIX for m in p.matches),
              str([m.rule for m in p.matches]))
        check("confident 가 아니다", not any(m.confident for m in p.matches))
        sec = "\n".join(P.source_section(p))
        check("확인하라고 적는다", "대응이 맞는지 먼저 확인" in sec)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_no_counterpart_invents_nothing() -> None:
    """[중요] 관계없는 원본을 붙이면 모델이 자신 있게 엉뚱한 것을 만든다."""
    paths, root = tree(REAL_SHAPE)
    try:
        p = P.counterparts(paths, ["Source/ModularStage/Mission/MSMissionTask.h"])
        check("아무것도 안 붙인다", not p.matches, str([m.target for m in p.matches]))
        check("신규로 본다고 말한다", any("신규" in n for n in p.notes), str(p.notes))
        check("절을 만들지 않는다", P.source_section(p) == [])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_source_module_is_not_its_own_source() -> None:
    """원본 파일이 대상으로 들어오면(있어선 안 되지만) 자기 자신을 원본으로 붙이지 않는다."""
    paths, root = tree(REAL_SHAPE)
    try:
        p = P.counterparts(paths, ["Source/Project_Alpha/Table s/tabledata/AlphaTableEnum.h"
                                   .replace(" ", "")])
        check("원본은 건너뛴다", not p.matches, str([m.target for m in p.matches]))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_missing_source_module_is_stated() -> None:
    paths, root = tree(["ModularStage/Mission/MSMissionTask.h"])
    try:
        p = P.counterparts(paths, ["Source/ModularStage/Mission/MSMissionTask.h"])
        check("원본 모듈 부재를 말한다",
              any("원본 모듈을 못 찾았다" in n for n in p.notes), str(p.notes))
        check("ok 가 아니다", not p.ok)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_truncation_is_announced() -> None:
    """[주의] 조용한 절단은 '다 봤다' 로 읽힌다."""
    many = [f"Project_Alpha/A{i}/AlphaFoo.h" for i in range(6)] + ["ModularStage/B/Foo.h"]
    paths, root = tree(many)
    try:
        p = P.counterparts(paths, ["Source/ModularStage/B/Foo.h"], max_each=2)
        check("2개만 실었다", len(p.matches[0].sources) == 2, str(p.matches[0].sources))
        check("자른 것을 말한다", any("만 실었다" in n for n in p.notes), str(p.notes))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── ③ [중요] 원본이 대상 목록으로 새지 않는다 ──────────────────────────────────────

def test_porting_paths_never_leak_into_target_list() -> None:
    """[중요] 새면 워커가 **읽기 전용 모듈을 고친다.** 두 목록이 한 문서에 있으니 실재하는 위험이다."""
    paths, root = tree(REAL_SHAPE)
    try:
        p = P.counterparts(paths, ["Source/ModularStage/Table/TableEnum.h"])
        sec = "\n".join(P.source_section(p))
        # [중요] 대상 파일은 이제 **큐 레코드**에서 온다 (매니페스트 파싱 철거 2026-09-02).
        #    여기서 지킬 계약은 하나로 좁혀졌다: **원본 절이 원본 경로만 싣는가.**
        check("원본 경로가 실린다", "Project_Alpha" in sec, sec[:160])
        # [중요] 원본 절이 실는 것은 **원본 경로**뿐이다 — 대상(트윈) 경로가 아니다
        items = [ln for ln in sec.splitlines() if ln.strip().startswith("- 원본")]
        check("[중요] 원본 절의 항목은 원본 경로뿐이다",
              bool(items) and all("Project_Alpha" in ln for ln in items), str(items)[:200])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    for fn in (test_normalize_strips_measured_prefixes_once,
               test_exact_match_is_preferred,
               test_prefix_match_is_found_but_flagged,
               test_no_counterpart_invents_nothing,
               test_source_module_is_not_its_own_source,
               test_missing_source_module_is_stated,
               test_truncation_is_announced,
               test_porting_paths_never_leak_into_target_list):
        fn()
    total = PASS + FAIL
    print(f"{'OK' if not FAIL else 'FAIL'} test_porting: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
