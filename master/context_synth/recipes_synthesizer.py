"""소비자 recipes_synthesizer (#157) — 원전 `watcher/recipes_synthesizer.py` 629줄의 이식.

생산자②(`signals.py`)가 쌓은 `recipes/_signals.jsonl` 을 유휴 시간에 소화한다:
    ① LLM 클러스터링 (같은 의도의 신호 묶기)
    ② 임계치(min_signals)를 넘은 클러스터만 레시피 MD 로 합성 — 다음 code-writer 가
       작업 시작 시 읽는 절차서다. 미달 클러스터의 신호는 다음 사이클까지 남는다.
    ③ 처리된 신호는 `_signals.archive.jsonl` 로 이동 (28일 보관)
    ④ rejected_approaches + error_recoveries 는 별도로 `_anti_patterns.md` 카탈로그로
       집계 (negative learning — sparse 하지만 학습 가치가 가장 높다)

원전과의 차이 (로직 동일):
    common._call_llm      → 상용 체인 (원전 기본값도 Claude — #205 실측 근거와 같다)
    base_dir              → paths (신호는 `{root}/recipes/`, files_read 해석은 `{root}/repo/`
                            기준 — 원전 base_dir 는 Source/ 를 품은 프로젝트 루트였고 우리
                            위상에서 그 자리는 repo 다)
    [주의] 읽기 도구(find_recipes/get_anti_patterns — code-writer 가 작업 시작 시 부르는
    쪽)는 원전 code_recipes MCP 서버 소관으로 이 629줄 밖이다. 여기는 **합성**만.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .review_gen import commercial_chat
from .signals import read_signals, signals_path

ARCHIVE_FILENAME = "_signals.archive.jsonl"
ANTI_PATTERNS_FILENAME = "_anti_patterns.md"
RECIPE_MIN_SIGNALS = 5          # 원전 config 기본값 (하한 2)
ARCHIVE_KEEP_DAYS = 28


def recipes_dir(paths) -> Path:
    return signals_path(paths).parent


def archive_path(paths) -> Path:
    return recipes_dir(paths) / ARCHIVE_FILENAME


def _slugify(name: str) -> str:
    """레시피 이름을 안전한 파일명으로 변환."""
    s = re.sub(r'[\\/:*?"<>|\s]+', '_', (name or "").strip())
    s = re.sub(r'_+', '_', s).strip('_')
    return s[:64] or "recipe"


# ─────────────────────────────────────────
# 클러스터링 (LLM 1회)
# ─────────────────────────────────────────

def _cluster_signals(signals: list, *, chat=None, logf=None) -> list:
    """LLM 에 신호 목록을 주고 의도별로 클러스터링. (원전 글자대로)"""
    log = logf or (lambda m: None)
    if not signals:
        return []

    # 신호 1건이면 단독 클러스터로 처리 (LLM 생략)
    if len(signals) == 1:
        s = signals[0]
        return [{
            "recipe_name": _slugify(s.get("intent", "recipe")),
            "intent": s.get("intent", ""),
            "signal_indices": [0],
            "tags": [],
        }]

    summary_lines = []
    for i, s in enumerate(signals):
        files_preview = ", ".join((s.get("files_read") or [])[:3])
        queries_preview = ", ".join((s.get("queries") or [])[:3])
        iters = s.get("iterations", 1)
        rej = len(s.get("rejected_approaches") or [])
        fb = "Y" if (s.get("feedback_notes") or "").strip() else "N"
        summary_lines.append(
            f"[{i}] intent='{s.get('intent', '')}' "
            f"iter={iters} feedback={fb} rejected={rej} "
            f"queries=[{queries_preview}] files=[{files_preview}]"
        )
    summary = "\n".join(summary_lines)

    prompt = f"""Below is a list of code-writer agent work signals.
Cluster signals with similar intent. For each cluster assign:
- recipe_name: ASCII identifier, PascalCase, no spaces (e.g. "MissionTaskAdd", "AbilityRegister")
- intent: one English sentence describing the cluster
- tags: 2-5 keywords identifying the domain (e.g. ["Mission", "BTTask", "Combat"])

