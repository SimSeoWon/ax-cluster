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
        print(f"   → {f.path}/.git/info/exclude 에 `/{bundle.AX_DIR}/` (커밋 안 됨)")
    return 0


def cmd_deliver(project: str) -> int:
    bad = 0
    for f in _facts(project):
        if not f.checkout_ok:
            print(f"  🔴 {f.host}: 체크아웃 없음 — 배달하지 않는다 ({'; '.join(f.errors)})")
            bad += 1
            continue
        try:
            r = bundle.deliver(project, f)
        except bundle.BundleError as e:
            print(f"  🔴 {f.host}: {e}")
            bad += 1
            continue
        print(f"  ✅ {f.host} [{f.role}]: config={r['config']} · CLAUDE.md {r['claude_md_mode']}")
        for sp in r["skills"]:
            print(f"     skill={sp}")
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
        mark = "✅" if (ok_skill and ok_cfg) else "🔴"
        print(f"  {mark} {f.host} [{f.role}]: 스킬 {len(names)}종 "
              f"{'일치' if ok_skill else '불일치/없음'} · config {'있음' if ok_cfg else '없음'}")
        bad += 0 if (ok_skill and ok_cfg) else 1
    return 1 if bad else 0


_CMDS = {"probe": cmd_probe, "plan": cmd_plan, "deliver": cmd_deliver, "check": cmd_check}


def main(argv: list) -> int:
    if not argv or argv[0] not in _CMDS:
        print(__doc__)
        return 2
    return _CMDS[argv[0]](argv[1] if len(argv) > 1 else DEFAULT_PROJECT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
