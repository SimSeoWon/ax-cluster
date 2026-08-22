"""온톨로지 재합성 — 소 1.3.3 의 LLM 부분 (중 1.3 의 마지막 조각).

    도메인 MD(의도) + 소스 발췌(.h/.cpp) + 관계 그래프
          │
          ▼  actions 프롬프트 · invariants 프롬프트 (각 1회)
       LLM (브로커 → 노드)
          │
          ▼  parse — 도메인 밖·근거 없음·신뢰도 미달을 버린다
          ▼  [중요] 사실 게이트 — 호출 관계를 `methods` 6,380건과 대조
          ▼  레이어 배정 (LLM 0)
       package.write — [중요] 검수 잠금 보존

## [중요] 여기서 결정한 것들

**⑴ objects 는 LLM 이 만들지 않는다.** 멤버 목록·파일·레이어는 전부 결정적으로 나온다
(`collect.members_of` + `layers.estimate_domain`). LLM 에게 물으면 있는 답을 지어내게 하는
것이고, 그건 **틀릴 여지만 늘린다.** 기본값은 `objects=None` — 기존 목록을 건드리지 않는다.

**⑵ 노드를 넘어뜨리지 않는다.** `num_ctx` 를 요청에 **반드시** 싣는다. 프롬프트 예산은
`contexts.TOTAL_CHARS` 가 지킨다 — **두 값은 함께 움직인다.**

[주의] **정정 2026-08-15.** 여기 있던 *"안 실으면 모델 기본 `context_length`(256K) 전제로 KV 를
잡아 보드가 멈춘다"* 는 **지금 조건에서 사실이 아니다.** 실측: `num_ctx` 없는 요청을 그 보드
Ollama 가 **`n_ctx = 4096`** 으로 올린다(`n_ctx_train = 262144` 는 모델 메타일 뿐이다).
[중요] **그래도 값을 싣는 이유는 남는다 — 어긋나면 통째로 재적재한다**(실측 **59.6초**:
4096 상주에 8192 요청). 브로커의 상주 복구 경로에 이 값이 빠져 있어서 매번 그 비용이 붙고
있었다(2026-08-15 에 고쳤다).

**⑶ 실패는 예외가 아니라 결과다.** 한 도메인이 죽었다고 배치를 멈추지 않는다. 다만 연속
실패가 임계에 닿으면 **중단한다** — 노드가 죽은 채로 7개를 태울 이유가 없다.

**⑷ 기본이 dry-run 이 아니다. 하지만 `--dry-run` 이 있고, 그것부터 쓴다.**
받아온 온톨로지 247 yaml 은 **스냅샷이자 현재 유일한 데이터**다. 통과율을 모른 채 덮으면
나쁜 문서 7도메인이 되고, 그건 좋은 문서 0개보다 나쁘다 — 컨텍스트 합성에서 이미 배운 것이다.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths
from ..work.generate import DEFAULT_BROKER, GenerateError, call_broker, unload_model
from . import collect, contexts as ctx_mod, domain_md, layers, package, parse, verify_facts, yaml_io

# [중요] **모델 이름이 곧 노드 선택이다.** 브로커(8102)가 모델 보유·상주로 라우팅하므로,
# 서로 다른 모델을 지정하면 서로 다른 기계로 간다 — 그게 2노드 병렬의 수단이다.
HEAVY_MODEL = "hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M"   # BC-250 상주(pinned)
CODER_MODEL = "qwen2.5-coder:14b"                                  # `.2` 상주(pinned)
ALT_MODEL = "gemma3:12b"          # `.2` 보유. [중요] 상주가 아니다 — 아래 함정 참조

# [중요] **기본은 두 노드의 「상주 모델」이다. 다른 모델을 고르면 핀이 깨진다.**
#
# 두 노드 다 `OLLAMA_MAX_LOADED_MODELS=1` 이라, `.2` 에 `gemma3:12b` 를 요청하면 상주하던
# `qwen2.5-coder:14b` 를 **쫓아낸다.** 그러면 브로커의 상주 재확립이 돌아 다시 14b 를
# 올리고(~60초), 다음 조각이 또 gemma 를 부르면 **왕복 스래싱**이 된다.
# 다른 모델로 재려면 그 노드의 핀을 **바꿔서** 재라 — 섞어 쓰지 말 것.
DEFAULT_MODELS = (HEAVY_MODEL, CODER_MODEL)

# [중요] 두 노드 모두 실측 상한이 8192 다 (BC-250 여유 ~2.0GB / 3060 여유 2569 MiB).
# 이 값을 올리려면 **양쪽 노드의 여유를 먼저 재라.**
NUM_CTX = 8192
TIMEOUT = 600
CIRCUIT_THRESHOLD = 3

# [중요] BC-250 은 요청마다 메모리를 쥐고 **안 놓는다.** 재실측 2026-08-15: 8192 상주 상태에서
# 작은 요청 하나에 `available` 이 1211 → 1048 → 989MB 로 **약 60MB씩** 줄었다(옛 기록의
# ~170MB 는 더 큰 프롬프트 기준이다). 그 보드는 모델이 12.3GB 를 먹어 **여유가 138~300MB**
# 뿐이라, 요청 몇 개면 zram 스래싱 → 정지다(실측: 03:04 OOM · 03:11 정지 · 03:22 자체 재부팅).
#
# [중요] **그런데 이 가드는 지금 한 번도 안 돈다** — `n` 이 `_lane` 호출마다 리셋되는데 우리
# 도메인은 레인당 조각이 1~3개다(2026-08-15 실측: 이 세션 35B 요청 ~14회 · 회수 0회).
# [주의] 고치려면 `keep_alive:-1` 상주와의 충돌을 먼저 정해야 한다 — 내리면 다음 요청이 60초
# 재적재다. **재고 나서 정할 일이라 지금은 기록만 한다.**
UNLOAD_EVERY = {HEAVY_MODEL: 5}

# [중요] **상용 CLI 도 레인이 될 수 있다** (사용자 지시 2026-08-09: *"노드 둘 다 클로드도 로그인
# 되어있으니 클로드를 통한 오케스트레이션도 시도해보고"*). 세 대 모두 설치돼 있다 —
# 마스터 2.1.226 · `.2` 2.1.225 · BC-250 2.1.222 (+ 마스터 `agy` 1.1.11).
#
# 층2 가 이미 같은 방식으로 부른다(`layer2_verify.call_agy`/`call_claude`) — **텍스트 in/out
# 이라 §2 의 "마스터는 파일을 만지지 않는다" 와 충돌하지 않는다.** 그래서 그 함수를 그대로 쓴다.
#
# [주의] **모토와의 긴장을 알고 쓴다** — *무료 로컬=대량 생산, 상용=검증만*. 온톨로지 재합성은
# 도메인 7개 × 드물게(stale 일 때만)라 "대량" 이 아니고, 마일스톤이 목표 ①에서 온톨로지를
# *"전자동이 아니라 사용자의 수동 명령과 대화형"* 이라고 못박아 뒀다. 그래도 **기본값은
# 로컬**로 두고, 상용은 명시할 때만 쓴다.
CLI_MODELS = ("claude", "agy")


class SynthError(RuntimeError):
    """재합성을 시작할 수 없다. [중요] 삼키면 빈 결과가 정상처럼 보인다."""


@dataclass
class DomainResult:
    domain: str
    actions: list = field(default_factory=list)
    invariants: list = field(default_factory=list)
    reasons: list = field(default_factory=list)      # 실패·거부 사유
    dropped_facts: list = field(default_factory=list)  # [중요] 사실 게이트가 버린 것
    parse_notes: list = field(default_factory=list)
    written: "package.WriteStats | None" = None
    elapsed_ms: int = 0
    prompt_chars: int = 0
    llm_failed: bool = False
    chunks: int = 0                       # 몇 조각으로 나눠 보냈나
    lanes: dict = field(default_factory=dict)     # 모델(=노드) → 배정된 조각 수
    allowed: set = field(default_factory=set)
    collisions_actions: int = 0           # 조각 간 이름 충돌 (병합에서 하나로)
    collisions_invariants: int = 0
    unloads: int = 0
    partial: bool = False                 # [중요] 변경분만 다시 만들었나 (소 3.2.2)
    invalidation: object = None           # `invalidate.Invalidation` — partial 일 때만
    invalidated: int = 0                  # 실제로 지운 yaml 수 (쓰기 직전)
    settled: int = 0                      # [중요] 워터마크를 올린 오브젝트 수 (stale 이 가라앉는다)
    unreflected: set = field(default_factory=set)   # [중요] 조각이 실패해 **재추출 못 한** 클래스
    descriptions: str = ""                # 레이어 책임 서술 결과 한 줄 (full 일 때만 · 소 3.1.4)

    @property
    def ok(self) -> bool:
        """한 종류라도 건졌나. [중요] **둘 다 0 이면 실패다** — 빈 결과를 성공으로 세지 않는다."""
        return bool(self.actions or self.invariants)

    @property
    def summary(self) -> str:
        s = f"{self.domain}: actions {len(self.actions)} · invariants {len(self.invariants)}"
        if self.partial:
            # 원전 카나리와 같은 항목을 낸다 (`partial=true … invalidated={a,i} preserved={a,i}`)
            iv = self.invalidation
            s += (f" · [진행] partial(변경 {len(getattr(iv, 'objects', ()) or ())} · "
                  f"scope {len(getattr(iv, 'scope_classes', ()) or ())} · "
                  f"무효화 {self.invalidated} · 보존 "
                  f"{getattr(iv, 'preserved_actions', 0) + getattr(iv, 'preserved_invariants', 0)})")
        if self.chunks > 1:
            s += f" · {self.chunks}조각"
            if self.lanes:
                s += "(" + " / ".join(f"{m.split('/')[-1][:14]}×{n}"
                                      for m, n in self.lanes.items()) + ")"
        if self.collisions_actions or self.collisions_invariants:
            s += f" · 조각간 중복 {self.collisions_actions + self.collisions_invariants}"
        if self.settled:
            s += f" · 워터마크 {self.settled}건 갱신"
        if self.unreflected:
            s += (f" · [중요] 미반영 {len(self.unreflected)}클래스"
                  f"({', '.join(sorted(self.unreflected)[:3])}"
                  f"{'…' if len(self.unreflected) > 3 else ''})")
        if self.descriptions:
            s += f" · {self.descriptions}"
        if self.dropped_facts:
            s += f" · [중요] 사실 게이트 {len(self.dropped_facts)}건 버림"
        if self.unloads:
            s += f" · 회수 {self.unloads}회"
        if self.reasons:
            s += " · " + " / ".join(self.reasons[:2])
        return s


@dataclass
class Stats:
    domains: int = 0
    ok: int = 0
    failed: int = 0
    skipped: int = 0            # 판정이 "다시 만들 것 없음" — 실패가 아니다
    partial: int = 0            # 그중 부분 갱신으로 돈 것 (소 3.2.2)
    aborted: str = ""
    elapsed_ms: int = 0
    results: list = field(default_factory=list)
    index_sync: str = ""        # [중요] 재합성이 바꾼 트윈을 검색 색인에 실었나 (소 3.2.4)

    @property
    def summary(self) -> str:
        s = f"도메인 {self.domains} → 성공 {self.ok} · 실패 {self.failed} · {self.elapsed_ms}ms"
        if self.index_sync:
            s += f" · 색인 {self.index_sync}"
        if self.partial:
            s += f" · [진행] 부분 갱신 {self.partial}"
        if self.skipped:
            s += f" · 건너뜀 {self.skipped}"
        if self.aborted:
            s += f" ·  중단({self.aborted})"
        return s


def _layer_map(paths: ProjectPaths, domain: str, members: dict) -> dict:
    """`{클래스: 레이어}` — 결정적 추정 (LLM 0)."""
    parents = {}
    for name in members:
        anc = collect.ancestors(paths, name, depth=1)
        parents[name] = anc[0] if anc else ""
    ests = layers.estimate_domain(parents, files=members, repo=paths.repo)
    return {e.name: (e.layer if e.layer in (1, 2, 3) else 3) for e in ests}


def _assign_layer(item: dict, layer_of: dict) -> None:
    """액션·invariant 의 레이어는 **구현 클래스를 따른다.**

    원본 `ontology_layers.action_layer` 와 같은 취지다. 못 정하면 **L3** — 가장 가변으로
    보수적으로 둔다(`package._layer_of` 와 같은 기본값).
    """
    impl = (item.get("implementation") or {}).get("primary") or ""
    cls = impl.split("::", 1)[0] if "::" in impl else ""
    if not cls:
        for c in item.get("objects_affected") or []:
            if c in layer_of:
                cls = c
                break
    item["layer"] = layer_of.get(cls, 3)


def _fact_gate(paths: ProjectPaths, actions: list) -> tuple:
    """[중요] **결정적 사실 게이트.** 호출 관계가 실측과 어긋난 액션을 버린다.

    `verify_facts` 가 `methods` 테이블(중 1.1 이 채운 6,380건)과 대조한다. 게이트가 닫혀
    있으면(테이블이 비었으면) **검사하지 않고 통과시킨다** — 물으면 전수 거짓양성이 된다.
    """
    kept, dropped = [], []
    known = verify_facts._known_classes(paths)
    for a in actions:
        report = verify_facts.verify_action(paths, a, known)
        if report.skipped_reason:
            kept.append(a)          # 검사 못 함 = 통과. 못 잰 것을 실패로 세지 않는다
            continue
        if report.ok:
            kept.append(a)
        else:
            dropped.append(f"{a.get('name')}: {report.reason}")
    return kept, dropped


def merge_items(batches: list) -> tuple:
    """조각별 결과를 **이름 기준으로** 합친다. 같은 이름이면 신뢰도 높은 쪽을 남긴다.

    [중요] **이건 기계적 병합이지 의미 종합이 아니다.** 두 조각이 같은 흐름의 앞뒤를 각각
    보고 서로 다른 이름을 붙이면 여기서는 **둘 다 남는다.** 사람(또는 대화형 에이전트)이
    합칠 자리이고, 그 한계를 아는 채로 두는 것이 조용히 하나를 버리는 것보다 낫다.
    """
    by_name: dict = {}
    collisions = 0
    for items in batches:
        for item in items:
            name = str(item.get("name") or "")
            if not name:
                continue
            prev = by_name.get(name)
            if prev is None:
                by_name[name] = item
                continue
            collisions += 1
            if float(item.get("confidence") or 0) > float(prev.get("confidence") or 0):
                by_name[name] = item
    return list(by_name.values()), collisions


def generate(prompt: str, model: str, *, broker: str, num_ctx: int, timeout: int,
             caller=None) -> str:
    """한 번의 생성. **모델 이름이 백엔드를 고른다.**

    `claude` / `agy` → 마스터의 상용 CLI (층2 와 같은 호출부 재사용).
    그 밖 → 브로커(8102) → 모델을 보유·상주한 노드.

    [중요] 실패는 `GenerateError` 로 통일한다 — 호출자가 백엔드별 예외를 알 필요가 없다.
    """
    # [중요] `claude:opus` 처럼 **레인 뒤에 모델을 붙일 수 있다.** 골조 생성이 이걸 쓴다 —
    #    골조는 1회 생성이고 모든 병렬 작업의 계약이 되므로 값을 쓸 자리다(소 1.1.1).
    lane, _, sub = model.partition(":")
    if lane in CLI_MODELS:
        from .. import layer2_verify
        if lane == "claude":
            out = layer2_verify.call_claude(prompt, timeout=timeout, model=sub)
        else:
            if sub:
                raise GenerateError(f"agy 는 모델 지정을 받지 않는다: {model}")
            out = layer2_verify.call_agy(prompt, timeout=timeout)
        if out is None:
            raise GenerateError(f"{model} CLI 가 응답하지 않았다 (미설치·타임아웃·비정상 종료)")
        return out
    return call_broker(prompt, model=model, broker=broker, timeout=timeout,
                       num_ctx=num_ctx, caller=caller)


def _lane(chunks: list, model: str, doc, kind: str, *, broker: str, num_ctx: int,
          timeout: int, caller, res: DomainResult) -> list:
    """한 모델(=한 노드)에 배정된 조각들을 **순차로** 처리한다.

    레인당 in-flight 를 1로 유지하는 것이 요점이다 — 같은 노드에 동시에 밀어넣으면
    Ollama 가 직렬화하면서 메모리만 함께 물고 있는다.
    """
    build = prompt_actions if kind == "actions" else prompt_invariants
    read_back = parse.actions if kind == "actions" else parse.invariants
    every = UNLOAD_EVERY.get(model, 0)
    out: list = []
    for n, ctx in enumerate(chunks, 1):
        p = build(doc, ctx)
        res.prompt_chars += len(p)
        try:
            raw = generate(p, model, broker=broker, num_ctx=num_ctx,
                           timeout=timeout, caller=caller)
        except GenerateError as e:
            res.reasons.append(f"{kind}[{ctx.summary}] LLM 실패: {e}")
            res.llm_failed = True
            # [중요] **이 조각의 클래스는 반영되지 않았다.** 기록하지 않으면 settle 이
            # 도메인 전체를 「반영했다」로 찍어 낡은 문서가 정합으로 위장한다
            # (2026-08-15 실측: 노드가 죽어 12개 클래스가 그렇게 위장됐다).
            res.unreflected |= ctx.names
            continue
        try:
            got = (read_back(raw, allowed=res.allowed) if kind == "actions"
                   else read_back(raw))
        except parse.ResponseError as e:
            res.reasons.append(f"{kind}[{ctx.summary}] 응답 거부: {e}")
            res.unreflected |= ctx.names      # 받긴 했지만 쓸 수 없었다 = 미반영
            continue
        res.parse_notes.append(f"{kind} {ctx.summary} → {got.summary}")
        out.append(got.items)
        # [중요] 누적 회수 (위 UNLOAD_EVERY). 실패해도 치명적이지 않다 — 다음 주기에 다시 한다.
        if every and n % every == 0 and caller is None:
            try:
                unload_model(model, broker=broker)
                res.unloads += 1
            except GenerateError:
                pass
    return out


def _manifest_extra(paths: ProjectPaths, domain: str, doc):
    """재합성 때 manifest 에 실을 것. [중요] **MD 의 태그를 `domain.yaml` 로 옮긴다.**

    [주의] **정정 (2026-08-10)**: 앞서 *"7개 중 6개 MD 에 `tags` 가 없다"* 고 적었던 것은
    **awk 로 프론트매터를 잘못 잘라 생긴 오독**이었다. 파서로 재보니 **전부 있고 yaml 과도
    일치**한다(받아온 스냅샷이 양쪽을 맞춰 보냈다).

    [중요] **그래도 이 함수는 필요하다.** 합성기는 `summary` 만 넘기고 있었으므로, 사람이 MD 에
    한글 태그를 넣고 `refresh` 를 돌리면 **그때 사라진다.** 지금까지 어긋나지 않은 것은
    아무도 MD 태그를 손대지 않았기 때문이지 안전해서가 아니다.

    [중요] **합치되 덮지 않는다.** 사람이 `domain.yaml` 에 직접 넣은 태그가 있을 수 있는데
    `package.write` 는 `manifest_extra` 를 **얕게 덮는다**(`man.update`). 그래서 여기서 미리
    union 을 만든다. 순서는 기존 것 먼저 — 사람이 정한 우선순위를 흔들지 않는다.
    """
    extra = {}
    if getattr(doc, "summary", ""):
        extra["summary"] = doc.summary[:2000]
    md_tags = [str(t).strip() for t in (getattr(doc, "tags", None) or []) if str(t).strip()]
    if md_tags:
        cur = yaml_io.read(paths.ontology / "domains" / domain / package.MANIFEST) or {}
        merged = [str(t) for t in (cur.get("tags") or []) if str(t).strip()]
        seen = {t.casefold() for t in merged}
        for t in md_tags:
            if t.casefold() not in seen:
                seen.add(t.casefold())
                merged.append(t)
        extra["tags"] = merged
    return extra or None



def refresh_domain(paths: ProjectPaths, domain: str, *, models: tuple = DEFAULT_MODELS,
                   broker: str = DEFAULT_BROKER, num_ctx: int = NUM_CTX,
                   timeout: int = TIMEOUT, dry_run: bool = False,
                   caller=None, with_objects: bool = False,
                   changed_classes: set | None = None) -> DomainResult:
    """도메인 하나를 재합성한다. **실패는 결과로 돌려준다 — 예외를 던지지 않는다.**

    도메인을 응집 순서로 **조각내어 여러 노드에 나눠 던지고**(사용자 지시 2026-08-09)
    결과를 합친다. `models` 하나면 단일 노드 순차와 같다.

    `changed_classes` 를 주면 **부분 재합성**이다 (소 3.2.2, 원전 η.7.3
    `_refresh_one_domain(changed_classes=set)`): 그 클래스가 언급된 yaml 만 무효화하고
    `scope`(변경 ∪ 응집) 만 다시 뽑아 **나머지는 보존**한다. `None` 이면 통짜(full).
    """
    res = DomainResult(domain=domain)
    t0 = time.monotonic()

    doc = domain_md.read(paths, domain)
    if doc is None:
        res.reasons.append("도메인 MD 가 없다")
        return res

    members = collect.members_of(paths, domain)
    if not members:
        res.reasons.append("멤버가 0 — 재합성할 대상이 없다")
        return res

    scope_members = members
    if changed_classes is not None:
        from . import invalidate
        inval = invalidate.determine_invalidation(paths, domain, set(changed_classes))
        scope = {n: members[n] for n in inval.scope_classes if n in members}
        if not scope:
            # [중요] **판정이 아무것도 못 고르면 full 로 간다.** 부분 갱신이 빈 scope 로 도는
            # 것은 "아무것도 안 하고 성공" 이고, 그것이 낡은 문서를 조용히 남기는 경로다.
            res.reasons.append("partial 불가: scope 가 도메인 멤버와 겹치지 않는다 → full")
        else:
            res.partial = True
            res.invalidation = inval
            scope_members = scope

    chunks = ctx_mod.chunk_domain(paths, domain, members=scope_members)
    chunks = [c for c in chunks if not c.empty]
    if not chunks:
        res.reasons.append("소스 발췌를 하나도 못 만들었다")
        return res
    res.chunks = len(chunks)
    # [중요] `allowed` 는 **도메인 전체 멤버**다. 조각 단위로 좁히면 조각을 가로지르는 액션이
    # 통째로 버려진다 — 우리가 조각낸 것이 원인인데 그 대가를 데이터가 치르게 된다.
    # cross-domain 차단이라는 원래 목적은 도메인 전체 집합으로도 그대로 지켜진다.
    res.allowed = set(members)

    layer_of = _layer_map(paths, domain, members)
    lanes = {m: chunks[i::len(models)] for i, m in enumerate(models)}
    lanes = {m: c for m, c in lanes.items() if c}
    res.lanes = {m: len(c) for m, c in lanes.items()}

    for kind in ("actions", "invariants"):
        with ThreadPoolExecutor(max_workers=len(lanes)) as ex:
            futures = [ex.submit(_lane, cs, m, doc, kind, broker=broker, num_ctx=num_ctx,
                                 timeout=timeout, caller=caller, res=res)
                       for m, cs in lanes.items()]
            batches: list = []
            for f in futures:
                batches.extend(f.result())
        items, collisions = merge_items(batches)
        for item in items:
            _assign_layer(item, layer_of)
        if kind == "actions":
            res.actions, res.collisions_actions = items, collisions
        else:
            res.invariants, res.collisions_invariants = items, collisions

    if res.actions:
        res.actions, res.dropped_facts = _fact_gate(paths, res.actions)

    if not res.ok:
        res.reasons.append("건진 항목이 0")
        res.elapsed_ms = int((time.monotonic() - t0) * 1000)
        return res

    if not dry_run:
        objects = None
        if with_objects:
            objects = [{"name": n, "file": members[n], "layer": layer_of.get(n, 3)}
                       for n in sorted(members)]
        if res.partial:
            res.invalidated = _delete_invalidated(res.invalidation)
        res.written = package.write(
            paths, domain,
            objects=objects,
            actions=res.actions or None,
            invariants=res.invariants or None,
            manifest_extra=_manifest_extra(paths, domain, doc),
            prune=not res.partial,      # [중요] 부분 갱신은 안 들어온 항목을 지우지 않는다
        )
        # [중요] **워터마크를 올린다 — 이것이 없으면 이 도메인은 영원히 stale 이다** (원본
        # η.7.2 제안 2 의 self-settling). [중요] **성공했을 때만** 찍는다: 실패한 재합성이
        # "반영했다" 고 말하면 낡은 문서가 조용히 정합으로 위장한다.
        from . import stale as stale_mod
        # [중요] **미반영 클래스는 settle 하지 않는다** — 그 클래스는 이번 합성이 못 봤다.
        # 찍으면 다음 사이클이 「정합」으로 읽어 **영영 다시 안 본다.**
        covered = set(scope_members if res.partial else members) - res.unreflected
        res.settled = stale_mod.settle(paths, domain, covered)
        # 레이어 책임 서술 (원본 η.7.4) — [중요] **full 전용.** 서술은 클래스 한둘 변경에 둔감해서
        # 부분 갱신마다 다시 뽑는 것은 과호출이다(원본 게이트 그대로). 쓰기 **직후**라
        # `collect_layer_members` 가 방금 쓴 L{n} 멤버를 읽을 수 있다 — 순서가 계약이다.
        if not res.partial:
            res.descriptions = describe_domain(
                paths, domain, model=models[0], broker=broker, num_ctx=num_ctx,
                timeout=timeout, caller=caller)
    res.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return res


def describe_domain(paths: ProjectPaths, domain: str, *, model: str = DEFAULT_MODELS[0],
                    broker: str = DEFAULT_BROKER, num_ctx: int = NUM_CTX,
                    timeout: int = TIMEOUT, caller=None) -> str:
    """레이어 책임 서술을 뽑아 쓴다 (소 3.1.4). 반환은 사람이 읽을 한 줄.

    원본: `ontology_refresh` 의 5번 절 — 추출(`ontology_descriptions`) + 저장
    (`write_layer_descriptions`)이 한 쌍이다.

    [중요] **여기서 실패해도 재합성은 이미 성공했다.** 서술은 그 위에 얹는 요약이므로 예외를
    올려 배치를 죽이지 않고 **값으로 돌려준다**(원본도 try/except 로 감싼다 — 다만 로그로
    흘린다). [주의] 조용해지지 않도록 사유를 문자열에 싣는다.
    """
    from . import descriptions as desc_mod
    try:
        res = desc_mod.extract(paths, domain, call=lambda p: generate(
            p, model, broker=broker, num_ctx=num_ctx, timeout=timeout, caller=caller))
        if not res.ok:
            return res.summary
        return f"{res.summary} · {desc_mod.write(paths, domain, res.descriptions).summary}"
    except Exception as e:                              # noqa: BLE001
        return f"[중요] 서술 실패 — {type(e).__name__}: {e}"


def _delete_invalidated(inval) -> int:
    """무효화된 yaml 을 지운다. **쓰기 직전에만 부른다.**

    [중요] **원전과 다르게 둔 것 — 원전은 추출 *전에* 지운다.** 그러면 LLM 이 통째로 실패했을
    때 대체물 없이 사라진다. 우리 규약은 *"실패는 결과로 돌려준다"* 이고, 받아온 스냅샷은
    **재생산이 안 되는 데이터**다(리포트 11 §20). 성공했을 때의 최종 상태는 원전과 같고,
    실패했을 때만 다르다 — 그쪽이 안전한 방향이다.
    """
    n = 0
    for p in list(getattr(inval, "actions", ()) or ()) + list(getattr(inval, "invariants", ()) or ()):
        try:
            p.unlink()
            n += 1
        except OSError:
            pass          # 이미 없다 = 목표 상태. 지우기 실패로 재합성을 죽이지 않는다
    return n


def prompt_actions(doc, ctx):
    from . import prompt
    return prompt.actions(doc, ctx)


def prompt_invariants(doc, ctx):
    from . import prompt
    return prompt.invariants(doc, ctx)



def run(paths: ProjectPaths, *, domains: list | None = None,
        models: tuple = DEFAULT_MODELS,
        broker: str = DEFAULT_BROKER, num_ctx: int = NUM_CTX, dry_run: bool = False,
        caller=None, progress=None) -> Stats:
    """여러 도메인 재합성. `domains` 를 안 주면 **stale 한 active 도메인만.**

    [중요] 전체를 무조건 다시 만들지 않는다 — 받아온 스냅샷을 이유 없이 덮는 것이 되고,
    `~/CLAUDE.md` 가 컨텍스트 문서에 대해 같은 금지를 못박아 뒀다.
    """
    from . import invalidate, stale
    plans: dict = {}
    if domains is None:
        results = stale.compute(paths)
        domains = [r.domain for r in results if r.stale]
        if not domains:
            # [중요] **「최신이라서 없다」와 「알 수 없어서 없다」를 가른다** (`#275`).
            #    판정 불가가 있는데 *"재합성할 이유가 없다"* 만 말하면 거짓 안심을 준다.
            _unk = sum(r.unknown for r in results)
            raise SynthError(
                "stale 한 도메인이 없다 — 재합성할 이유가 없다. 특정 도메인을 강제하려면 "
                "이름을 명시하라. 빈 배치를 성공으로 보고하지 않는다"
                + (f"\n[중요] 다만 **판정 불가 {_unk}건**이 있다 — 「최신」이 아니라 "
                   f"「알 수 없음」이다(`source_commit` 부재, #275). 그 문서들은 소스가 바뀌어 "
                   f"재합성될 때 비로소 스탬프를 얻는다." if _unk else ""))
        # [중요] **stale walk 만 부분 갱신 대상이다** (원전 배선 그대로). 사람이 도메인을
        # 명시한 것은 *"이 도메인을 다시 만들어라"* 라는 뜻이므로 언제나 full 이다 —
        # 원전도 `force_all`/`force_domains` 를 None(full) 으로 넘긴다.
        plans = {d: invalidate.plan_domain_refresh(paths, d) for d in domains}
    st = Stats(domains=len(domains))
    t0 = time.monotonic()
    consecutive = 0
    for i, d in enumerate(domains, 1):
        plan = plans.get(d)
        if plan is not None and not plan.full and not plan.changed:
            # 판정은 partial 인데 변경이 0 — 태울 이유가 없다. **건너뛴 것을 결과로 남긴다.**
            r = DomainResult(domain=d, reasons=[plan.reason])
            st.results.append(r)
            st.skipped += 1
            if progress:
                progress(f"  {i}/{len(domains)} ⏭ {plan.summary}")
            continue
        if progress and plan is not None:
            progress(f"  {i}/{len(domains)} {plan.summary}")
        r = refresh_domain(paths, d, models=models, broker=broker, num_ctx=num_ctx,
                           dry_run=dry_run, caller=caller,
                           changed_classes=(plan.changed if plan and not plan.full else None))
        st.results.append(r)
        if r.partial:
            st.partial += 1
        if r.ok:
            st.ok += 1
            consecutive = 0
        else:
            st.failed += 1
            consecutive = consecutive + 1 if r.llm_failed else 0
        if progress:
            progress(f"  {i}/{len(domains)} {r.summary}")
        if consecutive >= CIRCUIT_THRESHOLD:
            st.aborted = (f"LLM 연속 실패 {consecutive}회 — 남은 {len(domains) - i} 도메인을 "
                          f"태우지 않는다")
            break
    st.index_sync = sync_index(paths, dry_run=dry_run, wrote=st.ok > 0)
    st.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return st


def sync_index(paths: ProjectPaths, *, dry_run: bool = False, wrote: bool = True) -> str:
    """재합성이 바꾼 트윈을 **검색 색인에 싣는다.** 반환은 사람이 읽을 한 줄.

    원본: `ontology_refresh.run()` 끝의 `ontology_index_sync.try_sync_domain_index`
    (η.2.5 sync 트리거). [중요] **도메인마다가 아니라 배치 끝에 한 번** — 원본 그대로다.

    ## [중요] 이것이 없으면 자란 트윈을 검색이 못 본다

    실측 2026-08-15: `MissionRuntime` 이 actions 12→27 · invariants 10→30 으로 자랐는데
    `domain_index.json`·`bm25_domains.db` 는 **닷새 전(8/10) 것**이었다. 우리 색인을 깨우는
    경로는 둘뿐이었고 **둘 다 이 자리에 없다** — `rebuild_all` 은 **컨텍스트 MD** 변화로만
    깨어나고(색인기 로그: *"재색인 건너뜀(컨텍스트 MD 변화 없음)"*), `staging.commit` 은
    스테이징 세션을 쓸 때만이다. 온톨로지 재합성은 어느 쪽도 아니었다.

    ## 다르게 둔 것 — 지문은 우리 것, 실패는 값으로

    원본 가드는 **프로세스 안의 전역**(`_LAST_FINGERPRINT`)이라 재시작하면 잊는다. 우리
    `domain_index.sync` 는 **디스크에 지문을 남기므로** 그냥 부르면 된다(변화 없으면 스스로
    건너뛴다). 그리고 원본은 예외를 로그로 흘리지만 우리는 **값으로 돌려준다**(σ 감사 기준:
    *"예외를 값으로 돌려주면 조용하지 않다"*) — 색인이 실패해도 **재합성 결과는 이미 디스크에
    있으므로 배치를 죽이지 않는다.**
    """
    if dry_run or not wrote:
        return ""          # [중요] 쓴 것이 없으면 색인할 것도 없다 (빈 호출을 성공으로 세지 않는다)
    from ..context_search import domain_index
    try:
        return domain_index.sync(paths).summary
    except Exception as e:                              # noqa: BLE001
        return f"[중요] 실패 — {type(e).__name__}: {e}"
