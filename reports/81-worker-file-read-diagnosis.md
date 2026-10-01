# 81. 워커 파일 읽기 진단 — 두 워커 성공과 Windows 실행 세션 경계

2026-10-01~02 · 운영 코드 기준 커밋 `0d22882` · 사용자 승인 범위: `.2`·`.43` 실제 Codex
프로젝트·스킬 읽기와 MCP 진단, 후속 정식 CLI 업데이트. 단계별 기록은 아래에 보존한다.
프로젝트 파일·설정·ACL·워커 모드 변경 없음. 최신 프로젝트별 검증 범위는 마지막 절을 따른다.

## 확인한 사실

좁은 SSH 조회 스크립트 `/tmp/ax-worker-read-inspect.py`를 실행 승인받아 실행했다.
`.2`의 `E:\trunk\KimodoMotion_WebUI`에서 SSH 계정 `janus`가 다음 파일을 읽었다.

- `AGENTS.md`: 6,657 bytes
- `README.md`: 11,785 bytes
- `.agents/skills/ax-work/SKILL.md`: 13,778 bytes
- `.codex/config.toml`: 348 bytes

`codex --version`과 `codex exec --help` 모두 rc=0. 설치 버전 `0.153.4`,
Windows 홈 설정의 `sandbox="unelevated"`를 확인했다. 설정 값이나 파일을 변경하지 않았다.
공식 OpenAI 비대화형 문서와 CLI 참조에서 읽기 전용·ephemeral 옵션을 확인하고 설치 도움말과
대조했다. 아직 그 옵션으로 실제 Codex 읽기를 실행한 것은 아니다.

## 실패와 증명 경계

조회 명령 rc=1. ACL 출력 단계에서 Python이 `icacls`의 바이트 출력을 UTF-8로
잘못 해석해 대체문자 U+FFFD를 생성했고, cp949 표준출력에 이를 출력하면서
`UnicodeEncodeError`가 발생했다. 이는 파일을 읽지 못한 오류가 아니라 진단 출력 오류다.
이 지점에서 멈췄으므로 `.2` Claude MCP 이름 조회, `.43` 조사 및 실제 Codex 샌드박스
내부의 파일 읽기는 미실행이다. SSH 읽기 성공을 Codex 내부 읽기 성공으로 일반화하지 않는다.

실패 후 코드·설정을 고치지 않는 공용 규칙에 따라 스크립트를 추가 수정하거나
다른 실행 경로로 우회하지 않았다. 출력 인코딩 처리 수정 승인 후 재개가 필요하다.
운영 큐·기존 work·워커 모드·ACL·Codex/Claude 설정·프로젝트 파일은 변경하지 않았다.

공식 참조:
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/developer-commands?surface=cli

## 출력 수정 승인 후 재개 결과

사용자가 진단 출력 처리 수정과 재개를 승인했다. ACL 출력을 cp949로 디코딩하고
ASCII-safe JSON으로 출력하도록 좁은 스크립트만 수정했다. 두 워커의 SSH 조회 rc=0.
두 워커 모두 AGENTS·README·프로젝트 로컬 ax-work 스킬·Codex config를 읽었다.
`.2` ACL에 `CodexSandboxUsers:(OI)(CI)(M)`가 있다.
조회 시점에는 두 워커의 Claude `.claude.json` 프로젝트 로컬 MCP 이름 목록에
`ax-client`가 존재했다. 이전 등록 직후 경고는 이 시점의 부재로 재현되지 않았다.
이름 존재만 확인했으며 실제 Claude MCP 도구 호출 성공은 증명하지 않는다.

공식 비대화형 문서와 설치 도움말에 맞춰 실제 Codex를 `exec --json --ephemeral -s read-only`
프로젝트 cwd에서 실행했다. 모델을 바꾸지 않았고 `.2`에는 기존 `windows.sandbox=unelevated`
값을 1회 실행 인자로 명시했다. 파일 내용은 출력하지 않고 읽은 바이트의 SHA256만 출력하게 했다.
진단에서는 `ax-client` MCP를 1회 인자로 끄고 모델에 MCP 사용을 금지했다.
설정 파일·프로젝트 파일·권한·워커 모드는 수정하지 않았다.

