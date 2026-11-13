"""컨텍스트 MD 합성 오케스트레이션 (중 1.2).

원본: `AgentTest/watcher/context.py` 의 `_group_files` · `_process_directory_group` ·
`process_commit` · `initial_context_build`.

[중요] **원본과 갈라지는 지점 넷.**

⑴ **LLM 은 브로커를 거친다.** 원본은 `claude`/`agy` CLI 를 subprocess 로 부른다. 마스터는
   도구 호출을 하지 않는 인프라라(§2) CLI 가 없고, 대신 브로커(8102)가 Ollama 노드를 앞에
   둔다. 그래서 원본의 `task_type` 화이트리스트 라우팅은 **모델 선택**으로 번역된다:
   컨텍스트 합성 = 35B(범용·한국어 산문), 코드 생성 = 14b coder. **두 모델이 서로 다른
   기계에 핀돼 있어 경합하지 않는다** — 원본이 한 PC 에서 쿼터를 나눠 쓰던 문제가 없다.

⑵ **배치 서킷브레이커.** 원본은 호출 단위로 백엔드를 차단했다(Claude 5h·agy 600s). 우리
   실패 모드는 다르다 — 브로커/노드가 죽으면 **남은 전부가 같은 이유로 실패**한다. 연속
   실패가 임계값에 닿으면 배치를 **중단**한다. 1,600번을 태워 0개를 만드는 것을 막는다.
   원본의 결정("한도 소진 시 폴백도 건너뛰고 None — 다른 백엔드로 트래픽 몰리는 과부하
   방지")과 같은 취지다.

⑶ **영구 유실을 카나리로 남긴다.** 원본이 판별 기준을 명확히 적어 뒀다 — *"skip 후 워터마크가
   전진하느냐"*. 예외를 삼키고 정상 리턴해 워터마크가 전진하는 곳만 대상이고, 원본은 그게
   딱 2곳이었다(컨텍스트 MD 유실 / 벡터 색인 누락). 우리 색인기도 워터마크를 전진시키므로
   **그룹 실패는 곧 영구 유실**이다 — `Stats.lost` 로 세고 사유를 들고 나온다.

⑷ **CP949.** 실측 44%(723/1,654)가 CP949 다. `source_text` 를 거쳐 읽는다 — 여기서 mojibake 가
   섞이면 **한글 주석이라는 가장 밀도 높은 신호가 조용히 쓰레기가 된다.**
"""
from __future__ import annotations

import sys

import time
import threading
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .. import source_text
from ..context_search.paths import ProjectPaths
from ..context_search.search_log import search_context
from ..graph import class_graph as cg, dependency as dep, parse as gparse
from ..work.generate import DEFAULT_BROKER, GenerateError, call_broker, unload_model
from ..work import llm_policy
from . import md as md_mod, prompt as prompt_mod, verify as verify_mod

# 컨텍스트 합성용 모델 — [중요] **Gemma 로 바꿨다** (실측 2026-08-08).
#
# 같은 3그룹에 네 모델을 돌려 **사실 게이트 통과율**로 비교했다:
#
#   Gemma4 E4B   3/3 · 12~32초   ← 채택. 4B급이라 UMA 보드 메모리 압박이 없다
#   Gemma3 12B   3/3 · 16~46초   ← 대안(.2, 전용 VRAM)
#   Qwen 35B     3/3 · ~11초     ← 빠르지만 요청당 ~170MB 누적 (BC-250 정지 사고)
#   Qwen 14b     형식 실패        ← frontmatter 닫는 줄을 빼먹는다(복구 로직으로 구제)
#
# **4B 가 35B 와 같은 통과율**인 것이 요점이다 — 지금 실패 유형은 문장력이 아니라 **지시
# 준수**다. 원본도 로컬 LLM 기본값으로 Gemma 4 E4B 를 골랐고, `context_review` 만 화이트
# 리스트에서 뺐다(*"4B 가 컨텍스트+리뷰 **통합** 프롬프트를 일관되게 처리할지 미검증"*).
# [중요] **우리는 리뷰를 붙이지 않으므로 그 제외 사유가 없다.**
SYNTH_MODEL = "agy"                  # 사용자 2026-10-08: 제미나이 1차, 로컬 LLM 폴백
LOCAL_MODEL = "gemma4:e4b"
FALLBACK_MODEL = "gemma3:12b"            # .2 전용 VRAM. E4B 가 얕을 때
HEAVY_MODEL = "hf.co/bartowski/Qwen_Qwen3.5-35B-A3B-GGUF:IQ2_M"   # 되돌릴 때만
SYNTH_TIMEOUT = 600

# 사용자 2026-10-08: 제미나이 1차, 로컬 LLM 폴백. 순서는 여기 한 곳이다.
# 호출 오류·형식 거부·사실 거부 모두 다음 모델로 간다. 각 모델은 그룹당 한 번만 시도한다.
# 모든 시도는 같은 md.finalize와 사실 게이트를 통과해야 하며 claude 제외는 유지한다.
SYNTH_CHAIN = (*llm_policy.CLOUD_LANES, LOCAL_MODEL)
_CLI_LANES = ("claude", "agy", "codex")          # `ontology.synth.CLI_MODELS` 와 같은 레인 이름
_CHAIN_EXCLUDED = ()

# [중요] KV 컨텍스트 상한. **이것이 BC-250 정지 사고의 진짜 원인이었다** — 모델 기본
# `context_length` 가 **262144(256K)** 라, 안 주면 그 전제로 KV 와 컨텍스트 체크포인트를
# 잡는다(실측 `checkpoint 1 of 32 ... 62.813 MiB` → 32개면 ~2.0GB, 보드 여유는 2.2GB).
# [중요] **8192 로 올렸다** (2026-08-08) — 관련 문서 발췌를 400 → 1,500자로 키웠기 때문이다.
# 두 값은 **함께 움직여야 한다**: 발췌만 늘리면 컨텍스트 창을 넘어 뒤가 잘리고, 모델은
# 그 사실을 말하지 않는다(조용히 앞부분만 본다).
#
# 안전한 이유: 합성 모델이 `gemma4:e4b`(4B급)로 바뀌어 KV 가 35B 때보다 훨씬 작다.
# [중요] 그래도 **35B(`HEAVY_MODEL`)로 되돌린다면 이 값을 다시 재라** — 그 조합이 보드를
# 넘어뜨렸다(리포트 10 §8).
SYNTH_NUM_CTX = 8192

# [중요] 몇 그룹마다 모델을 내렸다 올릴지. **`num_ctx` 만으로는 부족하다** — 실측 2026-08-08:
# 요청마다 여유가 935 → 880 → 680 → 447 → 259 MB 로 **단조 감소**한다(요청당 ~170MB).
# 누적 주체는 Ollama 의 프롬프트 캐시·컨텍스트 체크포인트이고, **모델을 내리면 전부
# 회수된다**(실측 266 → 14,445 MB). 그래서 주기적으로 내린다.
#
# [중요] **Gemma4 E4B 로 바꾼 뒤에는 0 이 기본이다** — 4B급이라 누적이 문제되는 규모가 아니고,
# 주기적 내리기는 재적재 비용만 낸다. 35B(`HEAVY_MODEL`)로 되돌린다면 5 로 올릴 것:
# 그때는 적재 후 여유 ~1,200MB / 요청당 ~170MB 라 5회면 ~350MB 가 남는다.
UNLOAD_EVERY = 0

# 연속 실패 임계값. 이보다 이어지면 배치를 중단한다 (위 ⑵).
CIRCUIT_THRESHOLD = 3