Signal list:
{summary}

Rules:
- Singleton clusters are allowed but only synthesized if they meet the threshold downstream.
- Output ENGLISH for recipe_name, intent, tags. Source intent may be Korean; summarize in English.
- BRACKET CONVENTION: tokens enclosed in [square brackets] in source intents are code identifiers
  (class names, UE features). Preserve them VERBATIM — do not translate, rename, or strip the brackets.

Output ONLY the JSON array below. No prose, no code fences.

[
  {{"recipe_name": "...", "intent": "...", "signal_indices": [0, 1, 2], "tags": ["Tag1", "Tag2"]}}
]
"""
    try:
        resp = (chat or commercial_chat)(prompt)
    except Exception as e:                                   # noqa: BLE001
        log(f"[레시피] 클러스터링 LLM 실패: {e}")
        return []
    if not resp:
        log("[레시피] 클러스터링 LLM 응답 없음")
        return []

    m = re.search(r'\[.*\]', resp, re.DOTALL)
    if not m:
        log("[레시피] 클러스터링 응답에서 JSON 배열 추출 실패")
        return []

    try:
        clusters = json.loads(m.group(0))
    except Exception as e:                                   # noqa: BLE001
        log(f"[레시피] 클러스터링 JSON 파싱 실패: {e}")
        return []

    if not isinstance(clusters, list):
        return []

    out = []
    for c in clusters:
        if not isinstance(c, dict):
            continue
        indices = c.get("signal_indices") or []
        if not isinstance(indices, list):
            continue
        indices = [i for i in indices if isinstance(i, int) and 0 <= i < len(signals)]
        if not indices:
            continue
        out.append({
            "recipe_name": _slugify(c.get("recipe_name") or c.get("intent") or "recipe"),
            "intent": str(c.get("intent") or ""),
            "signal_indices": indices,
            "tags": [str(t) for t in (c.get("tags") or []) if t],
        })
    return out


# ─────────────────────────────────────────
# 레시피 1개 합성
# ─────────────────────────────────────────

def _synthesize_one(paths, cluster: dict, signals: list,
                    max_source_bytes: int = 30_000, *, chat=None, logf=None) -> bool:
    """클러스터 1개에서 레시피 MD를 생성/갱신. 성공 시 True."""
    log = logf or (lambda m: None)
    cluster_signals = [signals[i] for i in cluster["signal_indices"]]
    if not cluster_signals:
        return False

    # 참조 파일 수집 (등장 빈도 정렬)
    file_freq: dict = {}
    for s in cluster_signals:
        for p in s.get("files_read", []):
            if not p:
                continue
            file_freq[p] = file_freq.get(p, 0) + 1
    sorted_files = sorted(file_freq.items(), key=lambda x: -x[1])

    # 헤더 우선, 총 max_source_bytes 까지만 발췌
    source_chunks: list = []
    used_bytes = 0
    used_files: list = []
    repo = Path(getattr(paths, "repo", paths.root))

    def _read_files(only_header: bool):
        nonlocal used_bytes
        for fpath, _ in sorted_files:
            if fpath in used_files:
                continue
            try:
                full = Path(fpath)
                if not full.is_absolute():
                    full = repo / fpath
                if not full.exists():
                    continue
                is_header = full.suffix.lower() in {".h", ".hpp", ".inl"}
                if only_header and not is_header:
                    continue
                content = full.read_text(encoding="utf-8", errors="replace")
                chunk_limit = 4000 if is_header else 2500
                content = content[:chunk_limit]
                chunk = f"\n=== {fpath} ===\n{content}\n"
                if used_bytes + len(chunk) > max_source_bytes:
                    return
                source_chunks.append(chunk)
                used_bytes += len(chunk)
                used_files.append(fpath)
            except Exception:                                # noqa: BLE001
                continue

    _read_files(only_header=True)
    _read_files(only_header=False)

    # 신호 요약 — intent + feedback_notes + rejected_approaches 모두 주입
    sig_summary_lines = []
    for idx, s in enumerate(cluster_signals):
        mods_list = s.get("files_modified") or []
        mod_paths = []
        for m in mods_list[:3]:
            if isinstance(m, dict):
                p = m.get("path", "")
                if p:
                    mod_paths.append(p)
        mods = ", ".join(mod_paths)

        block = [f"### Signal {idx + 1}"]
        block.append(f"- intent: {s.get('intent', '')}")
        block.append(f"- iterations: {s.get('iterations', 1)}")
        block.append(f"- modified: [{mods}]")
        fb = (s.get("feedback_notes") or "").strip()
        if fb:
            block.append(f"- feedback_notes: {fb}")
        rej = s.get("rejected_approaches") or []
        if rej:
            block.append("- rejected_approaches:")
            for r in rej:
                if isinstance(r, dict):
                    a = r.get("approach", "")
                    why = r.get("reason", "")
                    block.append(f"  * tried: {a} | rejected because: {why}")
        errs = s.get("error_recoveries") or []
        if errs:
            block.append("- error_recoveries (build/crash/behavioral):")
            for r in errs:
                if isinstance(r, dict):
                    err = r.get("error", "")
                    fix = r.get("fix", "")
                    block.append(f"  * symptom: {err} | recovery: {fix}")
        sig_summary_lines.append("\n".join(block))
    sig_summary = "\n\n".join(sig_summary_lines)

    prompt = f"""You are a senior engineer who distills repeated coding patterns into terse, reusable recipes.
