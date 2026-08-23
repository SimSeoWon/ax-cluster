"""서비스 신선도 판정 (`#301`) — pytest 없이 그대로 실행.

    .venv/bin/python master/test_service_freshness.py

[중요] 지키는 불변식:
   1. 기동 뒤에 코드가 바뀌면 **stale 이라고 말한다** (실측: 하루 동안 옛 코드로 돌았다)
   2. 판정 근거는 **`ExecMainStartTimestamp`** — `is-active` 도 종료코드도 아니다
   3. **못 읽었으면 「최신」으로 접지 않는다** (모르는 것을 괜찮다고 하지 않는다)
   4. **발동형(oneshot)은 판정 대상이 아니다** — 다음 발동이 곧 새 코드다
   5. 조용할 때는 **아무 줄도 내지 않는다** (늘 빨간 줄이 있으면 아무도 안 본다)
   6. [주의] **자동 재기동을 하지 않는다** — 승인 사항이다 (`docs/11` §11.5)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import service_freshness as F      # noqa: E402

PASS = FAIL = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {label}")
    else:
        FAIL += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


def fake(started: str = "Sat 2026-08-23 02:19:20 KST", rc: int = 0, epoch: str = "1787418000"):
    """가짜 systemctl·date. **실 서비스를 건드리지 않는다.**"""
    class R:
        def __init__(self, code, out):
            self.returncode, self.stdout = code, out

    def run(cmd):
        if cmd[0] == "systemctl":
            return R(rc, started)
        if cmd[0] == "date":
            return R(0, epoch)
        return R(1, "")
    return run


def main() -> int:
    print("\n[1] 기동 뒤 코드가 바뀌면 stale 이라고 말한다")
    # 기동 = 아주 옛날(epoch 0 근처) → 저장소 코드가 반드시 더 새롭다
    v = F.check("ax-task-queue", runner=fake(epoch="1"))[0]
    check("stale 로 판정한다", v.stale, f"{v.started} vs {v.newest}")
    check("무엇이 바뀌었는지 파일로 말한다", v.newest_file.endswith(".py"), v.newest_file)
    check("[중요] 재기동 명령을 그대로 준다",
          "systemctl restart ax-task-queue" in v.line, v.line)

    print("\n[2] 기동이 코드보다 새로우면 조용하다")
    v = F.check("ax-task-queue", runner=fake(epoch="99999999999"))[0]
    check("stale 아니다", not v.stale, v.line)
    check("「지금 코드다」라고 말한다", "지금 코드" in v.line, v.line)

    print("\n[3] [중요] 못 읽었으면 「최신」으로 접지 않는다")
    v = F.check("ax-task-queue", runner=fake(rc=1))[0]
    check("사유를 남긴다", bool(v.why), v.line)
    check("  stale 로도 단정하지 않는다 (모르는 것은 모른다)", not v.stale, v.line)
    v2 = F.check("ax-task-queue", runner=fake(started="", epoch="x"))[0]
    check("기동 시각이 비면 사유를 남긴다", bool(v2.why), v2.line)

    print("\n[4] [중요] 발동형(oneshot)은 판정 대상이 아니다")
    units = set(F.RESIDENT)
    check("상주만 잰다", units == {"ax-task-queue", "ax-broker", "ax-projects"}, str(units))
    check("[주의] 발동형을 이름으로 적어 둔다 (빠뜨린 것과 일부러 뺀 것을 가른다)",
          "ax-indexer" in F.TRIGGERED and "ax-status" in F.TRIGGERED, str(F.TRIGGERED))
    for t in F.TRIGGERED:
        check(f"  `{t}` 는 상주 목록에 없다", t not in F.RESIDENT)

    print("\n[5] 조용할 때는 아무 줄도 내지 않는다")
    lines = F.stale_lines(runner=fake(epoch="99999999999"))
    check("[중요] 빈 목록", lines == [], str(lines))

    print("\n[6] [주의] 코드 경로를 넓게 잡지 않는다")
    for unit, paths in F.RESIDENT.items():
        check(f"  `{unit}` 의 경로가 선언돼 있다", bool(paths) and all(
            (F.REPO / p).is_dir() for p in paths), str(paths))

    print("\n[7] [주의] 자동 재기동을 하지 않는다 (승인 사항)")
    src = (Path(F.__file__)).read_text(encoding="utf-8")
    check("[중요] 모듈에 restart 실행이 없다",
          "systemctl\", \"restart" not in src and "'restart'" not in src,
          "재기동을 스스로 하는 코드가 있다")
    check("  그 이유를 문서로 적어 뒀다", "§11.5" in src)

    print(f"\n{'='*46}\n통과 {PASS} · 실패 {FAIL}\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
