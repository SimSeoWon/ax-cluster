"""워커 번들 CLI (레드마인 #21).

    python -m master.client probe <프로젝트>     각 워커를 잰다 (읽기 전용)
    python -m master.client plan  <프로젝트>     배달할 내용만 보여준다 (쓰지 않는다)
    python -m master.client deliver <프로젝트>   config + 스킬 배달 → 되읽어 대조
    python -m master.client check <프로젝트>     배달된 것이 정본과 같은지 검사
    python -m master.client uproject <프로젝트>  에디터 플러그인 계획 (`--confirm` 으로 적용)

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
        # [중요] **MCP 엔트리를 계획에 찍는다** — 워커가 못 받는다는 판단이 조건문 한 줄에
        #    숨어 있으면 아무도 그것을 보지 못한다 (#261).
        mcp = spec.mcp_for(f.role, init)
        print(f"   → {f.path}/.mcp.json — 엔트리 {', '.join(mcp) or '(없음 — 이 역할은 받지 않는다)'}")
        # [중요] **codex 몫도 계획에 찍는다** (`#402`). 선언은 `spec.ENTRY_DOCS` ·
        #    `spec.codex_mcp_for` 하나씩이고, 안 찍으면 스킬 때(`#385`)와 같은 일이 난다 —
        #    배달은 정상인데 도구가 그것을 못 보는 상태가 **아무 표면에도 안 나타난다.**
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
        hk = spec.managed_hooks_for(f.role)
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
        ws = bundle.workshop_files(f.role, project)
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
            print(f"     residency=[주의] {res['error']}")
        if "agents_md" in r:
            print(f"     agents_md={r['agents_md']}  [{r.get('agents_md_mode', '?')}]")
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
        # [중요] **상주 갱신 출력 절이 여기 있었다** (`#277` → `#320` 으로 철거, 2026-08-27).
        #    상주가 없으므로 배달은 파일을 놓는 것으로 끝난다.
    return 1 if bad else 0


def cmd_check(project: str, *, only: str = "") -> int:
    """배달본이 정본과 같은가. [중요] 사본은 갈라진다 — 그래서 잰다."""
    bad = 0
    behind_hosts: list = []
    init = spec.load_init(project)
    for f in _facts(project, only=only):
        if not f.checkout_ok:
            print(f"  [주의] {f.host}: 체크아웃 없음")
            bad += 1
            continue
        ok_skill = True
        names = bundle.skills_for(f.role, init)
        for n in names:
            want = hashlib.sha256(bundle.skill_text(n).encode("utf-8")).hexdigest()
            # [중요] 도구별 자리를 **전부** 검사한다 — 한 곳만 보면 codex 쪽 누락이 안 보인다.
            for rel in spec.skill_rels(n):
                target = (f"{f.home}\\" + rel.replace("/", chr(92)) if f.windows
                          else f"{f.home}/{rel}")
                cmd = (f'powershell -Command "(Get-FileHash -LiteralPath \'{target}\' -Algorithm SHA256).Hash"'
                       if f.windows else f"sha256sum '{target}' 2>/dev/null | cut -d' ' -f1")
                rc, got = bundle._ssh(f.host, f.user, cmd)
                ok_skill = ok_skill and (got or "").strip().lower() == want
        cfg_path = (f"{f.path}\\{bundle.CONFIG_REL.replace('/', chr(92))}" if f.windows
                    else f"{f.path}/{bundle.CONFIG_REL}")
        rc2, _ = bundle._ssh(f.host, f.user,
                             (f'if exist "{cfg_path}" (echo OK)' if f.windows
                              else f"test -f '{cfg_path}' && echo OK"))
        ok_cfg = rc2 == 0
        # [중요] **페이로드도 잰다.** 스킬은 문서라 낡아도 사람이 읽다 눈치채지만, 파이썬 모듈은
        #    낡은 채로 **조용히 돈다** — `.33` 이 옛 review 로직으로 검수하면 그 판정은
        #    거짓말이다. 사본이 갈라지는 것이 이 명령의 존재 이유다.
        #    [주의] 해시는 **저장소 원문**으로 내고 **배달 위치**의 파일과 댄다 (#262).
        pay = bundle.payload_pairs(f.role)
        stale: list = []
        for rel, src in pay:
            want = hashlib.sha256(bundle.payload_text(src).encode("utf-8")).hexdigest()
            rp = f"{bundle.AX_DIR}/lib/{bundle.PAYLOAD_PKG}/{rel}"
            target = (f"{f.path}\\{rp.replace('/', chr(92))}" if f.windows
                      else f"{f.path}/{rp}")
            cmd = (f'powershell -Command "(Get-FileHash -LiteralPath \'{target}\' -Algorithm SHA256).Hash"'
                   if f.windows else f"sha256sum '{target}' 2>/dev/null | cut -d' ' -f1")
            _rc, got = bundle._ssh(f.host, f.user, cmd)
            if (got or "").strip().lower() != want:
                stale.append(rel)
        ok_pay = not stale
        # 요청자 전용 (소 3.8.4): .mcp.json 항목 + 역할 토큰
        ok_client = True
        client_note = ""
        if f.role == "requester":
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
            want_hooks = spec.managed_hooks_for(f.role)
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
                tp = (f"{f.path}\\{bundle.AX_DIR}\\token" if f.windows
                      else f"{f.path}/{bundle.AX_DIR}/token")
                cmd = (f'powershell -Command "(Get-FileHash -LiteralPath \'{tp}\' -Algorithm SHA256).Hash"'
                       if f.windows else f"sha256sum '{tp}' 2>/dev/null | cut -d' ' -f1")
                _rc, got_t = bundle._ssh(f.host, f.user, cmd)
                if (got_t or "").strip().lower() != want_t:
                    ok_client = False
                    client_note += " · [실패] 역할 토큰 불일치/없음 (재배달 필요)"
            else:
                client_note += " · [주의] 마스터에 requester 토큰이 없다 (init-role)"
        
        # [중요] **작업장 자산도 잰다** (#226 4번). 에이전트·스킬은 사람이 읽는 문서지만
        #    `tools:` 허용목록이 낡으면 **오류 없이 능력만 사라진다**(리포트 27 §13) — 페이로드가
        #    조용히 낡는 것과 같은 부류다. 33개를 한 번의 ssh 로 해시 뜬다.
        ws = bundle.workshop_files(f.role, project)
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

        # ── 상주 등록 (`#405`) — **파일이 아니라 「등록됐나」를 본다** ────────
        #    `#337` 의 훅과 같은 교훈이다: 파일 해시가 3자 일치해도 **등록이 없으면 안 돈다.**
        ok_res = True
        res_note = ""
        if f.role != "requester":
            from client.init import residency as _R
            _have_daemon = any(d.endswith("worker_daemon.py")
                               for d, _s in bundle.payload_pairs(f.role))
            if not _have_daemon:
                res_note = " · 상주 [건너뜀] 데몬 미배달 (`#404`)"
            else:
                _cmd = (f"schtasks /query /tn {_R.task_name(project)}" if f.windows
                        else "crontab -l 2>/dev/null")
                _rc, _out = bundle._ssh(f.host, f.user, _cmd)
                _hit = (_rc == 0) if f.windows else (_R.cron_marker(f) in (_out or ""))
                if not _hit:
                    ok_res = False
                    res_note = " · [실패] 상주 미등록 (배달만 되고 안 돈다)"

        # ── codex 몫 (`#402`) — **역할 무관** ────────────────────────────
        #    [중요] `AGENTS.md` 는 「있나」가 아니라 **관리 블록이 최신인가**를 본다. 전문은
        #    사람이 고칠 수 있으므로 해시 전체 대조는 정상을 실패로 답한다 — `check` 가
        #    정상 배달을 실패로 답한 전례가 이미 있다(`#337` 훅, 정확 일치 비교).
        ok_codex = True
        codex_note = ""
        _csep = chr(92) if f.windows else "/"
        raw_a = bundle._remote_read(f, f"{f.path}{_csep}{spec.CODEX_ENTRY_REL}")
        want_block = bundle.managed_block(project, f)
        if not (raw_a or "").strip():
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
            got = bundle.codex_mcp_get(f, n)
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
        ver = bundle.compare_version(f)
        ok_ver = ver["ok"]
        ver_note = f" · 출처 {ver['reason']}"
        # [중요] **저장된 태그를 기대값과 댄다** — 「저장」만 있고 「관리」가 없으면 태그가
        #    조용히 어긋난다. 이 태그로 요청·응답이 결정된다(§12.5-c).
        tag = bundle.compare_tag(f, project)
        ok_tag = tag["ok"]
        tag_note = f" · {tag['reason']}"

        mark = ("OK" if (ok_skill and ok_cfg and ok_pay and ok_client and ok_ws
                         and ok_ver and ok_tag and ok_codex and ok_res) else "FAIL")
        pay_note = (f" · payload {len(pay)}개 일치" if pay and ok_pay
                    else f" · [중요] payload 불일치/없음 {len(stale)}개: {', '.join(stale[:3])}"
                    if pay else "")
        print(f"  {mark} {f.host} [{f.role}]: 스킬 {len(names)}종 "
              f"{'일치' if ok_skill else '불일치/없음'} · config {'있음' if ok_cfg else '없음'}"
              f"{pay_note}{ws_note}{client_note}{codex_note}{res_note}{rm_note}{tag_note}{ver_note}")
        bad += 0 if (ok_skill and ok_cfg and ok_pay and ok_client and ok_ws
                     and ok_ver and ok_tag and ok_codex and ok_res) else 1
        if not ver["ok"]:
            behind_hosts.append((f.host, ver.get("behind"), ver.get("stamp_dirty")))
    # [중요] **끝에 한 줄로 모아 말한다** — 호스트별 줄에 섞이면 「몇 대가 낡았나」가 안 보인다.
    if behind_hosts:
        # [중요] **원인을 갈라 말한다.** 「커밋이 뒤처짐」과 「커밋은 같은데 추적 불가(dirty)」는
        #    고치는 방법이 다르다 — 전자는 재배달, 후자는 **마스터를 먼저 커밋**한 뒤 재배달이다.
        #    실측 2026-08-22: 재배달 직후 「최대 0 커밋 뒤」라고 찍혀 문구가 사실을 흐렸다.
        behind = [(h, n) for h, n, _d in behind_hosts if n]
        dirty_only = [h for h, n, d in behind_hosts if d and not n]
        other = [h for h, n, d in behind_hosts if not n and not d]
        print(f"\n  [중요] 마스터와 버전이 어긋난 기계 {len(behind_hosts)}대")
        print("        [중요] 클러스터는 버전이 하나다 — 배달물 해시가 같아도 같은 버전이 아니다.")
        if behind:
            print(f"        · 커밋이 뒤처짐 {len(behind)}대 (최대 {max(n for _h, n in behind)} "
                  f"커밋) → `python -m master.client deliver <프로젝트>`")
        if dirty_only:
            print(f"        · 커밋은 같지만 **dirty 트리에서 배달됨** {len(dirty_only)}대 — "
                  f"무엇이 갔는지 추적할 수 없다")
            print("          → 마스터를 **먼저 커밋**한 뒤 재배달한다 (순서가 계약이다)")
        if other:
            print(f"        · 판정 불가/계보 밖 {len(other)}대 — 위 사유 참조")

    # [중요] **마스터 자신의 서비스도 잰다** (`#301`). 배달 검증이 워커의 상주는 보는데
    #    마스터 서비스는 아무도 안 봤다 — 실측 2026-08-24: `ax-task-queue` 가 하루 동안
    #    옛 코드로 돌아 `.33` 의 프로젝트 태그가 무시됐다(`#293` 이 안 먹었다).
    #    [주의] 판정하고 **말하는 것까지**다 — 자동 재기동은 `docs/11` §11.5 위반이다.
    try:
        from .. import service_freshness as _fresh
        lines = _fresh.stale_lines()
    except Exception as e:                                   # noqa: BLE001
        lines = [f"[주의] 서비스 신선도를 재지 못했다 — {type(e).__name__}: {e}"]
    if lines:
        print(f"\n  [중요] 마스터 서비스 {len(lines)}개가 지금 코드가 아니다")
        for ln in lines:
            print(f"        · {ln}")
        print("        [주의] 자동 재기동은 하지 않는다 — 승인 사항이다 (`docs/11` §11.5)")
        bad = 1
    return 1 if bad else 0


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


_CMDS = {"probe": cmd_probe, "plan": cmd_plan, "deliver": cmd_deliver, "check": cmd_check,
         "uproject": cmd_uproject}


def main(argv: list) -> int:
    # [중요] 콘솔 UTF-8 강제 (소 3.5.5) — 리눅스에선 no-op, 윈도우 CP949 에선 즉사를 막는다.
    from ..utf8 import enforce as _utf8_enforce
    _utf8_enforce()
    if not argv or argv[0] not in _CMDS:
        print(__doc__)
        return 2
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
    if argv[0] in ("probe", "plan", "check"):
        return _CMDS[argv[0]](project, only=only)
    return _CMDS[argv[0]](project)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
