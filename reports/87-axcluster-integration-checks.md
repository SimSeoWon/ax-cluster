# AXCluster 통합 검사 보완 — #716

일감 정본: http://192.168.0.57:8080/issues/716

## 문제

AXCluster 프로필의 종전 통합 검사 `unittest discover -s master -p test_*.py` 는 스크립트형 검사
(`__main__` 에서 직접 세는 파일)를 돌리지 않는다. 일부 TestCase 만 실행돼 `Ran N`(N≥1)을 만족하므로
나머지 검사의 누락이 가려진다. 공용 `master/work/build_local.py` 는 수정하지 않는다.

## 구현 (Codex 지휘, 로컬 서브 에이전트) — 미커밋

- `master/integration_checks.py` — 명시 JSON 목록을 검증하고, 검사마다 별도 Python 프로세스(`-B`,
  임시 `AX_PROJECTS_ROOT`·`AX_GITEA_REPO_ROOT`)로 실행한다. rc≠0 · 건수 증거 없음/0건 ·
  total 불일치 · failed>0 · 전부 skip · 타임아웃 · 잘못된 목록은 차단.
- `master/test_integration_checks.py` — 회귀 15개.
- `tests/integration/checks.json` — 필수 7개: broker_routing · workshop_check · source_scope ·
  python_commit_review · build_local · skeleton_gate · integration_checks (각 180초).
- `tests/integration/test_axcluster.py` — 목록을 읽어 검사당 unittest 1개를 만든다.
- `master/client/payload/profile/AXCluster.yaml` — `test_start_dir: tests/integration`,
  `test_pattern: test_axcluster.py`. 다른 값은 그대로.

## 검증 (Claude, 2026-10-03 인계 후)

1. **코드 대조** — 5개 파일이 인계서 서술과 일치. 회귀 직접 실행 15/15 OK.
2. **실제 경로 7개 실행** — 프로필 값으로 `build_local.local_test_fn` 을 호출:
   `.venv/bin/python -B -m unittest discover -s tests/integration -p test_axcluster.py` →
   `TESTS OK (7)` · 3.4초 · 실행 전후 `git status` 동일.

   | 검사 | 건수 |
   |---|---|
   | broker_routing | 14 |
   | workshop_check | 77 |
   | source_scope | 32 |
   | python_commit_review | 7 |
   | build_local | 36 |
   | skeleton_gate | 51 |
   | integration_checks | 15 |

   broker 14 · workshop 77 · source_scope 32 는 리포트 86 의 이전 실측과 같다.
3. **실패 주입 (fail-closed)** — 스크래치 사본(저장소 밖, 끝나고 삭제)에 실패를 심고 같은
   `local_test_fn` 경로로 실행했다. 9/9 차단:

   | 주입 | 판정 |
   |---|---|
   | 8개 중 1개 rc=1 | FAILED (failures=1) — 정상 7개가 덮지 않음 |
   | 건수 0 | FAILED |
   | unittest 전부 skip | FAILED |
   | unittest 실패 1건 | FAILED |
   | 검사 파일 없음 | FAILED (errors=1, 발견 단계) |
   | 빈 목록 · 깨진 JSON · `master/test_*.py` 밖 경로 | 각각 FAILED (errors=1) |
   | 타임아웃 2초 | FAILED |

4. **연결 경로** — 프로필은 `payload/profile/<P>.yaml` 이 정본(`projects/profile.py`) →
   `client/bundle._tests_for` 가 `{'start_dir': 'tests/integration', 'pattern': 'test_axcluster.py'}`
   를 만든다(실행 확인) → 배달된 `.ax/config.json` 의 `tests` → `ax-advance` 스킬이
   `local_test_fn(start_dir=cfg["tests"]["start_dir"], …)` 을 부른다. 스킬 예시는 고칠 것 없음.

## 한계와 관찰

- **배달 전에는 효과가 없다.** 작업장 설정은 `384a07a` 배달본(`master` · `test_*.py`)이다.
  새 값은 5프로젝트 전체 `master.client update` 뒤에 적용된다.
- **래퍼는 스크립트의 자기 요약을 믿는다.** 검사 없이 `5/5 통과` 만 찍고 rc=0 인 스크립트는
  통과했다(주입 10번째). 그래서 「검토된 목록만 실행」이 전제다 — 현 목록 7개는 전부 기존 검사.
  환경 분리는 보안 샌드박스가 아니다.
- **실패 시 요약 숫자가 틀릴 수 있다.** 공용 `parse_unittest` 가 첫 `Ran N` 줄을 집어,
  자식 출력이 실패 메시지에 섞이면 자식 건수를 표시한다(전부 skip 주입에서 `(2)` 대신 `(1)`).
  판정(rc · `FAILED`)은 맞다. 범위 밖 파일이라 고치지 않았고 #716 노트에만 남긴다(사용자 결정).
- 기존 144 검사 파일 중 나머지 135개의 안전성·커버리지는 검토하지 않았다. 자동으로 목록에
  넣지 않는다.

## 하지 않은 것

커밋·푸시 · 배달 · 서비스 재기동 · 원격 파견 · 워커 동기화. 이 리포트는 #716 완료 판정이 아니다.
