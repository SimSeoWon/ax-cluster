"""임베딩 모델 선택 — 🔴 **한국어를 실을 수 있는 벡터**.

## 왜 바꿨나 (실측 2026-08-08)

기본값이던 chromadb 내장 `ONNXMiniLM_L6_V2`(= `all-MiniLM-L6-v2`)는 **영어 전용**이다.
같은 개념을 한글/영문으로 던져 실제 색인(961문서)에 검색한 결과:

    「전역 이벤트 시스템」  → WNDMonsterCollectionMana · WNDUITopMenuBase · mapedit_enum  ❌
     global event system   → GlobalEventSystem.md · EventBusSubsystem.md                 ✅
                             (둘 다 vector+bm25 — 두 채널이 동의)

**한글 질의는 두 채널 모두에서 실패한다.** 벡터는 모델이 영어 전용이라, BM25 는 토크나이저에
형태소 분석이 없어(`[가-힣]+` 로 "몬스터를" 이 한 토큰) 그렇다.

## 왜 이 모델인가

원본 시소러스 설계 문서가 남긴 실측을 그대로 쓴다:

> 다국어 대체 모델 중 **384차원짜리는 현재(all-MiniLM-L6-v2, 384차원) 대비 저장 증가가 0** —
> "기하급수적" 증가는 768/1024차원 모델(2~2.67배)에 한정된다.

`paraphrase-multilingual-MiniLM-L12-v2` 가 **384차원**이라 벡터 저장량이 그대로다.
원본 팀은 재임베딩 부담 때문에 시소러스를 택했지만, 우리는 961문서 · 재구축 40초라
그 제약이 없다.

**`fastembed` 을 쓴다** — ONNX 런타임(이미 설치돼 있다)만 필요하고 **PyTorch 를 끌어오지
않는다.** 원본의 *"PyTorch 불필요(~2GB 절약)"* 결정을 깨지 않는다(실측: `fastembed` +
`loguru`·`pillow`·`py_rust_stemmers` 4개뿐).

🔴 **모델을 바꾸면 기존 벡터는 전부 무효다.** 그래서 컬렉션 메타데이터에 모델 이름을 새기고,
불일치를 **조용히 넘기지 않는다** — 안 그러면 "검색이 왜 이상하지" 가 된다.
"""
from __future__ import annotations

import os

# 기본값. 바꾸려면 환경변수 `AX_EMBED_MODEL`.
MULTILINGUAL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ENGLISH_ONLY = "chromadb-default"          # 내장 ONNXMiniLM — 되돌릴 때만
DIMENSIONS = 384                            # 두 모델 공통. 다르면 재색인이 필요하다


def model_name() -> str:
    return os.environ.get("AX_EMBED_MODEL", MULTILINGUAL)


class _FastEmbed:
    """`fastembed` 을 chromadb 임베딩 함수 규약에 맞춘 얇은 어댑터.

    chromadb 가 요구하는 것은 `__call__(input) -> list[list[float]]` 과 `name()` 뿐이다.
    """

    def __init__(self, model: str):
        from fastembed import TextEmbedding
        self._model = model
        self._embed = TextEmbedding(model_name=model)

    def _run(self, input) -> list[list[float]]:
        return [list(map(float, v)) for v in self._embed.embed(list(input))]

    def __call__(self, input):                       # noqa: A002 - chromadb 규약
        return self._run(input)

    # 🔴 chromadb 신 API 는 문서/질의 임베딩을 **따로 부른다**(`embed_documents` /
    # `embed_query`). 없으면 `AttributeError` 로 검색이 죽는다 — 실측으로 걸렸다.
    # 이 모델은 비대칭 접두어(e5 계열의 `query:`/`passage:`)를 쓰지 않으므로 같은 경로다.
    def embed_documents(self, input):                # noqa: A002
        return self._run(input)

    def embed_query(self, input):                    # noqa: A002
        return self._run(input if isinstance(input, (list, tuple)) else [input])

    def name(self) -> str:
        return f"fastembed:{self._model}"


def build(model: str | None = None):
    """임베딩 함수를 만든다. 실패하면 **던진다** — 조용히 영어 모델로 떨어지지 않는다.

    조용한 폴백이 위험한 이유: 한글 검색이 그냥 나빠지고 **아무도 모른다.** 색인은 정상으로
    보이고 결과만 틀린다 — 우리가 반복해 온 실패 모양이다.
    """
    name = model or model_name()
    if name == ENGLISH_ONLY:
        from chromadb.utils import embedding_functions
        return embedding_functions.ONNXMiniLM_L6_V2()
    return _FastEmbed(name)


def stamp(model: str | None = None) -> str:
    """컬렉션 메타데이터에 새길 값."""
    return model or model_name()
