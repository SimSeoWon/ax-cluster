"""워커 번들 CLI (레드마인 #21).

    python -m master.client probe [<프로젝트>]     각 워커를 잰다 (읽기 전용)
    python -m master.client plan  [<프로젝트>]     배달할 내용만 보여준다 (쓰지 않는다)
    python -m master.client deliver [<프로젝트>]   config + 스킬 배달 → 되읽어 대조
    python -m master.client check [<프로젝트>]     배달된 것이 정본과 같은지 검사

[중요] **`probe` → `plan` → `deliver` 순서로 쓴다.** 남의 기계에 쓰는 작업이므로, 무엇을 어디에
쓸지 먼저 눈으로 본다.
"""
from __future__ import annotations

import hashlib
import json
import sys

from . import bundle, spec

DEFAULT_PROJECT = "ModularStage"


def _facts(project: str) -> list:
    out = []
    for host, user, path, driven, role in bundle.workshops(project):
        if not user or not path:
            print(f"  [주의] {host}: user/path 미등록 — 건너뜀 (레지스트리를 고칠 것)")
            continue
        out.append(bundle.probe(host, user, path, driven, role))
    return out


def cmd_probe(project: str) -> int:
    facts = _facts(project)
    for f in facts:
        print(f"  {f.summary}")
    return 0 if facts else 1


def _print_spec(project: str, init) -> None:
    """[중요] **사양을 계획 맨 위에 찍는다** (#266). 오버레이가 배선됐는지는 `config.yaml` 을
    고쳐 이 줄이 달라지는지로 확인한다 — 안 달라지면 선언이 안 먹는 것이다."""
    print(f"\n══ 초기화 사양 — {project} (선언: master/client/spec.py + config.yaml 의 `init:`)")
    print("   서버 절: " + " → ".join(s.key for s in spec.SERVER_STEPS)
          + "   [주의] 아직 실행기가 없다 (#259)")
    print(f"   도메인: {', '.join(init.domains) or '(선언 없음)'}")
    print(f"   컨벤션 절: {', '.join(init.convention_sections)}  "
          f"← 프로젝트 repo/CLAUDE.md 에서 읽는다 (work/conventions.py)")
    if init.extra_skills or init.extra_mcp:
        print(f"   프로젝트 추가: skills={init.extra_skills or '{}'} mcp={init.extra_mcp or '{}'}")


def cmd_plan(project: str) -> int:
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
    for f in _facts(project):
        print(f"\n── {f.summary}")
        if not f.checkout_ok:
            print("   [중요] 체크아웃이 없어 배달 대상이 아니다")
            continue
        cfg = bundle.config_for(project, f)
        print(f"   → {f.path}/{bundle.CONFIG_REL}")
        print("     " + json.dumps(cfg["checkout"], ensure_ascii=False)
              + f" caps={cfg['capabilities']}")
        print(f"     backends={json.dumps(cfg['backends'], ensure_ascii=False)}")
        for n in bundle.skills_for(f.role, init):
            print(f"   → {f.home}/.claude/skills/{n}/SKILL.md "
                  f"({len(bundle.skill_text(n))}자)  [role={f.role}]")
        # [중요] **MCP 엔트리를 계획에 찍는다** — 워커가 못 받는다는 판단이 조건문 한 줄에
        #    숨어 있으면 아무도 그것을 보지 못한다 (#261).
        mcp = spec.mcp_for(f.role, init)
        print(f"   → {f.path}/.mcp.json — 엔트리 {', '.join(mcp) or '(없음 — 이 역할은 받지 않는다)'}")
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
        ws = bundle.workshop_files(f.role)
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
        exc = ", ".join(f"`{x}`" for x in spec.git_excludes_for(f.role))
        print(f"   → {f.path}/.git/info/exclude 에 {exc} (커밋 안 됨)")
        # [주의] 추적 중인 파일은 exclude 로 못 막는다 — 이름으로 보고한다(고치지는 않는다).
        # [중요] **`.gitignore` 가 산출물 오염을 막는 쪽이다** (사용자 2026-08-22). info/exclude 는
        #    클론 로컬이라 그 기계에만 듣고, 팀원이 새로 클론하면 없다. 원전도 `.gitignore` 에
        #    마커 블록을 써서 사람이 커밋하게 했다(ModularStage `.gitignore:30-42` 가 그 결과다).
        #    [주의] 쓰는 것은 #259 onboard 다 — 여기서는 무엇이 들어갈지만 보여 준다.
        print(f"   → {f.path}/.gitignore 의 `{spec.GITIGNORE_BEGIN.split(chr(32))[0]}` 블록 "
              f"({len(spec.GITIGNORE_BODY)}줄, 커밋은 사람 몫 — 마스터는 push 못 한다)")
        tracked = bundle.tracked_managed(f)
        if tracked:
            print(f"   [중요] 저장소가 **추적 중**이라 exclude 가 안 듣는다: {', '.join(tracked)}"
                  f"\n       → 인프라 파일이 게임 산출물에 섞여 있다. `git rm --cached <파일>` +"
                  f" 위 .gitignore 블록을 **사람이 한 번 커밋**하면 끝난다 (처분은 #259)")
        # [중요] **폐지분을 이름으로 찍는다** (#266 완료 조건 3). 표에서 지우는 것만으로는 이미
        #    배달된 기계가 정리되지 않는다 — `#232` 가 그 부류였고 그때 실패는 조용했다.
        rm = spec.removals_for(f.role, init)
        for kind, names in (("스킬", rm["skills"]), ("MCP 엔트리", rm["mcp"])):
            if names:
                print(f"   ✕ 폐지 {kind}: {', '.join(names)}  "
                      f"[주의] 지우는 것은 아직 이 명령이 하지 않는다 (#232)")
    return 0


