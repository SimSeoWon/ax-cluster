"""`related_classes` 정규화 — 합성 산출물을 **스키마 형태로** 맞춘다 (`#382`).

## 무엇이 문제였나 (실측 2026-09-06)

프론트매터 규약은 **매핑형**이다 (작업장 `CLAUDE.md`):

    related_classes:
      - ClassName: path/to/file.ext

그런데 합성이 **경로만** 내놓는 경우가 있다:

    related_classes:
      - Source/NS/Interaction/NSInteractableComponent.h

파서(`documents.parse_frontmatter:41`)는 `-\\s+(\\w+):\\s+(.+)` 로 **매핑형만** 읽으므로 그 문서의
`related_classes` 는 **키가 아예 안 생긴다.** 조용하다 — 문서는 멀쩡히 있고 필드만 빈다.

    NS            문서 48건   · 매핑형 35 · **경로형 13(27%)** · 없음 0
    ModularStage  문서 1037건 · 매핑형 956 · 경로형 1 · 없음 80

사용자가 컨텍스트 문서의 존재 이유로 꼽은 둘 중 하나가 *"실제 코드 작성 시 사용할 관계가 있는
클래스 파일 주소"* 다 — NS 는 그 27%가 비어 있었다.

## [중요] 파서를 고치지 않는다

`parse_frontmatter` 머리말이 못박아 뒀다 — *"프론트매터를 생성하는 쪽과 짝이 맞춰져 있으므로
여기서 '개선' 하면 오히려 어긋난다"*. 파서가 경로형까지 받으면 **형태가 둘**이 되고 소비자마다
다르게 읽는다. 고칠 자리는 **만드는 쪽**이다.

## 🔴 [중요] 이름을 지어내지 않는다

경로에서 클래스명을 **추측하지 않는다** — `NSInteractableComponent.h` 의 클래스는
`UNSInteractableComponent` 이고 stem 과 다르다(UE 접두). 이름은 **클래스 그래프**(`graph/db`)의
`classes(name, file)` 에서만 가져온다. 그래프가 못 풀면 **그 줄을 그대로 두고 세어 보고한다** —
조용히 버리지도, 지어내지도 않는다.
"""
from __future__ import annotations

import re
# [DOC] 이 모듈은 pathlib.Path 를 쓰지 않는다 — 공개 이름·시그니처는 그대로 둔다.

_FM = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)", re.DOTALL)
_BLOCK = re.compile(r"(^related_classes:[ \t]*\n)((?:[ \t]+-[ \t]+.+\n?)*)", re.MULTILINE)
_MAPPED = re.compile(r"^[ \t]*-[ \t]+([A-Za-z_][\w.]*):[ \t]+\S")


def quote_unknown(text: str) -> tuple[str, int]:
    """related_classes 매핑의 bare `?` 만 YAML 문자열로 바꾼다 (#750).

    그래프 조회·YAML 재직렬화를 하지 않는다. 주석·줄바꿈·필드 순서·본문을 보존한다.
    """
    fm = _FM.match(text or "")
    if not fm:
        return text, 0
    in_related = False
    fixed = 0
    lines = []
    for line in fm.group(2).splitlines(keepends=True):
        if re.match(r"^related_classes:[ \t]*\r?(?:\n|$)", line):
            in_related = True
        elif line.strip() and not line[0].isspace():
            in_related = False
        if in_related:
            original = line
            # 기존 데이터의 path-key·이름 미상 key·standalone 항목도 의미를 바꾸지 않고 인용한다.
            line = re.sub(r"^([ \t]+-[ \t]+)\?([ \t]*:)", r'\1"?"\2', line)
            line = re.sub(
                r"^([ \t]+-[ \t]+.+:[ \t]+)\?([ \t]*(?:#.*)?\r?(?:\n|$))$",
                r'\1"?"\2', line)
            line = re.sub(r"^([ \t]+-[ \t]+)\?([ \t]*(?:#.*)?\r?(?:\n|$))$", r'\1"?"\2', line)
            fixed += line != original
        lines.append(line)
    if not fixed:
        return text, 0
    return fm.group(1) + "".join(lines) + fm.group(3) + text[fm.end():], fixed


