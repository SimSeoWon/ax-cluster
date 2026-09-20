---
name: ax-fix
description: 자동 리뷰·주간 플랜을 **번호(R12 · P3)** 로 받아 와서, 지금 main 기준으로 아직 합당한지 분석하고, 사용자가 고른 항목만 RAG 를 쓰는 서브 에이전트가 `fix/<번호>` 브랜치에 고친다. "R12 검토해볼까", "P3 수정해볼까", "리뷰 목록 보여줘", "플랜 목록", "고칠 리뷰 있어?", "/ax-fix" 같은 발화에 발동. [중요] 분산 작업 검수(`#N 리뷰`·머지 검토)는 이게 아니다 → `ax-review`.
---

# ax-fix — 리뷰·플랜의 수정 항목을 검토하고 적용한다 (요청자 측)

> 마스터가 생성해 배달한다. **손으로 고치지 말 것** — 다음 배달에 덮인다.

## 0. [중요] 먼저 — 이 스킬인지 가른다

| 발화 | 뜻 | 갈 곳 |
|---|---|---|
| `R12 검토해볼까` · `P3 수정해볼까` · `리뷰 목록` · `플랜 목록` | 자동 리뷰·주간 플랜의 **수정 항목** | [중요] **이 스킬** |
| `#N 리뷰` · `머지 검토` · `검수 요청 받았어` | 분산 작업을 `main` 에 반영할지 | `ax-review` |
| `라운드 종결` · `전진시켜` | 작업 브랜치 전진 | `ax-advance` |

[주의] **`R`/`P` 가 붙은 번호만 이 스킬이다.** `#209` 같은 번호는 레드마인 이슈 번호다.
원전은 *"리뷰 #4"* 로 레드마인 번호를 불렀으니 섞이지 않게 번호를 한 번 확인한다.

**원전 원칙 그대로다: 리뷰·플랜은 제안이지 지시가 아니다 — 수용 여부는 사람이 정한다.**
자동으로 도는 것은 모으기(마스터)와 사실 대조(파이썬)뿐이고, 「합당한가」와 「고칠까」는 사람이 답한다.

## 1. 흐름

    ① 번호 고르기   list_fixes → 표로 보여주고 사용자가 고른다 (스스로 고르지 않는다)
    ② 내려받기      fix_flow.py fetch R12   → .ax/fixes/R12/doc.md · doc.json
    ③ 대조          fix_flow.py check R12   → .ax/fixes/R12/check.md  (지금 origin/main 기준 사실)
    ④ 판정·질의     항목마다 「합당 / 해당 없음 / 의도된 동작 의심」 + 근거 → 사용자에게 묻는다   ← 사람
    ⑤ 적용          fix_flow.py worktree R12 → 수락분만 서브 에이전트가 고친다
                    → fix_flow.py diff R12 로 확인 → 커밋 여부 묻는다 ← 사람 → fix_flow.py commit
    ⑥ 기록          update_fix_status (항목마다) · 플랜이면 레드마인 노트

도구:

    MCP      mcp__ax-client__list_fixes · get_fix · update_fix_status
    스크립트  <프로젝트 Python> .ax/lib/axmaster/clientside/fix_flow.py list|fetch|check|worktree|diff|commit|status

[중요] **맨 `py`나 `python`을 쓰지 않는다.** 먼저 `.ax/config.json`의
`backends.python`을 읽고 그 **절대경로**를 실행한다. 같은 값이 `.mcp.json`의
`mcpServers.ax-client.command`에도 있다. 둘이 다르거나 값이 없으면 초기화가 어긋난 것이므로
실패를 보고하고 멈춘다. Windows Codex 샌드박스에서는 사용자 세션의 `py`가 Python을
열거해도 에이전트 셸에서는 `No installed Python found!`가 날 수 있다(2026-09-20 실측).
[중요] 스크립트는 **체크아웃 루트(cwd)** 에서 부른다 — `.ax/config.json`·`.ax/token` 을 거기서 읽는다.

## 2. 단계

### ① 번호 고르기

번호 없이 *"고칠 리뷰 있어?"* 로 오면 `list_fixes` 를 부르고 **미결 항목이 있는 것**을 표로 보여 준다
(번호 · 날짜 · 작성자 · 항목 수 · high/mid/low · 결정 상태). 무엇부터 할지는 사용자가 고른다.
웹에서도 같은 목록이 보인다: `http://192.168.0.57:8103/reviews`.

### ② 내려받기

    "<backends.python>" .ax/lib/axmaster/clientside/fix_flow.py fetch R12

`[fix] [실패]` 가 찍히면 사유를 그대로 보고하고 멈춘다(`not_mounted` 면 마스터의 마운트가 이 체크아웃의
프로젝트와 다른 것이다 — 우회하지 않는다).

### ③ 대조 — 사실만

    "<backends.python>" .ax/lib/axmaster/clientside/fix_flow.py check R12

`check.md` 를 **Read 로** 읽는다(콘솔은 요지만 찍힌다). 단서의 뜻:

