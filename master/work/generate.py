"""코드 생성 + 층2 통과 — **마스터의 몫은 여기서 끝난다** (PLAN §4.2 ②③④).

    작업장 ① 요청
       ↓
    마스터 ② 매니페스트로 프롬프트 조립 → 브로커로 라우팅
       ↓
    추론 노드 ③ 로컬 LLM 이 코드 생성 (무료)
       ↓
    마스터 ④ 층2 상용 모델 문법·API 검사 → **적합한 코드 뭉치**를 건넨다
       ↓
    작업장 ⑤ 적용 · 빌드 · 테스트 (마스터는 파일을 만지지 않는다)

🔴 **모토** (§4.3): 작성은 **무료 로컬 LLM**, 검증은 **상용 모델**. 값은 검증이라는
고레버리지 지점에만 쓴다. 이 모듈이 그 경계를 코드로 굳힌 것이다 —
생성은 브로커(무료), 검사는 `layer2_verify`(상용), **그리고 통과 못 하면 안 넘긴다.**

🔴 **추론은 stateless 다** (§4.2). Ollama 의 `context` 필드를 **의도적으로 재사용하지 않는다.**
라운드 간 누적은 git 이 운반한다(git-as-feedback-bus) — 프롬프트로 다시 넣으면 인바운드
토큰이 라운드마다 폭증한다. 두 경로를 섞지 말 것.

⚠️ **마크다운 펜스는 파이프라인이 지운다.** §4.4 실측에서 `qwen2.5-coder:14b` 의 유일한
결함이 이것이었다 — 코드 품질은 좋은데 ```cpp 로 감싸서 준다. 모델을 탓하지 말고 여기서 벗긴다.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from ..auth import auth_headers
from ..context_search.paths import ProjectPaths
from ..layer2_verify import verify_files
from ..verdict import Verdict
from . import manifest as mf

DEFAULT_BROKER = "http://localhost:8102"
CODER = "qwen2.5-coder:14b"          # §4.4 — UE5 C++ 생성용으로 확정
GEN_TIMEOUT = 900                    # 14b 는 느리다. 짧게 끊으면 받다 만 코드가 나온다

# 앞뒤를 감싼 펜스만 벗긴다. 본문 *중간*의 펜스는 남겨서 층2 가 잡게 한다 —
# 중간 펜스는 모델이 여러 파일을 뱉었거나 설명을 섞었다는 뜻이라 조용히 지우면 안 된다.
_FENCE = re.compile(r"\A\s*```[a-zA-Z+]*\s*\n(.*?)\n?\s*```\s*\Z", re.DOTALL)


class GenerateError(Exception):
    pass


@dataclass
class Generated:
    task_id: str
    code: str
    model: str = ""
    raw_len: int = 0
    stripped_fence: bool = False
    prompt_chars: int = 0

    @property
    def empty(self) -> bool:
        return not self.code.strip()


@dataclass
class Dispatch:
    """작업장에 건넬 결과. **`ok` 가 아니면 코드를 쓰지 말 것.**"""

    task_id: str
    generated: Generated | None = None
    verdict: Verdict | None = None
    error: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        # 🔴 fail-closed. verdict 가 없으면(검증을 못 돌렸으면) 통과가 아니다.
        return (not self.error and self.generated is not None
                and not self.generated.empty
                and self.verdict is not None and not self.verdict.blocked)

    @property
    def code(self) -> str:
        return self.generated.code if self.generated else ""

    def summary(self) -> str:
        if self.error:
            return f"{self.task_id}: 🔴 {self.error}"
        g, v = self.generated, self.verdict
        bits = [f"{len(g.code)}자 생성" if g else "생성 실패"]
        if g and g.stripped_fence:
            bits.append("펜스 제거")
        if v:
            bits.append(v.summary())
        mark = "✅" if self.ok else "🔴 차단"
        return f"{self.task_id}: {mark} — " + " · ".join(bits)


def strip_fence(text: str) -> tuple[str, bool]:
    """전체를 감싼 마크다운 펜스를 벗긴다. `(코드, 벗겼는지)`."""
    m = _FENCE.match(text or "")
    return (m.group(1), True) if m else ((text or "").strip(), False)


def build_prompt(*, manifest_body: str, instruction: str, target_file: str = "") -> str:
    """생성 프롬프트. **매니페스트를 그대로 싣는다** — 워커가 재검색하지 않게 (§4.2).

    🔴 인터페이스 동결을 명시한다. 클래스 단위 병렬 생성이 성립하려면 선언이 안 바뀌어야
    한다(§4.5) — 조각끼리 시그니처를 다르게 가정하면 컴파일에서야 드러난다.
    """
    parts = [
        "You are writing production Unreal Engine 5 C++ for an existing project.",
        "",
        "RULES — violating any of these makes the output unusable:",
        "1. The declarations you are given are FROZEN. Do not change signatures, "
        "class names, UPROPERTY/UFUNCTION specifiers, or the header layout.",
        "2. Fill in implementations only. Replace [PSEUDO] markers with real code.",
        "3. Output ONLY the file contents. No markdown fences, no commentary, "
        "no explanation before or after.",
        "4. Follow the conventions visible in the context below — this is an existing "
        "codebase, not a greenfield.",
        "",
        "=== CONTEXT COLLECTED BY THE SERVER (read this; do not search) ===",
        manifest_body.strip(),
        "=== END CONTEXT ===",
        "",
    ]
    if target_file:
        parts.append(f"Write the complete contents of: {target_file}")
    parts += ["", "TASK:", instruction.strip(), ""]
    return "\n".join(parts)


def call_broker(prompt: str, *, model: str = CODER, broker: str = DEFAULT_BROKER,
                token: str | None = None, timeout: int = GEN_TIMEOUT,
                num_ctx: int | None = None, caller=None) -> str:
    """브로커에 생성을 요청한다. **stateless** — `context` 를 주지도 받지도 않는다.

    🔴 **`num_ctx` 를 주라 — 안 주면 노드가 죽는다.** 실측 2026-08-08: BC-250 이 컨텍스트
    합성 배치 중 커널까지 멈췄다. 원인은 프롬프트 길이 자체가 아니라 **KV 할당 규모**였다:

    - 모델 `context_length = 262144`(256K). `num_ctx` 를 안 주면 그 전제로 잡는다
    - Ollama 가 요청마다 **컨텍스트 체크포인트**를 남긴다 —
      로그 실측 `created context checkpoint 1 of 32 ... size = 62.813 MiB`
    - **32 × 62.8 MiB ≈ 2.0 GB.** 그 보드의 여유가 **2.2 GB**(15.2GB 중 12.9GB 가 모델·UMA)
    - swap 은 **zram 8GB**(압축 RAM)라 물러설 곳이 없다 → 스래싱 → 커널 정지

    그래서 상한을 **요청에서** 건다. 노드 설정(`OLLAMA_KV_CACHE_TYPE=q4_0` 등)은 이미
    켜져 있었고 그것만으로는 부족했다.
    """
    options = {"temperature": 0}         # 재현성. §4.4 실측도 temperature=0 이었다
    if num_ctx:
        options["num_ctx"] = int(num_ctx)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options,
        # 35B 계열은 이게 없으면 사고 과정을 뱉어 토큰을 태운다 (§4.4).
        "think": False,
    }
    if caller:
        return caller(f"{broker}/api/generate", payload)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{broker}/api/generate", data=body, method="POST",
        headers={"Content-Type": "application/json", **auth_headers(token)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise GenerateError(f"브로커 HTTP {e.code}: "
                            f"{e.read().decode('utf-8', 'replace')[:200]}") from e
    except urllib.error.URLError as e:
        raise GenerateError(f"브로커에 닿지 않는다: {getattr(e, 'reason', e)}") from e
    except OSError as e:
        # 🔴 소켓 읽기 타임아웃은 `URLError` 가 아니라 `TimeoutError`(OSError 계열)로 올라온다.
        # 실측 2026-08-08: 컨텍스트 합성 배치가 이 예외로 **통째 크래시**했다 — 한 그룹이
        # 느렸을 뿐인데 남은 전부를 잃었다. 가장 흔한 실패 모드가 여기다(느린 모델).
        raise GenerateError(f"브로커 응답 대기 실패({type(e).__name__}): {e}") from e
    except (ValueError, TypeError) as e:
        # 응답이 JSON 이 아니거나 잘렸다 — 스트림이 중간에 끊긴 경우.
        raise GenerateError(f"브로커 응답을 해석할 수 없다: {e}") from e
    if res.get("error"):
        raise GenerateError(f"브로커 오류: {res['error']}")
    return res.get("response") or ""


def unload_model(model: str, *, broker: str = DEFAULT_BROKER,
                 token: str | None = None, timeout: int = 120) -> None:
    """모델을 내려 노드 메모리를 회수한다 (`keep_alive: 0`).

    🔴 **BC-250 처럼 UMA 로 메모리를 나눠 쓰는 노드에서 필요하다.** 실측 2026-08-08:
    합성 요청마다 여유가 ~170MB 씩 **단조 감소**한다(Ollama 프롬프트 캐시·컨텍스트
    체크포인트 누적). 모델을 내리면 **전부 회수된다**(266 → 14,445 MB).
    다음 요청이 자동으로 다시 적재하므로 올리는 쪽은 신경 쓸 필요가 없다.
    """
    payload = {"model": model, "prompt": "", "stream": False, "keep_alive": 0}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{broker}/api/generate", data=body, method="POST",
        headers={"Content-Type": "application/json", **auth_headers(token)})
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except (urllib.error.URLError, OSError) as e:
        raise GenerateError(f"모델 회수 실패: {e}") from e


def generate(paths: ProjectPaths, task_id: str, *, instruction: str,
             target_file: str = "", model: str = CODER, **kw) -> Generated:
    """매니페스트를 읽어 코드를 생성한다. 매니페스트가 없으면 **거부한다.**

    없는 채로 진행하면 로컬 LLM 이 grounding 0 으로 짜게 되고, 그건 §4.3 이 실측한
    환각(없는 API 호출)이 나오는 조건 그대로다. 조용히 진행하지 않는다.
    """
    body = mf.read(paths, task_id)
    if body is None:
        raise GenerateError(
            f"컨텍스트 매니페스트가 없다: {mf.manifest_path(paths, task_id)} — "
            "grounding 없이 생성하지 않는다 (§4.3)")
    prompt = build_prompt(manifest_body=body, instruction=instruction,
                          target_file=target_file)
    raw = call_broker(prompt, model=model, **kw)
    code, stripped = strip_fence(raw)
    return Generated(task_id=task_id, code=code, model=model, raw_len=len(raw),
                     stripped_fence=stripped, prompt_chars=len(prompt))


def dispatch(paths: ProjectPaths, task_id: str, *, instruction: str,
             target_file: str = "", model: str = CODER,
             verifier=None, **kw) -> Dispatch:
    """생성 → 층2 → 인계 준비. **마스터가 하는 일의 끝이다.**

    🔴 층2 를 통과하지 못하면 `ok=False` 다. 작업장은 `ok` 만 보고 판단하면 된다 —
    "코드가 왔으니 일단 적용" 이 되지 않게 하는 것이 이 반환값의 목적이다.
    """
    d = Dispatch(task_id=task_id)
    try:
        d.generated = generate(paths, task_id, instruction=instruction,
                               target_file=target_file, model=model, **kw)
    except GenerateError as e:
        d.error = str(e)
        return d

    if d.generated.empty:
        d.error = "생성 결과가 비었다"
        return d
    if d.generated.stripped_fence:
        d.notes.append("마크다운 펜스를 벗겼다 (§4.4 알려진 결함)")

    name = target_file or f"{task_id}.cpp"
    verify = verifier or verify_files
    d.verdict = verify([(name, d.generated.code)])
    return d
