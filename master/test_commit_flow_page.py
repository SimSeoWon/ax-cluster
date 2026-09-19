"""커밋 흐름 화면 + 좌측 목록 (`/commit-flow` · `nav.py`).

검증하는 것:

    ① 자립형이다 — 외부 자원 0 (온보딩·상태 화면과 같은 규약)
    ② 🔴 **사실을 지어내지 않는다** — 모델명이 코드 상수에서 온다
    ③ 🔴 **노드를 「BC250 전용」으로 말하지 않는다** — `.2` 폴백이 화면에 있다
    ④ 자동 구간에 상용이 없다는 것을 말한다
    ⑤ 🔴 **토큰·절대경로·본문이 없다** (이 포트는 무인증 공개다)
    ⑥ 좌측 목록이 모든 항목을 싣고, 지금 화면만 `on` 이다
    ⑦ 목록의 경로가 앱 라우트와 어긋나지 않는다 (죽은 링크 금지)
    ⑧ 온보딩도 같은 좌측 목록을 쓰고, 두 흐름을 서로 가리킨다

`.venv/bin/python master/test_commit_flow_page.py`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.webui import commit_flow as CF                        # noqa: E402
from master.webui import nav as NAV                               # noqa: E402
from master.webui import onboarding as OB                         # noqa: E402
from master.webui import app as APP                               # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [실패] {name}" + (f" — {detail}" if detail else ""))


def test_자립형():
    h = CF.render()
    check("① 외부 스크립트가 없다", "<script" not in h.lower())
    check("① 외부 링크 자원이 없다", 'rel="stylesheet"' not in h and "://" not in
          re.sub(r'aria-label="[^"]*"', "", h).split("<style>")[0])
    check("① SVG 가 인라인이다", "<svg" in h and "<img" not in h)
    check("① 한 화면이 한 파일이다", h.startswith("<!doctype html") and h.endswith("</html>"))


def test_사실은_코드에서_온다():
    from master.context_synth.synth import SYNTH_MODEL
    from master.context_synth.review_runner import DRAFT_MODEL
    h = CF.render()
    check("🔴 ② 합성 모델명이 상수에서 온다", SYNTH_MODEL in h, SYNTH_MODEL)
    check("🔴 ② 초고 모델명이 상수에서 온다", DRAFT_MODEL in h, DRAFT_MODEL)
    # 상수를 바꾸면 화면도 바뀌어야 한다 — 하드코딩이면 이 검사가 잡는다
    check("② 모델명이 하드코딩돼 있지 않다",
          'gemma4:e4b"' not in Path(CF.__file__).read_text(encoding="utf-8"),
          "소스에 리터럴이 박혀 있다")


def test_노드를_전용으로_말하지_않는다():
    h = CF.render()
    check("🔴 ③ .43 상주를 말한다", "상주" in h and ".43" in h)
    check("🔴 ③ .2 폴백을 말한다", ".2" in h and ("죽으면" in h or "폴백" in h), "")
    check("③ 브로커가 고른다고 말한다", "브로커" in h and "8102" in h)


def test_자동구간에_상용이_없다():
    h = CF.render()
    check("④ 상용이 사람 단계에만 있다고 말한다", "상용" in h and "사람" in h)
    check("④ 로컬이 무료임을 말한다", "로컬" in h and "무료" in h)
    check("④ 초고에 표가 없다는 것을 말한다", "표가 없" in h)


def test_민감정보_없음():
    h = CF.render()
    check("🔴 ⑤ 토큰이 없다", "token" not in h.lower() and "Bearer" not in h)
    check("🔴 ⑤ 절대경로가 없다", "/home/sim" not in h and "C:\\\\" not in h)
    check("⑤ API 키가 없다", "api_key" not in h.lower())


def test_좌측_목록():
    h = CF.render()
    for path, name, _d in NAV.ITEMS:
        check(f"⑥ 목록에 {name}", f'href="{path}"' in h, path)
    on = re.findall(r'<a class="item on" href="([^"]+)"', h)
    check("⑥ 지금 화면만 on", on == ["/commit-flow"], str(on))
    ob_on = re.findall(r'<a class="item on" href="([^"]+)"', OB.render())
    check("⑥ 온보딩에서는 온보딩이 on", ob_on == ["/onboarding"], str(ob_on))


def test_죽은_링크가_없다():
    """⑦ 목록의 경로가 앱 라우트와 어긋나면 사람이 고장으로 읽는다."""
    src = Path(APP.__file__).read_text(encoding="utf-8")
    for path, name, _d in NAV.ITEMS:
        if path == "/":
            continue
        # PREFIXES 에 있거나 라우트 분기에 문자열로 등장해야 한다
        served = any(path.startswith(p) for p in APP.PREFIXES) or f'"{path}"' in src
        check(f"⑦ {name}({path}) 가 서는 경로다", served, path)


def test_두_흐름이_서로를_가리킨다():
    ob, cf = OB.render(), CF.render()
    check("🔴 ⑧ 온보딩이 커밋 흐름을 가리킨다", '/commit-flow' in ob)
    check("🔴 ⑧ 커밋 흐름이 분산 작업과 다름을 말한다",
          "/onboarding" in cf and ("겹치지 않" in cf or "다른 흐름" in cf))
    check("⑧ 손 커밋이 게이트를 안 지난다는 것을 말한다", "게이트" in cf)


if __name__ == "__main__":
    for fn in (test_자립형, test_사실은_코드에서_온다, test_노드를_전용으로_말하지_않는다,
               test_자동구간에_상용이_없다, test_민감정보_없음, test_좌측_목록,
               test_죽은_링크가_없다, test_두_흐름이_서로를_가리킨다):
        fn()
    print(f"{PASS}/{PASS + FAIL} 통과")
    sys.exit(1 if FAIL else 0)
