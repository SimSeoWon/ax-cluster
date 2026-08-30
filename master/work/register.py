"""작업 등록 — `/distribute` 의 마스터 몫 (AgentTest `executor_work_register.py` 이식).

[중요] **원본에서 가장 크게 잘라낸 지점이다. 경계가 다르기 때문이다.**

AgentTest 의 `master_orchestrator` 는 **윈도우 UE5 프로젝트 루트에 함께 배포**됐다(zip 12종).
그래서 등록부가 저장소를 직접 만졌다 — `create_branch_if_needed` · `commit_skeletons` ·
`prepare_work_branch_impl`. 여기서는 **마스터가 파일을 소유하지 않고 소스 저장소에 push 도
못 한다**(§2.1, §8). 그러므로:

| 원본 등록부가 하던 일 | 여기 |
|---|---|
| 작업 브랜치 생성 | [실패] **작업장이 한다** |
| 골조 파일 쓰기 · 커밋 | [실패] **작업장이 한다** — 마스터는 골조 *텍스트*만 실어 보낸다 |
| 중복 검사 · work/task 큐 등록 | [완료] 마스터 |
| 컨텍스트 매니페스트 수집 | [완료] 마스터 (`manifest.py`) |

**이 경계가 §2.1 그대로다** — 마스터는 코드 뭉치를 조립해 건네는 데서 끝난다.

**분해(decomposition)는 여기 없다.** 요청 하나를 클래스 단위 태스크 N개로 쪼개는 것은 §4.5 의
주제이고 LLM 호출이 필요하다. 이 모듈은 **이미 쪼개진 명세를 받아 등록**한다 — 두 관심사를
섞으면 등록을 테스트할 때마다 추론이 필요해진다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from ..auth import auth_headers
from ..context_search.paths import ProjectPaths
from . import manifest as mf, twin_base
from .branch_names import base_branch

DEFAULT_QUEUE = "http://localhost:8101"
TIMEOUT = 30


class RegisterError(Exception):
    pass


@dataclass
class TaskSpec:
    """등록할 태스크 하나. **이미 클래스 단위로 쪼개진 것**이 들어온다 (§4.5)."""

    stem: str                                  # 조각 이름 (보통 클래스명)
    classes: list[str] = field(default_factory=list)
    contracts: str = ""                        # [중요] 동결 인터페이스 — 병렬 생성의 전제 (§4.5)
    skeleton: str = ""                         # 골조 텍스트. 파일로 쓰는 것은 작업장 몫
    target_file: str = ""            # 큐 레코드용(단수) — 여러 개면 `target_files` 의 첫 번째
    # [중요] 한 태스크가 맡는 파일 전부. **매니페스트에 실린다** — 예전엔 큐에만 있었다(#65).
    target_files: list = field(default_factory=list)
    header_file: str = ""
    depends_on: list = field(default_factory=list)
    requires: list = field(default_factory=list)   # 예: ["ue5"] — 능력 라우팅 (§5.2-C)
    priority: int = 0
    # [중요] 골조가 비어 있으면 등록 전에 **생성한다** (소 1.1.4). 그때 쓰는 재료가 아래 둘이다.
    instruction: str = ""                      # 무엇을 만들라는 것인지 (사람의 말)
    source_files: list = field(default_factory=list)   # 포팅 원본 — **읽기 전용** (소 1.3.5)
    depth_set: list = field(default_factory=list)      # `[PSEUDO:N]` — 소 1.2.4 가 소비

    def validate(self) -> None:
        if not (self.stem or "").strip():
            raise RegisterError("stem 이 비었다 — 태스크를 식별할 수 없다")
        if self.target_files and not self.target_file:
            self.target_file = self.target_files[0]
        if self.target_file and self.target_file not in self.target_files:
            self.target_files = [self.target_file] + list(self.target_files)
        if not self.classes and not self.target_file:
            raise RegisterError(
                f"{self.stem}: classes 도 target_file 도 없다 — "
                "매니페스트를 수집할 근거가 없다"
            )


@dataclass
class TaskResult:
    stem: str
    task_id: str = ""
    manifest_path: str = ""
    manifest_hits: int = 0
    carried_head: str = ""       # git-carried (#185) — durable 에 실린 커밋. 빈 값 = 못 실었다
    carried_error: str = ""
    error: str = ""
    manifest_degraded: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.task_id) and not self.error


@dataclass
class Registered:
    work_id: str
    tasks: list[TaskResult]
    generated: list = field(default_factory=list)   # 골조를 마스터가 만든 stem (소 1.1.4)
    gates: list = field(default_factory=list)       # 골조 빌드 게이트 판정 (소 1.1.5)
    base_branch: str = ""                           # `#319` 작업 브랜치 — 조각이 갈라진 자리
    # [중요] `#328` — 골조가 *"여기서 추측했다"* 고 말한 지점. **사람에게 닿아야 한다.**
    #    종전에는 `_fill_skeletons` 가 이것을 **버렸다** — 물음이 나와도 볼 길이 없었고,
    #    그래서 적립 루프가 한 번도 안 돌았다(적립 파일이 존재조차 안 했다).
    #    [주의] 이것은 **모델의 물음**이지 휴리스틱이 아니다 — 적립되는 것은 사람의 답뿐이다.
    questions: list = field(default_factory=list)   # [(stem, [Question, …])]
    accrued: list = field(default_factory=list)     # 이번 호출로 적립된 휴리스틱 주제

    @property
    def gate_checked(self) -> bool:
        """[중요] **미확인과 통과를 구분한다.** 게이트를 안 돌렸으면 빌드를 확인한 게 아니다."""
        return bool(self.gates) and all(getattr(g, "ok", False) for g in self.gates)

    @property
    def ok(self) -> bool:
        return bool(self.work_id) and all(t.ok for t in self.tasks)

    @property
    def failed(self) -> list[TaskResult]:
        return [t for t in self.tasks if not t.ok]

    def summary(self) -> str:
        n_ok = sum(1 for t in self.tasks if t.ok)
        # (아래에서 물음·적립을 덧붙인다 — `#328`)
        degraded = sum(1 for t in self.tasks if t.manifest_degraded)
        s = f"work={self.work_id} 태스크 {n_ok}/{len(self.tasks)} 등록"
        if degraded:
            s += f" · 매니페스트 결손 {degraded}건"
        if self.generated:
            s += f" · 골조 생성 {len(self.generated)}건"
        # [주의] 빌드를 확인했는지 **말로 적는다** — 안 적으면 미확인이 통과처럼 읽힌다
        s += (f" · 골조 빌드 [완료] {len(self.gates)}건" if self.gates
              else " · [주의] 골조 빌드 미확인")
        # [중요] **carry 실패는 크게 말한다** (리포트 39 지적, 2026-08-25 → 2026-08-29 수정).
        #    종전에는 `carried_error` 를 채우고 **아무 데서도 찍지 않았다** — 등록이 「성공」으로
        #    읽히고, 파견 단계에서 fail-closed 로 막혀서야 드러났다. 등록 실패는 아니지만
        #    (트윈 사본은 있다) **다음 단계가 막히는 사실**이라 물음·게이트와 같은 급으로 찍는다.
        carried = [t for t in self.tasks if (t.carried_error or "").strip()]
        if carried:
            head = "; ".join(f"{t.task_id or t.stem}: {t.carried_error}" for t in carried[:2])
            more = f" (외 {len(carried) - 2}건)" if len(carried) > 2 else ""
            s += f" · [중요] **carry 실패 {len(carried)}건 — 파견이 막힌다** — {head}{more}"
        if self.failed:
            s += f" · [중요] 실패 {len(self.failed)}건"
        # [중요] `#328` — **물음이 있으면 크게 말한다.** 종전에는 버려져서 사람이 볼 길이
        #    없었고, 그래서 적립 루프가 한 번도 안 돌았다. 안 보이면 없는 것과 같다.
        n_q = sum(len(qs) for _stem, qs in self.questions)
        if n_q:
            s += f" · [중요] **골조가 물음 {n_q}건을 냈다 — 답해야 적립된다**"
        if self.accrued:
            s += f" · 휴리스틱 적립 {len(self.accrued)}건"
        return s

    def question_lines(self) -> list:
        """사람에게 보일 물음. [주의] **모델의 제안이지 답이 아니다** — 그대로 적립하지 않는다."""
        out: list = []
        for stem, qs in self.questions:
            for q in qs:
                out.append(f"{stem}: {getattr(q, 'summary', str(q))}")
        return out


def _post(url: str, payload: dict, *, token: str | None = None,
          method: str = "POST") -> dict:
    """큐 호출 한 번. `method` 는 `#319` 가 PATCH(작업 브랜치 기록)를 쓰면서 열었다."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={"Content-Type": "application/json", **auth_headers(token)},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise RegisterError(f"{url} → HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RegisterError(f"{url} → 연결 실패: {e.reason}") from e


