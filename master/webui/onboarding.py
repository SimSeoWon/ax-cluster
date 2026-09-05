"""온보딩 화면 — **에이전트가 무엇이고 누가 무엇을 하는가** (`/onboarding`).

사용자 요청 2026-09-05: *"웹UX에 에이전트를 설명할 수 있는 온보딩 페이지가 추가되어야해!"*

## 이 화면이 답하는 것

처음 보는 사람이 `http://192.168.0.57:8103` 을 열었을 때 **여기서 무슨 일이 벌어지는지**를
한 화면에서 알게 한다. 상태(`/cluster`)는 *"지금 어떤가"* 를 말하고, 여기는 *"무엇인가"* 를
말한다 — 둘을 섞지 않는다.

## [중요] 사실은 코드에서 가져온다 — 여기서 지어내지 않는다

기계 목록·역할·레인 순서 같은 값은 **한 곳에 있어야 한다**. 이 모듈이 자기 사실을 따로 적으면
파이프라인이 바뀔 때마다 화면만 낡는다(그 부류를 이 저장소가 이미 여러 번 치렀다). 그래서
`status` 의 팔레트를 그대로 쓰고, 파이프라인 7단계는 **정본 문구**를 인용한다.

[주의] **토큰·경로·본문은 싣지 않는다.** 이 포트의 `/api/v1` 은 무인증 공개이고 이 화면도
같은 층이다 — 개념과 역할까지만 적는다(민감한 본문은 8101 의 토큰 잠긴 자리에 있다).
"""
from __future__ import annotations

import html

from ..status import _CSS

_EXTRA = """
.nav{display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0 1.4rem}
.nav a{border:1px solid var(--line);border-radius:999px;padding:.35rem .85rem;
 font-size:.82rem;text-decoration:none;background:var(--card);color:var(--fg)}
.nav a.on{border-color:var(--accent);color:var(--accent)}
.lede{font-size:1.02rem;max-width:62ch;color:var(--fg)}
.steps{counter-reset:s;display:grid;gap:.5rem;margin:.6rem 0 0}
.step{display:grid;grid-template-columns:2.1rem 1fr;gap:.7rem;border:1px solid var(--line);
 border-radius:10px;background:var(--card);padding:.7rem .85rem}
.step .n{font-variant-numeric:tabular-nums;font-weight:650;color:var(--accent);
 font-size:1.05rem;text-align:center}
.step b{font-weight:650}
.step .who{color:var(--dim);font-size:.78rem;font-family:ui-monospace,Menlo,monospace}
.step p{margin:.25rem 0 0;font-size:.87rem;color:var(--fg)}
.step.human{border-left:4px solid var(--warning)}
.cols{display:grid;gap:.7rem;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.card{border:1px solid var(--line);border-radius:10px;background:var(--card);padding:.85rem .9rem}
.card h3{margin:0 0 .35rem;font-size:.92rem}
.card .role{font-family:ui-monospace,Menlo,monospace;font-size:.78rem;color:var(--dim)}
.card ul{margin:.45rem 0 0;padding-left:1.05rem;font-size:.85rem}
.card li{margin:.15rem 0}
.no{color:var(--dim)}
.callrow{display:grid;grid-template-columns:auto 1fr;gap:.2rem .8rem;font-size:.87rem;
 align-items:baseline}
.callrow code{color:var(--accent)}
.note{border:1px solid var(--line);border-left:4px solid var(--accent);background:var(--card);
 border-radius:8px;padding:.7rem .9rem;margin:.9rem 0;font-size:.88rem}
.note.warn{border-left-color:var(--warning)}
"""

