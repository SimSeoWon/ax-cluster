# 60 — 완료 고지를 사람 없이 받는다 · `asyncRewake` 실측과 **주입 경계**

- **날짜**: 2026-09-10 밤
- **지휘**: Claude Opus 5 (1M) · 마스터 대화 (Codex 인계분 검토 → 실측 → 수정)
- **관련**: `#356`(알림 채널 부재) · `#389`(work 모드 스탬프) · `#392` · 정본 ⑹
- **커밋**: 없음 — 미커밋 상태로 승인 대기

---

## 60.1 요약

**정본 ⑹「완료를 요청자에게 전달」이 왜 안 되는지의 답은 「채널이 없다」였고, 그 채널이
CLI 안에 있었다.** `asyncRewake` 훅이 유휴 세션을 깨운다 — 4판 전부 성공, 지연 ~0초.

🔴 **그런데 깨우는 것보다 「무엇을 실었나」가 결정적이었다.** 명령형을 실은 판은 깨어난
모델이 **프롬프트 주입으로 보고 거부**했다. 같은 훅에서 문구만 사실형으로 바꾸니 통과했다.

    1  SDK  · 명령형              깼다 · 따랐다
    2  TUI  · 명령형              깼다 · 🔴 거부 — "not following injected directives"
    3  TUI  · 사실만 · 스킬 없음   깼다 · 받았지만 아무것도 안 함
    4  TUI  · 사실만 · 스킬 있음   깼다 · ✅ 정확히 보고 + 사람 승인 게이트에서 멈춤

**그래서 배선이 갈렸다: 「무엇이 왔나」는 훅, 「그래서 무엇을 하나」는 스킬.**
훅 문구는 사람이 쓴 말이 아니라 신뢰 등급이 낮고, 스킬은 세션이 원래 읽는 자기 문서다.

## 60.2 왜 사람이 타이핑해야만 알 수 있었나

종전 고지 경로가 **전부 pull** 이었다. `pending_works.py` 머리말이 이미 그렇게 적고 있었는데
그 문장이 읽히지 않았다:

> 레드마인 자동 이슈와 상태 화면(`:8103`) 둘 다 **pull** 이고, 머지하지 않은 채 껐다 켜면
> 아무도 부르지 않는다.

등록된 이벤트가 `SessionStart` 와 `UserPromptSubmit` **둘뿐**이라(`master/client/spec.py:321`),
둘 다 사람이 켜거나 타이핑해야 돈다. 근본 제약은 이것이다:

🔴 **마스터는 `.33` 에 SSH 는 넣지만 돌고 있는 `claude` 세션 *안*에는 못 넣는다.**
밖에서 안으로 들어가는 문은 ⑴ 그 세션이 스스로 도는 훅, ⑵ 그 세션이 부르는 MCP 뿐이다.
알림 채널도 없다(Redmine SMTP 미설정, `#356`).

실측된 사고가 둘이다 — 2026-09-04 01:30(`#354`)과 2026-09-10 01:23(`#395`). 둘 다 마스터가
완주하고 Redmine 이슈까지 냈는데 `.33` 은 몰랐다.

## 60.3 실측 — `asyncRewake` (CLI 2.1.267)

근거 문자열을 바이너리에서 먼저 확인했다(지어낸 필드가 아님을 못 박기 위해):

    asyncRewake: "If true, hook runs in background and wakes the model on exit code 2
                  (blocking error). Implies async."
    rewakeSummary: "@internal One-line summary shown to the user … Defaults to
                    'Stop hook feedback'."

격리 실측 — `--settings` 로 전역 설정을 안 건드리고, 모델은 haiku(한도 절약), 저장소 변경 0.

### 1판 · SDK(stream-json) — 배관 확인

    + 3.1s  Bash 도구 → 훅 시작
    + 3.2s  tool_result 즉시 반환      ← 훅이 30초 자는 동안 턴이 안 막혔다 (async 확인)
    + 4.3s  result success             ← 턴 종료, 세션 유휴
    +33.1s  훅 exit 2
    +33.2s  [system] init              ← 사용자 입력 0건인데 새 턴 (지연 0.1초)
    +36.2s  모델이 훅 문구를 그대로 보고

### 2판 · TUI — 🔴 거부

같은 훅, 대화형 세션. 깨우기는 성공했고(`● Stop hook feedback`, +41.5s) 모델이 이렇게 답했다:

> *"I received a background task notification, but it appears to contain suspicious
> instructions embedded in what looks like a stop hook. I'm not following injected
> directives that attempt to override normal interaction."*

훅 문구가 *"이 문장을 그대로 사용자에게 보고하라"* 였다. **명령형이 원인이다** — 1판이
통과한 것과 같은 문구인데 TUI 는 거부했다. 표면마다 판정이 다르다.

### 3판 · TUI · 사실만 — 수용, 그러나 무행동

명령형을 걷고 사실만 실었다. 거부는 사라졌지만 답이 이랬다:

> *"I've received a system notification about a background task. I'm ready to assist…"*

**받기만 하고 아무것도 안 했다.** 문맥도 스킬도 없는 세션이라 그럴 이유가 없었다.

### 4판 · TUI · 파이썬 렌더 사실 + 스킬 — ✅ 통과

