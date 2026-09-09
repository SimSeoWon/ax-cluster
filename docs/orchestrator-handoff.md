# 현재 AX 작업 인수인계

> [중요] **한 벌만 유지한다.** 새 파일을 만들지 말고 이 파일을 덮어 쓴다.
> 양식은 `docs/15-orchestrator-handoff.md` §15.5 · 공용 규칙은 `docs/orchestrator-rules.md`.
> 모르는 상태는 **`미확인`** 으로 적는다. **이 기록은 잠금이 아니다** — 실행을 막지 않는다.
> 🔴 **여기 적힌 「완료」를 그대로 믿지 않는다.** 받는 쪽은 HEAD·dirty diff·이슈·프로세스를
> 직접 대조한다 (근거: `orchestrator-rules.md` §5).

- **갱신 시각**: 2026-09-10 00:05 KST (UTC+9)
- **지휘 도구 / 세션 식별자**: Claude Opus 5 (1M) · `session_013ARKFveJVpq2Kk4prTGZRM`
  담당 기록: `conductor.json` `agent=claude` — [주의] `why`/`at` 은 **2026-09-08 것 그대로**다
  (갱신하지 않았다). [주의] **잠금이 아니다** — Codex 쪽에서 `codex` 로 바꾸면 된다.
- **상태**: 🔴 **라이브 실증 대기 — `.33` 등재 한 번만 남았다.** 클러스터는 깨끗하다.

## 🔴 바로 다음 작업 — `.33` 에서 분산 작업 등재 (실증)

**모든 수정과 정리가 끝나 있다.** `.33` 에서 **새 세션**을 열고 등재하는 것 하나뿐이고,
그 한 번이 **넷을 동시에** 잰다:

    ①      `.2` 의 codex 가 실제 골조 작업을 완주하는가   (프로브만 통과 · 실물은 처음)
    ③      `needs_revision` 이 다시 파견되는가            (`b786f1f`)
    ⑹      `.33` 에 완료·실패 고지가 실제로 나가는가       (한 번도 실측 안 됐다)
    `#385` 워커 지휘자로서 codex 가 **두 대에서** 도는가

[중요] **`.33` 세션을 새로 열어야 한다** — MCP 는 세션 시작에 한 번만 붙는다(리포트 52).
[중요] **워커 모드는 `codex` 다** — `lane` 으로 내리지 않았다. 사용자 지적:
*"임시로 이전 방식으로 돌아가는건 그냥 회피하는거잖아"*. 실증 중 `.2` 가 또 막히면
**그때 `claude` 로 스왑**한다 — 그것이 `#385` 가 하라고 만든 동작이고 스왑 자체가 실증된다.

## 사용자 결정 · 승인 범위 · 근거 / 미결 질문

- 🔴 **회피하지 않는다** (사용자 2026-09-09). 내가 `lane` 으로 내려 실증하자고 제안했다가
  정정받았다. `lane` 은 **생성이 마스터 한 대에 몰리는** 구조이고(429 하나로 4조각 중 3이
  죽은 2026-09-04 가 그 결과), `#385` 의 워커측 지휘자가 그 병목을 흩는다.
  **「분산」이라는 이름값을 하게 만드는 것이 이번 모드다.**
- **실증 더미는 남기지 않는다** (사용자 2026-09-09) — `#390` 은 삭제했다.
- 🔴 **미결 — 워커 지휘자 기본값.** 상수는 여전히 `_UNDECIDED_DEFAULT`(값 `lane`)이고
  **저장 상태는 `codex`** 다. 사람이 정하면 이름과 값을 함께 바꾼다.
- 🔴 **미결 — `#233`·`#229` 의 처분.** 2026-09-06 감사 노트의 `[주의]` 단서가 그대로다.
  앞선 감사자가 일부러 「완료」로 안 넘긴 것으로 보여 이번 세션도 닫지 않았다.
- **미결 — 속도·비용.** *"워커 2대 = 12% 빠르고 90% 비쌌다"*(2026-08-09)는 **lane 시절**
  수치다. 병목이 마스터였으니 워커를 늘려도 안 빨라진 것이 당연하다. 워커측 지휘자에서
  산수가 달라질 **가능성**이 있지만 **추측이다** — 이번 실증이 처음 잰다.

## 저장소 · 브랜치 · HEAD / 미커밋 파일

    저장소   ~/ax-cluster   브랜치 main   HEAD f54b2fd
             [완료] **세 곳 동기** — 로컬 · origin(GitHub private) · `.43` 모두 f54b2fd
             미커밋   docs/orchestrator-handoff.md (이 파일 · 커밋 승인 대기)

이 세션 커밋 2개:

    b786f1f  fix(dispatch) `needs_revision` 도 파견 대상이다 — work 이 멈추고 `.33` 이 끝을 못 들었다
    f54b2fd  fix(codex)    Windows 워커 샌드박스를 `unelevated` 로 못 박는다 — `.2` 가 파일을 못 썼다

## 완료한 작업 / 검증 명령·결과

**어제 등재분(`20260909_2305_ns_fdae9d57` · 4조각)이 실패했고 원인 둘을 찾아 고쳤다.**

