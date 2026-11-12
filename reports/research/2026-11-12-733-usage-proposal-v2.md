> 작성: Gemini (agy 1.5.6 · gemini-4-argon-medium) · 실행: `master.work.gemini_report` · 2026-11-12 23:43 · 프로젝트 AXCluster
> 자료: src/master/context_synth/plan_generator.py, src/master/context_synth/planner.py, src/master/context_synth/recipes_synthesizer.py, src/master/context_synth/scope_plan.py, src/master/test_planner.py, src/master/test_recipes.py, src/master/test_usage_cli_paths.py, src/master/work/usage.py
> 검증: Codex 패치 전체 대상·내용 검토 및 hunk 8개 줄 수 일치 확인, 적용 rc0. 관련 검사 57/57·67/67·18/18, 실제 상용 CLI 두 호출의 프로젝트 usage JSONL 기록 rc0 확인. 전체 결과는 리포트 173 및 Redmine #733 마감 노트.
> 소요 504초 · 토큰 입력 193990 / 출력 42331 / 캐시읽기 143835

### 변경 설명

1. **주간 플랜 사용량 기록 (`src/master/context_synth/planner.py:23`, `src/master/context_synth/planner.py:107-112`)**
   - `run_weekly_plans`에서 작성자별 `generate_improvement_plans` 호출을 `usage.sink(paths.usage_log, source="weekly_plan", task_id=f"{week_num}:{author_name}")`로 감쌉니다.
   - `scope_plan.run_scope`(`src/master/context_synth/scope_plan.py:450-452`)는 이미 `source="scope_plan"` sink로 `generate_improvement_plans`(`src/master/context_synth/plan_generator.py:178-190`)를 호출하므로, `plan_generator.py`가 아닌 `planner.py`에만 sink를 두어 `scope_plan` 기록이 덮이지 않게 유지합니다.

2. **레시피 합성 사용량 기록 (`src/master/context_synth/recipes_synthesizer.py:26`, `src/master/context_synth/recipes_synthesizer.py:572-621`)**
   - `run_recipe_synthesis` 본문 전체(활성 신호 없는 분기의 `_aggregate_anti_patterns`, `_cluster_signals`, `_synthesize_one`, 마지막 `_aggregate_anti_patterns` 모두 포함)를 `usage.sink(paths.usage_log, source="recipe_synthesis", task_id=task_id)`로 감쌉니다.
   - 상용 CLI 공용 진입은 `usage.emit_cli`(`src/master/work/usage.py:695-714`)에서 성공·실패(rc≠0) 호출마다 1행씩 기록하므로 별도 수동 `usage.record` 호출은 추가하지 않습니다.

3. **기존 테스트 fixture 보완 및 CLI 경로 회귀 검증 (`src/master/test_planner.py:77`, `src/master/test_recipes.py:39-42`, `src/master/test_usage_cli_paths.py:31-46`, `src/master/test_usage_cli_paths.py:321-424`)**
   - `test_planner.py`와 `test_recipes.py`의 가짜 경로 객체 `P`에 `usage_log` 속성을 명시해 운영 경로에서 `paths.usage_log` 누락을 조용히 넘기지 않으면서 기존 주입 `chat` 테스트 호환성을 유지합니다.
   - `test_usage_cli_paths.py`에서 가짜 CLI를 통해 ① 주간 플랜 예외 실패 시 1행 기록·원본 리뷰 보존·바깥 sink 복원 및 재시도 성공 시 1행 추가(`source="weekly_plan"`, `task_id=f"{week}:사람"`), ② 범위 플랜의 `generate_improvement_plans` 호출 시 `source="scope_plan"` 유지, ③ 레시피 합성의 클러스터링·합성·안티패턴 3회 호출, 활성 신호 없는 아카이브 안티패턴 분기 1회 호출, 예외 발생 시 1행 기록 및 바깥 sink 복원을 검증합니다.

