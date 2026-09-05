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
from . import twin_base
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
    # [중요] 한 태스크가 맡는 파일 전부 (#65).
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
                "무엇을 만들라는 것인지 식별할 수 없다"
            )


@dataclass
class TaskResult:
    stem: str
    task_id: str = ""
    error: str = ""

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
    # 🔴 라운드 — 등록은 1, 개선요청은 큐가 열어 준 값 (사용자 결정 2026-09-05)
    round: int = 1

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
        s = (f"work={self.work_id} 라운드 {self.round} "
             f"태스크 {n_ok}/{len(self.tasks)} 등록")
        if self.generated:
            s += f" · 골조 생성 {len(self.generated)}건"
        # [주의] 빌드를 확인했는지 **말로 적는다** — 안 적으면 미확인이 통과처럼 읽힌다
        s += (f" · 골조 빌드 [완료] {len(self.gates)}건" if self.gates
              else " · [주의] 골조 빌드 미확인")
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
        detail = e.read().decode("utf-8", "replace")[:600]
        # [중요] **큐가 낸 사유를 그대로 꺼낸다** — 요청자가 읽고 고치는 문장이다. 종전에는
        #    FastAPI 의 `{"detail": {...}}` 포장이 그대로 나가서, 라운드 불일치 같은 **조치가
        #    분명한 거절**이 JSON 뭉치로 보였다(실측 2026-09-05, 개선요청 표면).
        try:
            got = json.loads(detail)
            inner = got.get("detail") if isinstance(got, dict) else None
            if isinstance(inner, dict) and inner.get("error"):
                raise RegisterError(str(inner["error"])) from e
            if isinstance(inner, str) and inner:
                raise RegisterError(inner) from e
        except (ValueError, AttributeError):
            pass
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
    # [중요] **`sk.build` 로 폴백하지 않는다** (사용자 결정 2026-08-30). 골조는 `.33` 이
    #    만든다(`#317` ①·`#319` · `ax-request` §3.5) — 마스터에 「조용히 만드는」 경로를
    #    남겨 두면 그 결정이 코드에서 다시 열린다. 실제로 그렇게 열려 있었고, 첫 실전 등재가
    #    `claude:opus` 를 동시 2프로세스로 돌렸다.
    #    [주의] 주입 없이 여기 오는 것은 **호출부의 버그**다 — 조용히 만들지 말고 말한다.
    if make_skeleton is None:
        raise RegisterError(
            "골조 생성기가 주입되지 않았다 — 마스터는 골조를 만들지 않는다. "
            "골조는 요청자가 `task/<work_id>/base` 에 실물로 커밋한다 (`#317` ①·`#319`)")
    fn = make_skeleton
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


def _prepare_specs(specs, *, paths, make_skeleton, gate, heuristics) -> dict:
    """명세 검증 · 답 적립 · (주입됐으면) 골조 생성 — **큐를 만지기 전에** 끝내는 것들.

    [중요] **등재와 개선요청이 같은 준비를 쓴다.** 두 입구로 갈렸어도(사용자 결정
    2026-09-05) 조각을 만드는 규칙은 하나여야 한다 — 갈라 두면 한쪽만 고치는 사고가 난다.
    """
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
            raise RegisterError(f"stem 이 중복이다: {s.stem} — 조각을 구별할 수 없다")
        seen.add(s.stem)
    return {"generated": generated, "gates": gates,
            "questions": questions, "accrued": accrued}


