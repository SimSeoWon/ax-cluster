# 82. AXCluster 워커·Windows Codex 원격 실증·.33 상주 추론

2026-10-03 · Codex · 사용자 승인: AXCluster 마운트 시 .2·.33 워커 사용, 서버 클론·배달,
작동 확인, .33 상주 모델 설정, 공식 Codex 업데이트 및 메모리·AGENTS·CLAUDE·README 기록.
커밋·푸시 승인은 별개다.

## 배달 범위

AXCluster 요청자는 마스터다. 게임의 .33 requester 역할과 게임 트리는 별개다.

| 노드 | 체크아웃 | 결과 |
|---|---|---|
| .2 / janus | `E:\trunk\AXCluster` | 정식 클론 0ffd74b · worker · deliver/check OK |
| .33 / user | `C:\trunk\AXCluster` | 정식 클론 0ffd74b · worker · deliver/check OK |
| .43 / sim | `/home/sim/trunk/AXCluster` | 기존 worker · deliver/check OK · 소스 a0cbf42 |

기록 도중 마스터 HEAD가 외부에서 384a07a로 바뀌었다. 워커 소스가 현재 마스터와 동일하다고
주장하지 않는다. .2의 Claude 홈 MCP 미등록·중복 홈 스킬 경고는 Codex 실증과 별개로 남는다.

## 원격 설정과 실증

운영 정본: [Windows Codex 원격 실행](../docs/windows-codex-remote.md).
`workspace-write`, `windows.sandbox="unelevated"`, `sandbox_workspace_write.network_access=true`
및 `/IT /RL LIMITED` 런처를 함께 쓴다. SSH는 작업 데이터 전송과 예약 작업 요청만 한다.
**세션 1은 런처 이름이지 고정 SessionId가 아니다.** .33 USER SessionId 18에서 실행됐다.
예약 작업 요청 성공·CLI 버전 출력·배달 검사와 실제 파일 수정 성공을 구분한다.

큐를 쓰지 않는 단일 진단 파일만 허용했다. `.ax/config.json` 프로젝트와
`master/source_text.py` 상수를 읽고 `(nonce, 'AXCluster', ('utf-8','cp949','utf-8/replace'))`를
반환하게 했다. 토큰은 읽지 않았다. 마스터가 AST와 대상 밖 Git 변경 여부를 확인했다.

| 노드 / 실행 | 결과와 경계 |
|---|---|
| .2, .ax/work 최초 | 읽기 성공 · apply_patch 실패 · BLOCKED · 원인 미확정 |
| .2, master 소스 | rc=0 · DONE · 반환값 일치 · 대상 밖 변경 없음 · 회수 44초 |
| .43, master 소스 | SSH Codex rc=0 · DONE · 반환값 일치 · 대상 밖 변경 없음 |
| .33, 로그인 부재 /IT | 240초 timeout · 예약 작업 미실행 · 해당 진단 요청 취소 후 파일 보관·정리 |
| .33, SSH 직접 | CLI rc=0이어도 셸 -1073741502 (0xC0000142) · BLOCKED · 파일 미수정 |
| .33, 로그인 세션18 / CLI0.157.1 | apply_patch 실패 두 번 후 PowerShell 쓰기 우회 · 반환값 일치 · 회수84초. patch 성공 아님 |
| .33, 로그인 세션18 / 공식 CLI0.159.3 | **apply_patch completed · DONE · rc=0 · 반환값 일치 · 대상 밖 변경 없음 · 회수53초** |

최종 nonce `ba2516a1013347c984ec4ab5fc004460`.
원시 출력 `/tmp/ax_smoke_ba2516a1013347c984ec4ab5fc004460-33.out`.
file_change item_13은 지정 파일 하나의 in_progress→completed, command_execution 비정상
종료 항목 없음, 최종 `RESULT: DONE`. apply_patch 실패 시 BLOCKED로 멈추고 셸 쓰기로
우회하지 않도록 명시했다. 진단 파일은 워커 `.ax/work/ax_smoke_<nonce>/completed_probe.py`에
보관하고 원위치에서 정리했다. 최종 .33 체크아웃 clean.

