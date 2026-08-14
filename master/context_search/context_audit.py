"""컨텍스트 MD 진단 — 원전 `mcp/context_search/context_audit.py` 이식
(소 3.4.1 · `#160`, 2026-08-14).

트윈 문서 전체를 읽어 **8분류**한다. 🔴 **읽기 전용이 기본이고, LLM 0 이다.**

    valid           frontmatter + 본문 ≥ 50자 + `## 요약`
    pence_wrapped   LLM 응답이 ```markdown … ``` 펜스에 감싸진 채 저장됨 (원전 σ.7)
    natural_prefix  frontmatter 앞에 자연어 도입부가 붙음 (원전 σ.7)
    shell_only      frontmatter 껍데기만 — 재생성 필요
    empty_summary   본문은 있는데 `## 요약` 이 없음
    no_frontmatter  `---` 로 시작하지 않음 (파싱 실패)
    dir_named       디렉토리 옆에 같은 이름의 MD — 구 dir-단위 흔적
    orphan_stem     🔴 대응 소스 파일이 없다 (좀비 MD)

## 🔴 왜 이것이 우리에게 특히 맞나 — 우리 코퍼스가 원전에서 왔다

`config.yaml` 의 `index.source` 가 **`infra_state_20260808.zip`** 이다. 지금 트윈 1,056건은
원전 환경에서 **받아온 스냅샷**이고, 그러므로 **원전이 겪은 손상 유형을 그대로 안고 있을 수
있다.** 이 감사는 정확히 그 코퍼스를 위해 쓰인 도구다.

⚠️ 이식 전 실측(2026-08-14): frontmatter 없음 1건 · 본문 50자 미만 147건 · `## 요약` 없음
163건 · **펜스 감싸짐 0건**. 표본이 전부 `_archive/project_alpha_md/` 였다 — 🔴 검색 로그에서
두 번 올라온 그 아카이브다(소 3.4.5·3.4.2 관측). 세 신호가 같은 곳을 가리킨다.

## 🔴 분류 순서가 판정을 바꾼다 (원전 그대로)

    ① dir_named    구조 흔적 — **내용 분류보다 먼저**
    ② orphan_stem  대응 소스 부재 — 내용이 아무리 멀쩡해도 좀비다
    ③ 내용 분류

순서를 바꾸면 아카이브된 문서가 `shell_only`(재생성 대상)로 잡힌다 — **재생성할 소스가 없는데
재생성 대상이 된다.** 원전이 이 순서를 고른 이유가 그것이다.

## 원전과 다르게 둔 것 둘

**① 복구는 「계획」이 기본이다.** 원전 `repair_context_md` 는 파일을 고치고 옮긴다. 우리는
`work/cleanup.py` 규약(*"기본은 세기만 한다"*)을 따라 **계획을 내고, 적용은 호출자가 명시**한다.
🔴 그리고 **아카이브 이동(`dir_named`·`orphan_stem`)은 이식 범위 밖으로 뒀다** — 트윈 문서를
옮기는 것은 사람의 판단이고, 지금 `_archive` 를 어떻게 할지가 **열린 질문**이다(검색 결과에
섞이는 것이 관측됐다). 근거 없이 옮기지 않는다.

**② 자동 복구는 펜스·자연어 도입부만.** 원전과 같다(LLM 0). ⚠️ 실측상 지금 **대상이 0건**이지만
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

# 🔴 LLM 0 으로 고칠 수 있는 것 / 재생성이 필요한 것 / 사람이 판단할 것
AUTO_FIXABLE = ("pence_wrapped", "natural_prefix")
NEEDS_REGEN = ("shell_only", "empty_summary", "no_frontmatter")
HUMAN_CALL = ("dir_named", "orphan_stem")


def strip_code_block_wrapper(md: str) -> str:
    """```markdown … ``` 펜스 + frontmatter 앞 자연어 도입부를 걷어낸다. **원전 그대로.**

    ⚠️ 원전은 이 함수를 `watcher/context.py` 와 MCP 양쪽에 **복제**해 두고 *"drift 차단을 위해
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
    # ⚠️ `## 코멘트` 이후는 **사람이 쓴 것**이라 시스템 평가 대상이 아니다 (원전 판단)
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
    """전체 진단 — 🔴 **읽기 전용.** `{total, categories, by_path, unreadable}`.

    🔴 순서: `dir_named` → `orphan_stem` → 내용 분류 (머리말 참조 — 바꾸면 판정이 바뀐다).
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
            # 🔴 조용히 건너뛰지 않는다 — 원전은 로그 한 줄만 남겼다. 우리는 세어서 돌려준다.
            unreadable.append(f"{rel_str}: {e}")
            continue

        cat = classify(content)
        categories[cat].append(rel_str)
        by_path[rel_str] = cat

    return {"total": sum(len(v) for v in categories.values()),
            "categories": categories, "by_path": by_path, "unreadable": unreadable}


def format_report(result: dict, sample_per_cat: int = 5) -> str:
    """사람이 읽는 리포트. 🔴 **무엇을 어떻게 고치는지까지** 적는다 (원전과 같은 구성)."""
    total = result.get("total", 0)
    cats = result.get("categories", {})
    if result.get("error"):
        return f"🔴 진단 불가 — {result['error']}"

    out = ["# 컨텍스트 MD 진단 리포트", "", f"- 총 파일: **{total}건**", ""]
    if result.get("unreadable"):
        out += [f"- 🔴 읽지 못한 파일 **{len(result['unreadable'])}건** "
                "(진단에서 빠졌다 — 사람이 봐야 한다)", ""]

    out += ["| 분류 | 건수 | 비율 | |", "|---|---|---|---|"]
    for c in CATEGORY_ORDER:
        n = len(cats.get(c, []))
        pct = (n / total * 100) if total else 0.0
        mark = "✅" if c == "valid" else ("🔧" if c in AUTO_FIXABLE else "⚠️")
        out.append(f"| `{c}` | {n} | {pct:.1f}% | {mark} |")
    out.append("")

    auto_n = sum(len(cats.get(c, [])) for c in AUTO_FIXABLE)
    out += [f"**자동 복구 가능 (LLM 0)**: {auto_n}건 — 펜스·자연어 도입부 제거", ""]
    regen_n = sum(len(cats.get(c, [])) for c in NEEDS_REGEN)
    if regen_n:
        out += [f"**LLM 재생성 필요**: {regen_n}건 — 소스가 다시 커밋되면 자연 회복한다", ""]
    human_n = sum(len(cats.get(c, [])) for c in HUMAN_CALL)
    if human_n:
        out += [f"🔴 **사람의 판단**: {human_n}건 — `dir_named`·`orphan_stem` 은 **옮기지 않는다.** "
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


# ── 자동 복구 — 🔴 **계획이 기본이다** (`work/cleanup.py` 와 같은 규약) ──────────

def plan_repair(context_dir, result: dict) -> dict:
    """펜스·자연어 도입부를 걷어낼 수 있는 것만 고른다. 🔴 **아무것도 쓰지 않는다.**

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
    """계획의 후보만 고친다. 🔴 **계획이 고른 것 밖은 건드리지 않는다.**"""
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
    """진단 + 리포트 파일 (🔴 **고치지 않는다**). 출력 `<프로젝트 데이터>/analysis/` (§5.5).

    🔴 **이것은 유휴 배치가 아니다 — 요청 시 도는 것이다.** 원전 `watch.py` 는 `context_audit`
    을 유휴 사이클에서 부르지 않는다(`import` 목록에 없다). 통로는 셋이었다: MCP 도구
    `audit_context_md` · HTTP 엔드포인트 · 스킬 `/audit-context`. 배치에 얹으면 **원전에 없는
    것을 내가 만드는 것**이므로 하지 않는다.

    ⚠️ **기록만 해 둔 개선 후보**: 주기적으로 돌려 트윈 건강도를 추적하기(방금 만든
    `master/batch/` 자리에 한 줄이면 된다). 🔴 원전에 없으므로 지금 넣지 않는다.
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


# ── CLI — 🔴 `report` 가 기본이고 `repair` 는 명시해야 한다 ──────────────────────

def main(argv: list | None = None) -> int:
    import sys
    from .paths import resolve

    args = list(argv if argv is not None else sys.argv[1:])
    cmd = args[0] if args else "report"
    if cmd in ("-h", "--help", "help"):
        print("사용법: python -m master.context_search.context_audit report|plan|repair [프로젝트]")
        print("  report  진단 + 리포트 파일 (기본, 🔴 고치지 않는다)")
        print("  plan    🔴 LLM 0 으로 고칠 수 있는 것만 보여준다 (아무것도 안 쓴다)")
        print("  repair  그 계획을 적용한다 — 펜스·자연어 도입부만.")
        print("          🔴 dir_named·orphan_stem 은 옮기지 않는다 (사람의 판단)")
        return 0

    paths = resolve(args[1] if len(args) > 1 else "")
    result = audit(paths.context, paths.repo)
    if result.get("error"):
        print(f"🔴 {result['error']}")
        return 1

    if cmd == "report":
        r = run_for_project(paths)
        print(format_report(result))
        print(f"\n→ {r['files'][0] if r.get('files') else '(파일 없음)'}")
        return 0 if r.get("ok") else 1

    plan = plan_repair(paths.context, result)
    print(f"고칠 수 있는 것 {len(plan['fixable'])}건 · 거부 {len(plan['refused'])}건")
    for rel, before, after in plan["fixable"][:20]:
        print(f"  🔧 {rel}  ({before} → {after})")
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
