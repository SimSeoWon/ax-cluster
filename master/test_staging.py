"""온톨로지 스테이징 편집 세션 (소 3.1.7 · `#190`) — 원전 η.9 이식분.

검증하는 것:

    ① 편집 중 🔴 **라이브가 안 바뀐다** (DoubleBufferedIndex 패턴의 파일시스템 버전)
    ② `begin` 은 **멱등** — 두 번 부르면 `resumed`
    ③ 🔴 세션을 **강제하지 않는다** — 세션이 없으면 `working_pkg` 가 라이브를 준다
    ④ 🔴 세션 메타는 staging **밖**의 형제다 (안에 두면 rename 때 pkg 를 오염시킨다)
    ⑤ commit — rename swap · 백업 **1세대만** · 색인 **1회**
    ⑥ 🔴 세션 중 라이브가 바뀌면 **막지 않고 알린다** (원전 판단: 저빈도, 과설계 방지)
    ⑦ discard — staging 만 사라지고 라이브 무영향
    ⑧ 세션 없이 commit/discard 는 `no_session` (조용히 성공하지 않는다)
    ⑨ 🔴 경로 탈출을 막는다

`.venv/bin/python master/test_staging.py`
"""
from __future__ import annotations

import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from master.ontology import staging as S                        # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


@dataclass
class Paths:
    ontology: Path


def fx(tmp) -> Paths:
    p = Paths(ontology=Path(tmp) / "ontology")
    d = p.ontology / "domains" / "MissionRuntime"
    (d / "L1" / "objects").mkdir(parents=True)
    (d / "domain.yaml").write_text("name: MissionRuntime\n", encoding="utf-8")
    (d / "L1" / "objects" / "UThing.yaml").write_text("name: UThing\nv: 1\n", encoding="utf-8")
    return p


# ── ①②③④ 세션 ───────────────────────────────────────────────────────────────

def test_editing_staging_leaves_live_alone():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        live = S.pkg_path(p, "MissionRuntime")
        before = (live / "L1" / "objects" / "UThing.yaml").read_text(encoding="utf-8")

        r = S.begin(p, "MissionRuntime")
        check("② 세션이 시작된다", r["status"] == "started", str(r))
        work = S.working_pkg(p, "MissionRuntime")
        check("① 편집 대상이 staging 이다", work.name.endswith(S.STAGING_SUFFIX), str(work))

        (work / "L1" / "objects" / "UThing.yaml").write_text("name: UThing\nv: 2\n",
                                                            encoding="utf-8")
        check("① 🔴 라이브가 안 바뀌었다",
              (live / "L1" / "objects" / "UThing.yaml").read_text(encoding="utf-8") == before)

        r2 = S.begin(p, "MissionRuntime")
        check("② 두 번째 begin 은 resumed (멱등)", r2["status"] == "resumed", str(r2))


def test_no_session_means_live():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        work = S.working_pkg(p, "MissionRuntime")
        check("③ 🔴 세션이 없으면 라이브를 준다 (세션을 강제하지 않는다)",
              not work.name.endswith(S.STAGING_SUFFIX), str(work))
        check("③ in_session 이 False", not S.in_session(p, "MissionRuntime"))


def test_meta_lives_outside_staging():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        S.begin(p, "MissionRuntime")
        pkg = S.pkg_path(p, "MissionRuntime")
        stg, meta = S.staging_paths(pkg)
        check("④ 메타가 존재한다", meta.exists(), str(meta))
        check("④ 🔴 메타가 staging **밖**이다 (안이면 rename 때 pkg 를 오염시킨다)",
              meta.parent == stg.parent and not str(meta).startswith(str(stg) + "/"),
              f"meta={meta} staging={stg}")


def test_missing_domain_is_a_fact():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        r = S.begin(p, "NoSuchDomain")
        check("없는 도메인은 not_found", r["status"] == "not_found", str(r))


# ── ⑤⑥ commit ────────────────────────────────────────────────────────────────

def test_commit_swaps_and_indexes_once():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        S.begin(p, "MissionRuntime")
        work = S.working_pkg(p, "MissionRuntime")
        (work / "L1" / "objects" / "UThing.yaml").write_text("name: UThing\nv: 2\n",
                                                            encoding="utf-8")
        calls = []
        r = S.commit(p, "MissionRuntime", sync=lambda _p: calls.append(1) or "synced")
        check("⑤ committed", r["status"] == "committed", str(r))

        live = S.pkg_path(p, "MissionRuntime")
        check("⑤ 라이브에 편집이 반영됐다",
              "v: 2" in (live / "L1" / "objects" / "UThing.yaml").read_text(encoding="utf-8"))
        check("⑤ staging 이 사라졌다", not S.in_session(p, "MissionRuntime"))
        check("⑤ 백업이 남았다", Path(r["backup"]).is_dir(), r["backup"])
        check("⑤ 백업에는 옛 내용이 있다",
              "v: 1" in (Path(r["backup"]) / "L1" / "objects" / "UThing.yaml")
              .read_text(encoding="utf-8"))
        check("⑤ 🔴 색인은 **한 번만**", len(calls) == 1, str(len(calls)))
        _, meta = S.staging_paths(live)
        check("⑤ 메타가 정리됐다", not meta.exists())