def _accrue(paths: ProjectPaths, heuristics) -> tuple:
    """사람의 답을 적립한다 (`#328`). `(적립된 주제, once 답 목록)`.

    [중요] **적립되는 것은 사람이 답한 것뿐이다** — 모델이 낸 물음(`Registered.questions`)은
    반대 방향으로 나가고, 여기 들어오지 않는다. 그 구분이 자동 승급을 껐던 것과 같은 이유다:
    모델의 제안을 적립하면 다음 골조가 **자기가 한 말을 근거로** 같은 선택을 반복한다.

    [중요] **`scope=once` 는 적립하지 않는다** — 이번 골조에만 실린다(`SkeletonSpec.answers`).
    적립하면 *"이번 스냅샷은 컴포넌트로"* 가 관계없는 다음 작업을 오염시킨다(사용자 지적
    2026-08-11: *"저 질문들은 답변하면 모든 분산 작업에 적용되는거야?"*).

    [주의] 적립 실패는 **등록을 막지 않는다** — 사유를 결과에 실어 올린다. 휴리스틱은 다음
    골조를 좋게 하는 것이지 이번 등록의 전제가 아니다.
    """
    from . import heuristics as H
    accrued: list = []
    once: list = []
    for item in (heuristics or []):
        if not isinstance(item, dict):
            accrued.append(f"[주의] 형식이 아니다 — 건너뜀: {str(item)[:60]}")
            continue
        h = H.Heuristic(topic=str(item.get("topic") or "").strip(),
                        decision=str(item.get("decision") or "").strip(),
                        why=str(item.get("why") or "").strip(),
                        at=str(item.get("at") or "").strip(),
                        scope=str(item.get("scope") or H.SCOPE_PROJECT).strip())
        if not h.storable:
            # 이번 골조에만 — 프롬프트에 실을 문장으로 넘긴다
            once.append(f"{h.topic}: {h.decision}" if h.topic else h.decision)
            accrued.append(f"(once) {h.topic or h.decision[:30]} — 적립하지 않는다")
            continue
        try:
            H.add(paths, h)
            accrued.append(f"{h.scope} · {h.topic}")
        except (ValueError, OSError) as e:                   # noqa: BLE001
            accrued.append(f"[주의] 적립 실패 — {h.topic or '(주제 없음)'}: {e}")
    return accrued, once


