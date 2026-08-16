"""태스크 묶기 — [중요] **파일이 갈라지지 않게** 묶는다 (레드마인 #65).

## 왜 묶는가 — 실측

    워커 1대 · 1파일   $0.133   →  파일당 $0.133
    워커 1대 · 4파일   $0.168   →  파일당 $0.042        **3.2배 절감**

4배 많은 일에 비용 1.26배·시간 1.6배다. **호출당 고정비**(캐시 생성 ~16k 토큰 + 세션 셋업)가
지배하기 때문이다(리포트 11 §19). 같은 이유로 워커 2대 병렬은 이 크기에서 **12% 빠르고 90%
비쌌다** — 캐시 생성이 워커별 고정비라 그대로 두 배가 된다.

## [중요] 그런데 클래스를 쪼갠 이유는 따로 있다 — 충돌 방지 (사용자 2026-08-09)

*"클래스 별로 분리하는건 분산 작업시 충돌을 방지하기 위해서인데"*. 그러므로 묶기는 그 목적을
**깨지 않는 선에서만** 해야 한다. 규칙은 개수가 아니라 **파일이다**:

    [중요] 같은 파일에 있는 것들은 **절대 갈라지지 않는다**  ← 갈라지면 두 워커가 같은 파일을 고친다
    여러 파일을 한 워커에 묶는 것은 **행위자를 줄이므로 충돌을 오히려 줄인다**

즉 묶기와 충돌 방지는 상충하지 않는다. 상충하는 것은 *"클래스마다 태스크 하나"* 라는 **수단**
이지 *"충돌을 막는다"* 는 **목적**이 아니다.

## [중요] 헤더와 구현은 한 몸이다 — 그러나 **basename 만 보면 안 된다**

`Foo.h` 와 `Foo.cpp` 는 같이 고쳐진다. 둘을 다른 워커에 주면 선언과 정의가 어긋난 채 각자
push 된다. 그런데 열쇠를 **basename 으로만** 잡으면 반대편 사고가 난다 — 실측 2026-08-10:

    같은 모듈 · 다른 폴더(UE `Public/` ↔ `Private/`)   50건   → **붙여야 한다**
    [중요] 다른 모듈 · 같은 이름                            9건    → **갈라야 한다** (파일 36개)

뒤쪽이 하필 **포팅 원본과 대상**이다(`Project_Alpha/…/Alpha_HexagonTileItem` ↔
`ModularStage/…/Alpha_HexagonTileItem`). 한 단위로 묶으면 워커에게 *"이 둘은 한 몸이니 같이
고쳐라"* 고 말하는 셈인데, 원본은 **읽기 전용**이다(원전 §포팅: *"원천 소스 파일 Edit/Write
절대 금지"*). 그래서 열쇠는 **모듈 + 경로(`Public`/`Private`/`Classes` 제거) + stem** 이다.

[주의] 원전(`AgentTest`)은 **정반대 방향으로 틀렸다** — `analyzer._parse_cpp_header` 가 `.cpp` 를
같은 폴더에서만 찾아 UE 위젯이 *"헤더 전용"* 으로 오판되고 **워커 태스크가 통째로 누락**됐다
(2026-06-07 prod 에서 발견). 우리 stem 방식은 그 50건을 이미 맞히고 있었다 — 고치는 것은
**남은 9건뿐**이지 방식 전체가 아니다.

## 크기는 실측된 점 하나뿐이다

4파일까지만 쟀다(파일당 3.2배 절감). 그 위가 어디서 꺾이는지는 **모른다** — 프롬프트 예산
(발췌 7,000자 · `num_ctx` 8192)과 all-or-nothing 실패 범위가 상한을 만든다. 그래서 기본값을
**4** 로 두고, 늘리려면 재고 나서 늘린다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_SIZE = 4        # [중요] 실측된 유일한 점. 위는 미측정 — 재고 나서 올린다.


@dataclass
class Unit:
    """갈라질 수 없는 최소 단위 — 보통 한 파일(짝인 `.h`/`.cpp` 포함)."""
    key: str                                  # 묶음 판정의 근거 (stem 또는 파일 경로)
    classes: list = field(default_factory=list)
    files: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.key or (self.classes[0] if self.classes else "?")


# UE 모듈은 선언과 구현을 이 폴더들로 가른다 — 열쇠에서 뺀다(위 § 참조).
_UE_SPLIT_DIRS = ("Public", "Private", "Classes")


def _stem(path: str) -> str:
    """`Source/A/Public/Foo.h` → `Source/A/Foo`.

    [중요] **basename 이 아니라 경로다.** `Public`/`Private`/`Classes` 만 빼서 `.h`/`.cpp` 짝은
    붙이고, **다른 디렉토리의 동명 파일은 갈라 놓는다**(실측 9건 = 포팅 원본↔대상).
    """
    p = str(path or "").replace("\\", "/").strip("/")
    if not p:
        return ""
    parts = p.split("/")
    name = parts[-1]
    name = name.rsplit(".", 1)[0] if "." in name else name
    dirs = [d for d in parts[:-1] if d not in _UE_SPLIT_DIRS]
    return "/".join(dirs + [name])


def units(items: list) -> list:
    """`[(클래스, 파일)]` → 갈라질 수 없는 단위들.

    [중요] **파일 stem 으로 묶는다** — `Foo.h`/`Foo.cpp` 는 한 몸이고, 한 파일에 여러 클래스가
    있으면 그 클래스들도 한 몸이다. 여기서 갈라 놓으면 뒤에서 무엇을 해도 충돌이 남는다.
    """
    out: dict = {}
    for cls, path in items:
        cls, path = str(cls or "").strip(), str(path or "").strip()
        if not cls and not path:
            continue
        key = _stem(path) if path else cls
        u = out.setdefault(key, Unit(key=key))
        if cls and cls not in u.classes:
            u.classes.append(cls)
        if path and path not in u.files:
            u.files.append(path)
    return [out[k] for k in sorted(out)]


def pack(units_: list, size: int = DEFAULT_SIZE) -> list:
    """단위들을 묶음으로 채운다. [중요] **단위를 쪼개지 않는다.**

    `size` 는 *단위* 수이지 파일 수가 아니다 — 한 단위가 `.h`+`.cpp` 둘일 수 있다.
    """
    if size < 1:
        raise ValueError(f"size 는 1 이상이어야 한다: {size}")
    return [units_[i:i + size] for i in range(0, len(units_), size)]


def plan(items: list, size: int = DEFAULT_SIZE) -> list:
    """`[(클래스, 파일)]` → 묶음 목록. 각 묶음이 태스크 하나가 된다."""
    return pack(units(items), size)


def check_disjoint(groups: list) -> list:
    """[중요] **불변식 검사** — 한 파일이 두 묶음에 나타나면 두 워커가 같은 파일을 고친다.

    위반 목록을 돌려준다(비어 있으면 안전). 호출자는 **비어 있지 않으면 파견하지 않는다.**
    """
    seen: dict = {}
    bad: list = []
    for i, g in enumerate(groups):
        for u in g:
            for f in u.files:
                if f in seen and seen[f] != i:
                    bad.append(f"{f}: 묶음 {seen[f]} 와 {i} 에 동시에 있다")
                seen[f] = i
    return bad


def summary(groups: list) -> str:
    n_units = sum(len(g) for g in groups)
    n_files = len({f for g in groups for u in g for f in u.files})
    n_cls = len({c for g in groups for u in g for c in u.classes})
    s = (f"묶음 {len(groups)} · 단위 {n_units} · 파일 {n_files} · 클래스 {n_cls}")
    bad = check_disjoint(groups)
    return s + (f" · [중요] 파일 중복 {len(bad)}건" if bad else " · [완료] 파일 겹침 없음")
