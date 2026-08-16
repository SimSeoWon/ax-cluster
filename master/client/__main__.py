"""워커 번들 CLI (레드마인 #21).

    python -m master.client probe [<프로젝트>]     각 워커를 잰다 (읽기 전용)
    python -m master.client plan  [<프로젝트>]     배달할 내용만 보여준다 (쓰지 않는다)
    python -m master.client deliver [<프로젝트>]   config + 스킬 배달 → 되읽어 대조
    python -m master.client check [<프로젝트>]     배달된 것이 정본과 같은지 검사

🔴 **`probe` → `plan` → `deliver` 순서로 쓴다.** 남의 기계에 쓰는 작업이므로, 무엇을 어디에
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
            print(f"  ⚠️ {host}: user/path 미등록 — 건너뜀 (레지스트리를 고칠 것)")
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
            print("   🔴 체크아웃이 없어 배달 대상이 아니다")
            continue
        cfg = bundle.config_for(project, f)
        print(f"   → {f.path}/{bundle.CONFIG_REL}")
        print("     " + json.dumps(cfg["checkout"], ensure_ascii=False)
              + f" caps={cfg['capabilities']}")
        print(f"     backends={json.dumps(cfg['backends'], ensure_ascii=False)}")
        for n in bundle.skills_for(f.role):
            print(f"   → {f.home}/.claude/skills/{n}/SKILL.md "
                  f"({len(bundle.skill_text(n))}자)  [role={f.role}]")
        # 🔴 페이로드도 **눈으로 보여 준다** — 남의 기계에 쓰는 파일을 계획에서 감추면
        #    `plan` 이 존재하는 이유가 없어진다 (모듈 독스트링: *"무엇을 어디에 쓸지 먼저 본다"*)
        pay = bundle.payloads_for(f.role)
        if pay:
            base = f"{f.path}/{bundle.AX_DIR}/lib/{bundle.PAYLOAD_PKG}"
            for d in bundle.payload_dirs(f.role):
                print(f"   → {base}/{d + '/' if d else ''}__init__.py  (패키지 표식)")
            for rel in pay:
                print(f"   → {base}/{rel} ({len(bundle.payload_text(rel))}자)  [payload]")
        print(f"   → {f.path}/.git/info/exclude 에 `/{bundle.AX_DIR}/` (커밋 안 됨)")
    return 0


def cmd_deliver(project: str, *, init: bool = False) -> int:
    bad = 0
    for f in _facts(project):
        if not f.checkout_ok:
            print(f"  🔴 {f.host}: 체크아웃 없음 — 배달하지 않는다 ({'; '.join(f.errors)})")
            bad += 1
            continue
        try:
            r = bundle.deliver(project, f, init=init)
        except bundle.BundleError as e:
            print(f"  🔴 {f.host}: {e}")
            bad += 1
            continue
        print(f"  ✅ {f.host} [{f.role}]: config={r['config']} · CLAUDE.md {r['claude_md_mode']}")
        ini = r.get("init") or {}
        if ini.get("ran"):
            # ⚠️ 일회성 프로비저닝 비용 — 작업 비용과 섞지 않는다 (#64)
            if ini.get("error"):
                print(f"     ⚠️ /init 실패 — {ini['error']} (AX 블록만으로 진행)")
            else:
                print(f"     /init 실행 · 턴 {ini.get('turns', 0)} · "
                      f"${ini.get('cost_usd', 0):.3f} (일회성)")
        elif ini.get("error"):
            print(f"     ⚠️ {ini['error']}")
        for sp in r["skills"]:
            print(f"     skill={sp}")
        # 🔴 **페이로드도 찍는다.** 첫 실 배달(2026-08-16)에서 파일 8개가 **실제로 갔는데**
        #    출력에 안 나와서, 확인하려면 원격 디렉토리를 직접 뒤져야 했다.
        #    *"배달했다고 믿지 않는다"* 는 사람이 읽는 출력에도 적용된다 — 안 보이는 산출물은
        #    다음 세션에 **없는 것으로 읽힌다.**
        for pp in r.get("payload") or []:
            print(f"     payload={pp}")
        print("     .git/info/exclude ✅ · 해시 대조 통과")
    return 1 if bad else 0


def cmd_check(project: str) -> int:
    """배달본이 정본과 같은가. 🔴 사본은 갈라진다 — 그래서 잰다."""
    bad = 0
    for f in _facts(project):
        if not f.checkout_ok:
            print(f"  ⚠️ {f.host}: 체크아웃 없음")
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
        # 🔴 **페이로드도 잰다.** 스킬은 문서라 낡아도 사람이 읽다 눈치채지만, 파이썬 모듈은
        #    낡은 채로 **조용히 돈다** — `.33` 이 옛 review 로직으로 검수하면 그 판정은
        #    거짓말이다. 사본이 갈라지는 것이 이 명령의 존재 이유다.
        pay = bundle.payloads_for(f.role)
        stale: list = []
        for rel in pay:
            want = hashlib.sha256(bundle.payload_text(rel).encode("utf-8")).hexdigest()
            rp = f"{bundle.AX_DIR}/lib/{bundle.PAYLOAD_PKG}/{rel}"
            target = (f"{f.path}\\{rp.replace('/', chr(92))}" if f.windows
                      else f"{f.path}/{rp}")
            cmd = (f'powershell -Command "(Get-FileHash -LiteralPath \'{target}\' -Algorithm SHA256).Hash"'
                   if f.windows else f"sha256sum '{target}' 2>/dev/null | cut -d' ' -f1")
            _rc, got = bundle._ssh(f.host, f.user, cmd)
            if (got or "").strip().lower() != want:
                stale.append(rel)
        ok_pay = not stale
        mark = "✅" if (ok_skill and ok_cfg and ok_pay) else "🔴"
        pay_note = (f" · payload {len(pay)}개 일치" if pay and ok_pay
                    else f" · 🔴 payload 불일치/없음 {len(stale)}개: {', '.join(stale[:3])}"
                    if pay else "")
        print(f"  {mark} {f.host} [{f.role}]: 스킬 {len(names)}종 "
              f"{'일치' if ok_skill else '불일치/없음'} · config {'있음' if ok_cfg else '없음'}"
              f"{pay_note}")
        bad += 0 if (ok_skill and ok_cfg and ok_pay) else 1
    return 1 if bad else 0


_CMDS = {"probe": cmd_probe, "plan": cmd_plan, "deliver": cmd_deliver, "check": cmd_check}


def main(argv: list) -> int:
    if not argv or argv[0] not in _CMDS:
        print(__doc__)
        return 2
    rest = [a for a in argv[1:] if not a.startswith("-")]
    project = rest[0] if rest else DEFAULT_PROJECT
    # 🔴 `--init` 은 **명시할 때만**. 실측으로 값을 못 했다(22턴 $1.68 대 payload 0원,
    #    미상 목록이 글자까지 같았다) — payload 가 저장소 대비 낡았을 때만 쓴다.
    if argv[0] == "deliver":
        return cmd_deliver(project, init="--init" in argv)
    return _CMDS[argv[0]](project)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