def _fill_skeletons(specs: list, *, paths: ProjectPaths, make_skeleton=None,
                    gate=None, gate_results: list | None = None,
                    questions_out: list | None = None,
                    once_answers: list | None = None) -> list:
    """골조가 빈 명세를 채운다 (소 1.1.4). **제자리에서 고치고** 생성한 stem 을 돌려준다.

    [중요] **생성 조건은 하나다 — `instruction` 이 있고 `skeleton` 이 없을 때.** 둘 다 없는 명세는
    **손대지 않는다**: 골조 없는 등록은 원래부터 정상 경로다(작업장이 골조를 쓰는 흐름).
    골조를 필수로 만들면 기존 호출자가 전부 깨지는데, 그건 이 칸이 할 일이 아니다.

    [중요] **동결 계약도 같이 채운다.** 골조만 있고 계약이 없으면 워커는 무엇이 동결됐는지 모르고
    층1 은 대조할 원본이 없다 — 병렬이 성립하지 않는다(§4.5).

    [중요] **생성한 골조가 골조가 아니면 등록하지 않는다.** `[PSEUDO]` 0개(=완성 파일)나 동결
    선언 0개는 원전이 값을 치르고 배운 실패다 — 글루 파일이 워커 태스크로 등재되던 버그.
    """
    need = [s for s in specs
            if not (s.skeleton or "").strip() and (s.instruction or "").strip()]
    if not need:
        return []
    from . import skeleton as sk
    fn = make_skeleton or sk.build
    made: list = []
    for s in need:
        spec = sk.SkeletonSpec(stem=s.stem, files=list(s.target_files),
                               classes=list(s.classes), instruction=s.instruction,
                               source_files=list(s.source_files),
                               # [중요] `#328` — `scope=once` 인 답은 **적립하지 않고 이 골조에만**
                               #    실린다. 적립하면 *"이번 스냅샷은 컴포넌트로"* 가 관계없는
                               #    다음 작업을 오염시킨다(사용자 지적 2026-08-11).
                               answers=list(once_answers or []))
        built = fn(paths, spec)
        if not built.ok:
            raise RegisterError(f"{s.stem}: 골조 생성 실패 — " + "; ".join(built.notes))
        # [중요] **골조 빌드 게이트** (소 1.1.5) — 통과해야만 등재한다. 골조는 모든 조각의
        #    base 라, 조각 하나가 깨지는 것과 값이 다르다: 깨진 골조는 **N개를 헛일로 만든다.**
        #    원전이 빌드를 등재 *뒤*에 두었다가 정확히 그 사고를 냈다.
        if gate is not None:
            g = gate(built)
            if gate_results is not None:
                gate_results.append(g)
            if not getattr(g, "ok", False):
                raise RegisterError(f"{s.stem}: [중요] 골조 빌드 게이트 차단 — "
                                    f"{getattr(g, 'summary', g)}")
        # [중요] 파일로 쓰지 않는다. 텍스트로 실어 보낸다 (§2.1).
        s.skeleton = "\n\n".join(f"=== FILE: {p} ===\n{t}"
                                 for p, t in sorted(built.files.items()))
        if not (s.contracts or "").strip():
            s.contracts = built.contracts()
        # [중요] `#328` — 물음을 **버리지 않고 올린다.** 사람이 답할 수 있어야 루프가 돈다.
        if questions_out is not None and getattr(built, "questions", None):
            questions_out.append((s.stem, list(built.questions)))
        s.depth_set = built.depth_set
        made.append(s.stem)
    return made