# 🔴 정본 7단계 — 사용자 확정 2026-09-02 (⑺ 은 2026-09-05 라이브 완주).
#    [중요] 여기 문구를 **고쳐 쓰지 않는다.** 화면이 정본을 재해석하기 시작하면 다음 사람은
#    코드와 화면 중 어느 쪽이 맞는지 알 수 없다.
_STEPS = [
    ("1", "요청", ".33 요청자",
     "사용자가 작업 PC에서 <code>claude</code> 를 켜고 요청한다 — 마스터에 컨텍스트 문서를 청한다."),
    ("2", "골조를 만든다", ".33 요청자",
     "모든 클래스의 동작을 계획하고 <b>골조</b>를 만든다 — 프로퍼티·메서드의 정의만 세우고, "
     "내용물은 주석 작업지시서(<code>[DOC]</code>·<code>[PSEUDO]</code>)로 남긴다."),
    ("3", "작업 브랜치에 올린다", ".33 요청자",
     "골조를 <code>task/&lt;work&gt;/base</code> 에 커밋하고 마스터에 <b>등록</b>한다. "
     "그 push 와 등록이 <b>둘 다</b> 파견 트리거다."),
    ("4", "조각으로 쪼갠다", ".57 마스터",
     "골조 파일을 기준으로 서브태스크를 만들고, 작업 브랜치에서 갈라진 <b>서브 브랜치</b>를 "
     "조각마다 세워 워커에게 넘긴다 — <b>병렬이 기본</b>이다."),
    ("5", "본문을 채운다", ".2 · .43 워커",
     "워커가 상용·로컬 LLM 레인(agy → qwen2.5-coder)으로 주석을 코드로 바꾸고 "
     "<b>자기 서브 브랜치에 커밋</b>한다. 끝나면 <code>main</code> 으로 돌아간다 — "
     "워커는 임시 저장소이고 남기는 것이 없다."),
    ("6", "끝났다고 알린다", ".57 마스터",
     "조각이 전부 끝나면 요청자에게 전달한다 — 레드마인 이슈에 노트가 쌓이고 "
     "<code>.33</code> 세션 훅이 매 턴 고지한다."),
    ("7", "머지하고 전진시킨다", ".33 요청자 · 사람",
     "서브 브랜치를 전부 작업 브랜치에 머지해 <b>한 번에</b> 검사한다(조각별 검증이 못 잡는 "
     "자리다). 그리고 「버그냐 구조 수정이냐」를 사람에게 묻고 그 브랜치를 한 칸 전진시킨다."),
]

_MACHINES = [
    ("요청자", ".33 · 사용자의 작업 PC", "requester",
     ["언리얼 작업이 <b>들어오는 창구</b> — 요청·골조·검수가 여기서 난다",
      "UE5 가 있어 통합 빌드를 돌린다 (⑺ 전진)",
      "<span class='no'>파견받지 않는다</span> — 워커가 아니다"]),
    ("마스터", ".57 · 이 서버", "master",
     ["큐·브로커·색인/온톨로지·파견을 돌린다",
      "조각을 쪼개 서브 브랜치를 세우고 워커에 넘긴다",
      "<span class='no'>골조를 만들지 않는다</span> · "
      "<span class='no'>소스 저장소에 push 하지 않는다</span>"]),
    ("워커", ".2 (RTX 3060) · .43 (BC-250)", "worker",
     ["큐에서 조각을 집어 본문을 코드로 바꾼다",
      "자기 서브 브랜치에 커밋하고 다음 작업을 청한다",
      "<span class='no'>임시 저장소다</span> — 커밋 뒤 브랜치·캐시를 지운다"]),
]

_GATES = [
    ("층 1", "정적 검사", "골조 계약 위반·마커 잔재를 잡는다. 통과 못 하면 커밋이 막힌다"),
    ("층 2", "grounding 검토", "선언부·관계를 프롬프트에 실어 <b>없는 것을 지어낸 자리</b>를 잡는다"),
    ("층 3", "조각별 UE5 빌드", "실제로 컴파일되는지 — 이 판정을 무인으로 낼 수 있는 것은 <code>.2</code> 뿐이다"),
    ("통합", "작업 브랜치 빌드", "⑺ 에서 전부 머지한 뒤 한 번. <b>조각별로는 안 나오는 결함</b>이 여기서 난다"),
]


def _steps_html() -> str:
    out = []
    for n, title, who, body in _STEPS:
        human = " human" if n == "7" else ""
        out.append(
            f'<div class="step{human}"><div class="n">{n}</div><div>'
            f'<b>{html.escape(title)}</b> <span class="who">{html.escape(who)}</span>'
            f'<p>{body}</p></div></div>')
    return '<div class="steps">' + "".join(out) + "</div>"


def _machines_html() -> str:
    out = []
    for name, where, role, items in _MACHINES:
        lis = "".join(f"<li>{x}</li>" for x in items)
        out.append(f'<div class="card"><h3>{html.escape(name)}</h3>'
                   f'<div class="role">{html.escape(where)} · role={html.escape(role)}</div>'
                   f"<ul>{lis}</ul></div>")
    return '<div class="cols">' + "".join(out) + "</div>"


def _gates_html() -> str:
    rows = "".join(f"<tr><td><b>{html.escape(a)}</b></td><td>{html.escape(b)}</td>"
                   f"<td>{c}</td></tr>" for a, b, c in _GATES)
    return ("<table><tr><th>층</th><th>무엇</th><th>왜 있나</th></tr>"
            + rows + "</table>")


def render() -> str:
    """자립형 HTML — 외부 자원 0 (상태 화면과 같은 규약)."""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AX 클러스터 — 온보딩</title><style>{_CSS}{_EXTRA}</style></head><body>