- `.43`: rc=0. 실제 `command_execution`의 exit_code=0과 네 파일 SHA256을 SSH 측 해시와
  대조해 전부 일치 확인. `READ_PROBE_COMPLETE` 발화만으로 판정한 것이 아니다.
  해당 프로젝트 파일 네 개의 읽기 전용 Codex 실행 성공을 증명한다.
- `.2`: rc=1. HTTP 400 `invalid_request_error`:
  `The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account.`
  `command_execution` 0건이므로 실제 파일 읽기는 실행되지 않았다. ACL 오류로 판정하지 않는다.

실패 후 모델·설정은 고치지 않고 읽기 조사만 이어갔다.
`.2` 홈 `C:\Users\janus\.codex\config.toml` 최상위 model은 `gpt-6.1-sol`,
`.43` 홈 `/home/sim/.codex/config.toml`은 `gpt-5.6-sol`이었다.
두 프로젝트 로컬 config에는 model 키가 없어 이번 요청은 홈 기본값을 사용했다.
`.2` 캐시 목록에는 `gpt-6.1-sol`도 있으나 실제 요청은 거부됐다.
캐시의 이름 존재를 계정 사용 가능 여부로 일반화하지 않는다.

두 실제 실행에서 `http://127.0.0.1:8000/mcp` 연결 오류가 stderr에 있었다.
`.43`의 셸 읽기는 성공했으므로 이를 파일 권한 실패와 혼동하지 않는다.
해당 MCP 연결 문제는 변경·복구하지 않았고 별도 진단 범위로 남긴다.

다음 제안은 사용자 승인 후 `.2`에만 `--model gpt-5.6-sol`을 1회 지정해 같은 읽기 검증을
다시 하는 것이다. 홈 기본 모델의 영구 변경이나 새 모델을 워커 배포 정본에 넣는 작업이 아니다.
읽기 전용 SSH 세션 검증은 운영 `workspace-write`·Windows 세션1 분산 경로의 읽기/쓰기
전체 검증과 다르다. 사용자 최초 파일 읽기 실패 경로·오류도 아직 지정되지 않았다.

## .2 모델 1회 지정 승인 후 결과

사용자가 `.2`에만 `--model gpt-5.6-sol`을 1회 지정하는 재검증을 승인했다.
동일 프로브의 Windows 실행 인자에만 해당 옵션을 넣어 실행했고 홈 config는 수정하지 않았다.

모델 호출은 통과했다. Codex 자체 rc=0이지만 실제 `command_execution` 한 건은
`status=failed`, `exit_code=-1073741502` (`0xC0000142`), `aggregated_output` 빈 문자열이었다.
실행 명령은 WindowsPowerShell에서 승인된 `py -c` 해시 조회를 실행하는 형태였다.
네 파일의 해시를 얻지 못했으므로 진단 스크립트는 rc=1로 판정했다.
「Codex가 정상 종료했으니 파일 읽기도 성공」으로 처리하지 않는다.

`reports/61`·`reports/62` 전문과 대조했다. 과거에도 Windows SSH 직접 Codex 실행에서
같은 셸 오류가 있었고, 설치본을 바꾸지 않은 세션1 스케줄러 경유 실행은 성공했다.
이번은 SSH 직접 실행·read-only이고 운영은 세션1·workspace-write이므로 현재 운영
경로 전체가 고장이라고 단정하지 않는다. 동일 오류가 기존 세션 경계 결함과 일치하는
단서이며 구체적인 이번 DLL/보안 객체 원인까지 확정한 것은 아니다.

실패 후 코드·설정·권한 추가 수정 없이 멈췄다. 다음 단계 제안은 승인된 별도 진단으로
로그온된 사용자 세션(운영 세션1 경계)에서 같은 파일 읽기를 대조하는 것이다.
기존 운영 job을 재등록하거나 실패한 work를 되살리지 않으며, 임시 패치 Codex/Rust
바이너리를 운영에 넣지 않는다. `.2` 홈 기본 모델은 여전히 `gpt-6.1-sol`이어서 운영
런처가 홈 기본값을 쓰는 경우의 모델 지원 문제는 별도 해결 판단이 필요하다.