def register_work(
    title: str,
    specs: list[TaskSpec],
    *,
    paths: ProjectPaths,
    target_repo: str,
    original_request: str = "",
    target_branch: str = "",
    queue_url: str = DEFAULT_QUEUE,
    token: str | None = None,
    poster=None,
    patch=None,
    searcher=None,
    make_skeleton=None,
    gate=None,
    carrier="AUTO",
    require_base: bool | None = None,
    heuristics=None,
) -> Registered:
    """work 를 만들고 태스크를 등록한다. 태스크마다 매니페스트를 1회 수집한다.

    `poster` 를 주입할 수 있는 이유는 테스트다 — 큐를 띄우지 않고 등록 규칙을 검증한다.

    [중요] **명세 검증을 먼저 전부 돌린다.** 절반 등록하고 실패하면 큐에 반쪽 work 가 남는데,
    그건 사람이 치워야 한다. 막을 수 있는 것은 미리 막는다.

    `make_skeleton` 은 골조가 없는 명세를 위해 **등록 전에** 불린다 (소 1.1.4). 기본은
    `skeleton.build` 이고, 골조를 이미 넘겨준 명세는 **건드리지 않는다**(하위 호환 — 사람이
    직접 쓴 골조가 LLM 출력보다 낫다면 그쪽이 이긴다).

    `gate(skeleton) -> GateResult` 를 주면 **골조를 세워 보고 통과해야만 등재한다**
    (소 1.1.5, `skeleton_gate.run`). [주의] **게이트를 안 주는 것은 통과가 아니라 미확인이다** —
    결과의 `gate_checked` 로 구분한다.
    """
    if not (title or "").strip():
        raise RegisterError("title 이 비었다")
    if not specs:
        raise RegisterError("등록할 태스크가 없다")
    seen: set[str] = set()
    for s in specs:
        s.validate()
    # [중요] **골조 생성은 큐를 만지기 전에 끝낸다.** 등록 도중 생성이 실패하면 반쪽 work 가
    #    남고, 그건 사람이 치운다 — 위 검증 선행과 같은 이유다.
    # ── `#328` 적립 루프 ────────────────────────────────────────────────
    # [중요] **적립이 골조 생성보다 먼저다.** 순서를 뒤집으면 이번에 답한 것이 이번 프롬프트에
    #    안 실린다 — 사람이 답했는데 아무것도 안 바뀌는 것으로 보인다.
    # [주의] 들어오는 것은 **사람의 답**이다. 나가는 것(`Registered.questions`)은 모델의 물음이고,
    #    둘은 **방향이 반대**다 — 그 구분이 이 저장소의 규칙이다(모델의 제안을 적립하지 않는다).
    accrued, once_answers = _accrue(paths, heuristics)

    gates: list = []
    questions: list = []
    # ── [중요] **마스터는 등재에서 골조를 만들지 않는다** (사용자 결정 2026-08-30) ──────────
    #
    # `#317` ①·`#319` 가 골조 제작을 **요청자(`.33`)** 로 옮겼다 — 골조는 `task/<work_id>/base`
    # 에 **실물로** 커밋돼야 조각들이 같은 계약을 본다(`ax-request` §3.5). 그런데 `#319` 는
    # 골조를 **나르는 것**만 없앴고(`register.py` 의 "골조 텍스트는 더 이상 실어 보내지 않는다"),
    # **만드는 것**은 이 자리에 그대로 남아 있었다.
    #
    # [주의] 그래서 첫 실전 등재(2026-08-30 21:57)에서 **마스터가 `claude:opus` 로 골조를
    # 생성하기 시작했다** — 조각 5개, 동시 2프로세스. 클라 타임아웃은 30초라 요청자는 이미
    # 포기했고, 재시도가 겹쳐 같은 골조를 여러 번 만들 뻔했다. 사용자: *"골조를 니가 왜 만드는데?"*
    #
    # `#336` ①(require_base)과 **같은 부류**다 — 사용자 결정 둘이 다른 시점에 구현됐고
    # 한쪽을 구현할 때 다른 쪽을 안 봤다.
    #
    # [주의] `make_skeleton` 을 **명시로 주입할 때만** 돈다 — 테스트가 그 자리를 쓴다.
    #    기본값(=주입 없음)에서는 **LLM 을 부르지 않는다.**
    generated: list = []
    if make_skeleton is not None:
        generated = _fill_skeletons(specs, paths=paths, make_skeleton=make_skeleton,
                                    gate=gate, gate_results=gates,
                                    questions_out=questions, once_answers=once_answers)
    for s in specs:
        if s.stem in seen:
            raise RegisterError(f"stem 이 중복이다: {s.stem} — 매니페스트가 서로를 덮어쓴다")
        seen.add(s.stem)

    post = poster or (lambda u, p: _post(u, p, token=token))
    # [중요] **주입된 큐가 PATCH 도 받는다** — `carrier="AUTO"` 와 같은 관례다. poster 를 주입한
    #    것은 "큐가 가짜다" 라는 뜻이고, 그때 실 HTTP 로 나가면 테스트가 마스터를 두드린다.
    if patch is not None:
        patcher = patch
    elif poster is not None:
        patcher = poster
    else:
        patcher = lambda u, p: _post(u, p, token=token, method="PATCH")   # noqa: E731
    # ── `require_base` 기본값은 **off** 다 (`#336` ① · 사용자 결정 2026-08-30) ──────────
    #
    # [중요] **종전 기본값(`poster is None` → 실전에서 항상 True)은 재설계 순서와 어긋났다.**
    #    `#317` 미결 ① 이 「work 등재를 0번으로」로 정했는데, 브랜치 이름이
    #    `task/<work_id>/base` 라 **work_id 를 받은 뒤에야 이름이 생긴다.** 그 시점에 base 는
    #    있을 수 없다(요청자가 그 다음에 만든다). 즉 재설계대로 가면 **등재가 구조적으로 한 번
    #    실패**했다 — `#319` 완료조건 2 와 `#317` ① 이 서로를 부정했고, 한쪽을 구현할 때 다른
    #    쪽을 안 봤다.
    #
    # [중요] **부재 판정을 없애는 것이 아니라 자리를 옮기는 것이다.** 뒤에 그대로 있다:
    #    · `#331` — base 가 원격에 없으면 통합자가 **거절**한다(at_commit="" · push 없음)
    #    · 매니페스트 — *"요청자가 먼저 만들어야 작업이 성립한다"* 를 결손으로 찍는다
    #    · `carry.publish` — 기준 커밋이 비면 실패하고 `8b0c0aa` 가 등록 응답에 크게 남긴다
    #    등재는 **기록**이고, 브랜치가 필요한 것은 **파견·통합**이다. 게이트를 필요한 자리에 둔다.
    #
    # [주의] 여전히 켤 수 있다 — `require_base=True` 를 명시하면 종전과 같이 거절한다.
    if require_base is None:
        require_base = False

    # [중요] carrier 기본 AUTO — 실전은 carry.publish, poster 주입(테스트)은 큐가 가짜이므로
    #    git 도 만지지 않는다 (None). 명시 주입이 둘 다 이긴다.
    if carrier == "AUTO":
        if poster is None:
            from .carry import publish as carrier      # noqa: F811
        else:
            carrier = None

    work_id = create_work(title, paths=paths, target_repo=target_repo,
                          original_request=original_request, target_branch=target_branch,
                          queue_url=queue_url, token=token, poster=post)

    # ── [중요] 여기부터는 **보상 취소**가 붙는다 (`#336` ③, 실측 2026-08-30) ──────────
    #    큐에는 삭제 API 가 없다(추가 전용 감사 로그). 그래서 등재가 중간에 죽으면 **열린
    #    반쪽 work** 가 남고, 그것은 마운트 전환(`set_active`)과 `test_projects.py` 를 막는다.
    #    실측: `.33` 첫 실전 등재가 `manifest.build` 에서 예외로 죽어 `total=1`(specs 4) 인
    #    work 이 `in_progress` 로 남았고, 다음 세션이 그것을 「이미 등재돼 있다」로 읽었다.
    #    지울 수 없으면 **종결시킨다** — 열려 있지만 않으면 다음 실행을 오염시키지 않는다.
    try:
        return _register_after_create(
            work_id, specs, paths=paths, target_branch=target_branch, queue_url=queue_url,
            token=token, post=post, patcher=patcher, searcher=searcher, carrier=carrier,
            require_base=require_base, generated=generated, gates=gates,
            questions=questions, accrued=accrued)
    except BaseException as e:                              # noqa: BLE001
        note = _abandon_work(work_id, paths=paths, queue_url=queue_url,
                             patcher=patcher, reason=f"{type(e).__name__}: {e}")
        raise RegisterError(f"{e}\n[중요] work {work_id} 는 {note}") from e


