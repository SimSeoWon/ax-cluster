"""작업 워크플로우 — 3-tier 브랜치 · 컨텍스트 매니페스트 (PLAN §4).

AgentTest plan v5 Phase C 의 워크플로우를 **§2.1 토폴로지에 맞게** 이식한다.
큰 차이 하나: 원본은 상용 모델 검증 워커가 durable merge 권위였지만,
여기서는 **층3(UE5 빌드 + RunTests)이 최종 권위**다 (§4.3).
"""
from .branch_names import (
    BranchNameError, attempt_branch, attempt_glob, base_branch, durable_branch,
    is_attempt, is_base, is_durable, parse_attempt, parse_base, parse_durable, work_glob,
)
from .manifest import Manifest, ManifestError, build, collect, manifest_path, read, write
from .generate import (
    CODER, Dispatch, GenerateError, Generated, dispatch, generate, strip_fence,
)

__all__ = [
    "BranchNameError", "attempt_branch", "attempt_glob", "base_branch", "durable_branch",
    "is_attempt", "is_base", "is_durable", "parse_attempt", "parse_base", "parse_durable",
    "work_glob",
    "Manifest", "ManifestError", "build", "collect", "manifest_path", "read", "write",
    "CODER", "Dispatch", "GenerateError", "Generated", "dispatch", "generate", "strip_fence",
]
