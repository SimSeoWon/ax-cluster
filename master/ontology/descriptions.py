"""레이어별 책임 서술 — *"이 레이어가 이 도메인에서 무엇을 책임지나"* (소 3.1.4). **LLM 1콜/도메인.**

원본: `watcher/ontology_descriptions.py` 270줄 (Phase η.7.4, 2026-05-31) +
저장기 `ontology_yaml_dump.write_layer_descriptions`.

레이어 분리(η.6/η.7)가 objects·actions·invariants 를 L1/L2/L3 로 **나누기만** 했다. 각
레이어가 무슨 책임을 지는지는 여전히 사람이 멤버 목록을 보고 유추해야 했고, 그 공백을 메우는
칸이다. manifest 의 `summary`·핵심 책임은 **도메인 전체** 단위라 안정도 관점이 빠진다.

⚠️ **우리 `layers.py` 는 이것이 아니다** — 그것은 다른 원본 파일(`ontology_layers.py`, η.6.1)의
이식본이고 **레이어를 추정**한다(LLM 0). 「어느 레이어인가」와 「그 레이어가 무슨 책임인가」는
다른 산출물이다. 마일스톤 4 함정 *"이름이 비슷한 다른 파일을 대응으로 착각한다"* 가 겨눈 자리다.

## 원본이 정한 것 — 그대로 옮긴다

    입력은 **이름과 요약뿐**    .h/.cpp 발췌를 안 읽는다. 서술은 이미 추출된 항목 위의
                                한 단계 위 추상이라 본문 재독 비용이 0 이다
    full rebuild 전용            부분 갱신마다 다시 뽑는 것은 과호출이다 — 서술은 클래스
                                한둘 변경에 둔감하다 (호출자가 게이트)
    stale 축 제외                리비전 워터마크에 참여하지 않는다 (eventually-consistent)
    verified_by_user            사람이 손본 서술은 재초안이 **덮지 않는다**
    🔴 비용 가드                 active 레이어 서술이 **전부 잠겨 있으면 LLM 을 아예 안 부른다**
    🔴 환각 레이어 제거          멤버가 0인 레이어에 LLM 이 서술을 붙이면 **버린다**

## 🔴 우리 쪽에서 다르게 둔 것 셋

**① LLM 호출은 주입한다.** 원본은 `common._call_llm` 을 모듈 전역에서 잡지만, 우리 합성기는
브로커(8102)를 통해 **모델 이름으로 노드를 고른다.** 호출자가 함수를 넘기면 테스트가
네트워크 없이 돈다 — 🔴 이 세션에 `dry_run` 이 LLM 을 안 막는다는 것을 이미 겪었다.

**② 파싱 실패를 값으로 돌려준다** (`Result.reason`). 원본은 `_LOG` 로 흘린다. σ 감사 기준이
*"예외·판정을 값으로 돌려주면 조용하지 않다"* 이고, 이 모듈은 **실패해도 재합성을 죽이지 않는**
자리라 조용해지기 쉽다.

**③ 프롬프트 본문은 원본 그대로다** — 문구를 손보면 같은 입력에 다른 서술이 나와 원본 산출물과
비교할 수 없다(`search_log_analyzer` 의 임계값을 그대로 둔 것과 같은 이유).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..context_search.paths import ProjectPaths
from . import domain_md, package

FILENAME = "description.md"
MAX_MEMBERS_PER_KIND = 25          # 이름만이라 가볍지만 프롬프트 폭발은 막는다 (원본 값)

LAYER_LABELS = {
    1: "L1 (트렁크/계약 — 가장 안정, 도메인의 핵심 추상·인터페이스)",
    2: "L2 (기반 패턴 — 중간 안정, 공통 구현 기반)",
    3: "L3 (구현 리프 — 가장 가변, 구체 구현·말단)",
}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)
_LAYER_KEY_RE = re.compile(r"^L?([123])$", re.I)
_FM_BLOCK_RE = re.compile(r"^---\s*\n.*?\n---\s*\n?", re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->\s*", re.S)

PROMPT_HEADER = """당신은 Unreal Engine 5 프로젝트의 도메인을 DDD 안정도 레이어(L1/L2/L3)별로
"이 레이어가 이 도메인 안에서 무엇을 책임지는가" 를 사람이 읽는 한국어 서술로 정리한다.

