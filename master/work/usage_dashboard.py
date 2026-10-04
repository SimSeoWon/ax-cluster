"""LLM 모델별 기간별 작업·토큰 대시보드 집계 골조.

[DOC] 사용자: 레드마인 일감별 Claude/Codex/Gemini/로컬 LLM 작업과 토큰을
일간·주간·월간으로 보는 신규 웹페이지. 비용·대화 본문은 출력하지 않는다.

동결 인터페이스: build_report의 이름·인자·기본값·반환 표기와 아래 JSON 계약.
UI 조각 master/webui/usage_page.py, 라우트 조각 master/webui/app.py가 소비한다.
공개 함수 변경 금지. 비공개 보조 함수는 추가 가능. 불필요한 lambda 대신 이름 있는 함수.

입력/집계 계약:
- period=daily|weekly|monthly. Asia/Seoul 달력 기준, 주 시작 월요일, 월 시작 1일.
  ISO/UTC 시각은 KST로 변환. usage_log의 naive 시각은 기존 마스터 KST로 해석.
- start/end=YYYY-MM-DD, 양끝 포함. 기본 최근 30일, 최대 366일. 역전·잘못된 값은
  ValueError. now 주입으로 날짜를 결정적으로 검사한다.
- family=""|claude|codex|gemini|local|unknown. 실제 model/lane/tool로 분류하고
  agy라는 이름만으로 Gemini라고 단정하지 않는다. model이 없으면 '모델 미상'.
- source=dispatch|session. 서로 겹칠 수 있어 두 소스의 합산 기능은 제공하지 않는다.
- dispatch: 등록 프로젝트별 usage_log.jsonl, work_id로 큐 _request.md의 project,
  title, redmine_issue_id와 연결. 활성·보관 일감 모두 고려. 연결 실패는 unlinked_calls.
- session: 기존 session_usage.DEFAULT_STORE 숫자 스냅샷만 읽는다. SSH/수집 실행 금지.
  일감·프로젝트 귀속이 없으므로 issues=[]이며 project 필터가 있으면 자료 없음과 경고.
- projects_root/queue_root/session_store는 서버·검사 주입 전용. 웹 쿼리로 경로를 받지 않는다.
  기본 Registry/AX_TASK_QUEUE_ROOT(또는 ~/ax-state)/DEFAULT_STORE를 사용한다.
- 등록되지 않은 project, 잘못된 period/family/source는 ValueError. project=""는 전체.
- measured=False는 미계측이며 토큰 0으로 표현하지 않는다. tokens는 측정된 호출만 합산,
  측정 호출 0건이면 None. 측정된 0은 0. 실패 rc!=0 호출도 사용량에 포함한다.
- Claude input은 cache_read/cache_create 제외 값이므로 총 토큰에 캐시를 더한다.
  Codex input은 cached input을 포함하므로 다시 더하지 않는다. reasoning은 output의
  부분집합이며 다시 더하지 않는다. 합계 정의를 warnings/화면에 명시한다.
- 깨진 JSON/잘못된 레코드/읽기 실패는 건수·고정 경고로 표시한다. 실제 예외는 stderr,
  화면/API에는 절대 경로·원문·인증값을 출력하지 않는다. 필터 이후에 모든 표를 집계한다.

반환 JSON 계약 (추가 키는 가능, 아래 키는 반드시 존재):
{period,start,end,project,family,source,timezone:'Asia/Seoul',generated_at,
 projects:[프로젝트명], warnings:[고정 문자열],
 totals:{calls,measured_calls,unmeasured_calls,failed_calls,tokens,input_tokens,
         output_tokens,cache_read,cache_create,reasoning_tokens,issues,unlinked_calls},
 buckets:[{date:'YYYY-MM-DD'(구간 첫날),family,calls,measured_calls,
           unmeasured_calls,failed_calls,tokens}],
 models:[{family,model,calls,measured_calls,unmeasured_calls,failed_calls,tokens}],
 issues:[{issue_id:양의정수,title,project,work_ids:[str],families:[str],calls,
          measured_calls,unmeasured_calls,failed_calls,tokens,last_at}]}
숫자 계수는 비음수 정수. tokens만 int|None. 일감 title은 큐에 저장된 제목임을 명시.
일감 상세 링크는 UI가 고정 Redmine URL과 issue_id로 만든다.
기간별/모델별 측정 토큰 합계는 totals.tokens와 일치해야 한다.

참조(실제 존재 확인): master/work/usage.py, master/work/session_usage.py,
master/task_queue/persistence.py, master/projects/config.py.
RAG: AXCluster/context/master/work/usage.md 및 session_usage.md.
허용 파일: 이 파일과 master/test_usage_dashboard.py만.
검사: python -B -m unittest master.test_usage_dashboard -v (임시 숫자 로그, 실제 LLM 0).
"""
from __future__ import annotations


def build_report(project: str = "", period: str = "daily", start: str = "",
                 end: str = "", family: str = "", source: str = "dispatch", *,
                 projects_root=None, queue_root=None, session_store=None, now=None) -> dict:
    # [DOC] 위 동결 계약에 맞는 읽기 전용 보고서. 다른 조각의 구현을 기다리지 않는다.
    # [PSEUDO] 실제 숫자 기록을 읽고 검증·정규화·연결·필터·달력 집계 후 JSON을 반환한다.
    raise NotImplementedError
