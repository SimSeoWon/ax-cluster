# `client/` — 워커 측 계층

[중요] **코드는 여기 없다. `master/client/` 에 있다.**

실행되는 것은 전부 마스터에서 돈다(venv·레지스트리·SSH 키가 거기 있다). 이 디렉토리는
**개념상의 자리**이고, 실제 구현과 배달물은 이렇게 나뉜다:

| | |
|---|---|
| `master/client/bundle.py` | 머신 프로브 · config 생성 · CLAUDE.md 병합 · SSH 배달 + **해시 대조** |
| `master/client/skills/ax-work/` | 워커가 받는 **작업 절차 스킬** (정본) |
| `master/client/payload/CLAUDE.md` | 체크아웃용 프로젝트 가이드 정본 (`/init` 산출, **머신 중립**) |
| `master/client/__main__.py` | `python -m master.client probe\|plan\|deliver\|check` |

## 워커에 배달되는 것

    <체크아웃>/.ax/config.json            경로·능력·백엔드의 **유일한 출처** (마스터 생성)
    <체크아웃>/.ax/work/<task_id>/        작업 부산물 — `.git/info/exclude` 로 무시
    <체크아웃>/CLAUDE.md                  정본 본문 + [중요] **머신별 AX 관리 블록**
    <홈>/.claude/skills/ax-work/SKILL.md  작업 절차

[중요] **경로를 문서에 박지 않는다.** 2026-08-09 실측: `.2` 의 `.mcp.json` 이 `.33` 의 경로를
가리키고 있었다(한 워커 설정이 다른 워커로 복사됨). 그래서 머신별 값은 **마스터가 레지스트리를
근거로 생성**한다.

[중요] **배달했다고 믿지 않는다.** 쓴 뒤 되읽어 sha256 을 대조한다 — 실제로 두 번 잡았다
(PowerShell 이 BOM·CRLF 를 넣음 / 18KB 에서 stdin 이 안 닫힘). 지금은 `scp` 로 보낸다.

## 역할 (`role`) — `driven` 과 다른 축

    driven   닿을 수 있나        ssh | interactive
    role     시켜도 되나         worker | requester

[중요] `.33` 은 SSH 가 열려 있어도 **`requester`** 라 `drivable_hosts` 에서 빠진다 — 사람이
편집 중인 트리에 일감을 파견하지 않는다.