레이어 의미 (안정도):
  - L1 트렁크/계약: 가장 안정. 도메인의 핵심 추상·인터페이스·계약. 거의 안 바뀜.
  - L2 기반 패턴: 중간 안정. 공통 구현 기반·재사용 패턴.
  - L3 구현 리프: 가장 가변. 구체 구현·말단 클래스·세부 동작.

== 작성 정신 ==
- 각 레이어 서술은 2~4문장 한국어. 그 레이어 멤버(objects/actions/invariants)가 도메인
  안에서 맡는 책임을 요약. 멤버 이름을 단순 나열 X — 책임·역할 중심으로 종합.
- 도메인 전체 요약(summary)·핵심 책임을 레이어 관점으로 분해하는 것이 목적.
- 멤버가 적거나 한쪽 종류만 있어도 그 레이어의 성격을 설명 (예: L3 에 구현만 몰려 있으면
  "구체 미션 태스크 구현이 이 레이어에 집중").
- 입력에 없는 클래스·기능을 지어내지 말 것. 근거는 주어진 멤버 이름 + 도메인 요약뿐.

== 응답 포맷 (반드시 JSON, 다른 텍스트 금지) ==
입력에 제시된 레이어에 대해서만 키를 채운다 (멤버 없는 레이어는 생략).
{
  "layer_descriptions": {
    "1": "<L1 책임 서술 2~4문장>",
    "2": "<L2 책임 서술>",
    "3": "<L3 책임 서술>"
  }
}
"""


def _pkg(paths: ProjectPaths, domain: str) -> Path:
    return paths.ontology / "domains" / domain


def collect_layer_members(paths: ProjectPaths, domain: str) -> dict:
    """패키지에서 레이어별 **멤버 이름만** 걷는다 (glob stem — 본문을 안 읽는다).

    🔴 **쓰기 직후에 부른다.** `package.write` 가 `L{n}/…/*.yaml` 을 디스크에 올린 상태를
    읽는 함수다(원본도 같은 순서를 계약으로 적어 뒀다).
    """
    root = _pkg(paths, domain)
    out: dict = {}
    for n in (1, 2, 3):
        ldir = root / f"L{n}"
        out[n] = {kind: sorted(p.stem for p in (ldir / kind).glob("*.yaml"))
                  if (ldir / kind).is_dir() else []
                  for kind in package.SUBDIRS}
    return out


def has_content(members: dict) -> bool:
    return any(members.get(k) for k in package.SUBDIRS)


def build_prompt(domain: str, summary: str, responsibilities: list, layer_members: dict) -> str:
    """LLM 1회분 프롬프트. 🔴 **문구는 원본 그대로** (바꾸면 산출물을 비교할 수 없다)."""
    parts = [PROMPT_HEADER, f"== 도메인: {domain} =="]
    if summary:
        parts.append(f"[도메인 요약]\n{summary}")
    if responsibilities:
        parts.append("[핵심 책임]")
        parts += [f"  - {r}" for r in responsibilities]
    parts += ["", "== 레이어별 멤버 (이 멤버들의 책임을 레이어 관점으로 서술) =="]
    for n in (1, 2, 3):
        members = layer_members.get(n) or {}
        if not has_content(members):
            continue
        parts += ["---", LAYER_LABELS[n]]
        for kind in package.SUBDIRS:
            names = members.get(kind) or []
            if names:
                shown = names[:MAX_MEMBERS_PER_KIND]
                more = f" (외 {len(names) - len(shown)}건)" if len(names) > len(shown) else ""
                parts.append(f"  {kind}: {', '.join(shown)}{more}")
    parts += ["", "== JSON 응답 =="]
    return "\n".join(parts)


def parse_response(text: str) -> tuple:
    """LLM 응답 → `({레이어: 서술}, 사유)`. 🔴 **실패 사유를 값으로 돌려준다.**

    키는 `"1"`·`"L1"`·`1` 을 모두 받는다(원본의 관대 정규화).
    """
    if not text:
        return {}, "응답이 비었다"
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        return {}, f"JSON 블록을 못 찾았다 (앞 120자: {text[:120]!r})"
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return {}, f"JSON 파싱 실패: {e}"
    block = data.get("layer_descriptions") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return {}, "`layer_descriptions` 가 없거나 dict 가 아니다"
    out = {}
    for raw_key, raw_val in block.items():
        km = _LAYER_KEY_RE.match(str(raw_key).strip())
        body = str(raw_val or "").strip()
        if km and body:
            out[int(km.group(1))] = body
    return out, "" if out else "레이어 서술이 하나도 없다"


# ── 저장·읽기 (원본 `dump_layer_description` / `read_layer_description`) ──────────

def read(path: Path) -> dict | None:
    """`description.md` → `{body, verified_by_user, layer, created}`. 없으면 `None`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    body = _COMMENT_RE.sub("", _FM_BLOCK_RE.sub("", text, count=1)).strip()
    try:
        layer = int(fm.get("layer")) if fm.get("layer") else None
    except (TypeError, ValueError):
        layer = None
    truthy = lambda v: str(v).strip().lower() in ("true", "1", "yes", "on")   # noqa: E731
    return {"body": body, "layer": layer, "created": fm.get("created", ""),
            "verified_by_user": truthy(fm.get("verified_by_user", "")),
            # 🔴 **우리 표식** — `package.locked_items` 와 같은 규약(둘을 함께 본다).
            # 원본에 없는 이유는 원본엔 "받아온 스냅샷" 이라는 상태가 없어서다.
            "protected": truthy(fm.get("protected", "")),
            "protected_reason": fm.get("protected_reason", "")}


