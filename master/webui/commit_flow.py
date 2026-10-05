"""커밋 흐름 화면 — **손으로 커밋한 코드가 어떻게 문서·리뷰가 되나** (`/commit-flow`).

사용자 요청 2026-09-19: *"사용자가 .33 메인 컴퓨터에서 작업하고 코드를 커밋하면 1차로
큐에서 .2번이나 BC250을 활용해 로컬LLM으로 컨텍스트 문서를 생성하고, 리뷰 큐에서 역시
동일하게 리뷰 초안을 생성하는걸 … 다이어그램으로"*.

## 이 화면이 `/onboarding` 과 다른 점

    /onboarding    **분산 작업** — 사람이 일감을 나눠 워커에게 맡기는 흐름 (7단계)
    /commit-flow   **손 커밋** — 사람이 그냥 커밋했을 때 자동으로 도는 흐름

둘은 **겹치지 않는다.** 분산 작업 커밋은 3층 게이트를 지나지만, `.33` 에서 손으로 한 커밋은
**어느 게이트도 안 지난다** — 이 화면의 흐름이 그 구멍을 덮는 장치다(`review_gen` 머리말).

## [중요] 사실은 코드에서 가져온다 — 여기서 지어내지 않는다

    SYNTH_MODEL         context_synth/synth.py        컨텍스트 합성 모델
    SYNTH_CHAIN         context_synth/synth.py        형식 거부 시 대체 사슬 (`#727`)
    DRAFT_MODEL         context_synth/review_runner.py 초고 모델
    broker.choose()     broker/routing.py             어느 노드가 받는지의 규칙

🔴 [주의] **노드를 「BC250 전용」으로 그리지 않는다.** 브로커는 ①상주 → ②`prefer` →
③폴백 순으로 고르고(`routing.py:45`), `.2`·`.43` **둘 다 `gemma4:e4b` 를 갖고 있다**(실측
2026-09-19). 평소엔 `.43` 이 상주라 거기로 가고, `.43` 이 죽으면 `.2` 가 받는다. 그림이
그걸 말하지 않으면 다음 사람은 「BC250 전용」으로 읽는다.

[주의] **토큰·경로·본문은 싣지 않는다** — 이 포트의 `/api/v1` 은 무인증 공개이고 이 화면도
같은 층이다(`onboarding` 과 같은 규약).
"""
from __future__ import annotations

import html

from ..status import _CSS
from .onboarding import _EXTRA as _BASE_EXTRA
from .nav import nav_html, SIDE_CSS

# 🔴 사실은 코드에서 읽는다 — 이 화면이 자기 값을 따로 적으면 모델이 바뀔 때 화면만 낡는다.
from ..context_synth.synth import SYNTH_CHAIN, SYNTH_MODEL
from ..context_synth.review_runner import DRAFT_MODEL

_EXTRA = _BASE_EXTRA + SIDE_CSS + """
.badge{display:inline-block;border:1px solid var(--line);border-radius:999px;
 padding:.1rem .5rem;font-size:.72rem;font-family:ui-monospace,Menlo,monospace;color:var(--dim)}
.badge.local{border-color:#3fb950;color:#3fb950}
.badge.human{border-color:var(--warning);color:var(--warning)}
"""

# 사슬 표기 — `e4b → agy → codex → 12b`. 상용 레인은 화면에서 이름을 알아보게 바꿔 적는다.
_LANE_LABEL = {"agy": "Antigravity", "codex": "Codex"}
_CHAIN_TEXT = " → ".join(_LANE_LABEL.get(m, m) for m in SYNTH_CHAIN)

# ── 다이어그램 값 ───────────────────────────────────────────────────────────
#
# [중요] **세로 · 3열 스윔레인** — `/onboarding` 의 flow_svg 와 같은 규약이다.
#   레인을 가로로 눕히면 화면 밖으로 나가고, 세로 스크롤은 페이지가 원래 하는 일이다.
_LANES = [
    ("`.33` 요청자", "사람의 작업 PC"),
    ("`.57` 마스터", "큐 · 색인 · 게시판"),
    ("`.43` · `.2` 워커", "로컬 LLM (무료)"),
]

