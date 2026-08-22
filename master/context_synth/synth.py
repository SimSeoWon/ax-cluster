"""컨텍스트 MD 합성 오케스트레이션 (중 1.2).

원본: `AgentTest/watcher/context.py` 의 `_group_files` · `_process_directory_group` ·
`process_commit` · `initial_context_build`.

[중요] **원본과 갈라지는 지점 넷.**

⑴ **LLM 은 브로커를 거친다.** 원본은 `claude`/`agy` CLI 를 subprocess 로 부른다. 마스터는
   도구 호출을 하지 않는 인프라라(§2) CLI 가 없고, 대신 브로커(8102)가 Ollama 노드를 앞에
   둔다. 그래서 원본의 `task_type` 화이트리스트 라우팅은 **모델 선택**으로 번역된다:
   컨텍스트 합성 = 35B(범용·한국어 산문), 코드 생성 = 14b coder. **두 모델이 서로 다른
   기계에 핀돼 있어 경합하지 않는다** — 원본이 한 PC 에서 쿼터를 나눠 쓰던 문제가 없다.

⑵ **배치 서킷브레이커.** 원본은 호출 단위로 백엔드를 차단했다(Claude 5h·agy 600s). 우리
   실패 모드는 다르다 — 브로커/노드가 죽으면 **남은 전부가 같은 이유로 실패**한다. 연속
   실패가 임계값에 닿으면 배치를 **중단**한다. 1,600번을 태워 0개를 만드는 것을 막는다.
   원본의 결정("한도 소진 시 폴백도 건너뛰고 None — 다른 백엔드로 트래픽 몰리는 과부하
   방지")과 같은 취지다.

⑶ **영구 유실을 카나리로 남긴다.** 원본이 판별 기준을 명확히 적어 뒀다 — *"skip 후 워터마크가
   전진하느냐"*. 예외를 삼키고 정상 리턴해 워터마크가 전진하는 곳만 대상이고, 원본은 그게
   딱 2곳이었다(컨텍스트 MD 유실 / 벡터 색인 누락). 우리 색인기도 워터마크를 전진시키므로
   **그룹 실패는 곧 영구 유실**이다 — `Stats.lost` 로 세고 사유를 들고 나온다.

⑷ **CP949.** 실측 44%(723/1,654)가 CP949 다. `source_text` 를 거쳐 읽는다 — 여기서 mojibake 가
   섞이면 **한글 주석이라는 가장 밀도 높은 신호가 조용히 쓰레기가 된다.**
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .. import source_text
from ..context_search.paths import ProjectPaths
from ..graph import class_graph as cg, dependency as dep, parse as gparse
from ..work.generate import DEFAULT_BROKER, GenerateError, call_broker, unload_model
from . import md as md_mod, prompt as prompt_mod, verify as verify_mod

# 컨텍스트 합성용 모델 — [중요] **Gemma 로 바꿨다** (실측 2026-08-08).
#
# 같은 3그룹에 네 모델을 돌려 **사실 게이트 통과율**로 비교했다:
#
#   Gemma4 E4B   3/3 · 12~32초   ← 채택. 4B급이라 UMA 보드 메모리 압박이 없다
#   Gemma3 12B   3/3 · 16~46초   ← 대안(.2, 전용 VRAM)
#   Qwen 35B     3/3 · ~11초     ← 빠르지만 요청당 ~170MB 누적 (BC-250 정지 사고)
#   Qwen 14b     형식 실패        ← frontmatter 닫는 줄을 빼먹는다(복구 로직으로 구제)
#
# **4B 가 35B 와 같은 통과율**인 것이 요점이다 — 지금 실패 유형은 문장력이 아니라 **지시
# 준수**다. 원본도 로컬 LLM 기본값으로 Gemma 4 E4B 를 골랐고, `context_review` 만 화이트
# 리스트에서 뺐다(*"4B 가 컨텍스트+리뷰 **통합** 프롬프트를 일관되게 처리할지 미검증"*).
# [중요] **우리는 리뷰를 붙이지 않으므로 그 제외 사유가 없다.**
SYNTH_MODEL = "gemma4:e4b"
FALLBACK_MODEL = "gemma3:12b"            # .2 전용 VRAM. E4B 가 얕을 때
HEAVY_MODEL = "hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M"   # 되돌릴 때만
SYNTH_TIMEOUT = 600

# [중요] KV 컨텍스트 상한. **이것이 BC-250 정지 사고의 진짜 원인이었다** — 모델 기본
# `context_length` 가 **262144(256K)** 라, 안 주면 그 전제로 KV 와 컨텍스트 체크포인트를
# 잡는다(실측 `checkpoint 1 of 32 ... 62.813 MiB` → 32개면 ~2.0GB, 보드 여유는 2.2GB).
# [중요] **8192 로 올렸다** (2026-08-08) — 관련 문서 발췌를 400 → 1,500자로 키웠기 때문이다.
# 두 값은 **함께 움직여야 한다**: 발췌만 늘리면 컨텍스트 창을 넘어 뒤가 잘리고, 모델은
# 그 사실을 말하지 않는다(조용히 앞부분만 본다).
#
# 안전한 이유: 합성 모델이 `gemma4:e4b`(4B급)로 바뀌어 KV 가 35B 때보다 훨씬 작다.
# [중요] 그래도 **35B(`HEAVY_MODEL`)로 되돌린다면 이 값을 다시 재라** — 그 조합이 보드를
# 넘어뜨렸다(리포트 10 §8).
SYNTH_NUM_CTX = 8192

# [중요] 몇 그룹마다 모델을 내렸다 올릴지. **`num_ctx` 만으로는 부족하다** — 실측 2026-08-08:
# 요청마다 여유가 935 → 880 → 680 → 447 → 259 MB 로 **단조 감소**한다(요청당 ~170MB).
# 누적 주체는 Ollama 의 프롬프트 캐시·컨텍스트 체크포인트이고, **모델을 내리면 전부
# 회수된다**(실측 266 → 14,445 MB). 그래서 주기적으로 내린다.
#
# [중요] **Gemma4 E4B 로 바꾼 뒤에는 0 이 기본이다** — 4B급이라 누적이 문제되는 규모가 아니고,
# 주기적 내리기는 재적재 비용만 낸다. 35B(`HEAVY_MODEL`)로 되돌린다면 5 로 올릴 것:
# 그때는 적재 후 여유 ~1,200MB / 요청당 ~170MB 라 5회면 ~350MB 가 남는다.
UNLOAD_EVERY = 0

# 연속 실패 임계값. 이보다 이어지면 배치를 중단한다 (위 ⑵).
CIRCUIT_THRESHOLD = 3

HEADER_EXTS = {".h", ".hpp", ".inl"}


class SynthError(RuntimeError):
    """합성을 시작할 수 없다. [중요] 삼키면 빈 결과가 정상처럼 보인다."""


@dataclass
class GroupResult:
    key: str
    files: list[str]
    written: bool = False
    reason: str = ""          # 쓰지 않았다면 왜
    chars: int = 0
    prompt_chars: int = 0
    elapsed_ms: int = 0
    verify: "verify_mod.Report | None" = None
    dry_ok: bool = False      # dry-run 에서 검증까지 통과했나

    @property
    def passed(self) -> bool:
        """문서를 쓸 수 있는 상태였나 (dry-run 포함)."""
        return self.written or self.dry_ok

    @property
    def lost(self) -> bool:
        """[중요] 영구 유실인가 — LLM 실패/게이트 거부로 문서가 안 생겼는가."""
        return not self.passed and self.reason != "변화 없음"


@dataclass
class Stats:
    groups: int = 0
    written: int = 0
    refused: int = 0            # 형식 게이트 거부 (σ.7-B) — 기존 파일 유지
    unfactual: int = 0          # [중요] 사실 게이트 거부 — 소스 실측과 어긋난다
    failed: int = 0             # LLM 실패
    skipped: int = 0            # 이미 있고 안 바뀜
    aborted: str = ""           # 서킷브레이커가 끊었으면 사유
    unloads: int = 0            # 캐시 회수를 위해 모델을 내린 횟수
    elapsed_ms: int = 0
    encodings: source_text.EncodingTally = field(default_factory=source_text.EncodingTally)
    results: list[GroupResult] = field(default_factory=list)

    @property
    def lost(self) -> int:
        """[중요] 문서가 생기지 않은 그룹 수. 이 숫자가 곧 영구 유실이다."""
        return self.refused + self.unfactual + self.failed

    @property
    def pass_rate(self) -> str:
        """사실 게이트 통과율. 모델 적합도의 지표다."""
        tried = self.written + self.refused + self.unfactual + self.failed
        return f"{self.written}/{tried}" if tried else "0/0"

    @property
    def summary(self) -> str:
        s = (f"그룹 {self.groups} → 통과 {self.written}"
             f" · 건너뜀 {self.skipped} · {self.elapsed_ms}ms")
        if self.refused:
            s += f" · [중요] 형식 거부 {self.refused}"
        if self.unfactual:
            s += f" · [중요] 사실 거부 {self.unfactual}"
        if self.failed:
            s += f" · [중요] LLM 실패 {self.failed}"
        if self.unloads:
            s += f" · 모델 회수 {self.unloads}회"
        if self.aborted:
            s += f" ·  중단({self.aborted})"
        return f"{s} · {self.encodings.summary}"


def group(files: list[str]) -> dict[str, list[str]]:
    """소스 파일 → `{부모/stem: [파일…]}`.

    같은 디렉토리의 같은 stem(`.h`/`.cpp` 쌍)이 **한 문서**를 공유한다. 원본과 같은 규칙이고,
    `md.read_source_commit` 이 소스→문서 경로를 되짚을 때도 이 규칙을 쓴다.

    각 그룹 안에서 **헤더를 먼저** 둔다 — 인터페이스를 읽고 구현을 보는 순서다.
    """
    groups: dict[str, list[str]] = {}
    for f in files:
        p = Path(f)
        groups.setdefault(str(p.parent / p.stem), []).append(f)
    for key in groups:
        groups[key].sort(key=lambda f: (0 if Path(f).suffix.lower() in HEADER_EXTS else 1,
                                        Path(f).name))
    return groups


def doc_path(paths: ProjectPaths, key: str) -> Path:
    """그룹 키 → 컨텍스트 MD 경로."""
    return paths.context / f"{key}.md"


def collect_related(paths: ProjectPaths, key: str, files: list[str], existing: str,
                    *, searcher=None) -> list:
    """관련 컨텍스트 문서 3개 (RAG 채널). **원본 `_build_related_context` 그대로.**

    질의는 `파일 stem + 기존 문서 본문 앞 200자` — 기존 문서가 없으면 stem 만으로 돈다.
    **자기 문서는 제외**한다(원본과 같다).
    """
    if searcher is None:
        try:
            from ..context_search.search import open_search
            searcher = open_search(paths.name)
        except Exception:                               # noqa: BLE001
            return []
    stem = Path(files[0]).stem if files else key.rsplit("/", 1)[-1]
    query = stem
    if existing:
        query += " " + md_mod.strip_comments(existing).strip()[:prompt_mod.RELATED_QUERY_BODY]
    self_doc = f"{key}.md"
    out: list = []
    try:
        for hit in searcher.search(query, limit=prompt_mod.RELATED_LIMIT + 1,
                                   excerpt=prompt_mod.RELATED_EXCERPT):
            if hit.file_id == self_doc:
                continue
            # [중요] **요약 절로 한정한다** (사용자 확정 2026-08-08).
            # `hit.excerpt` 는 임베딩 텍스트, 곧 「## 요약」 절이다. 본문 전체를 넣어 봤고
            # (951·762·1500자) 통과했지만 **요약으로 한정하기로 했다** — 원본이 그 절을
            # *"이 섹션만 벡터 임베딩 대상 — 짧고 검색 친화적으로"* 로 설계한 이유가
            # 그대로 여기에도 적용된다: 관련 문서는 **네비게이션 신호**지 읽을 자료가 아니다.
            # 「개선 필요 사항」의 기술 부채 서술까지 넣으면 협력 관계 신호가 희석된다.
            out.append((hit.file_id, (hit.excerpt or "")[:prompt_mod.RELATED_EXCERPT]))
            if len(out) >= prompt_mod.RELATED_LIMIT:
                break
    except Exception:                                   # noqa: BLE001
        return out
    return out


def collect_grounding(paths: ProjectPaths, files: list[str]) -> prompt_mod.Grounding:
    """관계 그래프에서 실측 근거를 모은다. **베스트에포트** — 그래프가 없으면 빈 근거다.

    [중요] 그래프가 없다고 합성을 막지는 않는다. 다만 `Grounding.empty` 가 True 면 호출자가
    그 사실을 통계에 남길 수 있다 — 근거 없이 만든 문서와 있는 문서를 나중에 구분해야 한다.
    """
    g = prompt_mod.Grounding()
    declared: list[str] = []
    for f in files:
        try:
            classes, _ = gparse.parse_file(paths.repo / f)
        except gparse.ParserUnavailable:
            break                      # 파서가 없으면 선언 근거 자체가 없다 — 조용히 비운다
        declared.extend(c["name"] for c in classes)
    g.declared_classes = sorted(dict.fromkeys(declared))
    for c in g.declared_classes[:prompt_mod.GROUNDING_LIMIT]:
        anc = cg.find_ancestors(paths, c, max_depth=3)
        if anc:
            g.ancestors[c] = anc
        sib = cg.find_siblings(paths, c)
        if sib:
            g.siblings[c] = sib
    seen_dep: set[str] = set()
    seen_inc: set[str] = set()
    for f in files:
        seen_dep.update(dep.dependents(paths, f, depth=1))
        seen_inc.update(dep.dependencies(paths, f, depth=1))
    g.dependents = sorted(seen_dep - set(files))
    g.includes = sorted(seen_inc - set(files))
    return g


def synthesize_group(paths: ProjectPaths, key: str, files: list[str], *,
                     commit: str = "", broker: str = DEFAULT_BROKER,
                     model: str = SYNTH_MODEL, caller=None, dry_run: bool = False,
                     content_limit: int = prompt_mod.CONTENT_LIMIT,
                     tally: source_text.EncodingTally | None = None) -> GroupResult:
    """한 그룹 → 컨텍스트 MD 한 개.

    실패는 **예외가 아니라 결과**다 — 한 그룹이 죽었다고 배치를 멈추지 않는다. 대신
    `GroupResult.reason` 에 사유가 남고 `lost` 가 True 가 된다.

    [중요] `dry_run` — 생성·검증만 하고 **디스크에 쓰지 않는다.** 받아온 스냅샷을 건드리지 않고
    모델 적합도(사실 게이트 통과율)를 재려면 이게 필요하다. 통과율을 모른 채 전체를 돌리면
    나쁜 문서 909개가 되고, 그건 좋은 문서 0개보다 나쁘다.
    """
    res = GroupResult(key=key, files=list(files))
    t0 = time.monotonic()

    bodies: dict[str, str] = {}
    for f in files:
        d = source_text.read(paths.repo / f)
        if tally is not None:
            tally.add(d)
        if d is not None:
            bodies[f] = d.text
    if not bodies:
        res.reason = "소스를 읽지 못했다"
        return res

    out = doc_path(paths, key)
    existing = ""
    if out.is_file():
        e = source_text.read(out)
        existing = e.text if e else ""

    grounding = collect_grounding(paths, files)
    grounding.related = collect_related(paths, key, files, existing)
    p = prompt_mod.build(files=files, bodies=bodies, grounding=grounding, existing=existing,
                         limit=content_limit)
    res.prompt_chars = len(p)

    try:
        raw = call_broker(p, model=model, broker=broker, timeout=SYNTH_TIMEOUT,
                          num_ctx=SYNTH_NUM_CTX, caller=caller)
    except GenerateError as e:
        res.reason = f"LLM 실패: {e}"
        return res

    doc, verdict = md_mod.finalize(raw, existing=existing, commit=commit)
    if not verdict.ok:
        # σ.7-B — [중요] 기존 파일을 남긴다. 다음 사이클에 다시 시도된다.
        res.reason = f"형식 게이트 {verdict.summary} · preview={verdict.preview!r}"
        return res

    # [중요] **사실 게이트** — 소스 실측과 대조한다. LLM 에게 자기 검증을 맡기지 않는다
    # (설계 규칙: 결정적 게이트가 LLM 판단보다 우선). 형식 게이트와 같은 처리 —
    # 거부하면 기존 파일이 남고 다음 사이클에 재시도된다.
    report = verify_mod.verify(doc, sources=bodies, declared=grounding.declared_classes)
    res.verify = report
    if not report.ok:
        res.reason = f"사실 게이트 거부 — {report.reason}"
        return res

    res.chars = len(doc)
    if dry_run:
        res.reason = "dry-run — 검증 통과 (쓰지 않았다)"
        res.dry_ok = True
        res.elapsed_ms = int((time.monotonic() - t0) * 1000)
        return res
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    res.written = True
    res.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return res


def run(paths: ProjectPaths, *, changed: list[str] | None = None, commit: str = "",
        skip_existing: bool = False, limit: int = 0, broker: str = DEFAULT_BROKER,
        model: str = SYNTH_MODEL, caller=None, dry_run: bool = False,
        content_limit: int = prompt_mod.CONTENT_LIMIT, unload_every: int = UNLOAD_EVERY,
        git=None, progress=None) -> Stats:
    """배치 합성. `changed` 를 주면 그 파일들만, 없으면 `Source/` 전체.

    `skip_existing` — 이미 문서가 있는 그룹을 건너뛴다(최초 전체 빌드에서 누락분만 보충).
    `limit` — 그룹 수 상한. 0 이면 무제한. [중요] 상한에 걸려 남긴 것은 `Stats.aborted` 에 적는다.
    """
    files = changed if changed is not None else cg.list_source_files(paths, git=git)
    if not files:
        raise SynthError("합성할 소스가 없다 — `Source/` 경계나 변경 목록을 확인하라. "
                         "빈 배치를 성공으로 보고하지 않는다")
    # [중요] **컨텍스트 문서 생성은 `Source/` 한정이다** (§5.2-E, 사용자 재확인 2026-08-22).
    #    `changed=None` 경로는 `list_source_files` 가 경계를 **두 겹**으로 지키는데(pathspec +
    #    접두 검사), `changed` 를 받는 경로에는 검사가 **없었다** — 호출자가 한 번 잘못 넘기면
    #    `Content/`(워킹트리의 93%, uasset 바이너리)가 그대로 합성 대상이 된다.
    #    [주의] 조용히 걸러내지 않고 **거부한다.** 걸러내면 호출자는 그것도 합성된 줄 안다.
    files = [str(f).strip().replace("\\", "/") for f in files]
    outside = [f for f in files if not f.startswith(f"{cg.SOURCE_SUBDIR}/")]
    if outside:
        raise SynthError(
            f"`{cg.SOURCE_SUBDIR}/` 밖의 파일이 합성 목록에 있다 ({len(outside)}건) — "
            f"컨텍스트 문서는 소스 한정이다(§5.2-E): "
            + ", ".join(outside[:5]) + (" ..." if len(outside) > 5 else ""))
    groups = group([f for f in files if (paths.repo / f).is_file()])
    if not groups:
        raise SynthError("살아 있는 소스 파일이 없다 (전부 삭제됐거나 경로가 틀렸다)")

    stats = Stats(groups=len(groups))
    t0 = time.monotonic()
    consecutive = 0
    for i, (key, fs) in enumerate(sorted(groups.items()), 1):
        if limit and stats.written + stats.refused + stats.unfactual + stats.failed >= limit:
            stats.aborted = f"상한 {limit} 도달 — 남은 {len(groups) - i + 1} 그룹 미처리"
            break
        if skip_existing and doc_path(paths, key).is_file():
            stats.skipped += 1
            stats.results.append(GroupResult(key=key, files=fs, reason="변화 없음"))
            continue
        r = synthesize_group(paths, key, fs, commit=commit, broker=broker, model=model,
                             caller=caller, dry_run=dry_run, content_limit=content_limit,
                             tally=stats.encodings)
        stats.results.append(r)
        if r.passed:
            stats.written += 1
            consecutive = 0
        else:
            if r.reason.startswith("LLM 실패"):
                stats.failed += 1
                consecutive += 1
            else:
                # 게이트 거부는 모델 응답이 온 것이라 서킷 차단 사유가 아니다.
                if r.reason.startswith("사실 게이트"):
                    stats.unfactual += 1
                else:
                    stats.refused += 1
                consecutive = 0
            if consecutive >= CIRCUIT_THRESHOLD:
                stats.aborted = (f"LLM 연속 실패 {consecutive}회 — 남은 "
                                 f"{len(groups) - i} 그룹을 태우지 않는다. 마지막 사유: "
                                 f"{r.reason[:120]}")
                break
        if progress:
            progress(f"  {i}/{len(groups)} {key} — {'통과' if r.passed else r.reason[:60]}")
        # [중요] 주기적으로 모델을 내려 누적된 캐시를 회수한다 (위 UNLOAD_EVERY 참조).
        # 다음 요청이 자동으로 다시 적재한다 — 우리가 올릴 필요는 없다.
        done = stats.written + stats.refused + stats.unfactual + stats.failed
        if unload_every and done and done % unload_every == 0 and caller is None:
            try:
                unload_model(model, broker=broker)
                stats.unloads += 1
            except GenerateError:
                pass       # 회수 실패는 치명적이지 않다 — 다음 주기에 다시 시도된다
    stats.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return stats