HEADER_EXTS = {".h", ".hpp", ".inl"}


class SynthError(RuntimeError):
    """합성을 시작할 수 없다. [중요] 삼키면 빈 결과가 정상처럼 보인다."""


@dataclass
class GroupResult:
    key: str
    files: list[str]
    written: bool = False
    reason: str = ""          # 쓰지 않았다면 왜
    chars: int = 0
    prompt_chars: int = 0
    elapsed_ms: int = 0
    verify: "verify_mod.Report | None" = None
    dry_ok: bool = False      # dry-run 에서 검증까지 통과했나
    related_fixed: int = 0            # `related_classes` 를 스키마 형태로 고친 줄 수 (`#382`)
    related_unresolved: list = field(default_factory=list)   # 못 푼 항목 — 지어내지 않는다
    tokens_in: int = 0        # 브로커가 준 사용량 (`#713`) — 노드가 안 주면 0
    tokens_out: int = 0
    digest: str = ""          # 프롬프트에 요약본을 썼으면 그 요약 (`pydigest`, `#711`)
    model: str = ""           # 형식 게이트를 통과한 결과를 낸 모델 (`#727`)
    attempts: list = field(default_factory=list)   # 사슬 시도 기록 — `모델 결과` 문자열들
    attempt_records: list[str] = field(default_factory=list)  # 원문·판정 JSON 경로
    policy_attempts: list = field(default_factory=list)
    needs_revalidation: bool = False
    source_fingerprint: str = ""

    @property
    def passed(self) -> bool:
        """문서를 쓸 수 있는 상태였나 (dry-run 포함)."""
        return self.written or self.dry_ok

    @property
    def lost(self) -> bool:
        """[중요] 영구 유실인가 — LLM 실패/게이트 거부로 문서가 안 생겼는가."""
        return not self.passed and self.reason != "변화 없음"


@dataclass
class Stats:
    groups: int = 0
    written: int = 0
    refused: int = 0            # 형식 게이트 거부 (σ.7-B) — 기존 파일 유지
    unfactual: int = 0          # [중요] 사실 게이트 거부 — 소스 실측과 어긋난다
    failed: int = 0             # LLM 실패
    skipped: int = 0            # 이미 있고 안 바뀜
    aborted: str = ""           # 서킷브레이커가 끊었으면 사유
    unloads: int = 0            # 캐시 회수를 위해 모델을 내린 횟수
    retried: int = 0            # 보류에서 다시 끌어온 그룹 수 (`#377`)
    tokens_in: int = 0          # 이 배치가 쓴 입력·출력 토큰 합 (`#713`)
    tokens_out: int = 0
    digested: int = 0           # 프롬프트에 요약본을 쓴 그룹 수 (`#711`)
    workers: int = 1            # 동시 합성 수 (`#715`)
    fallback_passed: int = 0    # 대체 사슬의 다음 모델이 통과시킨 그룹 수 (`#727`)
    elapsed_ms: int = 0
    encodings: source_text.EncodingTally = field(default_factory=source_text.EncodingTally)
    results: list[GroupResult] = field(default_factory=list)

    @property
    def lost(self) -> int:
        """[중요] 문서가 생기지 않은 그룹 수. 이 숫자가 곧 영구 유실이다."""
        return self.refused + self.unfactual + self.failed

    @property
    def pass_rate(self) -> str:
        """사실 게이트 통과율. 모델 적합도의 지표다."""
        tried = self.written + self.refused + self.unfactual + self.failed
        return f"{self.written}/{tried}" if tried else "0/0"

    @property
    def summary(self) -> str:
        s = (f"그룹 {self.groups} → 통과 {self.written}"
             f" · 건너뜀 {self.skipped} · {self.elapsed_ms}ms"
             f" · 토큰 입력 {self.tokens_in} · 출력 {self.tokens_out}")
        if self.digested:
            s += f" · 요약본 {self.digested}"
        if self.workers > 1:
            s += f" · 동시 {self.workers}"
        if self.fallback_passed:
            s += f" · 대체 모델 통과 {self.fallback_passed}"
        if self.refused:
            s += f" · [중요] 형식 거부 {self.refused}"
        if self.unfactual:
            s += f" · [중요] 사실 거부 {self.unfactual}"
        if self.failed:
            s += f" · [중요] LLM 실패 {self.failed}"
        if self.retried:
            s += f" · 보류 재시도 {self.retried}"      # `#377` — 다시 끌어온 그룹
        if self.unloads:
            s += f" · 모델 회수 {self.unloads}회"
        if self.aborted:
            s += f" ·  중단({self.aborted})"
        return f"{s} · {self.encodings.summary}"


def _log(msg: str) -> None:
    """합성 경로의 사유 기록 (`#285`). 저널에 실린다 — 유닛이 stderr 를 잡는다.

    [중요] 원전 `watcher/context.py` 는 같은 자리에서 `common.log` 를 부른다. 우리 이식이
    사유를 버린 것이 **이식 누락**이었다.
    """
    print(f"[synth] {msg}", file=sys.stderr, flush=True)


# 🔴 그룹을 **디스크 기준으로 채운다** (`#367`, 2026-09-06)
#
# [중요] 합성은 **변경된 파일만** 받는다(`events/consumer.py:_synthesize(changed=…)`). 그래서
#    커밋이 `.h` 하나만 바꾸면 그 그룹에 `.h` 뿐이고, 사실 게이트는 **짝 파일의 살아 있는 코드를
#    못 본다** → `.cpp` 에서 실제로 호출되는 이름이 *"주석에만 있는 식별자"* 로 거부된다.
#
#    실측 2026-09-05~06 (`#367`): `NSInteractionWorldSubsystem` 이 `SetDetected`·`SetFocused`·
#    `TriggerInteraction`·`ANSPlayerController` 로 거부됐는데, 그 셋은 **같은 그룹 `.cpp` 의
#    실제 호출**이다(67·78·86행). 두 파일을 함께 주면 유령이 아니다(재현 확인).
#
# [중요] **문서는 그룹 단위다** — 한 문서가 `.h`+`.cpp` 를 함께 서술한다. 그러니 판정도 그룹
#    전체를 봐야 한다(`#270` 이 이미 *"그룹 전체를 한 몸으로 본다"* 고 정한 규칙이고, 그 전제가
#    **입력이 완전할 때만** 성립했다).
# [주의] 없는 파일을 지어내지 않는다 — **디스크에 있는 것만** 더한다.
_PAIR_EXTS = (".h", ".hpp", ".inl", ".cpp", ".cc", ".c")


def _index_only(paths) -> bool:
    """프로필 `kind` 가 **UE 가 아닌** 타입인가 (`#693` · `#695` — `index_only`·`code`).
    모르면 False — 종전(unreal) 판정을 쓴다. [주의] 이름은 역사적이다: 묻는 것은 「UE 아님」이다."""
    try:
        from ..projects import profile                        # noqa: PLC0415
        return profile.is_non_unreal(paths.name)
    except Exception:                                         # noqa: BLE001
        return False


