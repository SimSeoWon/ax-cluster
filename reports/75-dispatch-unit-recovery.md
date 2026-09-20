# 리포트 75 — 파견 유닛 복구 경로를 운영 설치까지 닫았다 (`#360`)

- 날짜: 2026-09-20
- 구현: `ebe5e6a` · 계약 보강: `de79ad4`
- 일감: [`#360`](http://192.168.0.57:8080/issues/360)

## 1. 문제

2026-09-05 실증에서 `ax-dispatch.service` 와 `ax-dispatch.path` 가 함께 failed 상태가 됐다.
깨우려면 `reset-failed` 가 필요했지만, 당시 NOPASSWD 표면은 허용된 서비스의 `restart`만
제공했다. 이후 `#647`이 `ax-dispatch.service` 재시작은 열었으나 두 구멍이 남았다.

- helper가 `.service`만 다뤄 `.path`의 failed 상태를 지울 수 없었다.
- 명령이 `restart`뿐이라 `reset-failed` 자체를 호출할 수 없었다.

이 이슈의 범위는 재발 방지가 아니라, 다시 죽었을 때 마스터가 사람 손 없이 상태를 복구하는
경로다. 그래서 제시된 갈래 중 ⓐ NOPASSWD 복구 경로만 구현했고, ⓑ start-limit 완화와
ⓒ catchup 지연 수용은 선택하지 않았다.

## 2. 구현

`scripts/ax-service-restart-root`가 기존 1인자 `restart <base>` 형태를 보존하면서
`<verb> <unit>` 형태를 추가했다. 새 동작은 다음처럼 좁혀져 있다.

- verb는 `restart`와 `reset-failed`만 허용한다.
- `reset-failed`는 허용된 AX 기반 이름 9종과 `.service`·`.path`·`.timer` 접미어만 받는다.
- 2인자 `restart`는 helper가 해석할 수 있지만 sudoers에는 열지 않았다.
- `restart`로 `.path`·`.timer`를 조작하는 권한은 추가하지 않았다.
- `reset-failed`는 상태만 지우며 유닛을 기동하지 않는다.

사용자 CLI에는 `--reset-failed <unit>`와 `--recover <base>`가 생겼다. `--recover
ax-dispatch`는 관련 `.path`·`.service`·`.timer`를 조회하고 failed인 것만 상태 해제한다.
반환 코드가 0이어도 최종 상태가 failed면 실패로 판정한다.

기존 1인자 형태를 보존한 것은 호환성 때문이다. sudoers는 명령줄을 문자 그대로 맞추므로,
helper 형태를 한 번에 바꾸면 새 sudoers가 설치되기 전까지 기존 재시작 권한이 모두 끊긴다.

## 3. 검증과 증명의 경계

| 조각 | 근거 |
|---|---|
| `reset-failed`가 failed를 지운다 | 사용자 유닛을 실제 실패시켜 `failed` → `inactive/success` 확인 |
| 판정 로직 | failed 주입 11갈래와 `rc=0` 뒤 failed 잔존 회귀 테스트 |
| helper·sudoers 권한 경로 | `--recover ax-dispatch` 3유닛, 종전 재시작, 허용·차단 갈래 라이브 확인 |
| 권한 경로 × 실제로 죽은 운영 유닛 | **미실측** — 운영 유닛을 고의로 죽이지 않았다 |

`start-limit-hit`는 사용자 유닛으로 두 차례 재현을 시도했지만 `exit-code`까지만 갔다.
따라서 “restart만으로 start-limit이 풀리지 않는다”는 이번 회차의 실측이 아니라 `#360`의
2026-09-05 사고 기록이다. 설계는 그 주장에 의존하지 않는다. helper가 `.path`를 다루지
못했고 `reset-failed` 표면이 없었다는 사실만으로 복구 경로의 결손은 확정된다.

구현 당시 검증은 `master/test_service_restart.py` 75/75와 전체 5739/5739였다. 운영에서는
`--recover ax-dispatch`가 관련 3유닛을 보고했고, 기존 `ax-status` 재시작 경로와 sudoers
허용·차단 계약도 확인했다.

## 4. 인계 뒤 재설치 완료

인계 당시 저장소와 설치본은 동작이 같고 주석 3줄만 달랐다. Codex가 2026-09-20 20:40 KST에
정식 설치기를 다시 실행했다.

    ./scripts/install-ax-service-restart install
    /home/sim/ax-cluster/scripts/ax-service-restart.sudoers: parsed OK
    /etc/sudoers.d/ax-service-restart: parsed OK

이어 공식 검증 경로도 통과했다.

    ./scripts/install-ax-service-restart verify
    /etc/sudoers.d/ax-service-restart: parsed OK

샌드박스 안의 첫 `ls`에서는 root 소유 파일이 `nobody:nogroup`으로 보였으나, 샌드박스 해제
상태에서 다시 잰 실제 값은 다음과 같았다. 이는 설치 실패가 아니라 UID 매핑 착시였다.

    /usr/local/sbin/ax-service-restart-root  root:root 0755
    /etc/sudoers.d/ax-service-restart        root:root 0440

helper의 SHA-256은 저장소 원본과 설치본이 일치했다. 설치기는 sudoers 원본과 설치본 모두를
`visudo -cf`로 검사했고, 설치본 공식 `verify`도 통과했다.

## 5. 종결 판단

선택된 갈래 ⓐ의 구현·회귀·라이브 권한 검증·운영 설치·기록이 모두 끝났다. ⓑ와 ⓒ는 대안으로
남아 있을 뿐 선택된 작업이 아니므로 `#360`을 계속 열어 둘 잔여 작업이 아니다.

다만 커밋·푸시는 사람 승인 게이트다. 이 리포트와 색인·인계서를 커밋한 뒤 그 커밋을 근거로
Redmine 노트를 추가하고 `[AX]` 일감인 `#360`을 완료 100%로 닫는다.
