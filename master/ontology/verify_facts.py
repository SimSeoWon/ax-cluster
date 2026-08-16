"""온톨로지 사실 검증 — **결정적 게이트** (소 1.3.3 선행).

`context_synth/verify.py` 가 컨텍스트 MD 에 대해 하는 일을 **온톨로지 산출물**에 대해 한다.
같은 원칙이다: **LLM 에게 자기 검증을 맡기지 않는다**(결정적 게이트 > LLM 판단).

## 왜 필요한가 — actions 는 **관계를 주장**한다

컨텍스트 MD 는 "이 파일이 무엇인가" 를 말한다. 온톨로지 action 은 한 걸음 더 간다:

    "UManager_Mission 이 UMissionTaskExecutor 의 RunTask 를 호출한다"

**없는 호출을 지어내면 트윈이 조용히 거짓이 된다.** 그리고 그건 이 프로젝트의 성격상
가장 나쁜 실패다 — 문서는 지도인데 **틀린 자리로 보내는 지도**가 된다.

[중요] **원본이 이 자리를 위해 `methods` 테이블을 만들었다** — 데이터 스키마 문서가 그 존재
이유를 *"온톨로지 추출의 오탐 교차검증(다른 상속 라인의 동명 메서드 오귀속 방지)"* 이라고
적어 뒀다. 우리는 중 1.1 에서 그 테이블을 6,380건 채웠다. 여기가 그것을 쓰는 자리다.

## [중요] 게이트가 먼저 열려 있어야 한다

`methods` 가 비었을 때 소유권을 물으면 **전부 "없다"** 가 나와, 오탐 교차검증이 오히려
**전수 거짓양성**을 만든다. `class_graph.methods_ready()` 로 먼저 막는다 — 원본이 같은
이유로 같은 게이트를 둔다.

## 무엇을 검사하고 무엇을 봐주나

| 주장 | 검사 |
|---|---|
| object 의 `name` | `classes` 에 실재하는가 |
| object 의 `file` | 그 클래스의 실측 파일과 같은가 |
| action 의 호출 표기 `Class::Method(...)` | `methods`(+조상)에 있는가 |
| action 의 `objects_affected` | 실재하는 클래스인가 |

[중요] **모호하면 봐준다.** 두 가지를 의도적으로 놓친다:

- **엔진 클래스·외부 심볼** — `AActor::Tick` 은 우리 `classes` 에 없지만 실재한다.
  우리 소스에 있는 클래스에 대한 주장만 검사한다
- **괄호 없는 `Class::Member`** — enum 값·UPROPERTY 멤버가 그 형태다(실측 오탐 확인).
  `methods` 에는 함수만 있으므로 멤버를 물으면 당연히 "없다" 가 나온다

**정상 문서를 막는 게이트가 통과시키는 게이트보다 나쁘다** — 문서는 지도이고, 지도를
못 만들면 작업이 멈춘다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..context_search.paths import ProjectPaths
from ..graph import class_graph as cg, db as gdb

# [중요] **호출 형태만 잡는다** — `Class::Method(` 처럼 괄호가 붙은 것.
#
# 실측 2026-08-09: 괄호 없이 `Class::Member` 를 전부 잡았더니 **enum 값과 UPROPERTY 멤버가
# 오탐**으로 걸렸다(`ETopMenuVisibleUIFlag::Flags` · `UMSWidgetEventHUDWidget::SubscribedEventTags`).
# `methods` 테이블에는 **함수만** 있으므로 멤버 변수를 물으면 당연히 "없다" 가 나온다.
#
# 이 프로젝트에서 **정상 문서를 막는 게이트가 통과시키는 게이트보다 나쁘다** — 문서는
# 지도이고, 지도를 못 만들면 작업이 멈춘다. 그래서 **모호하면 봐준다.**
# [중요] **식별자와 `(` 사이 공백을 허용하지 않는다** (실측 2026-08-10).
# C++ 문법으로는 `f (x)` 도 호출이지만, 여기 들어오는 것은 **한국어 산문**이다:
#     target: "FGlobalEventSystem::PrivateHandler (ListenerMap)"
# 이건 호출이 아니라 **주석**인데 `\s*\(` 가 호출로 읽어 `GlobalEventSystem` 의 정상
# 문서 9건을 유령으로 신고했다(`PrivateHandler` 는 소스에서 static TSharedPtr **멤버**다).
# 저장소 원칙 그대로 — *정상 문서를 막는 게이트가 통과시키는 게이트보다 나쁘다.*
_CALL = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\s*(?:::|\.)\s*([A-Za-z_][A-Za-z0-9_]*)\(")


@dataclass
class Finding:
    kind: str            # ghost_class · wrong_file · ghost_method
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.subject} — {self.detail}"


@dataclass
class Report:
    findings: list = field(default_factory=list)
    checked: int = 0
    skipped_reason: str = ""      # 검사를 못 한 이유 (게이트가 닫힘 등)

    @property
    def ok(self) -> bool:
        return not self.findings

    @property
    def reason(self) -> str:
        if self.skipped_reason:
            return f"검사 못 함 — {self.skipped_reason}"
        if not self.findings:
            return f"통과 ({self.checked}건 대조)"
        return " · ".join(str(f) for f in self.findings[:6])


def _known_classes(paths: ProjectPaths) -> dict:
    """`{클래스: 파일}` — 우리 소스에 실재하는 것만."""
    if not gdb.exists(paths):
        return {}
    conn = gdb.connect(paths)
    try:
        return {r["name"]: r["file"] for r in conn.execute("SELECT name, file FROM classes")}
    finally:
        conn.close()


def verify_object(paths: ProjectPaths, obj: dict, known: dict | None = None) -> Report:
    """object yaml 하나. 하위 문서 참조(`kind: domain`)는 **검사 대상이 아니다.**"""
    from . import hierarchy
    r = Report()
    if hierarchy.is_domain_ref(obj):
        return r
    known = _known_classes(paths) if known is None else known
    if not known:
        r.skipped_reason = "클래스 그래프가 비었다 — `python -m master.graph build` 먼저"
        return r
    name = (obj or {}).get("name") or ""
    if not name:
        return r
    r.checked += 1
    if name not in known:
        r.findings.append(Finding("ghost_class", name, "클래스 그래프에 없다"))
        return r
    f = (obj.get("file") or "").replace("\\", "/")
    if f and known[name] and f != known[name]:
        r.findings.append(Finding("wrong_file", name, f"{f} ≠ 실측 {known[name]}"))
    return r


def verify_action(paths: ProjectPaths, action: dict, known: dict | None = None) -> Report:
    """action yaml 하나. **호출 관계를 실측과 대조한다.**

    [중요] `methods` 게이트가 닫혀 있으면 **검사하지 않는다** — 물으면 전부 "없다" 가 나와
    전수 거짓양성이 된다.
    """
    r = Report()
    known = _known_classes(paths) if known is None else known
    if not known:
        r.skipped_reason = "클래스 그래프가 비었다"
        return r
    if not cg.methods_ready(paths):
        r.skipped_reason = "methods 테이블이 비었다 — 물으면 전수 거짓양성이 된다"
        return r

    a = action or {}
    for cls in a.get("objects_affected") or []:
        r.checked += 1
        if isinstance(cls, str) and cls and cls not in known:
            r.findings.append(Finding("ghost_class", cls, "objects_affected 인데 실재하지 않는다"))

    impl = a.get("implementation") or {}
    texts = [str(impl.get("primary") or "")]
    texts += [str(x) for x in (impl.get("related") or [])]
    texts += [str(s.get("target") or "") for s in (a.get("flow") or []) if isinstance(s, dict)]
    for text in texts:
        for cls, method in _CALL.findall(text):
            # [중요] 우리 소스에 있는 클래스에 대한 주장만 검사한다 — 엔진 클래스는 봐준다.
            if cls not in known:
                continue
            r.checked += 1
            if not cg.method_belongs_to_class(paths, cls, method):
                r.findings.append(
                    Finding("ghost_method", f"{cls}::{method}",
                            "그 클래스(및 조상)의 헤더에 그 메서드 선언이 없다"))
    return r


def verify_domain(paths: ProjectPaths, domain: str) -> Report:
    """도메인 패키지 전체. **거부는 보류다** — 사유를 남기고 기존 파일을 지킨다."""
    from . import yaml_io
    root = paths.ontology / "domains" / domain
    man = yaml_io.read(root / "domain.yaml") or {}
    known = _known_classes(paths)
    out = Report()
    for rel in man.get("objects") or []:
        sub = verify_object(paths, yaml_io.read(root / str(rel)) or {}, known)
        out.findings.extend(sub.findings)
        out.checked += sub.checked
        out.skipped_reason = out.skipped_reason or sub.skipped_reason
    for rel in man.get("actions") or []:
        sub = verify_action(paths, yaml_io.read(root / str(rel)) or {}, known)
        out.findings.extend(sub.findings)
        out.checked += sub.checked
        out.skipped_reason = out.skipped_reason or sub.skipped_reason
    return out
