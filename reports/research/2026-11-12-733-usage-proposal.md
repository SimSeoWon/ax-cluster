> 작성: Gemini (agy 1.5.6 · gemini-4-argon-medium) · 실행: `master.work.gemini_report` · 2026-11-12 23:33 · 프로젝트 AXCluster
> 자료: src/master/context_synth/plan_generator.py, src/master/context_synth/planner.py, src/master/context_synth/recipes_synthesizer.py, src/master/context_synth/scope_plan.py, src/master/test_planner.py, src/master/test_recipes.py, src/master/test_usage_cli_paths.py, src/master/work/usage.py
> 검증: Codex 패치 전체 검토 — diff 헤더 줄 수 불일치 2곳으로 적용 실패(rc128), 소스 변경 0. 검사 자료 재사용 결함도 확인하여 v2로 재요청. 이 제안은 채택하지 않음.
> 소요 287초 · 토큰 입력 89611 / 출력 28187 / 캐시읽기 151714

### 구현 설명 및 근거

1. **주간 플랜(`run_weekly_plans`) 상용 CLI 사용량 기록 (`source="weekly_plan"`)**
   - `src/master/context_synth/planner.py:55-60`에서 `usage_log = Path(paths.usage_log)`를 확인하고, `src/master/context_synth/planner.py:106-109`의 작성자별 `generate_improvement_plans` 호출을 `with usage.sink(usage_log, source="weekly_plan", task_id=f"{week_num}:{author_name}"):`로 감싼다.
   - `src/master/work/usage.py:654-661`, `src/master/work/usage.py:695-715`의 기존 `usage.sink` 및 `emit_cli`가 상용 CLI 호출마다 성공/실패 1행을 기록하고 `finally`에서 바깥 sink를 복원하므로 수동 `usage.record`는 추가하지 않는다.
   - `src/master/context_synth/scope_plan.py:450-452`는 이미 `usage_mod.sink(paths.usage_log, source="scope_plan", task_id=f"scope:{scope.slug}")`로 `generate_improvement_plans`(`src/master/context_synth/plan_generator.py:178-339`)를 감싸고 있으므로, `plan_generator.py` 내부가 아니라 `planner.py`의 `run_weekly_plans`에서만 `weekly_plan` sink를 열어 `scope_plan` 기록이 덮이지 않게 유지한다.

2. **레시피 합성(`run_recipe_synthesis`) 상용 CLI 사용량 기록 (`source="recipe_synthesis"`)**
   - `src/master/context_synth/recipes_synthesizer.py:565-620`의 `run_recipe_synthesis` 진입 시 `usage_log = Path(paths.usage_log)`를 확인하고 함수 본문 전체를 `with usage.sink(usage_log, source="recipe_synthesis"):`로 감싼다.
   - 이로써 활성 신호가 없는 분기의 아카이브 기반 안티패턴 집계(`src/master/context_synth/recipes_synthesizer.py:573-580`), 클러스터링(`src/master/context_synth/recipes_synthesizer.py:585`), 클러스터 결과 없음 분기의 안티패턴 집계(`src/master/context_synth/recipes_synthesizer.py:586-592`), 개별 레시피 합성(`src/master/context_synth/recipes_synthesizer.py:600-605`), 합성 후 안티패턴 집계(`src/master/context_synth/recipes_synthesizer.py:614-618`)의 모든 상용 호출(`src/master/context_synth/recipes_synthesizer.py:118`, `src/master/context_synth/recipes_synthesizer.py:297`, `src/master/context_synth/recipes_synthesizer.py:519`)이 `source="recipe_synthesis"`로 기록된다.

3. **기존 테스트 가짜 `paths` 객체 호환성 및 운영 경로 누락 방지**
   - `src/master/test_planner.py:70-77` 및 `src/master/test_recipes.py:37-40`의 테스트용 가짜 경로 객체 `class P`에는 `usage_log` 속성이 없었다. 운영 코드에서 `getattr(paths, "usage_log", None)` 폴백으로 조용히 스킵하면 설정/객체 누락 시 사용량 기록이 무음으로 빠질 위험이 있으므로, 운영 경로(`planner.py`, `recipes_synthesizer.py`)에서는 `Path(paths.usage_log)`를 직접 요구해 누락을 조용히 허용하지 않고, 테스트의 `class P`에 `self.usage_log = root / "usage_log.jsonl"`을 명시적으로 보완한다.
   - `usage.sink`는 진입 시 ContextVar만 설정하고 실제 파일 쓰기는 `emit_cli`/`emit_broker` 호출 시에만 발생하므로(`src/master/work/usage.py:654-661`), 순수 파이썬 함수를 `chat`으로 주입하는 기존 단위 테스트(`src/master/test_planner.py`, `src/master/test_recipes.py`)의 파일시스템 동작과 완전히 호환된다.