def _abandon_work(work_id: str, *, paths, queue_url: str, patcher, reason: str) -> str:
    """실패한 등재를 **종결**시킨다. 반환은 사람에게 보일 한 마디."""
    try:
        patcher(f"{queue_url}/api/v1/works/{work_id}",
                {"project": paths.name, "merge_status": "cancelled",
                 "review_decision": {"decision": "cancelled", "reviewer": "register",
                                     "reason": f"등재 실패로 자동 종결 — {reason[:300]}"}})
        return "자동으로 `cancelled` 처리했다 (반쪽 work 를 남기지 않는다)"
    except Exception as e:                                  # noqa: BLE001
        # [주의] 이것마저 실패하면 **크게 말한다** — 조용히 넘기면 반쪽이 남은 줄 모른다
        return (f"[중요] **열린 채로 남았다** — 자동 종결도 실패했다({e}). "
                f"사람이 `PATCH /api/v1/works/{work_id}` 로 `merge_status=cancelled` 할 것")


def _register_after_create(work_id, specs, *, paths, target_branch, queue_url, token,
                           post, patcher, searcher, carrier, require_base,
                           generated, gates, questions, accrued):
    """work 생성 **뒤**의 단계들. 여기서 죽으면 호출부가 보상 취소한다."""
    # ── `#319` 작업 브랜치 ────────────────────────────────────────────────
    # [중요] **이름은 work_id 를 받은 뒤에야 만들어진다** — 생성 POST 에 실을 수 없어서
    #    곧바로 patch 한다. 큐가 work 메타의 SSOT 이고, 표·조회·검수가 그 값을 읽는다.
    base_ref = target_branch.strip() or base_branch(work_id)
    try:
        patcher(f"{queue_url}/api/v1/works/{work_id}",
                {"project": paths.name, "target_branch": base_ref})
    except RegisterError as e:
        # [주의] 조용히 넘기지 않는다 — 큐의 표가 브랜치를 거짓으로 말하면 검수가 엉뚱한
        #    브랜치를 머지한다. 다만 work 는 이미 생겼으므로 사유를 실어 올린다.
        raise RegisterError(
            f"work {work_id} 는 만들어졌으나 작업 브랜치({base_ref})를 큐에 기록하지 못했다: {e}"
        ) from e

    if require_base:
        # [중요] `#319` 완료 조건 2 — **없으면 시끄럽게 실패한다.** 조용히 main 으로 접으면
        #    조각 N개가 각자 main 에서 나고 골조 동결이 약속으로만 남는다(옛 동작).
        #    [주의] 여기서 멈추면 큐에 **태스크 없는 work** 가 남는다 — 그건 사람이 치운다.
        #    반쪽 등록(태스크 절반)보다 낫다는 판단은 이 파일의 기존 관례와 같다.
        b = base_status(paths, work_id, branch=base_ref)
        if not b.checked:
            raise RegisterError(
                f"작업 브랜치 `{base_ref}` 존재를 확인하지 못했다 ({b.error}) — "
                f"확인 실패는 통과가 아니다. work_id={work_id}")
        if not b.exists:
            raise RegisterError(
                f"작업 브랜치 `{base_ref}` 가 원격에 없다 — 골조가 거기 실물로 있어야 조각이 "
                f"갈라진다(`#319`). 요청자가 먼저 만들 것:\n    {b.instruction}\n"
                f"work_id={work_id}")

    results = register_tasks(work_id, specs, paths=paths, queue_url=queue_url, token=token,
                             poster=post, searcher=searcher, carrier=carrier)
    return Registered(work_id=work_id, tasks=results, generated=generated,
                      gates=gates, base_branch=base_ref,
                      questions=questions, accrued=accrued)


