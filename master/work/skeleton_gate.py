"""골조 빌드 게이트 — **등재 전에 한 번 세운다** (소 1.1.5).

## 왜 이 칸이 있나 — 원전이 값을 치르고 배운 것

원전 `/distribute` 는 처음에 **Step 6=등재 · Step 7=빌드** 였다. 그 순서에서 빌드가 실패하면
마스터가 working tree 만 고쳤고, **그 fix 가 커밋되지 않은 채** 워커들이 이미 등재된 base 위에서
작업했다. 즉 **깨진 골조가 `origin` 에 박히고 워커 전원이 그 위에서 짰다.** 순서를 뒤집어
`Step 6=빌드 · Step 7=등재` 로 고친 것이 원전의 결론이다.

🔴 **골조는 모든 조각의 base 다.** 조각 하나가 깨지면 그 조각만 다시 하면 되지만, **골조가
깨지면 N개가 전부 헛일**이다. 그래서 여기만은 등재 *전에* 세운다.

## 🔴 통합자가 세운다 (2026-08-11 토폴로지)

빌드는 UE5 가 있는 기계에서만 된다. 우리 구조에서 그것은 **통합자 `.2`** 다 —
`docs/8-git-authority.md` §8.4. 마스터는 골조 **텍스트**를 건네고 판정을 받는다.

    마스터   골조 생성(claude:opus) → 텍스트
       ↓ scp
    통합자   격리된 트리에 골조를 쓰고 → UE5 빌드 → 판정
       ↓
    마스터   통과해야만 등재한다 (실패면 등재하지 않는다)

⚠️ **여기서는 커밋하지 않는다.** 골조는 매니페스트로 워커에게 실려 가므로(`manifest.py`)
git 에 올라가지 않아도 파이프라인이 돈다. durable 에 커밋하는 것은 **소 1.4.3** 의 일이고,
그쪽은 *"검증을 통과한 산출물"* 을 다룬다. 두 관심사를 여기서 섞지 않는다.

## 🔴 fail-closed — 판정을 못 받으면 막는다

`layer3_verify.BuildResult` 의 계약을 그대로 쓴다: **UBT 가 실제로 판정을 낸 것만** 통과다.
SSH 실패·타임아웃·`Result:` 줄 없음은 전부 **차단**이다. *"확인하지 못했다"* 를 *"괜찮다"* 로
바꾸는 순간 이 게이트는 없는 것과 같다.

⚠️ **게이트를 안 붙이는 것과 게이트가 통과하는 것은 다르다.** 호출자가 게이트를 주지 않으면
`register_work` 는 예전처럼 그냥 등재한다 — 그건 *"빌드를 확인하지 않았다"* 이지 통과가
아니다. 결과에 그렇게 적는다.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

from ..layer3_verify import BuildResult, run_build_on_workshop

# 🔴 골조를 세울 때 짓는 것은 **에디터 타깃**이다. 골조엔 본문이 없으므로 게임 타깃까지
# 갈 이유가 없고, UHT(리플렉션 헤더 생성)가 도는 에디터 타깃이 우리가 잡고 싶은 실패
# — `GENERATED_BODY`·`UPROPERTY` 오류 — 를 낸다.
DEFAULT_TARGET_SUFFIX = "Editor"
BUILD_TIMEOUT = 3600


@dataclass
class GateResult:
    """골조 게이트 판정. 🔴 `ok` 가 아니면 **등재하지 않는다.**"""

    stem: str
    checked: bool = False              # 게이트를 실제로 돌렸나 (안 돌린 것 ≠ 통과)
    build: BuildResult | None = None
    placed: list = field(default_factory=list)   # 원격에 쓴 경로
    error: str = ""
    seconds: float | None = None

    @property
    def ok(self) -> bool:
        # 🔴 fail-closed — 돌리지 않았거나 판정이 없으면 통과가 아니다
        return bool(self.checked and self.build is not None and self.build.passed
                    and not self.error)

    @property
    def summary(self) -> str:
        if not self.checked:
            # ⚠️ 이것은 통과가 아니다. 호출자가 구분할 수 있게 말로 적는다.
            return f"{self.stem}: ⚠️ 빌드 미확인 (게이트를 돌리지 않았다)"
        if self.error:
            return f"{self.stem}: 🔴 게이트 실패 — {self.error}"
        b = self.build
        head = "✅" if self.ok else "🔴"
        s = f"{self.stem}: {head} {b.summary() if b else '판정 없음'}"
        if self.placed:
            s += f" · 파일 {len(self.placed)}"
        return s


def target_name(project: str, *, suffix: str = DEFAULT_TARGET_SUFFIX) -> str:
    """`ModularStage` → `ModularStageEditor`. 이미 붙어 있으면 그대로 둔다."""
    p = (project or "").strip()
    if not p:
        raise ValueError("project 가 비었다 — 빌드 타깃을 만들 수 없다")
    return p if p.endswith(suffix) else p + suffix


def _win_join(base: str, rel: str) -> str:
    """윈도우 경로로 잇는다. 🔴 원격이 `cmd` 라 슬래시를 섞으면 조용히 어긋난다."""
    rel = str(rel or "").replace("/", "\\").lstrip("\\")
    return base.rstrip("\\") + "\\" + rel


def place(facts, tree: str, files: dict, *, writer=None) -> list:
    """골조 텍스트를 **격리된 트리**에 쓴다. 🔴 사람·워커의 트리가 아니다.

    `writer(facts, abs_path, text)` 를 주입할 수 있는 이유는 테스트다 — `.2` 없이 배치
    규칙을 검증한다.
    """
    if not tree:
        raise ValueError("격리 트리 경로가 비었다 — 어디에 쓸지 모른다")
    from ..client import bundle as B
    put = writer or (lambda f, p, t: B.write_file(f, p, t))
    out: list = []
    for rel, text in sorted(files.items()):
        abs_path = _win_join(tree, rel) if getattr(facts, "windows", True) \
            else posixpath.join(tree, str(rel).replace("\\", "/"))
        put(facts, abs_path, text)
        out.append(abs_path)
    return out


def run(facts, skeleton, *, tree: str, project: str, uproject: str = "",
        build_bat: str = "", timeout: int = BUILD_TIMEOUT,
        writer=None, builder=None) -> GateResult:
    """골조를 세워 본다. **통과해야만 등재한다.**

    `builder` 를 주입할 수 있는 이유는 테스트다 — 실제 UE5 빌드 없이 계약을 검증한다.
    """
    g = GateResult(stem=getattr(skeleton, "stem", "?"))
    files = getattr(skeleton, "files", None) or {}
    if not files:
        g.error = "골조에 파일이 없다 — 세울 것이 없다"
        return g
    # 🔴 골조가 골조가 아니면 빌드할 이유도 없다 — 싼 검사를 먼저 한다
    if not getattr(skeleton, "ok", False):
        g.error = "골조가 아니다 (`[PSEUDO]` 0 또는 동결 0) — 빌드 전에 막는다"
        return g

    try:
        g.placed = place(facts, tree, files, writer=writer)
    except Exception as e:                                   # noqa: BLE001
        g.error = f"골조 배치 실패: {e}"
        return g

    bb = build_bat or _build_bat_from(facts)
    if not bb:
        # ⚠️ 엔진을 못 찾은 것은 **미확인**이지 통과가 아니다
        g.error = "UE5 Build.bat 을 찾지 못했다 — 확인 불가이므로 막는다"
        return g
    up = uproject or _win_join(tree, f"{project}.uproject")

    g.checked = True
    fn = builder or run_build_on_workshop
    g.build = fn(facts.host, facts.user, bb, target_name(project), up, timeout=timeout)
    g.seconds = getattr(g.build, "seconds", None)
    return g


def _build_bat_from(facts) -> str:
    """`UnrealEditor-Cmd.exe` 경로에서 `Build.bat` 을 유도한다.

    🔴 실측 2026-08-11: 이 기계의 엔진은 `C:\\Program Files\\UE_5.8` 이다 —
    `Epic Games` 하위가 **아니다.** 그래서 경로를 짐작하지 않고 `probe` 가 찾아 둔
    `facts.ue5` 에서 되짚는다.
    """
    ue5 = (getattr(facts, "ue5", "") or "").strip()
    if not ue5:
        return ""
    low = ue5.replace("/", "\\").lower()
    key = "\\engine\\binaries\\win64\\"
    if key not in low:
        return ""
    root = ue5[:low.index(key)]
    return root + r"\Engine\Build\BatchFiles\Build.bat"