## 로그인된 사용자 세션 대조 — 성공

사용자가 세션1 대조 진단을 승인했다. 읽기 조회에서 SSH Python의 SessionId=0,
`janus` console SessionId=1 활성 행을 확인했다. `query user`는 해당 행을 출력했지만
rc=1이었으므로 그 출력만으로 성공 판정을 하지 않았다. 실제 진단 실행에서 프로세스
SessionId=1을 별도로 계측하고 세션0이면 즉시 차단하는 검사를 넣었다.

좁은 `/tmp/ax-windows-interactive-read-probe.py` 실행 승인 후 임시 작업 스케줄러 작업
`AX_ReadProbe_760900e0a6ea4763b4af4603ca8c7f58`를 Interactive·Limited로 등록해 실행했다.
운영 `AxConductor_*` 작업이나 AX 큐를 실행·수정하지 않았다. 같은 Codex 설치본,
`gpt-5.6-sol` 1회 지정, `read-only`, `unelevated`, 동일 4파일 SHA256 명령을 사용했다.

결과: 실제 프로브 SessionId=1, Codex rc=0, 셸 `command_execution` exit_code=0,
네 파일 해시 모두 SSH 기준 해시와 일치, `probe_ok=true`.

| 파일 | `.2` 세션1 실제 Codex SHA256 |
|---|---|
| `AGENTS.md` | `a249f4675ee428bfb766be676855701b02bcd7a4f2cafae016f1a84fe9392dc2` |
| `README.md` | `755fde2a159eec2854866a82148f7de3c8e2607f0475d8eacd12f39d21ce0a4e` |
| `.agents/skills/ax-work/SKILL.md` | `717de60eb08d2b2b0758e459cb2d2ce34a706658d477233581d7271327fe4eb9` |
| `.codex/config.toml` | `3f80dc912cde22025dda0bed1d34c799e4c1b460da627de512fbb290a0703461` |

종료 후 임시 작업은 `Unregister-ScheduledTask`했고 재조회에서 부재를 확인했다.
진단 코드·출력은 아래 좁은 TEMP 디렉터리에 보존했다. 사용자 파일 삭제는 없다.

`C:\Users\janus\AppData\Local\Temp\AX_ReadProbe_760900e0a6ea4763b4af4603ca8c7f58`

`.43` SSH 실제 Codex 읽기와 `.2` 사용자 세션 실제 Codex 읽기가 모두 성공했다.
이 네 파일에 대해 `.2`의 읽기 ACL을 추가로 풀어야 한다는 증거는 없다.
동일 모델·명령의 세션0 실패/세션1 성공은 Windows 실행 세션 경계와 일치한다.
DLL 내부 상세 원인을 새로 확정한 것은 아니다. 또한 `.2` 홈 기본 `gpt-6.1-sol`은
변경하지 않았으므로 기본 모델로 운영 호출할 때의 요청 거부 문제는 여전히 남는다.
운영 workspace-write·세션1 런처 전체 파이프라인, MCP 호출, 사용자 최초 오류의 다른
파일 경로, 실제 요청자 대화 수신은 이번 읽기 진단과 별개의 검증이다.

## 분산 Codex 실행 계약 — SSH와 실행 세션을 구분한다

SSH 접속 성공·SSH 계정의 파일 읽기·Codex 내부 셸의 파일 읽기는 서로 다른 증거다.
이번 `.2` 실측에서는 SSH 프로세스가 SessionId=0이었다. 같은 설치본·모델·읽기 명령도
로그인된 사용자 세션에서는 성공했다. 여기서 「세션1」은 기존 코드의 경로 이름이다.
향후에도 숫자 1만 요구한다는 뜻이 아니라 실제 로그인된 사용자의 대화형 Windows 세션을
사용한다는 뜻이다. SSH의 TTY 유무와 Windows SessionId, Codex 대화 이력도 구분한다.

현재 정본은 이미 Python으로 다음 경로를 구현한다.

```text
Windows + codex:
마스터 run_worker → SSH로 시도별 job.json 전송 → schtasks /run
  → /IT·LIMITED 사용자 런처 → 프로젝트 cwd에서 codex exec
  → out.txt·rc.txt → 마지막 done.flag(request_id) → 마스터 대조·산출물 검증

Linux + codex:
마스터 run_worker → SSH로 프로젝트 cwd에서 codex exec → 마스터 산출물 검증
```

