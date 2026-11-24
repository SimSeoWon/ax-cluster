"""세션 귀속 출처 실측 검사 (`#1018`) — 임시 디렉토리만. 실 저장소·SSH·LLM 0.

본다: ① 원인 일곱 가지 각각 ② 원인 합 == 미귀속 ③ 윈도우 이중 구분자 판정(`_norm` 결함) ④ `.ax-issues/<N>`
⑤ 스냅샷 토큰(예비)·미연결 ⑥ usage_log 레인 계열별 커버리지 ⑦ 결합 가능 수와 귀속 라벨
⑧ 출력(표·JSON)에 절대 경로·origin·cwd·홈이 없다 ⑨ 읽기 전용(목록·mtime 불변) ⑩ `--json` 모양 ⑪ 결정성.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from master.work import session_provenance as sp

HOME = "/home/tester"
SHOPS = {
    "local": [(HOME + "/ax-cluster", "AXCluster")],
    "192.168.0.2": [("C:\\trunk\\AXCluster", "AXCluster")],
    "192.168.0.43": [("/home/sim/trunk/NS", "NS")],
}
CODEX_A = "11111111-2222-3333-4444-555555555555"
CODEX_B = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
CLAUDE_C = "c1c1c1c1-0000-0000-0000-000000000001"

# (host, tool, origin, project, cwd)
ENTRIES = [
    ("local", "agy", "brain/conv-empty/.system_generated/logs/transcript.jsonl", None, ""),
    ("local", "claude", "projects/-home-tester/" + CLAUDE_C + ".jsonl", None, HOME),
    ("local", "codex", "sessions/2026/11/01/rollout-2026-11-01T00-00-00-" + CODEX_A + ".jsonl",
     None, "/tmp/ax-pinned-xyz/tree"),
    ("local", "codex", "sessions/2026/11/01/rollout-2026-11-01T00-00-01-" + CODEX_B + ".jsonl",
     "AXCluster", HOME + "/ax-cluster/.ax-issues/942"),
    ("local", "claude", "projects/x/tmpother.jsonl", None, "/tmp/scratch"),
    ("local", "claude", "projects/x/issues.jsonl", None, "/srv/wt/.ax-issues/1020/sub"),
    ("192.168.0.2", "codex", "sessions/2026/11/02/rollout-x-" + "9" * 8 + "-0000-0000-0000-" + "9" * 12
     + ".jsonl", None, "C:\\\\trunk\\\\AXCluster\\\\master"),
    ("192.168.0.2", "claude", "projects/desk/other.jsonl", None, "C:\\Users\\janus\\Desktop"),
    ("192.168.0.43", "codex", "sessions/2026/11/03/rollout-y-" + "7" * 8 + "-0000-0000-0000-"
     + "7" * 12 + ".jsonl", "NS", "/home/sim/trunk/NS/.ax/work/ab12cd34"),
]


def _rec(tokens_in, out, ts="2026-11-01T00:00:00Z"):
    return {"ts": ts, "model": "", "input": tokens_in, "output": out, "cache_read": 0,
            "cache_create": 0, "reasoning": 0}


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.raw, self.store, self.projects = root / "raw", root / "sessions", root / "projects"
        self.raw.mkdir()
        lines = []
        for host, tool, origin, project, cwd in ENTRIES:
            lines.append(json.dumps({"project": project, "work_id": None, "task_id": None,
                                     "host": host, "tool": tool, "origin": origin,
                                     "raw": f"{project or '_unassigned'}/{host}/{tool}/{origin}",
                                     "cwd": cwd, "size": 1, "mtime": 1, "sha256": "x",
                                     "collected_at": "t"}, ensure_ascii=False))
        (self.raw / "index.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        # 스냅샷: tmp_ax codex(A) · 귀속 codex(B) · master_home claude · 색인에 없는 것 하나
        self._snap("local", "codex", ENTRIES[2][2], CODEX_A, [_rec(100, 10), _rec(50, 5)])
        self._snap("local", "codex", ENTRIES[3][2], CODEX_B, [_rec(7, 3)])
        self._snap("local", "claude", ENTRIES[1][2], CLAUDE_C, [_rec(1, 1), {"bad": 1}])
        self._snap("local", "codex", "sessions/pruned/rollout-gone.jsonl", "gone-id", [_rec(4, 4)])
        self.projects.mkdir()
        (self.projects / "projects.yaml").write_text(
            "version: 1\nactive: AXCluster\nprojects:\n  - AXCluster\n  - NS\n", encoding="utf-8")
        ax = self.projects / "AXCluster"
        ax.mkdir()
        usage = [
            {"lane": "codex", "session_id": CODEX_A},          # tmp_ax 세션과 일치
            {"lane": "codex", "session_id": CODEX_B},          # 귀속 세션과 일치
            {"lane": "codex", "session_id": "not-collected-1"},
            {"lane": "codex"},
            {"lane": "agy"},
            {"lane": "claude", "session_id": CLAUDE_C},        # claude 파일 이름 id 와 일치
            {"lane": "local:gemma4:e4b"},
            {"lane": ""},
        ]
        (ax / "usage_log.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in usage) + "not json\n", encoding="utf-8")
        (self.projects / "NS").mkdir()
        (self.projects / "NS" / "usage_log.jsonl").write_text(
            json.dumps({"lane": "codex"}) + "\n", encoding="utf-8")

    def _snap(self, host, tool, origin, sid, records):
        name = origin.removesuffix(".jsonl").replace("/", "__")
        p = self.store / host / tool / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"host": host, "tool": tool, "session_id": sid, "origin": origin,
                                 "records": records}), encoding="utf-8")

    def measure(self):
        return sp.measure(raw_root=self.raw, store=self.store, projects_root=self.projects,
                          home=Path(HOME), shops=SHOPS)

    def _state(self):
        out = {}
        for base in (self.raw, self.store, self.projects):
            for p in sorted(base.rglob("*")):
                st = p.stat()
                out[str(p)] = (st.st_mtime_ns, st.st_size)
        return out

    # ① ② ③ ④
    def test_causes_each_and_sum(self):
        r = self.measure()["raw_index"]
        self.assertEqual(r["total"], len(ENTRIES))
        self.assertEqual(r["unassigned"], 7)
        self.assertEqual(r["causes"], {"empty_cwd": 1, "master_home": 1, "windows_double_slash": 1,
                                       "ax_issues": 1, "tmp_ax": 1, "tmp_other": 1, "other": 1})
        self.assertTrue(r["cause_sum_ok"])
        self.assertEqual(sum(r["causes"].values()), r["unassigned"])
        self.assertEqual(r["by_project"], {"AXCluster": 1, "NS": 1, "_unassigned": 7})
        self.assertEqual(r["causes_by_host"]["windows_double_slash"], {"192.168.0.2": 1})
        self.assertEqual(r["causes_by_tool"]["empty_cwd"], {"agy": 1})
        self.assertEqual(r["ax_issue_numbers"], {"1020": 1})
        self.assertEqual(r["work_or_task_set"], 0)
        self.assertEqual(r["assigned_ax_issues"], 1)
        self.assertEqual(r["assigned_ax_issue_numbers"], {"942": 1})
        self.assertEqual(r["assigned_ax_work"], 1)

    def test_classify_order_and_rules(self):
        c = sp.classify
        self.assertEqual(c("   ", "local", SHOPS, HOME), ("empty_cwd", None))
        self.assertEqual(c(HOME + "/", "local", SHOPS, HOME), ("master_home", None))
        # 홈 하위는 master_home 이 아니다 · 다른 호스트의 같은 문자열도 아니다
        self.assertEqual(c(HOME + "/x", "local", SHOPS, HOME), ("other", None))
        self.assertEqual(c(HOME, "192.168.0.43", SHOPS, HOME), ("other", None))
        # 윈도우 이중 구분자: 접으면 등록 체크아웃에 잇는다 → #1020 결함
        self.assertEqual(c("C:\\\\trunk\\\\AXCluster", "192.168.0.2", SHOPS, HOME),
                         ("windows_double_slash", None))
        self.assertEqual(c("c://Trunk//axcluster/master", "192.168.0.2", SHOPS, HOME),
                         ("windows_double_slash", None))
        # 접어도 체크아웃 밖이면 아니다 · POSIX 호스트에는 적용하지 않는다
        self.assertEqual(c("C:\\\\Users\\\\janus", "192.168.0.2", SHOPS, HOME), ("other", None))
        self.assertEqual(c("/home/sim/trunk//NS", "192.168.0.43", SHOPS, HOME), ("other", None))
        # 이중 구분자 + .ax-issues 이지만 체크아웃에 잇히면 3 이 먼저다
        self.assertEqual(c("C:\\\\trunk\\\\AXCluster\\\\.ax-issues\\\\5", "192.168.0.2", SHOPS, HOME),
                         ("windows_double_slash", None))
        self.assertEqual(c("D:\\wt\\.ax-issues\\77", "192.168.0.2", SHOPS, HOME), ("ax_issues", 77))
        self.assertEqual(c("/tmp/ax-1/.ax-issues/8", "local", SHOPS, HOME), ("ax_issues", 8))
        self.assertEqual(c("/x/.ax-issues/abc", "local", SHOPS, HOME), ("other", None))
        self.assertEqual(c("/tmp/ax-733-live", "local", SHOPS, HOME), ("tmp_ax", None))
        self.assertEqual(c("/tmp/other", "local", SHOPS, HOME), ("tmp_other", None))
        self.assertEqual(c(None, "local", SHOPS, HOME), ("empty_cwd", None))

    # ⑤
    def test_snapshot_tokens_and_unlinked(self):
        s = self.measure()["snapshots"]
        self.assertEqual(s["label"], sp.PRELIMINARY)
        self.assertIn("예비", s["label"])
        rows = s["by_label"]
        self.assertEqual(rows["unassigned:tmp_ax"]["tokens"], 165)
        self.assertEqual(rows["unassigned:tmp_ax"]["by_tool"], {"codex": 165})
        self.assertEqual(rows["project:AXCluster"]["tokens"], 10)
        self.assertEqual(rows["unassigned:master_home"]["tokens"], 2)   # claude: 입력+출력+캐시
        self.assertEqual(rows["unlinked"]["files"], 1)
        self.assertEqual(rows["unlinked"]["tokens"], 8)
        self.assertEqual(s["invalid_records"], 1)
        self.assertEqual(s["files"], 4)
        self.assertEqual(s["index_without_snapshot"], len(ENTRIES) - 3)

    # ⑥ ⑦
    def test_usage_log_coverage_and_joinable(self):
        u = self.measure()["usage_log"]
        ax = u["by_project"]["AXCluster"]
        self.assertEqual(ax["codex"], {"rows": 4, "with_session_id": 3, "matched": 2})
        self.assertEqual(ax["agy"], {"rows": 1, "with_session_id": 0, "matched": 0})
        self.assertEqual(ax["claude"], {"rows": 1, "with_session_id": 1, "matched": 1})
        self.assertEqual(ax["local"], {"rows": 1, "with_session_id": 0, "matched": 0})
        self.assertEqual(ax["other"], {"rows": 1, "with_session_id": 0, "matched": 0})
        self.assertEqual(u["by_project"]["NS"]["codex"]["rows"], 1)
        self.assertEqual(u["joinable"], 3)
        self.assertEqual(u["joinable_by_label"], {"project:AXCluster": 1, "unassigned:tmp_ax": 1,
                                                  "unassigned:master_home": 1})
        self.assertEqual(u["invalid_lines"], 1)

    def test_origin_session_id(self):
        self.assertEqual(sp.origin_session_id("codex", ENTRIES[2][2]), CODEX_A)
        self.assertEqual(sp.origin_session_id("claude", ENTRIES[1][2]), CLAUDE_C)
        self.assertEqual(sp.origin_session_id("agy", ENTRIES[0][2]), "conv-empty")
        self.assertEqual(sp.origin_session_id("codex", "sessions/no-uuid.jsonl"), "")
        self.assertEqual(sp.origin_session_id("agy", "transcript.jsonl"), "")

    # ⑧ ⑩ ⑪
    def _cli(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = sp.main(["--raw-root", str(self.raw), "--store", str(self.store),
                          "--projects-root", str(self.projects), *extra])
        return rc, out.getvalue(), err.getvalue()

    def _assert_clean(self, text):
        forbidden = [HOME, "/home/", "/tmp/", "C:\\", "C:/", "Users", "janus", str(self.raw),
                     str(self.store), str(self.projects), str(Path.home()), "rollout-", "brain/",
                     "projects/x", "sessions/", ".jsonl"]
        for _, _, origin, _, cwd in ENTRIES:
            forbidden += [origin] + ([cwd] if cwd else [])
        for word in forbidden:
            self.assertNotIn(word, text, word)

    def test_cli_text_and_json_have_no_paths(self):
        # CLI 는 레지스트리에서 체크아웃을 읽는다 — 임시 레지스트리에 config.yaml 이 없으면 빈 표로 간다
        for name in ("AXCluster", "NS"):
            (self.projects / name / "config.yaml").write_text(
                f"name: {name}\nproject_id: Sim/{name}\n", encoding="utf-8")
        rc, text, err = self._cli()
        self.assertEqual(rc, 0, err)
        self.assertNotIn("설정 읽기 실패", err)
        self._assert_clean(err)
        self.assertIn("미귀속 원인", text)
        self.assertIn("예비 — 파일 간 중복 보정 전", text)
        self.assertTrue(all(line.startswith("[session_provenance]")
                            for line in err.splitlines() if "[session_provenance]" in line))
        self.assertIn("[session_provenance]", err)
        self._assert_clean(text)
        rc, js, err2 = self._cli("--json")
        self.assertEqual(rc, 0, err2)
        data = json.loads(js)
        self.assertEqual(set(data), {"issue", "raw_index", "snapshots", "usage_log"})
        self.assertEqual(data["issue"], 1018)
        for key in ("total", "unassigned", "causes", "causes_by_tool", "causes_by_host",
                    "cause_sum_ok", "ax_issue_numbers", "work_or_task_set",
                    "assigned_ax_issues", "assigned_ax_work", "by_project"):
            self.assertIn(key, data["raw_index"])
        self.assertEqual(set(data["raw_index"]["causes"]), set(sp.CAUSES))
        self._assert_clean(js)
        for line in err.splitlines() + err2.splitlines():
            if line.startswith("[session_provenance]"):
                self._assert_clean(line)

    def test_injected_measure_output_has_no_paths(self):
        rep = self.measure()
        self._assert_clean(json.dumps(rep, ensure_ascii=False))
        self._assert_clean(sp.render(rep))

    def test_deterministic(self):
        a, b = self.measure(), self.measure()
        self.assertEqual(json.dumps(a, ensure_ascii=False), json.dumps(b, ensure_ascii=False))
        self.assertEqual(sp.render(a), sp.render(b))
        self.assertEqual(list(a["raw_index"]["by_project"]), sorted(a["raw_index"]["by_project"]))

    # ⑨
    def test_read_only(self):
        for name in ("AXCluster", "NS"):
            (self.projects / name / "config.yaml").write_text(
                f"name: {name}\nproject_id: Sim/{name}\n", encoding="utf-8")
        before = self._state()
        self._cli()
        self._cli("--json")
        self.measure()
        self.assertEqual(self._state(), before)

    def test_missing_roots_are_empty_not_errors(self):
        rep = sp.measure(raw_root=self.raw / "none", store=self.store / "none",
                         projects_root=self.projects / "none", home=Path(HOME), shops=SHOPS,
                         names=["AXCluster"])
        self.assertEqual(rep["raw_index"]["total"], 0)
        self.assertTrue(rep["raw_index"]["cause_sum_ok"])
        self.assertEqual(rep["snapshots"]["files"], 0)
        self.assertEqual(rep["usage_log"]["joinable"], 0)
        self.assertFalse((self.raw / "none").exists())

    def test_registry_error_returns_2(self):
        err = io.StringIO()
        env = dict(os.environ)
        os.environ.pop("AX_PROJECTS_ROOT", None)
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = sp.main(["--raw-root", str(self.raw), "--store", str(self.store)])
        finally:
            os.environ.clear()
            os.environ.update(env)
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