The same coding intent was performed {len(cluster_signals)} times. Write a recipe so the next worker can follow it quickly.

Output language: ENGLISH (this content is consumed by an LLM as context — English saves tokens).
Style: imperative, concise, no marketing fluff. Bullet over prose.

BRACKET CONVENTION (CRITICAL):
- Tokens enclosed in [square brackets] in the source signals are code identifiers
  (class names, UE macros, function names). Preserve them VERBATIM in your output.
- Do NOT translate, rename, paraphrase, or strip the brackets.
- Example: source "미션 매니저[Manager_Mission]에서 [UMissionTaskExecutor]를 생성"
  → recipe "Spawn [UMissionTaskExecutor] from [Manager_Mission]"

Recipe name: {cluster['recipe_name']}
Representative intent: {cluster['intent']}

Observed signals (with feedback and rejected approaches):
{sig_summary}

Source excerpts (partial):
{''.join(source_chunks) if source_chunks else '(no source collected)'}

Output ONLY the Markdown body below. No frontmatter, no code fences.

## Intent
(1-2 sentences: what this change does and which system it touches)

## Steps
1. (concrete action — which file, which class/function to add or modify)
2. ...
3. ...

## Files of Interest
- path/to/file.h: role
- path/to/file.cpp: role

## Caveats
(Pitfalls, ordering constraints, hidden dependencies. Surface BOTH negative-learning streams here:
 - From rejected_approaches: "Avoid: <approach> — <reason>"
 - From error_recoveries:    "Watch for: <symptom> — Recovery: <fix>"
 If neither is present, write "None.")
