"""온톨로지 CLI — 재합성·검증·측정 (소 1.3.3).

    python -m master.ontology status                 도메인 상태 + stale 판정
    python -m master.ontology plan <도메인>           [중요] LLM 0 — 조각·프롬프트 크기만 본다
    python -m master.ontology verify [<도메인>]       사실 게이트만 (LLM 0)
    python -m master.ontology dry <도메인>            합성해 보고 **쓰지 않는다**
    python -m master.ontology refresh [<도메인>…]     합성해서 쓴다 (stale 만이 기본)
    python -m master.ontology describe --show         레이어 책임 서술 — **읽기만** (LLM 0)
    python -m master.ontology describe [<도메인>…]    그 서술을 뽑아 쓴다 ([중요] 도메인당 1콜)

[중요] **`plan` 부터 쓴다.** 노드 시간을 태우기 전에 프롬프트가 예산 안에 드는지, 몇 조각이
나오는지를 LLM 없이 본다 — 리포트 10 §8 의 사고가 "재보지 않고 보낸" 데서 났다.
[중요] **그 다음이 `dry`.** 받아온 온톨로지 247 yaml 을 통과율도 모른 채 덮지 않는다.
"""
from __future__ import annotations

import sys

from ..context_search.paths import resolve
from . import contexts as ctx_mod, collect, domain_md, stale, synth, verify_facts

# [중요] 출력에 남겨야 하는 토큰. JSON 5~15건(description·flow 포함) 기준 실측 여유값.
OUTPUT_RESERVE = 2500


def _paths(name: str = ""):
    return resolve(name)


def cmd_status(argv: list) -> int:
    paths = _paths()
    docs = domain_md.read_all(paths)
    if not docs:
        print("active 도메인이 없다 — `context/_domains/*.md` 를 확인하라")
        return 1
    print(f"프로젝트 {paths.name} · active 도메인 {len(docs)}")
    for d in docs:
        m = collect.members_of(paths, d.domain)
        print(f"  {d.domain:32s} 멤버 {len(m):3d} · {d.summary_note}")
    print()
    results = stale.compute(paths)
    print(stale.summary(results))
    # [중요] stale 옆에 **어떻게 다시 만들 것인지**를 같이 낸다 (소 3.2.2). LLM 0·부작용 0 이고,
    # *"왜 통짜로 돌았나"* 를 사람이 사후가 아니라 사전에 본다.
    if results:
        from . import invalidate
        print()
        for r in results:
            print("  " + invalidate.plan_domain_refresh(paths, r.domain).summary)
    return 0


def cmd_plan(argv: list) -> int:
    """[중요] LLM 0. 조각 수·프롬프트 크기·응집 순서를 눈으로 본다."""
    from . import prompt as prompt_mod
    paths = _paths()
    targets = argv or [d.domain for d in domain_md.read_all(paths)]
    total = requests = 0
    for name in targets:
        doc = domain_md.read(paths, name)
        if doc is None:
            print(f"  {name}: 도메인 MD 없음")
            continue
        members = collect.members_of(paths, name)
        chunks = ctx_mod.chunk_domain(paths, name, members=members)
        print(f"\n{name} — 멤버 {len(members)} → {len(chunks)}조각")
        for c in chunks:
            pa = len(prompt_mod.actions(doc, c))
            pi = len(prompt_mod.invariants(doc, c))
            total += pa + pi
            requests += 2
            # [중요] 실측 환산비 (2026-08-09, `prompt_eval_count`): 35B 2.85자/tok · 14b 2.79자/tok.
            #    보수적으로 작은 쪽을 쓴다 — 토큰을 과소평가하면 출력이 잘린다.
            tok = int(max(pa, pi) / 2.79)
            head = synth.NUM_CTX - tok
            flag = "" if head >= OUTPUT_RESERVE else f" [중요]출력여유 {head}tok"
            print(f"    [{c.part[0]}/{c.part[1]}] 클래스 {len(c.items):2d} · 발췌 {c.chars:6d}자"
                  f" · 프롬프트 {max(pa, pi):6d}자 ≈ {tok:5d}tok · 출력여유 {head:5d}tok{flag}")
            print(f"        {', '.join(sorted(c.names))}")
    print(f"\n전체 프롬프트 {total:,}자 · 요청 {requests}건 "
          f"(출력 여유 기준 {OUTPUT_RESERVE}tok, num_ctx {synth.NUM_CTX})")
    return 0