def create_work(title: str, *, paths: ProjectPaths, target_repo: str,
                original_request: str = "", target_branch: str = "",
                queue_url: str = DEFAULT_QUEUE, token: str | None = None,
                poster=None) -> str:
    """work 하나를 만들고 **work_id 를 돌려준다** — `#317` 미결 ① 순서의 0번.

    [중요] **떼어 낸 이유**: 작업 브랜치 이름이 `task/<work_id>/base` 라서 **work_id 가 먼저**
    나와야 요청자가 브랜치를 만들 수 있다. 등록을 한 덩어리로 두면 그 사이에 사람이 낄 자리가
    없다. 순서는 0) work 등재 → 1) 브랜치 생성 → 2) 골조 커밋·UHT·push → 3) 태스크 등재다.
    """
    post = poster or (lambda u, p: _post(u, p, token=token))
    work = post(f"{queue_url}/api/v1/works", {
        "title": title,
        # [중요] 프로젝트 귀속 스탬프 (#210) — 종결 기록·신호가 활성이 아니라 이 값으로 푼다
        "project": paths.name,
        "target_repo": target_repo,
        "target_branch": target_branch,
        "original_request": original_request or title,
        # [중요] 3-tier 브랜치를 쓴다. 원본의 pull 레거시 경로는 우리에게 없다 (`branch_names.py`).
        "distribution_mode": "push",
    })
    work_id = str(work.get("work_id") or work.get("id") or "")
    if not work_id:
        raise RegisterError(f"work_id 를 받지 못했다: {work}")
    return work_id