"""

    try:
        resp = (chat or commercial_chat)(prompt)
    except Exception as e:                                   # noqa: BLE001
        log(f"[레시피] '{cluster['recipe_name']}' 합성 LLM 실패: {e}")
        return False
    if not resp:
        log(f"[레시피] '{cluster['recipe_name']}' 합성 LLM 응답 없음")
        return False

    body = resp.strip()
    if body.startswith("```"):
        body = re.sub(r'^```\w*\s*\n', '', body)
        body = re.sub(r'\n```\s*$', '', body).strip()

    last_signal = max(
        (s.get("timestamp", "") for s in cluster_signals if s.get("timestamp")),
        default=datetime.now().isoformat(timespec="seconds")
    )

    rdir = recipes_dir(paths)
    rdir.mkdir(parents=True, exist_ok=True)
    out_path = rdir / f"{cluster['recipe_name']}.md"

    # 기존 누적 신호 수 보존
    prior_signal_count = 0
    if out_path.exists():
        try:
            prev = out_path.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'^signal_count:\s*(\d+)', prev, re.MULTILINE)
            if m:
                prior_signal_count = int(m.group(1))
        except Exception:                                    # noqa: BLE001
            pass
    total_signals = prior_signal_count + len(cluster_signals)

    tags_inline = "[" + ", ".join(str(t) for t in (cluster.get("tags") or [])) + "]"
    intent_safe = (cluster.get("intent") or "").replace("\n", " ").strip()

    frontmatter = (
        f"---\n"
        f"recipe_name: {cluster['recipe_name']}\n"
        f"tags: {tags_inline}\n"
        f"intent: {intent_safe}\n"
        f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"signal_count: {total_signals}\n"
        f"last_signal: {last_signal}\n"
        f"---\n\n"
    )

    out_path.write_text(frontmatter + body + "\n", encoding="utf-8")
    log(f"[레시피] '{cluster['recipe_name']}' 합성 완료 "
        f"(이번 신호 {len(cluster_signals)}건, 누적 {total_signals}건)")
    return True


# ─────────────────────────────────────────
# 신호 아카이빙
# ─────────────────────────────────────────

def _archive_signals(paths, processed_indices: set, signals: list,
                     archive_keep_days: int = ARCHIVE_KEEP_DAYS) -> None:
    """처리된 신호는 _signals.archive.jsonl 로 이동, 미처리는 _signals.jsonl 에 남긴다.
    archive 는 archive_keep_days 초과 항목을 정리한다.
    """
    rdir = recipes_dir(paths)
    sig_path = signals_path(paths)
    arc_path = archive_path(paths)

    if processed_indices:
        rdir.mkdir(parents=True, exist_ok=True)
        with arc_path.open("a", encoding="utf-8") as f:
            for i in sorted(processed_indices):
                f.write(json.dumps(signals[i], ensure_ascii=False) + "\n")

    with sig_path.open("w", encoding="utf-8") as f:
        for i, s in enumerate(signals):
            if i not in processed_indices:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

    if arc_path.exists():
        cutoff = datetime.now() - timedelta(days=archive_keep_days)
        kept_lines: list = []
        for line in arc_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                ts = rec.get("timestamp", "")
                dt = datetime.fromisoformat(ts) if ts else datetime.now()
                if dt >= cutoff:
                    kept_lines.append(line)
            except Exception:                                # noqa: BLE001
                kept_lines.append(line)
        arc_path.write_text(
            ("\n".join(kept_lines) + "\n") if kept_lines else "",
            encoding="utf-8"
        )


# ─────────────────────────────────────────
# 안티패턴 카탈로그 집계 (negative learning)
# ─────────────────────────────────────────
#
# rejected_approaches 는 sparse 하지만 학습 가치가 가장 높은 신호다.
# 활성·아카이브 모든 신호에서 추출해 dedupe 후 _anti_patterns.md 단일 카탈로그로 운영.
# code-writer 가 작업 시작 시 읽어 함정 회피 가이드로 활용.

def _aggregate_anti_patterns(paths, *, chat=None, logf=None) -> int:
    """rejected_approaches + error_recoveries 를 모아 _anti_patterns.md 카탈로그로 집계한다.

    카탈로그는 4섹션: User-Rejected / Build / Crash / Behavioral.
    Returns: 카탈로그의 unique 패턴 수. 작업 없음·실패 시 -1.
    """
    log = logf or (lambda m: None)
    rdir = recipes_dir(paths)
    sig_path = signals_path(paths)
    arc_path = archive_path(paths)

    rejected_entries: list = []
    error_entries: list = []

    for path in (sig_path, arc_path):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:                                # noqa: BLE001
                continue

            parent_intent = rec.get("intent", "")

            for r in (rec.get("rejected_approaches") or []):
                if not isinstance(r, dict):
                    continue
                approach = (r.get("approach") or "").strip()
                reason = (r.get("reason") or "").strip()
                if approach and reason:
                    rejected_entries.append({
                        "approach": approach, "reason": reason,
                        "parent_intent": parent_intent,
                    })

            for r in (rec.get("error_recoveries") or []):
                if not isinstance(r, dict):
                    continue
                err = (r.get("error") or "").strip()
                fix = (r.get("fix") or "").strip()
                if err and fix:
                    error_entries.append({
                        "error": err, "fix": fix,
                        "parent_intent": parent_intent,
                    })

    if not rejected_entries and not error_entries:
        log("[anti-pattern] 누적된 rejected_approaches·error_recoveries 없음 — 카탈로그 갱신 스킵")
        return -1

    # 프롬프트 크기 통제: 각각 가장 최근 100개로 제한 (합계 최대 200)
    if len(rejected_entries) > 100:
        rejected_entries = rejected_entries[-100:]
    if len(error_entries) > 100:
        error_entries = error_entries[-100:]

    rejected_block = "\n".join([
        f"- approach: {e['approach']}\n  reason: {e['reason']}\n  context: {e['parent_intent']}"
        for e in rejected_entries
    ]) or "(none)"

    error_block = "\n".join([
        f"- error: {e['error']}\n  fix: {e['fix']}\n  context: {e['parent_intent']}"
        for e in error_entries
    ]) or "(none)"

    total_entries = len(rejected_entries) + len(error_entries)

    prompt = f"""You are aggregating coding pitfalls into a clean anti-pattern catalog with 4 sections.