- `master/work/runner.py`: `uses_session1`·`run_worker`·`run_worker_session1`이 경로 선택과
  시도별 `.ax/session1/<task_id>/<request_id>/` 결과 회수를 담당한다(`#695`).
- `client/init/residency.py`: 배달 때 프로젝트별 `AxConductor_*`를 `/IT /RL LIMITED`로
  등록한다. SSH는 기존 작업을 깨우는 제어 통로다. 로그인 세션이 없으면 실행되지 않을 수
  있으며 직접 세션0 실행으로 자동 폴백하는 방안을 이번 보고서에서는 제안하지 않는다.
- `client/runtime/session1_conductor.py`: 실행 파일·sandbox 플래그·cwd의 주인이다.
  마스터는 작업 데이터와 제한된 승인 설정을 보내며 임의 셸 명령이나 프롬프트를 job으로
  받아 실행하는 새 범용 원격 실행면을 만들지 않는다.
- `.33`은 요청자다. 작업을 보내는 대상에 추가하지 않는다. Claude 지휘자 실행은 현재
  Windows Codex 전용 경로를 타지 않으며 이번 진단 결과를 Claude에 일반화하지 않는다.

남아 있는 두 문제도 분리한다. 현재 `build_argv`에는 모델 지정이 없어 `.2`의 지원되지
않는 홈 기본 모델을 상속할 수 있다. 사용자 세션 경로만 맞춰도 이 모델 오류까지 해결되지는
않는다. `gpt-5.6-sol` 1회 진단 성공을 영구 모델 정책이나 배포 완료로 기록하지 않는다.
또한 현재 준비 검사의 `codex sandbox cmd.exe ...` 성공은 실제 `codex exec` 셸 도구와
계정 모델 사용 가능 여부의 증명이 아니다. 보강한다면 기존 준비 검사 안에서 운영 경로와
같은 경계의 증거를 확인해야 하며 별도 사람 게이트를 추가하는 설계가 아니다.

## Python을 포함한 스킬이 필요한가 — 권고와 미구현 범위

권고는 **짧은 스킬 지시 + 기존 Python 실행 경로 재사용**이다. 새 SSH/Codex 실행 엔진을
스킬 안에 복제하지 않는다. OpenAI 공식 문서상 스킬은 필수 `SKILL.md`와 선택적 scripts·
references로 구성된다. 절차 안내는 지시문에, 결정적으로 보장해야 하는 경로 선택·시도 식별·
결과 판정은 Python 런타임에 둔다. 스킬 로드만으로 Windows 세션이 바뀌지는 않는다.