# (행, 레인, 제목, 부제, 사람인가)
_NODES = [
    (0, 0, "① 커밋 · push", "손으로 고친 코드 — **어느 게이트도 안 지난다**", True),
    (1, 1, "② 색인기가 집는다", "커밋마다 **첫 부모 기준** 변경 파일 · 깨끗한 머지는 건너뜀", False),
    (2, 2, "③ 컨텍스트 문서 합성", f"클래스별 `.md` — 로컬 `{SYNTH_MODEL}` · 형식 거부 시 대체 사슬", False),
    (3, 1, "④ 리뷰 큐에 등재", "커밋 하나 = 항목 하나 · 머지는 충돌 해소분만 · 색인은 **기다리지 않는다**", False),
    (4, 2, "⑤ 로컬 1차 초고", f"형식 자유 — `{DRAFT_MODEL}` · 중간 산출물", False),
    (5, 1, "⑥ Antigravity 2차", "원본 diff · 선언부와 대조해 정형 리뷰로 퇴고", False),
    (6, 1, "⑦ 최종 리뷰 · R번호", "표가 있는 리뷰 게시 · 성공한 초고 제거", False),
    (7, 0, "⑧ 사람이 검토", "*\"R33 검토해볼까?\"* — 지금 main에 합당한가", True),
    (8, 0, "⑨ 판정 · 적용", "수정 / 이미 반영 / 오탐이면 기각", True),
]

_EDGES = [
    "git SSH push → Gitea",
    "브로커 8102 (모델로 라우팅)",
    "마스터 내부 (색인 경로)",
    "마스터 내부 (큐 파일)",
    "브로커 8102",
    "`.57` Antigravity CLI",
    "파일 → `fix_index` 번호",
    "HTTP 8101 · `ax-fix`",
]

_LANE_X0, _LANE_W, _LANE_GAP = 18, 300, 22
_HEAD_H, _ROW_H, _BOX_H = 46, 92, 66
_CHANNEL = 34


def _lane_x(l: int) -> int:
    return _LANE_X0 + l * (_LANE_W + _LANE_GAP)


def _row_y(r: int) -> int:
    return _HEAD_H + r * _ROW_H