def register_work(
    title: str,
    specs: list[TaskSpec],
    *,
    paths: ProjectPaths,
    target_repo: str,
    original_request: str = "",
    target_branch: str = "",
    work_id: str = "",
    queue_url: str = DEFAULT_QUEUE,
    token: str | None = None,
    poster=None,
    patch=None,
    make_skeleton=None,
    gate=None,
    require_base: bool | None = None,
    heuristics=None,
) -> Registered:
    """work 를 만들고 태스크를 등록한다.

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
    # 🔴 [중요] **등재는 최초 전용이다 — 개선요청은 다른 호출이다** (사용자 결정 2026-09-05:
    #    *"분산작업 등록과 라운드 값을 받는 분산작업 개선 요청으로 말이야"*).
    #    종전에는 `work_id` 를 실으면 이 함수가 **재활성화**로 갈렸다. 한 입구에 두 뜻이라
    #    라운드를 상태로 추론했고, 상태가 예상 밖이면 조용히 틀렸다(`logic.register_task` 주석).
    if (work_id or "").strip():
        raise RegisterError(
            f"등재에 work_id 를 실을 수 없다 ({work_id}) — 이미 있는 분산 작업의 다음 라운드는 "
            f"**개선요청**이다: `improve_work(work_id=…, round=현재+1, specs=[…])`. "
            f"등재(`register_work`)는 **새 분산 작업**만 만든다(round=1)")
    if not (title or "").strip():
        raise RegisterError("title 이 비었다")
    if not specs:
        raise RegisterError("등록할 태스크가 없다")
    _prep = _prepare_specs(specs, paths=paths, make_skeleton=make_skeleton,
                           gate=gate, heuristics=heuristics)
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
    #    등재는 **기록**이고, 브랜치가 필요한 것은 **파견·통합**이다. 게이트를 필요한 자리에 둔다.
    #
    # [주의] 여전히 켤 수 있다 — `require_base=True` 를 명시하면 종전과 같이 거절한다.
    if require_base is None:
        require_base = False

    work_id = create_work(title, paths=paths, target_repo=target_repo,
                          original_request=original_request, target_branch=target_branch,
                          queue_url=queue_url, token=token, poster=post)

    # ── [중요] 여기부터는 **보상 취소**가 붙는다 (`#336` ③, 실측 2026-08-30) ──────────
    #    큐에는 삭제 API 가 없다(추가 전용 감사 로그). 그래서 등재가 중간에 죽으면 **열린
    #    반쪽 work** 가 남고, 그것은 마운트 전환(`set_active`)과 `test_projects.py` 를 막는다.
    #    실측: `.33` 첫 실전 등재가 예외로 죽어 `total=1`(specs 4) 인
    #    work 이 `in_progress` 로 남았고, 다음 세션이 그것을 「이미 등재돼 있다」로 읽었다.
    #    지울 수 없으면 **종결시킨다** — 열려 있지만 않으면 다음 실행을 오염시키지 않는다.
    try:
        return _register_after_create(
            work_id, specs, paths=paths, target_branch=target_branch, queue_url=queue_url,
            token=token, post=post, patcher=patcher,
            require_base=require_base, **_prep)
    except BaseException as e:                              # noqa: BLE001
        # [중요] **보상 취소는 「내가 만든 work」에만 한다** — 등재는 방금 만든 work 이라
        #    여기서 닫아도 남의 산출물이 죽지 않는다. 개선요청(`improve_work`)은 **닫지 않는다.**
        note = _abandon_work(work_id, paths=paths, queue_url=queue_url,
                             patcher=patcher, reason=f"{type(e).__name__}: {e}")
        raise RegisterError(f"{e}\n[중요] work {work_id} 는 {note}") from e


def improve_work(
    work_id: str,
    specs: list[TaskSpec],
    *,
    round: int,
    paths: ProjectPaths,
    target_branch: str = "",
    queue_url: str = DEFAULT_QUEUE,
    token: str | None = None,
    poster=None,
    patch=None,
    make_skeleton=None,
    gate=None,
    require_base: bool | None = None,
    heuristics=None,
) -> Registered:
    """🔴 **분산작업 개선요청 — 이미 있는 work 을 다음 라운드로 연다** (사용자 결정 2026-09-05).

    사용자: *"분산작업 등록과 라운드 값을 받는 분산작업 개선 요청으로 말이야"* ·
    *"라운드는 처음 작업 요청할 때는 1이고 모든 분산 작업 완료되어 `.33` 메인 작업 컴퓨터에서
    머지하고 개선 요청을 받은 경우 +1 이 되서 2 라운드 시작"*.

        ① 등록      `register_work(title, specs)`               round = 1
        ② 개선요청   `improve_work(work_id, round=N, specs)`     N = 현재 + 1   ← **여기**
        ③ 마감      `review.finalize_work(confirm=True)`        main 머지 · 큐 merged · 이슈 완료

    [중요] **`round` 는 확인용이다** — 값은 큐가 이미 알고 있고(현재+1), 요청자가 실어 보내는
    것은 *"내가 아는 라운드가 이거다"* 라는 대조다. 어긋나면 큐가 **거절**한다(맞추지 않는다).

    [중요] **승격이 조각 등재보다 먼저다.** 그래야 조각에 새겨지는 라운드가 올라간 값이고,
    서브 브랜치가 `task/<work>/r<N>/<조각>` 으로 갈린다. 종전에는 `register_task` 가 부수효과로
    승격해서, 상태가 예상 밖이면 지난 라운드 번호가 조용히 찍혔다.

    [주의] **실패해도 그 work 을 종결시키지 않는다.** 보상 취소(`_abandon_work`)는 「내가 만든
    work」에만 붙는다 — 지난 라운드까지 끝난 남의 work 을 닫으면 산출물이 통째로 죽는다.
    승격만 되고 등재가 실패한 경우는 **같은 호출을 다시 부르면 된다**(큐의 `reopen_work` 가
    「그 라운드 조각 0건」을 재시도로 본다).

    [주의] **`target_branch` 를 안 실으면 큐에 저장된 값을 쓴다** — 여기서 유도해 덮어쓰면
    ⑺ 이 전진시킨 브랜치가 조용히 `task/<work_id>/base` 로 원복된다.
    """
    wid = (work_id or "").strip()
    if not wid:
        raise RegisterError(
            "work_id 가 비었다 — 개선요청은 **이미 있는 분산 작업**을 여는 것이다. "
            "새 작업이면 `register_work(title=…, specs=[…])` 를 쓴다")
    if not specs:
        raise RegisterError("등록할 태스크가 없다")
    if int(round or 0) < 2:
        raise RegisterError(
            f"round={round!r} — 개선요청의 라운드는 2 이상이다(라운드 1은 **등록**이다). "
            f"큐가 아는 현재 라운드 + 1 을 실어라")
    _prep = _prepare_specs(specs, paths=paths, make_skeleton=make_skeleton,
                           gate=gate, heuristics=heuristics)
    post = poster or (lambda u, p: _post(u, p, token=token))
    if patch is not None:
        patcher = patch
    elif poster is not None:
        patcher = poster
    else:
        patcher = lambda u, p: _post(u, p, token=token, method="PATCH")   # noqa: E731
    # [중요] **2회차부터는 작업 브랜치가 이미 있어야 한다** — 라운드 1의 `require_base=False`
    #    는 *"work_id 를 받은 뒤에야 이름이 생긴다"* 가 근거였고(`#336` ①), 그 근거가 여기서는
    #    성립하지 않는다. 없으면 조각이 갈라질 자리가 없다.
    if require_base is None:
        require_base = True

    # ── ① 승격 (큐가 판정한다) ──────────────────────────────────────────────
    got = post(f"{queue_url}/api/v1/works/{wid}/reopen",
               {"project": paths.name, "round": int(round)})
    if isinstance(got, dict) and got.get("ok") is False:
        raise RegisterError(str(got.get("error") or got))
    opened = int((got or {}).get("round") or round)
    stored = str((got or {}).get("target_branch") or "")

    # ── ② 조각 등재 ────────────────────────────────────────────────────────
    try:
        r = _register_after_create(
            wid, specs, paths=paths, target_branch=(target_branch.strip() or stored),
            queue_url=queue_url, token=token, post=post, patcher=patcher,
            require_base=require_base, **_prep)
    except BaseException as e:                              # noqa: BLE001
        raise RegisterError(
            f"{e}\n[중요] 라운드 {opened} 등재가 실패했다 — work {wid} 는 **그대로 둔다**"
            f"(종결시키지 않는다). 같은 개선요청을 다시 부르면 이어서 등재한다") from e
    r.round = opened
    return r


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
                           post, patcher, require_base,
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
                             poster=post)
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
                   poster=None,
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
    # ── [중요] `depends_on` 은 **stem 으로 받고 task_id 로 보낸다** (`#343`, 사용자 결정) ──────
    #
    # 등재 시점에는 **task_id 가 아직 없다** — 큐가 등록하면서 발급한다. 그래서 호출자가 쓸 수
    # 있는 이름은 `stem` 뿐이다. 그런데 큐는 `task_id` 로 대조한다:
    #
    #     completed = {tid for tid, t in idx.tasks.items() if status in (verified,cancelled,failed)}
    #     if not all(d in completed for d in deps):   ← stem 은 여기 절대 안 들어간다
    #
    # 실측 2026-08-30: `.33` 이 `depends_on=['interactable_component']`(stem)로 보냈고, 세 조각이
    # **영원히 안 풀리는** 상태가 됐다. 조용히 막힌다 — 큐도 등재도 아무 말을 안 했다.
    #
    # [주의] **앞선 조각이 먼저 등록돼야 한다** — 목록 순서가 곧 의존 순서다. 뒤엣것을 가리키면
    #    아직 id 가 없으므로 **거절한다**(조용히 stem 을 그대로 보내면 같은 병이 재발한다).
    stem_to_id: dict = {}

    def _resolve_deps(spec) -> list:
        out = []
        for d in spec.depends_on or []:
            d = str(d).strip()
            if not d:
                continue
            if d in stem_to_id:
                out.append(stem_to_id[d])
            elif any(x.stem == d for x in specs):
                raise RegisterError(
                    f"{spec.stem}: `depends_on` 이 **뒤에 오는 조각**을 가리킨다 ({d}) — "
                    f"목록 순서가 의존 순서다. 앞으로 옮길 것")
            else:
                # [주의] 이미 task_id 인 경우도 받는다(재등록·수동 조립). 모르는 이름은 거절 —
                #    조용히 통과시키면 그 태스크가 영원히 안 풀린다.
                if not any(x.stem == d for x in specs) and len(d) >= 6 and " " not in d:
                    out.append(d)
                else:
                    raise RegisterError(
                        f"{spec.stem}: `depends_on` 의 `{d}` 는 이 work 의 stem 도 "
                        f"task_id 도 아니다")
        return out

    results: list[TaskResult] = []
    for spec in specs:
        r = TaskResult(stem=spec.stem)
        try:
            deps = _resolve_deps(spec)
        except RegisterError as e:
            r.error = str(e)
            results.append(r)
            continue
        try:
            reg = post(f"{queue_url}/api/v1/tasks", {
                "work_id": work_id,
                # work 와 같은 스탬프를 싣는다 — 서버가 대조한다(어긋나면 등록이 거절된다)
                "project": paths.name,
                "type": "code",
                "stem": spec.stem,
                "target_file": spec.target_file,
                "header_file": spec.header_file,
                "depends_on": deps,          # [중요] stem → task_id 로 바뀐 값 (`#343`)
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
            else:
                stem_to_id[spec.stem] = r.task_id      # 뒤 조각이 이 이름을 가리킬 수 있다
        except RegisterError as e:
            r.error = str(e)

        results.append(r)
    return results


