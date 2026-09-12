# Codex SSH Session 0 원인과 작업 범위

작성일: 2026-09-12  ·  대상: Windows 워커 `.2`  ·  관련: Redmine #401

## 결론

Claude가 토큰을 모두 사용했을 때 SSH로 워커 Codex를 호출해 작업을 넘기는 목표는
유효하다. `.2`에서 Codex 모델 호출 자체는 성공했지만, Windows OpenSSH가 만드는
Session 0에서 Codex sandbox 자식 프로세스가 실패했다. 재로그인·`ssh -t`·ConPTY로는
해결되지 않는다.

## 실증

같은 SSH Session 0에서 실제 Codex 모델과 같은 셸 명령을 실행했다.

| 실행 파일 | 결과 |
|---|---|
| 설치본 `codex-cli 0.153.4` | 셸 자식 실패, 출력 없음, `-1073741502` (`0xC0000142`) |
| 패치 빌드 `codex-cli 0.153.0` | `cmd.exe /d /c echo AX_CLOUD_SESSION0_OK` 성공, rc=0 |

패치 빌드는 원인 확인용으로만 만들었다. 워커에 배포하지 않았고 기존 설치본도 바꾸지
않았다.

## 원인

`elevated` Windows sandbox가 제한 토큰 자식을 만들 때 Session 0의 Window Station/Desktop에
자식 로그온 SID용 접근 ACE가 없다. Session 1 대화형 실행은 통과하지만 SSH Session 0은
실패한다. 이는 [openai/codex#37722](https://github.com/openai/codex/issues/37722)의 공개
원인 및 A-B-A 결과와 일치한다. ConPTY는 터미널 입출력만 제공하며 로그온 세션과 보안 ACL을
옮기지 않는다.

## 🔴 이 원인이 막는 것은 `#401` 하나가 아니다

같은 뿌리가 **`#402`(코덱스 배달 경로)의 `.2` 칸**도 막고 있다. `.2` 에서는 **사용자 구성
stdio MCP 가 하나도 뜨지 않는다** — 명령·경로를 셋으로 바꿔 전부 실패했다(상대·런처 /
절대·런처 / 절대·실제 exe). HTTP 인 `ax-projects` 는 붙는다(자식 프로세스가 없다).
[주의] **`node_repl` 이 살아 있는 것은 반례가 아니다** — 그 항목 env 의
`SKY_CUA_NATIVE_PIPE=1` 이 말하듯 **네이티브 named pipe** 를 쓴다.
같은 배달본이 `.43`(리눅스)에서는 `ax-client/get_anti_patterns (completed)` 로 완주했으므로,
**배선이 아니라 그 기계의 환경**이라는 것이 대조군으로 확정됐다. 이 이슈가 풀리면 `#402` 의
`.2` 칸도 함께 닫힌다.

## 🔴 미결 — 지금 `.2` 는 그 「채택하지 않는다」는 상태로 돌고 있다

아래 「운영 판단 2」는 `unelevated` 를 운영 해법으로 채택하지 않는다고 적지만, **`.2` 의 현재
설정이 바로 `sandbox = "unelevated"`** 다(2026-09-11 사용자 승인). `elevated` 로 되돌리면
편집·커밋이 다시 죽는다(4전 4패 기록). 즉 **「채택하지 않는다」와 「지금 그 상태다」 사이에
결정이 비어 있고, 그것은 사람이 고를 자리다**:

    ⓐ 유지          네트워크 격리 상실을 감수한다 (upstream #35940)
    ⓑ elevated 복귀  워커 실행 불가로 회귀한다
    ⓒ 빼둔다        upstream 릴리스까지 `.2` 를 codex 지휘자에서 제외 — 🔴 **사용자 확정
                    2026-09-12.** 설정은 `unelevated` 그대로 두고(되돌리면 편집·커밋이 죽는다)
                    `.2` 를 codex 지휘자로 쓰지 않는 것으로 막는다

[중요] **ⓒ 는 결정만이 아니라 코드로도 막혀 있다.** `conductor.worker_mode_readiness` 가 전환
전에 Windows Codex 의 Session 0 sandbox 셸 probe 를 실제로 돌리고, 실패하면 **모드 상태를
바꾸지 않는다**(`b326cba`). 실측 2026-09-12: `codex` 로 전환 시도 → `.2` 셸 probe exit 1 →
**거절**. 마스터 서비스는 전부 지금 코드로 돌고 있음을 확인했다(`service_freshness`).

## 운영 판단

1. 로그인 재시도는 해결책이 아니다. `.2` Session 0에서 모델 호출까지 이미 성공했다.
2. `unelevated`는 임시 우회일 뿐 네트워크 격리와 파이프 자식 문제를 잃을 수 있으므로
   운영 해법으로 채택하지 않는다.
3. 고정 SID DACL 스크립트나 전체 DACL 복원도 운영에 넣지 않는다. 동시 실행을 깨뜨릴 수 있다.
4. 정식 upstream 수정이 포함된 Codex 릴리스가 나오면 그 실행 파일만 워커에 배포한다.
   직접 패치를 유지해야 할 때만 별도 CI/Windows 빌더에서 빌드하고, Rust는 워커에 설치하지
   않는다.

## 범위 통제

이번 세션의 Rust 빌드·온보딩 코드 추가는 진단 범위를 넘어선 잘못된 변경이었다. 최종 운영
변경으로 간주하지 않는다. 신규 워커 온보딩은 upstream 릴리스·공식 설치 경로·해시 검증이
확정된 뒤 별도 설계한다.

[완료] **정리는 끝났다** (이 보고서 커밋 `f055b94` **이전**에 실행됐다 — 초판의 *"다음 작업에서
되돌리고"* 는 낡은 서술이라 정정한다):

    revert   3495d93 · 9aa2467 · 71e82fd   (운영 코드 커밋 e1ebf5d·647c0a4·8a202b6 을 되돌림)
    삭제      임시 artifact 370MB
    워킹트리   깨끗

[중요] **`.2` 는 건드리지 않았다 — 마스터 세션이 실물로 대조했다**: 설치본 `0.153.4` 그대로,
`~/.codex/config.toml` 의 `[mcp_servers.ax-client]` 와 `[windows] sandbox` 보존. 실증 중
`[projects.'c:\users\janus'] trust_level` 한 줄만 추가됐다(무해).

## 다음 작업

- [완료] Redmine #401 에 이 문서 링크와 실증 표를 등재했다 (2026-09-12).
  [주의] Codex 세션은 API 키를 못 읽어 못 했다 — **비밀 저장소 차이가 아니라 샌드박스다**:
  `redmine.api_key()` 는 `AX_REDMINE_API_KEY` → **`docker exec redmine-db-1 psql`** 순인데,
  Codex 기본 샌드박스가 그 실행을 막는다. 해법은 그 명령을 승인하거나 환경변수를 주는 것.
- upstream 수정 릴리스 여부를 확인한다.
- 릴리스가 없으면 운영 코드가 아닌 별도 실험 브랜치/CI에서만 패치를 관리한다.
- 워커 지휘자 readiness는 `.2` Codex 셸 검증이 통과하기 전 `codex`로 전환하지 않는다.