def flow_svg() -> str:
    """자립형 인라인 SVG — `/onboarding` 의 flow_svg 와 같은 규약(세로 3열 스윔레인)."""
    e = html.escape
    w = _lane_x(2) + _LANE_W + _CHANNEL
    h = _row_y(len(_NODES) - 1) + _BOX_H + 52
    p = [f'<svg viewBox="0 0 {w} {h}" width="100%" height="auto" role="img" '
         f'preserveAspectRatio="xMidYMin meet" '
         f'aria-label="손 커밋 흐름 — 로컬 초고와 Antigravity 2차 퇴고를 거쳐 최종 리뷰까지">',
         '<defs><marker id="cah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
         'markerHeight="7" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#8b949e"/></marker>'
         '</defs>']

    for i, (name, sub) in enumerate(_LANES):
        x = _lane_x(i)
        fill = "#161b22" if i % 2 == 0 else "#12171e"
        p.append(f'<rect x="{x}" y="0" width="{_LANE_W}" height="{h}" rx="10" fill="{fill}" '
                 f'stroke="#30363d"/>')
        p.append(f'<text x="{x + 14}" y="24" fill="#e6edf3" font-size="13.5" font-weight="650" '
                 f'font-family="ui-monospace,Menlo,monospace">{e(name.replace("`", ""))}</text>')
        p.append(f'<text x="{x + 14}" y="39" fill="#8b949e" font-size="11">{e(sub)}</text>')

    for idx, (_r, l, title, sub, human) in enumerate(_NODES):
        x, y = _lane_x(l) + 12, _row_y(idx)
        bw = _LANE_W - 24
        local = l == 2
        edge = "#d29922" if human else ("#3fb950" if local else "#30363d")
        p.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{_BOX_H}" rx="9" fill="#0d1117" '
                 f'stroke="{edge}" stroke-width="{2 if (human or local) else 1}"/>')
        if human:
            p.append(f'<rect x="{x}" y="{y}" width="4" height="{_BOX_H}" rx="2" fill="#d29922"/>')
        elif local:
            # 🔴 로컬 LLM 자리는 색 말고 표식으로도 말한다 — 「공짜로 도는 구간」이 이 흐름의 요점이다.
            p.append(f'<rect x="{x}" y="{y}" width="4" height="{_BOX_H}" rx="2" fill="#3fb950"/>')
        p.append(f'<text x="{x + 14}" y="{y + 25}" fill="#e6edf3" font-size="13.5" '
                 f'font-weight="650">{e(title)}</text>')
        words = e(sub.replace("**", "").replace("*", "").replace("`", "")).split()
        line, lines = "", []
        for word in words:
            trial = (line + " " + word).strip()
            if len(trial) > 34 and line:
                lines.append(line); line = word
            else:
                line = trial
        lines.append(line)
        for k, ln in enumerate(lines[:2]):
            p.append(f'<text x="{x + 14}" y="{y + 44 + k * 15}" fill="#8b949e" '
                     f'font-size="11.5">{ln}</text>')

    for idx, ((_r1, l1, *_), (_r2, l2, *_)) in enumerate(zip(_NODES, _NODES[1:])):
        y1, y2 = _row_y(idx) + _BOX_H, _row_y(idx + 1)
        x1, x2 = _lane_x(l1) + _LANE_W // 2, _lane_x(l2) + _LANE_W // 2
        mid = y1 + (y2 - y1) // 2
        d = f"M{x1},{y1} V{mid} H{x2} V{y2}" if l1 != l2 else f"M{x1},{y1} V{y2}"
        p.append(f'<path d="{d}" fill="none" stroke="#8b949e" stroke-width="1.5" '
                 f'marker-end="url(#cah)"/>')
        lab = _EDGES[idx] if idx < len(_EDGES) else ""
        if lab:
            # [주의] 라벨을 세로로 쓰지 않는다 (사용자 2026-09-05) — 90도 돌린 글자는 안 읽힌다.
            if l1 != l2:
                p.append(f'<text x="{(x1 + x2) // 2}" y="{mid - 6}" fill="#8b949e" '
                         f'font-size="10.5" text-anchor="middle" '
                         f'font-family="ui-monospace,Menlo,monospace">{e(lab)}</text>')
            else:
                p.append(f'<text x="{x1 + 10}" y="{mid + 4}" fill="#8b949e" font-size="10.5" '
                         f'font-family="ui-monospace,Menlo,monospace">{e(lab)}</text>')

    p.append(f'<text x="{_lane_x(0) + 12}" y="{h - 16}" fill="#8b949e" font-size="11.5">'
             f'<tspan fill="#3fb950">■</tspan> 로컬 LLM — 무료 · 한도를 안 먹는다   '
             f'<tspan fill="#d29922">■</tspan> 사람이 정하는 자리 — ①⑧⑨</text>')
    p.append("</svg>")
    return "".join(p)


def render() -> str:
    """자립형 HTML — 외부 자원 0 (온보딩·상태 화면과 같은 규약)."""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AX 클러스터 — 커밋 흐름</title><style>{_CSS}{_EXTRA}</style></head><body>
<div class="shell">{nav_html("/commit-flow")}<main>
<h1>손으로 커밋하면 무슨 일이 벌어지나</h1>
<div class="sub">컨텍스트 문서 · 로컬 1차 초고 · Antigravity 2차 퇴고 · 최종 리뷰</div>

<p class="lede"><code>.33</code> 에서 코드를 고쳐 커밋하면, 마스터가 그것을 집어
<b>클래스별 컨텍스트 문서</b>와 <b>로컬 리뷰 초고</b>를 만든다. 이어 마스터의
<b>Antigravity가 원본 diff와 초고를 대조</b>해 표가 있는 최종 리뷰로 퇴고한다.
사람이 번호로 부르는 단계는 리뷰 생성이 아니라 <b>지금 main에 적용할지 판단</b>하는 자리다.</p>

<div class="note"><b>분산 작업(<code>/onboarding</code>)과 겹치지 않는다.</b>
그쪽은 <b>일감을 쪼개 워커에게 맡기는</b> 흐름이고, 여기는 <b>그냥 커밋했을 때</b>
자동으로 도는 흐름이다. 🔴 분산 작업 커밋은 3층 게이트를 지나지만
<b>손 커밋은 어느 게이트도 안 지난다</b> — 이 흐름이 그 구멍을 덮는 장치다.</div>

