# 175 — #919 웹 작업 리포트 뷰어

2026-11-13 · 지휘 Codex → Claude(한도 소진 교대) · 로컬 Codex 서브에이전트 구현·지휘자 검토.

## 사용자 승인과 작업 위치

사용자 「919번 진행하자 작업 마무리하고 리포트는 계속 남기고 있는거지?」에 기존 리포트173·174와 Redmine 마감 결과 기록을 안내했다.
제안 플랜: reports/*.md·reports/research/*.md 목록과 메타, 안전한 상세 마크다운·Redmine/커밋 링크, 회귀·공식 통합·운영 확인 후 리포트·마감·배달.
사용자 「서브 에이전트로 작업 진행해줘」로 플랜 및 로컬 Codex 서브에이전트 방식 승인.
#919를 아이디어에서 마일스톤8 개선·확장으로 이동했다. Hermes 자동 학습·주간 자동 분석·자동 일감 생성은 이번 플랜에 포함하지 않았다.

plan_start_tool(919)은 `verdict=plan_needed, ok=false`였다. RAG·현재 소스를 대조하고 사용자 합의 뒤 T1/T2를 등록했다.

issue_start_tool(919) 핵심 원문:

```json
{"ok":true,"issue_id":919,"branch":"issue/919","repo":"/home/sim/ax-cluster/.ax-issues/919","checkout":"/home/sim/ax-cluster","already":false,"start_rev":"bb714072b856ba682233a8bb52e04cceb5d0271c","lock":"acquired","author":{"client":"codex-mcp-client","family":"codex","authors":["codex"]}}
```

시작 응답에 done·why는 없다. 편집·검사·커밋은 응답 repo, 운영 checkout은 main을 유지했다.
RAG request_id=1362d6bc874d4917a1412d18fbdc697c, search_id=4f00867ceebc46e38b21d76e99d27cf2.
운영 트윈 AXCluster/context/master/webui/{fixes_page,app,nav}.md 본문을 읽고 실제 소비자와 대조했다.

## 기존 자산 대조와 구현 경계

- nav.ITEMS가 공용 메뉴 정본, app.PREFIXES가 상위 라우팅·공개 경로의 공통 정본이다. 단일 페이지 링크만 추가해서 다른 화면에서 진입할 수 없는 상태를 만들지 않는다.
- fixes_page.render_markdown은 기존 제목·표·목록과 HTML escape를 제공하지만 코드 펜스와 Markdown 링크가 충분하지 않아 리포트 상세의 보완이 필요하다.
- test_usage_nav는 메뉴8개를 고정 검사하므로 신규 메뉴를 포함한 기대값으로 조정해야 한다. 기존 링크 보존은 유지한다.
- 원격 origin의 SSH 포트를 웹 포트로 추정하지 않았다. machines/sim-desktop.d/services.md의 Gitea3000과 sim-desktop.md의 정본 origin을 확인했다. 고정 조회 스크립트 `/tmp/ax-919-gitea-probe.sh`: http://192.168.0.57:3000/ → HTTP200, effective URL 동일. /etc/gitea/app.ini는 존재·0600 nobody인 것을 목록 조회로 확인했으나 내용은 읽지 않았다.
- 서브에이전트 /root/report_viewer는 지정 worktree·허용 파일에서 구현하며 운영 데이터·커밋·push·일감 상태·서비스를 조작하지 않는다. 에이전트에도 경로 목록 조회와 본문 읽기를 별도 도구 호출로 수행하도록 지시했다.

## 검증과 결과

### 지휘 교대 (Codex → Claude)

Codex는 서브에이전트 구현 회수 직후 5시간 한도로 중단했다(미커밋). 사용자 「919 이어서 진행해, rebase도 승인」으로 Claude가 인수했다.

- `issue_start_tool(919)`: `already=true`, 작성 계열 누적 `["codex","claude"]`.
- 인수인계 기록과 달랐던 점 둘: ① 인수인계 커밋 `318519d`는 이미 push돼 있었다(로컬 `main` = `origin/main`). ② 그래서 `origin/main`이 `issue/919`의 조상이 아니었다 → 승인받은 `git rebase --autostash main` rc0. 브랜치에 커밋이 없어 미커밋 변경만 그대로 옮겨졌다(수정 4·신규 3 동일).
- Codex가 적은 「32건 OK」는 믿지 않고 rebase 뒤 다시 돌렸다.

### 구현 (서브에이전트 산출물, Claude가 전체 diff 검토)

| 파일 | 내용 |
|---|---|
| `master/webui/reports_page.py` (신규) | `reports/*.md`·`reports/research/*.md` 목록(최신 커밋순, Git 이력 없는 문서는 뒤)·검색 `q`·분류 `kind=work\|research`·상세 마크다운(코드 펜스·표·목록·인용)·`#N` Redmine 링크·저장소에 실재하는 해시만 Gitea 커밋 링크 |
| `master/webui/app.py` | `PREFIXES`에 `/reports`, GET 전용 라우트(그 밖 405) |
| `master/webui/nav.py` | 공용 메뉴 `ITEMS`에 「작업 리포트」 |
| `master/test_reports_page.py` (신규 15건) · `master/test_usage_nav.py` · `tests/integration/checks.json` | 신규 검사와 메뉴 9개 기대값, 공식 목록 등록 |

검토에서 확인한 것: 본문·제목·작성 표기·검색어는 전부 `html.escape`를 거친다. 링크 `href`는 `http(s)` 절대 주소나 허용된 리포트 상대 경로로만 만들어진다. 파일 경로는 단일 파일명 또는 `research/파일명`의 `.md`만 받고, 역슬래시·`%`(이중 인코딩)·숨김 파일·심볼릭 링크·`reports/` 밖 해석은 400이다. 예외 문자열은 화면에 내보내지 않는다(고정 문구 400/503).

### 검사 (rebase 뒤, worktree에서 운영 venv로 실행)

| 검사 | 결과 |
|---|---|
| `test_reports_page.py` | 15건 OK |
| `test_usage_nav.py` · `test_webui_side_nav.py` · `test_integration_coverage.py` · `test_rag_routes.py` | 2 · 8 · 2 · 5건 OK |
| 정적 `pystatic.run_static`(base `318519d`, 변경 5파일) | pyflakes 차단0·노트0, import 3모듈 차단0, mypy call-arg 차단0·노트0 |
| 공식 통합 `tests/integration` | 195건 202.579초 OK |
| `git diff --check` | rc0 |

첫 실행은 worktree에 `.venv`가 없어 rc127이었다(짐작한 경로). 운영 저장소의 `.venv/bin/python`으로 다시 돌린 값이 위 표다.

### 한계

- 8103의 웹 화면은 로그인이 없다. 리포트 본문(사용자 발화 인용·절대 경로·LAN 주소)이 LAN 안에서 그대로 읽힌다. `api_history`가 같은 포트에서 인용·절대 경로를 가린 것과 다른 선택이며, 방어는 ufw LAN 전용 한 겹이다.
- 목록 요청마다 리포트 전체를 읽고 `git log`를 두 번 부른다(캐시 없음). 응답 시간은 재지 않았다.
- 재기동 뒤 실제 HTTP `/reports` 확인은 마감 뒤 `issue_wrapup` 단계에서 한다.

Codex 세션 파일: ~/.codex/sessions/2026/11/12/rollout-2026-11-12T23-17-23-01a1d01e-d294-7680-8cf8-661b8454f17f.jsonl.

최종 결과는 Redmine 마감 노트.
