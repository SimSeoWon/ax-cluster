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
변경으로 간주하지 않으며, 다음 작업에서 해당 커밋을 되돌리고 이 보고서만 보존한다. 신규
워커 온보딩은 upstream 릴리스·공식 설치 경로·해시 검증이 확정된 뒤 별도 설계한다.

## 다음 작업

- Redmine #401에 이 문서 링크와 위 실증 표를 등록한다.
- upstream 수정 릴리스 여부를 확인한다.
- 릴리스가 없으면 운영 코드가 아닌 별도 실험 브랜치/CI에서만 패치를 관리한다.
- 워커 지휘자 readiness는 `.2` Codex 셸 검증이 통과하기 전 `codex`로 전환하지 않는다.
