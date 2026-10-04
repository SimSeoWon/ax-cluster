"""/usage LLM 작업·토큰 시각화 화면 골조.

[DOC] build_report(JSON 계약은 master/work/usage_dashboard.py의 모듈 설명에 동결됨)을
소비한다. 집계 구현은 다른 조각 소유. 이 파일과 master/test_usage_page.py만 변경한다.
참조: master/webui/fixes_page.py, nav.py, master/status.py. 기존 어두운 색·좌측 메뉴 사용.
불필요한 lambda 대신 이름 있는 함수. 외부 CDN/새 의존성 금지.

UI 계약:
- 한국어 신규 페이지 /usage, 일간/주간/월간 전환, 프로젝트·기간·모델 계열 필터,
  작업 실행 기록/대화 세션 기록 선택. 숫자·날짜만 표시, 비용·대화·내부 경로 없음.
- 모델 계열 Claude/Codex/Gemini/로컬 LLM/미상. 실제 model별 요약 표와 기간별 토큰
  SVG 또는 canvas 그래프. 계열 색 구분·축·범례·값 확인·그래프 대체 표 제공.
- 레드마인 일감 표: 번호 링크 http://192.168.0.57:8080/issues/<양의정수>, 큐 제목,
  프로젝트, 참여 모델 계열, 호출·실패·미계측 건수, 측정 토큰, 최근 작업 시각.
- tokens=None은 '미계측', 실제 0은 '0'. 부분 미계측 건수와 미연결 호출을 명시한다.
  Gemini 기록 없음은 '기록 없음'. 작업/세션 합산하지 않고, 세션의 일감 미연결을 설명.
- 사용자/로그 문자열 HTML escape. 임베드 JSON의 </script> 등 안전 처리. 경고·에러도
  escape. 실제 예외/절대 경로는 사용자에게 보내지 않는다. 작은 화면에서 표 스크롤.
- render(report)는 완전한 HTML bytes. page(query)는 (HTTP 상태,HTML bytes).
  query는 project/period/start/end/family/source만 읽는다. loader=None이면 build_report,
  주입 loader는 동일 키워드 입력->dict 계약. ValueError는 400, 읽기 예외는 고정 안내 503.
  렌더러는 로그/파일/네트워크를 직접 읽지 않는다. 필터 GET /usage 링크·form으로 동작.
- 그래프·표에 input/cache/reasoning의 중복 합산 방지와 측정 토큰 합계임을 간단히 설명.

검사: python -B -m unittest master.test_usage_page -v. 주입 보고서로 검증, 라이브 조회 0.
"""
from __future__ import annotations


def render(report: dict) -> bytes:
    # [DOC] 공용 nav.nav_html('/usage')와 SIDE_CSS 사용. 보고서의 숫자와 큐 제목만 표시.
    # [PSEUDO] 필터·토큰 요약·기간 그래프·모델 표·일감 표·미계측 안내를 안전한 HTML로 만든다.
    raise NotImplementedError


def page(query=None, *, loader=None) -> tuple:
    # [DOC] build_report와 동결 키워드로 연결. ValueError/IO 오류를 안전한 HTTP 안내로 변환.
    # [PSEUDO] 허용 쿼리를 읽고 보고서를 불러 render를 호출하여 (status,bytes)를 반환한다.
    raise NotImplementedError