```diff
diff --git a/master/context_synth/planner.py b/master/context_synth/planner.py
--- a/master/context_synth/planner.py
+++ b/master/context_synth/planner.py
@@ -20,6 +20,7 @@
 from datetime import datetime, timedelta
 from pathlib import Path
 
+from ..work import usage
 from .issue_classifier import group_issues
 from .plan_archive import archive_reviews
 from .plan_generator import (_build_weekly_summary,
@@ -103,10 +104,12 @@
             continue
 
         # Step 3-4: 플랜 생성
-        plan_result = generate_improvement_plans(
-            grouped, context_dir, author_plans_dir, repo_dir,
-            week_num, chat=chat, logf=log,
-        )
+        with usage.sink(paths.usage_log, source="weekly_plan",
+                        task_id=f"{week_num}:{author_name}"):
+            plan_result = generate_improvement_plans(
+                grouped, context_dir, author_plans_dir, repo_dir,
+                week_num, chat=chat, logf=log,
+            )
 
         log(f"[플랜] {author_name}: 플랜 {plan_result['plans_generated']}건 생성 "
             f"(토큰 ~{plan_result['tokens_used']:,})")
diff --git a/master/context_synth/recipes_synthesizer.py b/master/context_synth/recipes_synthesizer.py
--- a/master/context_synth/recipes_synthesizer.py
+++ b/master/context_synth/recipes_synthesizer.py
@@ -23,6 +23,7 @@
 from datetime import datetime, timedelta
 from pathlib import Path
 
+from ..work import usage
 from .review_gen import commercial_chat
 from .signals import read_signals, signals_path
 
@@ -569,54 +570,56 @@
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
+    task_id = getattr(paths, "name", "") or Path(paths.root).name
+    with usage.sink(paths.usage_log, source="recipe_synthesis", task_id=task_id):
+        signals = read_signals(paths)
+        if not signals:
+            log("[레시피] 누적된 신호 없음 — 스킵")
+            # 신호 없어도 아카이브에 rejected_approaches 가 있을 수 있으니 한 번 시도
+            try:
+                _aggregate_anti_patterns(paths, chat=chat, logf=log)
+            except Exception as e:                               # noqa: BLE001
+                log(f"[anti-pattern] 집계 오류: {e}")
+            return 0
 
-    min_signals = max(2, int(min_signals))
-    log(f"[레시피] 신호 {len(signals)}건 분석 시작 (min={min_signals})")
+        min_signals = max(2, int(min_signals))
+        log(f"[레시피] 신호 {len(signals)}건 분석 시작 (min={min_signals})")
 
-    clusters = _cluster_signals(signals, chat=chat, logf=log)
-    if not clusters:
-        log("[레시피] 클러스터 결과 없음 — 스킵")
-        try:
-            _aggregate_anti_patterns(paths, chat=chat, logf=log)
-        except Exception as e:                               # noqa: BLE001
-            log(f"[anti-pattern] 집계 오류: {e}")
-        return 0
+        clusters = _cluster_signals(signals, chat=chat, logf=log)
+        if not clusters:
+            log("[레시피] 클러스터 결과 없음 — 스킵")
+            try:
+                _aggregate_anti_patterns(paths, chat=chat, logf=log)
+            except Exception as e:                               # noqa: BLE001
+                log(f"[anti-pattern] 집계 오류: {e}")
+            return 0
 
-    eligible = [c for c in clusters if len(c["signal_indices"]) >= min_signals]
-    log(f"[레시피] 클러스터 {len(clusters)}개, 합성 대상 {len(eligible)}개 "
-        f"(임계치 미만 {len(clusters) - len(eligible)}개는 다음 사이클까지 대기)")
+        eligible = [c for c in clusters if len(c["signal_indices"]) >= min_signals]
+        log(f"[레시피] 클러스터 {len(clusters)}개, 합성 대상 {len(eligible)}개 "
+            f"(임계치 미만 {len(clusters) - len(eligible)}개는 다음 사이클까지 대기)")
 
-    created = 0
-    processed_indices: set = set()
-    for c in eligible:
-        ok = _synthesize_one(paths, c, signals, chat=chat, logf=log)
-        if ok:
-            created += 1
-            for i in c["signal_indices"]:
-                processed_indices.add(i)
+        created = 0
+        processed_indices: set = set()
+        for c in eligible:
+            ok = _synthesize_one(paths, c, signals, chat=chat, logf=log)
+            if ok:
+                created += 1
+                for i in c["signal_indices"]:
+                    processed_indices.add(i)
 
-    if processed_indices:
-        _archive_signals(paths, processed_indices, signals)
-        log(f"[레시피] 처리된 신호 {len(processed_indices)}건 아카이브 이동")
-    else:
-        log("[레시피] 임계치 도달 클러스터 없음 — 신호 유지")
+        if processed_indices:
+            _archive_signals(paths, processed_indices, signals)
+            log(f"[레시피] 처리된 신호 {len(processed_indices)}건 아카이브 이동")
+        else:
+            log("[레시피] 임계치 도달 클러스터 없음 — 신호 유지")
 
-    # 안티패턴 카탈로그 집계 (레시피 합성과 별개로 rejected_approaches 만 모아 갱신)
-    try:
-        _aggregate_anti_patterns(paths, chat=chat, logf=log)
-    except Exception as e:                                   # noqa: BLE001
-        log(f"[anti-pattern] 집계 오류: {e}")
+        # 안티패턴 카탈로그 집계 (레시피 합성과 별개로 rejected_approaches 만 모아 갱신)
+        try:
+            _aggregate_anti_patterns(paths, chat=chat, logf=log)
+        except Exception as e:                                   # noqa: BLE001
+            log(f"[anti-pattern] 집계 오류: {e}")
 
-    return created
+        return created
 
 
 def main(argv=None) -> int:
diff --git a/master/test_planner.py b/master/test_planner.py
--- a/master/test_planner.py
+++ b/master/test_planner.py
@@ -73,7 +73,8 @@
         self.name = "NS"
         self.root = root
         self.context = root / "context"
         self.repo = root / "repo"
+        self.usage_log = root / "usage_log.jsonl"
 
 
 REVIEW_TPL = """# 자동 코드 리뷰 — {h12}
diff --git a/master/test_recipes.py b/master/test_recipes.py
--- a/master/test_recipes.py
+++ b/master/test_recipes.py
@@ -37,7 +37,9 @@
 class P:
     def __init__(self, root: Path):
+        self.name = "NS"
         self.root = root
         self.repo = root / "repo"
+        self.usage_log = root / "usage_log.jsonl"
 
 
 def fixture(n=5, with_negatives=False):
diff --git a/master/test_usage_cli_paths.py b/master/test_usage_cli_paths.py
--- a/master/test_usage_cli_paths.py
+++ b/master/test_usage_cli_paths.py
@@ -28,14 +28,19 @@
 import sys
 import tempfile
 from contextlib import redirect_stderr
+from datetime import datetime
 from pathlib import Path
 
 _ROOT = Path(__file__).resolve().parent.parent
 sys.path.insert(0, str(_ROOT))
 
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
@@ -316,7 +321,104 @@
         rows = lines(rp.usage_log)[n:]
         check("리뷰 큐 모양(바깥 sink + 주입 chat) → 호출마다 한 줄 (agy 2회 · 형식 재시도)",
               [r["lane"] for r in rows] == ["agy", "agy"], str(rows))
+
+        print("⑥-2 주간 플랜·범위 플랜·레시피 합성 — usage.sink 경로")
+        wp = ProjectPaths(name="W", root=tmp / "W")
+        (wp.context / "_domains").mkdir(parents=True)
+        (wp.repo / "Source" / "M").mkdir(parents=True)
+        (wp.repo / "Source" / "M" / "B.cpp").write_text("int line0;\n", encoding="utf-8")
+        w_rdir = wp.root / "reviews" / "사람"
+        w_rdir.mkdir(parents=True)
+        today = datetime.now().strftime("%Y-%m-%d")
+        week = datetime.now().strftime("%Y-W%W")
+        for i in range(3):
+            h = f"{'ab' * 16}{i:02d}"[:40]
+            (w_rdir / f"{today}_09{i:02d}_{h[:8]}.md").write_text(
+                f"# 자동 코드 리뷰 — {h[:12]}\n\n- 커밋: `{h}`\n\n### Source/M\n\n"
+                "## 2. 변경분 버그·안전성\n| 파일 | 위험도 | 라인 | 설명 | 권장 수정 |\n"
+                f"|---|---|---|---|---|\n| Source/M/B.cpp | 높음 | {10 + i * 30} | null 체크 누락 | IsValid 가드 |\n",
+                encoding="utf-8")
+        w_grouped = PL.group_issues(PL.parse_review_reports(w_rdir, "0000-00-00"), wp.context)
+        valid_plan = (
+            "## 문제 분석\n널 참조가 전달되면 역참조에서 실패한다.\n\n"
+            "## 수정 방안\nBefore: ptr->Run(); After: if (ptr) ptr->Run();\n\n"
+            "## 영향 범위\n호출자의 기존 정상 입력 동작은 유지한다.\n\n"
+            "## 우선순위 근거\n사용자 입력으로 발생하는 실패를 막는다.\n"
+        )
+        _env(CLAUDE_FAKE="json", FAKE_RESULT="OK")
+        with usage.sink(outer, source="ontology", task_id="outer-weekly"):
+            ok_fail = PL.run_weekly_plans(
+                wp, redmine=False,
+                chat=lambda pr: (L2.call_claude_why(pr, timeout=20),
+                                 (_ for _ in ()).throw(RuntimeError("cli boom")))[1])
+            restored_weekly = usage._SINK.get()
+        rows = lines(wp.usage_log)
+        check("주간 플랜 예외 실패 — 호출 1줄 기록 · 바깥 sink 미오염·복원",
+              ok_fail is False and len(rows) == 1
+              and (rows[0]["source"], rows[0]["task_id"], rows[0]["lane"]) == ("weekly_plan", f"{week}:사람", "claude")
+              and not outer.exists() and bool(restored_weekly)
+              and restored_weekly["task_id"] == "outer-weekly", str(rows))
+        _env(CODEX_FAKE="ok", FAKE_RESULT=valid_plan)
+        ok_retry = PL.run_weekly_plans(wp, redmine=False)
+        rows = lines(wp.usage_log)
+        check("[중요] 주간 플랜 재시도(기본 상용 체인) — 재시도도 1줄 추가 · source=weekly_plan",
+              ok_retry is True and len(rows) == 2
+              and [r["lane"] for r in rows] == ["claude", "codex"]
+              and all((r["source"], r["task_id"]) == ("weekly_plan", f"{week}:사람") for r in rows),
+              str(rows))
+
+        sp_log = tmp / "scope_usage.jsonl"
+        with usage.sink(sp_log, source="scope_plan", task_id="scope:combat"):
+            sp_res = PG.generate_improvement_plans(
+                w_grouped, wp.context, tmp / "scope_plans", wp.repo, "2026-11-12_1200")
+        sp_rows = lines(sp_log)
+        check("[중요] 범위 플랜은 plan_generator 호출 시 기존 source=scope_plan 유지",
+              sp_res["plans_generated"] == 1 and len(sp_rows) == 1
+              and (sp_rows[0]["source"], sp_rows[0]["task_id"], sp_rows[0]["lane"])
+              == ("scope_plan", "scope:combat", "codex"), str(sp_rows))
+
+        rcp = ProjectPaths(name="R2", root=tmp / "R2")
+        (rcp.repo / "Source" / "M").mkdir(parents=True)
+        for i in range(2):
+            SG.append_signal(
+                rcp, SG.make_record(
+                    intent=f"히트박스[UHitBox] 판정 추가 {i}",
+                    files_read=[], files_modified=[], source="pipeline",
+                    rejected_approaches=[{"approach": "틱마다 검사", "reason": "성능"}] if i == 0 else [],
+                    error_recoveries=[{"error": "linker error", "fix": "매크로 추가"}] if i == 0 else []))
+        _env(CODEX_FAKE="ok", FAKE_RESULT=(
+            '[{"recipe_name": "HitBox", "intent": "add hitbox", '
+            '"signal_indices": [0, 1], "tags": ["Combat"]}]\n'
+            "Avoid: 틱마다 검사 — 성능\nWatch for: linker error — Recovery: 매크로 추가"))
+        with usage.sink(outer, source="ontology", task_id="outer-recipe"):
+            made = RS.run_recipe_synthesis(rcp, min_signals=2)
+            restored_recipe = usage._SINK.get()
+        r_rows = lines(rcp.usage_log)
+        check("[중요] 레시피 합성(클러스터+합성+안티패턴) — 호출마다 1줄(총 3줄) · 바깥 sink 복원",
+              made == 1 and len(r_rows) == 3
+              and [r["lane"] for r in r_rows] == ["codex", "codex", "codex"]
+              and all((r["source"], r["task_id"]) == ("recipe_synthesis", "R2") for r in r_rows)
+              and not outer.exists() and bool(restored_recipe)
+              and restored_recipe["task_id"] == "outer-recipe", str(r_rows))
+        empty_made = RS.run_recipe_synthesis(rcp, min_signals=2)
+        r_rows = lines(rcp.usage_log)
+        check("레시피 활성 신호 없는 분기(아카이브 안티패턴)도 source=recipe_synthesis 1줄 기록",
+              empty_made == 0 and len(r_rows) == 4
+              and (r_rows[-1]["source"], r_rows[-1]["task_id"], r_rows[-1]["lane"])
+              == ("recipe_synthesis", "R2", "codex"), str(r_rows))
+        _env(CLAUDE_FAKE="json", FAKE_RESULT="OK")
+        with usage.sink(outer, source="ontology", task_id="outer-recipe-err"):
+            RS.run_recipe_synthesis(
+                rcp, min_signals=2,
+                chat=lambda pr: (L2.call_claude_why(pr, timeout=20),
+                                 (_ for _ in ()).throw(RuntimeError("recipe boom")))[1])
+            restored_err = usage._SINK.get()
+        r_rows = lines(rcp.usage_log)
+        check("레시피 합성 예외 시에도 호출 1줄 기록 · 바깥 sink 복원",
+              len(r_rows) == 5 and (r_rows[-1]["source"], r_rows[-1]["lane"]) == ("recipe_synthesis", "claude")
+              and not outer.exists() and bool(restored_err)
+              and restored_err["task_id"] == "outer-recipe-err", str(r_rows))
 
         print("⑧ 🔴 큰 프롬프트 — 명령줄에 싣지 않는다 (리눅스 인자 하나 128KB · E2BIG)")
         _env(CLAUDE_FAKE="json", FAKE_RESULT="OK")
         big = "가" * 70_000 + "\nEND-MARK"          # UTF-8 로 약 210KB — 인자 하나 상한을 넘는다
```
