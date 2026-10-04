"""좌측 목록 — **화면 하나에 한 벌** (사용자 요청 2026-09-19: *"좌측에 목록을 만들고"*).

## [중요] 여기가 링크의 정본이다

종전에는 화면마다 자기 `<div class="nav">` 를 따로 들고 있었다. 그 결과 **입구가 화면마다
달랐고**, 리포트 68 §7 이 그 값을 치렀다 — `/reviews` 는 200 이었는데 들어갈 링크가
`/cluster` 상단 한 줄뿐이라 사용자가 *"웹 UX에 리뷰나 개선플랜 목록이 안보이는데?"* 라고
물었다. 목록을 한 곳에 두면 **새 화면을 더해도 모든 화면에서 보인다.**

[주의] 여기에 링크를 더할 때 **그 경로가 실제로 서는지 확인한다.** 죽은 링크는 없는 화면보다
나쁘다 — 사람이 고장으로 읽는다.
"""
from __future__ import annotations

import html

# (경로, 이름, 한 줄 설명). 순서 = 화면에 보이는 순서.
# 🔴 위 둘이 「무엇인가」, 아래 셋이 「지금 어떤가 · 무엇이 있나」다.
ITEMS = [
    ("/onboarding", "분산 작업", "일감을 쪼개 워커에게 맡기는 흐름"),
    ("/commit-flow", "커밋 흐름", "손 커밋 → 로컬 초고 · Antigravity 리뷰"),
    ("/cluster", "클러스터 상태", "기계 · 서비스 · 지휘 상태"),
    ("/reviews", "리뷰 · 플랜", "번호가 붙은 수정 항목"),
    ("/ontology", "온톨로지 뷰어", "도메인 · 클래스 · 액션"),
    ("/", "컨텍스트 검색", "문서를 찾는다"),
]

SIDE_CSS = """
.shell{display:grid;grid-template-columns:230px 1fr;gap:1.6rem;align-items:start}
.side{position:sticky;top:1rem;border:1px solid var(--line);border-radius:12px;
 background:var(--card);padding:.8rem .7rem}
.side h2{margin:0 0 .5rem;padding:0 .5rem;font-size:.72rem;letter-spacing:.06em;
 text-transform:uppercase;color:var(--dim);border:0}
.side a{display:block;border-radius:8px;padding:.45rem .55rem;margin:.12rem 0;
 text-decoration:none;color:var(--fg);font-size:.88rem;line-height:1.25}
.side a:hover{background:rgba(255,255,255,.04)}
.side a.on{background:rgba(88,166,255,.12);color:var(--accent);font-weight:650}
.side a small{display:block;color:var(--dim);font-size:.72rem;font-weight:400;margin-top:.1rem}
.shell>main{min-width:0}
/* 🔴 좁은 화면에서는 목록을 위로 접는다 — 230px 를 고정하면 본문이 못 읽힌다 */
@media (max-width:760px){
  .shell{grid-template-columns:1fr;gap:1rem}
  .side{position:static}
  .side a small{display:none}
}
"""


def nav_html(current: str = "") -> str:
    """좌측 목록. `current` 는 지금 화면의 경로 — 그 항목만 `on` 이 붙는다."""
    # [DOC] 이 조각은 이 파일과 master/test_usage_nav.py만 변경한다. 기존 선언·여섯 메뉴 유지.
    # [DOC] ITEMS에 ('/usage','LLM 사용량','기간별 작업 · 토큰')을 하나 추가한다.
    # [PSEUDO] 공용 메뉴에 /usage 링크를 연결하고 유일성·활성 표시·기존 메뉴 유지 검사한다.
    e = html.escape
    out = ['<nav class="side"><h2>화면</h2>']
    for path, name, desc in ITEMS:
        on = " on" if path == current else ""
        out.append(f'<a class="item{on}" href="{e(path)}">{e(name)}'
                   f'<small>{e(desc)}</small></a>')
    out.append("</nav>")
    return "".join(out)