def project_symbols(paths) -> set:
    """🔴 **프로젝트 전체의 실재 심볼** — 클래스 이름 + 메서드 이름 (`#367`, 2026-09-06).

    [중요] **사실 게이트가 파일 하나만 보고 판정하면 안 되는 자리가 있다.** 그룹을 채워도
    (`complete_group`) 다른 파일에 선언된 것을 서술하면 여전히 유령으로 잡힌다 — 실측:
    `NSPropsBase` 주석이 *"서브클래스(예: ANSLootableChest)"* 라고 썼는데 그 클래스는
    `NSLootableChest.h:27` 에 **실재**한다.

    [중요] **게이트를 무디게 하는 것이 아니라 판정 근거를 넓히는 것이다.** 지어낸 이름은
    클래스 그래프에도 없으므로 그대로 잡힌다(2026-08-12 의 「없는 enum 멤버」가 그 부류).
    [주의] 그래프가 없으면 그래프 몫은 빈 집합이다. 그래프는 색인기가 **커서가 걸은 커밋만**
    갱신하므로 뒤처질 수 있다 — 실측 2026-09-12 NS: 커서가 갇혀 `ANSCharacterBase` 가 그래프에
    없었고 실재 클래스가 유령으로 거부됐다. 그래서 아래 `project_live_identifiers` 를 더한다.
    """
    names: set = set()
    try:
        from ..graph import db as gdb
        if gdb.exists(paths):
            with gdb.lock():
                con = gdb.connect(paths)
                names = {r[0] for r in con.execute("SELECT name FROM classes") if r and r[0]}
                names |= {r[0] for r in con.execute("SELECT method_name FROM methods")
                          if r and r[0]}
    except Exception:                                        # noqa: BLE001
        # [주의] 판정 근거를 못 얻은 것이지 통과가 아니다 — 빈 집합이면 종전 판정 그대로다
        names = set()
    names = {n for n in names if isinstance(n, str) and len(n) > 2}
    try:
        names |= project_live_identifiers(paths)
    except Exception:                                        # noqa: BLE001
        pass                            # 근거를 못 넓힌 것이지 통과가 아니다 — 그래프 몫만 쓴다
    return names


# 저장소 소스 디렉토리 → (파일 서명, 식별자 집합). 배치 하나가 그룹마다 부르므로 캐시한다.
_LIVE_CACHE: dict = {}


def project_live_identifiers(paths) -> set:
    """🔴 **프로젝트 전체 소스의 살아 있는 코드**에 등장하는 식별자 (2026-09-13).

    [중요] **그래프는 클래스·메서드 이름만 안다** — 그래서 실재하는 이름이 유령으로 잡혔다.
    실측 2026-09-13 NS (재시도마다 운에 따라 거부·통과가 갈렸고, 한 그룹은 포기됐다):

        IGenericTeamAgentInterface   엔진 인터페이스 — `NSPlayerController.h:28` 이 상속한다
        CurrentVulnerableState       멤버 변수 — `NSCharacterBase.h:233` · `.cpp` 에서 쓴다

    [중요] **게이트의 계약은 그대로다** — `verify` 의 주석 제거·식별자 규칙을 그대로 쓴다.
    프로젝트 어디에서도 코드에 없고 주석에만 있는 이름, 아예 없는 이름은 여전히 잡힌다.
    [주의] **대가**: 한 파일에서 주석 처리됐지만 다른 파일 코드에 살아 있는 이름은 통과한다 —
    `#367` 과 같은 판단이다(프로젝트에 실재하면 유령이 아니다).
    [주의] **디스크 기준이다** (`git ls-files` 가 아니다) — 합성이 소스를 디스크에서 읽으므로
    판정 근거도 같은 곳에서 온다. 파일 서명(경로·mtime·크기)이 같으면 다시 읽지 않는다.
    """
    # [중요] 경계는 `paths.scope` 다 (`#693`) — 루트가 여럿일 수 있고 제외가 있다(`ggml/`).
    src = paths.source
    roots = [d for d in paths.source_dirs if d.is_dir()]
    if not roots:
        return set()
    sig = []
    for f in sorted(p for d in roots for p in d.rglob("*")):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(paths.repo).as_posix()
        except ValueError:
            continue
        if not paths.scope.contains(rel, gparse.PARSE_EXTS):
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        sig.append((str(f), st.st_mtime_ns, st.st_size))
    key = tuple(sig)
    ckey = f"{paths.repo}|{paths.scope!r}"
    hit = _LIVE_CACHE.get(ckey)
    if hit is not None and hit[0] == key:
        return hit[1]
    out: set = set()
    for name, _mtime, _size in sig:
        d = source_text.read(Path(name))
        if d is None:
            continue
        # `#732` — 주석 규칙은 확장자가 정한다(경로 없이 부르면 C++ 규칙으로 `.py` 를 읽는다)
        out |= verify_mod.identifiers(
            verify_mod.strip_comments(d.text, lang=verify_mod.lang_for(name))[0])
    _LIVE_CACHE[ckey] = (key, out)
    return out


def complete_group(repo_root, key: str, files: list[str]) -> list[str]:
    """그룹 키의 **짝 파일을 디스크에서 채운다**. 원소 순서는 `group()` 규약과 같다."""
    have = {str(f).replace("\\", "/") for f in files}
    for ext in _PAIR_EXTS:
        cand = f"{key}{ext}"
        if cand not in have and (Path(repo_root) / cand).is_file():
            have.add(cand)
    return sorted(have, key=lambda f: (0 if Path(f).suffix.lower() in HEADER_EXTS else 1,
                                       Path(f).name))


def group(files: list[str]) -> dict[str, list[str]]:
    """소스 파일 → `{부모/stem: [파일…]}`.

    같은 디렉토리의 같은 stem(`.h`/`.cpp` 쌍)이 **한 문서**를 공유한다. 원본과 같은 규칙이고,
    `md.read_source_commit` 이 소스→문서 경로를 되짚을 때도 이 규칙을 쓴다.

    각 그룹 안에서 **헤더를 먼저** 둔다 — 인터페이스를 읽고 구현을 보는 순서다.
    """
    groups: dict[str, list[str]] = {}
    for f in files:
        p = Path(f)
        groups.setdefault(str(p.parent / p.stem), []).append(f)
    for key in groups:
        groups[key].sort(key=lambda f: (0 if Path(f).suffix.lower() in HEADER_EXTS else 1,
                                        Path(f).name))
    return groups


def doc_path(paths: ProjectPaths, key: str) -> Path:
    """그룹 키 → 컨텍스트 MD 경로."""
    return paths.context / f"{key}.md"


_RELATED_OPEN_LOCK = threading.Lock()


def _open_related(paths):
    # Chroma 공유 시스템의 최초 초기화는 여러 합성 스레드에서 겹치지 않는다.
    from ..context_search.search import open_search
    with _RELATED_OPEN_LOCK:
        return open_search(paths.name)


def _close_related(searcher):
    try:
        searcher.close()
    except Exception as e:                                  # noqa: BLE001
        _log(f"[related] 검색기 해제 실패 — {type(e).__name__}: {e}")


class _BatchRelated:
    """배치 소유 검색기. coordinator에서만 열고 검색하며 worker에는 목록만 준다."""

    def __init__(self, paths, *, searcher=None, enabled=True):
        self.paths = paths
        self.searcher = searcher
        self.attempted = searcher is not None or not enabled
        self.owned = False

    def collect(self, key, files):
        if not self.attempted:
            self.attempted = True
            try:
                self.searcher = _open_related(self.paths)
                self.owned = True
            except Exception as e:                          # noqa: BLE001
                _log(f"[related] 검색기를 열지 못했다 ({self.paths.name}) — "
                     f"{type(e).__name__}: {e} · 이번 배치는 재초기화하지 않는다")
        if self.searcher is None:
            return []
        out = doc_path(self.paths, key)
        d = source_text.read(out) if out.is_file() else None
        return collect_related(self.paths, key, files, d.text if d else "",
                               searcher=self.searcher)

    def close(self):
        if self.owned:
            _close_related(self.searcher)
            self.owned = False


