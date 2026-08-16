"""컨텍스트 MD 진단 — 원전 `mcp/context_search/context_audit.py` 이식
(소 3.4.1 · `#160`, 2026-08-14).

트윈 문서 전체를 읽어 **8분류**한다. [중요] **읽기 전용이 기본이고, LLM 0 이다.**

    valid           frontmatter + 본문 ≥ 50자 + `## 요약`
    pence_wrapped   LLM 응답이 ```markdown … ``` 펜스에 감싸진 채 저장됨 (원전 σ.7)
    natural_prefix  frontmatter 앞에 자연어 도입부가 붙음 (원전 σ.7)
    shell_only      frontmatter 껍데기만 — 재생성 필요
    empty_summary   본문은 있는데 `## 요약` 이 없음
    no_frontmatter  `---` 로 시작하지 않음 (파싱 실패)
    dir_named       디렉토리 옆에 같은 이름의 MD — 구 dir-단위 흔적
    orphan_stem     [중요] 대응 소스 파일이 없다 (좀비 MD)

## [중요] 왜 이것이 우리에게 특히 맞나 — 우리 코퍼스가 원전에서 왔다

`config.yaml` 의 `index.source` 가 **`infra_state_20260808.zip`** 이다. 지금 트윈 1,056건은
원전 환경에서 **받아온 스냅샷**이고, 그러므로 **원전이 겪은 손상 유형을 그대로 안고 있을 수
있다.** 이 감사는 정확히 그 코퍼스를 위해 쓰인 도구다.

[주의] 이식 전 실측(2026-08-14): frontmatter 없음 1건 · 본문 50자 미만 147건 · `## 요약` 없음
163건 · **펜스 감싸짐 0건**. 표본이 전부 `_archive/project_alpha_md/` 였다 — [중요] 검색 로그에서
두 번 올라온 그 아카이브다(소 3.4.5·3.4.2 관측). 세 신호가 같은 곳을 가리킨다.

## [중요] 분류 순서가 판정을 바꾼다 (원전 그대로)

    ① dir_named    구조 흔적 — **내용 분류보다 먼저**
    ② orphan_stem  대응 소스 부재 — 내용이 아무리 멀쩡해도 좀비다
    ③ 내용 분류

순서를 바꾸면 아카이브된 문서가 `shell_only`(재생성 대상)로 잡힌다 — **재생성할 소스가 없는데
재생성 대상이 된다.** 원전이 이 순서를 고른 이유가 그것이다.

## 원전과 다르게 둔 것 둘

**① 복구는 「계획」이 기본이다.** 원전 `repair_context_md` 는 파일을 고치고 옮긴다. 우리는
`work/cleanup.py` 규약(*"기본은 세기만 한다"*)을 따라 **계획을 내고, 적용은 호출자가 명시**한다.
[중요] 그리고 **아카이브 이동(`dir_named`·`orphan_stem`)은 이식 범위 밖으로 뒀다** — 트윈 문서를
옮기는 것은 사람의 판단이고, 지금 `_archive` 를 어떻게 할지가 **열린 질문**이다(검색 결과에
섞이는 것이 관측됐다). 근거 없이 옮기지 않는다.

**② 자동 복구는 펜스·자연어 도입부만.** 원전과 같다(LLM 0). [주의] 실측상 지금 **대상이 0건**이지만
이식한다 — 없는 것을 못 고치는 것과 **고칠 수 없는 것**은 다르고, 이 손상은 LLM 응답을 저장하는
경로가 살아 있는 동안 언제든 다시 난다.
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC_EXTENSIONS = (".h", ".hpp", ".inl", ".cpp", ".cs", ".py")
_DOMAIN_DIR_NAME = "_domains"
_BODY_MIN_CHARS = 50                  # 원전 값 그대로 (domain.DOC_MIN_BODY_CHARS 와 같은 정신)

CATEGORY_ORDER = (
    "valid", "pence_wrapped", "natural_prefix", "shell_only",
    "empty_summary", "no_frontmatter", "dir_named", "orphan_stem",
)

# [중요] LLM 0 으로 고칠 수 있는 것 / 재생성이 필요한 것 / 사람이 판단할 것
AUTO_FIXABLE = ("pence_wrapped", "natural_prefix")
NEEDS_REGEN = ("shell_only", "empty_summary", "no_frontmatter")
HUMAN_CALL = ("dir_named", "orphan_stem")


def strip_code_block_wrapper(md: str) -> str:
    """```markdown … ``` 펜스 + frontmatter 앞 자연어 도입부를 걷어낸다. **원전 그대로.**

    [주의] 원전은 이 함수를 `watcher/context.py` 와 MCP 양쪽에 **복제**해 두고 *"drift 차단을 위해
    단위 테스트는 두 위치 모두에서 동일 동작 검증"* 이라 적어 뒀다. 우리는 한 벌만 둔다 —
    복제가 없으면 drift 도 없다.
    """
    s = (md or "").strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", s, re.DOTALL | re.IGNORECASE)
    if m:
        s = m.group(1).strip()
    if not s.startswith("---"):
        fm = re.search(r"^---\s*$", s, re.MULTILINE)
        if fm:
            s = s[fm.start():]
    return s


def classify(content: str) -> str:
    """MD 한 건의 **내용** 분류. `dir_named`·`orphan_stem` 은 밖에서 판정한다."""
    stripped = (content or "").lstrip()

    if re.match(r"^```(?:markdown|md)?", stripped, re.IGNORECASE):
        return "pence_wrapped"

    if not stripped.startswith("---"):
        if stripped.strip() == "":
            return "no_frontmatter"
        # frontmatter 앞에 자연어가 붙었고 어딘가 `---` 가 있으면 도입부 손상이다
        if re.search(r"^---\s*$", content, re.MULTILINE):
            return "natural_prefix"
        return "no_frontmatter"

    fm_end = re.search(r"\n---\s*\n", content)
    if not fm_end:
        return "no_frontmatter"

    body = content[fm_end.end():]
    # [주의] `## 코멘트` 이후는 **사람이 쓴 것**이라 시스템 평가 대상이 아니다 (원전 판단)
    body_for_eval = re.sub(r"## 코멘트\s*\n.*", "", body, flags=re.DOTALL).strip()

    if len(body_for_eval) < _BODY_MIN_CHARS:
        return "shell_only"
    if not re.search(r"^##\s*요약", body_for_eval, re.MULTILINE):
        return "empty_summary"
    return "valid"


def is_dir_named(md_path: Path) -> bool:
    """디렉토리 옆에 같은 이름의 MD 인가 — 구 dir-단위 컨텍스트의 흔적."""
    return (md_path.parent / md_path.stem).is_dir()


def has_source(md_path: Path, context_dir: Path, repo_dir: Path) -> bool:
    """대응 소스가 저장소에 있나 — `orphan_stem` 판정.

    `context/<rel>/<stem>.md` ↔ `repo/<rel>/<stem>.{h,cpp,cs,…}` 로 맞춰 본다.
    """
    try:
        rel = md_path.relative_to(context_dir)
    except ValueError:
        return False
    src_dir = Path(repo_dir) / rel.parent
    if not src_dir.is_dir():
        return False
    return any((src_dir / f"{md_path.stem}{ext}").exists() for ext in _SRC_EXTENSIONS)


def audit(context_dir, repo_dir) -> dict:
    """전체 진단 — [중요] **읽기 전용.** `{total, categories, by_path, unreadable}`.

    [중요] 순서: `dir_named` → `orphan_stem` → 내용 분류 (머리말 참조 — 바꾸면 판정이 바뀐다).
    """
    context_dir = Path(context_dir)
    repo_dir = Path(repo_dir)
    categories: dict = {c: [] for c in CATEGORY_ORDER}
    unreadable: list = []

    if not context_dir.is_dir():
        return {"total": 0, "categories": categories, "by_path": {},
                "unreadable": [], "error": f"컨텍스트 디렉토리가 없다: {context_dir}"}

    by_path: dict = {}
    for md_path in sorted(context_dir.rglob("*.md")):
        rel = md_path.relative_to(context_dir)
        if rel.parts and rel.parts[0] == _DOMAIN_DIR_NAME:
            continue                                  # 도메인 패키지는 별도 자리다
        rel_str = str(rel).replace("\\", "/")

        if is_dir_named(md_path):
            categories["dir_named"].append(rel_str)
            by_path[rel_str] = "dir_named"
            continue
        if not has_source(md_path, context_dir, repo_dir):
            categories["orphan_stem"].append(rel_str)
            by_path[rel_str] = "orphan_stem"
            continue
        try:
            content = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            # [중요] 조용히 건너뛰지 않는다 — 원전은 로그 한 줄만 남겼다. 우리는 세어서 돌려준다.
            unreadable.append(f"{rel_str}: {e}")
            continue

        cat = classify(content)
        categories[cat].append(rel_str)
        by_path[rel_str] = cat

    return {"total": sum(len(v) for v in categories.values()),
            "categories": categories, "by_path": by_path, "unreadable": unreadable}


def format_report(result: dict, sample_per_cat: int = 5) -> str:
    """사람이 읽는 리포트. [중요] **무엇을 어떻게 고치는지까지** 적는다 (원전과 같은 구성)."""
    total = result.get("total", 0)
    cats = result.get("categories", {})
    if result.get("error"):
        return f"[중요] 진단 불가 — {result['error']}"

    out = ["# 컨텍스트 MD 진단 리포트", "", f"- 총 파일: **{total}건**", ""]
    if result.get("unreadable"):
        out += [f"- [중요] 읽지 못한 파일 **{len(result['unreadable'])}건** "
                "(진단에서 빠졌다 — 사람이 봐야 한다)", ""]

    out += ["| 분류 | 건수 | 비율 | |", "|---|---|---|---|"]
    for c in CATEGORY_ORDER:
        n = len(cats.get(c, []))
        pct = (n / total * 100) if total else 0.0
        mark = "[완료]" if c == "valid" else ("" if c in AUTO_FIXABLE else "[주의]")
        out.append(f"| `{c}` | {n} | {pct:.1f}% | {mark} |")
    out.append("")

    auto_n = sum(len(cats.get(c, [])) for c in AUTO_FIXABLE)
    out += [f"**자동 복구 가능 (LLM 0)**: {auto_n}건 — 펜스·자연어 도입부 제거", ""]
    regen_n = sum(len(cats.get(c, [])) for c in NEEDS_REGEN)
    if regen_n:
        out += [f"**LLM 재생성 필요**: {regen_n}건 — 소스가 다시 커밋되면 자연 회복한다", ""]
    human_n = sum(len(cats.get(c, [])) for c in HUMAN_CALL)
    if human_n:
        out += [f"[중요] **사람의 판단**: {human_n}건 — `dir_named`·`orphan_stem` 은 **옮기지 않는다.** "
                "트윈 문서를 이동하는 것은 사람이 정한다", ""]

    for c in CATEGORY_ORDER:
        items = cats.get(c, [])
        if not items or c == "valid":
            continue
        out += [f"### `{c}` 샘플 ({min(sample_per_cat, len(items))}/{len(items)})", ""]
        out += [f"- `{p}`" for p in items[:sample_per_cat]]
        if len(items) > sample_per_cat:
            out.append(f"- … 외 {len(items) - sample_per_cat}건")
        out.append("")
    return "\n".join(out)


# ── 자동 복구 — [중요] **계획이 기본이다** (`work/cleanup.py` 와 같은 규약) ──────────

def plan_repair(context_dir, result: dict) -> dict:
    """펜스·자연어 도입부를 걷어낼 수 있는 것만 고른다. [중요] **아무것도 쓰지 않는다.**

    걷어낸 뒤 **다시 분류해서 나아지는지 확인**한 것만 후보로 올린다 — 원전
    `_strip_and_validate` 와 같은 판단이고, 고쳐서 더 나빠지는 것을 막는다.
    """
    context_dir = Path(context_dir)
    cats = result.get("categories", {})
    fixable, refused = [], []
    for c in AUTO_FIXABLE:
        for rel in cats.get(c, []):
            p = context_dir / rel
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                refused.append((rel, f"읽기 실패: {e}"))
                continue
            new = strip_code_block_wrapper(content)
            after = classify(new)
            if after in AUTO_FIXABLE or after == "no_frontmatter":
                refused.append((rel, f"걷어내도 {after} 다 — 고치지 않는다"))
                continue
            if new == content:
                refused.append((rel, "바뀌는 것이 없다"))
                continue
            fixable.append((rel, c, after))
    return {"fixable": fixable, "refused": refused}


def apply_repair(context_dir, plan: dict) -> dict:
    """계획의 후보만 고친다. [중요] **계획이 고른 것 밖은 건드리지 않는다.**"""
    context_dir = Path(context_dir)
    fixed, failed = [], []
    for rel, before, after in plan.get("fixable", []):
        p = context_dir / rel
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            p.write_text(strip_code_block_wrapper(content), encoding="utf-8")
        except OSError as e:
            failed.append((rel, str(e)))
            continue
        fixed.append((rel, before, after))
    return {"fixed": fixed, "failed": failed}


def run_for_project(paths) -> dict:
    """진단 + 리포트 파일 ([중요] **고치지 않는다**). 출력 `<프로젝트 데이터>/analysis/` (§5.5).

    [중요] **이것은 유휴 배치가 아니다 — 요청 시 도는 것이다.** 원전 `watch.py` 는 `context_audit`
    을 유휴 사이클에서 부르지 않는다(`import` 목록에 없다). 통로는 셋이었다: MCP 도구
    `audit_context_md` · HTTP 엔드포인트 · 스킬 `/audit-context`. 배치에 얹으면 **원전에 없는
    것을 내가 만드는 것**이므로 하지 않는다.

    [주의] **기록만 해 둔 개선 후보**: 주기적으로 돌려 트윈 건강도를 추적하기(방금 만든
    `master/batch/` 자리에 한 줄이면 된다). [중요] 원전에 없으므로 지금 넣지 않는다.
    """
    result = audit(paths.context, paths.repo)
    if result.get("error"):
        return {"ok": False, "entries": 0, "files": [], "reason": result["error"]}
    out_dir = Path(paths.root) / "analysis"
    p = out_dir / "context_audit_report.md"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        p.write_text(format_report(result) + "\n", encoding="utf-8")
    except OSError as e:
        return {"ok": False, "entries": result["total"], "files": [],
                "reason": f"리포트 쓰기 실패: {e}"}
    return {"ok": True, "entries": result["total"], "files": [str(p)],
            "reason": "", "categories": {k: len(v) for k, v in result["categories"].items()}}


# ── CLI — [중요] `report` 가 기본이고 `repair` 는 명시해야 한다 ──────────────────────

def main(argv: list | None = None) -> int:
    import sys
    from .paths import resolve

    args = list(argv if argv is not None else sys.argv[1:])
    cmd = args[0] if args else "report"
    if cmd in ("-h", "--help", "help"):
        print("사용법: python -m master.context_search.context_audit report|plan|repair [프로젝트]")
        print("  report  진단 + 리포트 파일 (기본, [중요] 고치지 않는다)")
        print("  plan    [중요] LLM 0 으로 고칠 수 있는 것만 보여준다 (아무것도 안 쓴다)")
        print("  repair  그 계획을 적용한다 — 펜스·자연어 도입부만.")
        print("          [중요] dir_named·orphan_stem 은 옮기지 않는다 (사람의 판단)")
        return 0

    paths = resolve(args[1] if len(args) > 1 else "")
    result = audit(paths.context, paths.repo)
    if result.get("error"):
        print(f"[중요] {result['error']}")
        return 1

    if cmd == "report":
        r = run_for_project(paths)
        print(format_report(result))
        print(f"\n→ {r['files'][0] if r.get('files') else '(파일 없음)'}")
        return 0 if r.get("ok") else 1

    plan = plan_repair(paths.context, result)
    print(f"고칠 수 있는 것 {len(plan['fixable'])}건 · 거부 {len(plan['refused'])}건")
    for rel, before, after in plan["fixable"][:20]:
        print(f"   {rel}  ({before} → {after})")
    for rel, why in plan["refused"][:20]:
        print(f"  · {rel} — {why}")
    if cmd == "repair":
        if not plan["fixable"]:
            print("고칠 것이 없다 — 아무것도 하지 않았다.")
            return 0
        applied = apply_repair(paths.context, plan)
        print(f"고쳤다 {len(applied['fixed'])}건 · 실패 {len(applied['failed'])}건")
        return 1 if applied["failed"] else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ── 아카이브 이동 (`#160` 2단계) — [중요] **계획이 기본, 목적지는 `context/` 밖** ────
#
# 원전 `repair_context_md` 의 `archive_dir_named`·`archive_orphan` 이식.
#
# [중요] **목적지가 `context/` 밖인 것이 이 기능의 핵심이다.** 원전은
# `context_dir.parent / '_archive' / <종류> / <날짜>` 로 옮긴다 — 즉 **색인 범위를 벗어난다.**
#
# [주의] **우리 코퍼스는 그 반대로 놓여 있다** (실측 2026-08-14): `context/_archive/project_alpha_md/`
# 가 **`context/` 안**에 있어서 색인·검색에 그대로 잡힌다. 이 세션에 같은 신호가 세 번 나왔다:
#
#     검색 로그 1위        _archive/project_alpha_md/…/AlphaUIHUD_Mission.md  (소 3.4.5)
#     도메인 빈도          _archive 1 / 8 (소 3.4.2)
#     orphan_stem 112건    그중 101건이 _archive/ (소 3.4.1)
#
# [중요] **세 신호의 원인이 하나다 — 아카이브가 색인 안에 있다.** 원전 규약대로 밖으로 옮기면
# 셋이 함께 사라진다. 그것이 이 이식이 값을 내는 자리다.
#
# [중요] **그러나 파일을 움직이는 것은 사람의 승인 사항이다** — `plan_archive` 가 기본이고
# `apply_archive` 는 호출자가 명시해야 한다(`work/cleanup.py` 와 같은 규약).

ARCHIVE_SUBDIR = {"dir_named": "dir_named_md", "orphan_stem": "orphan_md"}


def archive_root(paths, kind: str, day: str) -> Path:
    """[중요] `context/` **밖**이다 — 안에 두면 색인 범위를 벗어나지 못한다 (실측 근거는 위 주석)."""
    return Path(paths.root) / "_archive" / ARCHIVE_SUBDIR[kind] / day


def plan_archive(paths, result: dict, *, kinds=("orphan_stem",), day: str = "") -> dict:
    """무엇을 어디로 옮길지 **계획만** 낸다. [중요] 아무것도 움직이지 않는다.

    `kinds` 는 `dir_named` · `orphan_stem` 중에서 **호출자가 고른다** — 기본은 orphan 뿐이고,
    `dir_named` 는 구조 흔적이라 따로 판단할 자리다.
    """
    from datetime import date
    day = day or date.today().isoformat()
    context_dir = Path(paths.context)
    moves, refused = [], []
    for kind in kinds:
        if kind not in ARCHIVE_SUBDIR:
            refused.append((kind, "아카이브 대상 종류가 아니다"))
            continue
        dest_root = archive_root(paths, kind, day)
        for rel in result.get("categories", {}).get(kind, []):
            src = context_dir / rel
            # 원전과 같은 평탄화 — 경로 구분자를 `__` 로 접어 이름 충돌을 막는다
            dst = dest_root / rel.replace("/", "__")
            if not src.exists():
                refused.append((rel, "원본이 없다 (이미 옮겨졌나)"))
                continue
            if dst.exists():
                # [중요] 덮어쓰지 않는다 — 아카이브는 증거이고, 덮으면 증거가 사라진다
                refused.append((rel, f"목적지가 이미 있다: {dst.name}"))
                continue
            moves.append((rel, str(dst), kind))
    return {"moves": moves, "refused": refused, "day": day, "kinds": list(kinds)}


def apply_archive(paths, plan: dict) -> dict:
    """계획의 이동만 수행한다. [중요] **계획이 고른 것 밖은 건드리지 않는다.**

    [주의] 이 함수는 **트윈 문서를 움직인다.** 호출 전에 사람의 승인을 받는 것이 규약이다
    (`CLAUDE.md` — 자동 로드 문서와 게임 소스 밖이지만, 트윈은 M2 의 산출물이다).
    """
    import shutil
    context_dir = Path(paths.context)
    moved, failed = [], []
    for rel, dst_str, kind in plan.get("moves", []):
        src = context_dir / rel
        dst = Path(dst_str)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except OSError as e:
            failed.append((rel, str(e)))
            continue
        moved.append((rel, dst_str, kind))
    return {"moved": moved, "failed": failed}


def format_archive_plan(plan: dict, sample: int = 10) -> str:
    moves = plan.get("moves", [])
    out = [f"# 아카이브 계획 ({', '.join(plan.get('kinds', []))} · {plan.get('day','')})", "",
           f"- 옮길 것: **{len(moves)}건** · 거부: {len(plan.get('refused', []))}건",
           "- [중요] 목적지는 `context/` **밖**이다 — 색인 범위를 벗어난다", ""]
    for rel, dst, kind in moves[:sample]:
        out.append(f"  - `{rel}` → `{Path(dst).parent.name}/{Path(dst).name}`  [{kind}]")
    if len(moves) > sample:
        out.append(f"  - … 외 {len(moves) - sample}건")
    if plan.get("refused"):
        out += ["", "거부:"] + [f"  - `{r}` — {why}" for r, why in plan["refused"][:sample]]
    return "\n".join(out)


# ── σ.9.0 빈 컨텍스트 4분기 (`#160` 3단계) ──────────────────────────────────────
#
# 원전 `post_unwrap_diagnosis` 이식. `shell_only` + `empty_summary` 를 **소스 활동 기준**으로
# 다시 가른다. [중요] **「빈 문서 N건」을 「고쳐야 할 N건」으로 읽으면 틀린다** — 소스가 오래 안
# 바뀐 문서가 비어 있는 것은 **트리거 정책의 정상 산물**이고, 소스가 최근 바뀌었는데 비어
# 있는 것이 **진짜 결함**이다(원전이 Level 5 라 부른 것).
#
#     recent_but_empty  [중요] 소스가 최근 변경됐는데 문서가 비었다 — **진짜 결함**
#     old_inactive      소스가 오래 조용하다 — 정상 산물
#     orphan_md         frontmatter 에 소스 링크는 있는데 그 파일이 없다 — 좀비
#     no_source_link    링크 자체가 없다 — 무엇을 근거로 만든 문서인지 모른다
#
# [주의] 우리에게 `shell_only` 가 **39건**이다(실측). 이 4분기가 그 39건 중 **몇 건이 실제
# 문제인지**를 가른다 — 그것이 이 이식의 값이다.
#
# ## [중요] 원전의 신호원(`mtime`)은 우리 환경에서 의미가 없다 — 실측으로 잡았다
#
# 원전은 소스 파일의 **`mtime`** 으로 「최근 변경」을 판정한다. 원전 환경은 팀원 PC 의 **오래
# 살아 있는 작업 복사본**이라 mtime 이 실제 편집을 따라간다. [중요] **우리는 갓 클론한 미러다.**
#
#     실측 2026-08-15: 소스 400개의 mtime 이 **전부 2026-08-08 한 날짜**(전개 시각)
#     같은 파일의 git 마지막 변경: 2025-10-12 · 2026-05-16
#     → 첫 판은 39건 **전부** `recent_but_empty` 로 나왔다. 결함이 아니라 **계측 오류**다
#
# 그래서 **기제는 옮기고 신호원만 우리 것으로 바꿨다** — `git log -1 --format=%ct <파일>`.
# [주의] 이것은 개선이 아니라 **이식이 성립하기 위한 조건**이다(마일스톤 4: *"그 수정이 겨눈
# 조건이 우리에게 없으면 옮기면 카고 컬트이거나 퇴행"*). mtime 경로는 폴백으로 남긴다 —
# git 을 못 읽는 트리(테스트 픽스처)에서도 분류가 돌아야 한다.

POST_UNWRAP_ORDER = ("recent_but_empty", "old_inactive", "orphan_md", "no_source_link")

BRANCH_EXPLAIN = {
    "D-a": "잔존 빈 문서가 전부 트리거 정책의 정상 산물이다 — 추가 조치 불필요",
    "D-b": "[중요] 소스가 최근 바뀌었는데 빈 문서가 있다 (Level 5) — 원인 추적 후 재생성",
    "D-c": "[중요] 좀비 문서가 있다 — 소스 링크가 가리키는 파일이 없다",
    "D-b+D-c": "[중요] 둘 다 있다 — Level 5 와 좀비를 함께 다뤄야 한다",
}


def extract_source_candidates(content: str, md_path: Path, context_dir: Path) -> list:
    """`related_classes` + `source_documents` + 위치 기반 stem 폴백. **원전 그대로.**

    [주의] 폴백을 **뒤에** 두는 것이 중요하다 — frontmatter 가 준 링크가 먼저다. 순서를 바꾸면
    문서가 스스로 밝힌 근거보다 우리 추측이 앞선다.
    """
    candidates: list = []
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        for _cls, path in re.findall(r"-\s+(\w+):\s+(.+)", fm):
            p = path.strip()
            if p and p not in candidates:
                candidates.append(p)
        sd = re.search(r"source_documents:\s*\n((?:\s+-\s+.+\n?)*)", fm)
        if sd:
            for p in re.findall(r"-\s+(\S+)", sd.group(1)):
                if p and p not in candidates:
                    candidates.append(p)
    try:
        rel = md_path.relative_to(context_dir)
    except ValueError:
        return candidates
    parent = str(rel.parent).replace("\\", "/")
    for ext in _SRC_EXTENSIONS:
        guess = f"{parent}/{md_path.stem}{ext}" if parent and parent != "." else f"{md_path.stem}{ext}"
        if guess not in candidates:
            candidates.append(guess)
    return candidates


def source_changed_at(repo_dir, rel: str):
    """소스가 **실제로** 마지막에 바뀐 시각(epoch). [중요] `mtime` 이 아니라 **git 커밋 시각**이다.

    [주의] 왜 mtime 이 아닌가 — 위 머리말의 실측: 우리 미러는 파일 400개의 mtime 이 전부 전개
    시각 한 날짜다. mtime 으로 재면 **모든 파일이 「최근 변경」** 이 되어 판정이 무의미해진다.

    git 을 못 읽으면 `mtime` 으로 폴백한다(테스트 픽스처처럼 git 이 없는 트리도 있다).
    폴백했다는 사실을 숨기지 않으려고 값만 돌려주고, 판정 쪽에서 균일함이 보이게 둔다.
    """
    import subprocess
    p = Path(repo_dir) / rel
    try:
        r = subprocess.run(["git", "-C", str(repo_dir), "log", "-1", "--format=%ct", "--", rel],
                           capture_output=True, text=True, timeout=15)
        out = (r.stdout or "").strip()
        if r.returncode == 0 and out.isdigit():
            return float(out)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return p.stat().st_mtime
    except OSError:
        return None


def _classify_post_unwrap(md_path: Path, context_dir: Path, repo_dir: Path,
                          recent_threshold_ts: float, now_ts: float) -> tuple:
    """빈 문서 하나를 소스 활동 기준으로 분류. `(분류, 정보)`."""
    try:
        content = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return "no_source_link", {"error": f"읽기 실패: {e}"}

    candidates = extract_source_candidates(content, md_path, context_dir)
    if not candidates:
        return "no_source_link", {}

    existing = []
    for cand in candidates:
        src = Path(repo_dir) / cand
        if src.is_file():
            ts = source_changed_at(repo_dir, cand)
            if ts is not None:
                existing.append((cand, ts))

    if not existing:
        # [중요] **폴백만 있었는지**를 가른다 — frontmatter 가 링크를 줬는데 그 파일이 없으면
        #    좀비(orphan_md)고, 링크 자체가 없었으면 근거 미상(no_source_link)이다.
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        fm_has_link = False
        if fm_match:
            fm = fm_match.group(1)
            fm_has_link = bool(re.search(r"-\s+\w+:\s+\S", fm)
                               or re.search(r"source_documents:", fm))
        if not fm_has_link:
            return "no_source_link", {"checked": len(candidates)}
        return "orphan_md", {"checked": len(candidates), "candidates_sample": candidates[:3]}

    existing.sort(key=lambda x: x[1], reverse=True)
    newest_src, newest_mtime = existing[0]
    info = {"source_path": newest_src, "source_mtime": newest_mtime,
            "age_days": round((now_ts - newest_mtime) / 86400.0, 1)}
    if newest_mtime >= recent_threshold_ts:
        return "recent_but_empty", info
    return "old_inactive", info


def post_unwrap_diagnosis(context_dir, repo_dir, *, recent_days: int = 30,
                          audit_result: dict | None = None, now=None) -> dict:
    """빈 문서를 4분기한다. `{total_empty, recent_days, categories, branch_decision}`.

    [중요] **`now` 를 주입할 수 있다** — 원전은 `datetime.now()` 를 직접 부른다. 소스 mtime 과
    비교하는 판정이라 시간을 고정하지 않으면 테스트가 날짜에 따라 흔들린다(`gates.py` 와
    같은 판단이고, 원전이 `attempt_branch(ts=…)` 를 인자로 둔 것과 같은 이유).
    """
    from datetime import datetime as _dt, timedelta as _td

    context_dir = Path(context_dir)
    repo_dir = Path(repo_dir)
    if audit_result is None:
        audit_result = audit(context_dir, repo_dir)

    cats = audit_result.get("categories", {})
    targets = list(cats.get("shell_only", [])) + list(cats.get("empty_summary", []))

    now = now or _dt.now()
    now_ts = now.timestamp()
    threshold = (now - _td(days=recent_days)).timestamp()

    out = {c: [] for c in POST_UNWRAP_ORDER}
    for rel in targets:
        cat, info = _classify_post_unwrap(context_dir / rel, context_dir, repo_dir,
                                         threshold, now_ts)
        out[cat].append({"md": rel, "info": info})

    has_recent = bool(out["recent_but_empty"])
    has_orphan = bool(out["orphan_md"])
    decision = ("D-b+D-c" if has_recent and has_orphan else
                "D-b" if has_recent else "D-c" if has_orphan else "D-a")
    return {"total_empty": len(targets), "recent_days": recent_days,
            "categories": out, "branch_decision": decision}


def format_post_unwrap_report(result: dict, sample_per_cat: int = 5) -> str:
    cats = result["categories"]
    total = result["total_empty"]
    decision = result["branch_decision"]
    out = ["# 빈 컨텍스트 4분기 진단 (σ.9.0)", "",
           f"- 대상(빈 문서): **{total}건** · 최근 기준 {result['recent_days']}일", "",
           f"**분기 판정: `{decision}`** — {BRANCH_EXPLAIN.get(decision, '?')}", "",
           "| 분류 | 건수 | |", "|---|---|---|"]
    for c in POST_UNWRAP_ORDER:
        n = len(cats.get(c, []))
        mark = "[중요]" if c in ("recent_but_empty", "orphan_md") and n else ("·" if not n else "[주의]")
        out.append(f"| `{c}` | {n} | {mark} |")
    out.append("")
    for c in POST_UNWRAP_ORDER:
        items = cats.get(c, [])
        if not items:
            continue
        out += [f"### `{c}` ({min(sample_per_cat, len(items))}/{len(items)})", ""]
        for it in items[:sample_per_cat]:
            age = it["info"].get("age_days")
            extra = f" — 소스 {age}일 전 변경" if age is not None else ""
            out.append(f"- `{it['md']}`{extra}")
        if len(items) > sample_per_cat:
            out.append(f"- … 외 {len(items) - sample_per_cat}건")
        out.append("")
    return "\n".join(out)
