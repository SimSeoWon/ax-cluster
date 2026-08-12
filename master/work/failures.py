"""실패 카탈로그 — 판정 실패를 **다음 생성 프롬프트로 되먹인다** (소 2.3.4).

## 🔴 휴리스틱과 **짝**이지만 반대쪽이다

    소 1.1.6  휴리스틱     사람의 판단   → 다음 골조   🔴 **사람이 답한 것만** 적립
    소 2.3.4  실패 카탈로그 기계의 판정   → 다음 골조   ✅ **기계가 모은다**

원전에는 뒤쪽(`_distribute_failures.md`)만 있었다. 앞쪽이 없으면 *"컴파일은 되지만 구조가
나쁜"* 선택이 영원히 교정되지 않는다(빌드가 통과하니 카탈로그에 안 남는다). 반대로 뒤쪽이
없으면 **같은 컴파일 오류를 매번 다시 낸다.** 둘 다 있어야 고리가 닫힌다.

🔴 **왜 이쪽은 기계가 모아도 되나**: 근거가 **결정적 판정**이기 때문이다 — 컴파일러가 낸 오류
문자열이고, 모델의 의견이 아니다. 휴리스틱에서 자동 적립을 금지한 이유(*"모델이 자기 말을
근거로 같은 선택을 반복한다"*)가 여기엔 적용되지 않는다.

## 🔴 무엇을 적립하나 — **판정 원문에서 뽑은 것만**

    층1  동결 위반 · 휘발 태그 잔재
    층2  상용 모델이 지적한 것
    층3  UE5 빌드 오류 (`error C####: …`) · 테스트 실패

⚠️ **산문 요약을 적립하지 않는다.** *"헤더를 잘못 물었다"* 같은 문장은 다음 프롬프트에서 아무
행동도 바꾸지 못한다. `error C2065: 'None': 선언되지 않은 식별자입니다` 는 바꾼다.

## 🔴 상한과 중복 제거

같은 오류가 열 번 나면 열 줄을 싣는 게 아니라 **한 줄 + 횟수**다. 프롬프트 예산은 선언부·규범이
써야 하고(그쪽이 grounding 의 본체다), 카탈로그가 그걸 밀어내면 손해다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

FILE_NAME = "failure-catalog.json"
BUDGET = 1500            # 프롬프트에 실을 상한 (휴리스틱 3000 보다 작다 — 사람의 결정이 위다)
MAX_ENTRIES = 12
KEEP = 200               # 파일에 남기는 최대 항목 수

# 🔴 컴파일러 오류에서 **판정 부분만** 뽑는다. 파일·줄 번호는 다음 작업에서 달라지므로
#    키에 넣지 않는다 — 넣으면 같은 실수가 매번 새 항목으로 쌓인다.
_MSVC = re.compile(r"\berror\s+(C\d{4})\s*:\s*(.+?)\s*$", re.MULTILINE)
_CLANG = re.compile(r"\berror\s*:\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class Failure:
    """카탈로그 한 줄. `key` 로 중복을 접는다."""

    key: str
    layer: str                      # "층1" · "층2" · "층3"
    detail: str = ""
    count: int = 1
    last: str = ""
    tasks: list = field(default_factory=list)

    def render(self) -> str:
        n = f" ({self.count}회)" if self.count > 1 else ""
        return f"- [{self.layer}] {self.key}{n}" + (f" — {self.detail}" if self.detail else "")


def path_for(paths):
    return paths.root / FILE_NAME


def extract_build_errors(log: str) -> list:
    """빌드 로그에서 **오류 판정만** 뽑는다. 🔴 결정적 — 요약하지 않는다."""
    out: list = []
    for code, msg in _MSVC.findall(log or ""):
        out.append(f"error {code}: {msg.strip()}")
    if not out:
        for msg in _CLANG.findall(log or ""):
            out.append(f"error: {msg.strip()}")
    # 순서를 유지하며 중복 제거 — 같은 오류가 여러 파일에서 나면 한 번만
    seen: set = set()
    uniq: list = []
    for e in out:
        if e not in seen:
            seen.add(e)
            uniq.append(e)
    return uniq


def from_applied(a) -> list:
    """`integrate.Applied` → 카탈로그 항목들. 🔴 **판정 원문에서만** 만든다."""
    items: list = []
    tid = getattr(a, "task_id", "") or ""
    l1 = getattr(a, "l1", None)
    if l1 is not None and not getattr(l1, "ok", True):
        for p in getattr(l1, "problems", [])[:5]:
            # 경로를 떼어 키를 만든다 — 파일마다 새 항목이 되면 카탈로그가 부풀 뿐이다
            key = p.split(": ", 1)[-1]
            items.append(Failure(key=key, layer="층1", tasks=[tid]))
    l2 = getattr(a, "l2", None)
    if l2 is not None and not getattr(l2, "approved", True):
        for f in getattr(l2, "findings", [])[:5]:
            items.append(Failure(key=str(f)[:200], layer="층2", tasks=[tid]))
    b = getattr(a, "build", None)
    if b is not None and not getattr(b, "passed", True):
        errs = extract_build_errors(getattr(b, "tail", "") or "")
        if errs:
            items += [Failure(key=e[:200], layer="층3", tasks=[tid]) for e in errs[:5]]
        else:
            # ⚠️ 오류 문자열을 못 뽑았으면 **그 사실을** 남긴다 — 조용히 빈손으로 끝내지 않는다
            why = getattr(b, "failure", "") or "판정 원문에서 오류를 못 뽑았다"
            items.append(Failure(key=f"빌드 실패(오류 문자열 미추출): {why}"[:200],
                                 layer="층3", tasks=[tid]))
    return items


def load(paths) -> list:
    p = path_for(paths)
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # ⚠️ 못 읽는 카탈로그로 생성을 막지 않는다 — 되먹임은 보조 재료다
        return []
    out: list = []
    for r in raw if isinstance(raw, list) else []:
        out.append(Failure(key=r.get("key", ""), layer=r.get("layer", ""),
                           detail=r.get("detail", ""), count=int(r.get("count") or 1),
                           last=r.get("last", ""), tasks=list(r.get("tasks") or [])))
    return [f for f in out if f.key]


def add(paths, items: list) -> int:
    """항목들을 **접어서** 적립한다. 돌려주는 것은 카탈로그의 총 항목 수."""
    if not items:
        return len(load(paths))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    have = {f.key: f for f in load(paths)}
    for it in items:
        old = have.get(it.key)
        if old is None:
            it.last = now
            have[it.key] = it
            continue
        # 🔴 같은 실수는 한 줄 + 횟수다 (프롬프트 예산을 아낀다)
        old.count += 1
        old.last = now
        for t in it.tasks:
            if t and t not in old.tasks:
                old.tasks.append(t)
    # 최근 것 · 자주 나는 것을 남긴다
    keep = sorted(have.values(), key=lambda f: (f.last, f.count), reverse=True)[:KEEP]
    p = path_for(paths)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps([{"key": f.key, "layer": f.layer, "detail": f.detail,
                                "count": f.count, "last": f.last, "tasks": f.tasks[:8]}
                               for f in keep], ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(p)
    return len(keep)


def render(items: list, *, budget: int = BUDGET, limit: int = MAX_ENTRIES) -> str:
    """골조 프롬프트에 실을 블록. 🔴 **자주 나는 것부터.** 없으면 빈 문자열."""
    if not items:
        return ""
    ranked = sorted(items, key=lambda f: (f.count, f.last), reverse=True)[:limit]
    lines = ["=== PAST FAILURES (measured by deterministic gates, not opinions) ===",
             "These exact errors were produced on earlier attempts in this project. "
             "Do not reproduce them."]
    used = 0
    kept = 0
    for f in ranked:
        line = f.render()
        if used + len(line) > budget:
            break
        lines.append(line)
        used += len(line)
        kept += 1
    if kept < len(items):
        # ⚠️ 자른 것을 말한다 — 조용한 절단은 "다 실었다" 로 읽힌다
        lines.append(f"(외 {len(items) - kept}건 생략 — 자주 난 것부터 실었다)")
    lines.append("=== END PAST FAILURES ===")
    return "\n".join(lines)


def attach(paths, *, budget: int = BUDGET) -> str:
    """파일에서 읽어 바로 프롬프트 블록으로. 실패해도 예외를 내지 않는다."""
    try:
        return render(load(paths), budget=budget)
    except Exception:                                    # noqa: BLE001
        return ""