def collect_related(paths: ProjectPaths, key: str, files: list[str], existing: str,
                    *, searcher=None) -> list:
    """관련 컨텍스트 문서 3개 (RAG 채널). **원본 `_build_related_context` 그대로.**

    질의는 `파일 stem + 기존 문서 본문 앞 200자` — 기존 문서가 없으면 stem 만으로 돈다.
    **자기 문서는 제외**한다(원본과 같다).
    """
    owned = searcher is None
    if owned:
        try:
            searcher = _open_related(paths)
        except Exception as e:                          # noqa: BLE001
            # [중요] **조용히 비우지 않는다** (`#285`). 관련 문서 0건은 프롬프트를 약하게
            #    만들고, 약한 프롬프트가 「다른 파일을 서술」로 이어진다(NS 실측). 그 인과를
            #    나중에 되짚으려면 여기서 말해야 한다.
            _log(f"[related] 검색기를 열지 못했다 ({paths.name}) — {type(e).__name__}: {e}")
            return []
    out: list = []
    try:
        stem = Path(files[0]).stem if files else key.rsplit("/", 1)[-1]
        query = stem
        if existing:
            query += " " + md_mod.strip_comments(existing).strip()[:prompt_mod.RELATED_QUERY_BODY]
        self_doc = f"{key}.md"
        with search_context(task_type="context_synthesis", caller="context_synth",
                            context_key=key):
            hits = searcher.search(query, limit=prompt_mod.RELATED_LIMIT + 1,
                                   excerpt=prompt_mod.RELATED_EXCERPT)
        for hit in hits:
            if hit.file_id == self_doc:
                continue
            # [중요] **요약 절로 한정한다** (사용자 확정 2026-08-08).
            # `hit.excerpt` 는 임베딩 텍스트, 곧 「## 요약」 절이다. 본문 전체를 넣어 봤고
            # (951·762·1500자) 통과했지만 **요약으로 한정하기로 했다** — 원본이 그 절을
            # *"이 섹션만 벡터 임베딩 대상 — 짧고 검색 친화적으로"* 로 설계한 이유가
            # 그대로 여기에도 적용된다: 관련 문서는 **네비게이션 신호**지 읽을 자료가 아니다.
            # 「개선 필요 사항」의 기술 부채 서술까지 넣으면 협력 관계 신호가 희석된다.
            out.append((hit.file_id, (hit.excerpt or "")[:prompt_mod.RELATED_EXCERPT]))
            if len(out) >= prompt_mod.RELATED_LIMIT:
                break
    except Exception as e:                              # noqa: BLE001
        _log(f"[related] 검색 실패 ({key}) — {type(e).__name__}: {e} · "
             f"관련 문서 {len(out)}건으로 진행한다")
        return out
    finally:
        if owned:
            _close_related(searcher)
    return out


def collect_grounding(paths: ProjectPaths, files: list[str]) -> prompt_mod.Grounding:
    """관계 그래프에서 실측 근거를 모은다. **베스트에포트** — 그래프가 없으면 빈 근거다.

    [중요] 그래프가 없다고 합성을 막지는 않는다. 다만 `Grounding.empty` 가 True 면 호출자가
    그 사실을 통계에 남길 수 있다 — 근거 없이 만든 문서와 있는 문서를 나중에 구분해야 한다.
    """
    g = prompt_mod.Grounding()
    declared: list[str] = []
    for f in files:
        try:
            classes, _ = gparse.parse_file(paths.repo / f)
        except gparse.ParserUnavailable as e:
            # [중요] **말한다.** 선언 근거가 없으면 모델이 파일을 혼동하고, 그것이 사실 게이트
            #    거부로 나타난다(NS 실측 2026-08-23: 「실측 선언 클래스를 하나도 언급하지
            #    않았다」 계열). 사유가 없으면 모델 탓과 환경 탓을 구분할 수 없다.
            _log(f"[grounding] 파서 없음 — 선언 근거 없이 진행한다 ({f}): {e}")
            break
        declared.extend(c["name"] for c in classes)
    g.declared_classes = sorted(dict.fromkeys(declared))
    for c in g.declared_classes[:prompt_mod.GROUNDING_LIMIT]:
        anc = cg.find_ancestors(paths, c, max_depth=3)
        if anc:
            g.ancestors[c] = anc
        sib = cg.find_siblings(paths, c)
        if sib:
            g.siblings[c] = sib
    seen_dep: set[str] = set()
    seen_inc: set[str] = set()
    for f in files:
        seen_dep.update(dep.dependents(paths, f, depth=1))
        seen_inc.update(dep.dependencies(paths, f, depth=1))
    g.dependents = sorted(seen_dep - set(files))
    g.includes = sorted(seen_inc - set(files))
    return g


def _remember(paths, key: str, files: list, res, commit: str, dry_run: bool):
    """거부는 **보류로 남기고**, 성공하면 지운다 (`#377` ⓑ).

    [중요] **자리가 여기다** — 배치 루프가 아니라 `synthesize_group` 이다. `one`·`fill`·`all`·
    소비자가 전부 이 함수를 거치므로, 루프에 두면 **경로에 따라 기록이 갈린다**(실측: `one` 으로
    거부가 났는데 보류가 안 남았다).
    [주의] dry-run 은 적지 않는다 — 쓰지 않은 실행이 목록을 바꾸면 안 된다.
    """
    if dry_run:
        return res
    from . import pending as pending_mod
    try:
        if res.written:
            pending_mod.clear(paths, key)
        elif res.reason and res.reason != "변화 없음":
            pending_mod.record(paths, key, list(files), res.reason, commit=commit)
    except Exception:                                        # noqa: BLE001
        pass                            # 기록이 합성을 죽이지 않는다
    return res


def _prompt_bodies(paths, bodies: dict, limit: int | None) -> tuple[dict, str]:
    """프롬프트에 넣을 본문. 🔴 **비UE 프로젝트의 긴 `.py` 는 요약본**으로 바꾼다 (`#711`).

    [중요] 사용자 결정 2026-10-03: 비UE 에만 · 함수 본문을 덜고 구조·독스트링·주석을 남긴다
       (`pydigest`). UE 프로젝트는 **종전 그대로**(앞에서 자르기) — 재합성 비용·결과를 바꾸지 않는다.
    [주의] 사실 게이트는 호출자가 **원본 `bodies`** 로 돌린다. 여기 결과는 프롬프트에만 쓴다.
    `limit=None`(상용 CLI 레인, `#782`)이면 자르는 것이 없으므로 요약하지 않는다 — 원본 그대로.
    """
    if limit is None:
        return bodies, ""
    if not _index_only(paths) or sum(len(b) for b in bodies.values()) <= limit:
        return bodies, ""
    from . import pydigest                                    # noqa: PLC0415
    out, notes = dict(bodies), []
    for f, body in bodies.items():
        if not f.endswith(".py"):
            continue
        d = pydigest.digest(body)
        if d is None:
            notes.append(f"{f} 파싱 실패 — 앞에서 자른다")
            continue
        out[f] = d.text
        notes.append(f"{f} {d.summary}")
    total = sum(len(b) for b in out.values())
    if notes and total > limit:
        notes.append(f"요약 뒤에도 {total}자 > 상한 {limit} — 넘는 부분은 잘린다")
    return out, " · ".join(notes)


def _is_cli(model: str) -> bool:
    return model.partition(":")[0] in _CLI_LANES