def test_backup_keeps_one_generation():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        for v in (2, 3):
            S.begin(p, "MissionRuntime")
            w = S.working_pkg(p, "MissionRuntime")
            (w / "L1" / "objects" / "UThing.yaml").write_text(f"name: UThing\nv: {v}\n",
                                                             encoding="utf-8")
            S.commit(p, "MissionRuntime")
        live = S.pkg_path(p, "MissionRuntime")
        bak = live.with_name(live.name + S.BACKUP_SUFFIX)
        check("⑤ 백업은 1세대만 (무한 누적 방지)",
              "v: 2" in (bak / "L1" / "objects" / "UThing.yaml").read_text(encoding="utf-8"),
              "직전 것이어야 한다")
        check("⑤ .bak.bak 같은 것이 안 생긴다",
              not bak.with_name(bak.name + S.BACKUP_SUFFIX).exists())


def test_live_change_during_session_is_reported_not_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        S.begin(p, "MissionRuntime")
        live = S.pkg_path(p, "MissionRuntime")
        time.sleep(0.01)
        # 백그라운드 재합성 흉내 — 라이브 manifest 를 건드린다
        (live / "domain.yaml").write_text("name: MissionRuntime\ntouched: 1\n", encoding="utf-8")

        r = S.commit(p, "MissionRuntime")
        check("⑥ 🔴 막지 않는다 — 커밋은 성공한다", r["status"] == "committed", str(r))
        check("⑥ 바뀐 사실을 알린다", r.get("live_changed_during_session") is True, str(r))
        check("⑥ 사유를 문장으로 남긴다", "막지 않았다" in (r.get("note") or ""), str(r.get("note")))


def test_index_failure_does_not_undo_the_swap():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        S.begin(p, "MissionRuntime")

        def boom(_p):
            raise RuntimeError("색인 터짐")

        r = S.commit(p, "MissionRuntime", sync=boom)
        check("⑤ 색인이 터져도 커밋은 끝났다", r["status"] == "committed", str(r))
        check("⑤ 색인 오류를 값으로 싣는다", "터짐" in str(r["index"].get("error", "")),
              str(r["index"]))
        check("⑤ 교체는 되돌아가지 않았다", not S.in_session(p, "MissionRuntime"))


# ── ⑦⑧⑨ discard · 방어 ──────────────────────────────────────────────────────

def test_discard_leaves_live_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        live = S.pkg_path(p, "MissionRuntime")
        before = (live / "L1" / "objects" / "UThing.yaml").read_text(encoding="utf-8")
        S.begin(p, "MissionRuntime")
        w = S.working_pkg(p, "MissionRuntime")
        (w / "L1" / "objects" / "UThing.yaml").write_text("name: UThing\nv: 99\n",
                                                          encoding="utf-8")
        r = S.discard(p, "MissionRuntime")
        check("⑦ discarded", r["status"] == "discarded", str(r))
        check("⑦ 🔴 라이브 무영향",
              (live / "L1" / "objects" / "UThing.yaml").read_text(encoding="utf-8") == before)
        check("⑦ staging 이 사라졌다", not S.in_session(p, "MissionRuntime"))
        _, meta = S.staging_paths(live)
        check("⑦ 메타도 정리됐다", not meta.exists())


def test_no_session_is_reported():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        check("⑧ 세션 없이 commit → no_session",
              S.commit(p, "MissionRuntime")["status"] == "no_session")
        check("⑧ 세션 없이 discard → no_session",
              S.discard(p, "MissionRuntime")["status"] == "no_session")


def test_path_escape_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        for bad in ("../evil", "a/b", "", ".hidden", "..", "x\\y"):
            try:
                S.pkg_path(p, bad)
                check(f"⑨ 경로 탈출 거부 ({bad!r})", False, "통과해 버렸다")
            except S.StagingError:
                check(f"⑨ 경로 탈출 거부 ({bad!r})", True)


def test_status_lists_open_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        p = fx(tmp)
        check("열린 세션이 없으면 빈 목록", S.status(p)["sessions"] == [])
        S.begin(p, "MissionRuntime")
        st = S.status(p)
        check("🔴 열린 세션을 찾아 준다 (잊으면 위험하다)",
              len(st["sessions"]) == 1 and st["sessions"][0]["domain"] == "MissionRuntime",
              str(st))


def main() -> int:
    for fn in (test_editing_staging_leaves_live_alone, test_no_session_means_live,
               test_meta_lives_outside_staging, test_missing_domain_is_a_fact,
               test_commit_swaps_and_indexes_once, test_backup_keeps_one_generation,
               test_live_change_during_session_is_reported_not_blocked,
               test_index_failure_does_not_undo_the_swap,
               test_discard_leaves_live_untouched, test_no_session_is_reported,
               test_path_escape_is_refused, test_status_lists_open_sessions):
        fn()
    total = PASS + FAIL
    print(f"{'✅' if not FAIL else '🔴'} test_staging: {PASS}/{total} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
