"""범위 플랜 (`#639` · 설계안 `docs/17-review-queue.md` §3.6 (나)) — 리뷰 큐 `kind=scope` 의 본체.

*"전투 시스템 전체 봐줘"* 같은 사람 요청을 받아 **그 범위의 개선 플랜**을 낸다. 산출물은 리뷰
파일이 아니라 **플랜**이다(주간 플랜과 같은 형식) — 원전 규약이 *"변경되지 않은 기존 코드의
이슈는 주간 플랜 담당"* 이라, 리뷰로 내면 파서 계약(변경분 표)도 역할 분담도 깨진다.

## 사용자 결정 (2026-11-12)

    ① 리뷰가 없는 파일은 **그 파일을 마지막으로 건드린 커밋**을 평범한 `kind=commit` 으로 등재해
       채운다 — 「파일 전체 리뷰」라는 새 산출물을 만들지 않는다.
    ② 입구는 마스터 CLI 와 `ax-projects` MCP 도구 하나. `.33`·8101 표면은 없다.
    ③ 저장은 `plans/_scope/<slug>/<회차>/` — `_` 접두라 주간 플랜 집계·`fix_index` 가 읽지 않는다.
       Redmine 에 등록하지 않는다.
    ④ 대상은 저장소 기준 디렉토리·경로(색인 경계 안) 또는 `domain:<도메인>`.

## 한 회차 (`run_scope`)

    ① 대상 → 범위 안 소스 파일 (결정적 실패면 1회에 종결)
    ② 파일마다 마지막 커밋 → 큐 상태·리뷰 파일로 가른다: 덮임 / 대기 / 공백 / 미등재
    ③ 미등재는 `kind=commit` 으로 등재 (사람 요청 우선순위 10 · 요청자 `scope:<slug>`)
    ④ 대기·방금 등재가 하나라도 있으면 이번 회차는 **대기**(WAIT · 회차당 1번 · 상한 12)
    ⑤ 다 끝났으면 덮인 커밋의 리뷰 지적 중 **범위 안 파일**만 모아 플랜을 만든다
    ⑥ `_summary.md` — 대상·파일·커밋·공백·지적·플랜·실패

[중요] 원본 리뷰는 옮기지 않는다 — 아카이브는 주간 플랜의 몫이다. 같은 지적이 주간 플랜에도
실릴 수 있다(산출물이 다르다 — 이쪽은 번호도 Redmine 일감도 받지 않는다).
[중요] 공백(리뷰가 포기된 커밋 · 커밋을 못 찾은 파일)은 **다시 등재하지 않고 보고한다** —
포기된 리뷰를 범위 요청마다 되살리면 끝나지 않는다. 복구는 사람이 요청 창구로 한다.

실행: .venv/bin/python -m master.context_synth.scope_plan request [--project P] <대상>
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import review_gen as rg
from . import review_queue as rq

PLANS_DIRNAME = "plans"
SCOPE_DIRNAME = "_scope"        # `_` 접두 — `fix_index._plan_files`·주간 플랜 인덱스가 건너뛴다
DOMAIN_PREFIX = "domain:"
PRIORITY = 10                   # 채우는 커밋 리뷰 — 사람 요청 (`#638` 규약 · `issue_link.PRIORITY` 와 같은 값)
# 🔴 범위 항목 자신은 그보다 **한 칸 아래**다. 같은 값이면 먼저 등재된 범위 항목이 매 회차 맨 앞에서
#    꺼내져 대기 1회를 쓰고 자리 하나를 차지한다 — 회차는 시간 예산(`review_runner.RUN_BUDGET`)으로
#    커밋 리뷰 몇 건에서 끊기므로, 커밋이 많은 범위는 플랜에 닿기 전에 대기 상한(12)에서 포기된다.
#    한 칸 아래면 채울 커밋 리뷰가 먼저 돌고, 자리가 남는 회차에만 범위 항목이 다시 본다.
#    자동 등재(0)보다는 여전히 앞선다.
SCOPE_PRIORITY = PRIORITY - 1

# 🔴 아래 둘은 `review_queue` 의 마커와 **글자가 같아야** 한다 — 갈래 판정(`rq.classify`)이 이 문구를 본다.
BAD_TARGET_WHY = "범위 대상을 해석하지 못했다"     # DETERMINISTIC_MARKERS — 1회에 종결
WAIT_WHY = "커밋 리뷰를 기다린다"                  # WAIT_MARKERS — 회차당 1번 · 상한 12

# 지적은 있는데 플랜이 0건일 때의 표시 — 기준 자체는 `plan_generator` 가 갖는다(여기서 다시 판정하지 않는다).
BELOW_GATE = "플랜 기준 미달"
GATE_RULE = "파일별 고위험 1건 이상 또는 중위험 3건 이상 · 반복 패턴 — plan_generator 기준"

_SLUG_UNSAFE = re.compile(r"[^0-9A-Za-z가-힣._-]+")
_DOMAIN_NAME = re.compile(r"^[0-9A-Za-z가-힣_.-]+$")


class ScopeError(ValueError):
    """대상을 해석할 수 없다 — 몇 번을 돌려도 같다(결정적)."""


@dataclass
class Scope:
    key: str                    # 정규화한 대상 — 큐 항목의 key (`master/context_synth` · `domain:Combat`)
    kind: str                   # "path" | "domain"
    slug: str
    files: list = field(default_factory=list)


# ── 대상 해석 ────────────────────────────────────────────────────────────────

def normalize_target(target: str) -> tuple:
    """대상 문자열 → `(kind, key)`. 형식이 틀리면 `ScopeError`.

    경로는 저장소 기준 상대 경로다 — 절대 경로·`..`·빈 값은 거절한다. 도메인은 `domain:<이름>`
    으로 **명시**한다(이름만 보고 경로인지 도메인인지 추측하지 않는다).
    """
    t = str(target or "").strip()
    if not t:
        raise ScopeError("대상이 비었다")
    if t.startswith(DOMAIN_PREFIX):
        name = t[len(DOMAIN_PREFIX):].strip()
        if not name or not _DOMAIN_NAME.match(name) or name in (".", ".."):
            raise ScopeError(f"도메인 이름이 아니다: {name or '(빈 값)'}")
        return "domain", DOMAIN_PREFIX + name
    p = t.replace("\\", "/")
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        raise ScopeError(f"절대 경로는 받지 않는다 — 저장소 기준 상대 경로를 준다: {t}")
    parts = [x for x in p.split("/") if x not in ("", ".")]
    if ".." in parts:
        raise ScopeError(f"`..` 이 든 경로는 받지 않는다: {t}")
    if not parts:
        raise ScopeError(f"대상이 저장소 전체다 — 색인 경계 안의 디렉토리·경로를 준다: {t}")
    return "path", "/".join(parts)


def slug_for(key: str) -> str:
    """대상의 디렉토리 이름 — 파일시스템에 안전하고 같은 대상이면 늘 같다.

    읽을 수 있는 부분 + 해시 8자. 해시가 있어 `a/b` 와 `a_b` 가 겹치지 않는다.
    """
    k = str(key or "")
    base = _SLUG_UNSAFE.sub("_", k).strip("._-")[:60] or "scope"
    return f"{base}-{hashlib.sha1(k.encode('utf-8')).hexdigest()[:8]}"


def _scope_of(paths):
    from ..context_search.paths import scope_of                   # noqa: PLC0415
    return getattr(paths, "scope", None) or scope_of(Path(paths.root))


def _boundary_files(paths, sc) -> list:
    """색인 경계 안의 추적 파일 — 인자 조립은 `class_graph.ls_files_args` 한 자리다."""
    import types                                                   # noqa: PLC0415

    from ..graph.class_graph import ls_files_args                  # noqa: PLC0415
    rc, out = rg._git(Path(paths.repo), *ls_files_args(types.SimpleNamespace(scope=sc)))
    if rc != 0:
        raise RuntimeError(f"git ls-files 실패 (rc={rc}): {out[:200]}")
    return [f for f in (ln.strip().replace("\\", "/") for ln in out.splitlines())
            if f and sc.contains(f)]


def resolve_scope(paths, target: str) -> Scope:
    """대상 → 범위 안 **소스 파일**(정렬). 못 풀면 `ScopeError`(결정적).

    경계는 `paths.scope.contains`, 소스 필터는 커밋 리뷰와 같은 `review_gen.review_source_files`
    다 — 문서·데이터 파일이 리뷰 호출을 만들지 않는다. git 이 실패하면 `RuntimeError`(일시적).
    """
    kind, key = normalize_target(target)
    sc = _scope_of(paths)
    if kind == "path":
        if not any(key == r or key.startswith(r.rstrip("/") + "/") for r in sc.roots):
            raise ScopeError(f"색인 경계 밖이다: {key} (경계: {sc.label()})")
        if any(key == x or key.startswith(x.rstrip("/") + "/") for x in sc.exclude):
            raise ScopeError(f"색인 경계에서 제외된 경로다: {key} (경계: {sc.label()})")
        tracked = _boundary_files(paths, sc)
        cand = [f for f in tracked if f == key or f.startswith(key + "/")]
        if not cand:
            raise ScopeError(f"그 경로에 추적 중인 파일이 없다: {key} "
                             f"(도메인이면 `{DOMAIN_PREFIX}<이름>` 으로 준다)")
    else:
        name = key[len(DOMAIN_PREFIX):]
        if not (Path(paths.ontology) / "domains" / name / "domain.yaml").is_file():
            raise ScopeError(f"없는 도메인이다: {name}")
        from ..ontology import collect                             # noqa: PLC0415
        members = collect.members_of(paths, name)
        recorded = {str(f).replace("\\", "/") for f in members.values() if f}
        if not recorded:
            raise ScopeError(f"도메인 {name} 의 멤버에 소스 파일이 적혀 있지 않다")
        tracked = set(_boundary_files(paths, sc))
        cand = sorted(recorded & tracked)
        if not cand:
            raise ScopeError(f"도메인 {name} 의 멤버 파일 {len(recorded)}건이 색인 경계 안에 없다")
    files = sorted(set(rg.review_source_files(paths, cand)))
    if not files:
        raise ScopeError(f"범위에 리뷰할 소스 파일이 없다: {key} (추적 파일 {len(cand)}건)")
    return Scope(key=key, kind=kind, slug=slug_for(key), files=files)


# ── 파일 → 마지막 커밋 → 상태 ────────────────────────────────────────────────

def last_commits(repo, files: list) -> tuple:
    """`({커밋: [그 커밋이 마지막으로 건드린 범위 파일]}, [커밋을 못 찾은 파일])`.

    미러의 로컬 객체만 읽는다(`review_gen._git`). git 이 실패하면 `RuntimeError`.
    """
    by_commit: dict = {}
    orphan: list = []
    for f in files:
        rc, out = rg._git(Path(repo), "log", "-1", "--format=%H", "--", f)
        if rc != 0:
            raise RuntimeError(f"git log 실패 ({f}, rc={rc}): {out[:200]}")
        sha = out.strip().splitlines()[0].strip() if out.strip() else ""
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            by_commit.setdefault(sha, []).append(f)
        else:
            orphan.append(f)
    return by_commit, orphan


def commit_files(paths, commit: str, fallback=()) -> list:
    """그 커밋이 바꾼 소스 파일 — 색인기가 등재할 때 싣는 것과 같은 모양(저장소 기준 · 소스만)."""
    rc, out = rg._git(Path(paths.repo), "show", "--name-only", "--no-renames", "--format=", commit)
    names = [ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()] if rc == 0 else []
    return rg.review_source_files(paths, names) or list(fallback)


def reviewed_commits(root) -> dict:
    """`{커밋(리뷰 머리말의 해시): 리뷰 파일}` — 작성자 디렉토리와 그 `_archive/` 의 **정형** 리뷰.

    큐에 항목이 없어도(큐 도입 전 리뷰 · 정리된 큐) 리뷰 파일이 있으면 그 커밋은 덮인 것이다.
    파일 → 커밋 대응은 `fix_index` 의 것을 그대로 쓴다. 형식 위반 파일은 세지 않는다 —
    소비자 기준 0건이라 색인기도 그런 커밋은 다시 등재한다.
    """
    from . import fix_index as fx                                  # noqa: PLC0415
    out: dict = {}
    for f in fx._review_files(Path(root)):
        commit = fx._review_head(f).get("commit") or ""
        if not commit:
            continue
        try:
            ok = rg.format_ok(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            ok = False
        if ok:
            out[commit] = f
    return out


def _same_commit(a: str, b: str) -> bool:
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def classify_commits(paths, commits) -> dict:
    """커밋들을 큐 상태·리뷰 파일로 가른다.

        covered   큐 `done` · 또는 정형 리뷰 파일이 있다
        waiting   큐 `pending`/`running`
        gaps      큐 `abandoned`/`failed` 이고 리뷰 파일도 없다 — 다시 넣지 않는다
        missing   큐에도 파일에도 없다 — 등재 대상

    반환 `{"covered": [...], "waiting": [...], "gaps": [{"commit", "why"}], "missing": [...]}`.
    """
    state = {it.get("id"): it for it in rq.items(paths.root)}
    on_disk = reviewed_commits(paths.root)
    out = {"covered": [], "waiting": [], "gaps": [], "missing": []}
    for c in commits:
        it = state.get(rq.item_id("commit", c))
        st = (it or {}).get("state")
        if st == "done":
            out["covered"].append(c)
        elif st in ("pending", "running"):
            out["waiting"].append(c)
        elif any(_same_commit(c, k) for k in on_disk):
            out["covered"].append(c)
        elif st in ("abandoned", "failed"):
            out["gaps"].append({"commit": c, "why": f"리뷰 {st} — {(it.get('last_why') or '사유 미기록')[:120]}"})
        else:
            out["missing"].append(c)
    return out


# ── 지적 수집 ────────────────────────────────────────────────────────────────

def _review_dirs(root) -> list:
    base = Path(root) / rg.REVIEWS_DIRNAME
    if not base.is_dir():
        return []
    out = []
    for author in sorted(d for d in base.iterdir() if d.is_dir() and not d.name.startswith("_")):
        out.append(author)
        out.extend(sorted(d for d in author.glob("_archive/*") if d.is_dir()))
    return out


def _in_scope(file: str, scope_files: list) -> str:
    """리뷰 표의 파일 칸 → 범위 안 파일 경로. 범위 밖이면 빈 문자열.

    리뷰어가 경로를 줄여 쓰기도 한다(`A.cpp`) — 범위 파일의 **꼬리와 하나만** 맞으면 그 파일이다.
    둘 이상 맞으면 고르지 않는다.
    """
    f = str(file or "").strip().strip("`").replace("\\", "/").lstrip("./")
    if not f:
        return ""
    if f in scope_files:
        return f
    hits = [s for s in scope_files if s.endswith("/" + f)]
    return hits[0] if len(hits) == 1 else ""


def collect_issues(paths, scope_files: list, commits) -> list:
    """덮인 커밋의 리뷰 지적 중 **범위 안 파일**의 것만. 기간 창이 없다(주간 플랜은 7일).

    작성자 디렉토리와 `_archive/` 를 전부 읽는다 — 파서는 주간 플랜과 같은
    `review_collector.parse_review_reports` 다. 파일 칸은 범위 파일의 전체 경로로 맞춘다
    (플랜 생성기가 그 경로로 소스 조각을 읽는다).
    """
    from .review_collector import parse_review_reports             # noqa: PLC0415
    want = list(commits)
    out = []
    for d in _review_dirs(paths.root):
        for issue in parse_review_reports(d, "0000-00-00"):
            sha = issue.commit_hash or Path(issue.source_review).stem.rsplit("_", 1)[-1]
            if not any(_same_commit(sha, c) for c in want):
                continue
            full = _in_scope(issue.file, scope_files)
            if full:
                out.append(dataclasses.replace(issue, file=full))
    return out


# ── 요약 ────────────────────────────────────────────────────────────────────

def summary_md(scope: Scope, *, label: str, commits: dict, covered: list, gaps: list,
               orphan: list, issues: int, grouped: dict | None, result: dict | None,
               plan_names: list, severities: str = "") -> str:
    failures = (result or {}).get("failures") or []
    made = (result or {}).get("plans_generated", 0)
    if failures:
        status = "생성 미완료"
    elif not issues:
        status = "지적 0건 — 플랜 없음"
    elif not made:
        status = BELOW_GATE          # 지적은 있으나 플랜 생성기의 기준에 못 미쳤다 — 조용히 0건이 되지 않게
    else:
        status = "완료"
    lines = [
        "---",
        f"scope: {scope.key}",
        f"run: {label}",
        f"plans_generated: {(result or {}).get('plans_generated', 0)}",
        f"status: {status}",
        "---",
        "",
        f"# 범위 플랜 요약 — {scope.key}",
        "",
        f"- 대상: `{scope.key}` ({'도메인' if scope.kind == 'domain' else '경로'})",
        f"- 회차: {label}",
        f"- 범위 안 소스 파일: {len(scope.files)}건",
        f"- 마지막 커밋: {len(commits)}건 — 리뷰로 덮임 {len(covered)} · 공백 {len(gaps)}",
        f"- 커밋을 찾지 못한 파일: {len(orphan)}건",
        f"- 수집 지적: {issues}건"
        + (f" (정리 뒤 {grouped['total']}건 · 코멘트 제외 {grouped['excluded_count']} · "
           f"파일 {len(grouped['file_issues'])}그룹 · 패턴 {len(grouped['pattern_issues'])})" if grouped else ""),
        *([f"- 지적 심각도: {severities}"] if severities else []),
        f"- 생성한 플랜: {(result or {}).get('plans_generated', 0)}건 · 실패 {len(failures)}건"
        + (f" — {BELOW_GATE}({GATE_RULE})" if status == BELOW_GATE else ""),
        "- Redmine 등록 없음 · 원본 리뷰 이동 없음 (`#639`)",
    ]
    if plan_names:
        lines += ["", "## 플랜", *[f"- [{n}]({n})" for n in plan_names]]
    if gaps or orphan:
        lines += ["", "## 공백 — 이 범위에서 리뷰가 없는 곳"]
        for g in gaps:
            fs = ", ".join(commits.get(g["commit"], [])[:5])
            lines.append(f"- 커밋 `{g['commit'][:12]}` — {g['why']} (파일: {fs})")
        lines += [f"- 파일 `{f}` — 마지막 커밋을 찾지 못했다" for f in orphan]
    if failures:
        lines += ["", "## 생성 실패"]
        lines += [f"- {x.get('file')}: {str(x.get('reason') or '')[:300]}" for x in failures]
    return "\n".join(lines) + "\n"


# ── 소비자 한 회차 ───────────────────────────────────────────────────────────

def run_scope(paths, item: dict, res, *, chat=None, logf=None, now: datetime | None = None):
    """범위 항목(`kind=scope`) 한 회차. `res` 는 `review_runner.RunnerResult` — 채워서 돌려준다.

    `chat(prompt) -> str` 주입은 테스트 자리다. 기본은 플랜 생성기와 같은 상용 체인
    (`review_gen.commercial_chat`)이고, 빈 임시 디렉터리를 작업 자리로 준다(`#844` — 에이전트가
    서비스 작업 폴더 = 마스터 라이브 트리에서 명령을 돌리지 않게). 상용 호출에 한도를 두지 않는다.
    """
    log = logf or (lambda m: None)
    root, iid = paths.root, item["id"]

    def fail(why: str):
        got = rq.finish(root, iid, ok=False, why=why, logf=log)
        res.state, res.why = "failed", why
        log(f"[범위플랜] 종료 {item.get('key')} — {got.get('state')} "
            f"(갈래 {got.get('last_kind')} · 시도 {got.get('attempts')}) {why[:100]}")
        return res

    # ① 대상 해석
    try:
        scope = resolve_scope(paths, item.get("key") or "")
    except ScopeError as e:
        return fail(f"{BAD_TARGET_WHY} — {e}")
    except Exception as e:                                         # noqa: BLE001
        return fail(f"범위 해석 실패 — {type(e).__name__}: {e}")
    try:
        commits, orphan = last_commits(paths.repo, scope.files)
    except RuntimeError as e:
        return fail(f"범위 커밋 조회 실패 — {e}")
    log(f"[범위플랜] 해석 {scope.key} ({scope.kind}) — 파일 {len(scope.files)} · 커밋 {len(commits)}"
        + (f" · 커밋 없는 파일 {len(orphan)}" if orphan else ""))

    # ② 가르기 → ③ 미등재 등재
    cls = classify_commits(paths, sorted(commits))
    queued = 0
    for c in cls["missing"]:
        files = commit_files(paths, c, fallback=commits[c])
        got = rq.enqueue(root, kind="commit", key=c, files=files,
                         requester=f"scope:{scope.slug}", priority=PRIORITY, logf=log)
        queued += 1
        log(f"[범위플랜] 등재 {c[:8]} 파일 {len(files)}건 ({got.get('state')}) — 범위 파일 "
            f"{', '.join(commits[c][:3])}{' …' if len(commits[c]) > 3 else ''}")
    for g in cls["gaps"]:
        log(f"[범위플랜] [주의] 공백 {g['commit'][:8]} — {g['why']} · 다시 등재하지 않는다")
    for f in orphan:
        log(f"[범위플랜] [주의] 공백 — 마지막 커밋을 찾지 못한 파일 {f}")

    # ④ 대기
    waiting = len(cls["waiting"]) + queued
    if waiting:
        why = (f"범위 {scope.key} — {WAIT_WHY} (대기 {len(cls['waiting'])}건 · 이번 회차 등재 {queued}건 "
               f"/ 커밋 {len(commits)}건 · 덮임 {len(cls['covered'])} · 공백 {len(cls['gaps'])})")
        log(f"[범위플랜] 대기 {scope.key} — 남은 커밋 리뷰 {waiting}건 "
            f"(대기 {len(cls['waiting'])} · 등재 {queued}) · 다음 회차에 다시 본다")
        rq.set_meta(root, iid, slug=scope.slug, files=len(scope.files), commits=len(commits),
                    waiting=waiting)
        return fail(why)

    # ⑤ 지적 → 플랜
    from .issue_classifier import group_issues                     # noqa: PLC0415
    from .plan_generator import generate_improvement_plans         # noqa: PLC0415
    covered = cls["covered"]
    issues = collect_issues(paths, scope.files, covered)
    label = (now or datetime.now()).strftime("%Y-%m-%d_%H%M")
    plans_dir = Path(root) / PLANS_DIRNAME / SCOPE_DIRNAME / scope.slug
    run_dir = plans_dir / label
    rel = f"{PLANS_DIRNAME}/{SCOPE_DIRNAME}/{scope.slug}/{label}"
    grouped = group_issues(issues, Path(paths.context)) if issues else None
    total = grouped["total"] if grouped else 0
    log(f"[범위플랜] 지적 {scope.key} — 수집 {len(issues)}건 · 정리 뒤 {total}건"
        + (f" (코멘트 제외 {grouped['excluded_count']} · 파일 {len(grouped['file_issues'])}그룹 · "
           f"패턴 {len(grouped['pattern_issues'])})" if grouped else "")
        + f" · 덮인 커밋 {len(covered)} · 공백 {len(cls['gaps']) + len(orphan)}")

    sev: dict = {}
    for i in issues:
        sev[i.severity or "?"] = sev.get(i.severity or "?", 0) + 1
    severities = " · ".join(f"{k} {v}" for k, v in sorted(sev.items()))
    result = None
    if total:
        from contextlib import ExitStack                           # noqa: PLC0415

        from ..work import usage as usage_mod                      # noqa: PLC0415
        with ExitStack() as stack:
            ask = chat
            if ask is None:
                import tempfile                                    # noqa: PLC0415
                try:
                    empty = stack.enter_context(tempfile.TemporaryDirectory(
                        prefix="ax-scope-plan-", ignore_cleanup_errors=True))
                except OSError as e:
                    return fail(f"범위 플랜 빈 작업 디렉터리 생성 실패 — {type(e).__name__}: {e}")
                log(f"[범위플랜] 상용 체인 작업 디렉터리 {empty} (빈 디렉터리)")
                ask = lambda p: rg.commercial_chat(p, workdir=empty)   # noqa: E731
            repo_dir = Path(paths.repo) if getattr(paths, "repo", None) else None
            with usage_mod.sink(paths.usage_log, source="scope_plan", task_id=f"scope:{scope.slug}"):
                result = generate_improvement_plans(grouped, Path(paths.context), plans_dir, repo_dir,
                                                    label, chat=ask, logf=log)
        log(f"[범위플랜] 플랜 생성 {scope.key} — {result['plans_generated']}건 저장 · "
            f"검증 통과 후보 {result['validated_candidates']} · 실패 {len(result['failures'])} "
            f"(토큰 ~{result['tokens_used']:,})")

    # ⑥ 요약
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        names = sorted(f.name for f in run_dir.glob("*.md") if not f.name.startswith("_"))
        (run_dir / "_summary.md").write_text(
            summary_md(scope, label=label, commits=commits, covered=covered, gaps=cls["gaps"],
                       orphan=orphan, issues=len(issues), grouped=grouped, result=result,
                       plan_names=names, severities=severities),
            encoding="utf-8")
    except OSError as e:
        return fail(f"범위 플랜 요약 저장 실패 — {type(e).__name__}: {e}")
    log(f"[범위플랜] 저장 {rel}/ — 플랜 {len(names)}건 + _summary.md")
    rq.set_meta(root, iid, slug=scope.slug, files=len(scope.files), commits=len(commits), waiting=0,
                run=label, plans_dir=rel, issues=len(issues), plans=len(names),
                gaps=len(cls["gaps"]) + len(orphan))

    failures = (result or {}).get("failures") or []
    if failures:
        # 플랜 생성기는 하나라도 실패하면 아무것도 쓰지 않는다 — 다음 회차가 처음부터 다시 만든다.
        first = str(failures[0].get("reason") or "")[:200]
        return fail(f"범위 플랜 생성 미완료 — {len(failures)}건 실패: {failures[0].get('file')}: {first}")

    gap_n = len(cls["gaps"]) + len(orphan)
    if not total:
        note = "지적 0건 — 플랜 없음"
    elif not names:
        note = f"{BELOW_GATE} — 플랜 0건 · 지적 {total}건({severities})"
        log(f"[범위플랜] [주의] {scope.key} — 지적 {total}건({severities})이 있으나 {BELOW_GATE}: {GATE_RULE}")
    else:
        note = f"플랜 {len(names)}건 · 지적 {total}건"
    note += f" · 파일 {len(scope.files)} · 커밋 {len(commits)}" + (f" · 공백 {gap_n}" if gap_n else "") + f" → {rel}"
    rq.finish(root, iid, ok=True, note=note, logf=log)
    res.state, res.written = "done", str(run_dir / "_summary.md")
    log(f"[범위플랜] 종료 {scope.key} — done · {note}")
    return res


# ── 입구 ────────────────────────────────────────────────────────────────────

def request(paths, target: str, *, requester: str = "cli", logf=None) -> dict:
    """범위 플랜을 요청한다 — 대상을 검증하고 큐에 `kind=scope` 로 등재한다(LLM 0).

    대상을 못 풀면 `ScopeError`. 이미 대기·진행·완료인 대상이면 `already=True` 로 그 항목을 돌려준다.
    """
    log = logf or (lambda m: None)
    scope = resolve_scope(paths, target)
    iid = rq.item_id("scope", scope.key)
    prior = next((x for x in rq.items(paths.root) if x.get("id") == iid), None)
    already = bool(prior) and prior.get("state") in ("pending", "running", "done")
    item = rq.enqueue(paths.root, kind="scope", key=scope.key, requester=requester,
                      priority=SCOPE_PRIORITY, logf=log)
    name = getattr(paths, "name", "") or ""
    if already:
        log(f"[범위플랜] 요청 생략 kind=scope {scope.key} ({name}) — 이미 {item.get('state')}")
    else:
        log(f"[범위플랜] 요청 등재 kind=scope {scope.key} ({name}) 요청자={requester} — "
            f"파일 {len(scope.files)}건 · 큐 소비자가 플랜 경로로 처리한다")
    return {"ok": True, "already": already, "id": item.get("id"), "state": item.get("state"),
            "project": name, "target": scope.key, "kind": scope.kind, "slug": scope.slug,
            "files": len(scope.files),
            "plans_dir": f"{PLANS_DIRNAME}/{SCOPE_DIRNAME}/{scope.slug}"}


def main(argv=None) -> int:
    import argparse

    # 🔴 마운트된 프로젝트만 받는다 — MCP 입구와 같은 정책(검색·갱신은 마운트된 것만, 예외 없음).
    from ..context_search.paths import resolve_mounted_only
    from ..projects.config import ConfigError

    ap = argparse.ArgumentParser(description="범위 플랜 요청 (#639)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("request", help="대상(디렉토리·경로 또는 domain:<이름>)의 개선 플랜을 큐에 요청한다")
    rp.add_argument("--project", default="", help="프로젝트 (기본: 마운트된 프로젝트)")
    rp.add_argument("target", help="저장소 기준 경로 또는 domain:<도메인>")
    a = ap.parse_args(argv)

    try:
        paths = resolve_mounted_only(a.project)
    except ConfigError as e:
        print(f"[중요] [범위플랜] 프로젝트를 풀지 못했다: {e}", flush=True)
        return 1
    try:
        out = request(paths, a.target, requester="cli", logf=lambda m: print(m, flush=True))
    except ScopeError as e:
        print(f"[범위플랜] 거절 — {BAD_TARGET_WHY}: {e}", flush=True)
        return 2
    except (rq.ReviewQueueError, RuntimeError) as e:
        print(f"[중요] [범위플랜] 등재 실패 — {type(e).__name__}: {e}", flush=True)
        return 1
    if out["already"]:
        print(f"이미 {out['state']} — {out['id']} ({out['project']})", flush=True)
    else:
        print(f"등재 {out['id']} ({out['project']}) 상태={out['state']} 파일 {out['files']}건 "
              f"→ {out['plans_dir']}/", flush=True)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
