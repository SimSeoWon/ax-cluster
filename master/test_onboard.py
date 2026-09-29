"""온보딩 판정·실행기 (`#259`) — 계획은 읽기 전용, 실행은 승인 뒤 서버→클라를 잇는다.

[중요] **판정기부터 검증하는 순서다.** 새 프로젝트에 처음 돌리기 전에, 이미 초기화된 프로젝트
(ModularStage)에서 여섯 단계가 **전부 참**으로 나오는지 · 아무것도 없는 프로젝트에서 **남은 것을
이름으로** 답하는지 본다. 판정이 틀린 실행기는 「했다」고 거짓 보고한다.

`python3 master/test_onboard.py`
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def _sandbox():
    """빈 Gitea bare + 빈 레지스트리. [주의] `AX_PROJECTS_ROOT` 는 **호출 시점**에 읽히므로
    환경변수로 돌릴 수 있다(`GITEA_REPO_ROOT` 는 임포트 상수라 `bare_path` 를 명시한다)."""
    tmp = Path(tempfile.mkdtemp(prefix="ax-onboard-test-"))
    (tmp / "gitea" / "o" / "r.git").mkdir(parents=True)
    (tmp / "gitea" / "o" / "r.git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (tmp / "root").mkdir()
    (tmp / "root" / "projects.yaml").write_text('version: 1\nactive: ""\nprojects: []\n',
                                                encoding="utf-8")
    return tmp


def test_step_source_is_spec() -> None:
    """[중요] 단계 목록을 `onboard.py` 가 **다시 적지 않는다** — 선언은 `spec.SERVER_STEPS` 다."""
    from master.client import spec
    from master.projects import onboard

    check("판정기가 선언의 모든 단계를 덮는다",
          set(onboard.PROBES) == {s.key for s in spec.SERVER_STEPS},
          f"{set(onboard.PROBES)} vs {[s.key for s in spec.SERVER_STEPS]}")

    src = (Path(__file__).resolve().parent / "projects" / "onboard.py").read_text(
        encoding="utf-8")
    # 단계 순서를 여기 리터럴로 다시 적으면 두 벌이 된다
    check("순서를 다시 적지 않는다 (spec 을 돈다)", "for step in spec.SERVER_STEPS" in src)


def test_uninitialized() -> None:
    """등록조차 안 된 프로젝트 → 여섯 단계 전부 남았다고 **이름으로** 답한다."""
    from master.projects.onboard import plan
    tmp = _sandbox()
    keep = os.environ.get("AX_PROJECTS_ROOT")
    try:
        os.environ["AX_PROJECTS_ROOT"] = str(tmp / "root")
        d = plan("없는것", hosts=False).to_dict()
        # [주의] 개수를 박지 않는다 — 단계가 늘면(2026-08-22 에 `hook` 이 늘었다) 칸이 조용히
        #    거짓이 된다. **사양에서 세는 것**이 옳다.
        from master.client import spec
        check("모든 단계가 남았다", len(d["remaining"]) == len(spec.SERVER_STEPS),
              f"{d['remaining']} vs {len(spec.SERVER_STEPS)}")
        check("이름으로 답한다", "bare" in d["remaining"] and "index" in d["remaining"])
        # [중요] 선결이 깨진 단계는 **판정을 시도하지 않는다** — "비었다" 와 "잴 수 없다" 는 다르다
        blocked = [s for s in d["steps"] if s.get("blocked")]
        # [주의] 분모는 `SERVER_STEPS` 를 따른다 — 숫자를 박으면 단계가 늘 때마다 갈린다
        #    (`#273` 이 「4/6」으로 잘못 보고한 그 부류). **register 가 깨지면 트윈 경로를
        #    모르므로 그것을 쓰는 단계 전부**가 blocked 다 — `hook` 은 bare 만 보므로 제외.
        # [주의] **여기도 이름을 박아 뒀다** — `#330` 이 `guard` 를 넣자 5 vs 6 으로 깨졌다.
        #    성질로 센다: `bare`·`register`·`hook` 은 `(reg, name)` 을 받아 트윈 경로가 필요
        #    없고, **그 밖 전부**가 register 미완이면 blocked 다.
        _no_paths = {"bare", "register", "hook"}
        expect_blocked = sum(1 for st in spec.SERVER_STEPS if st.key not in _no_paths)
        check("[중요] 선결 미충족은 blocked 로 갈린다", len(blocked) == expect_blocked,
              f"{len(blocked)} vs {expect_blocked}")
        check("[주의] hook 은 blocked 가 아니다 — 레지스트리만 있으면 잴 수 있다",
              not next(s for s in d["steps"] if s["step"] == "hook").get("blocked"))
        check("blocked 가 사유를 말한다", all("아직이다" in s["blocked"] for s in blocked))
        check("판정 실패가 아니라 계획이다 (ok=True)", d["ok"], str(d))
    finally:
        if keep is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = keep


def test_registered_only() -> None:
    """등록만 된 프로젝트 → `bare`·`register` 만 참, 나머지 넷이 남는다."""
    from master.projects.logic import register_project
    from master.projects.onboard import plan
    tmp = _sandbox()
    keep = os.environ.get("AX_PROJECTS_ROOT")
    try:
        os.environ["AX_PROJECTS_ROOT"] = str(tmp / "root")
        register_project("Fresh", "o/r", bare_path=str(tmp / "gitea" / "o" / "r.git"))
        d = plan("Fresh", hosts=False).to_dict()
        by = {s["step"]: s for s in d["steps"]}
        check("bare 통과", by["bare"]["done"], str(by["bare"]))
        check("register 통과", by["register"]["done"], str(by["register"]))
        check("clone 은 남았다", not by["clone"]["done"] and "클론이 없다" in by["clone"]["detail"],
              str(by["clone"]))
        # [주의] **이름 목록을 박지 않는다 — 사양에서 유도한다.** 같은 파일의 다른 검사가
        #    이미 *"개수를 박지 않는다"* 라고 적어 뒀는데 여기만 이름을 박아 뒀고, `#330` 이
        #    `guard` 를 넣자 조용히 깨졌다. 「이름으로 답한다」는 성질은 그대로 잰다.
        from master.client import spec as _spec
        _done = {"bare", "register"}
        check("남은 것을 이름으로",
              d["remaining"] == [s.key for s in _spec.SERVER_STEPS if s.key not in _done],
              str(d["remaining"]))
        # [중요] clone 이 아직이면 그래프·합성·색인은 **잴 수 없다** (0건과 구분한다)
        check("[중요] clone 미완이 뒤 셋을 blocked 로 만든다",
              all(by[k].get("blocked") for k in ("graph", "synth", "index")),
              str({k: by[k].get("blocked") for k in ("graph", "synth", "index")}))
        # 🔴 `profile` 은 클론을 기다리지 않는다 (`#693`) — 막힘이면 러너 없는 단계라 `run` 이
        #    시작부터 거절하고, 클론을 못 하니 판정도 못 한다(교착). 새 프로젝트에서만 보인다.
        check("🔴 profile 은 clone 미완에도 blocked 가 아니다 (교착 방지)",
              not by["profile"].get("blocked"), str(by["profile"]))

        # 빈 디렉토리를 통과시키지 않는다
        (tmp / "root" / "Fresh" / "repo").mkdir()
        by2 = {s["step"]: s for s in plan("Fresh", hosts=False).to_dict()["steps"]}
        check("[중요] 빈 디렉토리는 클론이 아니다",
              not by2["clone"]["done"] and "git 저장소가 아니다" in by2["clone"]["detail"],
              str(by2["clone"]))
    finally:
        if keep is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = keep


def test_guard_step_is_the_write_surface(*, _tmp=None) -> None:
    """[중요] `#330` — 온보딩이 **pre-push 쓰기 가드**를 깐다.

    이 단계가 없어서 NS 가 무방비로 돌았다(실측 2026-08-28): 가드 원본은 2026-08-14 에
    코드로 들어왔지만 온보딩 단계가 아니었고, 그 뒤 온보딩한 NS 는 그것을 지나지 않았다.
    [주의] **`hook` 과 다른 것이다** — 그쪽은 Gitea 서버의 post-receive(받은 push → 재색인),
    이쪽은 마스터 자기 클론의 pre-push(나가는 push 를 막는다). 이름이 겹쳐 있는 줄 알았다.
    """
    from master.client import spec as _spec
    from master.projects import onboard as _ob
    keys = [s.key for s in _spec.SERVER_STEPS]
    check("사양에 `guard` 단계가 있다", "guard" in keys, str(keys))
    check("[중요] `hook` 과 별개 단계다 (이름이 겹치지 않는다)",
          "hook" in keys and keys.index("guard") != keys.index("hook"), str(keys))
    # [주의] LFS 저장소를 클론하면 git-lfs 가 pre-push 를 넣는다 — 먼저 깔면 클론이 덮는다
    check("[주의] `guard` 는 `clone` **뒤**다 (LFS 훅이 덮지 못하게)",
          keys.index("guard") > keys.index("clone"), str(keys))
    check("판정기·실행기가 배선돼 있다",
          "guard" in _ob.PROBES and "guard" in _ob.RUNNERS,
          f"{list(_ob.PROBES)} / {list(_ob.RUNNERS)}")

    # [중요] **판정을 두 벌로 만들지 않았다** — `#329` 의 `hook_status` 를 그대로 쓴다
    import inspect
    src = inspect.getsource(_ob._probe_guard)
    check("[중요] `hook_status` 를 재사용한다 (판정이 한 벌이다)", "hook_status" in src, src[:120])
    check("  설치기도 `install_hook` 하나다",
          "install_hook" in inspect.getsource(_ob.do_guard))


def test_synth_stamps_commit() -> None:
    """[중요] **최초 합성도 `source_commit` 을 박는다** (사용자 지적 2026-08-22).

    처음엔 `do_synth` 가 `commit` 을 넘기지 않아 **신규 프로젝트의 문서 전부가 스탬프 없이**
    만들어졌다. `md.py:153` 이 *"`commit` 이 비면 그 줄이 안 붙는다"* 고 적어 뒀고, `md.py:19` 는
    그 값이 **중 1.3 stale 판정의 한쪽**이라고 못박았다. 훅 경로(`consumer._synthesize`)는
    넘기는데 온보딩 경로는 안 넘겼다 — **두 경로가 같은 계약이어야 한다.**
    """
    import inspect
    from master.projects import onboard

    src = inspect.getsource(onboard.do_synth)
    check("[중요] synth.run 에 commit 을 넘긴다", "commit=head.strip()" in src, src[-200:])
    check("HEAD 를 못 읽으면 합성하지 않는다", "HEAD 를 읽지 못해 합성하지 않는다" in src)
    # 훅 경로와 대조 — 두 곳이 같은 계약인지
    from master.events import consumer
    hook_src = inspect.getsource(consumer._synthesize)
    check("훅 경로도 commit 을 넘긴다 (대조군)", "commit=r.to_commit" in hook_src)

    # 넘기지 않으면 스탬프가 안 붙는다는 것 자체를 잰다 (md 계약 확인)
    # [주의] `finalize` 는 **형식 게이트를 통과한 문서**에만 스탬프를 찍는다 — 최소 문서로
    #    부르면 게이트에서 막혀 스탬프를 못 본다(내가 그렇게 짜서 칸이 빨갛게 됐다).
    #    그래서 `stamp()` 를 직접 잰다 — 이 계약이 요점이다.
    from master.context_synth import md as M
    doc = ("---\ntags: [x]\ncategory: a/b/c\nrelated_classes:\n  - UX: a.h\n---\n\n"
           "## 요약\nUX 는 무엇을 한다.\n\n## 개선 필요 사항\n없음\n")
    check("[중요] commit 을 주면 박힌다",
          "source_commit: abc1234" in M.stamp(doc, commit="abc1234"))
    check("[주의] 안 주면 안 박힌다 (그래서 넘겨야 한다)",
          "source_commit:" not in M.stamp(doc, commit=""))
    # 형식을 갖춘 문서로 finalize 왕복도 확인한다
    out, verdict = M.finalize(doc, existing="", commit="abc1234")
    check("finalize 도 같은 결과", verdict.ok and "source_commit: abc1234" in out,
          f"{verdict} {out[:80]}")


def test_live_modularstage() -> None:
    """[중요] **라이브 판정** — 이미 초기화된 실물에서 여섯 단계가 전부 참이어야 한다.

    이것이 판정기의 진짜 검증이다. 유닛 샌드박스는 우리가 만든 상태를 되읽는 것이라
    *"판정이 실물을 재는가"* 를 답하지 못한다(이 저장소가 반복해 물린 부류다).
    [주의] 마스터에서만 유효하다 — 트윈이 없으면 **건너뛰지 않고 사유를 찍는다**.
    """
    from master.projects.onboard import plan
    root = Path("/home/sim/ax-cluster")
    if not (root / "ModularStage" / "config.yaml").is_file():
        print("  [주의] ModularStage 트윈이 없다 — 라이브 판정을 건너뛴다 (마스터가 아니다)")
        return
    keep = os.environ.get("AX_PROJECTS_ROOT")
    try:
        os.environ["AX_PROJECTS_ROOT"] = str(root)
        d = plan("ModularStage", hosts=False).to_dict()
        # 🔴 [중요] **`profile` 은 사람이 답해야 끝나는 단계다** (`#650`) — 자동으로 채워질
        #    수 없으므로 「남음」이 정상이다. 나머지가 남으면 그건 진짜 미초기화다.
        #    [주의] 이 예외를 넓히지 않는다. `profile` **하나만** 허용한다 — 목록을 느슨하게
        #    두면 다음에 진짜로 빠진 단계가 이 구멍으로 조용히 통과한다.
        check("[중요] 라이브: 남은 단계가 `profile` 말고는 없다",
              set(d["remaining"]) <= {"profile"}, str(d["remaining"]))
        by = {s["step"]: s for s in d["steps"]}
        check("근거가 실물이다 (그래프 건수)", "classes=" in by["graph"]["detail"],
              by["graph"]["detail"])
        # [중요] 판정은 **그룹마다 문서가 있는지**다 (`#274`) — 「MD N건」이 아니다.
        #    실물은 문서 1,055 > 그룹 909 라 개수 비교로는 판정이 안 된다.
        check("[중요] synth 가 분모를 든다 (909/909 꼴)",
              by["synth"]["done"] and "/" in by["synth"]["detail"]
              and "그룹" in by["synth"]["detail"], by["synth"]["detail"])
        check("index 가 워터마크를 근거로 든다", "@" in by["index"]["detail"],
              by["index"]["detail"])
    finally:
        if keep is None:
            os.environ.pop("AX_PROJECTS_ROOT", None)
        else:
            os.environ["AX_PROJECTS_ROOT"] = keep


def test_conventions_step_is_the_manifest_source() -> None:
    """[중요] **컨벤션의 원천은 마스터 미러의 CLAUDE.md 다** (`#294`, 실측 2026-08-24).

    `work/conventions.project_doc` 이 `<트윈>/repo/CLAUDE.md` 의 `## Code conventions` 절을
    읽어 워커 매니페스트에 싣는데, 배달은 각 기계의 **체크아웃**에만 갔고 미러는 대상이
    아니었다 — NS 미러에 파일이 없어 매니페스트의 컨벤션이 **영구히 비었다.** MS 는 사람이
    그 파일을 놓아 둬서 우연히 돌고 있었다(N=1 에서는 우연과 설계가 구별되지 않는다).
    """
    from master.client import spec
    from master.context_search.paths import ProjectPaths
    from master.projects import onboard as O
    from master.work import conventions as C

    print("\n[컨벤션] 미러가 원천이다 (#294)")
    check("단계 선언에 있다", any(st.key == "conventions" for st in spec.SERVER_STEPS),
          str([st.key for st in spec.SERVER_STEPS]))
    check("실행기가 배선돼 있다", "conventions" in O.RUNNERS, str(sorted(O.RUNNERS)))
    check("판정기가 배선돼 있다", "conventions" in O.PROBES, str(sorted(O.PROBES)))

    tmp = _sandbox()
    p = ProjectPaths(name="ModularStage", root=tmp / "T")
    p.repo.mkdir(parents=True, exist_ok=True)
    (p.repo / ".git" / "info").mkdir(parents=True, exist_ok=True)

    ok, why = O._probe_conventions(p)
    check("[중요] 파일이 없으면 남음으로 답한다", not ok and "CLAUDE.md 가 없다" in why, why)

    # [중요] **파일 존재만으로는 부족하다** — 절 이름이 계약이다
    (p.repo / "CLAUDE.md").write_text("# CLAUDE.md\n\n본문만 있고 절이 없다\n",
                                      encoding="utf-8")
    ok, why = O._probe_conventions(p)
    check("[중요] 절이 없으면 「있다」로 세지 않는다", not ok and "절이 비었다" in why, why)

    # 실행기 — 본문을 넣고 무시 목록까지
    (p.repo / "CLAUDE.md").unlink()
    detail = O.do_conventions(p, project="ModularStage")
    text, note = C.project_doc(p.repo)
    sec = C.extract_section(text, spec.DEFAULT_CONVENTION_SECTIONS[0])
    check("절을 만든다", bool(sec.strip()), f"{detail} · {note}")
    ok, _ = O._probe_conventions(p)
    check("판정이 통과로 바뀐다", ok, detail)

    # [중요] **미러를 더럽히지 않는다** — 소스의 `.gitignore` 에 `/CLAUDE.md` 가 있다고
    #    기대할 수 없다(NS 는 UE 템플릿이라 없었고, 파일을 놓자마자 `?? CLAUDE.md` 였다).
    exclude = (p.repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    check("[중요] `.git/info/exclude` 에 넣는다 (`.gitignore` 를 고치지 않는다)",
          "/CLAUDE.md" in exclude, exclude)
    check("  두 번 돌려도 중복으로 넣지 않는다",
          O._exclude_in_mirror(p) == "무시 목록 이미 있음", O._exclude_in_mirror(p))

    # [중요] **정본이 있으면 규약 절은 정본에서 갱신된다** (사용자 지시 2026-09-01).
    #    옛 계약은 *"이미 있으면 무조건 덮지 않는다"* 였는데, 그 보호가 실제로는 **골격+실측으로
    #    생성된 절을 영구히 굳혔다**(NS: 2026-08-24 생성 → 09-01 까지 *"주석은 영문"* 이 SSOT).
    #    정본은 사람의 결정이므로 미러를 이긴다.
    (p.repo / "CLAUDE.md").write_text(
        "# 사람이 쓴 것\n\n## Code conventions\n\n- 손으로 정한 규칙\n\n## 딴 절\n\n- 남아야 한다\n",
        encoding="utf-8")
    d2 = O.do_conventions(p, project="ModularStage")
    after = (p.repo / "CLAUDE.md").read_text(encoding="utf-8")
    check("[중요] 정본이 있으면 규약 절을 정본에서 갱신한다", "정본에서 갱신했다" in d2, d2)
    check("  미러의 옛 규약은 사라진다", "손으로 정한 규칙" not in after, after[:200])
    check("  [중요] 규약 **절만** 만진다 — 다른 절은 보존",
          "남아야 한다" in after, after[:400])
    canon = C.extract_section(after, spec.DEFAULT_CONVENTION_SECTIONS[0])
    check("  판정이 통과다 (미러 == 정본)", O._probe_conventions(p)[0], canon[:120])

    # [주의] **정본이 없으면 종전대로 손대지 않는다** — 미러의 내용이 사람이 적은 것일 수 있고,
    #    그것을 실측본으로 덮는 것이 바로 그 버그였다.
    (p.repo / "CLAUDE.md").write_text("# 사람이 쓴 것\n\n## Code conventions\n\n- 손으로 정한 규칙\n",
                                      encoding="utf-8")
    d3 = O.do_conventions(p, project="정본없는프로젝트")
    check("[주의] 정본이 없으면 덮지 않는다", "덮지 않는다" in d3, d3)
    check("  사람이 쓴 내용이 남는다",
          "손으로 정한 규칙" in (p.repo / "CLAUDE.md").read_text(encoding="utf-8"))
    shutil.rmtree(tmp, ignore_errors=True)


def test_lfs_skip_persists_in_config() -> None:
    """🔴 LFS skip 은 **클론 순간의 환경변수가 아니라 config** 여야 한다 (`#376`).

    실측 2026-09-06: 환경변수는 그 명령에만 듣고 config 에 안 남아, 이후 색인기의 `pull` 이
    smudge 를 켠 채 돌다 죽었다(*"Smudge error"*). 커서가 멈춰 RAG 가 커밋을 못 봤다.
    [중요] 판정은 **선언 확인**이다 — 「LFS 를 받으려 했나」를 잡으면 이미 늦다.
    """
    print("\n[LFS] 미러는 포인터 전용 — 설정이 지속되고, 없으면 잡히고, 보정된다 (`#376`)")
    import subprocess

    from master.projects import onboard as O                              # noqa: N806
    tmp = Path(tempfile.mkdtemp(prefix="ax-lfs-"))
    repo = tmp / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)

    miss = O.lfs_skip_missing(repo)
    check("설정이 없으면 **세 키를 이름으로** 답한다", len(miss) == 3, str(miss))

    O.apply_lfs_skip(repo)
    check("보정하면 빈 튜플", O.lfs_skip_missing(repo) == (), str(O.lfs_skip_missing(repo)))
    got = subprocess.run(["git", "-C", str(repo), "config", "--local", "--get",
                          "filter.lfs.smudge"], capture_output=True, text=True).stdout.strip()
    check("  smudge 가 `--skip` 이다", got == "git-lfs smudge --skip -- %f", got)
    O.apply_lfs_skip(repo)
    check("멱등 — 두 번 걸어도 그대로", O.lfs_skip_missing(repo) == ())

    # 값이 **다르면** 없는 것으로 본다 (사람이 되돌린 경우)
    subprocess.run(["git", "-C", str(repo), "config", "--local", "filter.lfs.smudge",
                    "git-lfs smudge -- %f"], check=True)
    check("[중요] 값이 다르면 잡는다 (있다/없다가 아니라 **같은가**)",
          "filter.lfs.smudge" in O.lfs_skip_missing(repo), str(O.lfs_skip_missing(repo)))
    shutil.rmtree(tmp, ignore_errors=True)


def test_full_run_delivers_and_checks_clients() -> None:
    """`#259`: 전체 온보딩은 서버에서 끝나지 않고 클라이언트 대조까지 간다."""
    from master.projects import onboard as O

    calls = []
    # 서버 단계가 전부 완료된 모양만 주입한다. 이 검사의 축은 그 **다음** 클라 절이다.
    old_probe = O.probe_server
    try:
        O.probe_server = lambda _name, registry=None: []
        out = O.run("Fresh", confirm=True, registry=object(),
                    client_deliverer=lambda n: calls.append(("deliver", n)) or 0,
                    client_checker=lambda n: calls.append(("check", n)) or 0)
        check("전체 실행이 deliver → check 순서로 잇는다",
              calls == [("deliver", "Fresh"), ("check", "Fresh")], str(calls))
        check("클라 절도 완료 목록에 남는다",
              out["client"] == {"ran": True, "deliver_rc": 0, "check_rc": 0}
              and "client" in out["done"], str(out))

        calls.clear()
        partial = O.run("Fresh", confirm=True, only=["hook"], registry=object(),
                        client_deliverer=lambda n: calls.append(("deliver", n)) or 0,
                        client_checker=lambda n: calls.append(("check", n)) or 0)
        check("--only 서버 복구는 사람 작업장을 건드리지 않는다",
              calls == [] and not partial["client"]["ran"], str(partial))

        failed = O.run("Fresh", confirm=True, registry=object(),
                       client_deliverer=lambda _n: 0,
                       client_checker=lambda _n: 1)
        check("전체 check 실패는 온보딩 실패다",
              "클라이언트 초기화 실패" in failed["error"]
              and "client" not in failed["done"], str(failed))
    finally:
        O.probe_server = old_probe


def test_index_watermark_waits_for_synth() -> None:
    """🔴 **온보딩 색인도 합성이 끝났을 때만 워터마크를 찍는다** (`#274` ④ · `#693`).

    실측 2026-09-29 Kimodo: 합성 86/89 포기 2분 뒤 `do_index` 가 확인 없이 HEAD 를 찍었다.
    푸시 경로(`consumer`)에만 게이트가 있었다. [주의] **진짜 git** 으로 잰다 — HEAD 를 읽는
    자리를 흉내 내면 「찍었다」가 계약이 아니라 픽스처의 값이 된다.
    """
    import subprocess
    from master.context_search.paths import ProjectPaths
    from master.projects import onboard as O

    print("\n[색인] 워터마크는 합성이 끝났을 때만 (#274 ④)")
    tmp = _sandbox()
    p = ProjectPaths(name="X", root=tmp / "T")
    p.repo.mkdir(parents=True)
    g = lambda *a: subprocess.run(["git", "-C", str(p.repo), *a], check=True,
                                  capture_output=True)
    g("init", "-q")
    (p.repo / "a.txt").write_text("a", encoding="utf-8")
    g("add", "a.txt")
    g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "a")
    head = subprocess.run(["git", "-C", str(p.repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    p.config.write_text("index:\n  last_indexed_commit: ''\n  last_indexed_at: ''\n",
                        encoding="utf-8")

    class St:
        vector_docs = 86
    built = []
    rebuild = lambda paths: built.append(1) or St()

    out = O.do_index(p, rebuild=rebuild, complete=lambda paths: (False, "86/89 그룹 — 3개 미합성"))
    cfg = p.config.read_text(encoding="utf-8")
    check("🔴 86/89 면 워터마크를 찍지 않는다", head not in cfg, cfg)
    check("  그래도 색인은 만든다", built == [1], str(built))
    check("  사유에 분모가 보인다", "86/89" in out and "워터마크 미기입" in out, out)

    out = O.do_index(p, rebuild=rebuild, complete=lambda paths: (True, "89/89 그룹"))
    cfg = p.config.read_text(encoding="utf-8")
    check("89/89 면 HEAD 를 찍는다", f"last_indexed_commit: {head}" in cfg, cfg)
    check("  완료 사유를 싣는다", "89/89" in out and head[:7] in out, out)

    import inspect
    check("기본 판정은 푸시 경로와 같은 함수다",
          "synth_complete" in inspect.getsource(O.do_index))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    for fn in (test_step_source_is_spec, test_uninitialized, test_registered_only,
               test_guard_step_is_the_write_surface, test_synth_stamps_commit, test_live_modularstage,
               test_conventions_step_is_the_manifest_source, test_lfs_skip_persists_in_config,
               test_full_run_delivers_and_checks_clients, test_index_watermark_waits_for_synth):
        fn()
    print(f"{'OK' if not FAIL else 'FAIL'} test_onboard: {PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
