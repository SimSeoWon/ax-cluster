"""태스크 템플릿 레지스트리 — 원전 `ontology_task_manage.py` 288줄 이식 (소 2.2.1 · `#139`).

**재사용 가능한 「작업 유형 템플릿」** 을 도메인 온톨로지처럼 등록·소비한다. 도메인이
*"어떤 개념·클래스가 있다"*(구조 지식)라면, 태스크 템플릿은 *"이런 작업을 어떻게 추가하는가"*
(절차 + 예제 + 규약 + 계약)의 플레이북이다.

[중요] **prescriptive 다 — descriptive 가 아니다.** 원전이 이 자리에서 방향을 한 번 틀었고
(2026-06-07), 사용자 정정 원문이 그 이유다: *"도메인 레지스트하듯 태스크를 등록하고,
분산작업·에이전트가 이걸 TDD처럼 활용해 환각 없길 바라는 거지, **할 때마다 코드 분석해
온톨로지 만드는 게 아니다**."* 그래서 이 모듈은 **LLM·그래프 추론을 하지 않는다** — 받은
스펙을 결정적으로 기록할 뿐이다(우리 `ontology/create.py` 와 같은 규약).

## [중요] 검색 채널 분리 불변식 (원전 그대로)

태스크 템플릿은 도메인 검색 채널(`ontology_domains`/`bm25_domains`)에 **인덱싱하지 않는다.**
이름으로 `list`/`get` 하는 **구조 레지스트리**다. 원전 근거(사용자 지적): 섞으면 도메인
문서와 경합해 **한쪽이 묻힌다.** [주의] 그래서 이 모듈은 색인기를 부르지 않는다 — 부르고 싶어지면
그 불변식을 먼저 다시 읽을 것.

## 저장 위치

    <프로젝트>/ontology/tasks/<TaskType>/task.yaml     ← 도메인 `domains/<D>/domain.yaml` 옆

[중요] **형식은 우리 `yaml_io` 를 쓴다.** 원전도 자기 `_yaml_dump`/`parse_domain_yaml` 을
재사용했다 — 여기서 직렬화를 새로 쓰면 도메인과 **형식이 갈라지고** 왕복이 깨진다.

## `tdd` 플래그가 왜 여기 있나 — 층3 의 전제

원전 ζ Step 3c: 통합 빌드 게이트가 **`tdd:true` 인 템플릿의 `test_spec.filter`** automation
테스트만 실제로 돌린다. 기본이 `false` 인 이유도 사용자 발화에 있다 — *"미션 태스크처럼
'과업 성공→다음 단계' 진행이 가장 기본 원칙인데 이게 흔들리면 사용자는 소프트 프리징 상태"* →
**그런 critical 작업유형만 켠다.** 문서 부재·미선언 = 테스트 안 함.
[주의] 우리 층3(`RunTests`)이 **fail-open + loud warning** 인 것은 이 프로젝트에 자동화 테스트가
0개이기 때문이고, 이 칸이 그 구멍을 메우는 **입구**다.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from . import yaml_io

TASKS_DIR = "tasks"
TASK_FILE = "task.yaml"

# [중요] 이름은 **영문 PascalCase** 다 — 디렉토리·URL 경로·도구 인자에 그대로 박히기 때문이다.
#    한글은 `title` 에 쓴다(원전 규칙 그대로).
_SAFE_RE = re.compile(r'[\\/:*?"<>|\s]+')


def safe_task_type(name: str) -> str:
    return _SAFE_RE.sub("_", (name or "").strip()).strip("_")


def tasks_dir(ontology_root) -> Path:
    return Path(ontology_root) / TASKS_DIR


def task_path(ontology_root, task_type: str) -> Path:
    return tasks_dir(ontology_root) / task_type / TASK_FILE


def _header(data: dict) -> str:
    return (
        f"# Task Template — {data.get('task_type', '?')} ({data.get('title', '')})\n"
        f"# 재사용 작업 유형 플레이북. 사람이 등록하고 워커·에이전트가 소비한다.\n"
        f"# [중요] 검색 인덱싱 안 함 — 이름으로 조회하는 구조 레지스트리(채널 분리 불변식).\n"
        f"\n"
    )


def _ordered(task_type: str, *, title, summary, related_domains, structure, example,
             conventions, contracts, tdd, test_spec, created) -> dict:
    """키 순서를 고정한다 — diff 가 의미를 갖게. (원전 `_ordered_template` 미러)"""
    return {
        "task_type": task_type,
        "title": title or task_type,
        "summary": summary or "",
        "related_domains": list(related_domains or []),
        "structure": list(structure or []),      # [{role, class_pattern, base, note}, …]
        "example": dict(example or {}),          # {instance, refs:[…]}  ← [중요] 참조 경로(코드 stale 회피)
        "conventions": list(conventions or []),  # [str, …]
        "contracts": dict(contracts or {}),      # {preconditions:[], postconditions:[], acceptance:[]}
        # [중요] TDD opt-in — 기본 false. true 일 때만 게이트가 test_spec.filter 를 실제로 돌린다
        "tdd": bool(tdd),
        "test_spec": dict(test_spec or {}),      # {filter:"<Automation 필터>", covers:[계약 참조]}
        "created": created,
    }


def create(ontology_root, task_type: str, *, title: str = "", summary: str = "",
           related_domains=None, structure=None, example=None, conventions=None,
           contracts=None, tdd: bool = False, test_spec=None) -> dict:
    """명시 스펙으로 `task.yaml` 을 만든다. [중요] **추론하지 않는다.**"""
    safe = safe_task_type(task_type)
    if not safe:
        return {"status": "error", "reason": "task_type 이 비었다"}
    if not safe.isascii():
        # [주의] 이름이 디렉토리·URL·도구 인자에 박히므로 여기서 막는다. 한글은 title 로.
        return {"status": "rejected", "task_type": safe,
                "reason": "task_type 에 비ASCII — 영문 PascalCase 가 필요하다 "
                          "(디렉토리·URL·도구 인자 호환). 한글은 title 에 쓴다"}
    path = task_path(ontology_root, safe)
    if path.exists():
        return {"status": "exists", "task_type": safe, "reason": "같은 이름 템플릿이 이미 있다"}

    data = _ordered(safe, title=title, summary=summary, related_domains=related_domains,
                    structure=structure, example=example, conventions=conventions,
                    contracts=contracts, tdd=tdd, test_spec=test_spec,
                    created=datetime.now().strftime("%Y-%m-%d"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_header(data) + yaml_io.dump(data), encoding="utf-8")
    return {"status": "created", "task_type": safe, "path": str(path),
            "structure_roles": len(data["structure"])}


def edit(ontology_root, task_type: str, *, title=None, summary=None, related_domains=None,
         structure=None, example=None, conventions=None, contracts=None,
         tdd=None, test_spec=None) -> dict:
    """[중요] **준 필드만 갱신한다** — 통째 덮어쓰기가 아니다. 안 준 필드는 보존된다."""
    safe = safe_task_type(task_type)
    path = task_path(ontology_root, safe)
    cur = yaml_io.read(path)
    if cur is None:
        return {"status": "not_found", "task_type": safe}
    changed = []
    for key, val in (("title", title), ("summary", summary),
                     ("related_domains", related_domains), ("structure", structure),
                     ("example", example), ("conventions", conventions),
                     ("contracts", contracts), ("tdd", tdd), ("test_spec", test_spec)):
        if val is not None:
            cur[key] = val
            changed.append(key)
    data = _ordered(safe, title=cur.get("title"), summary=cur.get("summary"),
                    related_domains=cur.get("related_domains"), structure=cur.get("structure"),
                    example=cur.get("example"), conventions=cur.get("conventions"),
                    contracts=cur.get("contracts"), tdd=cur.get("tdd"),
                    test_spec=cur.get("test_spec"),
                    created=cur.get("created") or datetime.now().strftime("%Y-%m-%d"))
    path.write_text(_header(data) + yaml_io.dump(data), encoding="utf-8")
    return {"status": "ok", "task_type": safe, "changed": changed}


def listing(ontology_root) -> dict:
    """등록된 템플릿 목록. [중요] **검색이 아니라 디렉토리 스캔이다**(채널 분리 불변식)."""
    root = tasks_dir(ontology_root)
    items = []
    if root.is_dir():
        for pkg in sorted(p for p in root.iterdir() if p.is_dir()):
            data = yaml_io.read(pkg / TASK_FILE) or {}
            items.append({"task_type": pkg.name,
                          "title": data.get("title", ""),
                          "related_domains": data.get("related_domains", []) or [],
                          "tdd": bool(data.get("tdd")),
                          "structure_roles": len(data.get("structure", []) or [])})
    return {"status": "ok", "count": len(items), "templates": items}


def get(ontology_root, task_type: str) -> dict:
    """소비 진입점 — 워커·에이전트의 grounding 이 여기서 온다. 구조 dict + 원문."""
    safe = safe_task_type(task_type)
    path = task_path(ontology_root, safe)
    data = yaml_io.read(path)
    if data is None:
        return {"status": "not_found", "task_type": safe}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raw = ""
    return {"status": "ok", "task_type": safe, "data": data, "raw": raw, "path": str(path)}


def remove(ontology_root, task_type: str) -> dict:
    """템플릿 제거(디렉토리째).

    [주의] 원전은 *"기계 산출물이라 즉시 삭제"* 라고 적었지만 **우리 것은 사람이 등록한 것**이다
    (prescriptive — 합성물이 아니다). 그래도 원전대로 즉시 지운다: 이 저장소의 잠금 규약
    (`verified_by_user`·`protected`)은 **합성이 덮는 것**을 막는 장치이고, 사람이 이름을 대고
    지우는 것은 그 부류가 아니다. [중요] 다만 **되돌릴 수 없으므로 호출자가 확인을 받는다.**
    """
    safe = safe_task_type(task_type)
    pkg = tasks_dir(ontology_root) / safe
    if not pkg.is_dir():
        return {"status": "not_found", "task_type": safe}
    shutil.rmtree(pkg)
    return {"status": "deleted", "task_type": safe}


def collect_test_filters(ontology_root, task_types) -> dict:
    """[중요] **층3 게이트의 입구** — `tdd:true` 인 템플릿의 `test_spec.filter` 만 모은다.

    원전 `executor_helpers.collect_work_test_filters` 의 판정부. 원전 규칙 그대로:

        tdd 가 꺼져 있거나 미선언   → 조용히 건너뛴다 (대부분의 task 가 여기)
        tdd 는 켰는데 filter 가 없다 → [주의] **말한다** — 켜 놓고 안 도는 것이 최악이다

    [주의] 두 번째 줄이 이 함수의 존재 이유다. 원전이 같은 자리에서 *"TDD 도는 줄 알았는데 안 돈"*
    silent gap 을 겪고 카나리 로그를 보강했다(ζ Step 3 오동작 검출).
    """
    filters, warnings, skipped = [], [], []
    for t in task_types or []:
        r = get(ontology_root, t)
        if r.get("status") != "ok":
            warnings.append(f"{t}: 템플릿을 찾을 수 없다")
            continue
        data = r.get("data") or {}
        if not data.get("tdd"):
            skipped.append(t)
            continue
        f = ((data.get("test_spec") or {}).get("filter") or "").strip()
        if not f:
            warnings.append(f"{t}: [중요] tdd=true 인데 test_spec.filter 가 없다 — 켜 놓고 안 돈다")
            continue
        if f not in filters:
            filters.append(f)
    return {"filters": filters, "warnings": warnings, "skipped": skipped}
