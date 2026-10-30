> 작성: Gemini (agy 1.4.11 · gemini-3.8-flash-medium) · 실행: `master.work.gemini_report` · 2026-10-31 01:08 · 프로젝트 AXCluster
> 자료: src/AXCluster/search_logs/user-command-snapshot.jsonl, src/ModularStage/analysis/kr_ground_truth.tsv, src/master/bench_kr.py, src/master/context_search/search_log.py, src/redmine/issue-211.md, src/redmine/issue-373.md, src/redmine/issue-837.md, src/redmine/issue-838.md, src/redmine/issue-839.md, src/redmine/issue-840.md, src/redmine/issue-842.md, src/redmine/issue-843.md, src/redmine/issue-844.md, src/redmine/issue-845.md, src/redmine/issue-846.md, src/redmine/issue-847.md, src/redmine/issue-848.md, src/redmine/issue-849.md, src/redmine/issue-850.md
> 검증: Codex 핵심 주장 8항목 대조 — 일치 4 · 불일치 4. [검증 불일치] 개발 활용의 직접증거·집계, 상위 발췌 누락, #373 수정 대상, #849 인용 해석. 본문 원문 보존; 상세는 2026-10-31-211-rag-usage-validation-codex-verification.md를 함께 읽는다. 범위 검사(자동): 인용 83개 — 범위 안 83 · 범위 밖 0 · 파일 없음 0 · 읽기 실패 0
> 소요 386초 · 토큰 입력 145568 / 출력 34922 / 캐시읽기 1834456

# #211 RAG 실사용 검증 및 검색 로그 분석 보고서

---

## 1. 요약

사용자의 핵심 의문(로그 축적 여부, 레드마인 기반 검색 여부, 개발 착수 시점의 RAG 참조 및 검증 타당성)에 대한 분석 결과는 다음과 같습니다.

1. **#211 분석을 위한 RAG 검색 로그 축적 여부: "아니오 (판정 표본 부족 및 도메인 분리)"**
   - #211의 본래 완료 기준은 자연어 질의에 대한 **사람 확정(confirmed=y) 표본 30건** 확보 시 `bench_kr.py`를 재실행하여 판정하는 것입니다(src/master/bench_kr.py:98-100, src/redmine/issue-211.md:29, 45). 현재 `kr_ground_truth.tsv`의 자연 계층 확정 표본은 **4건**에 불과하며 2026-08-17 이후 동결 상태입니다(src/ModularStage/analysis/kr_ground_truth.tsv:2-5, src/redmine/issue-211.md:45).
   - 2026-10-20 #837 배포 이후 축적된 사용자 명령 검색(`task_type=user_command`)은 총 **19건**입니다(src/AXCluster/search_logs/user-command-snapshot.jsonl:1-19). 이를 `request_id`로 그룹화하면 독립 요청은 **17건**이며, 이 중 2건은 검증·진단용(드라이런)입니다.
   - 더욱이 축적된 19건은 **AXCluster(Python)** 프로젝트 환경에서 발생한 검색이며, 기존 정답 집합인 **ModularStage(UE5/C++)**와 대상 코드베이스 및 문서 체계가 완전히 분리되어 있어 기존 평가셋에 단순 합산할 수 없습니다.

2. **레드마인 일감 처리 시 RAG 검색 수행 여부: "수행되나, 레드마인 직접 조회가 아닌 LLM 질의 생성 단계의 반영"**
   - 사용자가 "#844 착수해", "#845 착수해"와 같이 일감 번호만 지시하더라도, LLM이 생성한 검색 질의(`llm_query`)에는 해당 레드마인 이슈의 핵심 키워드(예: `workdir 격리`, `_limited`, `REVIEW_TIMEOUT`)가 정확히 포함되어 RAG 검색이 호출됩니다(src/AXCluster/search_logs/user-command-snapshot.jsonl:9, 10, 11).
   - 다만 RAG 검색 엔진 자체(`search_context`)가 레드마인 API나 일감 본문을 직접 읽어 검색하는 것이 아니라, 마스터 에이전트(LLM)가 이전 맥락 또는 레드마인 도구를 통해 파악한 내용을 바탕으로 RAG 검색 질의를 작성한 것으로 추론됩니다(src/master/context_search/search_log.py:38-48).

