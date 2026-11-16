"""🔴 테스트 임시 큐 루트는 진짜 레드마인에 쓰지 않는다 (실측 2026-09-13).

## 왜 이 파일이 있나

`_read_redmine_config` 는 큐 루트에 `config.json` 이 없으면 마스터 해석자(URL · 컨테이너 DB 의
API 키 · 레지스트리의 프로젝트)로 폴백한다. 라이브 큐 `~/ax-state` 에 그 파일이 없어서 넣은
폴백인데 **모든 루트**에 걸려 있었다. 그래서 테스트가 임시 루트로 `register_work` 를 부르면,
셸에 `AX_PROJECTS_ROOT` 가 있을 때 **진짜 레드마인에 진짜 이슈**가 났다 — NS 에 198건.

## 못박는 계약

    ① 임시 루트는 폴백하지 않는다 — 원전처럼 `config.json` 만 본다
    ② 라이브 루트(`AX_TASK_QUEUE_ROOT`)는 종전대로 폴백한다 — 서비스는 달라지지 않는다
    ③ 임시 루트라도 `config.json` 에 적힌 설정은 그대로 쓴다 (원전 동작)
    ④ 임시 루트에서 `register_work` 는 이슈 게시를 부르지 않는다

[중요] **이 테스트 자체가 레드마인에 닿지 않는다** — 해석자는 가짜 값을 돌려주고, 게시 함수는
호출만 기록한다. 가드가 깨져도 기록만 늘고 네트워크는 타지 않는다.

    .venv/bin/python master/test_redmine_live_guard.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master import redmine as RM                                           # noqa: E402
from master.task_queue import logic_cleanup as LC                          # noqa: E402
from master.task_queue import persistence as P                             # noqa: E402
from master.task_queue.logic import register_work                          # noqa: E402
from master.task_queue.persistence import TaskIndex                        # noqa: E402

_pass = 0
_fail = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _pass, _fail
    if ok:
        _pass += 1
        print(f"  [완료] {label}")
    else:
        _fail += 1
        print(f"  [실패] {label}" + (f" — {detail}" if detail else ""))


class _Fakes:
    """해석자를 가짜로, 게시를 기록으로 바꾼다. 환경변수도 되돌린다."""

    def __enter__(self):
        self.saved = (RM.base_url, RM.api_key, RM.project_of,
                      LC._redmine_post_issue, os.environ.get(P.STATE_ROOT_ENV))
        RM.base_url = lambda: "http://fake-redmine"
        RM.api_key = lambda: "fake-key"
        RM.project_of = lambda project: "ns"
        self.posts: list = []
        LC._redmine_post_issue = lambda cfg, subject, desc, fv="": (self.posts.append(subject) or 777)
        return self

    def __exit__(self, *exc):
        RM.base_url, RM.api_key, RM.project_of, LC._redmine_post_issue, env = self.saved
        if env is None:
            os.environ.pop(P.STATE_ROOT_ENV, None)
        else:
            os.environ[P.STATE_ROOT_ENV] = env
        return False


def _tmp(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))


def test_live_root_judgement() -> None:
    print("\n[1] 라이브 큐 루트 판정")
    live, other = _tmp("ax-live-"), _tmp("ax-other-")
    with _Fakes():
        os.environ[P.STATE_ROOT_ENV] = str(live)
        check("`AX_TASK_QUEUE_ROOT` 와 같은 루트는 라이브다", P.is_live_queue_root(live))
        check("  경로 표기가 달라도(끝 슬래시) 같으면 라이브다",
              P.is_live_queue_root(str(live) + "/"))
        check("[중요] 다른 루트는 라이브가 아니다", not P.is_live_queue_root(other))


def test_temp_root_does_not_fall_back() -> None:
    print("\n[2] 🔴 임시 루트는 마스터 해석자로 폴백하지 않는다 (NS 198건의 뿌리)")
    live, tmp = _tmp("ax-live-"), _tmp("ax-nowork-")
    with _Fakes():
        os.environ[P.STATE_ROOT_ENV] = str(live)
        cfg = LC._read_redmine_config(tmp, "NS")
        check("[중요] 임시 루트 — url·키·프로젝트가 모두 비어 있다",
              not (cfg["url"] or cfg["api_key"] or cfg["project"]), str(cfg))
        cfg_live = LC._read_redmine_config(live, "NS")
        check("라이브 루트 — 종전대로 해석자 값으로 채운다 (서비스는 안 달라진다)",
              cfg_live == {"url": "http://fake-redmine", "api_key": "fake-key", "project": "ns"},
              str(cfg_live))


def test_config_json_still_honored() -> None:
    print("\n[3] 임시 루트라도 `config.json` 에 적힌 설정은 쓴다 (원전 동작)")
    live, tmp = _tmp("ax-live-"), _tmp("ax-cfg-")
    (tmp / "config.json").write_text(json.dumps({
        "redmine_url": "http://from-config/", "redmine_api_key": "cfg-key",
        "redmine_project": "cfgproj"}), encoding="utf-8")
    with _Fakes():
        os.environ[P.STATE_ROOT_ENV] = str(live)
        cfg = LC._read_redmine_config(tmp, "NS")
        check("`config.json` 값이 그대로 나온다",
              cfg == {"url": "http://from-config", "api_key": "cfg-key", "project": "cfgproj"},
              str(cfg))


def _wait_posts(fakes, want: int, sec: float = 2.0) -> None:
    end = time.monotonic() + sec
    while time.monotonic() < end and len(fakes.posts) < want:
        time.sleep(0.02)


def test_register_work_on_temp_root_posts_nothing() -> None:
    print("\n[4] 🔴 임시 루트의 `register_work` 는 레드마인에 게시하지 않는다")
    live, tmp = _tmp("ax-live-"), _tmp("ax-nowork-")
    with _Fakes() as f:
        os.environ[P.STATE_ROOT_ENV] = str(live)
        register_work(TaskIndex(tmp), title="상호작용", target_repo="/tmp/repo", project="NS",
                      target_branch="task/W1/base")
        _wait_posts(f, 1, sec=1.0)                      # 가드가 깨졌다면 이 사이에 기록된다
        check("[중요] 게시 호출 0회", f.posts == [], str(f.posts))

    print("\n[5] 대조 — 라이브 루트의 `register_work` 는 종전대로 등재 이슈를 만든다")
    with _Fakes() as f:
        os.environ[P.STATE_ROOT_ENV] = str(live)
        register_work(TaskIndex(live), title="상호작용", target_repo="/tmp/repo", project="NS",
                      target_branch="task/W1/base")
        _wait_posts(f, 1)
        check("등재 이슈 게시 1회", f.posts == ["[분산 작업] 상호작용"], str(f.posts))


def test_liveness_is_pinned_at_scheduling() -> None:
    """🔴 `#973` — 비동기 작업의 라이브 판정은 예약 시점에 고정된다.

    실측 2026-11-16: `test_rounds` 가 임시 루트를 `AX_TASK_QUEUE_ROOT` 로 라이브 선언한 틈에, 그 루트에서
    앞서 예약됐지만 늦게 돈 등재 스레드가 진짜 키로 NS #974 를 만들었다. 여기서는 `idx.lock` 을 쥐어
    스레드를 붙잡은 채 환경을 바꾼다 — 게시는 기록 대역이라 네트워크를 타지 않는다.
    """
    print("\n[6] 🔴 예약 뒤 루트가 라이브로 바뀌어도 늦게 도는 스레드는 실제 설정을 쓰지 않는다 (#973)")
    live, tmp = _tmp("ax-live-"), _tmp("ax-late-")
    with _Fakes() as f:
        os.environ[P.STATE_ROOT_ENV] = str(live)
        idx = TaskIndex(tmp)
        with idx.lock:                                  # 등재 스레드는 `with idx.lock:` 에서 기다린다
            register_work(idx, title="상호작용", target_repo="/tmp/repo", project="NS",
                          target_branch="task/W2/base")
            os.environ[P.STATE_ROOT_ENV] = str(tmp)     # 예약 뒤 같은 루트를 라이브로 선언(test_rounds ⓑ 꼴)
        _wait_posts(f, 1, sec=1.0)
        check("[중요] 예약 때 임시였으면 게시 0회", f.posts == [], str(f.posts))

        seen: list = []
        done = threading.Event()

        def job():
            seen.append(LC._read_redmine_config(tmp, "NS"))
            done.set()
        os.environ[P.STATE_ROOT_ENV] = str(live)
        gate = threading.Event()
        LC._spawn_redmine_job(tmp, lambda: (gate.wait(2), job()))
        os.environ[P.STATE_ROOT_ENV] = str(tmp)
        gate.set()
        done.wait(2)
        check("  고정된 판정 — 해석자 폴백 없음", seen and not (seen[0]["url"] or seen[0]["api_key"]),
              str(seen))

        seen.clear()
        done.clear()
        os.environ[P.STATE_ROOT_ENV] = str(tmp)
        LC._spawn_redmine_job(tmp, job)
        done.wait(2)
        check("  대조 — 예약 때 라이브면 종전대로 해석자 값", seen and seen[0]["url"] == "http://fake-redmine",
              str(seen))
        check("  예약 밖(직접 호출)은 종전대로 그때의 판정", LC._read_redmine_config(tmp, "NS")["api_key"]
              == "fake-key")


def main() -> int:
    for fn in (test_live_root_judgement, test_temp_root_does_not_fall_back,
               test_config_json_still_honored, test_register_work_on_temp_root_posts_nothing,
               test_liveness_is_pinned_at_scheduling):
        fn()
    total = _pass + _fail
    print(f"\n{'OK' if not _fail else 'FAIL'} test_redmine_live_guard: {_pass}/{total} 통과")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