| 단서 | 뜻 | 다음 |
|---|---|---|
| 리뷰 뒤 안 바뀌었다 | 지적이 그대로일 가능성이 크다 | 코드를 읽어 확인 |
| 줄이 남아 있다 | 파일은 바뀌었지만 그 줄은 있다 | 지금 줄 번호로 읽기 |
| 줄이 사라졌다 | 이미 고쳐졌을 수 있다 | 읽고 「해당 없음」 후보 |
| 파일이 없다 | 옮겨졌거나 지워졌다 | 「해당 없음」 후보 |

[주의] **단서는 판정이 아니다.** 반드시 지금 코드를 읽는다 — `git show origin/main:<파일>` 또는 ⑤의
worktree. 이 체크아웃의 작업 트리는 사람이 고치던 중일 수 있으니 기준으로 삼지 않는다.

### ④ 판정과 질의 — [중요] 여기서 멈춘다

항목마다 한 줄 근거로 판정해 **표로** 보여 준다:

    | 항목 | 판정 | 근거 (지금 코드 기준) | 권장 |
    | R12-1 | 합당 | 47행 Get() 결과를 IsValid 없이 역참조 — 그대로 남아 있다 | 적용 |
    | R12-2 | 해당 없음 | 3f2a1c 에서 가드가 이미 들어갔다 | stale |
    | R12-3 | 의도 의심 | 호출부가 늘 유효한 값을 넘긴다 — 사람이 판단 | 보류 |

그리고 묻는다: **"적용할 항목 · 기각할 항목 · 보류할 항목을 골라 주세요."**
[중요] 답을 받기 전에는 **아무것도 고치지 않고 아무것도 기록하지 않는다.**
[주의] 짧은 수긍(`응`)은 방금 한 질문이 무엇이었는지 확인한 뒤에만 승인으로 읽는다.

「의도된 기능」이라는 답이면 그 이유를 받아 `dismissed` 로 기록한다. 원전의 `review-consultant`
처럼 **컨텍스트 MD 에 `[리뷰]` 코멘트를 남길지는 따로 묻는다** — 남기면 다음 주간 플랜이 그 지적을 뺀다.

### ⑤ 적용 — 수락한 항목만

    "<backends.python>" .ax/lib/axmaster/clientside/fix_flow.py worktree R12

체크아웃 **옆에** `ax-fix-R12` worktree 와 `fix/R12` 브랜치가 생긴다(있으면 재사용 · 리셋하지 않는다).
서브 에이전트(`code-writer`)에게 넘기는 것:

- worktree 경로 — **그 안의 파일만** 고친다
- 수락한 항목의 파일·라인·지적·권장 수정과 ④의 근거
- 먼저 RAG: `search_context`(대상 클래스·도메인) · `find_recipes` · `get_anti_patterns` · `find_history`
- 금지(원전): 클래스·함수·UPROPERTY 이름 바꾸기 · 상속 구조 변경 · 모듈 간 이동 · 수락하지 않은 항목 손대기

서브 에이전트가 끝나면 **결과를 믿지 말고 확인한다**:

    "<backends.python>" .ax/lib/axmaster/clientside/fix_flow.py diff R12

`.ax/fixes/R12/diff.patch` 를 Read 로 읽어 각 항목이 실제로 해소됐는지 본다(파일 수·증감은 `flow.log`
에 남는다). 그 요지를 사용자에게 보여 주고 **커밋할지 묻는다.** UE5 빌드로 확인할지도 묻는다
(이 PC 에서 돌릴 수 있지만 사람에게 묻지 않고 돌리지 않는다).

승인되면 **스크립트로** 커밋한다 — `git commit` 을 직접 치지 않는다(해시·항목이 로그에 남아야 한다):

    "<backends.python>" .ax/lib/axmaster/clientside/fix_flow.py commit R12 --items R12-1,R12-4 --message "<한 줄 요지>"

`fix/R12` 가 아니면 거절하고, 메시지는 `fix(R12-1,R12-4): …` 가 된다. 출력의 `commit` 을 ⑥에 쓴다.
[중요] **push 하지 않고 `main` 에 머지하지 않는다** — 그건 사람이 한다.

### ⑥ 기록

항목마다 결정을 되돌린다(MCP `update_fix_status` 또는 스크립트 `status`):

    applied   --branch fix/R12 --commit <sha>   커밋까지 한 항목
    dismissed --note "<이유>"                    사용자가 기각
    stale     --note "<근거>"                    지금 main 에 해당 없음 (사용자 동의 뒤)
    failed    --note "<무엇이 막혔나>"            고치다 막힘

플랜(`P3`)은 `applied`/`dismissed` 가 플랜 MD 의 status 를 `acted`/`dismissed` 로 맞춘다.
플랜에 레드마인 번호가 있으면 `redmine_note` 로 결과(브랜치·커밋·항목)를 노트로 남긴다 —
**상태 변경은 사용자에게 물은 뒤에만**, 원전처럼 「해결」까지다.

## 3. 멈추는 자리

- 명령·스크립트가 실패하면(rc≠0 · `[fix] [실패]` · 거절) **사유와 갈래를 보고하고 멈춘다.** 코드·설정을 고쳐 우회하지 않는다.
- 사람의 체크아웃에서 브랜치를 바꾸지 않는다 — worktree 만 쓴다.
- 한 번에 한 번호만 다룬다. 다른 번호의 항목을 섞지 않는다.
- 진행 기록은 `.ax/fixes/<번호>/flow.log` 에 쌓인다 — 보고할 때는 요지만 말한다.