<h1>AX 클러스터 — 여기서 무슨 일이 벌어지나</h1>
<div class="sub">에이전트 역할 · 파이프라인 7단계 · 사람이 개입하는 자리</div>
<div class="nav">
  <a class="on" href="/onboarding">온보딩</a>
  <a href="/cluster">클러스터 상태 →</a>
  <a href="/ontology">온톨로지 뷰어 →</a>
  <a href="/">컨텍스트 검색 →</a>
</div>

<p class="lede">언리얼 프로젝트 한 덩어리의 작업을 <b>클래스 단위 조각</b>으로 쪼개
여러 기계의 에이전트에게 나눠 맡기고, 결과를 한 브랜치에 모아 <b>사람이 판단</b>하는
파이프라인이다. 자동화된 것은 <b>나르기와 채우기</b>이고, <b>무엇을 만들지</b>와
<b>이것으로 갈지</b>는 사람이 정한다.</p>

<div class="note"><b>세 종류의 에이전트가 있고, 역할이 겹치지 않는다.</b>
요청자는 <b>만들 것을 정하고 검수</b>하고, 마스터는 <b>쪼개서 나르고</b>, 워커는
<b>채운다</b>. 이 경계가 흐려지면 같은 일을 두 곳이 하거나 아무도 안 한다.</div>

<h2>에이전트 — 누가 무엇을 하나</h2>
{_machines_html()}

<h2>파이프라인 — 요청 하나가 도는 길</h2>
{_steps_html()}

<div class="note warn"><b>사람이 개입하는 자리는 둘이다.</b>
⑺ <b>전진</b>에서 「버그냐 구조 수정이냐」를 묻고, 마지막 <b>마감</b>에서 <code>main</code> 에
넣을지 정한다. 나머지는 승인 없이 돈다 — 대신 <b>게이트가 판정</b>한다.</div>

<h2>한 분산 작업은 여러 라운드를 돈다</h2>
<p class="lede">⑺ 에서 작업 브랜치를 한 칸 전진시킨 뒤 <b>더 고칠 것이 있으면 같은 작업에
조각을 더한다</b>. 그것이 라운드 2·3이고, 서브 브랜치 이름에 라운드 번호가 들어가
(<code>task/&lt;work&gt;/r2/&lt;조각&gt;</code>) 지난 라운드와 섞이지 않는다.
작업이 끝나는 것은 사람이 「더 없다」라고 할 때뿐이다.</p>
<div class="card" style="margin-top:.7rem">
  <div class="callrow">
    <code>등록</code><span>새 분산 작업을 연다 — <b>라운드 1</b></span>
    <code>개선요청</code><span>이미 있는 작업의 다음 라운드 — <b>라운드 = 현재 + 1</b>
      (값이 어긋나면 거절한다)</span>
    <code>마감</code><span><code>main</code> 머지 · 브랜치 정리 · 레드마인 이슈를 「완료」로</span>
  </div>
</div>

<h2>판정은 게이트가 한다 — 모델이 아니라</h2>
<p class="lede">결정적 검사(빌드·정적 분석)가 LLM 판단보다 위다. 모델은 <b>본문을 쓰고</b>,
통과 여부는 게이트가 말한다.</p>
{_gates_html()}

<h2>시작하려면</h2>
<div class="cols">
  <div class="card"><h3>작업을 요청하고 싶다</h3>
    <ul><li>작업 PC(<code>.33</code>)의 프로젝트 폴더에서 <code>claude</code> 를 켠다</li>
        <li>무엇을 만들지 한국어로 말한다 — 골조·등록은 스킬이 안내한다</li>
        <li>끝나면 세션이 <b>라운드 종결 대기</b>를 고지한다</li></ul></div>
  <div class="card"><h3>지금 상태가 궁금하다</h3>
    <ul><li><a href="/cluster">클러스터 상태</a> — 머신·서비스·큐에 열린 태스크</li>
        <li><a href="/ontology">온톨로지 뷰어</a> — 도메인·클래스·불변식</li>
        <li>일감과 진행은 레드마인(<code>:8080</code>)에 쌓인다</li></ul></div>
</div>

<div class="foot">이 화면은 <b>무엇인가</b>를 설명한다 — <b>지금 어떤가</b>는
<a href="/cluster">클러스터 상태</a>에 있다. 사실이 바뀌면 이 페이지가 아니라
파이프라인 정본(<code>~/CLAUDE.md</code> 7단계)이 먼저 바뀐다.</div>
</body></html>"""


def page() -> bytes:
    return render().encode("utf-8")
