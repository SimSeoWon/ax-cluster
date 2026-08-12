"""`/distribute` — 큰 작업 하나를 분산하는 **사람의 입구** (소 1.3.4).

## 🔴 원샷이 아니다 — 단계마다 사람이 끊는다

    ① plan       분해 계획을 세워 **보여준다**       → 사람이 보고 **자른다**
    ② register   골조 생성 + 🔴 골조 빌드 게이트     → 통과해야 큐에 등재된다
    ③ dispatch   추론 파견 (기본 직렬)               → 응답을 스풀에 쌓고 인계 묶음을 낸다
    ④ (통합자)   적용 → 빌드 판정 → 커밋            → 🔴 **중 1.4. 아직 없다**

자동으로 이어 붙이지 않는 이유가 각 단계마다 있다:

- **분해가 틀리면 N개 조각이 전부 헛일**이 된다. 골조가 틀린 것 다음으로 비싸다. 원전도
  Step 2 에서 플랜을 사용자 승인에 걸었다
- **골조는 모든 병렬 조각의 계약**이다. 틀린 골조는 조각 전부를 오염시키므로 빌드로 세워 본
  뒤에만 등재한다(소 1.1.5 — 첫 실전에서 결함 셋을 잡았다)
- **파견은 돈이다.** 계획을 확인하지 않고 던지면 잘못된 계약으로 N번 산다

## 🔴 계획은 파일로 나온다 — 그래야 **자를 수** 있다

`preview()` 를 눈으로 보는 것만으로는 자를 수 없다. 그래서 `plan` 은 JSON 을 남기고, 사람은
**그 파일에서 조각을 지우거나 순서를 고친다.** `register` 는 그 파일을 읽는다 — 즉 사람의
편집이 **파이프라인의 입력**이다.

⚠️ 분해는 결정적이므로 같은 입력에 같은 계획이 나온다. 파일을 두는 이유는 재현이 아니라
**편집**이다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import decompose, infer, register

PLAN_DIR = "plans"
PLAN_VERSION = 1


class DistributeError(RuntimeError):
    """입구에서 막았다. 🔴 **막은 이유를 사람이 읽는다.**"""


def plan_dir(paths) -> Path:
    return paths.root / PLAN_DIR


def plan_path(paths, slug: str) -> Path:
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (slug or "work"))
    return plan_dir(paths) / f"{safe}.json"


@dataclass
class Staged:
    """한 단계의 결과. 🔴 **다음 단계로 자동으로 가지 않는다.**"""

    stage: str
    ok: bool = True
    text: str = ""
    path: str = ""
    detail: dict = field(default_factory=dict)

    @property
    def next_step(self) -> str:
        if not self.ok:
            return "🔴 다음 단계로 가지 않는다 — 위 사유를 먼저 해결한다"
        return {
            "plan": ("🔴 **다음은 사람이 한다**: 위 계획 파일을 열어 필요 없는 조각을 지우거나 "
                     "순서를 고친다. 그 다음 `register`."),
            "register": ("🔴 **다음은 사람이 확인한다**: 골조 빌드 게이트 판정을 읽는다. "
                         "미확인이면 통과가 아니다. 그 다음 `dispatch`."),
            "dispatch": ("⚠️ **여기서 멈춘다** — 적용·빌드·커밋은 통합자(중 1.4)의 일이고 "
                         "아직 없다. 응답은 스풀에 있다."),
        }.get(self.stage, "")

    def render(self) -> str:
        out = [self.text.rstrip()]
        if self.path:
            out.append(f"\n계획 파일: {self.path}")
        out.append("\n" + self.next_step)
        return "\n".join(x for x in out if x is not None)


# ── ① plan ──────────────────────────────────────────────────────────────────────

def stage_plan(paths, items: list, *, slug: str, instruction: str = "",
               requires=None, write: bool = True) -> Staged:
    """분해 계획을 세워 **보여주고 파일로 남긴다.** 🔴 등록하지 않는다.

    `items` — `[(클래스, 파일)]`. 무엇을 고칠지는 **이 함수 밖에서** 정해진다(트윈 검색·그래프로
    사람과 에이전트가 합의한 결과). 여기서는 그것을 **조각으로 가르고 순서를 매기는** 일만 한다.
    """
    if not items:
        return Staged("plan", ok=False,
                      text="🔴 대상이 비었다 — 어떤 클래스·파일을 고칠지가 먼저다. "
                           "트윈 검색(`search_context_tool`)으로 대상을 정한 뒤 다시 부른다")
    p = decompose.plan(paths, items)
    text = p.preview()
    if not p.ok:
        return Staged("plan", ok=False,
                      text=text + "\n\n🔴 **파견할 수 없는 계획이다** — 같은 물결에서 같은 파일을 "
                                  "두 조각이 고친다. 분해 대상을 다시 고른다")
    st = Staged("plan", text=text, detail={"pieces": len(p.pieces), "waves": len(p.waves())})
    if write:
        d = plan_dir(paths)
        d.mkdir(parents=True, exist_ok=True)
        rec = {
            "version": PLAN_VERSION, "slug": slug, "instruction": instruction,
            "requires": list(requires or []),
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            # 🔴 사람이 여기서 조각을 **지운다**. 그것이 이 파일의 존재 이유다.
            "pieces": [{"stem": x.stem, "classes": list(x.classes), "files": list(x.files),
                        "depth": x.depth, "order": x.order,
                        "depends_on": list(x.depends_on)} for x in p.ordered()],
            "cycles": p.cycles, "notes": p.notes,
        }
        path = plan_path(paths, slug)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
        st.path = str(path)
    return st


def load_plan(paths, slug: str) -> tuple:
    """계획 파일 → `(조각들, 메타)`. 🔴 **사람이 편집한 뒤의 상태**를 읽는다."""
    path = plan_path(paths, slug)
    if not path.is_file():
        raise DistributeError(f"계획 파일이 없다: {path} — `plan` 을 먼저 돌린다")
    rec = json.loads(path.read_text(encoding="utf-8"))
    if int(rec.get("version") or 0) != PLAN_VERSION:
        raise DistributeError(f"계획 파일 형식이 다르다 (version={rec.get('version')}) — "
                              f"`plan` 을 다시 돌린다")
    pieces = [decompose.Piece(stem=x.get("stem", ""), classes=list(x.get("classes") or []),
                              files=list(x.get("files") or []), depth=int(x.get("depth") or 0),
                              order=int(x.get("order") or 0),
                              depends_on=list(x.get("depends_on") or []))
              for x in (rec.get("pieces") or [])]
    if not pieces:
        raise DistributeError(f"계획에 조각이 없다: {path} — 전부 지웠다면 등록할 것이 없다")
    return pieces, rec


# ── ② register — 🔴 골조 게이트를 통과해야 등재된다 ────────────────────────────

def stage_register(paths, *, slug: str, title: str, target_repo: str, target_branch: str = "",
                   gate=None, make_skeleton=None, queue_url=register.DEFAULT_QUEUE,
                   poster=None, searcher=None) -> Staged:
    """사람이 자른 계획을 등록한다. 골조는 없으면 생성되고, `gate` 를 주면 **세워 보고** 등재한다.

    ⚠️ **게이트를 안 주는 것은 통과가 아니라 미확인이다** — 결과에 그렇게 적는다.
    """
    pieces, rec = load_plan(paths, slug)
    plan = decompose.Plan(pieces=pieces)
    v = plan.violations()
    if v:
        return Staged("register", ok=False,
                      text="🔴 편집된 계획이 불변식을 깬다 — 같은 물결에서 같은 파일을 두 조각이 "
                           "고친다:\n" + "\n".join(f"    {x}" for x in v))
    specs = decompose.to_specs(plan, instruction=rec.get("instruction", ""),
                              requires=rec.get("requires") or [])
    reg = register.register_work(
        title, specs, paths=paths, target_repo=target_repo, target_branch=target_branch,
        original_request=rec.get("instruction", "") or title,
        queue_url=queue_url, poster=poster, searcher=searcher,
        make_skeleton=make_skeleton, gate=gate)
    lines = [reg.summary()]
    for t in reg.tasks:
        mark = "✅" if t.ok else "🔴"
        lines.append(f"  {mark} {t.stem} → {t.task_id or t.error}"
                     + (f" · 매니페스트 결손 {len(t.manifest_degraded)}" if t.manifest_degraded
                        else ""))
    if not reg.gate_checked:
        # 🔴 미확인을 통과처럼 읽히게 두지 않는다
        lines.append("")
        lines.append("⚠️ **골조 빌드를 확인하지 않았다.** 게이트 없이 등재된 골조는 컴파일되는지 "
                     "아무도 모른다 — 전임 시스템이 정확히 그 구조에서 깨진 골조를 `origin` 에 "
                     "박았다. `gate=skeleton_gate.run(...)` 를 주고 다시 하는 것이 옳다.")
    return Staged("register", ok=reg.ok, text="\n".join(lines),
                  detail={"work_id": reg.work_id,
                          "tasks": [t.task_id for t in reg.tasks if t.ok],
                          "gate_checked": reg.gate_checked})


# ── ③ dispatch ─────────────────────────────────────────────────────────────────

def stage_dispatch(paths, *, work_id: str = "", limit: int = 4, parallel: bool = False,
                   **kw) -> Staged:
    """추론 파견. 🔴 **기본은 직렬** — 실측이 병렬을 부정한다(12% 빠르고 90% 비쌌다)."""
    hand = infer.run_many(paths, limit=limit, work_id=work_id, parallel=parallel, **kw)
    return Staged("dispatch", ok=bool(hand.ordered()), text=hand.summary(),
                  detail={"passed": len(hand.ordered()), "failed": len(hand.failed),
                          "skipped": len(hand.skipped), "cost_usd": hand.cost_usd})


# ── CLI ──────────────────────────────────────────────────────────────────────────
#
#   python -m master.work.distribute plan     <프로젝트> <슬러그> <클래스:파일…>
#   python -m master.work.distribute register <프로젝트> <슬러그> <제목> <저장소>
#   python -m master.work.distribute dispatch <프로젝트> [work_id] [N]
#
# 🔴 세 단계를 한 명령으로 합치지 않는다 (§ 모듈 머리말).

def main(argv) -> int:
    from ..context_search.paths import resolve
    cmd = (argv[0] if argv else "").strip()
    if cmd not in ("plan", "register", "dispatch"):
        print(__doc__.split("## 🔴 계획은")[0])
        print("  plan | register | dispatch")
        return 2
    paths = resolve(argv[1] if len(argv) > 1 else "")

    if cmd == "plan":
        slug = argv[2] if len(argv) > 2 else "work"
        items = []
        for a in argv[3:]:
            cls, _, f = a.partition(":")
            if not f:
                print(f"🔴 `클래스:파일` 형식이 아니다: {a}")
                return 2
            items.append((cls, f))
        st = stage_plan(paths, items, slug=slug)
    elif cmd == "register":
        if len(argv) < 5:
            print("  register <프로젝트> <슬러그> <제목> <저장소>")
            return 2
        st = stage_register(paths, slug=argv[2], title=argv[3], target_repo=argv[4])
    else:
        st = stage_dispatch(paths, work_id=argv[2] if len(argv) > 2 else "",
                            limit=int(argv[3]) if len(argv) > 3 else 4)
    print(st.render())
    return 0 if st.ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