def is_locked(meta) -> bool:
    """재생성이 **대체하면 안 되는** 서술인가. 🔴 뜻이 다른 두 표식을 함께 본다.

        verified_by_user   사람이 검수했다
        protected          받아온 스냅샷이다 — 우리가 같은 품질로 재생산하지 못한다

    `package.py` 가 항목 yaml 에 대해 정확히 같은 판정을 한다. 서술만 다르게 두면 같은
    데이터가 파일 종류에 따라 다르게 취급된다 — 그것이 드리프트의 시작이다.
    """
    return bool(meta) and (meta.get("verified_by_user") or meta.get("protected"))


def dump(domain: str, layer: int, body: str, *, verified: bool = False,
         created: str = "", now=None, protected: str = "") -> str:
    """`description.md` 본문. 🔴 자동 초안은 **언제나 `verified_by_user: false`**.

    `created` 를 받는 이유는 원본과 같다 — 본문을 갱신해도 **최초 생성일을 보존**한다.
    `now` 는 주입 가능하다(원본은 `datetime.now()` 직접 호출 — 그러면 테스트가 시간을 못 고정한다.
    🔴 원본 자신이 `attempt_branch(ts=…)` 에서 같은 이유로 인자를 뒀다).
    """
    created = created or (now or datetime.now()).strftime("%Y-%m-%d")
    return (
        "---\n"
        f"domain: {domain}\n"
        f"layer: {layer}\n"
        f"verified_by_user: {'true' if verified else 'false'}\n"
        + (f"protected: true\nprotected_reason: {protected}\n" if protected else "")
        + f"created: {created}\n"
        "created_by: ontology-descriptions\n"
        "---\n\n"
        "<!-- 자동 생성 초안 (원본 Phase η.7.4). 손보고 verified_by_user: true 로 바꾸면\n"
        "     이후 자동 재초안이 이 파일을 덮지 않는다. false 로 되돌리거나 삭제하면 재생성. -->\n\n"
        + str(body).strip() + "\n")


@dataclass
class WriteStats:
    written: int = 0
    preserved_verified: int = 0      # 🔴 사람이 검수한 것 — 덮지 않았다
    unchanged: int = 0
    removed: int = 0                 # 멤버가 0이 된 레이어의 비검증 서술 (drift 정리)
    layers: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = f"서술 작성 {self.written} · 그대로 {self.unchanged}"
        if self.preserved_verified:
            s += f" · 🔒 검수 보존 {self.preserved_verified}"
        if self.removed:
            s += f" · 정리 {self.removed}"
        return s


