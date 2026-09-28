"""웹 UI 「전문 보기」 — 컨텍스트 문서 전문 (사용자 요청 2026-09-29 · 공개로 결정).

이 포트는 인증이 없다 — 그래서 **좁힌 것**을 잰다:
  ① `context/` 아래 `.md` 만 · 절대경로·`..`·역슬래시·드라이브 문자 거절 · 없는 파일 404
  ② 응답에 절대경로가 없다
  ③ 라우트가 실제 앱에 붙어 있다 (in-process ASGI · 쿼리스트링 전달)
  ④ 화면에 버튼·모달·Esc 닫기가 있다 (이 기계엔 JS 런타임이 없어 구조로 잰다 — 실물은 라이브 확인)
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.webui import routes  # noqa: E402
from master.webui.app import WebUI  # noqa: E402
from master.webui.web_ui_original import WEB_UI_HTML  # noqa: E402

PASS = FAIL = 0


def check(name, cond, got=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}" + (f" — {got}" if got else ""))


DOC = "---\ntags: [a, b]\ncategory: 툴/스크립트\n---\n\n## 요약\n본문 첫 줄\n"


def _twin(tmp: Path):
    root = tmp / "K"
    (root / "context" / "scripts").mkdir(parents=True)
    (root / "context" / "scripts" / "caption_image.md").write_text(DOC, encoding="utf-8")
    (root / "secret.md").write_text("밖", encoding="utf-8")
    return types.SimpleNamespace(root=root, context=root / "context", name="K")


def test_reads_and_confines(tmp: Path):
    print("\n① 읽기와 경계")
    p = _twin(tmp)
    st, d = routes.api_context_doc(p, "scripts/caption_image.md")
    check("정상 문서 200", st == 200, str(d))
    check("  frontmatter 와 본문을 가른다", "category: 툴/스크립트" in d.get("frontmatter", "")
          and d.get("body", "").startswith("## 요약"), json.dumps(d, ensure_ascii=False)[:160])
    check("  [중요] 응답에 절대경로가 없다", str(tmp) not in json.dumps(d, ensure_ascii=False))
    for bad in ("../secret.md", "scripts/../../secret.md", str(p.root / "secret.md"),
                "scripts\\caption_image.md", "C:/x.md", "scripts/caption_image.py", ""):
        st, d = routes.api_context_doc(p, bad)
        check(f"🔴 거절 400 — {bad!r}", st == 400, f"{st} {d}")
    st, d = routes.api_context_doc(p, "scripts/nope.md")
    check("없는 문서 404", st == 404, f"{st} {d}")


def test_route_is_wired(tmp: Path):
    print("\n③ 앱 라우트")
    p = _twin(tmp)
    app = WebUI(lambda: p)
    got = {}

    async def rcv():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def snd(ev):
        if ev["type"] == "http.response.start":
            got["status"] = ev["status"]
        elif ev["type"] == "http.response.body":
            got["body"] = got.get("body", b"") + ev.get("body", b"")

    q = "file=scripts%2Fcaption_image.md".encode()
    asyncio.run(app({"type": "http", "method": "GET", "path": "/api/v1/context/doc",
                     "headers": [], "query_string": q}, rcv, snd))
    body = json.loads(got.get("body") or b"{}")
    check("GET /api/v1/context/doc → 200 + 본문", got.get("status") == 200
          and "본문 첫 줄" in body.get("body", ""), f"{got.get('status')} {str(body)[:120]}")
    got.clear()
    asyncio.run(app({"type": "http", "method": "GET", "path": "/api/v1/context/doc",
                     "headers": [], "query_string": b"file=..%2Fsecret.md"}, rcv, snd))
    check("🔴 탈출 시도는 앱에서도 400", got.get("status") == 400, str(got.get("status")))


def test_page_has_button_and_modal():
    print("\n④ 화면")
    h = WEB_UI_HTML
    check("검색 결과에 「전문 보기」 버튼", "viewDoc(\\'' + escAttr(r.file)" in h)
    check("문서 목록에도 버튼 (행 클릭 검색과 겹치지 않게 stopPropagation)",
          "event.stopPropagation(); viewDoc(" in h)
    check("모달 마크업", 'id="docModal"' in h and 'id="dmText"' in h and 'id="dmFront"' in h)
    check("Esc·배경·× 로 닫힌다", "e.key === 'Escape'" in h and "event.target === this" in h
          and 'onclick="closeDoc()"' in h)
    check("[중요] 본문은 textContent 로 넣는다 (innerHTML 이 아니다 — 문서 속 HTML 이 실행되지 않게)",
          "getElementById('dmText').textContent = d.body" in h)
    check("요청은 파일 이름을 인코딩한다", "encodeURIComponent(file)" in h)


def main() -> int:
    d = Path(tempfile.mkdtemp())
    try:
        (d / "a").mkdir()
        test_reads_and_confines(d / "a")
        (d / "b").mkdir()
        test_route_is_wired(d / "b")
    finally:
        shutil.rmtree(d)
    test_page_has_button_and_modal()
    print(f"{'OK' if not FAIL else 'FAIL'} test_context_doc_view: {PASS}/{PASS + FAIL} 통과")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