You receive TWO input streams:

A) USER-REJECTED APPROACHES — the developer first tried these, but the user pushed back on design grounds:
{rejected_block}

B) ERROR RECOVERIES — the build/runtime/observed behavior pushed back. This includes:
   - Build/linker failures
   - Runtime crashes (assertions, access violations)
   - Intermittent behavioral bugs caught via log-driven investigation (where `error` describes the SYMPTOM and `fix` describes the ROOT CAUSE + change)
{error_block}

Your task:
1. Merge entries describing the same essential pitfall (different wording, same meaning) and count occurrences.
2. For stream B, classify each merged entry as:
   - "Build"      — compile/linker errors
   - "Crash"      — runtime crashes / assertions
   - "Behavioral" — intermittent / observed bad behavior caught via investigation (clue: error describes a behavior not a tool message)
3. For stream A, group by inferred domain tag (Mission, UI, Network, Combat, AI, Data, etc. — infer from context).
4. BRACKET CONVENTION: tokens in [square brackets] are code identifiers. Preserve VERBATIM — do not translate, rename, or strip brackets.
5. Output ENGLISH (LLM-internal consumption). Source entries may be Korean.
6. If a section has no entries, write "_None recorded yet._" under it (do not omit the section).

Output ONLY the Markdown body below. No frontmatter, no code fences.

## User-Rejected Approaches
Group by inferred domain.

### [Domain]
- Avoid: <approach> — <reason>. _(× <count> if > 1; omit count if 1)_

## Build Recoveries
- Watch for: <error sig> — Recovery: <fix>. _(× <count> if > 1)_

## Crash Recoveries
- Watch for: <crash sig> — Recovery: <fix>. _(× <count> if > 1)_