업데이트는 실행 중인 Codex가 없음을 확인한 뒤 공식 npm registry에서
`@openai/codex@0.159.3`을 설치했다. 설치 후 `codex-cli 0.159.3` 확인.
업데이트 뒤 성공은 관측 사실이나 버전 차이가 근본 원인이라는 인과는 미확정이다.
샌드박스 우회·private desktop 변경·자동 로그인·진단 바이너리 배포는 하지 않았다.
운영 파이프라인 등재·⑺ 전진·finalize 전체 실증은 수행하지 않았다.

## .33 상주 모델

설치된 Ollama0.35.0은 최초 서버가 꺼져 있었다. 새 작업 `AX_Ollama33`을
S4U·Limited·AtStartup으로 설정하여 설치본 `ollama.exe serve`를 실행했다.
프로세스 SessionId0, 11434 리스너, 로컬·LAN API 확인. Codex /IT 작업과 별개다.

공식 `gemma4:e4b` pull 성공, 디스크 6,583,656,505 bytes,
digest `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c`.
context8192, keep_alive=-1 요청에 `AX_READY`, done=true, /api/ps 상주를 확인했다.
디스크 크기와 nvidia-smi 전체 사용량을 모델 VRAM 실측으로 대체하지 않는다.
재부팅 후 자동 시작·서버 재시작 후 상주 복원은 미검증이다.

브로커 .33:11434 (rtx3080, 합성 모델 pin) 추가 로컬 변경:
`test_broker_routing.py` 14/14, `test_broker_health.py` 11/11 통과.
**미커밋·미푸시·재시작 전**이므로 운영 브로커는 아직 기존 노드만 사용한다.

## 기록과 남은 일

사용자 명시 승인으로 repo AGENTS·CLAUDE·README, 홈 진입 문서의 machines 정본,
Windows 두 기계 문서, 인수인계, Claude 기존 메모리·색인에 기록한다. 홈 symlink 보존.
Codex/Claude 공용 기억은 양쪽 진입 문서가 가리키는 운영 문서다. Codex 내부 SQLite는
지원하는 쓰기 도구가 이 세션에 없어 직접 수정하지 않는다.
재합성76/347 외부 정정은 보존하며 이 실증을 재합성 완료로 해석하지 않는다.
문서 패치 context 불일치 실패는 적용 여부를 다시 읽어 대조했고 운영 설정 실패와 구분한다.

다음 운영 반영은 검토된 변경의 커밋·Gitea 푸시 승인, 브로커 재시작·실제 .33 라우팅 확인,
깨끗한 커밋에서 워커 재배달이다. 이번 진단 성공을 그 단계의 완료로 대신하지 않는다.


## 추가 실증 — 브로커 운영 반영 (사용자 별도 승인)

사용자 “브로커 반영해줘”, “그럼 병렬3개 전달되는거지?”에 따라 적용했다.
공식 재시작 도구로 ax-broker 기동 시각 11:43:35→12:43:44 KST,
active/running, Result=success 확인. 테스트 routing14/14·health11/11 재통과.
기본 샌드박스의 서비스 조회·HTTP EPERM은 승인된 좁은 명령을 샌드박스 해제로 실행했다.

인증된 /health에서 .43·.2·.33 모두 healthy, resident/pin=gemma4:e4b 확인.
브로커 /api/generate에 동시3개 진단(각 num_ctx8192, num_predict64)을 보냈다.
X-AX-Endpoint는 각각 rtx3060(1.30초), rtx3080(1.49초), bc250(9.68초),
모두 done=true·eval_count64. /health에서 세 노드가 동시에 inflight>0인 상태도 확인.
진단 스크립트 `/tmp/ax-broker-three-node-smoke.py`, parallel_three_nodes=true.

새 합성의 _workers는 상주 노드3을 읽어 동시3으로 실행한다. 이미 시작한 배치는 n을
시작 시 한 번 계산하므로 동시 수가 자동으로 중간 변경되지는 않는다.
브로커가 운영 코드의 로컬 변경을 읽은 상태이며 커밋·푸시는 실행하지 않았다.
이 추가 실증이 앞의 “운영 반영 전” 상태를 갱신한다.