def file_to_class(paths) -> dict:
    """`파일경로 → 클래스명`. 그래프가 없으면 빈 dict (그러면 정규화가 아무것도 안 한다)."""
    from ..graph import db as gdb
    if not gdb.exists(paths):
        return {}
    out: dict = {}
    conn = gdb.connect(paths)
    try:
        for row in conn.execute("SELECT name, file FROM classes"):
            f = str(row["file"] or "").replace("\\", "/")
            if f and f not in out:              # 한 파일에 여럿이면 **첫 선언**을 쓴다
                out[f] = str(row["name"])
    finally:
        conn.close()
    return out


def class_to_file(paths) -> dict:
    """`클래스명 → 파일경로` (`#712`). 그래프의 `classes` 그대로 — 파이썬에서 겹친 이름은 이미
    모듈명이 붙어 있어(`master.verdict.Verdict`) 짧은 이름으로는 **안 걸린다**(고르지 않는다)."""
    from ..graph import db as gdb
    if not gdb.exists(paths):
        return {}
    conn = gdb.connect(paths)
    try:
        return {str(r["name"]): str(r["file"] or "").replace("\\", "/")
                for r in conn.execute("SELECT name, file FROM classes") if r["file"]}
    finally:
        conn.close()


_UNKNOWN = re.compile(r'''^([ \t]*-[ \t]+)<?([A-Za-z_][\w.]*)>?:[ \t]+(?:\?|"\?"|'\?')[ \t]*$''')


def normalize(text: str, mapping: dict, names: dict | None = None) -> tuple:
    """`(새 본문, 고친 줄 수, 못 푼 줄들)`. 프론트매터 밖은 건드리지 않는다.

    🔴 `names`(`클래스명 → 경로`, `#712` · 사용자 결정 2026-10-03 「전체 적용」): 모델이 경로를 몰라
    `이름: ?` 로 쓴 줄을 **그래프에 그 이름이 정확히 있을 때만** 채운다. 이름을 지어내지 않는 원칙은
    그대로다 — 없는 이름·겹친 짧은 이름은 `?` 로 남는다.
    """
    fm = _FM.match(text or "")
    if not fm:
        return text, 0, []
    head, body, tail = fm.group(1), fm.group(2), fm.group(3)
    fixed, unresolved = 0, []

    def one_block(m):
        nonlocal fixed
        lines_out = []
        for ln in m.group(2).splitlines():
            qm = _UNKNOWN.match(ln) if names else None
            if qm and qm.group(2) in names:
                lines_out.append(f"{qm.group(1)}{qm.group(2)}: {names[qm.group(2)]}")
                fixed += 1
                continue
            if not ln.strip() or _MAPPED.match(ln):
                lines_out.append(ln)
                continue
            # ⑵ `<ClassName>: path` — 이름은 이미 있고 **꺾쇠 때문에** 파서가 버린다.
            #    형식만 고치는 것이라 지어내는 것이 아니다 (실측: 모델이 이 변형을 낸다).
            am = re.match(r"^([ \t]*-[ \t]+)<([A-Za-z_]\w*)>:[ \t]+(\S+)[ \t]*$", ln)
            if am:
                if am.group(3) in ("?", '"?"', "'?'", "-"):  # 경로가 없다 — 내용 문제다
                    unresolved.append(f"<{am.group(2)}>: {am.group(3)}")
                    lines_out.append(ln)
                    continue
                lines_out.append(f"{am.group(1)}{am.group(2)}: {am.group(3)}")
                fixed += 1
                continue
            im = re.match(r"^([ \t]*-[ \t]+)(\S+)[ \t]*$", ln)
            if not im:
                unresolved.append(ln.strip())        # `경로: 설명문` 등 — 세어서 보고한다
                lines_out.append(ln)
                continue
            indent, path = im.group(1), im.group(2).replace("\\", "/")
            name = mapping.get(path)
            if not name:                        # 그래프가 못 푼다 — 그대로 두고 센다
                unresolved.append(path)
                lines_out.append(ln)
                continue
            lines_out.append(f"{indent}{name}: {path}")
            fixed += 1
        return m.group(1) + "\n".join(lines_out) + ("\n" if m.group(2).endswith("\n") else "")

    new_body = _BLOCK.sub(one_block, body)
    out = head + new_body + tail + text[fm.end():] if fixed else text
    out, quoted = quote_unknown(out)
    return out, fixed + quoted, unresolved