- 🔴 **① `.2` 의 codex 가 파일을 못 썼다** — 모델이 아니라 **실행 환경**이다. `.2` 의
  `~/.codex/config.toml` 은 **데스크톱 앱이 관리**해서 `[windows] sandbox = "elevated"` 인데,
  그 러너는 세션 9 의 네이티브 파이프를 쓴다. SSH 는 세션 0 이라 안 닿는다:

      exec_command failed: CreateProcess { message: "Rejected(\"Failed to create unified exec
          process: timed out after 15000ms connecting runner pipe-in\")" }
      agent_message: "Unable to create probe.txt because the file-writing tools failed."

  🔴 **그런데 `codex exec` 는 rc=0 으로 끝난다** — `wcommit` ②의 실패 분기를 안 타고,
  되읽기에 골조가 그대로 올라와 층1 이 `[PSEUDO]` 로 막았다. 마스터에는 **「codex 가 코드를
  덜 썼다」로만 보였다.** 프로브로 값을 특정했다: `-c windows.sandbox="unelevated"` →
  `.2` 에서 명령 실행·파일 쓰기가 살아났다(`RESULT: DONE` · 파일 확인).
  [주의] powershell 은 여전히 죽는다(`0xC0000142` — 세션 0 특유) · codex 가 `cmd.exe` 로 우회.
- 🔴 **③ `needs_revision` 이 파견 게이트에 안 보였다** — `#388` 이 만든 상태를
  `logic_claim` 에만 알리고 `autodispatch` 에는 안 알렸다. 실측:

      23:20:34  [revise] c1e3d128 1/3 — 재시도로 보낸다        → needs_revision
      23:29:07  안 건다 — pending 태스크가 없다 (멱등)         → 아무도 안 집는다

  work 이 terminal 3/4 에서 멈춰 `merge_status` 가 `ready_for_review` 로 안 뒤집혔다
  ⇒ **`.33` 은 끝을 영영 못 듣는다**(정본 ⑹ 이 통째로 죽는다).
  [주의] 같은 날 `267f22a6` 의 2·3차 시도가 이어진 것은 배관이 아니라 **우연**이다 — 마침
  `.33` 이 `[SKELETON-FIX]` 를 push 해 새 파견이 걸렸다. 그 우연이 결함을 가렸다.
- **회귀 4903/4904** (`test_autodispatch` 19/19 · `test_runner` 80/80 · `test_projects` 63/63).
  남은 1건은 `#393` 뿐이다.
- 🔴 **배선을 실물 probe 로 확인했다** — ① 수정이 `facts.windows` 조건부라 **판정이 틀리면
  수정이 조용히 안 먹는다.** 그 자리를 쟀다:

      192.168.0.2   worker  os=windows  windows=True   → sandbox 플래그 실림: True
      192.168.0.43  worker  os=linux    windows=False  → 실림: False (의도대로)
      192.168.0.33  requester                          → 파견 대상 아님

  [주의] `ax-dispatch.service` 는 oneshot 이라 **재기동 없이 새 코드를 쓴다** — 따로 재시작할
  것이 없다.
- **정리 전수 확인** — NS 원격 `main` 하나(d93e7c8) · 큐 works 0 · tasks 0 · 3대 전부 `main`
  dirty 0 · 보류 없음 · 레드마인 `#390` DELETE 204 (`#386`·`#361` 보존).
- **일감 3건 등재** — `#391`(워커 stdout 폐기) · `#392`(work 모드 스탬프 수정 표면 부재) ·
  `#393`(test_mcp_servers 도구 수).

## 미검증 / 실패·보류 사유

- 🔴 **라이브 실증이 전부 미검증이다** (위 §바로 다음 작업의 넷). 프로브는 임시 폴더에
  파일 하나 쓴 것뿐이고, **실제 골조 작업은 무게가 다르다.**
- 🔴 **`#388` 의 「다음 시도가 피드백을 읽는가」는 어제도 못 쟀다** — 워커가 애초에 아무것도
  안 썼으므로 잴 재료가 없었다. 배관(피드백 커밋·상한 3·종결)만 확인됐다.
  [주의] 이번 실증에서도 층1 이 안 막으면 **또 못 잰다.** 그때는 「못 쟀다」로 적는다 —
  **없는 실패를 만들어 재지 않는다.**
- **`#387` 미착수** · **`#384` ⑥ 종결 미착수**(두 방향 인계의 시간·설명량 계량) ·
  **Codex MCP 미배선**(`~/.codex/config.toml` `[mcp_servers]` 0건) — 셋 다 그대로다.
- **실패한 것 없음.** rc≠0·차단·예외로 멈춘 자리는 없다.
  [주의] 하네스가 `-s danger-full-access` 프로브를 한 번 막았고, 그 갈래 없이
  `windows.sandbox` 로 원인을 찾았다.

## 실행 중인 서비스 작업·프로세스 / 로그 위치

    상시    systemd 6종 active · `ax-dispatch.path` 보류 없음(`hold.json` 없음)
    큐      works 0 · tasks 0 (23:58:44 재기동)
    모드    `~/.cache/ax-dispatch/mode.json` = **codex**
    로그    파견 로그가 정본 — `journalctl -u ax-dispatch.service` / `-catchup`
    서브에이전트  없음

## 관련 문서 링크

- `docs/orchestrator-rules.md` · `docs/15-orchestrator-handoff.md`
- `docs/16-worker-orchestrator-mode.md` — §16.6 지휘 상태 표면 · §16.8 `reverify` · §16.9 스탬프
- 리포트 `57`(Codex→Claude 인계) · `58`(revise 루프 · work 모드 스탬프)
