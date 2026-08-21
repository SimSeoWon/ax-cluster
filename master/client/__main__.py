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

from . import bundle

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


def cmd_plan(project: str) -> int:
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
        for n in bundle.skills_for(f.role):
            print(f"   → {f.home}/.claude/skills/{n}/SKILL.md "
                  f"({len(bundle.skill_text(n))}자)  [role={f.role}]")
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
        print(f"   → {f.path}/.git/info/exclude 에 `/{bundle.AX_DIR}/` (커밋 안 됨)")
    return 0


def cmd_deliver(project: str, *, init: bool = False) -> int:
    bad = 0
    for f in _facts(project):
        if not f.checkout_ok:
            print(f"  [중요] {f.host}: 체크아웃 없음 — 배달하지 않는다 ({'; '.join(f.errors)})")
            bad += 1
            continue
        try:
            r = bundle.deliver(project, f, init=init)
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
    for f in _facts(project):
        if not f.checkout_ok:
            print(f"  [주의] {f.host}: 체크아웃 없음")
            bad += 1
            continue
        ok_skill = True
        names = bundle.skills_for(f.role)
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

        mark = "OK" if (ok_skill and ok_cfg and ok_pay and ok_client and ok_ws) else "FAIL"
        pay_note = (f" · payload {len(pay)}개 일치" if pay and ok_pay
                    else f" · [중요] payload 불일치/없음 {len(stale)}개: {', '.join(stale[:3])}"
                    if pay else "")
        print(f"  {mark} {f.host} [{f.role}]: 스킬 {len(names)}종 "
              f"{'일치' if ok_skill else '불일치/없음'} · config {'있음' if ok_cfg else '없음'}"
              f"{pay_note}{ws_note}{client_note}")
        bad += 0 if (ok_skill and ok_cfg and ok_pay and ok_client and ok_ws) else 1
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