<h2>흐름</h2>
<div class="flow">{flow_svg()}</div>
<div class="legend">
  <span><b class="ok">■</b> 로컬 LLM — 무료</span>
  <span><b>■</b> 사람이 정하는 자리</span>
  <span>자동 구간: 로컬 1차 → Antigravity 2차 · Claude 자동 폴백 없음</span>
</div>

<h2>어느 기계가 받나 — 브로커가 모델로 고른다</h2>
<div class="note"><b>노드를 지정하지 않는다.</b> 마스터는 <b>모델 이름</b>으로
브로커(<code>8102</code>)에 청하고, 브로커가 ①<b>상주 중</b> → ②<code>prefer</code> 지정 →
③폴백 순으로 노드를 고른다.
<div class="callrow" style="margin-top:.5rem">
  <code>.43</code><span><span class="badge local">{html.escape(SYNTH_MODEL)} 상주</span>
    평소 여기로 간다 — 이미 올라가 있어 <b>적재 0초</b></span>
  <code>.2</code><span><span class="badge">{html.escape(SYNTH_MODEL)} 보유</span>
    <b><code>.43</code> 이 죽으면 받는다</b> — 재적재를 물지만 응답은 된다</span>
</div></div>

<h2>합성이 형식 게이트에 걸리면 — 대체 사슬</h2>
<div class="note"><b>순서: <code>{html.escape(_CHAIN_TEXT)}</code></b> (<code>SYNTH_CHAIN</code>, <code>#727</code>).
첫 모델은 언제나 로컬이다 — 상용 레인은 로컬 1차가 <b>형식 게이트에서 거부된 그룹</b>에만,
레인마다 한 번씩 돈다. 어느 모델의 결과든 <b>같은 형식·사실 게이트</b>를 통과해야 문서가 된다.
노드 장애(응답 없음)는 사슬을 타지 않고 회로 차단기가 맡는다. <b>Claude 는 사슬에 없다.</b>
<code>gemma3:12b</code> 는 예시 태그를 베끼는 등 품질 문제가 실측돼 마지막 수단이다.</div>

<h2>머지 커밋은 어떻게 되나</h2>
<div class="note">색인기는 커밋마다 <b>그 커밋의 첫 부모</b>와 비교해 변경 파일을 센다(<code>#744</code>) —
옆 브랜치의 변경이 엉뚱한 커밋에 붙지 않는다. <b>깨끗한 머지</b>는 들어온 조각 커밋들이 이미
합성·리뷰됐으므로 건너뛴다(리뷰 큐에는 「스킵: 머지 — 조각 커밋이 리뷰했다」). 충돌을 손으로
해소했거나 머지 안에서 고친 부분이 있으면 <b>그 부분만</b> 리뷰한다.</div>

<h2>왜 로컬 1차와 Antigravity 2차로 나누나</h2>
<div class="note warn"><b>로컬 모델이 표까지 만드는 길은 실측 뒤 접었다.</b>
형식은 스키마 강제로 지켜지지만
칸이 밀리고 <b>과생성이 2~6배</b>라 유령 항목이 진짜 지적의 4배가 된다 — 그 비용은
사람이 훑으며 치른다. 그래서 로컬 출력은 <b>중간 초고</b>로만 두고, Antigravity가
원본 diff·선언부를 다시 확인해 정형 리뷰를 만든다. <b>Claude 자동 폴백은 없다.</b></div>

<h2>초고는 게시하지 않고 최종 리뷰만 번호를 받는다</h2>
<div class="note"><b>초고에는 표도 R번호도 없다.</b> Antigravity 퇴고가 성공하면
최종 리뷰만 게시판에 올라가고 초고는 제거된다. 사람이 <code>R33</code>을 부르면 새 리뷰를
만드는 것이 아니라, 그 지적이 <b>현재 main에도 합당한가 / 이미 반영됐나 / 의도된 동작인가</b>를
검토해 수락분만 적용한다.</div>
</main></div></body></html>"""


def page() -> bytes:
    return render().encode("utf-8")