def _chain_for(model: str | None, chain) -> list[str]:
    """이 그룹이 탈 모델 순서 (`#727`).

    model=None은 기본 SYNTH_CHAIN, 명시 모델은 그 하나다(수동 --model/--fallback).
    claude는 빼고 중복 모델은 한 번만 남기며 받은 순서는 그대로 유지한다.
    """
    if chain is None:
        chain = SYNTH_CHAIN if model is None else (model,)
    out: list[str] = []
    for m in chain:
        if m.partition(":")[0] in _CHAIN_EXCLUDED:
            _log(f"[사슬] {m} 는 합성 사슬에서 뺀다 — 쓰는 일의 레인 정책 (#727)")
            continue
        if m not in out:
            out.append(m)
    return out


def _generate(prompt: str, model: str, *, broker: str, caller, cli, usage: dict,
              tree=None) -> str:
    """한 번의 생성. 로컬 → 브로커, `codex`/`agy` → 마스터의 상용 CLI (`#727`).

    [중요] 상용 호출은 `layer2_verify.call_*_why` 공용 진입을 탄다 — 그 진입이 `usage.sink` 로
    감싼 구간에서 사용량 한 줄을 남긴다(`#728`·`#733`). 실패는 `GenerateError` 로 통일한다.
    `cli` 는 테스트 주입(`(lane, prompt, timeout) -> str | None`).
    """
    if not _is_cli(model):
        return call_broker(prompt, model=model, broker=broker, timeout=SYNTH_TIMEOUT,
                           num_ctx=SYNTH_NUM_CTX, caller=caller, usage=usage)
    lane, _, sub = model.partition(":")
    if sub:
        raise GenerateError(f"{lane} 는 모델 지정을 받지 않는다: {model}")
    if cli is not None:
        response = cli(lane, prompt, SYNTH_TIMEOUT)
        out, why = response if isinstance(response, tuple) else (response, "")
    else:
        from .. import layer2_verify as l2                        # noqa: PLC0415
        # `#848` — 상용 CLI 는 고정 트리에서 돈다. 못 만들면 `GenerateError` 로 이 레인만 실패한다
        wd = {} if tree is None else {"workdir": str(tree())}
        if lane == "codex":
            out, _events, why = l2.call_codex_why(prompt, timeout=SYNTH_TIMEOUT, **wd)
        elif lane == "agy":
            out, why = l2.call_agy_why(prompt, timeout=SYNTH_TIMEOUT, **wd)
        else:
            out, why = l2.call_claude_why(prompt, timeout=SYNTH_TIMEOUT)
    if why or not out or not str(out).strip():
        raise GenerateError(f"{lane} CLI 가 응답하지 않았다 — {why or '빈 출력'}")
    return out


class _AttemptRecord:
    """실제 모델 시도 원문과 판정의 원자적 스냅샷. 기록 실패는 합성 판정을 바꾸지 않는다."""

    def __init__(self, paths, *, key, files, commit, model, prompt, declared, dry_run,
                 prompt_limit=None):
        self.enabled = not dry_run
        self.saved = False
        self.path = paths.root / "synth_attempts" / f"{uuid.uuid4().hex}.json"
        try:
            from ..projects import profile
            kind = profile.load(paths.name).get("kind") or "unknown"
        except Exception:                                  # noqa: BLE001
            kind = "unknown"
        self.data = {"schema": 1, "attempt_id": self.path.stem, "project": paths.name,
                     "group": key, "files": list(files), "commit": commit,
                     "model": model, "project_kind": kind, "declared": list(declared),
                     "prompt": prompt, "prompt_limit": prompt_limit,   # None = 무제한 (`#782`)
                     "raw": None, "raw_received": False,
                     "format": None, "facts": None, "status": "generating",
                     "started_at": time.time()}
        self.update()

    def update(self, **fields):
        self.data.update(fields)
        if not self.enabled:
            return
        tmp = self.path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(tmp, self.path)
            self.saved = True
        except Exception as e:                              # noqa: BLE001
            _log(f"[attempt] 기록 실패 ({self.path}) — {type(e).__name__}: {e}")
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


class _LazyTree:
    """상용 CLI 의 작업 디렉터리 — 리뷰 커밋(없으면 미러 HEAD)의 고정 트리를 **처음 쓸 때** 만든다 (`#848`).

    🔴 agy·codex 는 workdir 없이 부르면 서비스 작업 폴더(`ax-indexer` = 마스터 라이브 트리)에서
    명령을 돌린다 — `#844` 가 리뷰 큐에서 막은 것과 같은 부류다. 로컬만 타거나 dry-run 이면 만들지 않는다.
    병렬 묶음이 하나를 같이 쓴다(같은 저장소에 동시 `worktree add` 를 피한다). 실패는 `GenerateError`
    — 라이브 트리로 되돌아가지 않는다.
    """

    def __init__(self, repo, commit: str, stack):
        self.repo, self.commit, self.stack = repo, commit or "HEAD", stack
        self.path = None
        self.error = ""
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            if self.path is None and not self.error:
                from .pinned_tree import pinned_worktree               # noqa: PLC0415
                try:
                    self.path = self.stack.enter_context(
                        pinned_worktree(self.repo, self.commit, logf=lambda m: _log(f"[synth] {m}")))
                except RuntimeError as e:
                    self.error = str(e)
            if self.error:
                raise GenerateError(f"고정 트리를 만들지 못했다 — {self.error}")
            return self.path


def synthesize_group(paths: ProjectPaths, key: str, files: list[str], *, tree=None,
                     **kw) -> GroupResult:
    """한 그룹 → 컨텍스트 MD 한 개. 본체는 `_synthesize_group`.

    `tree` (`#848`) — 상용 CLI 의 작업 디렉터리 공급자. `run()` 은 배치 하나에 하나를 만들어 준다.
    직접 부르는 경로(`revalidation`·CLI)는 여기서 자기 것을 만들고 끝나면 지운다.
    """
    if tree is not None:
        return _synthesize_group(paths, key, files, tree=tree, **kw)
    from contextlib import ExitStack                                # noqa: PLC0415
    with ExitStack() as stack:
        return _synthesize_group(paths, key, files, **kw,
                                 tree=_LazyTree(paths.repo, kw.get("commit", ""), stack))