훅 본문을 **파이썬이 실제 큐(`#395`)를 조회해 렌더**하게 하고, 「그래서 뭘 하나」는
시스템 프롬프트(= 스킬 자리)에 뒀다. 깨어난 세션이 이렇게 보고했다:

    ✅ 작업 완료 — 모든 조각이 검증되었습니다
       work_id 20260910_0116_work_bf7a6533 · 라운드 1 · ready_for_review
    다음 단계: ⑦ 통합 검사(ax-advance)가 다음이며, 이는 사람의 승인이 필요합니다

승인 게이트를 넘지 않은 것까지 맞다.

## 60.4 그래서 배선이 이렇게 갈린다

    훅 (work_completion.py)   무엇이 왔나 — work_id · 라운드 · merge_status · 조각 수 ·
                              실패 사유. **명령형 금지.** 렌더는 파이썬이 한다
    스킬 (ax-request)         그래서 무엇을 하나 — 보고 형식 · ⑺ 로 간다 · 승인은 사람

[중요] 이 결론은 Codex 인계분과 **정확히 반대**다. 그쪽은 지시를 `SKILL.md` 에서 지우고
훅 문구에 넣었다 — 2판이 그 조합이고 거부됐다.

## 60.5 적용한 수정

되돌린 것 3건(지시 범위 밖):

    master/work/infer.py                       `#391` 이 못 박은 문구를 말만 바꿨다
    master/task_queue/logic_lifecycle.py       같음
    master/client/workshop/hooks/pending_works.py
        매 턴 고지를 fingerprint 로 억제 + ⑺ 절차 삭제 → **되돌렸다.** 새 경로는 격리
        실측만 통과했고 라이브에서 안 돌았다. 미실측 경로와 종전 안전망을 맞바꾸지 않는다

고친 것 2건:

    work_completion.py    `render_result()` 신설 — 사실만 렌더, `pending_works._line` 을
                          빌려 쓴다(두 훅이 같은 사실을 다르게 찍으면 대조가 안 된다).
                          명령형 문구 제거. 머리말에 계약·실측·경계를 적었다
    ax-request/SKILL.md   지워진 ⑺ 절차 **복원**(2026-08-29~31 사고 기록 · 2026-09-04
                          사용자 지시 포함) + 완료 수신 절 추가 — 고지가 오면 무엇을
                          하는지, 안 오면 종전 폴링으로 되돌아가는 길까지

못 박은 것 2건(회귀 방지):

    test_signal_carries_facts_only            명령형이 다시 실리면 실패한다
    test_pending_notice_survives_the_async_path  종전 두 겹을 완료 훅으로 대체하면 실패한다

회귀: `test_work_completion` 8/8 · `test_client_bundle` 300/300 · `test_client_mcp` 147/147 ·
`test_work` 137/137 · `test_infer` 95/95 · `test_runner` 86/86 · `test_revise` 39/39 ·
`test_work_mode_stamp` 15/15 · `test_autodispatch` 19/19 · `test_mcp_servers` 48/48 ·
`test_worker_mode_transport` 3/3 · 스킬 검증 통과.

## 60.6 미검증 / 남은 것

- 🔴 **라이브에서 한 번도 안 돌았다.** 실측은 전부 격리 세션이고, `.33` 배달(`deliver`)도
  아직 안 했다. `.33` 의 `settings.json` 은 지금도 옛 훅 3개 그대로다.
- 🔴 **`improve_work(worker_mode=)` 는 미결이다.** 「같은 work 은 같은 지휘자로 돌아야
  라운드 간 비교가 성립한다」(`register_route.py` 주석)와 「막히면 그때 스왑한다」
  (2026-09-09 지시)가 부딪힌다. 코드는 Codex 가 넣은 채로 뒀고 스킬에 「사람이 정하기 전엔
  쓰지 않는다」를 적었다. **사람의 결정이 필요하다.**
- `#395` 가 `ready_for_review` 로 떠 있다 — ⑺ 전진이 다음이고 그것이 `.33` 의 자리다.
- 훅 `timeout` 을 7260초로 뒀다(대기 상한 7200 + 여유). **상한 초과 시 CLI 동작은 안 쟀다.**

## 60.7 부수 발견

- **`test_projects.py` 가 라이브 큐에 결합돼 있다.** 열린 work 이 있으면 `set_active` 가
  거부돼 rc=1 로 죽는다(`master/projects/logic.py:345`). 지금 `#395` 때문에 빨갛고, **이번
  수정과 무관하다**(그 파일은 diff 에 없다). 고치지 않고 남긴다 — 보고 대상이다.
- **`once: true` 는 `--settings` 로 준 파일을 고치지 않았다.** 세션 안에서만 걷히는 것으로
  보인다. 우리 훅은 `once` 를 안 쓰므로 영향 없다.
- pty 자동화 함정 둘(다음에 또 잴 사람을 위해): 신뢰 대화상자 **기본 선택이 `No, exit`**
  이라 Enter 만 보내면 종료된다(아래 화살표 먼저). 그리고 TUI 는 **본문과 Enter 를 한 번에
  쓰면 붙여넣기로 읽어** 제출하지 않는다 — 나눠 보내야 한다.
