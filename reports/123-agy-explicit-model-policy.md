# agy 자동 기본 모델 고정 · Argon 명시 사용 제한 (#830)

2026-10-18 · Codex · 로컬 서브 에이전트 구현, 마스터 대조. 현재 HEAD `08291cc`, 아래 변경은 미커밋이다.

## 사용자 결정

> Argon 은 파이썬 코드 작업등에서 검증을 하기 위해 토큰을 일단 함부로 쓰지 말고, 코드 리뷰는 기존에도 아르곤 없어도 잘 작동하고 있었잖아. 사용자가 명시적으로 아르곤을 쓰라고 하지 않는다면 기본 모델은 아르곤이면 안돼

기존 정상 운영 설정의 canonical ID `gemini-3.8-flash-medium`을 공용 자동 호출 기본값으로 명시한다. 사용자 agy 설정에 모델 선택을 맡기지 않는다. Argon은 자동 기본·자동 폴백에 포함하지 않는다. 직접 모델을 지정하고 `allow_argon=True`를 함께 준 수동 호출만 가능하다. 이번 검증에는 Argon을 호출하지 않았다.

리뷰 큐의 Antigravity 단독 정책과 작성·검증의 교차 계열은 유지한다. Claude·GPT-OSS 모델을 agy 안의 자동 폴백으로 추가하지 않았다. Flash 등급별 한도는 같은 묶음이므로 기본 내부 폴백도 두지 않는다. 명시적으로 허용한 Gemini 후보를 전달할 수 있는 실행 계약만 갖춘다.

## 구현

- `master/agy_models.py`: canonical ID·`agy models` 목록 검사, 메타데이터 TTL 캐시, 모델별 지속 쿨다운 및 `Resets in` 해석, 잠금·원자 교체. 전체 호출에 한 시간 제한을 적용한다.
- 호출별 `--log-file`에서 기존 `usage.parse_agy_log`로 실제 모델을 읽는다. 실제 모델 불일치는 결과를 거부하며, 한도 오류가 함께 있어도 다른 모델 폴백으로 숨기지 않는다. 실제 모델을 확인하지 못하면 미상으로 기록·경고하고 요청 모델을 실제 모델로 지어내지 않는다.
- `layer2_verify.run_agy`를 생성 레인과 리뷰·합성·층2가 공유한다. 실행 경계는 계측을 중복 기록하지 않으며 공용 호출은 시도별, 생성 레인은 기존 결과 계측 경로를 사용한다.
- 사용량에 `requested_model`·`actual_model`·`model_source`를 전달한다. 실패한 호출의 사용량도 보존한다. 종료 코드가 0이어도 모델 불일치·응답 오류를 성공으로 반환하지 않는다.
- 기존 standalone 진입에서도 동일 `work/usage.py` 파서를 로드한다. 별도 파서를 복제하지 않았다.
- 상태 경로는 `AX_AGY_STATE_PATH` → `AX_PROJECTS_ROOT/.ax/agy/models.json` → standalone 홈 캐시 순이다. 실제 `ax-task-queue`·`ax-projects`의 `ProtectSystem=strict`와 쓰기 허용 경로를 대조했다. 서비스 권한·설정은 변경하지 않았다.
- 정책 회귀 검사를 `tests/integration/checks.json`에 추가했다.

공개 CLI `agy help models`에는 모델 목록 외 JSON·별칭 사전 해석·쿼터 조회 계약이 없다. 따라서 canonical 목록 사전 검사와 실제 모델 로그 사후 대조를 구분한다. 알 수 없는 향후 CLI 내부 별칭 변경을 호출 전에 완전히 증명하는 기능이 있다고 주장하지 않는다.

## 검증

- 정책 15/15, 계측 27/27, CLI 경로 51/51, sink 35/35, 리뷰 큐 68/68 통과.
- 단독 import 환경(`python -I`, 작업 위치 `/tmp`)에서 기존 파서 로딩과 서비스 상태 경로를 별도로 확인했다.
- 라이브 Flash Medium **1회**: `AX830_FLASH_OK`, 요청·실제 모델 모두 `gemini-3.8-flash-medium`, 확인 출처 `log`, 종료 0. 입력 18,978·출력 290토큰. 요청은 짧아도 CLI 기본 컨텍스트가 포함된 실제 사용량이다. 임시 계측 파일로 이중 운영 집계를 피했다. **Argon 호출 0회.**
- 공식 통합 168개는 `-f` 실행에서 **127개 실행·126개 통과·1개 실패**, 나머지 41개 미실행으로 중단했다(146.853초, 종료 1). 실패는 `test_context_synth`의 사용량 주입 검사다. `master/test_context_synth.py:975-987`이 종전 `_run_rc`를 패치하고 `/usr/bin/agy`를 가리키지만, 새 경로는 metadata 검사와 `_run_raw`를 사용한다. 그 결과 agy 주입 응답을 받지 못하고 codex로 넘어가 예상 사용량 행 검사가 실패했다. 원인을 소스와 대조했으며 **아직 고치거나 재실행하지 않았다**. 이것을 공식 전수 통과로 보고하지 않는다.

