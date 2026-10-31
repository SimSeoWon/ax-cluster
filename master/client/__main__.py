"""워커 번들 CLI (레드마인 #21).

    python -m master.client probe <프로젝트>     각 워커를 잰다 (읽기 전용)
    python -m master.client plan  <프로젝트>     배달할 내용만 보여준다 (쓰지 않는다)
    python -m master.client deliver <프로젝트>   config + 스킬 배달 → 되읽어 대조
    python -m master.client check <프로젝트>     배달된 것이 정본과 같은지 검사
    python -m master.client update               **마운트된** 프로젝트를 현재 HEAD로 배달·검사
    python -m master.client update --all         등록된 모든 프로젝트를 배달·검사 (종전 기본)
    python -m master.client uproject <프로젝트>  에디터 플러그인 계획 (`--confirm` 으로 적용)
    python -m master.client master-local         마스터 Claude·Codex·agy 에 ax-client 등록 계획
                                                 (`--apply` 로 적용 · `--check` 로 대조)
    python -m master.client setup-host --host=<ip> --root=<경로> [--user=<계정>] [--confirm]
                                                 워커 한 대를 새로 놓거나 옮긴다 — 등록부 경로 →
                                                 낡은 상주 해제 → 클론·배달 → 대조 (기본은 계획만)
    python -m master.client home-guides [--host=<ip>] [--apply]
                                                 기계별 홈 CLAUDE.md·AGENTS.md 를 정본과 대조
                                                 (`--apply` 는 copy 대상의 DIFF 만 백업 후 쓴다, #861)

[중요] **`probe` → `plan` → `deliver` 순서로 쓴다.** 남의 기계에 쓰는 작업이므로, 무엇을 어디에
쓸지 먼저 눈으로 본다.

## [중요] 프로젝트 인자는 **필수**다 — 폴백이 없다 (`#227` 소 1.2)

전에는 생략하면 `DEFAULT_PROJECT = "ModularStage"` 로 떨어졌다. **그것은 폴백이 아니라 조용한
오답이다** (사용자 2026-08-22: *"아무것도 설정 안하고 폴백에서 처리된다면 그게 폴백 처리냐?"*) —
`config.json` 의 `project` 는 **요청·응답을 결정하는 태그**이고, 인자를 한 번 빼먹으면 다른
프로젝트의 기계가 `ModularStage` 태그를 받아 **남의 프로젝트로 일한다.**

이 저장소의 관례가 이미 그쪽이다: `projects_root()` 는 *"폴백은 없다 — 명시하라"*,
태그 계약(§12.5-c)은 *"빈 태그도 거절(fail-closed)"* 이다. 여기만 값을 주워 쓰고 있었다.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import bundle, spec


def _mounted_project_for_check() -> str:
    """검증이 사용할 마운트.

    [중요] 조회 실패를 빈 값으로 접지 않는다. 빈 값은 ``desired_state`` 에서
    "이 프로젝트가 마운트됐다"와 같은 쪽으로 판정되므로, 실패를 숨기면 비마운트
    프로젝트의 정상적인 미등록을 장애로 오판한다.
    """
    return (bundle.Registry.load().active or "").strip()



def _facts(project: str, *, only: str = "") -> list:
    """이 프로젝트의 작업장 실측. `only` 가 있으면 **그 호스트 하나만**.

    🔴 [중요] **`--host` 가 없어서 일회용 스크립트를 쓰게 됐다** (`#407`, 2026-09-12).
    `.33`(사람 기계)을 빼거나 한 대만 먼저 재보려면 방법이 없어서 스크래치패드에 배달
    스크립트를 따로 썼는데, 그건 저장소에 없어 **다음 사람이 못 쓴다.** 손으로 하는 일을
    선언으로 옮기는 것이 이 옵션의 축이다.
    [주의] 모르는 호스트를 주면 **조용히 0대에 배달하지 않는다** — 아래에서 거절한다.
    """
    out = []
    known = []
    for host, user, path, driven, role, dispatch in bundle.workshops(project):
        known.append(host)
        if only and host != only:
            continue
        if not user or not path:
            print(f"  [주의] {host}: user/path 미등록 — 건너뜀 (레지스트리를 고칠 것)")
            continue
        out.append(bundle.probe(host, user, path, driven, role, dispatch))
    if only and not out:
        raise SystemExit(f"[중요] `--host {only}` 가 {project} 의 작업장에 없다 — "
                         f"있는 것: {', '.join(known) or '(없음)'}")
    return out


def cmd_probe(project: str, *, only: str = "") -> int:
    facts = _facts(project, only=only)
    for f in facts:
        print(f"  {f.summary}")
    return 0 if facts else 1


def _print_spec(project: str, init) -> None:
    """[중요] **사양을 계획 맨 위에 찍는다** (#266). 오버레이가 배선됐는지는 `config.yaml` 을
    고쳐 이 줄이 달라지는지로 확인한다 — 안 달라지면 선언이 안 먹는 것이다."""
    print(f"\n══ 초기화 사양 — {project} (선언: master/client/spec.py + config.yaml 의 `init:`)")
    print("   서버 절: " + " → ".join(s.key for s in spec.SERVER_STEPS))
    print("   클라 절: 전체 onboard --confirm 시 checkout → deliver → check (#259)")
    print(f"   도메인: {', '.join(init.domains) or '(선언 없음)'}")
    print(f"   컨벤션 절: {', '.join(init.convention_sections)}  "
          f"← 프로젝트 repo/CLAUDE.md 에서 읽는다 (work/conventions.py)")
    if init.extra_skills or init.extra_mcp:
        print(f"   프로젝트 추가: skills={init.extra_skills or '{}'} mcp={init.extra_mcp or '{}'}")


def cmd_plan(project: str, *, only: str = "") -> int:
    init = spec.load_init(project)
    _print_spec(project, init)
    # [중요] **호스트를 프로브하기 전에 선언을 검증한다.** 없는 스킬을 선언했을 때 생
    #    트레이스백으로 죽어 뒤 호스트의 계획이 아예 안 나온 실측이 있다 (2026-08-22).
    bad = bundle.validate_spec(init)
    if bad:
        print("\n[중요] 초기화 사양이 저장소와 어긋난다 — 계획을 내지 않는다:")
        for b in bad:
            print(f"   ✕ {b}")
        print("   → config.yaml 의 `init:` 을 고치거나 그 스킬을 저장소에 놓을 것")
        return 2
    for f in _facts(project, only=only):
        print(f"\n── {f.summary}")
        if not f.checkout_ok:
            # [중요] **배달 항목으로 낸다** (`#254` 완료 조건 1) — 종전에는 *"배달 대상이 아니다"*
            #    라고만 찍어서, 「무엇을 하면 이 기계가 준비되는가」가 계획에 없었다.
            # [주의] **임포트도 `try` 안에 둔다** — 밖에 뒀다가 `Path` 미임포트로 `NameError` 가
            #    나서 사유조차 안 찍혔다(실측 2026-08-22). 실패를 말하지 못하면 없는 것과 같다.
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
                from client.init import bootstrap as _B
                cfg_ = bundle.Registry.load().config_of(project)
                for line in _B.plan_lines(f, cfg_):
                    print(line)
            except Exception as e:                           # noqa: BLE001
                print(f"   [중요] 체크아웃이 없고 클론 계획도 못 냈다: {e}")
            print("   [주의] 위 클론이 끝나야 아래 배달물이 갈 자리가 생긴다")
            continue
        cfg = bundle.config_for(project, f)
        # [중요] **태그를 계획에 명시한다** (사용자 2026-08-22: *"태그 명시해서 저장하고,
        #    관리해"*). 이 값으로 요청·응답이 결정되므로 계획에서 눈으로 확인해야 한다.
        tag = bundle.compare_tag(f, project)
        print(f"   → {f.path}/{bundle.CONFIG_REL}  [태그 {project}]"
              + ("" if tag["ok"] else f"  ← [중요] 지금 저장된 값: {tag['stored'] or '(없음)'}"))
        print("     " + json.dumps(cfg["checkout"], ensure_ascii=False)
              + f" caps={cfg['capabilities']}")
        print(f"     backends={json.dumps(cfg['backends'], ensure_ascii=False)}")
        for n in bundle.skills_for(f.role, init):
            # [주의] 도구별 자리를 **전부** 찍는다 — 선언은 `spec.SKILL_HOMES` 하나다(`#385`).
            #    계획에 안 보이면 사람이 배달 내용을 눈으로 확인할 수 없다.
            for rel in spec.skill_rels(n):
                print(f"   → {f.home}/{rel} "
                      f"({len(bundle.skill_text(n))}자)  [role={f.role}]")
            print(f"   → {f.path}/{spec.project_skill_rel(n)} "
                  f"({len(bundle.skill_text(n))}자)  [프로젝트 로컬 정본 · #699]")
        # [중요] **MCP 엔트리를 계획에 찍는다** — 워커가 못 받는다는 판단이 조건문 한 줄에
        #    숨어 있으면 아무도 그것을 보지 못한다 (#261).
        mcp = spec.mcp_for(f.role, init)
        if mcp and spec.mcp_scope_for(init) == "local":
            for n in mcp:
                print(f"   → {f.host}: `{bundle.claude_mcp_local_cmd(f, n)}`  "
                      "[로컬 스코프 — .mcp.json 은 안 건드림 · #693]")
        else:
            print(f"   → {f.path}/.mcp.json — 엔트리 {', '.join(mcp) or '(없음 — 이 역할은 받지 않는다)'}")
        if not spec.entry_docs_for(init):
            print(f"   → {f.path}/CLAUDE.md · {spec.CODEX_ENTRY_REL} — [건너뜀] 색인 전용: "
                  "커밋된 사람 파일이라 관리 블록을 쓰지 않는다 (#693)")
        # [중요] **codex 몫도 계획에 찍는다** (`#402`). 선언은 `spec.ENTRY_DOCS` ·
        #    `spec.codex_mcp_for` 하나씩이고, 안 찍으면 스킬 때(`#385`)와 같은 일이 난다 —
        #    배달은 정상인데 도구가 그것을 못 보는 상태가 **아무 표면에도 안 나타난다.**
        if spec.entry_docs_for(init):
            print(f"   → {f.path}/{spec.CODEX_ENTRY_REL} — codex 진입 문서 "
                  f"[블록만 교체 · 없으면 CLAUDE.md 시드]")
        cmcp = spec.codex_mcp_for(f.role, init)
        if cmcp:
            for n in cmcp:
                print(f"   → {f.host}: `{bundle.codex_mcp_cmd(f, n)}`"
                      + ("" if f.codex else "  ← [주의] codex 없음 — 건너뛴다"))
        # [중요] **훅 「등록」을 계획에 찍는다** (`#337`) — 파일 배달과 다른 자리다. 종전에는
        #    `.claude/hooks/domain_hint.py` 가 배달 목록에만 있어서, 그것이 **등록되지 않아
        #    한 번도 안 돈다**는 사실이 계획에도 보고에도 나타나지 않았다.
        hk = spec.managed_hooks_for(f.role, init)
        if hk:
            print(f"   → {f.path}/{spec.SETTINGS_REL} — 훅 등록 "
                  + ", ".join(f"{ev}({rel.rsplit('/', 1)[-1]})" for ev, _m, rel, _t in hk)
                  + "  [관리 항목만 교체 · 사용자 훅 보존]")
        # [중요] 페이로드도 **눈으로 보여 준다** — 남의 기계에 쓰는 파일을 계획에서 감추면
        #    `plan` 이 존재하는 이유가 없어진다 (모듈 독스트링: *"무엇을 어디에 쓸지 먼저 본다"*)
        #    [주의] **읽는 자리와 쓰는 자리를 갈라 쓴다** (#262) — 계획에 찍히는 것은 *배달 위치*고
        #    글자 수는 *저장소 원문*에서 온다. 한 값으로 쓰면 재배치가 계획을 조용히 바꾼다.
        pay = bundle.payload_pairs(f.role)
        if pay:
            base = f"{f.path}/{bundle.AX_DIR}/lib/{bundle.PAYLOAD_PKG}"
            for d in bundle.payload_dirs(f.role):
                print(f"   → {base}/{d + '/' if d else ''}__init__.py  (패키지 표식)")
            for dest, src in pay:
                print(f"   → {base}/{dest} ({len(bundle.payload_text(src))}자)  [payload]")
        ws = bundle.workshop_files(f.role, project, init)
        if ws:
            # [중요] **자산은 개수로 찍는다** — 33개를 한 줄씩 찍으면 계획이 안 읽힌다.
            #    다만 어느 묶음이 몇 개인지는 말한다(안 보이는 산출물은 없는 것으로 읽힌다).
            groups: dict = {}
            for rel, _src in ws:
                groups.setdefault(rel.split("/")[1], []).append(rel)
            summary = " · ".join(f"{k} {len(v)}개" for k, v in sorted(groups.items()))
            print(f"   → {f.path}/.claude/ 작업장 자산 {len(ws)}개 ({summary})  [workshop]")
            print(f"   → {f.path}/.claude/CLAUDE.md — `{bundle.WS_BEGIN}` 블록만 교체")
        # [중요] **제외 목록을 전부 찍는다** (#266, 사용자 지적 2026-08-22). 종전에는 `.ax/` 만
        #    찍었고 목록도 두 줄이었다 — `.33` 이 안 더러운 이유가 **그 프로젝트 `.gitignore` 의
        #    세 줄**(실측 `:36 .claude/` `:40 /.mcp.json` `:41 /CLAUDE.md`)이었지 우리 목록이
        #    아니었다. 새 프로젝트엔 그 줄이 없고 우리는 `.gitignore` 를 고칠 수 없다(§2.1).
        # [중요] **상주 등록을 계획에 낸다** (`#255` 완료 조건 1 · `#405` 복원) — 종전에는 두
        #    기계의 등록 방식이 **문서에만** 있어 새 기계에서 재현되지 않았다. 켜면 안 되는
        #    경우의 사유도 찍는다(마운트를 따른다).
        if f.role != "requester":
            try:
                from client.init import residency as _R
                mounted = (bundle.Registry.load().active or "").strip()
                for line in _R.plan_lines(project, f, mounted=mounted):
                    print(line)
            except Exception as e:                           # noqa: BLE001
                print(f"   [주의] 상주 등록 계획을 못 냈다: {e}")
        exc = ", ".join(f"`{x}`" for x in spec.git_excludes_for(f.role))
        print(f"   → {f.path}/.git/info/exclude 에 {exc} (커밋 안 됨)")
        # [주의] 추적 중인 파일은 exclude 로 못 막는다 — 이름으로 보고한다(고치지는 않는다).
        # [중요] **`.gitignore` 가 산출물 오염을 막는 쪽이다** (사용자 2026-08-22). info/exclude 는
        #    클론 로컬이라 그 기계에만 듣고, 팀원이 새로 클론하면 없다. 원전도 `.gitignore` 에
        #    마커 블록을 써서 사람이 커밋하게 했다(ModularStage `.gitignore:30-42` 가 그 결과다).
        #    [주의] 쓰는 것은 #259 onboard 다 — 여기서는 무엇이 들어갈지만 보여 준다.
        # [중요] **`deliver` 는 아직 이것을 쓰지 않는다.** 계획이 배달하지 않는 것을 `→` 로
        #    찍으면 계획이 거짓말을 한다 — 그 부류가 이 저장소가 가장 싫어하는 것이다
        #    (§12.6: *"plan 에 안 보이면 미완"* 의 뒤집힌 형태). 표시를 갈라 둔다.
        print(f"   ◦ {f.path}/.gitignore 의 `{spec.GITIGNORE_BEGIN.split(' — ')[0]}` 블록 "
              f"({len(spec.GITIGNORE_BODY)}줄) — [주의] **이 명령은 쓰지 않는다** "
              f"(#259 onboard 의 자리 · 추적 파일이라 커밋은 사람 몫)")
        tracked = bundle.tracked_managed(f)
        if tracked:
            print(f"   [중요] 저장소가 **추적 중**이라 exclude 가 안 듣는다: {', '.join(tracked)}"
                  f"\n       → 인프라 파일이 게임 산출물에 섞여 있다. `git rm --cached <파일>` +"
                  f" 위 .gitignore 블록을 **사람이 한 번 커밋**하면 끝난다 (처분은 #259)")
        # [중요] **폐지분을 이름으로 찍는다** (#266 완료 조건 3). 표에서 지우는 것만으로는 이미
        #    배달된 기계가 정리되지 않는다 — `#232` 가 그 부류였고 그때 실패는 조용했다.
        # [중요] **상주 등록 계획 절이 여기 있었다** (`#255` → `#320` 으로 철거, 2026-08-27).
        #    상주가 0이므로 낼 계획이 없다. 파견은 마스터가 SSH 로 민다.
        rm = spec.removals_for(f.role, init)
        for kind, names in (("스킬", rm["skills"]), ("MCP 엔트리", rm["mcp"])):
            if names:
                # [중요] `#232` 는 2026-09-02 에 닫혔다 — `deliver` 가 실제로 지운다
                #    (`bundle._remote_rm_dir`, fail-open). 종전 문구는 *"지우는 것은 아직 이
                #    명령이 하지 않는다"* 였고 **그 말이 맞았다** — 주석만 「지운다」고 적혀
                #    있었고 구현이 없었다. `check` 가 `ax-work` 잔존을 잡아 드러났다.
                doing = "deliver 가 지운다" if kind == "스킬" else "지우지 않는다 (#235 미결)"
                print(f"   ✕ 폐지 {kind}: {', '.join(names)}  [주의] {doing}")
    return 0


def cmd_deliver(project: str, *, init: bool = False, only: str = "") -> int:
    # [중요] 사양은 **한 번만** 읽어 호스트마다 넘긴다 — 호스트별로 다시 읽으면 배달 도중
    #    `config.yaml` 이 바뀌었을 때 기계마다 다른 선언이 실린다.
    # [주의] `init`(= `--init`, 원격 `/init` 플래그)과 `project_init`(사양)은 **다른 것**이다.
    pinit = spec.load_init(project)
    problems = bundle.validate_spec(pinit)
    if problems:
        print("[중요] 초기화 사양이 저장소와 어긋난다 — 배달하지 않는다:")
        for b in problems:
            print(f"   ✕ {b}")
        return 2
    bad = 0
    for f in _facts(project, only=only):
        if not f.checkout_ok:
            # [중요] **먼저 놓는다** (`#254`). 종전에는 사유만 적고 건너뛰어서, 새 기계는
            #    사람이 손으로 클론해야 했다 — 자동화 전제와 어긋난다.
            try:
                r0 = bundle.bootstrap_checkout(project, f)
                print(f"  [완료] {f.host}: 체크아웃 부트스트랩 — "
                      f"{r0.get('commit','?')} · LFS {r0.get('lfs','?')}")
                f = bundle.probe(f.host, f.user, f.path, f.driven, f.role, f.dispatch)
            except bundle.BundleError as e:
                print(f"  [중요] {f.host}: 부트스트랩 실패 — {e}")
                bad += 1
                continue
        try:
            r = bundle.deliver(project, f, init=init, project_init=pinit)
        except bundle.BundleError as e:
            print(f"  [중요] {f.host}: {e}")
            bad += 1
            continue
        print(f"  [완료] {f.host} [{f.role}]: config={r['config']} · CLAUDE.md {r['claude_md_mode']}")
        ini = r.get("init") or {}
        if ini.get("ran"):
            # [주의] 일회성 프로비저닝 비용 — 작업 비용과 섞지 않는다 (#64)
            if ini.get("error"):
                print(f"     [주의] /init 실패 — {ini['error']} (AX 블록만으로 진행)")
            else:
                print(f"     /init 실행 · 턴 {ini.get('turns', 0)} · "
                      f"${ini.get('cost_usd', 0):.3f} (일회성)")
        elif ini.get("error"):
            print(f"     [주의] {ini['error']}")
        for sp in r["skills"]:
            print(f"     skill={sp}")
        # [중요] 제거 결과를 **이름으로** 찍는다 — 합계만 찍으면 무엇이 안 지워졌는지 모른다
        for rmv in r.get("removed") or []:
            print(f"     removed={rmv}")
        # [중요] **페이로드도 찍는다.** 첫 실 배달(2026-08-16)에서 파일 8개가 **실제로 갔는데**
        #    출력에 안 나와서, 확인하려면 원격 디렉토리를 직접 뒤져야 했다.
        #    *"배달했다고 믿지 않는다"* 는 사람이 읽는 출력에도 적용된다 — 안 보이는 산출물은
        #    다음 세션에 **없는 것으로 읽힌다.**
        for pp in r.get("payload") or []:
            print(f"     payload={pp}")
        if r.get("workshop"):
            print(f"     workshop={len(r['workshop'])}개 → {f.path}/.claude/ "
                  f"(agents·skills·rules·hooks)")
        if "workshop_md" in r:
            print(f"     workshop_md={r['workshop_md']}")
        if "mcp_json" in r:
            print(f"     mcp_json={r['mcp_json']}")
        res = r.get("residency") or {}
        if res.get("registered"):
            print(f"     residency={res['registered']} · " + " · ".join(res.get("results") or []))
        elif res.get("skipped"):
            # [중요] **왜 안 걸었는지를 찍는다** — 빠진 채 「완료」로 보이면 `#255` 이전이다
            print(f"     residency=[건너뜀] {res['skipped']}")
        elif res.get("error"):
            print(f"     residency=[실패] {res['error']}")
            bad += 1
        # [중요] **갱신 결과를 찍는다** (`#277`) — 판정을 했는데 안 보이면 「안 한 것」과
        #    구분되지 않는다. 이 줄이 없어서 종전에 갱신이 화면에 안 보였다.
        rr = r.get("residency_refresh") or {}
        if rr.get("refreshed"):
            extra = f" · pid {rr['pid_killed']} 종료" if rr.get("pid_killed") else ""
            print(f"     residency_refresh=[완료] {rr['refreshed']}{extra}"
                  + (f" · {rr['note']}" if rr.get("note") else ""))
        elif rr.get("pending"):
            print(f"     residency_refresh=[주의] {rr['pending']} (pid {rr.get('pid')})")
        elif rr:
            print(f"     residency_refresh={rr.get('why', '이상 없음')}")
        if "agents_md" in r:
            print(f"     agents_md={r['agents_md']}  [{r.get('agents_md_mode', '?')}]")
        for cl in r.get("claude_mcp_local") or []:
            # 로컬 스코프 등록 결과 (`#693`) — 배달 요약에서 빠져 FAIL 원인을 가렸다
            print(f"     claude_mcp_local={cl}")
        for cm in r.get("codex_mcp") or []:
            # [중요] 걸었는지와 **왜 안 걸었는지**를 둘 다 찍는다 (리포트 44 의 교훈)
            print(f"     codex_mcp={cm}")
        if "settings_json" in r:
            # [중요] 훅 **등록** 자리 — 파일 배달과 다른 것이다 (`#337`)
            print(f"     settings_json={r['settings_json']}  [훅 등록]")
        if "role_token" in r:
            # [중요] 값이 아니라 경로(또는 부재 안내)만 찍힌다
            print(f"     role_token={r['role_token']}")
        print("     .git/info/exclude [완료] · 해시 대조 통과")
        if "fetch_prune" in r:
            print(f"     fetch_prune={r['fetch_prune']}")
        # [중요] **상주 갱신 출력 절이 여기 있었다** (`#277` → `#320` 으로 철거, 2026-08-27).
        #    상주가 없으므로 배달은 파일을 놓는 것으로 끝난다.
    return 1 if bad else 0


def cmd_check(project: str, *, only: str = "", stats: dict | None = None) -> int:
    """배달본이 정본과 같은가. [중요] 사본은 갈라진다 — 그래서 잰다.

    ``stats`` 를 넘기면 판정 내역을 채운다 (`#737`, 사용자 2026-10-05) — ``update`` 가
    「실행 중 HEAD 이동」 때문인 실패와 진짜 실패를 갈라 말하기 위해서다.
      ``bad``          실패 호스트 수 (+ 마스터 서비스 신선도 실패 1)
      ``behind_only``  **출처가 HEAD 보다 커밋 뒤처졌다는 것만** 실패 사유인 호스트 수
      ``dirty_only``   **커밋은 같고 배달 도장이 dirty 라는 것만** 실패 사유인 호스트 수
      ``behind_dirty`` 뒤처짐 + dirty 도장 **둘만** 실패 사유인 호스트 수
      ``fresh_bad``    마스터 서비스 신선도 실패(0/1 — ``bad`` 에 포함)
      ``fresh_changed_at``  그 실패가 **전부** 「기동 뒤 파일 변경」일 때 가장 이른 변경 mtime
                       (판정 불가 사유가 섞이면 ``None``) — ``update`` 가 「실행 중 변경 탓」을 가른다
    [주의] 판정 자체는 바꾸지 않는다 — 뒤처짐도 dirty 도장도 여전히 FAIL 이다.
    """
    bad = 0
    behind_only = 0
    dirty_only = 0
    behind_dirty = 0
    behind_hosts: list = []
    init = spec.load_init(project)
    for f in _facts(project, only=only):
        if not f.checkout_ok:
            print(f"  [주의] {f.host}: 체크아웃 없음")
            bad += 1
            continue
        ok_skill = True
        names = bundle.skills_for(f.role, init)
        # 🔴 `#655` — 아래에서 잴 고정 파일의 해시를 **연결 한 번에** 받는다. 종전에는 파일마다
        #    ssh(Windows 는 PowerShell 기동)를 따로 열어 `.2` 한 대 검사에 13회·약 8초가 들었다.
        #    [주의] 받지 못한 경로는 빈 값이라 「불일치」로 판정된다 — 실패는 실패 쪽으로 닫힌다.
        _probe_targets = [bundle._write_target(f, r, "home")
                          for n in names for r in spec.skill_rels(n)]
        _probe_targets += [bundle._write_target(f, spec.project_skill_rel(n), "checkout")
                           for n in names]
        _probe_targets += [bundle._write_target(
            f, f"{bundle.AX_DIR}/lib/{bundle.PAYLOAD_PKG}/{rel}", "checkout")
            for rel, _src in bundle.payload_pairs(f.role)]
        _probe_targets.append(bundle._write_target(f, f"{bundle.AX_DIR}/token", "checkout"))
        known = bundle.remote_hashes(f, _probe_targets)
        for n in names:
            want = hashlib.sha256(bundle.skill_text(n).encode("utf-8")).hexdigest()
            # [중요] 도구별 자리를 **전부** 검사한다 — 한 곳만 보면 codex 쪽 누락이 안 보인다.
            for rel in spec.skill_rels(n):
                target = bundle._write_target(f, rel, "home")
                ok_skill = ok_skill and known.get(target, "") == want
            target = bundle._write_target(f, spec.project_skill_rel(n), "checkout")
            ok_skill = ok_skill and known.get(target, "") == want
        cfg_path = (f"{f.path}\\{bundle.CONFIG_REL.replace('/', chr(92))}" if f.windows
                    else f"{f.path}/{bundle.CONFIG_REL}")
        rc2, _ = bundle._ssh(f.host, f.user,
                             (f'if exist "{cfg_path}" (echo OK)' if f.windows
                              else f"test -f '{cfg_path}' && echo OK"))
        ok_cfg = rc2 == 0
        # Windows의 프로젝트 로컬 도구는 `py` 런처에 기대지 않는다. 초기화 프로브가
        # 절대경로를 못 찾았으면 파일 배달이 끝났어도 Codex가 fix_flow/client_mcp를 못 돈다.
        ok_python = (not f.windows) or bool(f.python)
        python_note = ("" if ok_python else
                       " · [실패] Python 절대경로를 못 찾았다 (Codex 로컬 도구 실행 불가)")
        # [중요] **페이로드도 잰다.** 스킬은 문서라 낡아도 사람이 읽다 눈치채지만, 파이썬 모듈은
        #    낡은 채로 **조용히 돈다** — `.33` 이 옛 review 로직으로 검수하면 그 판정은
        #    거짓말이다. 사본이 갈라지는 것이 이 명령의 존재 이유다.
        #    [주의] 해시는 **저장소 원문**으로 내고 **배달 위치**의 파일과 댄다 (#262).
        pay = bundle.payload_pairs(f.role)
        stale: list = []
        for rel, src in pay:
            want = hashlib.sha256(bundle.payload_text(src).encode("utf-8")).hexdigest()
            target = bundle._write_target(
                f, f"{bundle.AX_DIR}/lib/{bundle.PAYLOAD_PKG}/{rel}", "checkout")
            if known.get(target, "") != want:
                stale.append(rel)
        ok_pay = not stale
        # 요청자 전용 (소 3.8.4): .mcp.json 항목 + 역할 토큰
        ok_client = True
        client_note = ""
        if f.role == "requester":
            if spec.mcp_scope_for(init) == "local":
                # 🔴 색인 전용(`#693`) — 배달이 쓴 자리(로컬 스코프)를 본다. `.mcp.json` 을 보면
                #    정상 배달을 실패로 답한다(`#337` 과 같은 부류: 쓰는 자리와 재는 자리가 갈림).
                got_l = bundle.claude_mcp_local_get(f, bundle.MCP_SERVER_NAME)
                if not got_l:
                    ok_client = False
                    client_note = " · [실패] 로컬 스코프에 ax-client 가 없다 (~/.claude.json)"
                elif not bundle.claude_mcp_local_matches(got_l, f):
                    ok_client = False
                    client_note = " · [실패] 로컬 스코프 ax-client 항목이 다르다"
                else:
                    client_note = " · ax-client 로컬 스코프 일치"
            else:
                raw = bundle._remote_read(f, (f"{f.path}\\.mcp.json" if f.windows
                                              else f"{f.path}/.mcp.json"))
                try:
                    entry = (json.loads(raw or "{}").get("mcpServers") or {}).get(
                        bundle.MCP_SERVER_NAME)
                except ValueError:
                    entry = None
                if entry != bundle.mcp_entry_for(f):
                    ok_client = False
                    client_note = " · [실패] .mcp.json 의 ax-client 항목이 없거나 다르다"
            # [중요] **훅이 「등록」됐는지 잰다** (`#337`). 이 검사가 없어서 배달은 계속
            #    [완료] 를 보고했고 `domain_hint.py` 는 배달된 채 죽어 있었다 — 파일 해시는
            #    3자 일치였다. **파일이 있다 ≠ 훅이 돈다.**
            want_hooks = spec.managed_hooks_for(f.role, init)
            if want_hooks:
                _sr = (spec.SETTINGS_REL.replace("/", chr(92)) if f.windows
                       else spec.SETTINGS_REL)
                _sp = chr(92) if f.windows else "/"
                raw_s = bundle._remote_read(f, f"{f.path}{_sp}{_sr}")
                try:
                    hooks_got = (json.loads(raw_s or "{}").get("hooks") or {})
                except ValueError:
                    hooks_got = None
                if hooks_got is None:
                    ok_client = False
                    client_note += f" · [실패] {spec.SETTINGS_REL} 이 깨진 JSON 이다"
                else:
                    for ev, matcher, rel, timeout in want_hooks:
                        # [중요] 조립은 `bundle.hook_entry` 한 자리다 — 여기서 다시 만들면
                        #    필드가 늘 때 검사기만 낡아 **정상 배달을 실패로 답한다**(실측).
                        want_e = bundle.hook_entry(matcher, rel, timeout, f)
                        if want_e not in (hooks_got.get(ev) or []):
                            ok_client = False
                            client_note += (f" · [실패] 훅 미등록 — {ev}: "
                                            f"{rel} (배달만 되고 안 돈다)")
            from .. import auth as _auth
            _rt = _auth.load_role_token("requester")
            if _rt:
                want_t = hashlib.sha256((_rt + "\n").encode("utf-8")).hexdigest()
                tp = bundle._write_target(f, f"{bundle.AX_DIR}/token", "checkout")
                if known.get(tp, "") != want_t:
                    ok_client = False
                    client_note += " · [실패] 역할 토큰 불일치/없음 (재배달 필요)"
            else:
                client_note += " · [주의] 마스터에 requester 토큰이 없다 (init-role)"
        
        # [중요] **작업장 자산도 잰다** (#226 4번). 에이전트·스킬은 사람이 읽는 문서지만
        #    `tools:` 허용목록이 낡으면 **오류 없이 능력만 사라진다**(리포트 27 §13) — 페이로드가
        #    조용히 낡는 것과 같은 부류다. 33개를 한 번의 ssh 로 해시 뜬다.
        ws = bundle.workshop_files(f.role, project, init)
        ws_stale: list = []
        if ws:
            base = (f.path + chr(92) + ".claude") if f.windows else (f.path + "/.claude")
            if f.windows:
                # [주의] 인용이 세 겹(bash → ssh → powershell)이라 **조립해서** 만든다.
                #    한 줄 f-string 에 넣으려다 두 번 깨졌다 — 읽는 사람도 못 읽는다.
                ps = ("Get-ChildItem -LiteralPath '" + base + "' -Recurse -File "
                      "-Include *.md,*.py | ForEach-Object { "
                      "$h=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash; "
                      "Write-Output ($_.FullName.Substring(" + str(len(base) + 1)
                      + ") + ' ' + $h) }")
                cmd = 'powershell -NoProfile -Command "' + ps + '"'
            else:
                cmd = (f"cd '{base}' 2>/dev/null && find . -type f \\( -name '*.md' -o "
                       "-name '*.py' \\) -exec sha256sum {} + 2>/dev/null")
            _rc, got = bundle._ssh(f.host, f.user, cmd)
            remote = {}
            for line in (got or "").splitlines():
                parts = line.strip().replace("\\", "/").split()
                if len(parts) == 2 and len(parts[1]) == 64:          # windows: 경로 해시
                    remote[parts[0].lstrip("./")] = parts[1].lower()
                elif len(parts) == 2 and len(parts[0]) == 64:        # linux: 해시 경로
                    remote[parts[1].lstrip("./")] = parts[0].lower()
            for rel, src in ws:
                inner = rel.split("/", 1)[1]                         # `.claude/` 를 뗀다
                want = hashlib.sha256(bundle.workshop_text(src).encode("utf-8")).hexdigest()
                if remote.get(inner) != want:
                    ws_stale.append(inner)
        ok_ws = not ws_stale
        ws_note = (f" · 작업장 자산 {len(ws)}개 일치" if ws and ok_ws
                   else f" · [중요] 작업장 자산 불일치/없음 {len(ws_stale)}개: "
                        f"{', '.join(ws_stale[:3])}" if ws else "")

        # [중요] **폐지분이 아직 남아 있는지 이름으로 답한다** (#266 완료 조건 4).
        #    합계만 답하면 「무엇이」 남았는지 알 수 없고, 그러면 고칠 수 없다.
        rm = spec.removals_for(f.role, init)
        left: list = []
        if rm["skills"]:
            if f.windows:
                probe = " ; ".join(
                    f"if (Test-Path '{f.home}\\.claude\\skills\\{n}') {{ Write-Output '{n}' }}"
                    for n in rm["skills"])
                cmd = 'powershell -NoProfile -Command "' + probe + '"'
            else:
                probe = " ; ".join(f"test -e '{f.home}/.claude/skills/{n}' && echo {n}"
                                   for n in rm["skills"])
                cmd = probe
            _rc, got = bundle._ssh(f.host, f.user, cmd)
            left = [x.strip() for x in (got or "").splitlines() if x.strip() in rm["skills"]]
        rm_note = (f" · [중요] 폐지 스킬이 남아 있다: {', '.join(left)}" if left else
                   f" · 폐지 {len(rm['skills'])}종 없음(정리됨)" if rm["skills"] else "")

        # 상주 작업 데몬은 금지다. 조회 실패는 정상 부재가 아니다 (#861).
        from client.init import residency as _R
        _cmd = _R.registration_query_command(project, f)
        _rc, _out = bundle._ssh(f.host, f.user, _cmd)
        _state = _R.registration_status(_rc, _out, f)
        ok_res = _state["known"] and not _state["present"]
        if not _state["known"]:
            res_note = f" · [실패] {_state['error']}"
        elif _state["present"]:
            res_note = " · [실패] 금지된 상주 데몬이 등록돼 있다 (#861)"
        else:
            res_note = " · 상주 미등록 정상 — 서버 SSH 주관 (#861)"

        # ── codex 몫 (`#402`) — **역할 무관** ────────────────────────────
        #    [중요] `AGENTS.md` 는 「있나」가 아니라 **관리 블록이 최신인가**를 본다. 전문은
        #    사람이 고칠 수 있으므로 해시 전체 대조는 정상을 실패로 답한다 — `check` 가
        #    정상 배달을 실패로 답한 전례가 이미 있다(`#337` 훅, 정확 일치 비교).
        ok_codex = True
        codex_note = ""
        _csep = chr(92) if f.windows else "/"
        raw_a = bundle._remote_read(f, f"{f.path}{_csep}{spec.CODEX_ENTRY_REL}")
        want_block = bundle.managed_block(project, f)
        if not spec.entry_docs_for(init):
            codex_note = f" · {spec.CODEX_ENTRY_REL} 건너뜀(색인 전용 — 사람 파일)"
        elif not (raw_a or "").strip():
            ok_codex = False
            codex_note = f" · [실패] {spec.CODEX_ENTRY_REL} 이 없다 (codex 는 CLAUDE.md 를 안 읽는다)"
        elif want_block not in raw_a:
            ok_codex = False
            codex_note = f" · [실패] {spec.CODEX_ENTRY_REL} 의 AX 블록이 낡았다"
        # [중요] **codex 가 실제로 보는 것**을 묻는다 — 파일을 보는 것이 아니다.
        #    🔴 rc 로 판정하지 않는다: 없는 이름에도 `codex mcp get` 은 rc=0 이다(실측).
        for n in spec.codex_mcp_for(f.role, init):
            if not f.codex:
                codex_note += f" · [주의] codex 없음 — {n} 등록 검사 건너뜀"
                continue
            got = bundle.codex_mcp_get(f, n, project=True)
            if not got:
                ok_codex = False
                codex_note += f" · [실패] codex 가 {n} 을 모른다 (`codex mcp get` 못 찾음)"
            elif not bundle.codex_mcp_matches(got, f):
                ok_codex = False
                _tr = got.get("transport") or {}
                codex_note += (f" · [실패] codex 의 {n} 이 다르다 — "
                               f"{_tr.get('command')} {' '.join(_tr.get('args') or [])}")

        # [중요] **배달본의 출처 커밋을 마스터 HEAD 와 댄다** (#266, 사용자 2026-08-22:
        #    *"커밋한 해시키 등을 이용해 각 워커들과 인프라 서버간 비교하는게 있어야"* +
        #    *"config 파일 문서에 명기하면 이것만 비교하면 되는거잖아"*). 값은 이미
        #    `.ax/config.json` 의 `delivered_by` 에 있었고 **아무도 안 읽었다.**
        #    [중요] **판정은 `version.compare` 가 한다** — `same` 만 통과다. 처음에 「뒤처짐은
        #    실패가 아니다」로 짰다가 사용자 정정으로 되돌렸다: 클러스터는 **버전이 하나**이고,
        #    통신 규칙(`CONTRACT`)과 `config.json` 생성기가 모두 마스터에 있다. 배달물 해시가
        #    같은 것은 *그 커밋들이 배달물을 안 바꿨다*는 뜻일 뿐 **같은 버전이라는 뜻이 아니다.**
        # 🔴 **옛 스킬 사본이 codex 스킬 루트에 남아 있나** (실측 2026-09-13 `.2`) — 배달본이
        #    일치해도 codex 가 **옛 사본을 골라 읽으면** 정본은 안 쓰인다. 파일 해시 대조로는 안 보인다.
        shadows = bundle.shadow_skills(f, names)
        ok_shadow = True  # `#699`: 체크아웃 `.agents/skills` 정본이 홈 사본보다 앞선다.
        shadow_note = (f" · [주의] 홈 중복 스킬 {len(shadows)}개 — "
                       f"프로젝트 로컬 정본 우선: {', '.join(shadows[:3])}" if shadows else "")
        ver = bundle.compare_version(f)
        ok_ver = ver["ok"]
        ver_note = f" · 출처 {ver['reason']}"
        # [중요] **저장된 태그를 기대값과 댄다** — 「저장」만 있고 「관리」가 없으면 태그가
        #    조용히 어긋난다. 이 태그로 요청·응답이 결정된다(§12.5-c).
        tag = bundle.compare_tag(f, project)
        ok_tag = tag["ok"]
        tag_note = f" · {tag['reason']}"

        # `#787` ③ — 워커 클론이 원격에서 지운 브랜치의 원격추적 ref 를 남기지 않는가
        ok_prune, prune_note = bundle.check_fetch_prune(f)
        # `#830` — 워커의 agy 호출이 `--model` 로 넘길 정본 id 가 배달됐는가 (없으면 별칭 → Argon)
        ok_agy, agy_note = bundle.check_agy_model(f)

        mark = ("OK" if (ok_skill and ok_cfg and ok_python and ok_pay and ok_client and ok_ws
                         and ok_ver and ok_tag and ok_codex and ok_res and ok_shadow
                         and ok_prune and ok_agy) else "FAIL")
        pay_note = (f" · payload {len(pay)}개 일치" if pay and ok_pay
                    else f" · [중요] payload 불일치/없음 {len(stale)}개: {', '.join(stale[:3])}"
                    if pay else "")
        print(f"  {mark} {f.host} [{f.role}]: 스킬 {len(names)}종 "
              f"{'일치' if ok_skill else '불일치/없음'} · config {'있음' if ok_cfg else '없음'}"
              f"{python_note}{pay_note}{ws_note}{client_note}{codex_note}{shadow_note}{res_note}{rm_note}"
              f"{prune_note}{agy_note}{tag_note}{ver_note}")
        bad += 0 if (ok_skill and ok_cfg and ok_python and ok_pay and ok_client and ok_ws
                     and ok_ver and ok_tag and ok_codex and ok_res and ok_shadow
                     and ok_prune and ok_agy) else 1
        # `#737` — 다른 검사는 모두 통과했고 출처만 어긋난 호스트를 사유별로 센다.
        #    실행 중 마스터에 커밋이 들어오면 「N 커밋 뒤」, 작업 트리를 고치면 「dirty 도장」
        #    — 정확히 이 모양으로 실패한다.
        if (ok_skill and ok_cfg and ok_python and ok_pay and ok_client and ok_ws
                and ok_tag and ok_codex and ok_res and ok_shadow and ok_prune and ok_agy):
            kind = _version_failure_kind(ver)
            behind_only += kind == "behind"
            dirty_only += kind == "dirty"
            behind_dirty += kind == "behind_dirty"
        if not ver["ok"]:
            behind_hosts.append((f.host, ver.get("behind"), ver.get("stamp_dirty")))
    # [중요] **끝에 한 줄로 모아 말한다** — 호스트별 줄에 섞이면 「몇 대가 낡았나」가 안 보인다.
    if behind_hosts:
        # [중요] **원인을 갈라 말한다.** 「커밋이 뒤처짐」과 「커밋은 같은데 추적 불가(dirty)」는
        #    고치는 방법이 다르다 — 전자는 재배달, 후자는 **마스터를 먼저 커밋**한 뒤 재배달이다.
        #    실측 2026-08-22: 재배달 직후 「최대 0 커밋 뒤」라고 찍혀 문구가 사실을 흐렸다.
        behind = [(h, n) for h, n, _d in behind_hosts if n]
        # [주의] 위의 정수 카운터 `dirty_only` 와 이름이 같으면 그것을 목록으로 덮는다 — 그러면
        #    `stats["dirty_only"]` 가 목록이 되어 `update` 의 실패 요약이 TypeError 로 죽었다
        #    (실측 2026-10-07, dirty 트리에서 `update`). 출력용 목록은 이름을 가른다.
        dirty_hosts = [h for h, n, d in behind_hosts if d and not n]
        other = [h for h, n, d in behind_hosts if not n and not d]
        print(f"\n  [중요] 마스터와 버전이 어긋난 기계 {len(behind_hosts)}대")
        print("        [중요] 클러스터는 버전이 하나다 — 배달물 해시가 같아도 같은 버전이 아니다.")
        if behind:
            print(f"        · 커밋이 뒤처짐 {len(behind)}대 (최대 {max(n for _h, n in behind)} "
                  f"커밋) → `python -m master.client deliver <프로젝트>`")
        if dirty_hosts:
            print(f"        · 커밋은 같지만 **dirty 트리에서 배달됨** {len(dirty_hosts)}대 — "
                  f"무엇이 갔는지 추적할 수 없다")
            print("          → 마스터를 **먼저 커밋**한 뒤 재배달한다 (순서가 계약이다)")
        if other:
            print(f"        · 판정 불가/계보 밖 {len(other)}대 — 위 사유 참조")

    # [중요] **마스터 자신의 서비스도 잰다** (`#301`). 배달 검증이 워커의 상주는 보는데
    #    마스터 서비스는 아무도 안 봤다 — 실측 2026-08-24: `ax-task-queue` 가 하루 동안
    #    옛 코드로 돌아 `.33` 의 프로젝트 태그가 무시됐다(`#293` 이 안 먹었다).
    #    [주의] 판정하고 **말하는 것까지**다 — 자동 재기동은 `docs/11` §11.5 위반이다.
    # `#737` — 줄은 `stale_lines()` 와 같은 규칙으로 만들되 판정(`check()`)을 직접 받는다:
    #    「기동 뒤 언제 바뀌었나」(mtime)가 있어야 update 가 「실행 중 변경 탓」을 가른다.
    fresh_changed_at = None
    try:
        from .. import service_freshness as _fresh
        verdicts = [v for v in _fresh.check() if v.stale or v.why]
        lines = [v.line for v in verdicts]
        if verdicts and not any(v.why for v in verdicts):
            fresh_changed_at = min(v.newest for v in verdicts)
    except Exception as e:                                   # noqa: BLE001
        lines = [f"[주의] 서비스 신선도를 재지 못했다 — {type(e).__name__}: {e}"]
    if lines:
        print(f"\n  [중요] 마스터 서비스 {len(lines)}개가 지금 코드가 아니다")
        for ln in lines:
            print(f"        · {ln}")
        print("        [주의] 자동 재기동은 하지 않는다 — 승인 사항이다 (`docs/11` §11.5)")
        bad += 1
    if stats is not None:
        stats.update(bad=bad, behind_only=behind_only, dirty_only=dirty_only,
                     behind_dirty=behind_dirty, fresh_bad=1 if lines else 0,
                     fresh_changed_at=fresh_changed_at)
    return 1 if bad else 0


def _version_failure_kind(ver: dict) -> str:
    """출처 대조 실패의 모양 (`#737`). `behind`·`dirty`·`behind_dirty`, 그 밖은 빈 문자열.

    [주의] 판정 불가·계보 밖(`behind is None`)이나 dirty 미상은 빈 문자열이다
    — 실행 중 변경 탓으로 접지 않는다.
    """
    if ver.get("ok"):
        return ""
    behind, dirty = ver.get("behind"), ver.get("stamp_dirty")
    if behind and dirty is False:
        return "behind"
    if behind == 0 and dirty:
        return "dirty"
    if behind and dirty:
        return "behind_dirty"
    return ""


def cmd_uproject(project: str, *, confirm: bool = False) -> int:
    """`.uproject` 의 에디터 플러그인 (`#335`). [중요] **`plan` 이 기본, `--confirm` 이 트리거.**

    `.uproject` 는 게임 소스라 §0.05 대상이다 — 배달이 조용히 켜지 않는다.
    """
    from . import uproject as U
    init = spec.load_init(project)
    for line in U.plan(project, init=init):
        print(line)
    if not confirm or not init.uproject_plugins:
        return 0
    print()
    print("[중요] --confirm 이 있다 — 요청자의 `.uproject` 에 쓴다")
    for line in U.apply(project, init=init, facts=_facts(project)):
        print(line)
    return 0


def cmd_ensure(project: str, *, only: str = "") -> int:
    """폐기된 데몬 ensure의 호환 안내. 워커 프로브나 원격 명령을 실행하지 않는다."""
    from client.init import residency as R
    print(f"  ― {project}: {R.DECOMMISSIONED_REASON} — ensure는 아무것도 실행하지 않는다")
    return 0


def _master_head() -> str:
    """마스터 저장소 HEAD 전체 해시. 읽지 못하면 빈 문자열 (`#737` — 테스트가 주입한다).

    [중요] `version.identity()` 와 **같은 저장소 뿌리(`version.REPO_ROOT`)** 를 읽는다 — 배달
    도장의 commit 과 같은 자리다. 실저장소 대신 임시 저장소로 돌리는 검사가 뿌리 하나만 바꾼다.
    """
    from .. import version as _version
    out, err = _version._git("rev-parse", "HEAD")
    return out if not err else ""


def _master_dirty():
    """마스터 작업 트리가 dirty 인가 — `True`/`False`, 읽지 못하면 `None` (`#737`).

    🔴 [중요] **정의를 새로 만들지 않는다** — 배달 도장(`bundle._delivery_stamp`)이 찍는
    `version.identity()["dirty"]`(= `git status --porcelain` 이 비었나) 그대로다. 정의가
    갈리면 「시작은 깨끗했다」는 말과 검사의 「dirty 도장」이 서로 다른 것을 센다.
    """
    from .. import version as _version
    return _version.identity().get("dirty")


def _head_trail(reads) -> str:
    """HEAD 읽기 값들을 관측 순서대로 `A → B → A` 로 (`#737` R42-1).

    [중요] 연속 중복만 접는다 — 끝이 시작과 같아도 **중간에 다른 값이 있었으면 그대로 보인다.**
    읽지 못한 값(빈 문자열)은 뺀다.
    """
    out: list = []
    for h in reads:
        if h and (not out or out[-1] != h):
            out.append(h)
    return " → ".join(h[:7] for h in out)


def _dirty_word(d) -> str:
    return "dirty" if d else "깨끗" if d is False else "모름"


def cmd_update(*, init: bool = False, all_projects: bool = False) -> int:
    """**마운트된** 프로젝트 작업장을 현재 리비전으로 맞추고 즉시 검사한다. `--all` 은 등록 전체.

    🔴 [중요] **기본 대상은 마운트 하나다** (`#655`·`#745`, 사용자 결정 2026-10-06). 종전에는
    등록 프로젝트 전부(5개 × 3대)를 직렬로 돌아 한 번에 15~20분이 걸렸고, 「검색·갱신은 마운트된
    것만」 원칙과도 어긋났다. 비마운트 프로젝트는 **마운트 전환 때** `set_active` 가 버전을
    대조해 뒤처진 기계만 맞춘다(`sync_check(align=True)` 가 그 기본이다). 그래서 커밋마다 돌리는
    이 명령이 다른 프로젝트까지 갈 이유가 없다.
    [중요] 대상은 여전히 호출자가 고르지 않는다 — 마운트(`projects.yaml` 의 `active`)가 정한다.
    마운트가 비었거나 등록에 없으면 **폴백 없이** 멈춘다. `all_projects=True`(`--all`)는 종전
    동작 그대로다: 등록 전체, 신규 프로젝트 자동 포함. 한 프로젝트가 실패해도 나머지까지 시도하되,
    하나라도 실패하면 전체 명령은 실패다.

    🔴 [중요] **실행 중 마스터 HEAD 이동을 따로 말한다** (`#737`, 사용자 결정 2026-10-05).
    배달은 그 순간의 HEAD 로 스탬프를 찍고 검사는 HEAD 를 다시 읽는다 — 그 사이 커밋이
    들어오면 검사가 「1 커밋 뒤」로 실패하고 요약은 「check」 한 단어뿐이었다(실측
    2026-10-04: 5fc6786 에서 시작 · 문서 커밋 4ac3099 가 중간에 들어와 ModularStage 2대 FAIL).
    그래서 시작·검사 직전·끝에서 HEAD 를 읽고, 움직였으면 그 사실과 그 탓인 실패를 갈라 적는다.
    🔴 [중요] **작업 트리 dirty 도 같은 방식으로 잰다** (`#737`, 사용자 승인 2026-10-05). 실측
    2026-10-05: HEAD 는 그대로인데 실행 중 `commit_flow.py` 를 커밋 없이 고쳐 이후 배달 도장이
    전부 `dirty=true` 로 찍혔고 검사 11/15 FAIL — 실행 중에는 아무 말도 없었다.
    시작부터 dirty 면 크게 경고하고 **계속한다** — 배달 도장은 「배달을 막지 않는다」가 계약이다
    (`bundle._delivery_stamp`). 실행 중 dirty 해지면 따로 말하고 rc 를 실패로 둔다.
    [주의] **초록불로 바꾸지 않는다** — 배달물은 배달 시점의 작업 트리에서 읽혔으므로 새 HEAD 와
    다를 수 있다. 자동 재실행·커밋 잠금은 하지 않는다(사람이 다시 돌린다).
    """
    import time

    registry = bundle.Registry.load()
    problems = registry.check()
    if problems:
        print("[중요] 프로젝트 레지스트리가 깨져 있어 전체 업데이트를 시작하지 않는다")
        for problem in problems:
            print(f"  FAIL {problem}")
        return 1
    if not registry.names:
        print("[중요] 등록된 프로젝트가 없다")
        return 1
    if all_projects:
        targets = list(registry.names)
        print(f"[update] 대상: 등록 프로젝트 전체 {len(targets)}개 (--all)")
    else:
        mounted = (getattr(registry, "active", "") or "").strip()
        if not mounted:
            print("[중요] 마운트(projects.yaml 의 active)가 비어 있다 — 폴백은 없다. "
                  "전체를 돌리려면 --all")
            return 2
        if mounted not in registry.names:
            print(f"[중요] 마운트 `{mounted}` 가 등록 목록에 없다 — 레지스트리를 먼저 고쳐라")
            return 1
        targets = [mounted]
        print(f"[update] 대상: 마운트된 {mounted} 만 — 비마운트 프로젝트는 전환 때 맞춘다 "
              "(전체는 --all)")

    # 서비스 신선도 실패가 「실행 중 파일 변경」 탓인지 가르는 기준 시각(파일 mtime 과 같은 축).
    started_at = int(time.time())
    head_start = _master_head()
    dirty_start = _master_dirty()
    if head_start:
        print(f"[update] 시작 마스터 HEAD {head_start[:7]} — 실행 중에는 마스터에 커밋하지 말 것")
    else:
        print("[주의] 시작 마스터 HEAD 를 읽지 못했다 — 실행 중 HEAD 이동을 감지할 수 없다")
    if dirty_start:
        print("[중요] 마스터 트리가 dirty 다 — 배달 도장이 「추적 불가」로 찍힌다, 커밋 후 실행하라")
        print("        [주의] 배달은 막지 않고 계속한다 (도장은 배달을 막지 않는 것이 계약이다) — "
              "검사의 dirty 실패는 이 탓이다")
    elif dirty_start is None:
        print("[주의] 시작 마스터 트리의 dirty 여부를 읽지 못했다 — 실행 중 dirty 변화를 감지할 수 없다")
    else:
        print("[update] 시작 마스터 트리 깨끗 — 실행 중에는 마스터 작업 트리도 고치지 말 것")

    failed: list[str] = []
    delivered: list[str] = []
    for project in targets:
        print(f"\n══ {project}: 현재 HEAD 배달", flush=True)
        if cmd_deliver(project, init=init):
            failed.append(f"{project}: deliver")
            continue
        delivered.append(project)

    head_pre_check = _master_head()
    dirty_pre_check = _master_dirty()
    if head_start and head_pre_check and head_pre_check != head_start:
        print(f"\n[중요] 배달 중 마스터 HEAD 가 움직였다: {head_start[:7]} → {head_pre_check[:7]}")
    if dirty_start is False and dirty_pre_check:
        print("\n[중요] 배달 중 마스터 트리가 dirty 해졌다 — 이후 배달 도장은 「추적 불가」다")

    # `#699` — 프로젝트별 전역 설정이 다음 배달에 덮어써지는 결함을
    # 즉시 검사가 놓쳤다. 전부 배달한 **뒤** 전부를 다시 재서 종료 상태를 본다.
    checked: list[tuple[str, dict]] = []
    for project in delivered:
        print(f"══ {project}: 배달 결과 검사", flush=True)
        stats: dict = {}
        if cmd_check(project, stats=stats):
            checked.append((project, stats))

    head_end = _master_head()
    dirty_end = _master_dirty()
    heads = (head_start, head_pre_check, head_end)
    dirties = (dirty_start, dirty_pre_check, dirty_end)
    seen = [h for h in heads if h]
    # R42-1 — **어느 읽기든** 시작과 다르면 이동이다(A→B→A 도 이동이다).
    moved = bool(head_start) and any(h != head_start for h in seen)
    became_dirty = dirty_start is False and any(d for d in dirties[1:])
    for project, stats in checked:
        failed.append(_label_check_failure(project, stats, moved=moved,
                                           dirty_start=bool(dirty_start),
                                           became_dirty=became_dirty, started_at=started_at))

    if moved:
        trail = _head_trail(heads)
        print(f"\n[중요] 실행 중 마스터 HEAD 가 움직였다: {trail}"
              " — 배달물이 새 HEAD 와 다를 수 있다, 다시 실행하라")
        if head_end and head_end == head_start:
            print("        [주의] 끝 HEAD 는 시작과 같지만 중간에 달랐다 — 그 사이 배달·검사는 "
                  "다른 HEAD 를 봤을 수 있다")
        print("        [주의] update 실행 중에는 마스터에 커밋하지 말 것 "
              "(배달은 그 순간의 작업 트리를 읽는다)")
    elif head_start and not head_end:
        print("\n[주의] 끝 마스터 HEAD 를 읽지 못했다 — 실행 중 HEAD 이동을 확인하지 못했다")
    if became_dirty:
        trail = " → ".join(_dirty_word(d) for d in dirties)
        print(f"\n[중요] 실행 중 마스터 트리가 dirty 해졌다 ({trail}) — 이후 배달 도장은 "
              "「추적 불가」다, 커밋한 뒤 다시 실행하라")
        print("        [주의] update 실행 중에는 마스터 작업 트리를 고치지 말 것 "
              "(배달은 그 순간의 작업 트리를 읽는다)")
    elif dirty_start:
        print("\n[주의] 시작부터 마스터 트리가 dirty 였다 — 커밋한 뒤 다시 실행하라")
    elif dirty_start is False and dirty_end is None:
        print("\n[주의] 끝 마스터 트리의 dirty 여부를 읽지 못했다 — 실행 중 dirty 변화를 확인하지 못했다")

    if failed or moved or became_dirty:
        why = ", ".join(failed) if failed else (
            "검사는 통과했으나 " + " · ".join(w for w, on in (
                ("HEAD 가 움직였다", moved), ("트리가 dirty 해졌다", became_dirty)) if on))
        print("\n[중요] 전체 업데이트 실패: " + why)
        return 1
    what = f"등록 프로젝트 {len(targets)}개" if all_projects else f"마운트된 {targets[0]}"
    print(f"\n[완료] {what}를 현재 HEAD로 배달·검사했다")
    return 0


def _label_check_failure(project: str, stats: dict, *, moved: bool, dirty_start: bool,
                         became_dirty: bool, started_at: int) -> str:
    """검사 실패 한 건의 요약 표기 (`#737`).

    실패 호스트 **전부**(+ 서비스 신선도)가 실행 중 변경으로 설명될 때만 그 탓으로 적는다.
    하나라도 다른 사유가 섞이거나 내역을 모르면 종전 표기 `<프로젝트>: check` 그대로다.
      · 「출처 N 커밋 뒤(dirty 아님)」      ← HEAD 이동
      · 「커밋은 같고 dirty 도장」          ← 시작부터 dirty / 실행 중 dirty
      · 「뒤처짐 + dirty 도장」             ← 둘 다
      · 서비스 신선도 — 바뀐 파일의 mtime 이 실행 시작 뒤 **그리고** 실행 중 변경(이동·dirty)이 있었을 때
    """
    plain = f"{project}: check"
    bad = stats.get("bad")
    if not bad:
        return plain
    dirty_cause = dirty_start or became_dirty
    bo, do, bd = (stats.get(k) or 0 for k in ("behind_only", "dirty_only", "behind_dirty"))
    fresh = stats.get("fresh_bad") or 0
    changed_at = stats.get("fresh_changed_at")
    fresh_ok = bool(fresh and changed_at is not None and changed_at >= started_at
                    and (moved or became_dirty))
    parts: list = []
    explained = 0
    if moved and bo:
        explained += bo
        parts.append(f"출처 뒤처짐 {bo}대")
    if dirty_cause and do:
        explained += do
        parts.append(f"dirty 도장 {do}대")
    if moved and dirty_cause and bd:
        explained += bd
        parts.append(f"뒤처짐+dirty 도장 {bd}대")
    if fresh_ok:
        explained += fresh
        parts.append("서비스 신선도(실행 중 파일 변경 — 재기동 필요)")
    if not parts or explained != bad:
        return plain
    used_head = moved and (bo or bd)
    used_dirty = dirty_cause and (do or bd)
    causes = [c for c, on in (("실행 중 HEAD 이동", used_head),
                              ("실행 중 트리 dirty", used_dirty and became_dirty),
                              ("시작부터 트리 dirty", used_dirty and dirty_start and not became_dirty),
                              ("실행 중 파일 변경", fresh_ok and not used_head and not used_dirty))
              if on]
    return f"{project}: check ({' · '.join(causes)} 탓 — {' · '.join(parts)})"


def cmd_master_local(*, apply: bool = False, check: bool = False) -> int:
    """마스터 로컬 CLI 셋(Claude·Codex·agy)에 `ax-client` 등록 — 기본은 계획만.

    [중요] 프로젝트 인자를 받지 않는다 — `config.json` 의 `project` 는 **마운트**다(`update` 처럼
    프로젝트를 고르지 않는 명령). 마운트를 못 읽으면 폴백 없이 멈춘다.
    """
    from . import master_local as ml
    if apply and check:
        print("[master-local] --apply 와 --check 는 따로 돌린다")
        return 2
    try:
        project = ml.mounted_project()
    except Exception as e:                                           # noqa: BLE001
        print(f"[master-local] [실패] 마운트를 못 읽는다 — {e}")
        return 2
    if not project:
        print("[master-local] [실패] 마운트(projects.yaml 의 active)가 비어 있다 — 폴백은 없다")
        return 2
    p = ml.Paths.default()
    try:
        if check:
            return ml.check(p, project)
        if apply:
            return ml.apply(p, project)
        for line in ml.plan(p, project):
            print(line)
        print("[master-local] 계획만 출력했다 — 쓰려면 --apply")
        return 0
    except ml.MasterLocalError as e:
        print(f"[master-local] [실패] {e}")
        return 1


def cmd_home_guides(*, apply: bool = False, host: str = "") -> int:
    """기계별 홈 안내서 대조 — 기본은 읽기 전용, `--apply` 는 copy 대상의 DIFF 만 (`#861`).

    프로젝트 인자를 받지 않는다 — 대상은 `home_guides.TARGETS` 표다.
    """
    from . import home_guides
    return home_guides.run(apply=apply, host=host)


_CMDS = {"probe": cmd_probe, "plan": cmd_plan, "deliver": cmd_deliver, "check": cmd_check,
         "ensure": cmd_ensure, "uproject": cmd_uproject, "update": cmd_update,
         "master-local": cmd_master_local, "setup-host": None,
         "home-guides": None}


def main(argv: list) -> int:
    # [중요] 콘솔 UTF-8 강제 (소 3.5.5) — 리눅스에선 no-op, 윈도우 CP949 에선 즉사를 막는다.
    from ..utf8 import enforce as _utf8_enforce
    _utf8_enforce()
    if not argv or argv[0] not in _CMDS:
        print(__doc__)
        return 2
    if argv[0] == "update":
        return cmd_update(init="--init" in argv, all_projects="--all" in argv)
    if argv[0] == "master-local":
        return cmd_master_local(apply="--apply" in argv, check="--check" in argv)
    if argv[0] == "home-guides":
        host = ""
        for a in argv[1:]:
            if a.startswith("--host="):
                host = a.split("=", 1)[1].strip()
        return cmd_home_guides(apply="--apply" in argv, host=host)
    if argv[0] == "setup-host":
        # 프로젝트 인자를 받지 않는다 — 대상은 마운트가 정한다(`setup_host` 머리말)
        from . import setup_host
        opts = dict(a[2:].split("=", 1) for a in argv[1:] if a.startswith("--") and "=" in a)
        if not opts.get("host") or not opts.get("root"):
            print("[중요] --host=<ip> 와 --root=<경로> 가 필요하다")
            return 2
        return setup_host.run(opts["host"], opts["root"], user=opts.get("user", ""),
                              confirm="--confirm" in argv)
    rest = [a for a in argv[1:] if not a.startswith("-")]
    # [중요] **fail-closed** — 주워 쓰지 않는다 (`#227` 소 1.2, 모듈 머리말 참조).
    if not rest:
        print(f"[중요] 프로젝트 인자가 없다 — 폴백은 없다.\n"
              f"    python -m master.client {argv[0]} <프로젝트>\n"
              f"  이 값이 각 기계의 `.ax/config.json` 의 `project` 태그가 되고, 그 태그로 "
              f"요청·응답이 결정된다.\n"
              f"  등록된 프로젝트를 보려면: python -m master.projects (MCP) 또는 "
              f"레지스트리(projects.yaml)")
        return 2
    project = rest[0]
    # [중요] `--init` 은 **명시할 때만**. 실측으로 값을 못 했다(22턴 $1.68 대 payload 0원,
    #    미상 목록이 글자까지 같았다) — payload 가 저장소 대비 낡았을 때만 쓴다.
    # [중요] `--host <ip>` — 한 대만. 값은 레지스트리의 호스트와 **정확히 일치**해야 한다.
    only = ""
    for a in argv[1:]:
        if a.startswith("--host="):
            only = a.split("=", 1)[1].strip()
    if argv[0] == "deliver":
        return cmd_deliver(project, init="--init" in argv, only=only)
    if argv[0] == "uproject":
        # [중요] 관례대로 `plan` 이 기본 — 쓰려면 `--confirm` 을 명시한다
        return cmd_uproject(project, confirm="--confirm" in argv)
    if argv[0] in ("probe", "plan", "check", "ensure"):
        return _CMDS[argv[0]](project, only=only)
    return _CMDS[argv[0]](project)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