def cmd_deliver(project: str, *, init: bool = False) -> int:
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
    for f in _facts(project):
        if not f.checkout_ok:
            print(f"  [중요] {f.host}: 체크아웃 없음 — 배달하지 않는다 ({'; '.join(f.errors)})")
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
        if "role_token" in r:
            # [중요] 값이 아니라 경로(또는 부재 안내)만 찍힌다
            print(f"     role_token={r['role_token']}")
        print("     .git/info/exclude [완료] · 해시 대조 통과")
    return 1 if bad else 0


def cmd_check(project: str) -> int:
    """배달본이 정본과 같은가. [중요] 사본은 갈라진다 — 그래서 잰다."""
    bad = 0
    behind_hosts: list = []
    init = spec.load_init(project)
    for f in _facts(project):
        if not f.checkout_ok:
            print(f"  [주의] {f.host}: 체크아웃 없음")
            bad += 1
            continue
        ok_skill = True
        names = bundle.skills_for(f.role, init)
        for n in names:
            want = hashlib.sha256(bundle.skill_text(n).encode("utf-8")).hexdigest()
            target = (f"{f.home}\\.claude\\skills\\{n}\\SKILL.md" if f.windows
                      else f"{f.home}/.claude/skills/{n}/SKILL.md")
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
        ws = bundle.workshop_files(f.role)
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

        mark = ("OK" if (ok_skill and ok_cfg and ok_pay and ok_client and ok_ws and ok_ver)
                else "FAIL")
        pay_note = (f" · payload {len(pay)}개 일치" if pay and ok_pay
                    else f" · [중요] payload 불일치/없음 {len(stale)}개: {', '.join(stale[:3])}"
                    if pay else "")
        print(f"  {mark} {f.host} [{f.role}]: 스킬 {len(names)}종 "
              f"{'일치' if ok_skill else '불일치/없음'} · config {'있음' if ok_cfg else '없음'}"
              f"{pay_note}{ws_note}{client_note}{rm_note}{ver_note}")
        bad += 0 if (ok_skill and ok_cfg and ok_pay and ok_client and ok_ws and ok_ver) else 1
        if not ver["ok"]:
            behind_hosts.append((f.host, ver.get("behind"), ver.get("stamp_dirty")))
    # [중요] **끝에 한 줄로 모아 말한다** — 호스트별 줄에 섞이면 「몇 대가 낡았나」가 안 보인다.
    if behind_hosts:
        known = [n for _h, n, _d in behind_hosts if n is not None]
        dirty_n = sum(1 for _h, _n, d in behind_hosts if d)
        span = f"최대 {max(known)} 커밋 뒤" if known else "거리 판정 불가"
        print(f"\n  [중요] 마스터와 버전이 다른 기계 {len(behind_hosts)}대 ({span}"
              + (f" · {dirty_n}대는 dirty 트리에서 배달됨" if dirty_n else "") + ")")
        print("        [중요] 클러스터는 버전이 하나다 — 배달물 해시가 같아도 같은 버전이 아니다.")
        print("        → `python -m master.client deliver <프로젝트>` 로 맞춘다")
    return 1 if bad else 0


_CMDS = {"probe": cmd_probe, "plan": cmd_plan, "deliver": cmd_deliver, "check": cmd_check}


def main(argv: list) -> int:
    # [중요] 콘솔 UTF-8 강제 (소 3.5.5) — 리눅스에선 no-op, 윈도우 CP949 에선 즉사를 막는다.
    from ..utf8 import enforce as _utf8_enforce
    _utf8_enforce()
    if not argv or argv[0] not in _CMDS:
        print(__doc__)
        return 2
    rest = [a for a in argv[1:] if not a.startswith("-")]
    project = rest[0] if rest else DEFAULT_PROJECT
    # [중요] `--init` 은 **명시할 때만**. 실측으로 값을 못 했다(22턴 $1.68 대 payload 0원,
    #    미상 목록이 글자까지 같았다) — payload 가 저장소 대비 낡았을 때만 쓴다.
    if argv[0] == "deliver":
        return cmd_deliver(project, init="--init" in argv)
    return _CMDS[argv[0]](project)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