공식 참조: [Build skills](https://learn.chatgpt.com/docs/build-skills).

현재 프로젝트 로컬 `ax-work`는 실행된 워커가 대상 소스를 읽고 본문을 작성하는 계약이다.
실행 전 세션 선택은 마스터 런타임의 책임이므로 워커 `ax-work` 내부에서 자신을 다시 SSH로
실행시키는 구조는 피한다. 마스터용 안내가 필요하면 기존 공용 MCP/파견 창구를 호출하도록
하고, Python 보조 스크립트가 필요해도 기존 런타임을 감싸는 얇은 진입점으로 한정한다.
홈의 별도 복사본을 새 정본으로 삼지 않고 저장소·배달 계약 안에서 관리해야 한다.

후속 구현 후보는 (1) 운영 모델 선택 계약 확정, (2) 실제 사용자 세션·프로젝트 cwd·실제
도구 결과를 기존 준비 검사에서 확인, (3) 그 경로를 안내하는 스킬 보강이다. 성공 판정은
SSH rc나 Codex rc=0·완료 발화만이 아니라 해당 시도의 도구 실행 결과와 산출물에 둔다.
진단용 `--ephemeral` 등 인자를 운영에 그대로 복사하거나 샌드박스를 해제하는 변경도 하지 않는다.

이번 요청에서는 보고서·인수인계서만 보강했다. 신규 스킬·Python 운영 코드·설정·모델·ACL·
서비스·큐는 변경하지 않았고 커밋·push·배포도 하지 않았다. 후속 구현과 실증은 별도 사용자
승인 범위로 남긴다. 항목·진행의 정본은 Redmine이며 이 목록은 새 진행 장부가 아니다.

## 정식 CLI 업데이트 — .43 완료 후 .2 사용자 세션 종료 대기

사용자가 두 워커의 정식 CLI 업데이트를 승인했다. 공식 npm `latest=0.159.3`와 OpenAI
GitHub 정식 릴리스 `rust-v0.159.3`(prerelease=false, 2026-09-30 22:57:34 UTC)을 대조했다.
임시 로컬 빌드가 아니라 upstream 정식 배포본이다. 두 워커의 변경 전 버전은 `0.153.4`였다.

읽기 전용 사전 조회와 큐 조회를 좁은 스크립트로 승인받아 실행했다. 큐 8건은 모두
merged/rejected/cancelled였고 `.43`에 실행 중인 Codex 프로세스는 없었다. `.2`에는
SessionId=1의 `codex` PID 3136·21988, `codex-computer-use-swift` PID 4236 및
SessionId=0의 `codex-windows-sandbox-service` PID 19516이 관측됐다. 실행 중인
사용자 세션의 용도는 확인하지 않았으며 강제 종료나 설치 덮어쓰기는 하지 않았다.

- `.43`: 기존 standalone 설치의 `/home/sim/.local/bin/codex update`를 승인된 좁은
  스크립트로 실행했다. rc=0, 새 호출 `codex-cli 0.159.3` 확인. 실제 링크 대상은
  `/home/sim/.codex/packages/standalone/releases/0.159.3-x86_64-unknown-linux-musl/bin/codex`.
  홈 config의 변경 전후 SHA256 일치(`config_unchanged=true`). 모델 설정 변경 없음.
- `.2`: npm 사용자 전역 설치(`C:\Users\janus\AppData\Roaming\npm`)의 `0.153.4`를
  유지한다. 사용자 세션을 저장·종료한 뒤 프로세스 부재를 재확인하고 업데이트해야 한다.

이번 단계는 2대 중 1대 업데이트이며 모델 호출·셸 읽기 재검증은 아직 하지 않았다.
특히 `.2` 기본 모델 지원 오류가 업데이트로 해결됐다고 기록하지 않는다.
좁은 실행 스크립트: `/tmp/ax-codex-update-preflight.py`, `/tmp/ax-codex43-update.py`.
프로젝트 파일·ACL·운영 런처·마스터 CLI·`.33`·서비스는 변경하지 않았다. 커밋·push 없음.

### 사용자 세션 종료 후 .2 업데이트

사용자가 `.2` Codex 종료를 알렸다. 재조회에서 사용자 `codex`와 computer-use 프로세스는
없고 기존 SessionId=0 샌드박스 서비스 PID 19516만 남은 것을 확인했다. 서비스를 종료하거나
재등록하지 않았다. 좁은 `/tmp/ax-codex2-update.py`를 승인받아 기존 사용자 npm prefix에
`@openai/codex@0.159.3`을 설치했다. rc=0, `codex-cli 0.159.3`, 홈 config 해시 불변.
두 워커 모두 정식 CLI 업데이트 완료(2/2)이며 기본 모델·권한 설정은 유지했다.

업데이트 뒤 `.43` SSH 실제 Codex 읽기 전용 진단은 rc=0, 셸 exit_code=0,
네 파일 해시 모두 일치했다. localhost:8000 MCP 연결 오류는 계속 있으나 읽기는 성공했다.
`.2`는 모델 1회 override를 제거한 `--home-model` 진단으로 로그인 사용자 세션에서
재검증했다. 실제 SessionId=1, Codex rc=0, 셸 exit_code=0, 네 파일 해시 전부 일치.
홈 기본 `gpt-6.1-sol`을 변경하지 않았는데 이번 호출에서는 종전 HTTP 400 모델 오류가
재현되지 않았다. CLI 업데이트 후 성공이라는 관측이며 서버 측 가용성 변화와 분리해
원인을 단정하거나 모든 계정·모델의 지원을 보장하지 않는다.

임시 작업 `AX_ReadProbe_f85c3d11c78c42a98f679fabaeb15660`은 제거·부재 확인했다.
로그는 `C:\Users\janus\AppData\Local\Temp\AX_ReadProbe_f85c3d11c78c42a98f679fabaeb15660`에
보존했다. `.2`에도 localhost:8000 MCP 연결 오류는 남았지만 실제 읽기는 성공했다.
기존 운영 AxConductor 작업·AX 큐는 호출하지 않았다. 업데이트·기본 모델 읽기 검증은
2/2 성공이나 Windows SSH 세션0의 업데이트 후 동작, workspace-write 분산 작업 전체와
MCP 실제 호출·`.33` 통보 수신은 이번 결과로 증명하지 않는다.

## MCP 직접 조회 — .2 연결 성공, 조회 도구 선택은 스코프 위반

사용자 승인으로 `/tmp/ax-worker-mcp-readonly.py`를 작성했다. 과거 임시 파일·추정 머신
경로 조회 오류 두 차례와 상대경로 대조 오류 한 차례로 각각 멈췄으며, 사용자 재개·수정
승인 뒤 확인된 배달본만 사용했다. 상대경로는 프로젝트 cwd 기준으로 대조한다.

`.2` 프로젝트에서 `codex mcp list --json`이 활성 `ax-client`를 확인했다. Python310과
상대 `.ax/lib/axmaster/clientside/client_mcp.py`를 프로젝트 cwd에서 그대로 실행했다.
MCP initialize와 tools/list 응답 정상, serverInfo=ax-client/1.0, 도구 목록 35개 수신.
따라서 이 단계의 stdio 연결·서버 기동은 성공이다. Codex 모델의 네이티브 호출 증명은 아니다.

그러나 선택한 `list_works` 실제 호출은 isError=true, HTTP 403을 반환했다.
`master/auth.py`의 WORKER_SCOPE에는 GET `/api/v1/works`가 없고 컨벤션 읽기
GET `/api/v1/anti_patterns` 등이 있다. 이는 의도된 워커 권한 경계에 맞는 거절이며
서버 다운·토큰 부재·MCP 연결 실패로 판정하지 않는다. 진단 도구 선택이 잘못됐다.
워커 권한을 넓히거나 요청자 토큰으로 바꾸지 않았다.

프로브 rc=1 뒤 `.43` 실행 전 멈췄다. 다음 진단은 사용자 승인 후 읽기 전용
`get_anti_patterns`로 바꾸는 것이다. 그 뒤 Codex 내부 실제 호출과 다른 활성 MCP의
검증이 남는다. `.2` 목록에는 localhost:8000의 unreal-mcp, 사용자 USER의 Python312를
가리키는 kimodo-keypose 등도 있다. 경로·설정 존재만 관측했고 각각의 호출 성공은 미검증이다.

### 허용된 도구로 재검증 — 직접 MCP 2/2, Codex 내부 1/2

사용자 승인 후 진단 호출만 `get_anti_patterns`로 바꿨다. 두 워커 모두 initialize·
tools/list·tools/call 성공, isError=false, `ok=true`, `exists=false`,
`project=KimodoMotion_WebUI`. 카탈로그 부재는 도구의 정상 응답이다.

이후 실제 Codex 기본 모델·read-only·ephemeral 호출을 승인받아 실행했다. 진단에서는
ax-client에 `enabled_tools=["get_anti_patterns"]`와 해당 도구의 approval_mode=approve만
1회 인자로 넣고 다른 MCP는 목록 이름별 enabled=false로 지정했다. 영구 config 수정 없음.

- `.43`: Codex rc=0, 실제 mcp_tool_call의 server=ax-client,
  tool=get_anti_patterns, status=completed, error=null, 응답 ok=true. 네이티브 호출 성공.
- `.2`: 실제 SessionId=1이지만 Codex rc=1, 도구 호출 0건. 시작 단계의 오류는
  `Error loading config.toml: invalid transport in mcp_servers.code-review`.
  직접 MCP 연결은 이미 성공했으므로 이를 ax-client 서버 장애로 판정하지 않는다.
  목록 이름을 config 키로 일괄 비활성화하는 진단 override가 실제 설정 층과 맞지 않는
  가능성을 먼저 조사해야 한다. code-review는 목록에서 이미 disabled였다.

실패 후 스크립트·워커 설정을 추가 수정하지 않고 멈췄다. 임시 작업
`AX_ReadProbe_af1256b6f0464736a68661d116be8eee`은 제거·부재 확인. 동명 Windows TEMP
디렉터리에 진단 로그를 보존했다. 다음은 승인 후 1회 비활성화 override의 설정 층을
대조하거나 그 override를 제외한 진단이다. 다른 활성 MCP와 분산 전체 검증은 남아 있다.

### .2 진단 override 제외 후 네이티브 호출 성공

2026-10-02 KST, 사용자 승인 후 이름별 enabled=false 인자를 진단 코드에서만 제거하고
`.2`를 재실행했다. 기존 config·기본 모델은 그대로이며 읽기 전용 도구 허용 인자만 유지했다.
실제 SessionId=1, Codex rc=0, mcp_tool_call server=ax-client,
tool=get_anti_patterns, status=completed, error=null, 응답 ok=true·exists=false·
project=KimodoMotion_WebUI. 완료 발화가 아니라 실제 MCP 이벤트로 판정했다.
앞선 invalid transport는 이 재검증에서 재현되지 않았다. 기존 워커 설정을 고친 결과가 아니다.

이로써 ax-client 직접 연결·조회 2/2, 실제 Codex 내부 읽기 전용 MCP 호출 2/2를 확인했다.
`.43`은 다른 MCP를 1회 비활성화한 진단이고 `.2`는 그 인자 없이 성공한 차이를 보존한다.
localhost:8000 unreal-mcp 연결 오류는 `.2` stderr에 계속 남았다. ax-client 성공을
다른 MCP 전체의 정상 상태로 확대하지 않는다. 분산 전체·실패 통보 수신은 미검증이다.

임시 작업 `AX_ReadProbe_40364e32005340c2bdcd4024cfe5c9fe` 제거·부재 확인.
동명 `C:\Users\janus\AppData\Local\Temp\AX_ReadProbe_40364e32005340c2bdcd4024cfe5c9fe`
디렉터리에 로그 보존. 운영 작업·큐·권한·서비스 변경이나 커밋·push는 없었다.

## 최종 범위 정정 — Kimodo는 Unreal 프로젝트가 아니다

사용자 지적 후 프로젝트 프로필과 배달 규칙을 확인했다.
`master/client/payload/profile/KimodoMotion_WebUI.yaml`은 `kind: code`, `purpose: tool`,
언어 Python WebUI·C++ 엔진 포크 서브모듈, 분산 대상 확장자 `.py`, 테스트 시작점
`webui/tests`, 패턴 `*_test.py`다. AX 워커의 기본 관리 MCP는
`master/client/spec.py`의 `MCP_BY_ROLE`에 선언된 `ax-client`다.

따라서 이전 설명에서 unreal-mcp 연결 오류와 「다른 활성 MCP 전체 검증」을 이 프로젝트의
미완료 조건으로 묶은 것은 잘못이었다. 오류 관측 자체는 보존하되 **이 비UE 프로젝트의
검증 완료 조건에서 제외한다.** 목록에 노출됐다는 이유로 필요한 MCP가 되는 것은 아니다.
다른 설정층 항목의 정확한 귀속이나 삭제 필요성을 확정하지 않았으며 설정 삭제도 하지 않는다.

현재 성공 범위는 워커 2대의 정식 CLI 업데이트·기본 모델 파일 읽기·ax-client 직접 조회·
실제 Codex 네이티브 읽기 전용 호출이다. 아직 남은 것은 `.33`이 요청하는 작은 `.py`
새 분산 작업의 파견→실행→회수→종결과 실제 대화의 완료·실패 고지 수신이다.
기존 cancelled work는 재개하지 않으며 UE 빌드·Unreal MCP는 이 실증에서 요구하지 않는다.
전진·finalize는 별도 사람 승인이다.

이 정정·인수인계서·보고서 색인의 문서 3개 커밋·push는 사용자 승인 후 진행한다.
새 스킬·운영 코드·프로젝트 설정 변경이나 추가 배포는 이번 문서 커밋 범위에 없다.
