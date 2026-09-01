"""골조 빌드 게이트 — **등재 전에 한 번 세운다** (소 1.1.5).

## 왜 이 칸이 있나 — 원전이 값을 치르고 배운 것

원전 `/distribute` 는 처음에 **Step 6=등재 · Step 7=빌드** 였다. 그 순서에서 빌드가 실패하면
마스터가 working tree 만 고쳤고, **그 fix 가 커밋되지 않은 채** 워커들이 이미 등재된 base 위에서
작업했다. 즉 **깨진 골조가 `origin` 에 박히고 워커 전원이 그 위에서 짰다.** 순서를 뒤집어
`Step 6=빌드 · Step 7=등재` 로 고친 것이 원전의 결론이다.

[중요] **골조는 모든 조각의 base 다.** 조각 하나가 깨지면 그 조각만 다시 하면 되지만, **골조가
깨지면 N개가 전부 헛일**이다. 그래서 여기만은 등재 *전에* 세운다.

## [중요] 통합자가 세운다 (2026-08-11 토폴로지)

빌드는 UE5 가 있는 기계에서만 된다. 우리 구조에서 그것은 **통합자 `.2`** 다 —
`docs/8-git-authority.md` §8.4. 마스터는 골조 **텍스트**를 건네고 판정을 받는다.

    마스터   골조 생성(claude:opus) → 텍스트
       ↓ scp
    통합자   격리된 트리에 골조를 쓰고 → UE5 빌드 → 판정
       ↓
    마스터   통과해야만 등재한다 (실패면 등재하지 않는다)

[주의] **여기서는 커밋하지 않는다.** 골조는 매니페스트로 워커에게 실려 가므로(`manifest.py`)
git 에 올라가지 않아도 파이프라인이 돈다. durable 에 커밋하는 것은 **소 1.4.3** 의 일이고,
그쪽은 *"검증을 통과한 산출물"* 을 다룬다. 두 관심사를 여기서 섞지 않는다.

## [중요] fail-closed — 판정을 못 받으면 막는다

`layer3_verify.BuildResult` 의 계약을 그대로 쓴다: **UBT 가 실제로 판정을 낸 것만** 통과다.
SSH 실패·타임아웃·`Result:` 줄 없음은 전부 **차단**이다. *"확인하지 못했다"* 를 *"괜찮다"* 로
바꾸는 순간 이 게이트는 없는 것과 같다.

[주의] **게이트를 안 붙이는 것과 게이트가 통과하는 것은 다르다.** 호출자가 게이트를 주지 않으면
`register_work` 는 예전처럼 그냥 등재한다 — 그건 *"빌드를 확인하지 않았다"* 이지 통과가
아니다. 결과에 그렇게 적는다.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

from ..layer3_verify import BuildResult, run_build_on_workshop

# [중요] 골조를 세울 때 짓는 것은 **에디터 타깃**이다. 골조엔 본문이 없으므로 게임 타깃까지
# 갈 이유가 없고, UHT(리플렉션 헤더 생성)가 도는 에디터 타깃이 우리가 잡고 싶은 실패
# — `GENERATED_BODY`·`UPROPERTY` 오류 — 를 낸다.
DEFAULT_TARGET_SUFFIX = "Editor"
BUILD_TIMEOUT = 3600


@dataclass
class GateResult:
    """골조 게이트 판정. [중요] `ok` 가 아니면 **등재하지 않는다.**"""

    stem: str
    checked: bool = False              # 게이트를 실제로 돌렸나 (안 돌린 것 ≠ 통과)
    build: BuildResult | None = None
    placed: list = field(default_factory=list)   # 원격에 쓴 경로
    error: str = ""
    seconds: float | None = None
    mode: str = ""                     # `#317` 미결 ② — 무엇으로 쟀나 (uht | full)

    @property
    def ok(self) -> bool:
        # [중요] fail-closed — 돌리지 않았거나 판정이 없으면 통과가 아니다
        return bool(self.checked and self.build is not None and self.build.passed
                    and not self.error)

    @property
    def summary(self) -> str:
        if not self.checked:
            # [주의] 이것은 통과가 아니다. 호출자가 구분할 수 있게 말로 적는다.
            return f"{self.stem}: [주의] 빌드 미확인 (게이트를 돌리지 않았다)"
        if self.error:
            return f"{self.stem}: [중요] 게이트 실패 — {self.error}"
        b = self.build
        head = "OK" if self.ok else "FAIL"
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
    """윈도우 경로로 잇는다. [중요] 원격이 `cmd` 라 슬래시를 섞으면 조용히 어긋난다."""
    rel = str(rel or "").replace("/", "\\").lstrip("\\")
    return base.rstrip("\\") + "\\" + rel


# [중요] 리터럴이다 — `skeleton.PERMANENT_TAGS[0]` 과 같은 값이지만 **임포트하지 않는다.**
#    이 모듈은 작업장 배달본에 실리고 `work/skeleton.py` 는 실리지 않는다(배달 가드 테스트가
#    그것을 잰다). 상대 임포트를 넣으면 배달본에서 ImportError 로 죽는다.
DOC_TAG = "[DOC]"


def _has_doc(files: dict) -> bool:
    """골조 어디든 `[DOC]` 가 하나라도 있나. [주의] 헤더·구현 둘 다 본다 — 계약이 어느
    파일에 실릴지는 조각의 성질이 정하고, 게이트가 그것까지 규정하지는 않는다."""
    return any(DOC_TAG in (t or "") for t in (files or {}).values())


def place(facts, tree: str, files: dict, *, writer=None) -> list:
    """골조 텍스트를 **격리된 트리**에 쓴다. [중요] 사람·워커의 트리가 아니다.

    `writer(facts, abs_path, text)` 를 주입할 수 있는 이유는 테스트다 — `.2` 없이 배치
    규칙을 검증한다.
    """
    if not tree:
        raise ValueError("격리 트리 경로가 비었다 — 어디에 쓸지 모른다")
    if writer is None:
        # [중요] 마스터 전용 경로 — 클라이언트 배달본에는 client 패키지가 없다.
        #    맨 ImportError 로 죽으면 "배달이 빠졌나" 로 오진한다 (#197 실 구동에서
        #    layer3 의 지연 임포트가 같은 모양으로 죽었다). 무엇을 해야 하는지 말한다.
        try:
            from ..client import bundle as B
        except ImportError as e:
            raise RuntimeError("place() 는 마스터 전용이다 — 클라이언트에서는 writer= 를 "
                               "주입할 것 (배달본에 client 패키지는 실리지 않는다)") from e
        writer = (lambda f, p, t: B.write_file(f, p, t))
    put = writer
    out: list = []
    for rel, text in sorted(files.items()):
        abs_path = _win_join(tree, rel) if getattr(facts, "windows", True) \
            else posixpath.join(tree, str(rel).replace("\\", "/"))
        put(facts, abs_path, text)
        out.append(abs_path)
    return out


MODE_UHT = "uht"        # [중요] 기본 — 헤더 계약만 본다 (`#317` 미결 ② 결정)
MODE_FULL = "full"      # 링크까지 — [주의] 골조 단계에는 성립하지 않는다 (아래 참조)


def run(facts, skeleton, *, tree: str, project: str, uproject: str = "",
        build_bat: str = "", timeout: int = BUILD_TIMEOUT,
        writer=None, builder=None, mode: str = MODE_UHT) -> GateResult:
    """골조를 세워 본다. **통과해야만 등재한다.**

    `builder` 를 주입할 수 있는 이유는 테스트다 — 실제 UE5 빌드 없이 계약을 검증한다.

    ## [중요] 기본은 **UHT** 다 (`#317` 미결 ② 결정 2026-08-27 · 구현·실측 2026-08-28)

    사용자 말 그대로: *"경량해서 검사해도 될 거 같아. 모든 사이클 끝나고 `.33` 에서 머지작업
    할 거잖아."* **골조 단계에 풀 빌드는 성립하지 않는다** — 골조가 헤더 계약이면 정의 없는
    `UFUNCTION` 하나로 `LNK2019` 가 나고, 그건 *골조가 깨진 것*이 아니라 *미완성인 것*이다.

    실측 (`.2` 격리 워크트리 · NSEditor):

        UHT   정상 골조 **9.7초**(첫 회, 생성 86파일) / 재실행 6.1초
              엉터리 지정자 **5.3초에 파일:행** — `AxUhtProbe.h(12): Error: Unknown specifier …`
        풀    75~122초 — **8~12배**

    [주의] **UHT 가 놓치는 부류**(실측 2026-08-28): 정의 없는 `UFUNCTION` · include 누락 ·
    없는 부모 상속. 그것들은 **조각 빌드에서 N번 터진다.** 사용자가 그 비용을 받아들였고
    마지막 `.33` 머지가 안전망이다. `mode=MODE_FULL` 로 옛 동작을 부를 수 있다 —
    되돌릴 자리를 남긴다.
    """
    if mode not in (MODE_UHT, MODE_FULL):
        raise ValueError(f"mode 는 {MODE_UHT}|{MODE_FULL} 여야 한다: {mode!r}")
    g = GateResult(stem=getattr(skeleton, "stem", "?"))
    files = getattr(skeleton, "files", None) or {}
    if not files:
        g.error = "골조에 파일이 없다 — 세울 것이 없다"
        return g
    # [중요] 골조가 골조가 아니면 빌드할 이유도 없다 — 싼 검사를 먼저 한다
    if not getattr(skeleton, "ok", False):
        g.error = "골조가 아니다 (`[PSEUDO]` 0 또는 동결 0) — 빌드 전에 막는다"
        return g

    # [중요] **계약이 보존 태그로 남았는가** — 실측 2026-09-01 에 이것이 0 이었다.
    #    그날 골조는 「무엇을 왜」를 전부 `[PSEUDO]` 에 넣었다(11파일 `[DOC]` 0개 ·
    #    `[PSEUDO]` 86개). `[PSEUDO]` 는 구현하면 워커가 **지우는** 태그라, Opus 로 11분
    #    들여 만든 계약이 첫 구현에서 증발하고 `main` 에는 *"왜 이렇게 생겼나"* 가 안 남는다.
    #    그것을 막자는 것이 2026-08-27 결정(「무엇을 왜」는 `[DOC]`)인데 **재는 게이트가
    #    없어서** 손으로 쓴 골조가 UHT 빌드만 통과하고 지나갔다.
    # [주의] 세는 것은 `[DOC]` 뿐이다 — `[STATE]`/`[BIND]`/`[REPLICATED]` 는 성질 표시라
    #    조각에 따라 없는 게 정상이다. 「계약이 하나도 보존되지 않았다」만 결정적으로 잡는다.
    if not _has_doc(files):
        g.error = ("계약이 보존 태그로 남지 않았다 (`[DOC]` 0개) — 빌드 전에 막는다. "
                   "「무엇을 왜」는 `[DOC]`, 「여기를 채워라」만 `[PSEUDO]` "
                   "(사용자 결정 2026-08-27) — `[PSEUDO]` 는 구현하면 지워지므로 "
                   "계약을 거기 두면 `main` 에 남지 않는다")
        return g

    try:
        g.placed = place(facts, tree, files, writer=writer)
    except Exception as e:                                   # noqa: BLE001
        g.error = f"골조 배치 실패: {e}"
        return g

    bb = build_bat or _build_bat_from(facts)
    if not bb:
        # [주의] 엔진을 못 찾은 것은 **미확인**이지 통과가 아니다
        g.error = "UE5 Build.bat 을 찾지 못했다 — 확인 불가이므로 막는다"
        return g
    up = uproject or _win_join(tree, f"{project}.uproject")

    g.checked = True
    g.mode = mode
    if builder is not None:
        fn = builder
    else:
        from ..layer3_verify import run_uht_on_workshop
        fn = run_uht_on_workshop if mode == MODE_UHT else run_build_on_workshop
    g.build = fn(facts.host, facts.user, bb, target_name(project), up, timeout=timeout)
    g.seconds = getattr(g.build, "seconds", None)
    return g


def build_bat_from_editor(ue5_cmd: str) -> str:
    """`UnrealEditor-Cmd.exe` 경로 **문자열**에서 `Build.bat` 을 유도한다. 못 찾으면 빈 문자열.

    [중요] 실측 2026-08-11: 이 기계의 엔진은 `C:\\Program Files\\UE_5.8` 이다 —
    `Epic Games` 하위가 **아니다.** 그래서 경로를 짐작하지 않고 `probe` 가 찾아 둔 값에서
    되짚는다.

    [주의] **공개 함수로 뗀 이유** (중 2.1 `#135`): 요청자 `.33` 은 `facts` 객체가 아니라 배달된
    `.ax/config.json` 의 `backends.ue5_cmd` **문자열**을 갖는다. 유도 규칙을 거기에 다시 쓰면
    같은 규칙이 두 벌이 되고, 엔진 경로 관례가 바뀌는 날 한쪽만 고쳐진다.
    """
    ue5 = (ue5_cmd or "").strip()
    if not ue5:
        return ""
    low = ue5.replace("/", "\\").lower()
    key = "\\engine\\binaries\\win64\\"
    if key not in low:
        return ""
    root = ue5[:low.index(key)]
    return root + r"\Engine\Build\BatchFiles\Build.bat"


def _build_bat_from(facts) -> str:
    """`facts.ue5` 판 — 기존 호출자(`skeleton_gate`·`integrate`)가 쓰는 이름. 규칙은 위 하나다."""
    return build_bat_from_editor(getattr(facts, "ue5", "") or "")