def cmd_verify(argv: list) -> int:
    """사실 게이트만 돌린다 (LLM 0) — 지금 있는 온톨로지가 소스와 맞는가."""
    paths = _paths()
    targets = argv or [d.domain for d in domain_md.read_all(paths)]
    bad = 0
    for name in targets:
        r = verify_facts.verify_domain(paths, name)
        mark = "OK" if r.ok else "FAIL"
        print(f"  {mark} {name}: {r.reason}")
        bad += 0 if r.ok else 1
    return 1 if bad else 0


def _report(r: synth.DomainResult) -> None:
    print(f"  {r.summary}")
    for n in r.parse_notes:
        print(f"      {n}")
    for d in r.dropped_facts:
        print(f"      [중요] 버림 {d}")
    if r.written:
        print(f"      {r.written.summary}")



def _models(argv: list) -> tuple:
    """`--model claude` / `--model agy` / `--model local`. [중요] 기본은 로컬 2노드.

    실측(리포트 11 §20)으로 **로컬 레인의 합성이 받아온 스냅샷보다 얕다**는 것이 드러났다.
    레인이 코드에는 있는데(`synth.CLI_MODELS`) **CLI 로 고를 수 없어** 그 비교를 못 하고 있었다.
    """
    if "--model" not in argv:
        return synth.DEFAULT_MODELS
    v = argv[argv.index("--model") + 1] if argv.index("--model") + 1 < len(argv) else ""
    if v in synth.CLI_MODELS:
        return (v,)
    if v == "local":
        return synth.DEFAULT_MODELS
    raise SystemExit(f"  [중요] 모르는 레인: {v!r} — {('local',) + synth.CLI_MODELS} 중 하나")


def _rest(argv: list) -> list:
    """플래그와 그 값을 걷어낸 나머지(도메인 이름들)."""
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a == "--model":
            skip = True
            continue
        if a.startswith("-"):
            continue
        out.append(a)
    return out


def cmd_dry(argv: list) -> int:
    paths = _paths()
    models, names = _models(argv), _rest(argv)
    if not names:
        print("도메인 이름이 필요하다 — `dry <도메인> [--model claude|agy|local]`")
        return 2
    print(f"  레인: {', '.join(m.split('/')[-1] for m in models)}")
    for name in names:
        r = synth.refresh_domain(paths, name, dry_run=True, models=models)
        _report(r)
    return 0


def cmd_refresh(argv: list) -> int:
    paths = _paths()
    models, argv = _models(argv), _rest(argv)
    try:
        st = synth.run(paths, domains=argv or None, models=models, progress=print)
    except synth.SynthError as e:
        print(f"[중요] {e}")
        return 1
    print(st.summary)
    for r in st.results:
        _report(r)
    return 0 if st.failed == 0 else 1



# ── 사람이 온톨로지를 손보는 자리 (소 1.3.1 · 1.3.2 · 1.3.6 · 1.3.7 · 1.3.9) ──────────
#
# [중요] **전부 사람이 부른다.** 자동 승급은 폐기됐다(2026-06-01 영구 비활성) — 여기 있는
# 어떤 명령도 스스로 도메인을 만들거나 클래스를 편입하지 않는다.