def write(paths: ProjectPaths, domain: str, descriptions: dict, *,
          skip_unchanged: bool = True, now=None) -> WriteStats:
    """레이어별 `description.md` 를 쓴다. **검수 잠금은 보존하고, 빈 레이어는 정리한다.**"""
    st = WriteStats()
    root = _pkg(paths, domain)
    for layer in sorted(descriptions or {}):
        body = str(descriptions[layer] or "").strip()
        if not body:
            continue
        path = root / f"L{int(layer)}" / FILENAME
        existing = read(path)
        if is_locked(existing):
            st.preserved_verified += 1
            continue
        if skip_unchanged and existing and existing["body"] == body:
            st.unchanged += 1                     # mtime 을 흔들지 않는다
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dump(domain, int(layer), body,
                             created=(existing or {}).get("created", ""), now=now),
                        encoding="utf-8")
        st.written += 1
        st.layers.append(int(layer))

    # 멤버가 0이 된 레이어의 **비검증** 서술은 지운다 — 근거 없는 서술이 남으면 거짓말이 된다
    members = collect_layer_members(paths, domain)
    for layer in (1, 2, 3):
        if layer in (descriptions or {}):
            continue
        path = root / f"L{layer}" / FILENAME
        if not path.is_file():
            continue
        existing = read(path)
        if is_locked(existing) or has_content(members.get(layer) or {}):
            continue
        try:
            path.unlink()
            st.removed += 1
        except OSError:
            pass
    return st


# ── 진입점 ────────────────────────────────────────────────────────────────────

@dataclass
class Result:
    domain: str
    descriptions: dict = field(default_factory=dict)
    reason: str = ""                 # 🔴 안 뽑은/못 뽑은 이유 — 조용히 비지 않는다
    llm_calls: int = 0
    dropped_layers: list = field(default_factory=list)   # 멤버 0인데 LLM 이 지어낸 것

    @property
    def ok(self) -> bool:
        return bool(self.descriptions)

    @property
    def summary(self) -> str:
        s = f"{self.domain}: 서술 {len(self.descriptions)}개(L{','.join(str(n) for n in sorted(self.descriptions)) or '-'})"
        if self.dropped_layers:
            s += f" · 🔴 환각 레이어 {len(self.dropped_layers)}건 버림"
        if self.reason:
            s += f" · {self.reason}"
        return s


def extract(paths: ProjectPaths, domain: str, *, call) -> Result:
    """도메인 하나의 레이어 책임 서술 — **LLM 최대 1회.**

    `call(prompt) -> str` 을 주입받는다(위 「다르게 둔 것 ①」). 🔴 **비용 가드 둘이 먼저**다:
    멤버 있는 레이어가 0이거나, 그 레이어 서술이 **전부 검수 잠김**이면 LLM 을 안 부른다.
    """
    res = Result(domain=domain)
    layer_members = collect_layer_members(paths, domain)
    active = {n for n, mem in layer_members.items() if has_content(mem)}
    if not active:
        res.reason = "멤버 있는 레이어가 0 — LLM 을 부르지 않는다"
        return res

    root = _pkg(paths, domain)
    if all(is_locked(read(root / f"L{n}" / FILENAME)) for n in sorted(active)):
        res.reason = "🔒 active 레이어 서술이 전부 잠김(검수·보호) — LLM 을 부르지 않는다"
        return res

    doc = domain_md.read(paths, domain)
    summary = (getattr(doc, "summary", "") or "")[:2000] if doc else ""
    responsibilities = list(getattr(doc, "responsibilities", None) or []) if doc else []

    prompt = build_prompt(domain, summary, responsibilities, layer_members)
    try:
        text = call(prompt)
        res.llm_calls = 1
    except Exception as e:                              # noqa: BLE001
        res.reason = f"🔴 LLM 호출 실패 — {type(e).__name__}: {e}"
        return res

    parsed, reason = parse_response(text or "")
    # 🔴 멤버가 0인 레이어에 붙은 서술은 버린다 — 근거가 없다
    res.descriptions = {n: t for n, t in parsed.items() if n in active}
    res.dropped_layers = sorted(set(parsed) - active)
    if not res.descriptions:
        res.reason = reason or "멤버 있는 레이어에 대한 서술이 없다"
    return res


__all__ = ["Result", "WriteStats", "build_prompt", "collect_layer_members", "dump",
           "extract", "has_content", "is_locked", "parse_response", "read", "write"]