첫 CLI 경로 검사에서 테스트의 쿼터 시나리오가 다음 독립 사례에 임시 쿨다운을 남겨 실패했다. 운영 상태는 오염되지 않았다. 실패를 보고하고 중단한 뒤 사용자 승인으로 사례별 상태 격리·standalone import·실패 사유 전달을 보완하고 재검증했다.

## 남은 범위와 배포

사용자가 이어 **「인프라 서버 말고 워커 BC250, .2 PC와 메인 작업 PC(.33)도 변경되어야해」**라고 명시했다. 따라서 마스터만으로 완료 처리하지 않는다. 기존 로컬 서브 에이전트 방식을 그대로 이어받으며 다시 방식 선택을 묻지 않는다.

읽기 조사 결과(아래 파일은 아직 편집하지 않음):

- `master/client/bundle.py`의 배달 config `backends`에는 agy 설치 여부만 있고 모델 필드가 없다.
- `master/client/skills/ax-work/SKILL.md:119-120`의 직접 agy 명령, Windows `client/runtime/session1_conductor.py:197-198`의 중계 명령에 `--model`이 없다. BC250의 직접 실행과 Windows 중계 모두 대상이다. ax-infer는 별도 실행 예시가 없어 추가 대조가 필요하다.
- 최소 설계 후보는 마스터 공용 기본값 → 배달 `.ax/config.json backends.agy_model` → 스킬 직접 명령과 Windows relay의 `--model`이다. 설정 누락 때 사용자 CLI 기본값으로 조용히 후퇴하면 안 된다. 아직 확정·구현하지 않았다.
- `master/work/gemini_report.py`의 수동 리서치 경로도 모델을 생략한다. heartbeat, `.run` 원본 보관, 재시도 회복·경고 종료 3, remote 사용량 POST 계약을 유지해야 한다. 현재 `agy_models.py`는 Linux `fcntl`을 써 Windows에 그대로 배달할 수 없다. 전체 정책 배달/이식과 경량 모델 입력 계약 중 어느 방법으로 연결할지 설계가 남았다.
- remote 계측을 늘리면 서버 수신부 whitelist가 새 provenance 필드를 보존하는지도 확인해야 한다.
- `master_local`의 agy 설정 처리는 MCP 권한 병합이며 기존 모델 값을 보존한다. 이를 모델 변경 기능으로 오해해 쓰지 않는다. 임시 원격 스크립트나 홈 설정 손수 덮기로 배달 계약을 우회하지 않는다.

사용자가 「토큰 없다 인수 인계서 작성해」라고 요청해 구현을 중단했다. 서브 에이전트 중단 완료, 공식 검사도 이미 종료했다. 워커·리서치 경로 추가 구현과 공식 검사 실패 보완이 다음 작업이다. 실패 보완은 사용자 실패 규칙에 맞춰 원인·수정 범위를 먼저 보고한 뒤 재개한다.

커밋·푸시·배달·서비스 재기동은 이번 #830에 대해 아직 승인·실행하지 않았다. `#830`은 진행 상태로 유지한다. 현재 마운트는 AXCluster다.

이 세션의 앞선 `R154-1`은 `08291cc`로 커밋·푸시, AXCluster 배달 3/3 통과. MotionForge 전환 후 요청자 배달 3/3, `.33` 실제 `--wait`와 첫 응답 라운드 누락 후 실제 큐 복구를 확인하고 AXCluster로 되돌렸다. 상세는 Redmine #799 노트가 정본이다.

## 후속 — 워커·요청자 확장 (2026-10-18 16:0x~, Claude 인수)

인수 직후 실측: 워커 3대(`.43` 1.3.3 · `.2` 1.3.3 · `.33` 1.3.2)는 agy 설정에 **모델 지정이 없었다**(`.43` 은 설정 파일 자체 부재). 네 기계 모두 `--model`·`--log-file` 지원, `.43` 의 `agy models` 가 정본 id 를 돌려준다. 워커가 실제로 어느 모델로 돌았는지는 로그에 해석 줄이 없어 **미확인**이다.