def cmd_describe(argv: list) -> int:
    """describe [--show] [도메인…] — 레이어별 책임 서술 (소 3.1.4). [중요] 도메인당 LLM 1콜.

    `--show` 는 **읽기만** 한다 (LLM 0) — 지금 무엇이 있고 무엇이 잠겨 있는지.
    """
    from . import descriptions as dm
    paths = _paths()
    show = "--show" in argv
    models, argv = _models([a for a in argv if a != "--show"]), _rest(
        [a for a in argv if a != "--show"])
    targets = argv or [d.domain for d in domain_md.read_all(paths)]
    for domain in targets:
        if show:
            rows = []
            for n in (1, 2, 3):
                got = dm.read(paths.ontology / "domains" / domain / f"L{n}" / dm.FILENAME)
                if got:
                    rows.append(f"L{n}{'' if got['verified_by_user'] else ''} "
                                f"{len(got['body'])}자")
            print(f"  {domain:32s} {' · '.join(rows) or '없음'}")
            continue
        print(f"  {domain} … ", end="", flush=True)
        print(synth.describe_domain(paths, domain, model=models[0]))
    return 0


def cmd_new(argv: list) -> int:
    """new <도메인> [상위] — 씨앗 MD 를 만든다. [중요] 덮지 않는다."""
    from . import create
    if not argv:
        print("  new <도메인> [상위]"); return 2
    paths = _paths()
    try:
        r = create.create(paths, argv[0], parent=argv[1] if len(argv) > 1 else "")
    except create.CreateError as e:
        print(f"  [중요] {e}"); return 1
    print("  " + r.summary)
    print(f"  → {r.path}  (열어서 절을 채운 뒤 `refresh` 로 합성한다)")
    return 0


def cmd_unassigned(argv: list) -> int:
    """unassigned [표본수] — 어느 도메인에도 없는 클래스. **노출만 한다.**"""
    from . import unassigned
    paths = _paths()
    n = int(argv[0]) if argv and argv[0].isdigit() else unassigned.DEFAULT_LIMIT
    print(unassigned.scan(paths, sample=n).render(limit=n))
    return 0


def cmd_lock(argv: list) -> int:
    """lock <도메인> <kind> <이름> | lock --list [도메인] — 검수 잠금."""
    from . import edit
    paths = _paths()
    if argv and argv[0] in ("--list", "-l"):
        rows = edit.locked_items(paths, argv[1] if len(argv) > 1 else "")
        print(f"  잠긴 항목 {len(rows)}건")
        for r in rows:
            print(f"    {r['domain']}/{r['layer']}/{r['kind']}/{r['name']}")
        return 0
    if len(argv) < 3:
        print("  lock <도메인> <objects|actions|invariants> <이름>  또는  lock --list"); return 2
    try:
        print("  " + edit.set_lock(paths, argv[0], argv[1], argv[2], True).summary)
    except edit.EditError as e:
        print(f"  [중요] {e}"); return 1
    return 0


def cmd_unlock(argv: list) -> int:
    """unlock <도메인> <kind> <이름> — [중요] 풀면 다음 재합성이 덮는다."""
    from . import edit
    if len(argv) < 3:
        print("  unlock <도메인> <objects|actions|invariants> <이름>"); return 2
    try:
        print("  " + edit.set_lock(_paths(), argv[0], argv[1], argv[2], False).summary)
    except edit.EditError as e:
        print(f"  [중요] {e}"); return 1
    return 0


def cmd_view(argv: list) -> int:
    """view [출력경로] — 자립형 HTML 한 장을 만든다. [중요] **서비스를 띄우지 않는다.**

    [주의] 이 문서는 비공개 게임 구조를 담는다 — 내부망에 올릴지는 **사람이 정한다**
    (2026-08-10 결정: 파일로만 두고 공유는 나중에).
    """
    from pathlib import Path
    from . import view as vw
    paths = _paths()
    out = Path(argv[0]) if argv and not argv[0].startswith("-") else None
    try:
        p, n = vw.write(paths, out=out)
    except Exception as e:                                # noqa: BLE001
        print(f"  [중요] {e}")
        return 1
    print(f"  [완료] {p}  ({n:,} 바이트, 자립형)")
    print("  브라우저로 그 파일을 열면 된다. 외부 자원을 쓰지 않는다.")
    return 0