def _synthesize_group(paths: ProjectPaths, key: str, files: list[str], *,
                     commit: str = "", broker: str = DEFAULT_BROKER,
                     model: str | None = None, caller=None, dry_run: bool = False,
                     content_limit: int = prompt_mod.CONTENT_LIMIT,
                     tally: source_text.EncodingTally | None = None,
                     chain=None, cli=None, related=None, searcher=None,
                     cloud_only: bool = False,
                     expected_source_fingerprint: str | None = None,
                     expected_artifact_fingerprint: str | None = None,
                     tree=None) -> GroupResult:
    """한 그룹 → 컨텍스트 MD 한 개.

    실패는 **예외가 아니라 결과**다 — 한 그룹이 죽었다고 배치를 멈추지 않는다. 대신
    `GroupResult.reason` 에 사유가 남고 `lost` 가 True 가 된다.

    [중요] `dry_run` — 생성·검증만 하고 **디스크에 쓰지 않는다.** 받아온 스냅샷을 건드리지 않고
    모델 적합도(사실 게이트 통과율)를 재려면 이게 필요하다. 통과율을 모른 채 전체를 돌리면
    나쁜 문서 909개가 되고, 그건 좋은 문서 0개보다 나쁘다.
    """
    res = GroupResult(key=key, files=list(files))
    t0 = time.monotonic()

    bodies: dict[str, str] = {}
    for f in files:
        d = source_text.read(paths.repo / f)
        if tally is not None:
            tally.add(d)
        if d is not None:
            bodies[f] = d.text
    if not bodies:
        res.reason = "소스를 읽지 못했다"
        return res

    out = doc_path(paths, key)
    existing = ""
    if out.is_file():
        e = source_text.read(out)
        existing = e.text if e else ""

    grounding = collect_grounding(paths, files)
    if related is not None:
        grounding.related = related
    elif caller is None or searcher is not None:
        grounding.related = collect_related(paths, key, files, existing, searcher=searcher)
    else:
        grounding.related = []                 # 주입 caller는 실제 외부 검색도 하지 않는다
    # 🔴 `#782` (사용자 결정 2026-10-10) — 프롬프트는 **레인 종류마다** 만든다.
    #    상용 CLI(`agy`·`codex`) = 원본 본문 무제한 · 요약 없음.
    #    로컬(브로커) = 종전 그대로 `content_limit`(기본 4000) + `pydigest` 요약(`#711`).
    #    `content_limit`(CLI `--content-limit` 포함)은 **로컬에만** 건다 — 상용은 결정상 무제한.
    #    사슬이 상용·로컬을 오가므로 종류별로 **처음 쓸 때 한 번만** 만든다(지연·캐시).
    #    사실 게이트·`md.finalize` 는 어느 시도든 같다 — 원본 `bodies` 로 판정한다.
    prompts: dict[str, tuple[str, str, int | None]] = {}

    def _prompt_for(kind: str) -> tuple[str, str, int | None]:
        if kind not in prompts:
            limit = None if kind == "cloud" else content_limit
            pbodies, digest = _prompt_bodies(paths, bodies, limit)
            text = prompt_mod.build(files=files, bodies=pbodies, grounding=grounding,
                                    existing=existing, limit=limit)
            prompts[kind] = (text, digest, limit)
            label = "cloud 무제한" if limit is None else f"local 상한 {limit}"
            _log(f"{key} — 프롬프트 {label} {len(text)}자" + (f" · {digest}" if digest else ""))
        return prompts[kind]

    # 호출·형식·사실 실패는 다음 모델로 간다. 결과마다 같은 게이트를 탄다.
    from ..work import usage as usage_mod                         # noqa: PLC0415
    models = _chain_for(model, chain)
    doc = ""
    format_reason = llm_reason = ""
    for n, m in enumerate(models):
        explicit_cloud = len(models) == 1 and _is_cli(m)
        if not explicit_cloud and not llm_policy.eligible(
                m, res.policy_attempts, allow_local=not cloud_only):
            res.attempts.append(f"{m} 건너뜀(quota 정책)")
            continue
        if _is_cli(m) and caller is not None and cli is None:
            # 주입된 브로커 호출자(테스트)에서 진짜 상용 CLI 를 부르지 않는다
            res.attempts.append(f"{m} 건너뜀(주입된 호출자)")
            res.policy_attempts.append({"lane": m, "kind": "error", "error": "주입된 호출자"})
            continue
        # 이 시도가 실제로 보내는 프롬프트. `prompt_chars`·`digest` 는 **마지막 시도**(통과했다면
        #    통과 모델)의 값이다 — 결과를 만든 프롬프트를 가리키게 (`#782`)
        p, res.digest, p_limit = _prompt_for("cloud" if _is_cli(m) else "local")
        res.prompt_chars = len(p)
        usage: dict = {}
        t_call = time.monotonic()
        attempt = _AttemptRecord(paths, key=key, files=files, commit=commit, model=m,
                                 prompt=p, declared=grounding.declared_classes, dry_run=dry_run,
                                 prompt_limit=p_limit)
        if attempt.saved:
            res.attempt_records.append(str(attempt.path))
            _log(f"{key} — {m} · 원문 기록 {attempt.path}")
        try:
            # `#713` ① — 이 그룹의 호출을 트윈의 `usage_log.jsonl` 에 `synth` 로 남긴다.
            #    상용 CLI 도 같은 sink 를 읽는다(`#728`·`#733`)
            with usage_mod.sink(paths.usage_log, source="synth", task_id=key):
                raw = _generate(p, m, broker=broker, caller=caller, cli=cli, usage=usage,
                                tree=tree)
                # 정규화가 원문을 바꾸거나 예외를 내기 전에 받은 응답 그대로 보존한다.
                attempt.update(raw=raw, raw_received=True, status="received")
                # `#751` — 상용 CLI 의 토큰은 공용 진입이 사용량 행으로 남긴다. 로그 줄도 그 값을
                #    보여 준다(종전엔 「미상」). [주의] GroupResult 합계는 **로컬만** — 계약 그대로다.
                shown = usage or (usage_mod.sink_cli_tokens() if _is_cli(m) else {})
        except GenerateError as e:
            res.policy_attempts.append({"lane": m, "kind": llm_policy.classify_failure(str(e)),
                                        "error": str(e)})
            attempt.update(status="transport_error", error=str(e), finished_at=time.time())
            llm_reason = f"LLM 실패: {e}"
            res.attempts.append(f"{m} LLM 실패")
            _log(f"{key} — {m} LLM 실패 · {int(time.monotonic() - t_call)}초 · 프롬프트 {len(p)}자"
                 f" · {str(e)[:120]}")
            res.reason = llm_reason
            continue
        res.tokens_in += usage.get("in", 0)
        res.tokens_out += usage.get("out", 0)
        _log(f"{key} — {m} · 토큰 입력 {shown.get('in', '미상')} · 출력 {shown.get('out', '미상')}"
             f" · {int(time.monotonic() - t_call)}초 · 프롬프트 {len(p)}자")
        doc, verdict = md_mod.finalize(raw, existing=existing, commit=commit)
        attempt.update(format={"ok": verdict.ok, "reason": verdict.reason,
                               "summary": verdict.summary, "preview": verdict.preview},
                       normalized_doc=doc,
                       status="format_passed" if verdict.ok else "format_rejected")
        if not verdict.ok:
            attempt.update(finished_at=time.time())
        if verdict.ok:
            res.attempts.append(f"{m} 형식 통과")
            # 정규화로 새로 드러난 이름까지 검증한다. 저장할 문서와 검사한 문서가 같다.
            from . import related as related_mod
            doc, fixed, unresolved = related_mod.normalize_doc(doc, paths)
            res.related_fixed, res.related_unresolved = fixed, list(unresolved)
            attempt.update(normalized_doc=doc)
            report = verify_mod.verify(doc, sources=bodies,
                                       declared=grounding.declared_classes,
                                       known=project_symbols(paths),
                                       live_counts=_index_only(paths))
            res.verify = report
            attempt.update(facts={"ok": report.ok, "reason": report.reason,
                                  "ghosts": report.ghosts, "declared": report.declared,
                                  "unknown_related": report.unknown_related,
                                  "mentioned_declared": report.mentioned_declared},
                           status="facts_passed" if report.ok else "facts_rejected")
            if report.ok:
                res.model = m
                res.policy_attempts.append({"lane": m, "kind": "success"})
                res.reason = ""
                break
            attempt.update(finished_at=time.time())
            res.reason = f"사실 게이트 거부 — {report.reason}"
            res.policy_attempts.append({"lane": m, "kind": "facts", "error": report.reason})
            res.attempts.append(f"{m} 사실 거부")
            _log(f"{key} — {m} {res.reason}")
            continue
        # σ.7-B — [중요] 기존 파일을 남긴다. 사슬이 다 실패하면 다음 사이클에 다시 시도된다.
        format_reason = f"형식 게이트 {verdict.summary} · preview={verdict.preview!r}"
        res.policy_attempts.append({"lane": m, "kind": "format", "error": verdict.reason})
        res.reason = format_reason
        res.attempts.append(f"{m} 형식 거부")
        _log(f"{key} — {m} 형식 거부 · preview={verdict.preview!r}")
    if len(res.attempts) > 1 or (res.model and res.model != models[0]):
        _log(f"{key} — 사슬 {' → '.join(res.attempts)}"
             + (f" · 통과 모델 {res.model}" if res.model else " · 전부 실패"))
    if not res.model:
        # 마지막 실제 시도의 실패 종류로 집계한다. 모든 모델의 개별 결과는 원문 기록에 남는다.
        res.reason = res.reason or "LLM 실패: 사슬에 시도할 모델이 없다"
        if len(res.attempts) > 1:
            res.reason += f" · 사슬: {' → '.join(res.attempts)}"
        return _remember(paths, key, files, res, commit, dry_run)

    import hashlib
    res.source_fingerprint = hashlib.sha256(json.dumps(
        bodies, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    res.needs_revalidation = not _is_cli(res.model)
    for field_name, value in (
            ("needs_revalidation", "true" if res.needs_revalidation else "false"),
            ("generation_model", json.dumps(res.model)),
            ("generation_source_fingerprint", res.source_fingerprint),
            ("generation_source_files", json.dumps(sorted(bodies)))):
        doc = md_mod._set_field(doc, field_name, value)

    res.chars = len(doc)
    if dry_run:
        res.reason = "dry-run — 검증 통과 (쓰지 않았다)"
        res.dry_ok = True
        res.elapsed_ms = int((time.monotonic() - t0) * 1000)
        return res
    try:
        if expected_source_fingerprint is not None:
            current = {}
            for f in bodies:
                source = source_text.read(paths.repo / f)
                if source is None:
                    raise OSError(f"재검증 중 소스 유실: {f}")
                current[f] = source.text
            fingerprint = hashlib.sha256(json.dumps(
                current, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            if fingerprint != expected_source_fingerprint:
                raise OSError("재검증 중 소스 변경 — 기존 문서 보존")
        if expected_artifact_fingerprint is not None:
            fingerprint = hashlib.sha256(out.read_bytes()).hexdigest()
            if fingerprint != expected_artifact_fingerprint:
                raise OSError("재검증 중 문서 변경 — 기존 문서 보존")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(doc, encoding="utf-8")
    except OSError as e:
        res.reason = f"쓰기 실패: {e}"
        res.policy_attempts.append({"lane": res.model, "kind": "write", "error": str(e)})
        attempt.update(status="write_error", error=str(e), finished_at=time.time())
        return res
    res.written = True
    attempt.update(status="written", document=str(out), finished_at=time.time())
    res.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return _remember(paths, key, files, res, commit, dry_run)


MAX_WORKERS = 6        # 원전 `watcher/common.py:42` 와 같은 상한 — 노드가 늘어도 이 이상 띄우지 않는다


def _workers(parallel: int | None, *, model: str, broker: str, caller) -> tuple[int, str]:
    """동시 합성 수와 그 사유. 🔴 `#715` — 원전은 병렬(`MAX_WORKERS = 6`)이었는데 이식이 직렬이었다.

    로컬 노드는 한 번에 한 요청을 처리하므로 **그 모델이 상주한 노드 수**만큼 띄운다 — 더 띄우면
    한 노드에 쌓여 기다릴 뿐이다(브로커는 처리 중 요청이 적은 노드로 보낸다). 브로커를 못 읽으면
    1 — 종전 동작이다. 주입된 호출자(테스트)는 명시하지 않으면 1.
    """
    if parallel is not None:
        return max(1, min(int(parallel), MAX_WORKERS)), "지정"
    if caller is not None:
        return 1, "주입된 호출자"
    if _is_cli(model):
        return 1, "상용 CLI — 직렬"
    try:
        import json as _json
        import urllib.request as _ur
        from ..auth import auth_headers, load_token          # noqa: PLC0415
        req = _ur.Request(f"{broker}/health", headers=auth_headers(load_token()))
        with _ur.urlopen(req, timeout=5) as r:
            eps = _json.loads(r.read().decode("utf-8")).get("endpoints") or []
        hot = [e["name"] for e in eps if e.get("healthy") and e.get("resident") == model]
    except Exception as e:                                    # noqa: BLE001
        return 1, f"브로커 상태를 못 읽었다 — 직렬 ({type(e).__name__})"
    if not hot:
        return 1, "상주 노드 없음 — 직렬"
    return max(1, min(len(hot), MAX_WORKERS)), "상주 " + "·".join(hot)


def run(paths: ProjectPaths, *, changed: list[str] | None = None, commit: str = "",
        skip_existing: bool = False, limit: int = 0, broker: str = DEFAULT_BROKER,
        model: str | None = None, caller=None, dry_run: bool = False,
        content_limit: int = prompt_mod.CONTENT_LIMIT, unload_every: int = UNLOAD_EVERY,
        git=None, progress=None, parallel: int | None = None,
        chain=None, cli=None, searcher=None) -> Stats:
    """배치 합성. changed가 없으면 등록 소스 경계 전체를 대상으로 한다.

    skip_existing은 기존 문서를 건너뛰고 limit은 시도 그룹 수를 제한한다.
    parallel은 합성 동시 수이고 None이면 상주 노드 수를 사용한다.
    검색기는 첫 실제 작업 묶음에서 열며 관련검색은 coordinator에서 직렬 수행한다.
    주입 searcher는 호출자가 소유·해제한다. 주입 caller는 searcher 없으면 검색을 생략한다.
    """
    from contextlib import ExitStack                                # noqa: PLC0415
    related = _BatchRelated(paths, searcher=searcher, enabled=caller is None)
    try:
        # `#848` — 배치 하나에 고정 트리 하나. 병렬 묶음이 같이 쓰고 끝나면 지운다
        with ExitStack() as stack:
            return _run(paths, changed=changed, commit=commit, skip_existing=skip_existing,
                        limit=limit, broker=broker, model=model, caller=caller,
                        dry_run=dry_run, content_limit=content_limit, unload_every=unload_every,
                        git=git, progress=progress, parallel=parallel, chain=chain, cli=cli,
                        related_resource=related, tree=_LazyTree(paths.repo, commit, stack))
    finally:
        related.close()


def _run(paths: ProjectPaths, *, changed: list[str] | None = None, commit: str = "",
         skip_existing: bool = False, limit: int = 0, broker: str = DEFAULT_BROKER,
         model: str | None = None, caller=None, dry_run: bool = False,
         content_limit: int = prompt_mod.CONTENT_LIMIT, unload_every: int = UNLOAD_EVERY,
         git=None, progress=None, parallel: int | None = None,
         chain=None, cli=None, related_resource, tree=None) -> Stats:
    """배치 합성. `changed` 를 주면 그 파일들만, 없으면 경계(`paths.scope`, 기본 `Source/`) 전체.

    `skip_existing` — 이미 문서가 있는 그룹을 건너뛴다(최초 전체 빌드에서 누락분만 보충).
    `limit` — 그룹 수 상한. 0 이면 무제한. [중요] 상한에 걸려 남긴 것은 `Stats.aborted` 에 적는다.
    `parallel` — 동시 합성 수. `None` 이면 **그 모델이 상주한 노드 수**(`_workers`, `#715`).
    `chain` — 형식 거부 시의 모델 순서. `None` 이면 `_chain_for` 규칙(`#727`). `cli` 는 테스트 주입.
    """
    files = changed if changed is not None else cg.list_source_files(paths, git=git)
    if not files:
        raise SynthError(f"합성할 소스가 없다 — `{paths.scope.label()}` 경계나 변경 목록을 확인하라. "
                         "빈 배치를 성공으로 보고하지 않는다")
    # [중요] **컨텍스트 문서 생성은 `Source/` 한정이다** (§5.2-E, 사용자 재확인 2026-08-22).
    #    `changed=None` 경로는 `list_source_files` 가 경계를 **두 겹**으로 지키는데(pathspec +
    #    접두 검사), `changed` 를 받는 경로에는 검사가 **없었다** — 호출자가 한 번 잘못 넘기면
    #    `Content/`(워킹트리의 93%, uasset 바이너리)가 그대로 합성 대상이 된다.
    #    [주의] 조용히 걸러내지 않고 **거부한다.** 걸러내면 호출자는 그것도 합성된 줄 안다.
    files = [str(f).strip().replace("\\", "/") for f in files]
    #    [중요] 판정은 `SourceScope.contains` 한 자리다 (`#693`) — 기본 경계는 종전과 같다.
    outside = [f for f in files if not paths.scope.contains(f)]
    if outside:
        raise SynthError(
            f"`{paths.scope.label()}` 밖의 파일이 합성 목록에 있다 ({len(outside)}건) — "
            f"컨텍스트 문서는 소스 한정이다(§5.2-E): "
            + ", ".join(outside[:5]) + (" ..." if len(outside) > 5 else ""))
    groups = group([f for f in files if (paths.repo / f).is_file()])
    # 🔴 [중요] **거부된 그룹을 다시 끌어온다** (`#377` ⓑ). 사실/형식 게이트가 거부하면 기존
    #    문서가 남고 커서는 전진하므로(`#375`) 다시 만들 계기가 **영영 없었다** — 파일이 있으니
    #    아무도 모르고 RAG 는 옛 내용을 답한다. 변경이 없어도 보류분은 다시 시도한다.
    #    [주의] **상한이 있는 재시도다** — 리포트 51 의 「같은 커밋을 하루 종일」을 만들지 않는다.
    from . import pending as pending_mod
    retried = 0
    for pkey, pfiles in pending_mod.due(paths):
        alive = [f for f in pfiles if (paths.repo / f).is_file()]
        if alive and pkey not in groups:
            groups[pkey] = alive
            retried += 1
    # 🔴 **짝 파일을 채운다** (`#367`) — 변경분만 들어와도 판정은 그룹 전체를 본다
    groups = {k: complete_group(paths.repo, k, fs) for k, fs in groups.items()}
    if not groups:
        raise SynthError("살아 있는 소스 파일이 없다 (전부 삭제됐거나 경로가 틀렸다)")

    stats = Stats(groups=len(groups))
    stats.retried = retried
    t0 = time.monotonic()
    consecutive = 0
    primary = model or SYNTH_MODEL
    n, why = _workers(parallel, model=primary, broker=broker, caller=caller)
    stats.workers = n
    _log(f"{paths.name} — 그룹 {len(groups)} · 동시 {n} ({why})")
    order = sorted(groups.items())
    i = 0                                    # 다음에 볼 그룹 (0 부터)
    stop = False
    while i < len(order) and not stop:
        # ① 묶음을 짠다 — 상한·건너뜀은 **묶기 전에** 판정한다(종전 직렬과 같은 규칙)
        batch: list = []
        while i < len(order) and len(batch) < n:
            attempted = stats.written + stats.refused + stats.unfactual + stats.failed
            if limit and attempted + len(batch) >= limit:
                stats.aborted = f"상한 {limit} 도달 — 남은 {len(order) - i} 그룹 미처리"
                stop = True
                break
            key, fs = order[i]
            i += 1
            if skip_existing and doc_path(paths, key).is_file():
                stats.skipped += 1
                stats.results.append(GroupResult(key=key, files=fs, reason="변화 없음"))
                continue
            batch.append((i, key, fs))
        if not batch:
            continue
        # 검색기 초기화·검색은 worker를 띄우기 전에 한 스레드에서 수행한다.
        related = [related_resource.collect(key, fs) for _idx, key, fs in batch]
        # ② 동시에 합성한다 — 🔴 `#715`: 원전은 `MAX_WORKERS` 병렬이었다. 인코딩 집계는 작업마다
        #    따로 세고 합친다(`+=` 는 스레드 사이에서 유실될 수 있다)
        tallies = [source_text.EncodingTally() for _ in batch]

        def _one(j):
            _idx, key, fs = batch[j]
            return synthesize_group(paths, key, fs, commit=commit, broker=broker, model=model,
                                    caller=caller, dry_run=dry_run,
                                    content_limit=content_limit, tally=tallies[j],
                                    chain=chain, cli=cli, related=related[j], tree=tree)
        if len(batch) == 1:
            results = [_one(0)]
        else:
            with ThreadPoolExecutor(max_workers=len(batch)) as ex:
                results = list(ex.map(_one, range(len(batch))))
        for t in tallies:
            for f in ("utf8", "cp949", "degraded", "unreadable"):
                setattr(stats.encodings, f, getattr(stats.encodings, f) + getattr(t, f))
        # ③ 결과는 **그룹 순서대로** 센다 — 연속 실패 판정이 직렬과 같은 뜻을 갖게
        for (idx, key, fs), r in zip(batch, results):
            stats.results.append(r)
            stats.tokens_in += r.tokens_in
            stats.tokens_out += r.tokens_out
            if r.digest:
                stats.digested += 1
            if r.passed and r.model and r.model != primary:
                stats.fallback_passed += 1
            if r.passed:
                stats.written += 1
                consecutive = 0
            else:
                if r.reason.startswith("LLM 실패"):
                    stats.failed += 1
                    consecutive += 1
                else:
                    # 게이트 거부는 모델 응답이 온 것이라 서킷 차단 사유가 아니다.
                    if r.reason.startswith("사실 게이트"):
                        stats.unfactual += 1
                    else:
                        stats.refused += 1
                    consecutive = 0
                if consecutive >= CIRCUIT_THRESHOLD and not stop:
                    # [주의] 같은 묶음의 나머지는 이미 돌았다 — 세기는 다 하고, **다음 묶음을 안 띄운다**
                    stats.aborted = (f"LLM 연속 실패 {consecutive}회 — 남은 "
                                     f"{len(order) - i} 그룹을 태우지 않는다. 마지막 사유: "
                                     f"{r.reason[:120]}")
                    stop = True
            if progress:
                progress(f"  {idx}/{len(order)} {key} — {'통과' if r.passed else r.reason[:60]}")
        # [중요] 주기적으로 모델을 내려 누적된 캐시를 회수한다 (위 UNLOAD_EVERY 참조).
        # 다음 요청이 자동으로 다시 적재한다 — 우리가 올릴 필요는 없다. 묶음 사이에서만 한다.
        done = stats.written + stats.refused + stats.unfactual + stats.failed
        if (unload_every and done and done % unload_every < len(batch) and caller is None
                and not _is_cli(primary)):
            try:
                unload_model(primary, broker=broker)
                stats.unloads += 1
            except GenerateError:
                pass       # 회수 실패는 치명적이지 않다 — 다음 주기에 다시 시도된다
    stats.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return stats
