"""등록된 운영 문서의 근거 수집·LLM 수정안·명시적 적용 (#838).

공유 계약 (JSON으로 보존 가능한 dict):
registry.collect(root, registry_path, ids=None) -> plan
  schema_version=1, root/registry 절대경로, registry_hash, head,
  documents=[id,path(등록값),target(root 기준 정본),role,protected,instructions,
             before,before_sha256,evidence=[path,sha256,text]].
draft.generate(plan, lane='codex', timeout=180, generator=None, usage_log=None) -> artifact
  plan의 문서/근거를 보존하고 각 문서에 decision(update/unchanged),after,
  after_sha256,reason,citations(['상대경로:줄번호']),diff를 추가한다.
  generator(prompt, lane, timeout) -> JSON 문자열 (테스트 주입).
apply.apply_draft(root, registry_path, artifact, confirm=False,
                  approved_ids=None, allow_protected=False) -> report
  현재 등록목록·정본·입력 해시와 대조한 뒤 미리보기 또는 명시 승인분만 쓴다.
LLM은 파일을 쓰지 않는다. 자동 커밋·배포·서비스 재기동은 없다.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


# 읽기 전용 격리 실행(임시 workdir)을 지원하는 생성 레인. 자동 폴백은 없다.
LANES = ("codex", "claude")


class DocSyncError(RuntimeError):
    """등록·근거·수정안·적용 계약이 충족되지 않았다."""


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path: Path) -> str:
    """UTF-8 원문을 줄바꿈 변환 없이 보존한다."""
    try:
        return Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise DocSyncError(f"문서를 읽을 수 없다: {path}: {exc}") from exc