def cmd_drift(argv: list) -> int:
    """drift [도메인] — 트윈과 소스가 어긋난 곳. [중요] **보고만 한다.**"""
    from . import drift as dr
    print(dr.audit(_paths(), domain=argv[0] if argv and not argv[0].startswith("-") else "").render())
    return 0


def cmd_protect(argv: list) -> int:
    """protect [--off] [--apply] [도메인] --why <사유> — 재생성으로 대체하지 않을 것을 표시.

    [중요] `verified_by_user`(검수 잠금)와 **다른 표식**이다 — 247건에 "사람이 검수했다" 를 찍으면
    나중에 *진짜로 검수한 것*을 구분할 수 없다. 기본은 계획만.
    """
    from . import edit as oe
    why = ""
    if "--why" in argv:
        i = argv.index("--why")
        why = argv[i + 1] if i + 1 < len(argv) else ""
        argv = argv[:i] + argv[i + 2:]
    on = "--off" not in argv
    apply = "--apply" in argv
    rest = [a for a in argv if not a.startswith("-")]
    paths = _paths()
    if on and not why:
        print('  protect <도메인> --why "왜 재생성으로 대체하면 안 되는지" [--apply]')
        return 2
    try:
        r = oe.protect_all(paths, domain=rest[0] if rest else "", reason=why, on=on, apply=apply)
    except oe.EditError as e:
        print(f"  [중요] {e}")
        return 1
    print("  " + r.summary)
    for dom, kind, name in r.changed[:10]:
        print(f"      {dom}/{kind}/{name}")
    if len(r.changed) > 10:
        print(f"      … 외 {len(r.changed) - 10}건")
    if not apply:
        print("\n  [중요] 아무것도 쓰지 않았다. 반영하려면 `--apply`.")
    return 0


def cmd_protected(argv: list) -> int:
    """protected [도메인] — 무엇이 왜 언제 기준으로 보호돼 있나."""
    from . import edit as oe
    rows = oe.protected_items(_paths(), argv[0] if argv else "")
    print(f"  보호 {len(rows)}건")
    for r in rows[:20]:
        print(f"    {r['domain']}/{r['kind']}/{r['name']}  기준 {r['at'][:8] or '미상'}")
    if rows:
        print(f"    사유: {rows[0]['reason'][:100]}")
    return 0


def cmd_sync(argv: list) -> int:
    """sync [--apply] [도메인] — 경로·선언 메서드를 소스에 맞춘다. [중요] 기본은 계획만."""
    from . import sync as sync_mod
    apply = "--apply" in argv
    rest = [a for a in argv if not a.startswith("-")]
    paths = _paths()
    stats = ([sync_mod.sync_domain(paths, rest[0], apply=apply)] if rest
             else sync_mod.sync_all(paths, apply=apply))
    for st in stats:
        print("  " + st.summary)
        for name, old, new in st.path_fixed[:5]:
            print(f"      경로 {name}: {old or '(없음)'} → {new}")
        for name in st.missing[:5]:
            print(f"      [주의] 그래프에 없다: {name} (남겨 둠)")
    if not apply:
        print("\n  [중요] 아무것도 쓰지 않았다. 반영하려면 `sync --apply`.")
    return 0

_COMMANDS = {"status": cmd_status, "plan": cmd_plan, "verify": cmd_verify,
             "dry": cmd_dry, "refresh": cmd_refresh,
             "new": cmd_new, "unassigned": cmd_unassigned,
             "lock": cmd_lock, "unlock": cmd_unlock, "sync": cmd_sync, "describe": cmd_describe,
             "protect": cmd_protect, "protected": cmd_protected, "drift": cmd_drift, "view": cmd_view}


def main(argv: list) -> int:
    # [중요] 콘솔 UTF-8 강제 (소 3.5.5) — 리눅스에선 no-op, 윈도우 CP949 에선 즉사를 막는다.
    from ..utf8 import enforce as _utf8_enforce
    _utf8_enforce()
    if not argv or argv[0] not in _COMMANDS:
        print(__doc__)
        return 2
    return _COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
