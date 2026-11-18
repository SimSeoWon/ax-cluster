"""착수 전 인터뷰의 **분류 문서** 로더 — `#960` T1.

분류 하나 = 문서 하나다(사용자 2026-11-15: 「추후에 이식하는 작업처럼 작업하는 것이 추가될테니
각 상황에 대한 문서를 분리하고 임포트하는 형식으로」 · 「각 문서 머리말에 둬」).

    master/skills/ax-plan/reference/category-<name>.md

    ---
    name: bug                       # 파일 이름의 <name> 과 같아야 한다
    label: 버그 — 원래 되던 동작이 깨졌다   # 분류 질문에 보일 한 줄
    steps: [investigate, specify, reproduce, impact]   # 이 분류에서 진행할 단계
    wayfinder_ask: true             # 선택(기본 false) — 분류 확정 직후 웨이파인더 진행 여부를 묻는다(`#982`)
    ---
    (본문 — LLM 이 읽는 단계별 안내)

[중요] **Python 은 머리말만 본다** — 단계를 열거나 건너뛰는 판단이 코드 분기(「버그면 재현」)로
남지 않게 하려는 것이다. 분류를 더할 때는 문서 하나만 만든다.
[중요] **문서 하나라도 깨지면 전체를 거절한다**(fail-closed) — 깨진 분류가 조용히 빠지면 사용자에게
보일 분류 목록이 말없이 줄어든다.

단계 순서는 이 모듈이 아니라 `master/interview.py` 의 고정 순서가 정한다. `steps` 는 **어떤 단계를
하는지**만 정하고 순서는 바꾸지 못한다. `classify`(분류)는 분류가 정해지기 전 단계라 머리말에 쓰지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "master/skills/ax-plan/reference"
PREFIX = "category-"

# 분류 뒤에 오는 단계 — 고정 순서(사용자 2026-11-15 「각 순서를 고정하고」). classify 는 앞에 늘 있다.
STEPS: tuple[str, ...] = ("investigate", "specify", "reproduce", "impact")
REQUIRED = ("specify",)              # 스펙 없이 스펙 영역을 쓸 수 없다
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class CategoryError(ValueError):
    """분류 문서가 깨졌다 — 전체 거절."""


@dataclass(frozen=True)
class Category:
    name: str
    label: str
    steps: tuple[str, ...]           # STEPS 순서로 정렬된, 이 분류에서 하는 단계
    body: str
    path: Path
    wayfinder_ask: bool = False      # `#982` — 분류 확정 직후 「웨이파인더로 진행할까」를 묻는 분류인가

    def applies(self, step: str) -> bool:
        return step in self.steps

    def as_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "steps": list(self.steps),
                "skipped": [s for s in STEPS if s not in self.steps],
                "wayfinder_ask": self.wayfinder_ask,
                "doc": str(self.path.relative_to(REPO)) if self.path.is_relative_to(REPO) else str(self.path)}


def _parse(path: Path) -> tuple[Category | None, list[str]]:
    rel = path.name
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return None, [f"{rel}: 머리말 없음"]
    try:
        end = text.index("\n---", 3)
        fm = yaml.safe_load(text[4:end])
    except Exception as e:                                   # noqa: BLE001
        return None, [f"{rel}: 머리말 YAML 파싱 실패 — {type(e).__name__}"]
    if not isinstance(fm, dict):
        return None, [f"{rel}: 머리말이 사전이 아니다"]
    bad = []
    name, label, steps = fm.get("name"), fm.get("label"), fm.get("steps")
    want = path.stem[len(PREFIX):]
    if not isinstance(name, str) or not NAME.match(name):
        bad.append(f"{rel}: name 형식 {name!r}")
    elif name != want:
        bad.append(f"{rel}: name {name!r} ≠ 파일 이름 {want!r}")
    if not isinstance(label, str) or not label.strip():
        bad.append(f"{rel}: label 이 비었다")
    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
        bad.append(f"{rel}: steps 는 문자열 목록이어야 한다")
        steps = []
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        bad.append(f"{rel}: 모르는 단계 {unknown} — 쓸 수 있는 것 {list(STEPS)}")
    if len(set(steps)) != len(steps):
        bad.append(f"{rel}: steps 중복")
    missing = [s for s in REQUIRED if s not in steps]
    if missing:
        bad.append(f"{rel}: 필수 단계 빠짐 {missing}")
    ask = fm.get("wayfinder_ask", False)
    if not isinstance(ask, bool):                  # `#982` — "yes"·1 같은 값을 참으로 읽지 않는다
        bad.append(f"{rel}: wayfinder_ask 는 true/false 여야 한다 — {ask!r}")
    extra = sorted(set(fm) - {"name", "label", "steps", "wayfinder_ask"})
    if extra:
        bad.append(f"{rel}: 모르는 머리말 키 {extra}")
    nl = text.find("\n", end + 1)                  # `#969` 14 — 닫는 `---` 뒤 개행이 없으면 본문이 비었다
    body = text[nl + 1:].strip() if nl != -1 else ""
    if not body:
        bad.append(f"{rel}: 본문(단계 안내)이 비었다")
    if bad:
        return None, bad
    ordered = tuple(s for s in STEPS if s in steps)
    return Category(name, label.strip(), ordered, body, path, wayfinder_ask=ask), []


def load(root: Path | None = None) -> dict[str, Category]:
    """분류 문서를 모두 읽는다. 하나라도 깨졌거나 하나도 없으면 `CategoryError`."""
    root = Path(root) if root is not None else ROOT
    files = sorted(root.glob(f"{PREFIX}*.md")) if root.is_dir() else []
    if not files:
        raise CategoryError(f"분류 문서가 없다 — {root}/{PREFIX}<name>.md")
    out: dict[str, Category] = {}
    bad: list[str] = []
    for f in files:
        cat, probs = _parse(f)
        bad += probs
        if cat is not None:
            out[cat.name] = cat
    if bad:
        raise CategoryError("분류 문서 거절 — " + " · ".join(bad))
    return out


def get(name: str, root: Path | None = None) -> Category:
    cats = load(root)
    if name not in cats:
        raise CategoryError(f"모르는 분류 {name!r} — 등록된 분류 {sorted(cats)}")
    return cats[name]
