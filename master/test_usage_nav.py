"""[DOC] 메뉴 조각 검사 골조. 허용 파일 master/webui/nav.py와 이 파일만.
기존 ITEMS에 /usage, 이름 'LLM 사용량', 설명 '기간별 작업 · 토큰'을 하나만 추가한다.
nav_html 기존 선언·메뉴·반응형 스타일을 유지한다. 다른 조각 파일 변경 금지.
"""
import unittest

import sys
from pathlib import Path

# 통합 검사는 스크립트로 단독 실행한다(`tests/integration/checks.json`) — 저장소 루트를 경로에 둔다
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.webui.nav import ITEMS, nav_html


class UsageNavTests(unittest.TestCase):
    def test_usage_link_is_unique_and_active(self):
        usage = [item for item in ITEMS if item[0] == "/usage"]
        self.assertEqual(usage, [("/usage", "LLM 사용량", "기간별 작업 · 토큰")])
        rendered = nav_html("/usage")
        self.assertEqual(rendered.count('href="/usage"'), 1)
        self.assertIn(
            '<a class="item on" href="/usage">LLM 사용량'
            '<small>기간별 작업 · 토큰</small></a>', rendered)
        self.assertEqual(rendered.count('class="item on"'), 1)
        self.assertNotIn('class="item on"', nav_html())
        self.assertIn(
            '<a class="item" href="/usage">LLM 사용량',
            nav_html("/reviews"))

    def test_existing_links_remain(self):
        existing = [
            ("/onboarding", "분산 작업", "일감을 쪼개 워커에게 맡기는 흐름"),
            ("/commit-flow", "커밋 흐름", "손 커밋 → 로컬 초고 · Antigravity 리뷰"),
            ("/cluster", "클러스터 상태", "기계 · 서비스 · 지휘 상태"),
            ("/reviews", "리뷰 · 플랜", "번호가 붙은 수정 항목"),
            ("/rag-logs", "RAG 검색 로그", "사용자 원문 · 검색 질의 · 반환 결과"),
            ("/ontology", "온톨로지 뷰어", "도메인 · 클래스 · 액션"),
            ("/", "컨텍스트 검색", "문서를 찾는다"),
        ]
        self.assertEqual([item for item in ITEMS if item[0] != "/usage"], existing)
        self.assertEqual(len(ITEMS), 8)
        rendered = nav_html()
        positions = []
        for path, name, desc in existing:
            with self.subTest(path=path):
                link = (f'<a class="item" href="{path}">{name}'
                        f'<small>{desc}</small></a>')
                self.assertEqual(rendered.count(link), 1)
                positions.append(rendered.index(link))
                active = nav_html(path)
                self.assertIn(link.replace('class="item"', 'class="item on"'), active)
                self.assertEqual(active.count('class="item on"'), 1)
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(rendered.startswith('<nav class="side"><h2>화면</h2>'))
        self.assertTrue(rendered.endswith("</nav>"))


if __name__ == "__main__":
    unittest.main()
