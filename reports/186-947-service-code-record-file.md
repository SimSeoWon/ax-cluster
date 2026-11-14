# 186 — #947 서비스 신선도 기동 기록을 파일에도 · 판정 불가 사유 구분

2026-11-14 · Claude · 이 세션이 직접 구현(사용자 선택).

## 발단

#946 wrapup에서 `ax-projects`가 「의존 판정 불가(기동 코드 기록을 읽지 못했다 (journalctl rc=1))」로 나왔다.

조사해 보니 다음과 같았다.
- `journalctl --grep`은 맞는 줄이 0개면 rc=1을 돌려준다. 그래서 그 rc=1은 조회 실패가 아니라 **기록 부재**였다.
- 기록이 없던 이유는 저널이 4.0G 상한에 차서 회전했기 때문이다. 가장 오래된 줄이 10:10:02였고, 부팅은 10:09:24, `ax-projects` 기동은 10:09:42였다.
- 회전을 일으킨 것은 snap `nordvpnd`의 AppArmor DENIED audit이다. 10분에 91,535건이 쌓여 저널 보존이 약 9시간으로 줄었다.

사용자 결정으로 NordVPN을 마스터에서 제거했다(snap `--purge`, 크롬 확장은 사용자가 따로 제거). `ax-projects`는 재기동했다(19:35:55). 그래도 「보존 기간보다 오래 돈 서비스는 판정할 수 없다」는 구조는 남아서 #947로 등록했다.

RAG request_id `74598656d3874d82baa5b6c14454e56a`. `service_freshness`·`issue_wrapup`·세 진입점 문서와 실제 소스를 대조했다. 세 상주 서비스의 `__main__`이 `record_startup`을 부르고, 기록은 stdout(저널)에만 있었다.

## 변경 (`b9ec8e8`)

- `record_startup`
  - 같은 기록을 `~/ax-state/service-code/<unit>.json`에도 쓴다. 위치는 `AX_SERVICE_CODE_DIR`로 바꿀 수 있다.
  - 임시 파일을 쓴 뒤 `os.replace`로 바꿔 넣는다(원자적).
  - 결과는 `[service-code] <unit> 기동 기록 파일 …` 한 줄로 남긴다. 쓰기에 실패해도 기동은 계속된다.
- `_record`
  - 현재 invocation·감시 범위·버전과 맞는 파일을 먼저 읽는다.
  - 파일이 없거나 맞지 않으면 종전 저널 판독으로 폴백한다. 이때 판정 불가 사유 끝에 `· 파일: <사정>`을 붙인다.
- 저널 판독(`_journal_record`)의 사유를 셋으로 가른다.
  - 「기록 없음」: rc=1이면서 출력·오류가 모두 빈 경우, 또는 맞는 줄 0개.
  - 「회전 가능성」: 가장 오래된 저널 epoch가 기동보다 늦으면 두 시각을 함께 적는다. 가장 오래된 줄은 첫 줄만 읽고 끊는다(실측 0.05초).
  - 「읽지 못했다 (rc=N) — stderr 끝줄」: 진짜 조회 실패.
- 판정 정책은 그대로다. 판정 불가는 최신으로 접지 않고, 자동 재기동하지 않는다.

## 검사

- `test_service_freshness` 통과 81 · 실패 0 (신규 [7] 13건)
  - 종전 검사는 기록 파일을 버리는 임시 디렉터리에 쓰게 해서, 저널 경로를 그대로 검증한다.
  - 판정은 빈 임시 디렉터리를 읽는다. 실제 `~/ax-state`에 쓰이지 않은 것을 확인했다.
- `test_client_bundle` 661/661 · `test_issue_wrapup` 39/39 · `test_service_restart` 통과 75
- pyflakes 0 · 공식 통합 `Ran 199 tests / OK` rc0
- 실물(읽기 전용, 워크트리 코드로 운영 서비스를 판정)
  - `ax-broker`(부팅 10:09:42 기동, 재기동 없음)가 다음 사유로 나왔다: 「기동 코드 기록이 저널에 없다 — 저널 회전으로 지워졌을 수 있다 (가장 오래된 저널 1794618602 > 기동 1794618582, epoch) · 파일: 기록 파일 없음」.
  - 워크트리는 파일 시각이 새것이라 1차 거름을 통과하지 못하고 기록 조회까지 간다. 운영 checkout에서는 1차 거름으로 「최신」이다.

## 마감 뒤 확인할 것

이 모듈은 세 상주 서비스 모두의 의존이다. 그래서 wrapup이 「의존 변경」으로 판정해 재기동할 것으로 예상한다.
- 재기동 뒤 `~/ax-state/service-code/<unit>.json` 세 개가 생기는지
- 판정이 파일로 되는지(저널 조회 없이 깨끗한지)
- 결과는 Redmine 마감 노트에 덧붙인다.

미대조: #944 `[history]` 조회 rc1은 당시 저널이 이미 지워져 같은 원인인지 확인할 수 없다.

## 2회차 (T4) — 브로커 샌드박스

1회차 마감 뒤 실물에서 문제가 나왔다.
- `ax-task-queue`·`ax-projects`는 재기동하자 파일이 생겼다. 저널 grep 없이 파일로 판정되는 것도 확인했다.
- `ax-broker`(사용자 승인 재기동 19:50:09)는 `[Errno 30] Read-only file system`으로 파일을 쓰지 못했다. 유닛이 `ProtectHome=read-only` + `ProtectSystem=strict`이고 쓰기 허용 경로가 없었다.
- 실패 처리는 설계대로 동작했다. 기동은 계속됐고 로그 한 줄을 남긴 뒤 저널로 폴백했다. 그래도 브로커만 저널 보존에 기대는 상태가 남았다.
- 설계 때 유닛 샌드박스를 확인하지 않은 것은 내 누락이다. 검사는 임시 디렉터리라 이 경로를 볼 수 없었다.

사용자 「ⓐ로 진행해줘」에 따라 다음을 바꿨다.
- `master/systemd/ax-broker.service`에 `ReadWritePaths=-/home/sim/ax-state/service-code` 한 줄을 넣었다. 쓰기 허용은 그 디렉터리 하나뿐이다. `-`는 디렉터리가 없어도 기동을 막지 않게 한다.
- `test_units_can_write_record_947`을 추가했다. 상주 유닛 파일을 직접 읽어, 홈을 읽기 전용으로 묶은 유닛이 기록 디렉터리를 쓰기 허용하는지 본다.
  - 수정 전 유닛으로 돌리면 broker를 실패로 잡는다(되돌려 확인).
  - [주의] 처음에는 `ProtectSystem=strict`도 막는다고 가정했다. 그런데 `ax-projects`(strict + `ProtectHome=false`, `ax-state` 쓰기 허용 없음)가 실제로 파일을 썼다(19:48:25). 그래서 기준을 실측대로 `ProtectHome` 읽기 전용일 때로 좁혔다. strict가 왜 막지 않았는지는 설명하지 못했다.
- `test_service_freshness` 통과 84 · 실패 0 · pyflakes 0.
- 설치(`/etc/systemd/system` 복사 · daemon-reload · broker 재기동)와 파일 생성 확인은 마감 뒤에 하고 Redmine 노트로 남긴다.

최종 결과는 Redmine #947 마감 노트에 있다.