사용자 결정(이 세션): 권장 설계 · 로컬 서브 에이전트 3개 · `__main__.py` 수정 허용 · ⓐ `usage.py` 워커 배달 · 실제 모델 **미상도 거절**(마스터 포함) · 워커 모델 id 는 `gemini-` 접두 필수.

| 자리 | 바뀐 것 |
|---|---|
| 공식 검사 실패 | `test_context_synth` 의 주입 자리를 `_run_raw`·`_catalog_run`·사례별 상태 파일로 이동(테스트만) |
| `bundle.py` · `__main__.py` | `backends.agy_model`(정본 `agy_models.DEFAULT_MODEL` 하나) 배달 · `check` 가 없음·다름을 FAIL · 워커에 `work/usage.py` 배달 · `agy_models.py` 는 배달 목록 밖(테스트로 고정) |
| `session1_conductor.py` (`.2`·`.33`) | `--model`·`--log-file` · 모델 부적합 → agy 미실행 rc 78 · 파서 부재·실제 모델 불일치·미상 → rc 79(증거 보존) · 판정 로그 줄 |
| `gemini_report.py` (마스터·`.33 --remote`) | `--model` 명시 · 부적합 → 종료 2 · 불일치·미상 → 종료 1(종전 「로그 없음 → 3」 대체) · Argon 은 `--model`+`--allow-argon` 둘 다 |
| `agy_models.execute` (마스터) | 실제 모델 미상 → 실패 · 쿨다운·폴백 없음 |
| `ax-work`·`ax-gemini` SKILL.md | 직접 호출 명령에 `--model "$M"`·`--log-file` · 대조 규칙 |

검증: 공식 **168/168 OK**(174초) · `master/test_*.py` **172파일 전부 rc 0**. 실호출·배달은 아직 없다.

[주의] 실수 1건: 서브 에이전트 하나가 공유 작업 트리에서 `git stash`→`pop` 을 돌렸다. 직후 전 파일의 변경 표지를 대조해 유실 없음을 확인했다. 다음부터 서브 에이전트 지시에 git 상태 변경 명령 금지를 명시한다.

[주의] 배달 순서: 새 런처는 config 의 `agy_model` 과 `usage.py` 가 함께 가야 돈다(없으면 78·79 로 막힌다 — fail-closed). `update` 한 번이 둘을 같이 싣는다.

남은 것: 커밋·push(승인 대기) → `master.client update` → 기계마다 Flash Medium 실호출 1회(직접·중계·`--remote`)로 요청=실제 모델 확인. 원격 사용량 행의 요청/실제 모델은 `note` 에 실린다(구조화 필드는 큐 서버 변경이 필요해 범위 밖).

### 커밋·배달·실호출 (16:2x~16:3x)

- 커밋 `e6033ba` push · AXCluster `update` 3/3 OK(`agy_model` 대조 포함).
- `.43` 직접 호출(ax-work 명령 그대로): rc 0 · 로그 `label="Gemini 3.8 Flash (Medium)"` 만 · 배달된 `usage.py` 판정 일치.
- `.2` 세션 1 중계: 다음 실제 분산 작업 때 실증(사용자 결정). **미실증.**
- `.33` `--remote`(MotionForge 전환): rc 1 — agy `authentication failed or timed out`, SSH 세션 인증 실패로 보인다. 검사는 fail-closed 로 출력을 버렸다. 사유 문구가 인증 실패보다 「모델 미상」을 앞세운다. agy 1.3.2 로그 `Model ID … not in local config, defaulting to CCPA`. 증거는 세션 scratch 에만 있다. 확인 파일 삭제, 사람 변경 2건 보존.
- 🔴 `set_active_tool(align=True)` 결함: 서비스(12:44 시작)가 커밋(16:26) 이전 bundle 로 배달하고 도장은 현재 HEAD — `check` 3/3 FAIL. CLI `update` 로 복구, 복귀는 `align=False`.
- 서비스 재기동 미승인 — 마스터 서비스 경로(리뷰 큐 층2 등)는 아직 #830 이전 코드다.
- 사용자 결정 후속: `ax-projects`·`ax-task-queue` 재기동(16:35:49, health 200 · broker 는 변경 코드 미사용) · 결함 **#831** 등록(align 의 옛 코드 배달 + gemini_report 사유 순서) · `.33 --remote` 실증 보류.
