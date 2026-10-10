# 105 — #788 정책·main 병합 드라이런

2026-10-10 19:16 KST · Codex · 사용자 「둘다 수정을 했으니 테스트가 필요해」

## 대상과 호출

work `20261010_1742_788_1_46881e71`의 전진된 base `65951cbcd5b01d188e13620122acb236636df4f6`를 대상으로 기존 `ax-review`의 `review.review_work`를 실행했다. `build_local.local_test_fn(start_dir="tests/integration", pattern="test_axcluster.py", python="/home/sim/ax-cluster/.venv/bin/python")`, `remote="gitea-write"`, `keep_tree=True`를 사용했다. 기본 샌드박스의 SSH 차단 후 같은 명령을 승인 해제로 재실행했다. 임시 대체 스크립트·워커 재파견·push·finalize·배포는 하지 않았다.

검수 트리: `/home/sim/ax-cluster/AXCluster/ax-review-20261010_1742_788_1_46881e71`, HEAD `68ae95a62d7194926858f9d7236f7a7a682d7c63`, clean으로 보존한다. 기준 원격 main은 `67eb3f97d9a1f9fd744b60507b8f7fc8c86c0fde`다.

## 결과

- main+전진 base 병합 충돌 없음. `ok=true`, `gate_passed=true`, `build_skipped=false`, `error` 없음.
- #787로 삭제된 r1 서브 브랜치 두 개는 전진 base의 병합 증거로 정상 인식했다. 정책 조각은 `af3e1376fa`, 기록 조각은 `65951cbcd5`에서 병합됐음을 실제 로그로 확인했다. `merged_durables=[]`는 누락이 아니라 이미 feature/base에 들어 있는 조각이므로 재병합하지 않은 결과다.
- AXCluster 명시 통합 검사 31/31 통과, 62.2초. `test_branch_prune` 69개, `test_autodispatch` 26개를 포함한다.
- 같은 검수 트리에서 `python -B -m unittest master.test_llm_policy master.test_revalidation -v`: 2/2 통과, 0.418초. 클라우드 순서·quota 전용 Claude/local·혼합 일반 오류·거짓 429·쓰기/검증 실패 분류·local 재검증 표시, 기록의 영속성·지연·오래된 fingerprint 보존·조회 상한·스레드/프로세스 동시 쓰기·손상 JSON·원자 저장 실패를 검사했다.
- 실제 클라우드 quota를 소진하거나 LLM을 호출하지 않았다. 생성 세 경로와 주기 실행 연결은 아직 미구현이므로 이번 결과를 #788 전체 종단 검사로 주장하지 않는다.

## 발견한 형식 문제

`git diff --check gitea-write/main HEAD` 종료 코드 2:

- `master/test_revalidation.py:118`: new blank line at EOF.
- `master/work/revalidation.py:168`: new blank line at EOF.

두 파일이 main에는 신규 추가이므로 이전 골조 a31cf1d와의 diff 검사에서는 잡히지 않았던 문제다. 기능 검사는 통과했지만 형식 검사까지 통과했다고 보고하지 않는다. 실패 시 코드·설정은 고치지 않고 보고한다는 공용 규칙에 따라 파일 본문을 수정하지 않았다. 후속 수정 대상은 이 두 파일의 끝 빈 줄뿐이며 새 커밋/push는 별도 승인 대상이다.

## 보존 상태

실행 뒤 Gitea 정본 refs 재조회: main `67eb3f9`, 작업 base `65951cbc` 그대로. 큐 상태 변경·main 반영·배포 없음. 결과는 #789 및 인수인계서에 기록한다.