4. **회귀 검증 (`test_planner.py`, `test_recipes.py`, `test_usage_cli_paths.py`)**
   - `src/master/test_planner.py:124-170`, `src/master/test_recipes.py:76-180`: 주입 `chat` 실행 중 활성 `_SINK`의 `path`/`source`/`task_id`와 종료 후 `None` 복원, 활성 신호 0건 분기에서의 안티패턴 `recipe_synthesis` sink 적용을 검증한다.
   - `src/master/test_usage_cli_paths.py:454-476`: 가짜 CLI(`claude`·`codex`·`agy`) 환경에서 ① `run_weekly_plans`의 예외 발생 회차 1행 기록·재시도 회차 1행 기록·바깥 sink 복원, ② 비포착 예외 탈출 시 바깥 sink 복원, ③ `scope_plan` sink 아래 `generate_improvement_plans` 호출 시 `source="scope_plan"` 불변, ④ `run_recipe_synthesis`의 신호 없는 분기(1행)와 클러스터·합성·안티패턴 전 경로(3행) 기록 및 예외 시 바깥 sink 복원을 검증한다.
   - 제공된 `src/` 사본 밖의 호출자 및 외부 파일은 확인 불가다.

```diff
--- a/master/context_synth/planner.py
+++ b/master/context_synth/planner.py
@@ -20,6 +20,7 @@
 from datetime import datetime, timedelta
 from pathlib import Path
 
+from ..work import usage
 from .issue_classifier import group_issues
 from .plan_archive import archive_reviews
 from .plan_generator import (_build_weekly_summary,
@@ -57,6 +58,7 @@
     reviews_dir = Path(paths.root) / REVIEWS_DIRNAME
     context_dir = Path(paths.context)
     repo_dir = Path(paths.repo) if getattr(paths, "repo", None) else None
+    usage_log = Path(paths.usage_log)
 
     since = (now - timedelta(days=7)).strftime("%Y-%m-%d")
     period = f"{since} ~ {now.strftime('%Y-%m-%d')}"
@@ -103,10 +105,12 @@
             continue
 
         # Step 3-4: 플랜 생성
-        plan_result = generate_improvement_plans(
-            grouped, context_dir, author_plans_dir, repo_dir,
-            week_num, chat=chat, logf=log,
-        )
+        with usage.sink(usage_log, source="weekly_plan",
+                        task_id=f"{week_num}:{author_name}"):
+            plan_result = generate_improvement_plans(
+                grouped, context_dir, author_plans_dir, repo_dir,
+                week_num, chat=chat, logf=log,
+            )
 
         log(f"[플랜] {author_name}: 플랜 {plan_result['plans_generated']}건 생성 "
             f"(토큰 ~{plan_result['tokens_used']:,})")
--- a/master/context_synth/recipes_synthesizer.py
+++ b/master/context_synth/recipes_synthesizer.py
@@ -23,6 +23,7 @@
 from datetime import datetime, timedelta
 from pathlib import Path
 
+from ..work import usage
 from .review_gen import commercial_chat
 from .signals import read_signals, signals_path
 
@@ -569,53 +570,55 @@
     합성 후 _aggregate_anti_patterns 도 호출되어 _anti_patterns.md 카탈로그를 갱신한다.
     """
     log = logf or (lambda m: None)
-    signals = read_signals(paths)
-    if not signals:
-        log("[레시피] 누적된 신호 없음 — 스킵")
-        # 신호 없어도 아카이브에 rejected_approaches 가 있을 수 있으니 한 번 시도
-        try:
-            _aggregate_anti_patterns(paths, chat=chat, logf=log)
-        except Exception as e:                               # noqa: BLE001
-            log(f"[anti-pattern] 집계 오류: {e}")
-        return 0
-
-    min_signals = max(2, int(min_signals))
-    log(f"[레시피] 신호 {len(signals)}건 분석 시작 (min={min_signals})")
-
-    clusters = _cluster_signals(signals, chat=chat, logf=log)
-    if not clusters:
-        log("[레시피] 클러스터 결과 없음 — 스킵")
-        try:
-            _aggregate_anti_patterns(paths, chat=chat, logf=log)
-        except Exception as e:                               # noqa: BLE001
-            log(f"[anti-pattern] 집계 오류: {e}")
-        return 0
-
-    eligible = [c for c in clusters if len(c["signal_indices"]) >= min_signals]
-    log(f"[레시피] 클러스터 {len(clusters)}개, 합성 대상 {len(eligible)}개 "
-        f"(임계치 미만 {len(clusters) - len(eligible)}개는 다음 사이클까지 대기)")
-
-    created = 0
-    processed_indices: set = set()
-    for c in eligible:
-        ok = _synthesize_one(paths, c, signals, chat=chat, logf=log)
-        if ok:
-            created += 1
-            for i in c["signal_indices"]:
-                processed_indices.add(i)
-
-    if processed_indices:
-        _archive_signals(paths, processed_indices, signals)
-        log(f"[레시피] 처리된 신호 {len(processed_indices)}건 아카이브 이동")
-    else:
-        log("[레시피] 임계치 도달 클러스터 없음 — 신호 유지")
-
-    # 안티패턴 카탈로그 집계 (레시피 합성과 별개로 rejected_approaches 만 모아 갱신)
-    try:
-        _aggregate_anti_patterns(paths, chat=chat, logf=log)
-    except Exception as e:                                   # noqa: BLE001
-        log(f"[anti-pattern] 집계 오류: {e}")
-
-    return created
+    usage_log = Path(paths.usage_log)
+    with usage.sink(usage_log, source="recipe_synthesis"):
+        signals = read_signals(paths)
+        if not signals:
+            log("[레시피] 누적된 신호 없음 — 스킵")
+            # 신호 없어도 아카이브에 rejected_approaches 가 있을 수 있으니 한 번 시도
+            try:
+                _aggregate_anti_patterns(paths, chat=chat, logf=log)
+            except Exception as e:                               # noqa: BLE001
+                log(f"[anti-pattern] 집계 오류: {e}")
+            return 0
+
+        min_signals = max(2, int(min_signals))
+        log(f"[레시피] 신호 {len(signals)}건 분석 시작 (min={min_signals})")
+
+        clusters = _cluster_signals(signals, chat=chat, logf=log)
+        if not clusters:
+            log("[레시피] 클러스터 결과 없음 — 스킵")
+            try:
+                _aggregate_anti_patterns(paths, chat=chat, logf=log)
+            except Exception as e:                               # noqa: BLE001
+                log(f"[anti-pattern] 집계 오류: {e}")
+            return 0
+
+        eligible = [c for c in clusters if len(c["signal_indices"]) >= min_signals]
+        log(f"[레시피] 클러스터 {len(clusters)}개, 합성 대상 {len(eligible)}개 "
+            f"(임계치 미만 {len(clusters) - len(eligible)}개는 다음 사이클까지 대기)")
+
+        created = 0
+        processed_indices: set = set()
+        for c in eligible:
+            ok = _synthesize_one(paths, c, signals, chat=chat, logf=log)
+            if ok:
+                created += 1
+                for i in c["signal_indices"]:
+                    processed_indices.add(i)
+
+        if processed_indices:
+            _archive_signals(paths, processed_indices, signals)
+            log(f"[레시피] 처리된 신호 {len(processed_indices)}건 아카이브 이동")
+        else:
+            log("[레시피] 임계치 도달 클러스터 없음 — 신호 유지")
+
+        # 안티패턴 카탈로그 집계 (레시피 합성과 별개로 rejected_approaches 만 모아 갱신)
+        try:
+            _aggregate_anti_patterns(paths, chat=chat, logf=log)
+        except Exception as e:                                   # noqa: BLE001
+            log(f"[anti-pattern] 집계 오류: {e}")
+
+        return created
 
 
 def main(argv=None) -> int:
--- a/master/test_planner.py
+++ b/master/test_planner.py
@@ -25,6 +25,7 @@
 from master.context_synth import planner as PL                   # noqa: E402
 from master.context_synth import plan_generator as PG            # noqa: E402
 from master.context_synth.plan_dedup import _inherit_redmine_issue_id  # noqa: E402
+from master.work import usage                                    # noqa: E402
 
 PASS = FAIL = 0
 
@@ -74,6 +75,7 @@
         self.root = root
         self.context = root / "context"
         self.repo = root / "repo"
+        self.usage_log = root / "usage_log.jsonl"
 
 
 REVIEW_TPL = """# 자동 코드 리뷰 — {h12}
@@ -124,10 +126,11 @@
 def test_end_to_end():
     # [DOC] #632: planner는 프로젝트 이름을 주차 등록에 전달한다. 외부 호출은 주입한다.
     p, rdir = fixture(pattern=True)
-    chats, regs = [], []
+    chats, regs, sinks = [], [], []
 
     def chat(prompt):
         chats.append(prompt)
+        sinks.append(usage._SINK.get())
         return valid_response(prompt)
 
     ok = PL.run_weekly_plans(p, chat=chat,
@@ -136,6 +139,11 @@
                              logf=lambda m: None)
     check("[중요] 플랜이 생성됐다", ok is True)
     week = datetime.now().strftime("%Y-W%W")
+    check("#733 주간 플랜 생성 구간에 weekly_plan sink(주차·작성자) 적용 및 복원",
+          bool(sinks) and all(s and s.get("path") == p.usage_log
+                              and s.get("source") == "weekly_plan"
+                              and s.get("task_id") == f"{week}:사람" for s in sinks)
+          and usage._SINK.get() is None, str(sinks))
     wd = p.root / "plans" / "사람" / week
     plans = [f.name for f in wd.glob("*.md") if f.name != "_summary.md"]
     check("고위험 파일 플랜이 나왔다 (B.cpp 높음)", "high_B.md" in plans, str(plans))
--- a/master/test_recipes.py
+++ b/master/test_recipes.py
@@ -21,6 +21,7 @@
 
 from master.context_synth import recipes_synthesizer as RS      # noqa: E402
 from master.context_synth import signals as SG                  # noqa: E402
+from master.work import usage                                   # noqa: E402
 
 PASS = FAIL = 0
 
@@ -38,6 +39,7 @@
     def __init__(self, root: Path):
         self.root = root
         self.repo = root / "repo"
+        self.usage_log = root / "usage_log.jsonl"
 
 
 def fixture(n=5, with_negatives=False):
@@ -75,10 +77,11 @@
 
 def test_synthesis_roundtrip():
     p = fixture(5, with_negatives=True)
-    calls = []
+    calls, sinks = [], []
 
     def chat(prompt):
         calls.append(prompt)
+        sinks.append(usage._SINK.get())
         if "Cluster signals" in prompt:
             return "설명 산문...\n" + CLUSTER_JSON + "\n끝"
         if "anti-pattern catalog" in prompt:
@@ -87,6 +90,10 @@
 
     n = RS.run_recipe_synthesis(p, min_signals=5, chat=chat, logf=lambda m: None)
     check("[중요] 생산자 실물 파일에서 레시피 1건", n == 1, str(n))
+    check("#733 클러스터·합성·안티패턴 호출에 recipe_synthesis sink 적용 및 복원",
+          len(sinks) == 3 and all(s and s.get("path") == p.usage_log
+                                  and s.get("source") == "recipe_synthesis" for s in sinks)
+          and usage._SINK.get() is None, str(sinks))
 
     recipe = RS.recipes_dir(p) / "HitBoxJudge.md"
     text = recipe.read_text(encoding="utf-8")
@@ -176,6 +183,21 @@
     p2 = fixture(2, with_negatives=True)
     got2 = RS._aggregate_anti_patterns(p2, chat=lambda pr: "카탈로그 라인이 없는 응답")
     check("응답에서 카탈로그 라인을 못 세면 갱신 스킵 (-1)", got2 == -1, str(got2))
+    p3 = fixture(0)
+    RS.recipes_dir(p3).mkdir(parents=True, exist_ok=True)
+    RS.archive_path(p3).write_text(json.dumps({
+        "timestamp": datetime.now().isoformat(timespec="seconds"),
+        "intent": "아카이브 안티패턴",
+        "rejected_approaches": [{"approach": "매 프레임 탐색", "reason": "비용"}],
+    }, ensure_ascii=False) + "\n", encoding="utf-8")
+    no_sig_sinks = []
+    n3 = RS.run_recipe_synthesis(
+        p3, chat=lambda pr: (no_sig_sinks.append(usage._SINK.get()), ANTI_BODY)[1],
+        logf=lambda m: None)
+    check("#733 활성 신호 0건 분기에서도 안티패턴 호출에 recipe_synthesis sink 적용 및 복원",
+          n3 == 0 and len(no_sig_sinks) == 1
+          and no_sig_sinks[0] and no_sig_sinks[0].get("path") == p3.usage_log
+          and no_sig_sinks[0].get("source") == "recipe_synthesis"
+          and usage._SINK.get() is None)
 
 
 def main() -> int:
--- a/master/test_usage_cli_paths.py
+++ b/master/test_usage_cli_paths.py
@@ -26,6 +26,7 @@
 import subprocess
 import sys
 import tempfile
+from datetime import datetime
 from contextlib import redirect_stderr
 from pathlib import Path
 
@@ -34,7 +35,11 @@
 
 from master import layer2_verify as L2                                # noqa: E402
 from master.context_search.paths import ProjectPaths                  # noqa: E402
+from master.context_synth import plan_generator as PG                 # noqa: E402
+from master.context_synth import planner as PL                        # noqa: E402
+from master.context_synth import recipes_synthesizer as RS            # noqa: E402
 from master.context_synth import review_gen as RG                     # noqa: E402
+from master.context_synth import signals as SG                        # noqa: E402
 from master.work import lanes as LN                                   # noqa: E402
 from master.work import usage                                         # noqa: E402
 from master.work import usage_dashboard as UD                         # noqa: E402
@@ -462,6 +467,139 @@
         raw = {"ts": "2026-10-04 12:00:00", "lane": "claude", "model": "claude-opus-4-1", "measured": True,
                "rc": 0, "input_tokens": 1, "output_tokens": 1, "source": "board"}
         check("claude 모델명이 실려도 claude", UD._normal_record(raw, session=False)["family"] == "claude")
+
+        print("⑩ 주간 플랜·레시피 합성·범위 플랜 — weekly_plan · recipe_synthesis · scope_plan (#733)")
+        wp = ProjectPaths(name="W", root=tmp / "W")
+        (wp.context / "_domains").mkdir(parents=True)
+        (wp.repo / "Source" / "M").mkdir(parents=True)
+        (wp.repo / "Source" / "M" / "B.cpp").write_text("int line0;\n", encoding="utf-8")
+        w_rdir = wp.root / "reviews" / "사람"
+        w_rdir.mkdir(parents=True)
+        today = datetime.now().strftime("%Y-%m-%d")
+        week = datetime.now().strftime("%Y-W%W")
+        for i in range(3):
+            h = f"{'cd' * 16}{i:02d}"[:40]
+            (w_rdir / f"{today}_10{i:02d}_{h[:8]}.md").write_text(
+                f"# 자동 코드 리뷰 — {h[:12]}\n\n- 커밋: `{h}`\n\n### Source/M\n\n"
+                f"## 1. 변경분 코딩 컨벤션\n| 파일 | 항목 | 위반 내용 | 라인 | 심각도 |\n|---|---|---|---|---|\n\n"
+                f"## 2. 변경분 버그·안전성\n| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n|---|---|---|---|---|\n"
+                f"| Source/M/B.cpp | 높음 | {10 + i * 30} | null 체크 누락 | 가드 |\n\n"
+                f"## 3. 영향 분석\n없음.\n",
+                encoding="utf-8")
+        valid_plan = (
+            "## 문제 분석\n널 참조가 전달되면 역참조에서 실패한다.\n\n"
+            "## 수정 방안\nBefore: ptr->Run(); After: if (ptr) ptr->Run();\n\n"
+            "## 영향 범위\n호출자의 기존 정상 입력 동작은 유지한다.\n\n"
+            "## 우선순위 근거\n사용자 입력으로 발생하는 실패를 막는다.\n"
+        )
+        w_outer = tmp / "w_outer.jsonl"
+        with usage.sink(w_outer, source="ontology", task_id="outer-plan"):
+            _env(CLAUDE_FAKE="json", FAKE_RESULT=valid_plan)
+
+            def raising_plan_chat(pr):
+                L2.call_claude_why(pr, timeout=20)
+                raise RuntimeError("플랜 후보 예외")
+
+            ok_fail = PL.run_weekly_plans(wp, chat=raising_plan_chat, redmine=False, logf=lambda _: None)
+            after_fail_sink = usage._SINK.get()
+            _env(CODEX_FAKE="ok", FAKE_RESULT=valid_plan)
+            ok_retry = PL.run_weekly_plans(wp, redmine=False, logf=lambda _: None)
+            after_retry_sink = usage._SINK.get()
+        w_rows = lines(wp.usage_log)
+        check("[중요] 주간 플랜 예외 1행 + 재시도 1행 기록 (source=weekly_plan · task_id에 주차·작성자)",
+              ok_fail is False and ok_retry is True and len(w_rows) == 2
+              and [(r["lane"], r["source"], r["task_id"]) for r in w_rows]
+              == [("claude", "weekly_plan", f"{week}:사람"), ("codex", "weekly_plan", f"{week}:사람")],
+              str(w_rows))
+        check("주간 플랜 sink 종료 후 바깥 sink 복원 및 바깥 로그 무오염",
+              bool(after_fail_sink) and after_fail_sink.get("task_id") == "outer-plan"
+              and bool(after_retry_sink) and after_retry_sink.get("task_id") == "outer-plan"
+              and not w_outer.exists())
+
+        # 비포착 예외가 generate_improvement_plans 밖으로 탈출해도 바깥 sink 가 복원된다.
+        wp_abort = ProjectPaths(name="WA", root=tmp / "WA")
+        (wp_abort.context / "_domains").mkdir(parents=True)
+        abort_rdir = wp_abort.root / "reviews" / "사람"
+        abort_rdir.mkdir(parents=True)
+        for i in range(3):
+            h = f"{'ef' * 16}{i:02d}"[:40]
+            (abort_rdir / f"{today}_11{i:02d}_{h[:8]}.md").write_text(
+                (w_rdir / sorted(w_rdir.iterdir())[i].name).read_text(encoding="utf-8"),
+                encoding="utf-8")
+        with usage.sink(w_outer, source="ontology", task_id="outer-abort"):
+            _env(CLAUDE_FAKE="json", FAKE_RESULT=valid_plan)
+            caught_abort = False
+            try:
+                def abort_chat(pr):
+                    L2.call_claude_why(pr, timeout=20)
+                    raise BaseException("비포착 탈출")
+                PL.run_weekly_plans(wp_abort, chat=abort_chat, redmine=False, logf=lambda _: None)
+            except BaseException:
+                caught_abort = True
+            restored_abort = usage._SINK.get()
+        check("비포착 예외 탈출 시에도 호출 1행 기록 및 바깥 sink 복원",
+              caught_abort and len(lines(wp_abort.usage_log)) == 1
+              and lines(wp_abort.usage_log)[0].get("source") == "weekly_plan"
+              and bool(restored_abort) and restored_abort.get("task_id") == "outer-abort")
+
+        # scope_plan 은 이미 source=scope_plan sink 를 가지므로 plan_generator 가 덮어쓰지 않는다.
+        from master.context_synth.review_collector import ReviewIssue
+        scope_issue = ReviewIssue(file="Source/M/B.cpp", line="10", category="safety", severity="high",
+                                  description="null", recommendation="guard", review_date=today,
+                                  commit_hash="c", module="M", source_review="r.md")
+        scope_grouped = {"file_issues": {"Source/M/B.cpp": [scope_issue]},
+                         "pattern_issues": [], "excluded_count": 0, "total": 1}
+        _env(CLAUDE_FAKE="json", FAKE_RESULT=valid_plan)
+        with usage.sink(wp.usage_log, source="scope_plan", task_id="scope:combat"):
+            PG.generate_improvement_plans(scope_grouped, wp.context, wp.root / "plans" / "_scope",
+                                          wp.repo, "2026-11-12_1200", logf=lambda _: None)
+        scope_row = lines(wp.usage_log)[-1]
+        check("[중요] scope_plan 기존 sink 기록 불변 (plan_generator 가 덮지 않는다)",
+              (scope_row.get("source"), scope_row.get("task_id")) == ("scope_plan", "scope:combat"),
+              str(scope_row))
+
+        # run_recipe_synthesis: 신호 없는 분기(아카이브 안티패턴) + 클러스터·합성·안티패턴 + 예외 복원
+        sp = ProjectPaths(name="S", root=tmp / "S")
+        (sp.repo / "Source" / "M").mkdir(parents=True)
+        (sp.repo / "Source" / "M" / "UHitBox.h").write_text("class UHitBox {};\n", encoding="utf-8")
+        RS.recipes_dir(sp).mkdir(parents=True, exist_ok=True)
+        RS.archive_path(sp).write_text(json.dumps({
+            "timestamp": datetime.now().isoformat(timespec="seconds"),
+            "intent": "아카이브 신호",
+            "rejected_approaches": [{"approach": "전수 루프", "reason": "성능"}],
+        }, ensure_ascii=False) + "\n", encoding="utf-8")
+        anti_body = (
+            "## User-Rejected Approaches\n\n### Combat\n- Avoid: 전수 루프 — 성능.\n\n"
+            "## Build Recoveries\n- Watch for: linker error on [UHitBox] — Recovery: UCLASS.\n\n"
+            "## Crash Recoveries\n_None recorded yet._\n\n"
+            "## Behavioral Investigations\n_None recorded yet._"
+        )
+        cluster_json = ('[{"recipe_name": "HitBoxJudge", "intent": "Add [UHitBox] judgement", '
+                        '"signal_indices": [0, 1], "tags": ["Combat", "히트박스"]}]')
+        recipe_body = ("## Intent\nAdd [UHitBox] judgement.\n\n## Steps\n1. Edit [UHitBox].\n\n"
+                       "## Files of Interest\n- Source/M/UHitBox.h: class\n\n## Caveats\nNone.")
+        r_outer = tmp / "r_outer.jsonl"
+        with usage.sink(r_outer, source="ontology", task_id="outer-recipe"):
+            _env(CODEX_FAKE="ok", FAKE_RESULT=anti_body)
+            n0 = RS.run_recipe_synthesis(sp, logf=lambda _: None)
+            after_empty_sink = usage._SINK.get()
+            for i in range(2):
+                SG.append_signal(sp, SG.make_record(
+                    intent=f"히트박스[UHitBox] 판정 {i}",
+                    files_read=["Source/M/UHitBox.h"],
+                    files_modified=[{"path": "Source/M/UHitBox.cpp", "summary": "판정"}],
+                    rejected_approaches=[{"approach": "전수 루프", "reason": "성능"}] if i == 0 else [],
+                    error_recoveries=[{"error": "linker error on [UHitBox]", "fix": "UCLASS"}] if i == 0 else [],
+                    source="pipeline"))
+
+            def recipe_cli_chat(pr):
+                res = (cluster_json if "Cluster signals" in pr
+                       else anti_body if "anti-pattern catalog" in pr else recipe_body)
+                _env(CLAUDE_FAKE="json", FAKE_RESULT=res)
+                return L2.call_claude_why(pr, timeout=20)[0]
+
+            n1 = RS.run_recipe_synthesis(sp, min_signals=2, chat=recipe_cli_chat, logf=lambda _: None)
+            after_full_sink = usage._SINK.get()
+        s_rows = lines(sp.usage_log)
+        check("[중요] 레시피 합성 — 신호 0건 분기(1행) + 클러스터·합성·안티패턴(3행) 모두 source=recipe_synthesis",
+              n0 == 0 and n1 == 1 and len(s_rows) == 4
+              and [r[" lane" if " lane" in r else "lane"] for r in s_rows] == ["codex", "claude", "claude", "claude"]
+              and all(r.get("source") == "recipe_synthesis" for r in s_rows),
+              str(s_rows))
+        check("레시피 합성 sink 종료 후 바깥 sink 복원 및 바깥 로그 무오염",
+              bool(after_empty_sink) and after_empty_sink.get("task_id") == "outer-recipe"
+              and bool(after_full_sink) and after_full_sink.get("task_id") == "outer-recipe"
+              and not r_outer.exists())
     finally:
         os.environ["PATH"] = old_path
         _AGY_STATE_ROOT = None
``` detail: Done.