def base_status(paths: ProjectPaths, work_id: str, *, branch: str = "", runner=None):
    """작업 브랜치가 원격에 있나 — `twin_base.Base` 를 돌려준다 (`#319`).

    `branch` 를 주면 그 이름으로 본다(저장된 `target_branch` 가 유도값을 이기는 경우).
    """
    b = twin_base.resolve(paths, work_id, runner=runner)
    if branch and branch != b.branch:
        b.branch = branch
        b.exists = False
        b.commit = ""
        try:
            heads = twin_base.remote_heads(paths, runner=runner)
        except twin_base.TwinBaseError as e:
            b.error = str(e)
            return b
        b.exists = branch in heads
        if b.exists:
            b.commit = heads[branch]
    return b


def register_tasks(work_id: str, specs: list[TaskSpec], *, paths: ProjectPaths,
                   queue_url: str = DEFAULT_QUEUE, token: str | None = None,
                   poster=None, searcher=None, carrier=None,
                   heuristics=None, accrued_out: list | None = None) -> list[TaskResult]:
    """이미 있는 work 아래에 태스크를 등록한다 — `#317` 미결 ① 순서의 3번.

    [중요] 골조 텍스트는 **더 이상 실어 보내지 않는다** (`#319` 완료 조건 3) — 작업 브랜치에
    실물로 있다. `task_data.skeleton` 은 **감사용 기록**으로만 남긴다(누가 무엇을 골조로
    삼았는지는 나중에 물어볼 수 있어야 한다).
    """
    post = poster or (lambda u, p: _post(u, p, token=token))
    # [중요] `#328` — `#319` 순서(0 등재 → 1 브랜치 → 2 **골조+질문·답** → 3 태스크 등재)에서
    #    답이 나오는 시점과 마스터를 두드리는 시점이 **같은 순간**이다. 그래서 여기서도 받는다.
    #    [주의] 골조는 이 함수가 만들지 않으므로 `once` 답은 쓸 자리가 없다 — 적립분만 본다.
    #    [중요] `register_work` 는 **여기로 넘기지 않는다** — 그쪽이 이미 적립했다(이중 적립 방지).
    if heuristics:
        acc, once = _accrue(paths, heuristics)
        if once:
            acc.append(f"[주의] `once` 답 {len(once)}건은 이 표면에서 쓸 자리가 없다 — "
                       f"골조를 만드는 호출에 실어야 한다")
        if accrued_out is not None:
            accrued_out.extend(acc)
    # 검색기는 태스크마다 새로 열지 않는다 — 모델 로딩이 태스크 수만큼 반복된다.
    if searcher is None:
        try:
            from ..context_search import ContextSearch
            searcher = ContextSearch(paths)
        except Exception as e:                       # noqa: BLE001
            searcher = mf._BrokenSearcher(e)

    results: list[TaskResult] = []
    for spec in specs:
        r = TaskResult(stem=spec.stem)
        try:
            reg = post(f"{queue_url}/api/v1/tasks", {
                "work_id": work_id,
                # work 와 같은 스탬프를 싣는다 — 서버가 대조한다(어긋나면 등록이 거절된다)
                "project": paths.name,
                "type": "code",
                "stem": spec.stem,
                "target_file": spec.target_file,
                "header_file": spec.header_file,
                "depends_on": spec.depends_on,
                "requires": spec.requires,
                "priority": spec.priority,
                "origin": "master",
                "task_data": {
                    "stem": spec.stem,
                    "classes": spec.classes,
                    "contracts": spec.contracts,
                    # [주의] 감사용 사본이다 — **전송 수단이 아니다**(`#319`). 워커는 작업
                    #    브랜치에서 골조를 읽는다.
                    "skeleton": spec.skeleton,
                },
            })
            r.task_id = str(reg.get("task_id") or reg.get("id") or "")
            if not r.task_id:
                r.error = f"task_id 를 받지 못했다: {reg}"
        except RegisterError as e:
            r.error = str(e)

        if r.task_id:
            # 매니페스트는 베스트에포트다 — 실패해도 등록을 되돌리지 않는다.
            # 다만 결손을 결과에 실어 호출자가 알 수 있게 한다.
            #
            # [중요] **주석은 그렇게 적혀 있었는데 `try` 가 없었다** (`#336` ③, 실측 2026-08-30).
            #    `.33` 의 첫 실전 등재가 `contracts` 를 리스트로 보냈고 `mf.build` 안의
            #    `contracts.strip()` 이 `AttributeError` 로 터졌다. 그 예외가 **루프 밖으로
            #    빠져나가** 등록 전체를 죽였고, 이미 등록된 태스크 1건과 work 이 큐에 남았다
            #    (specs 는 4건이었다). 「베스트에포트」가 계약이면 **잡아야 계약이다.**
            #    [주의] 여기서 잡는 것은 **매니페스트·carry** 뿐이다 — 태스크 등록 자체의
            #    실패는 위 `except RegisterError` 가 이미 `r.error` 로 싣는다.
            try:
                _build_manifest_and_carry(r, spec, paths=paths, work_id=work_id,
                                          searcher=searcher, carrier=carrier)
            except Exception as e:                          # noqa: BLE001
                r.manifest_degraded = list(r.manifest_degraded) + [
                    f"[중요] 매니페스트 생성이 예외로 죽었다 — {type(e).__name__}: {e}"]
        results.append(r)
    return results