## Behavioral Investigations
- Symptom: <observed behavior> — Found: <root cause + change>. _(× <count> if > 1)_
"""

    try:
        resp = (chat or commercial_chat)(prompt)
    except Exception as e:                                   # noqa: BLE001
        log(f"[anti-pattern] LLM 실패 — 갱신 스킵: {e}")
        return -1
    if not resp:
        log("[anti-pattern] LLM 응답 없음 — 갱신 스킵")
        return -1

    body = resp.strip()
    if body.startswith("```"):
        body = re.sub(r'^```\w*\s*\n', '', body)
        body = re.sub(r'\n```\s*$', '', body).strip()

    # 카탈로그 라인 카운트: Avoid / Watch for / Symptom 셋 다 합산
    unique_count = (
        body.count("Avoid:") + body.count("Watch for:") + body.count("Symptom:")
    )
    if unique_count == 0:
        log("[anti-pattern] LLM 응답에서 카탈로그 라인 추출 실패 — 갱신 스킵")
        return -1

    rdir.mkdir(parents=True, exist_ok=True)
    out_path = rdir / ANTI_PATTERNS_FILENAME
    frontmatter = (
        f"---\n"
        f"type: anti_patterns\n"
        f"last_updated: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"rejected_entries_processed: {len(rejected_entries)}\n"
        f"error_entries_processed: {len(error_entries)}\n"
        f"total_entries_processed: {total_entries}\n"
        f"unique_patterns: {unique_count}\n"
        f"---\n\n"
        f"# Project Anti-Patterns\n\n"
        f"Patterns to avoid — both design (user-rejected) and tool (build/crash/behavioral). "
        f"code-writer reads this at task start to avoid repeating known traps.\n\n"
    )
    out_path.write_text(frontmatter + body + "\n", encoding="utf-8")
    log(f"[anti-pattern] 카탈로그 갱신 — rejected {len(rejected_entries)} + "
        f"error {len(error_entries)} → unique {unique_count}")
    return unique_count


# ─────────────────────────────────────────
# 메인 엔트리
# ─────────────────────────────────────────

def run_recipe_synthesis(paths, *, min_signals: int = RECIPE_MIN_SIGNALS,
                         chat=None, logf=None) -> int:
    """레시피 합성 메인 엔트리. 생성된 레시피 수를 반환.

    합성 후 _aggregate_anti_patterns 도 호출되어 _anti_patterns.md 카탈로그를 갱신한다.
    """
    log = logf or (lambda m: None)
    signals = read_signals(paths)
    if not signals:
        log("[레시피] 누적된 신호 없음 — 스킵")
        # 신호 없어도 아카이브에 rejected_approaches 가 있을 수 있으니 한 번 시도
        try:
            _aggregate_anti_patterns(paths, chat=chat, logf=log)
        except Exception as e:                               # noqa: BLE001
            log(f"[anti-pattern] 집계 오류: {e}")
        return 0

    min_signals = max(2, int(min_signals))
    log(f"[레시피] 신호 {len(signals)}건 분석 시작 (min={min_signals})")

    clusters = _cluster_signals(signals, chat=chat, logf=log)
    if not clusters:
        log("[레시피] 클러스터 결과 없음 — 스킵")
        try:
            _aggregate_anti_patterns(paths, chat=chat, logf=log)
        except Exception as e:                               # noqa: BLE001
            log(f"[anti-pattern] 집계 오류: {e}")
        return 0

    eligible = [c for c in clusters if len(c["signal_indices"]) >= min_signals]
    log(f"[레시피] 클러스터 {len(clusters)}개, 합성 대상 {len(eligible)}개 "
        f"(임계치 미만 {len(clusters) - len(eligible)}개는 다음 사이클까지 대기)")

    created = 0
    processed_indices: set = set()
    for c in eligible:
        ok = _synthesize_one(paths, c, signals, chat=chat, logf=log)
        if ok:
            created += 1
            for i in c["signal_indices"]:
                processed_indices.add(i)

    if processed_indices:
        _archive_signals(paths, processed_indices, signals)
        log(f"[레시피] 처리된 신호 {len(processed_indices)}건 아카이브 이동")
    else:
        log("[레시피] 임계치 도달 클러스터 없음 — 신호 유지")

    # 안티패턴 카탈로그 집계 (레시피 합성과 별개로 rejected_approaches 만 모아 갱신)
    try:
        _aggregate_anti_patterns(paths, chat=chat, logf=log)
    except Exception as e:                                   # noqa: BLE001
        log(f"[anti-pattern] 집계 오류: {e}")

    return created


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="레시피 합성 (#157)")
    ap.add_argument("--min-signals", type=int, default=RECIPE_MIN_SIGNALS)
    args = ap.parse_args(argv)

    from ..context_search.paths import resolve
    n = run_recipe_synthesis(resolve(""), min_signals=args.min_signals, logf=print)
    print(f"레시피 {n}건 생성")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
