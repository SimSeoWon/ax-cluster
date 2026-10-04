"""[DOC] 메뉴 조각 검사 골조. 허용 파일 master/webui/nav.py와 이 파일만.
기존 ITEMS에 /usage, 이름 'LLM 사용량', 설명 '기간별 작업 · 토큰'을 하나만 추가한다.
nav_html 기존 선언·메뉴·반응형 스타일을 유지한다. 다른 조각 파일 변경 금지.
"""
import unittest


class UsageNavTests(unittest.TestCase):
    def test_usage_link_is_unique_and_active(self):
        # [PSEUDO] ITEMS의 /usage 1개, nav_html('/usage') 활성 링크·이름을 검증.
        raise NotImplementedError

    def test_existing_links_remain(self):
        # [PSEUDO] 기존 여섯 경로·라벨·설명과 nav_html 출력이 유지되는지 검증.
        raise NotImplementedError


if __name__ == "__main__":
    unittest.main()
