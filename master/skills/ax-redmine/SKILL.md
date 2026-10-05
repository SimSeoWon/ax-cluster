---
name: ax-redmine
description: AX 마스터에서 레드마인 일감을 조회·등록·노트·상태 변경·마일스톤 관리할 때 쓴다. "레드마인", "일감 등록", "이슈 조회", "노트 남겨", "일감 닫아", "마일스톤" 같은 발화에 발동. Claude·Codex·Antigravity 공용.
---

# ax-redmine — 마스터의 레드마인 조작

정본: `~/ax-cluster/master/skills/ax-redmine/SKILL.md`. 세 CLI 가 같은 파일을 링크로 읽는다.

## 1. 경로는 하나 — `ax-client` MCP

    조회   redmine_list_issues · redmine_get_issue · redmine_meta
    쓰기   redmine_create_issue · redmine_note(상태·완료율·마일스톤·부모) · redmine_link_commit
    버전   redmine_create_version · redmine_update_version · redmine_delete_version

- 모두 마스터 8101 `/api/v1/redmine/*` 를 requester 토큰으로 거친다. API 키는 세션에 없다.
- MCP 가 안 보이거나 호출이 실패하면 **사유를 보고하고 사용자에게 묻는다.**
  Python·curl·docker 직접 호출, 임시 스크립트, 예전 `/tmp` 경로 재사용으로 우회하지 않는다
  (사용자 결정 2026-10-05).

## 2. 어느 프로젝트에 쓰나

    AX 인프라 일감         `ax-cluster` (id 3)
    게임·도구 프로젝트      `<twin>/config.yaml` 의 `redmine.project` (modularstage · ns · kimodo …)

미설정이면 등록을 거절한다 — 다른 프로젝트로 폴백하지 않는다(`#293`).

## 3. 상태 — 이름을 추측하지 않는다

- 쓰기 전에 `redmine_meta` 로 실재하는 상태 이름을 확인한다.
- 닫힌 상태는 **「완료」뿐**이다. 「해결」은 열린 상태다.
- 닫을 때는 완료 근거(커밋 해시·라이브 결과)를 같은 노트에 싣고 `done_ratio=100`.
- 우선순위·제목·본문도 `redmine_note` 로 바꾼다(`priority_name`·`subject`·`description`,
  비우면 그대로). 우선순위 이름은 `redmine_meta` 로 확인하고, `description` 은 본문 전체 교체다.

## 4. 누가 닫나 (사용자 결정 2026-09-06 · 2026-10-05)

    AX 인프라 일감 (ax-cluster)    마스터가 작업·검증을 끝냈으면 마스터가 「완료」로 닫는다
    분산 작업(게임 소스) 일감        상태 전이는 `.33` 의 자리 — 마스터는 노트만
    분산 작업 마감                  `finalize_work(confirm=True)` 가 닫는다 — 손으로 닫지 않는다

## 5. 쓰기 규칙

- 노트·본문은 MCP 인자(JSON)로만 보낸다 — 셸 문자열을 거치면 백틱 구절이 조용히 사라진다.
- 쓴 뒤에는 `redmine_get_issue` 로 되읽어 노트·상태가 실제로 반영됐는지 확인한다.
- 일감 하나에 결과를 노트로 쌓는다 — 라운드마다 새 이슈를 만들지 않는다.
- 마일스톤 삭제는 되돌릴 수 없다 — 사람 승인 뒤에만 `confirm=true`.
- 「클러스터 작업 하자」는 열린 `[AX]` 일감 목록을 보여 주라는 뜻이다 — 고르는 것은 사용자다.
- 토큰·API 키를 출력하지 않는다.