3. **개발 플랜 작성 및 착수 시 RAG 참조 여부와 로그 기록: "참조 로그는 남으나, 계획 반영의 직접 증거는 계측 한계"**
   - 스펙 등록 후 플랜 작성 및 개발 착수 시점에 RAG 검색이 호출되고 로그가 누적되는 파이프라인은 정상 가동 중입니다(src/AXCluster/search_logs/user-command-snapshot.jsonl:1, 3, 5, 8, 9, 13, 18, 19).
   - 그러나 검색 결과로 반환된 문서를 실제 에이전트가 계획이나 코드에 반영했는지는 이슈 노트를 통한 간접 기록(7건) 및 직접 활용 확인(8건)으로 나뉘며, 검색 로그 자체에는 '결과 문서 채택/인용 여부'를 추적하는 필드가 없어 로그만으로는 확정할 수 없습니다(src/master/context_search/search_log.py:68-82).

4. **일감 단위 검증의 타당성: "방법론은 타당하나 표본과 평가 축의 재정의 필요"**
   - 실제 일감 착수 시 생성된 19건의 검색어는 **100% 한영 혼합 질의(`mixed` 15건, `en` 4건)**였으며, 순수 한글 질의(`hangul_only`)는 0건이었습니다.
   - 따라서 순수 한글 질의에서의 벡터 채널 게이팅을 검증하려던 #211의 기존 가설(src/master/bench_kr.py:45-48)은 실제 개발 환경 질의와 미스매치가 발생합니다. 일감 착수 맥락에서 RAG 품질을 검증하려면 '한영 혼합 질의의 기술 문서 적중도'로 목적이 확장되어야 합니다.

---

## 2. 분모·자료 범위

분석에 사용된 데이터의 분모와 출처는 다음과 같습니다.

| 구분 | 건수 | 출처 및 근거 | 비고 |
| :--- | :---: | :--- | :--- |
| **분석 대상 로그** | **19건** | `src/AXCluster/search_logs/user-command-snapshot.jsonl:1-19` | 5개 일자(10/20~10/31) 누적 `task_type=user_command` 전수 |
| **독립 요청 수** | **17건** | `src/AXCluster/search_logs/user-command-snapshot.jsonl` (request_id 고유값) | 다중 검색 2건(요청당 2회 검색) 포함 |
| **일자별 전체 누적** | **119건** | `BRIEF.md:13` | `context_synthesis` 자동 생성 100건 제외된 수치 |
| **구형 회전 캐시** | **273건** | `BRIEF.md:13` | 구형 회전 캐시(`search_log.jsonl`) 포함 수치 (분모 상이) |
| **기존 정답 집합** | **186건** | `src/ModularStage/analysis/kr_ground_truth.tsv:2-187` | 자연(natural) 4건 + 구조(structural) 182건 |
| **#211 판정 기준** | **30건** | `src/master/bench_kr.py:98-100`, `src/redmine/issue-211.md:29, 45` | 자연 계층 사람 확정(`confirmed=y`) 목표치 (현재 4건) |

- **언어 분포 (19건)**: `mixed` 15건, `en` 4건, `ko` 0건 (src/master/context_search/search_log.py:85-100 휴리스틱 판정 기준).
- **자료 경계**: `src/` 사본 파일만 검토하였으며 저장소 원본, 네트워크, MCP 탐색 및 파일 생성·수정, 코드 실행을 수행하지 않았습니다.

---

## 3. 19검색 전수 검토표

각 검색에 대해 `search_id`(앞 8자리), 사용자 요청 및 연결 이슈, LLM 생성 질의, 질의 적합성, 반환 문서 적합성(후보), 계획·개발 반영 여부(직접증거/간접기록/확인불가), 근거 인용을 기록합니다.