def normalize_doc(text: str, paths) -> tuple:
    """편의 — 매핑을 그래프에서 만들어 `normalize` 를 부른다."""
    return normalize(text, file_to_class(paths), class_to_file(paths))


# ── 기존 문서 보수 (`#382` 완료 조건 3) ─────────────────────────────────
def repair(paths, *, confirm: bool = False, quote_unknown_only: bool = False) -> dict:
    """이미 쓰인 문서들을 훑어 경로형을 매핑형으로 고친다.

    [중요] **기본은 계획이다** — 이 저장소 관례대로 `--confirm` 이 트리거다.
    [주의] 재합성으로는 안 낫는다 — `#375` 가 지적한 대로 문서가 **있으면** 커서가 전진해
    다시 만들 계기가 없다. 그래서 보수 경로가 따로 필요하다.
    """
    from ..context_search import documents
    mapping, names = ({}, {}) if quote_unknown_only else (file_to_class(paths), class_to_file(paths))
    plan, unresolved_all = [], []
    scanned = 0
    for md in sorted(paths.context.rglob("*.md")):
        rel = md.relative_to(paths.context).as_posix()
        if not quote_unknown_only and documents.is_excluded(rel):
            continue
        try:
            with md.open(encoding="utf-8", errors="strict" if quote_unknown_only else "replace", newline="") as stream:
                text = stream.read()
        except OSError:
            if quote_unknown_only:
                raise                     # 전수 인용 교정에서 읽지 못한 파일을 숨기지 않는다.
            continue
        scanned += 1
        if quote_unknown_only:
            new, fixed = quote_unknown(text)
            unresolved = []
        else:
            new, fixed, unresolved = normalize(text, mapping, names)
        unresolved_all += [f"{rel}: {u}" for u in unresolved]
        if fixed:
            plan.append((rel, fixed))
            if confirm:
                with md.open("w", encoding="utf-8", newline="") as stream:
                    stream.write(new)
    return {"files": len(plan), "fixed": sum(n for _r, n in plan),
            "unresolved": unresolved_all, "detail": plan[:20],
            "applied": bool(confirm),
            "quote_unknown_only": bool(quote_unknown_only),
            "scanned": scanned,
            "bare_remaining": (0 if confirm else sum(n for _r, n in plan)) if quote_unknown_only else None,
            "note": "" if confirm else "계획만 — `--confirm` 이 쓴다"}


def main(argv=None) -> int:
    import sys
    from ..context_search.paths import resolve
    args = list(argv if argv is not None else sys.argv[1:])
    confirm = "--confirm" in args
    quote_only = "--quote-unknown-only" in args
    names = [a for a in args if not a.startswith("-")]
    if not names:
        print("사용: python -m master.context_synth.related <프로젝트> [--quote-unknown-only] [--confirm]")
        return 2
    got = repair(resolve(names[0]), confirm=confirm, quote_unknown_only=quote_only)
    print(f"{names[0]}: 파일 {got['files']}개 · 줄 {got['fixed']}개 "
          f"{'수정함' if got['applied'] else '(계획만 — --confirm 이 쓴다)'}")
    if quote_only:
        print(f"  전수 조회 {got['scanned']}파일 · bare ? 잔여 {got['bare_remaining']}줄")
    for rel, n in got["detail"]:
        print(f"   {rel} — {n}줄")
    if got["unresolved"]:
        print(f"[주의] 그래프가 못 푼 경로 {len(got['unresolved'])}건 — 이름을 지어내지 않는다:")
        for u in got["unresolved"][:10]:
            print("   ", u)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
