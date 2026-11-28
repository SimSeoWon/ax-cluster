# 225 — 절차 강제의 구멍: 질문·입력·실패 장부와 멈춤 판정 (#1040)

사용자: *「스킬에 스크립트를 이용해 정적인 플로우를 강제하여 절차적 작업을 하도록 하는건데, 이걸 무시하더라구」*.
11-27 밤 Codex 세션 기록(`~/.codex/sessions/2026/11/27/rollout-2026-11-27T21-30-20-…jsonl`)과 Redmine #1037·#1039 노트를
대조해 네 사건을 확인했다(본문 표). 공통 원인 — 도구가 **형식**(순서·빈 값)만 강제하고 **내용**(그 답이 승인인가 ·
판정대로 이어 갔는가 · 실패가 누구 것인가)은 지휘 모델이 채운다. 산문 규칙은 있었으나 코드가 집행하지 않았다.

`issue_start_tool`: `repo=/home/sim/ax-cluster/.ax-issues/1040`, `start_rev=1f434fc9c804`. 분류 버그, 인터뷰 5단계 +
스펙 + 플랜(태스크 8 · 체크리스트 6 · 자율성 0.5) 모두 사용자 문답으로 확정. 진행 방식은 직접(사용자 선택).

## 사용자가 인터뷰에서 정한 것

- 심각한 것은 질문을 묻는 것이 아니라 **인터뷰 단계 자체를 건너뛴 것**이다.
- 질문은 추천 1번 + 다른 방안 2~3개(없으면 생략), 보기 밖의 채팅 답도 받는다.
- 확신도는 0~100. 수정이 나오면 0 으로 되돌리면 인터뷰가 끝나지 않으므로 **어긋난 만큼** 깎는다. 추천 1번을 고르면
  에이전트가 원하는 것과 같다고 본다. 깎는 폭은 실사용하며 고친다.
- 실증은 마감 뒤 운영 실물로(대역 근거로 C2·C5 충족, 운영 확인은 마감 노트).

## 구현

| 태스크 | 커밋 | 내용 |
|---|---|---|
| T1 | `d11d0a0` | `master/interview_ledger.py` 질문 장부 · 입력 장부 · `judge` · 관문 스위치(`interview_gate: enforce`, 기본 꺼짐). 표면 `interview_ask` — ax-projects · 8101 · ax-client |
| T2 | `c445c1b` | `UserPromptSubmit` 훅 `prompt_ledger.py` → 8101 `/api/v1/interview/prompt`(로그는 길이만, 원문은 트윈 장부) · fail-open |
| T3 | `930d0d5` | `interview.record`·`write_spec`·`plan_tools.set_plan` 이 쓰기 직전 판정 · 노트에 확신도 줄 · `divergence` 인자 · 가짜 getter 검사는 `gate=True` 로만 켜진다 |
| T4 | `dbaebf0` | 실패 장부 `record_check` · `plan_tools.start` 가 열린 실패를 가른다 — 경로가 전부 이번 일감 변경 안이면 resume, 밖·경로 모름이면 stop · `check_result_tool` |
| T5 | `b30b39e` | `Stop` 훅 `stop_gate.py` + 8101 `/api/v1/interview/stop` — 잠금 활성 + resume/next + 사유 없음이면 block. 사유 = 답 대기 질문 · stop · 사용자 멈춤 지시. 연속 3회 상한. 사유 문장은 사실만 |
| T6 | `4ad7247` | 배달 — `master_local`(Claude `settings.json` · Codex `hooks.json`) · `spec.MANAGED_HOOKS`(요청자만, 워커 제외). 옆 세션 보호(대화 기록에 `"issue_id": N` 이 있을 때만 막음). 멈춤 판정도 관문 스위치를 따른다 |
| T7 | `51d9282` | ax-plan · .33 ax-issue · `docs/issue-spec.md` §4 · 공용 규칙 §1.1·§1.9 · `machines/sim-desktop.md`(사전 동의) |

[주의] **T4 판정 범위를 스펙 문구보다 넓혔다.** 스펙은 「이번 일감 미커밋 변경」이었으나 00:35 원인(`SKILL.md:100`)은
#1039 T1 에 **커밋돼 있었다** — 미커밋만 보면 그 사례가 stop 이 된다. 「시작 리비전 이후 커밋 + 미커밋 + 새 파일」로 본다.
[주의] T7 작성 중 내 문구에도 같은 접두사 누락이 나 `test_skill_conventions` 53/54 — 이번 일감 변경 안의 실패라
새 규칙대로 고치고 다시 검사했다(54/54).

## 실증

대역 — 운영 서비스·설정 무변경. 실 Claude 세션 3회(`claude -p --model haiku --settings <임시>`, 가짜 8101 클라):

| 확인 | 결과 |
|---|---|
| 00:27 재현 — 그 일감을 다룬 세션 + 서버 block | 첫 Stop 차단 → 모델이 사실 문장을 받아 **2턴째로 이어 갔다**(주입으로 거부하지 않음) · `stop_hook_active` 두 번째 Stop 통과 |
| 옆 세션(일감 언급 없음) + 서버 block | 막지 않음, 1턴 |
| `UserPromptSubmit` | 사용자 문장이 원문 그대로 `/api/v1/interview/prompt` 로 · 모델 컨텍스트에 아무것도 붙지 않음 |

| 검사 | 결과 |
|---|---|
| `master/test_interview_ledger.py` | 60/60 — 22:15 원문 거절 · 질문 미등록 거절 · 확신도 50→70·80→100·70→35·90→80 · 00:35 resume · 변경 밖 stop · 00:27 block · 15:37 멈춤 지시 통과 |
| `master/test_prompt_ledger_hook.py` | 17/17 |
| `master/test_tagging.py` | 288/288(실물 라우트: requester 200 · worker 403 · 태그 없음 거절 · 원문은 장부에만 · 관문 꺼짐이면 막지 않음) |
| `master/test_client_master_local.py` · `test_client_bundle.py` · `test_client_spec.py` | 139/139 · 670/670 · 227/227 |
| 공식 통합 `-m unittest discover -s tests/integration -p test_axcluster.py -f -v` | rc 0, 223/223, 28.961초 |
| `python -m master.sweep` | rc 0, 249파일 · 13016/13016 · unittest 663/663 · 실패 0 |

## 마감 뒤에 남는 것 (운영)

1. 재기동(`ax-task-queue`·`ax-projects`) → 배달 → 운영 체크아웃에서 `master.client master-local --apply` → `--check`.
2. **Codex 훅은 사람이 `codex` 의 `/hooks` 에서 한 번 승인해야 돈다**(공식 문서 — 해시로 신뢰 기록, 바뀔 때마다).
3. `AXCluster/config.yaml` 에 `interview_gate: enforce` → 운영 실물 확인(입력 장부 기록 · 멈춤 판정 라우트).
4. `.33` 요청자 훅은 게임 프로젝트 배달(`update --all` 또는 마운트 전환) 때 간다 — 그 프로젝트 관문은 배달·check 뒤 켠다.
5. 비범위로 남김: 도구를 불러 보지 않고 단정하는 유형(21:55) · `.33` Codex 의 프로젝트 `hooks.json`.
6. 발견: agy 허용 목록에 #1037·#1039 의 `wayfinder_*` 도구가 빠져 있다(기존 차이 — master-local apply 미실행).

최종 결과는 Redmine #1040 마감 노트.
