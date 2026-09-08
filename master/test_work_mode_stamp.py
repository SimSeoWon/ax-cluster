"""`#389` — 지휘자 모드가 **work 에 박히고**, 전역을 바꿔도 도는 work 은 안 흔들린다."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from master.task_queue.persistence import TaskIndex                    # noqa: E402
from master.task_queue.logic import register_work                      # noqa: E402
from master.work import autodispatch as AD                             # noqa: E402

PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [완료] {name}")
    else:
        FAIL += 1
        print(f"  [중요] 실패: {name}" + (f" — {got}" if got else ""))


def _idx():
    return TaskIndex(Path(tempfile.mkdtemp(prefix="ax-wmode-")))


print("[1] 큐 레코드 — 스탬프가 박힌다")
idx = _idx()
w = register_work(idx, title="t", target_repo="R", worker_mode="codex")
check("등재 성공", w.get("ok"), str(w))
meta = idx.works[w["work_id"]]
check("🔴 worker_mode 가 레코드에 있다", meta.get("worker_mode") == "codex",
      str(meta.get("worker_mode")))

w2 = register_work(idx, title="t2", target_repo="R", slug="t2")
check("안 주면 None (등재 쪽이 채운다)", idx.works[w2["work_id"]].get("worker_mode") is None,
      str(idx.works[w2["work_id"]].get("worker_mode")))

print("[2] 🔴 전역을 바꿔도 박힌 값은 안 흔들린다")
before = idx.works[w["work_id"]].get("worker_mode")
from master.work import mode as MODE                                   # noqa: E402
_saved = MODE.STATE
try:
    MODE.STATE = Path(tempfile.mkdtemp(prefix="ax-mode-")) / "mode.json"
    MODE.set_mode("lane", why="테스트", by="t")
    check("전역이 lane 이 됐다", MODE.current()[0] == "lane", MODE.current()[0])
    check("🔴 그런데 work 스탬프는 codex 그대로",
          idx.works[w["work_id"]].get("worker_mode") == before == "codex",
          str(idx.works[w["work_id"]].get("worker_mode")))
finally:
    MODE.STATE = _saved

print("[3] 등재가 전역값을 스탬프한다 (`work/register.create_work`)")
from master.work import register as REG                                # noqa: E402
sent = {}


def _poster(url, payload):
    sent.update(payload)
    return {"work_id": "W1"}


class _Paths:
    name = "NS"
    repo = "/tmp/x"


_saved = MODE.STATE
try:
    MODE.STATE = Path(tempfile.mkdtemp(prefix="ax-mode2-")) / "mode.json"
    MODE.set_mode("codex", why="테스트", by="t")
    REG.create_work("t", paths=_Paths(), target_repo="R", poster=_poster)
    check("🔴 안 줬는데 전역값이 실렸다", sent.get("worker_mode") == "codex",
          str(sent.get("worker_mode")))
    sent.clear()
    REG.create_work("t", paths=_Paths(), target_repo="R", worker_mode="lane", poster=_poster)
    check("🔴 명시가 전역을 이긴다", sent.get("worker_mode") == "lane", str(sent.get("worker_mode")))
finally:
    MODE.STATE = _saved

print("[4] 파견이 스탬프를 명시로 넘긴다 (`autodispatch`)")
got = {}


def _fake_many(paths, **kw):
    got.update(kw)

    class H:
        items, skipped, note = [], [], ""
    return H()


def _api(method, path, payload=None):
    if path.startswith("/api/v1/works/"):
        return {"work": {"work_id": "W1", "worker_mode": "codex", "round": 1,
                         "merge_status": "in_progress", "target_branch": "task/W1/base"},
                "tasks": [{"task_id": "a", "status": "pending"}]}
    return {}


check("work_meta 가 스탬프를 읽는다",
      AD.work_meta("W1", api=_api).get("worker_mode") == "codex")

# [주의] `should_dispatch` 는 실 트윈·실 저장소를 읽는다 — 여기서 재려는 것은 **인자 전달**이라
#    그 관문만 주입으로 통과시킨다. 관문 자체는 `test_autodispatch` 가 잰다.
_saved_sd = AD.should_dispatch
try:
    AD.should_dispatch = lambda paths, wid, api=None: (True, "테스트")
    AD.dispatch(_Paths(), "W1", api=_api, runner_many=_fake_many)
finally:
    AD.should_dispatch = _saved_sd

check("🔴 mode 가 **명시로** 넘어갔다", got.get("mode") == "codex", str(got.get("mode")))
check("병렬도 여전히 명시다", got.get("parallel") is True, str(got.get("parallel")))

# 스탬프가 없는 옛 work — 종전대로 전역을 읽게 빈 값이 가야 한다
got.clear()


def _api_old(method, path, payload=None):
    if path.startswith("/api/v1/works/"):
        return {"work": {"work_id": "W0", "round": 1, "merge_status": "in_progress"},
                "tasks": [{"task_id": "a", "status": "pending"}]}
    return {}


try:
    AD.should_dispatch = lambda paths, wid, api=None: (True, "테스트")
    AD.dispatch(_Paths(), "W0", api=_api_old, runner_many=_fake_many)
finally:
    AD.should_dispatch = _saved_sd
check("🔴 스탬프 없는 옛 work 은 빈 값 — 종전 동작(전역 읽기) 유지",
      got.get("mode") == "", repr(got.get("mode")))

print()
print("=" * 46)
print(f"통과 {PASS} · 실패 {FAIL}")
print("=" * 46)
sys.exit(1 if FAIL else 0)