def _build_manifest_and_carry(r, spec, *, paths, work_id, searcher, carrier) -> None:
    """매니페스트 수집 + git-carried 적재. **예외를 잡지 않는다** — 호출부가 잡는다."""
    m = mf.build(paths, r.task_id, work_id=work_id, classes=spec.classes,
                 target_files=spec.target_files, stem=spec.stem,
                 contracts=spec.contracts,
                 # [중요] 포팅 원본 (소 1.3.5) — 사람이 준 `source_files` 가 이기고,
                 #    없으면 대상 파일로 자동 조회한다. **경로만** 실린다.
                 source_files=spec.source_files,
                 searcher=searcher)
    r.manifest_path = str(mf.write(paths, m))
    r.manifest_hits = m.hits
    r.manifest_degraded = m.degraded
    # [중요] git-carried (#185 판정 2026-08-17) — 매니페스트를 조각 durable
    #    `task/<work_id>/<task_id>` 에 commit·push 한다. 원전 C.2 의 성질 복원:
    #    재배정은 fetch 만, 이력은 git 에. 실패해도 등록은 성립하되(트윈 사본은 있다)
    #    **결과에 크게 남긴다** — 파견은 fail-closed 라 이대로면 배달에서 막힌다.
    if carrier is not None:
        c = carrier(paths, work_id, r.task_id, m.body, base_commit=m.base_commit)
        r.carried_head = c.head if c.ok else ""
        r.carried_error = c.error