| 번호 | search_id | request_id | 사용자 요청 / 관련 이슈 | LLM 질의 (`llm_query`) / 언어 | 질의 적합성 | 반환 문서 근거 적합성 (후보) | 계획·개발 사용 여부 | 근거 인용 및 분석 |
| :---: | :---: | :---: | :--- | :--- | :---: | :--- | :---: | :--- |
| **1** | `fde21357` | `39d8d62d` | "보완 수정은 어떻게 할지 플랜 작성해"<br>([#837](src/redmine/issue-837.md:55)) | `#837 RAG 검색 로그 웹UI search_id 페이지네이션 domain_index 채널 순위 context_synthesis`<br>(`mixed`) | 상 | 1. `synth.md` (하)<br>2. `search.md` (상)<br>3. `search_log_analyzer.md` (상) | 간접기록 | `src/AXCluster/search_logs/user-command-snapshot.jsonl:1`<br>#837 보완 항목(페이지네이션, 채널 순위 등) 언급되나 RAG 직접 인용 부재. 3위 발췌 빈값(`""`). |
| **2** | `0bf526da` | `2b234c66` | "응! 드라이런도 해야겠어"<br>([#837](src/redmine/issue-837.md:60)) | `RAG 검색 로그 사용자 원문 요청 ID 웹UI`<br>(`mixed`) | 상 | 1. `search_log_analyzer.md` (상)<br>2. `web_ui_original.md` (중)<br>3. `onboarding.md` (하) | **직접증거**<br>(진단용) | `src/AXCluster/search_logs/user-command-snapshot.jsonl:2`<br>`src/redmine/issue-837.md:60`에 request_id 및 search_id, 반환 3건 대조가 명시된 실증 드라이런. |
| **3** | `30224ba7` | `49aaba9b` | "모두 커밋하고. 838번 진행하자..."<br>([#838](src/redmine/issue-838.md:36)) | `등록 문서 README CLAUDE AGENTS 온보딩 문서 갱신 LLM 합성 Python 기존 구현`<br>(`mixed`) | 상 | 1. `prompt.md` (상)<br>2. `pyskel.md` (하)<br>3. `context_synth/__init__.md` (중)<br>4. `recipes_read.md` (하) | 간접기록 | `src/AXCluster/search_logs/user-command-snapshot.jsonl:3`<br>`src/redmine/issue-838.md:37`에 distribute RAG 검색 및 `prompt.py` 대조 기록. 3위 발췌 빈값. |
| **4** | `dcffcb4e` | `ed46ba42` | "응 스킬 연결부터 진행해"<br>([#838](src/redmine/issue-838.md:53)) | `doc_sync 문서 최신화 스킬 연결 plan draft apply`<br>(`mixed`) | 중 | 1. `commit_flow.md` (하)<br>2. `plan_register.md` (중)<br>3. `test_sqlite_util.md` (하) | 확인불가 | `src/AXCluster/search_logs/user-command-snapshot.jsonl:4`<br>신규 생성 중인 모듈이라 반환 문서가 빗나감. 3, 5위 발췌 빈값. 스킬 작성에 미활용 추론. |
| **5** | `3ef43487` | `98ba942f`<br>(다중 1/2) | "839번 840 진행해보자 모두 무슨 작업들이야?"<br>([#839](src/redmine/issue-839.md:27), [#840](src/redmine/issue-840.md:34)) | `#839 doc_sync 영향 문서 탐지 Redmine 운영 근거 보호 문서 실증 #840 #788 클라우드 체인 한도 소진 로컬 재검증`<br>(`mixed`) | 상 | 1. `test_redmine_live_guard.md` (중)<br>2. `doc_sync/__main__.md` (상)<br>3. `redmine.md` (상) | 간접기록 | `src/AXCluster/search_logs/user-command-snapshot.jsonl:5`<br>#839 내용은 적중했으나 #840 내용 부족으로 8분 뒤 Search 6으로 2차 질의 분해 실행. 2, 4, 6위 발췌 빈값. |
| **6** | `92e645fc` | `98ba942f`<br>(다중 2/2) | "839번 840 진행해보자 모두 무슨 작업들이야?"<br>([#840](src/redmine/issue-840.md:18)) | `context_synth synth SYNTH_CHAIN ontology synth DEFAULT_MODELS work lanes quota_exhausted batch run 재검증`<br>(`en`) | 상 | 1. `test_context_synth.md` (상)<br>2. `commit_flow.md` (중)<br>3. `test_synth_parallel.md` (상)<br>4. `synth.md` (상) | 간접기록 | `src/AXCluster/search_logs/user-command-snapshot.jsonl:6`<br>`src/redmine/issue-840.md:18-20`의 `SYNTH_CHAIN`, `DEFAULT_MODELS` 조사에 활용. 한영 혼합이나 en 분류됨. |
| **7** | `9faafa5c` | `3cd78255` | "둘 다 해주고 레드마인 일감으로 등록해줘"<br>([#842](src/redmine/issue-842.md:18)) | `인수인계서 크기 제한 검사 document-registry handoff 체크포인트`<br>(`mixed`) | 상 | 1. `test_doc_sync_registry.md` (중)<br>2. `test_signals.md` (하)<br>3. `work/infer.md` (하) | 확인불가 | `src/AXCluster/search_logs/user-command-snapshot.jsonl:7`<br>반환 문서 대부분이 인수인계서 크기 제한과 무관한 하위 테스트로 채워짐. 3위 발췌 빈값. |
| **8** | `5501aae2` | `3e617cb6` | ".2 윈도우 머신의 보드가 망가져서 교체하고..."<br>([#843](src/redmine/issue-843.md:8)) | `신규 워커 작업장 등재 클론 부트스트랩 bootstrap_checkout 상주 과제 schtasks 등록 세션1 conductor`<br>(`mixed`) | 상 | 1. `conductor.md` (상)<br>2. `session1_conductor.md` (상)<br>3. `orchestration.md` (중)<br>4. `worker_daemon.md` (상) | 간접기록 | `src/AXCluster/search_logs/user-command-snapshot.jsonl:8`<br>`src/redmine/issue-843.md:19`의 상주 과제 해제 및 지휘자 재등록 설계에 참조. 7위 발췌 빈값. |
| **9** | `4c5a573f` | `538455c9` | "#844 착수해"<br>([#844](src/redmine/issue-844.md:8)) | `리뷰 큐 review_runner agy 퇴고 workdir 격리 worktree 임시 트리 call_agy_why run_agy`<br>(`mixed`) | 최상 | 1. `test_usage_cli_paths.md` (상)<br>2. `pinned_tree.md` (상)<br>3. `test_pinned_tree.md` (상)<br>4. `review_runner.md` (상) | **직접증거** | `src/AXCluster/search_logs/user-command-snapshot.jsonl:9`<br>`src/redmine/issue-844.md:37`에 반환 2, 4위인 `pinned_tree.pinned_worktree`와 `review_runner.agy_only` 수정 명시. |
| **10** | `c36e7d71` | `88e8710c` | "#845 착수해"<br>([#845](src/redmine/issue-845.md:8)) | `agy 모델 쿨다운 한도 감지 _limited evidence log 429 RESOURCE_EXHAUSTED quota 재시도 리뷰 큐 transient`<br>(`mixed`) | 최상 | 1. `test_llm_policy.md` (중)<br>2. `log_candidates.md` (하)<br>3. `test_rag_logs_page.md` (하)<br>4. `agy_models.md` (상) | **직접증거** | `src/AXCluster/search_logs/user-command-snapshot.jsonl:10`<br>`src/redmine/issue-845.md:36, 53`에 반환 4위 `agy_models._limited`를 직접 수정 대상으로 확정. 4, 6위 발췌 빈값. |
| **11** | `153db6cf` | `219e69f7` | "#846 착수해"<br>([#846](src/redmine/issue-846.md:8)) | `리뷰 큐 퇴고 프롬프트 정형 리뷰 골격 형식 REVIEW_TIMEOUT agy 탐색 review_gen build prompt`<br>(`mixed`) | 최상 | 1. `test_rag_logs_page.md` (하)<br>2. `test_review_runner.md` (상)<br>3. `test_revise.md` (중)<br>4. `review_runner.md` (상) | **직접증거** | `src/AXCluster/search_logs/user-command-snapshot.jsonl:11`<br>`src/redmine/issue-846.md:54`에 `review_gen.build_prompt` 프롬프트 규칙 추가 반영. 2, 4, 6위 발췌 빈값. |
| **12** | `51ee8a25` | `762f3aa8` | "#847 착수해"<br>([#847](src/redmine/issue-847.md:8)) | `review_queue classify transient 시도 상한 finish claim attempts 재시도 포기 갈래`<br>(`mixed`) | 최상 | 1. `pending.md` (중)<br>2. `review_runner.md` (상)<br>3. `test_pending.md` (중) | 간접기록 | `src/AXCluster/search_logs/user-command-snapshot.jsonl:12`<br>`src/redmine/issue-847.md:25, 42`에 `review_queue.classify`와 `review_runner.drain` 수정 반영. |
| **13** | `5b327673` | `a3609e03` | "#848 착수해"<br>([#848](src/redmine/issue-848.md:8)) | `컨텍스트 합성 synth agy call_agy_why SYNTH_TIMEOUT 프롬프트 ontology synth 색인기 consumer`<br>(`mixed`) | 최상 | 1. `context_synth/__init__.md` (상)<br>2. `test_context_synth.md` (상)<br>3. `synth.md` (상) | **직접증거** | `src/AXCluster/search_logs/user-command-snapshot.jsonl:13`<br>`src/redmine/issue-848.md:42, 53`에 반환 3위 `context_synth/synth.py` 격리 수정 직접 연결. 6위 발췌 빈값. |
| **14** | `873e1184` | `fc9cecdc`<br>(다중 1/2) | "응 849번 진행하자!"<br>([#849](src/redmine/issue-849.md:8)) | `#849 온톨로지 합성 agy codex 고정 트리 pinned_worktree 기준 커밋 #848`<br>(`mixed`) | 상 | 1. `session_usage.md` (하)<br>2. `test_dismissal_candidates.md` (하)<br>3. `branch_names.md` (하) | 확인불가<br>(미사용) | `src/AXCluster/search_logs/user-command-snapshot.jsonl:14`<br>질의에 이슈 번호 및 한글 서술이 섞여 빗나감(오답 밀림). 결과 무효로 보고 12초 뒤 Search 15 재검색. |
| **15** | `4bc3069b` | `fc9cecdc`<br>(다중 2/2) | "응 849번 진행하자!"<br>([#849](src/redmine/issue-849.md:12)) | `master/ontology/synth.py refresh_domain _policy_generate source_commit`<br>(`en`) | 최상 | 1. `ontology/synth.md` (상)<br>2. `projects/config.md` (중)<br>3. `webui/fixes_page.md` (하) | **직접증거** | `src/AXCluster/search_logs/user-command-snapshot.jsonl:15`<br>`src/redmine/issue-849.md:41, 48`에 반환 1위 `ontology/synth.py` 수정 명시. 파일명 직접 타겟팅 성공. |
| **16** | `a7810aba` | `b3757326` | "드라이런 할 방법을 강구해줘"<br>([#849](src/redmine/issue-849.md:46)) | `ontology dry refresh_domain dry_run 임시 도메인 ProjectPaths`<br>(`en`) | 상 | 1. `ontology/synth.md` (상)<br>2. `ontology/pkg_audit.md` (상)<br>3. `test_ontology_synth.md` (상) | **직접증거**<br>(진단용) | `src/AXCluster/search_logs/user-command-snapshot.jsonl:16`<br>`src/redmine/issue-849.md:46`의 도메인 부재 시 드라이런 방법 및 pkg_audit 진단에 참조. 3위 발췌 빈값. |
| **17** | `b1c7d0cd` | `20bde7ed` | "다시 확인해"<br>([#850](src/redmine/issue-850.md:9)) | `ontology contexts prompt Python code profile kind 합성 사실검증`<br>(`en`) | 상 | 1. `context_synth/__init__.md` (중)<br>2. `work/pyskel.md` (중)<br>3. `projects/profile.md` (상) | **직접증거** | `src/AXCluster/search_logs/user-command-snapshot.jsonl:17`<br>`src/redmine/issue-850.md:9-13`의 AXCluster.yaml 프로필(kind: code) 검토로 이어짐. 3위 발췌 빈값. |
| **18** | `5b7fa27d` | `ef2436c9` | "#850 착수하자, 갈림길부터 정리해줘"<br>([#850](src/redmine/issue-850.md:38)) | `온톨로지 합성 프롬프트 소스 발췌 프로젝트 kind 언어별 분기 Python 클래스`<br>(`mixed`) | 최상 | 1. `graph/pyparse.md` (상)<br>2. `test_source_scope.md` (중)<br>3. `graph/parse.md` (상) | **직접증거** | `src/AXCluster/search_logs/user-command-snapshot.jsonl:18`<br>`src/redmine/issue-850.md:54-60`에 1위 `pyparse` AST 분해 및 contexts/prompt 설계 반영. 5, 7, 8위 발췌 빈값. |
| **19** | `d123eb31` | `12834f58` | "373 수정부터 착수해줘"<br>([#373](src/redmine/issue-373.md:140)) | `finalize_work 마감 정리 요청자 로컬 브랜치 삭제 branch -d target_branch`<br>(`mixed`) | 최상 | 1. `test_branch_prune.md` (상)<br>2. `cleanup.md` (상)<br>5. `test_review.md` (상) | **직접증거** | `src/AXCluster/search_logs/user-command-snapshot.jsonl:19`<br>`src/redmine/issue-373.md:144-158`에 반환 2, 5위인 `cleanup.md` 및 `test_review.py` 수정에 직결. 5위 발췌 빈값. |

---

## 4. 원래 목표와 보완 목표

### 4.1 원래 목표 (#211)
- **핵심 가설**: 순수 한글 질의에서 BM25 단독은 정답을 찾으나, RRF 융합 시 벡터 채널의 비관련 상관 오답이 상위로 밀어 올려 순위가 왜곡된다(src/redmine/issue-211.md:10, src/master/bench_kr.py:8).
- **해결책 및 검증**: 식별자가 없는 한글 전용 질의(`hangul_only`)에 대해 벡터 채널을 끄는 게이팅(`gated`) 및 trigram 테이블(`kr_on`) 적용(src/master/bench_kr.py:8-9, 45-48).
- **판정 규칙**: ModularStage 기준 `kr_ground_truth.tsv`의 **자연 계층 사람 확정 표본 30건** 확보 시 `bench_kr.py`로 baseline 대비 hit@1, hit@5, MRR 측정 후 확정(src/master/bench_kr.py:98-100, src/redmine/issue-211.md:29).

### 4.2 사용자 요청의 더 넓은 목적
- 실제 개발 라이프사이클("사용자 의도 → 레드마인 스펙 등록 → 플랜 작성 → RAG 질의 생성 → 검색 결과 → 개발 계획 반영")에서 RAG가 실질적인 엔지니어링 근거를 올바르게 제공하고 있는가의 엔드투엔드 유용성 검증.

### 4.3 두 목표의 관계 및 구조적 차이
1. **대상 프로젝트 및 문서 체계 분리**:
   - #211의 정답표는 ModularStage(UE5 C++ 프로젝트) 기준(`Source/ModularStage/...`)이며, 현재 실사용 로그는 AXCluster(Python 인프라) 기준(`master/...`)입니다. 두 프로젝트는 소스 구조와 온톨로지가 전혀 다르므로 AXCluster 검색 로그를 ModularStage 정답표에 단순 합산하는 것은 평가 오염을 초래합니다.
2. **질의 형태의 불일치**:
   - #211의 게이팅 가설 대상인 `hangul_only` 질의(src/master/bench_kr.py:45-48)는 19건 중 **0건**입니다. 실제 개발 질의는 100% 영문 모듈명, 식별자, CLI 명령어가 결합된 `mixed` 또는 `en` 질의였습니다.
   - 따라서 기존 #211 하네스를 그대로 돌려도 실제 개발 질의들에는 게이팅 분기(`if gated and hangul_only(q0)`)가 전혀 타지 않습니다(src/master/bench_kr.py:65).
3. **평가 지표의 차이**:
   - #211은 검색 순위 지표(hit@1, MRR) 중심의 정량 평가인 반면, 사용자의 요구는 "계획 수립에 필요한 핵심 모듈이 검색되고 실제로 쓰였는가"라는 작업 완수 기여도 평가입니다.

---

## 5. #211 수정 제안 및 진단 한계

### 5.1 현재 표본으로 가능한 진단
1. **수집 및 로깅 파이프라인 무결성**: 사용자 명령 원문과 LLM 질의, 검색 ID, 결과 스냅샷이 누락 없이 기록되고 있습니다(src/AXCluster/search_logs/user-command-snapshot.jsonl:1-19, src/master/context_search/search_log.py:68-82).
2. **다중 검색 전환 패턴 관찰**: 1차 질의가 너무 일반적이거나 오답으로 밀릴 경우(Search 5, Search 14), LLM이 정밀한 영문 식별자 질의로 2차 검색(Search 6, Search 15)을 수행하여 정답 문서를 찾아내는 복구 흐름이 확인되었습니다.

### 5.2 현재 표본으로 내릴 수 없는 정책 결론
1. "KR 라우팅(trigram) 또는 한글 채널 게이팅을 전면 적용/폐기해야 한다"는 결론 불가 (자연 확정 표본 4건에 불과하며, 실사용 로그는 `hangul_only` 범위 밖임).
2. "검색 결과가 개발 계획 수립에 결정적 기여를 했다"고 확정 불가 (반환 문서 중 실제 채택된 문서를 추적하는 계측 부재).

### 5.3 #211 본문 및 완료조건 보완안 (제안)
> [!NOTE]
> 본 보완안은 제안이며 실제 파일에 임의 적용하지 않습니다.

1. **본문 보완안**:
   - 프로젝트 범위 분리 명시: ModularStage(UE5) 고유의 정답 집합과 AXCluster(Python) 실사용 로그 평가 트랙을 분리.
   - 가설 범위 확장: 기존 `hangul_only` 게이팅 가설 외에, 실제 현장에서 다수를 차지하는 '한영 혼합 질의(`mixed`)에서의 벡터/BM25 가중치 및 RRF 순위 품질' 항목 추가.
2. **완료 조건 보완안**:
   - [기존 유지] ModularStage 정답 집합의 자연 확정 표본 30건 도달 시 `bench_kr.py` 판정 규칙은 폐기하지 않고 유지(src/master/bench_kr.py:98-100).
   - [신규 추가] AXCluster 실사용 일감 착수 표본 중 개발자 확인을 거친 **사람 확정(confirmed=y) 20건** 별도 레이어 구축.
   - [계측 보완] 신규 도구를 추가하지 않고, 기존 `search_context` 컨텍스트 매니저(src/master/context_search/search_log.py:38)에 에이전트가 프롬프트/계획 수립에 실제로 채택한 문서를 기록할 수 있는 최소 필드(`selected_file_ids` 등)의 기록 규약 마련.

### 5.4 사람 라벨이 필요한 후보 질문 (19건 로그 기반)
아래 질의들은 반환된 스냅샷 발췌를 통해 정답 문서 후보가 식별되었으나, 최종 품질 지표로 삼기 위해서는 사람 확정 라벨링(`confirmed=y`)이 필요합니다.

1. `리뷰 큐 review_runner agy 퇴고 workdir 격리 worktree 임시 트리 call_agy_why run_agy` (Search 9)
   - 기대 문서 후보: `master/context_synth/pinned_tree.md`, `master/context_synth/review_runner.md`
2. `agy 모델 쿨다운 한도 감지 _limited evidence log 429 RESOURCE_EXHAUSTED quota 재시도 리뷰 큐 transient` (Search 10)
   - 기대 문서 후보: `master/agy_models.md`, `master/test_agy_models.md`
3. `컨텍스트 합성 synth agy call_agy_why SYNTH_TIMEOUT 프롬프트 ontology synth 색인기 consumer` (Search 13)
   - 기대 문서 후보: `master/context_synth/synth.md`, `master/context_synth/__init__.md`
4. `온톨로지 합성 프롬프트 소스 발췌 프로젝트 kind 언어별 분기 Python 클래스` (Search 18)
   - 기대 문서 후보: `master/graph/pyparse.md`, `master/ontology/contexts.md`, `master/ontology/prompt.md`
5. `finalize_work 마감 정리 요청자 로컬 브랜치 삭제 branch -d target_branch` (Search 19)
   - 기대 문서 후보: `master/work/cleanup.md`, `master/test_review.md`

---

## 6. 근거 목록

본 보고서의 모든 판단과 수치는 아래 파일들의 실제 사본 내용을 근거로 합니다.

- `src/AXCluster/search_logs/user-command-snapshot.jsonl:1-19`: 19건 검색 전수 원본 (요청자, ts, search_id, request_id, llm_query, results, result_snapshot, lang).
- `src/master/context_search/search_log.py:1-6`: RAG 요청 추적 및 로그 수집 기본 정책 (#837).
- `src/master/context_search/search_log.py:38-48`: `search_context` 메타데이터 주입 및 request_id 부여 로직.
- `src/master/context_search/search_log.py:68-82`: `_snapshot` 함수 (file_id, rrf_score, excerpt, meta 추출 규약).
- `src/master/context_search/search_log.py:85-100`: `detect_lang` 언어 분류 휴리스틱 (ko, en, mixed 판정 기준).
- `src/master/bench_kr.py:1-18`: #211 한글 검색 벤치마크 하네스 개요 및 baseline/gated 변형 정의.
- `src/master/bench_kr.py:45-48`: `hangul_only` 판정 로직 (식별자 부재 + 한글 포함 조건).
- `src/master/bench_kr.py:98-100`: 자연 계층 30건 미만 시 최종 판정 보류 규칙.
- `src/ModularStage/analysis/kr_ground_truth.tsv:1-5`: 자연 계층(natural) 4건 정답 집합 사본.
- `src/ModularStage/analysis/kr_ground_truth.tsv:6-187`: 구조 계층(structural) 182건 정답 집합 사본.
- `src/redmine/issue-211.md:8-16`: #211 원래 목표 및 가설.
- `src/redmine/issue-211.md:29, 45`: 자연 확정 4건 정체 및 30건 판정 보류 조건 기록.
- `src/redmine/issue-211.md:54-56`: 2026-10-18 재측정 결과 및 한국어 실패 질의 분석.
- `src/redmine/issue-837.md:8-15, 23-28`: #837 사용자 원문/LLM 질의 연결 로그 수집 목적 및 스키마.
- `src/redmine/issue-837.md:60`: #837 실증 드라이런 (Search 2와 정확히 일치하는 기록).
- `src/redmine/issue-838.md:36-37, 53`: #838 착수 및 스킬 연결 기록 (Search 3, 4 대응).
- `src/redmine/issue-839.md:27, 49-60`: #839 영향 문서 탐지 및 스냅샷 근거 결정 (Search 5 대응).
- `src/redmine/issue-840.md:18-20, 38`: #840 클라우드 체인 및 재검증 로직 (Search 6 대응).
- `src/redmine/issue-842.md:18, 34-48`: #842 인수인계서 크기 제한 일감 등록 (Search 7 대응).
- `src/redmine/issue-843.md:8-19`: #843 .2 머신 워커 설정 및 부트스트랩 (Search 8 대응).
- `src/redmine/issue-844.md:8-25, 37`: #844 리뷰 큐 workdir 격리 착수 기록 (Search 9 대응).
- `src/redmine/issue-845.md:8-27, 36, 53`: #845 agy 한도 감지 오탐 수정 기록 (Search 10 대응).
- `src/redmine/issue-846.md:8-24, 54`: #846 리뷰 큐 퇴고 프롬프트 규칙 추가 (Search 11 대응).
- `src/redmine/issue-847.md:8-22, 25, 42`: #847 agy 쿨다운 회차 중단 로직 (Search 12 대응).
- `src/redmine/issue-848.md:8-30, 42, 53`: #848 컨텍스트 합성 격리 트리 수정 (Search 13 대응).
- `src/redmine/issue-849.md:8-28, 41, 46`: #849 온톨로지 합성 격리 및 드라이런 탐색 (Search 14, 15, 16 대응).
- `src/redmine/issue-850.md:8-46, 54-60`: #850 Python 프로젝트 온톨로지 합성 결함 수정 (Search 17, 18 대응).
- `src/redmine/issue-373.md:140-158`: #373 finalize_work 로컬 base 브랜치 정리 (Search 19 대응).

---

## 7. 확인 불가 및 분석 한계

1. **결과 문서 채택 여부 계측 부재 (직접 증거의 한계)**
   - `search_log.py`는 검색 당시의 1~N위 `file_id`, 점수, 발췌를 스냅샷으로 영속화하지만(src/master/context_search/search_log.py:68-82), 호출한 에이전트가 이 중 어떤 문서를 읽고 계획 프롬프트에 주입했는지는 로그에 기록되지 않습니다. 따라서 계획 반영 여부는 레드마인 노트 서술과의 대조를 통한 간접 확인에 의존합니다.
2. **발췌 누락(`excerpt=""`)으로 인한 스냅샷 판정 한계**
   - 19건 검색 중 1위, 2위 문서는 발췌가 정상 저장되었으나, 3위 이하 문서의 상당수에서 `excerpt: ""`로 빈 문자열이 저장되어 있습니다(예: Search 1의 3위, Search 4의 3·5위, Search 5의 2·4·6위, Search 18의 5·7·8위 등). 이는 해당 문서의 본문 추출 실패인지 상위 랭크 외 발췌 생략 로직인지 로그만으로는 구분이 불가능합니다.
3. **자연어 사람 확정 표본의 절대 부족**
   - 정량적 벤치마크 평가를 위한 사람 확정 표본이 4건에 불과하여 통계적 유의성을 가진 검색 품질 수치(hit@1, hit@5, MRR)를 도출할 수 없습니다(src/master/bench_kr.py:98-100).
4. **레드마인 직접 조회 여부의 미확정**
   - LLM 질의에 레드마인 핵심 키워드가 포함되어 있는 것은 확인되나, 마스터 에이전트가 RAG 호출 직전에 어떤 MCP 도구로 레드마인 본문을 읽었는지는 본 RAG 검색 로그 사본 범위 밖이므로 직접 증명할 수 없습니다(추론으로 표기).
