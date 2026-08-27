"""`#325` — 식별자는 **언제나 문자열**이다 (재기동 왕복).

## [중요] 무엇이 문제였나

`task_id` 는 `secrets.token_hex(4)` — 8자 hex 다. 8자가 **전부 숫자**일 확률이
`(10/16)^8 = 2.33%` 이고, 프론트매터 파서(`_parse_scalar`)가 `isdigit()` 이면 `int()` 로
바꾼다. 그래서 재기동(`TaskIndex.rebuild()`) 뒤 그 태스크는 인덱스에 **int 키**로 앉고,
문자열 조회가 전부 빗나갔다 — `GET /tasks/<id>` · submit · heartbeat 가 다 404.

**flake 로 한 번 넘겼다가** 30회 돌려 3/30 재현해서 잡았다. 간헐 실패를 flake 로 접는 것이
이 부류를 숨긴다.

## 고친 모양 (사용자 결정 2026-08-28: ⓐ+ⓑ 둘 다)

    쓰는 쪽  `_emit_scalar` 가 **왕복이 안 되는 문자열을 인용**한다 → 새 레코드는 안 깨진다
    읽는 쪽  `_as_id` 가 id 를 str 로 고정한다              → **이미 있는 파일도 산다**

한쪽만 하면 반쪽이다: 쓰는 쪽만 하면 옛 레코드가 남고, 읽는 쪽만 하면 선행 0 이 붙은 값을
못 되살린다(그건 어차피 복원 불가 — 아래 참조).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.task_queue.logic import claim_task, register_task, register_work    # noqa: E402
from master.task_queue.persistence import (                                     # noqa: E402
    TaskIndex, _as_id, _build_md, _emit_scalar, _parse_frontmatter, _parse_scalar,
)

_fail = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _fail
    if ok:
        print(f"  [완료] {label}")
    else:
        _fail += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def test_scalar_roundtrip() -> None:
    print("\n[1] 스칼라 왕복 — 쓴 대로 읽힌다 (쓰는 쪽 ⓑ)")
    for s in ("43144512", "0043144512", "4314a512", "20260827_2307", "abc", "-1", "0"):
        back = _parse_scalar(_emit_scalar(s))
        check(f"  {s!r} 왕복", back == s, f"→ {back!r} ({type(back).__name__})")
    check("[주의] 진짜 int 는 int 로 남는다 (epoch 등)", _parse_scalar(_emit_scalar(7)) == 7)
    check("  bool·null 도 그대로", _parse_scalar(_emit_scalar(True)) is True
          and _parse_scalar(_emit_scalar(None)) is None)


def test_frontmatter_roundtrip() -> None:
    print("\n[2] 프론트매터 왕복 — 전부-숫자 id 가 살아남는다")
    meta = {"task_id": "43144512", "work_id": "00112233", "epoch": 3, "status": "claimed"}
    back, _ = _parse_frontmatter(_build_md(meta, "본문\n"))
    check("[중요] task_id 가 str 로 돌아온다",
          back["task_id"] == "43144512" and isinstance(back["task_id"], str),
          f"{back.get('task_id')!r}")
    check("[중요] 선행 0 이 보존된다", back["work_id"] == "00112233", f"{back.get('work_id')!r}")
    check("[주의] epoch 은 여전히 int", back["epoch"] == 3 and isinstance(back["epoch"], int))


def test_as_id() -> None:
    print("\n[3] 읽는 쪽 정규화 (ⓐ) — 옛 레코드도 산다")
    check("int 를 str 로", _as_id(43144512) == "43144512")
    check("str 은 그대로", _as_id("4314a512") == "4314a512")
    check("None 은 빈 문자열 (키가 안 된다)", _as_id(None) == "")


def test_rebuild_survives_numeric_id() -> None:
    """[중요] 이 파일의 목적 — **재기동 뒤 문자열 id 로 조회되나.**"""
    print("\n[4] [중요] 재기동 왕복 — 전부-숫자 id 를 강제로 심는다")
    root = Path(tempfile.mkdtemp(prefix="ax-325-"))
    idx = TaskIndex(root)
    w = register_work(idx, title="t", target_repo="/tmp/repo")
    register_task(idx, work_id=w["work_id"], type="build", task_data={}, stem="b")
    t = claim_task(idx, "w-.2", capabilities=["ue5"], types=["build"])
    old_tid = t["task_id"]

    # 파일을 **옛 모양**(인용 없는 전부-숫자 id)으로 바꿔 심는다 — 마이그레이션 대상 재현
    path = idx.task_paths[old_tid]
    # [주의] **인용 여부를 가정하지 않는다** — 무작위 id 가 전부 숫자면 `#325` 의 왕복 인용이
    #    걸려 파일에는 `task_id: "12345678"` 로 저장된다. 인용 없는 형태만 찾으면 2.33% 확률로
    #    치환이 빗나가 이 테스트가 **간헐 실패**한다(실제로 그랬다 — 이 파일이 잡으려는 결함과
    #    같은 부류다). 줄 전체를 정규식으로 갈아 끼운다.
    import re as _re
    text = _re.sub(r"^task_id:.*$", "task_id: 43144512", path.read_text(encoding="utf-8"),
                   count=1, flags=_re.M)
    path.write_text(text, encoding="utf-8")

    again = TaskIndex(root)
    again.rebuild()
    check("[중요] 문자열 키로 조회된다 (종전에는 KeyError)", "43144512" in again.tasks,
          str(list(again.tasks)[:3]))
    check("  레코드의 task_id 도 str 이다",
          isinstance(again.tasks.get("43144512", {}).get("task_id"), str),
          repr(again.tasks.get("43144512", {}).get("task_id")))
    check("  int 키로는 안 앉아 있다", 43144512 not in again.tasks)
    check("  경로도 같이 잡힌다", "43144512" in again.task_paths)


def main() -> int:
    for fn in (test_scalar_roundtrip, test_frontmatter_roundtrip, test_as_id,
               test_rebuild_survives_numeric_id):
        fn()
    total = 17
    print(f"\n{'OK' if not _fail else '[실패]'} test_id_typing: {total - _fail}/{total} 통과")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
