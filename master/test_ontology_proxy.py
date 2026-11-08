"""#898 실제 8101 앱의 인증·태그 경계와 기존 온톨로지 코어 호출 회귀."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from master.context_search.paths import ProjectPaths
from master.projects.config import ConfigError
from master.task_queue import server
from master.ontology import yaml_io

TOKEN = "master-" + "m" * 40
REQUESTER = "requester-" + "r" * 40
WORKER = "worker-" + "w" * 40
ROUTES = ["/api/v1/ontology/" + name for name in (
    "create-domain", "edit-item", "remove-item", "lock-item", "list-locked",
    "unassigned-classes", "sync")]
ROUTES += ["/api/v1/workshops/list", "/api/v1/workshops/check-clean"]
ROUTES += ["/api/v1/thesaurus/resolve"]
ROUTES += ["/api/v1/ontology/" + name for name in (
    "edit-domain-field", "list-log-tags", "set-log-tag", "remove-log-tag",
    "staging-begin", "staging-commit", "staging-discard", "staging-status",
    "rename-domain", "rename-class")]


class OntologyProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        idx = Mock(works={}, tasks={})
        with patch.object(server, "TaskIndex", return_value=idx), \
                patch.object(server, "_bootstrap_log_rotation"), \
                patch.object(server, "_tq_log"), \
                patch.object(server, "recover_stuck_works", return_value=[]), \
                patch.object(server, "load_token", return_value=TOKEN), \
                patch("master.auth.load_role_token", side_effect=lambda role: {
                    "requester": REQUESTER, "worker": WORKER}[role]), \
                patch("threading.Thread.start"), patch("uvicorn.run") as run:
            server._run_http_server(cls.root, 0, "127.0.0.1")
        cls.client = TestClient(run.call_args.args[0])

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.tmp.cleanup()

    def setUp(self):
        self.data = tempfile.TemporaryDirectory(dir=self.root)
        self.paths = ProjectPaths("Game", Path(self.data.name))
        self.resolve = patch("master.context_search.paths.resolve_mounted_only", side_effect=self.mounted)
        self.resolve.start()
        self.log = patch.object(server, "_tq_log")
        self.log.start()

    def tearDown(self):
        self.log.stop()
        self.resolve.stop()
        self.data.cleanup()

    def mounted(self, project):
        if project in ("", "Game"):
            return self.paths
        raise ConfigError("다른 프로젝트는 마운트되지 않았다")

    def post(self, route, payload, token=REQUESTER):
        headers = {"Authorization": "Bearer " + token} if token else {}
        return self.client.post(route, json=payload, headers=headers)

    def package(self, domain="D"):
        root = self.paths.ontology / "domains" / domain
        item = root / "L1/objects/Obj.yaml"
        item.parent.mkdir(parents=True)
        yaml_io.write(item, {"name": "Obj", "layer": 1, "summary": "old"})
        yaml_io.write(root / "domain.yaml", {"domain": domain, "objects": ["L1/objects/Obj.yaml"]})
        return item

    def test_authentication_and_exact_requester_scope(self):
        for route in ROUTES:
            self.assertEqual(self.post(route, {}, token="").status_code, 401)
            self.assertEqual(self.post(route, {}, token=WORKER).status_code, 403)
            # 시소러스는 기존 prefix scope를 유지하고, 신규 관리 경로만 exact이다.
            self.assertEqual(self.post(route + "/other", {}).status_code,
                             404 if route == ROUTES[9] else 403)
            with patch("master.task_queue.ontology_proxy.process") as process, \
                    patch("master.projects.logic.list_workshops") as shops, \
                    patch("master.projects.workshop_check.check_project_workshops") as clean:
                # 기존 GET /works prefix는 /workshops에도 일치하지만 POST 코어는 실행되지 않는다.
                self.assertEqual(self.client.get(route, headers={
                    "Authorization": "Bearer " + REQUESTER}).status_code,
                    405 if route in ROUTES[7:9] else 403)
                process.assert_not_called()
                shops.assert_not_called()
                clean.assert_not_called()

    def test_all_routes_require_project_and_reject_wrong_project(self):
        payloads = [dict(name="New"), dict(domain="D", kind="objects", name="Obj", patch={}),
                    dict(domain="D", kind="objects", name="Obj"),
                    dict(domain="D", kind="objects", name="Obj"), {}, {}, {}, {}, {},
                    {"terms": ["용어"]}, {"domain": "D"}, {"domain": "D"},
                    {"domain": "D", "tag": "tag", "cvar": "cvar"},
                    {"domain": "D", "tag": "tag"}, {"domain": "D"},
                    {"domain": "D"}, {"domain": "D"}, {},
                    {"old": "D", "new": "Other"},
                    {"domain": "D", "old": "Obj", "new": "Other"}]
        self.assertEqual(len(ROUTES), 20)
        self.assertEqual(len(payloads), len(ROUTES))
        with patch("master.task_queue.ontology_proxy.process") as process, \
                patch("master.projects.logic.list_workshops") as shops, \
                patch("master.projects.workshop_check.check_project_workshops") as clean:
            for route, payload in zip(ROUTES, payloads):
                for project, status in (("", "no_project_tag"), ("Other", "not_mounted")):
                    response = self.post(route, dict(payload, project=project))
                    self.assertEqual(response.status_code, 200)
                    self.assertFalse(response.json()["ok"])
                    self.assertEqual(response.json()["status"], status)
            process.assert_not_called()
            shops.assert_not_called()
            clean.assert_not_called()

    def test_actual_create_edit_lock_remove_core(self):
        created = self.post(ROUTES[0], dict(project="Game", name="한글도메인", tags=["태그"]))
        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.json()["ok"])
        self.assertTrue((self.paths.root / "context/_domains/한글도메인.md").is_file())
        duplicate = self.post(ROUTES[0], dict(project="Game", name="한글도메인"))
        self.assertFalse(duplicate.json()["ok"])
        domain = self.paths.ontology / "domains/D"
        item = domain / "L1/objects/Obj.yaml"
        item.parent.mkdir(parents=True)
        yaml_io.write(item, {"name": "Obj", "layer": 1, "summary": "old"})
        yaml_io.write(domain / "manifest.yaml", {"objects": ["L1/objects/Obj.yaml"]})
        payload = dict(project="Game", domain="D", kind="objects", name="Obj")
        edited = self.post(ROUTES[1], dict(payload, patch={"summary": "new", "name": "Other"})).json()
        self.assertTrue(edited["ok"])
        self.assertTrue(edited["locked"])
        self.assertEqual(edited["ignored"], ["name"])
        self.assertEqual(yaml_io.read(item)["summary"], "new")
        locked = self.post(ROUTES[4], dict(project="Game", domain="D")).json()
        self.assertEqual(locked["count"], 1)
        removed = self.post(ROUTES[2], payload).json()
        self.assertFalse(removed["ok"])
        self.assertTrue(item.exists())
        unlocked = self.post(ROUTES[3], dict(payload, locked=False)).json()
        self.assertFalse(unlocked["locked"])
        self.assertTrue(self.post(ROUTES[2], payload).json()["ok"])
        self.assertFalse(item.exists())

    def test_sync_preview_default_and_scan_forward_existing_core(self):
        stat = SimpleNamespace(domain="D", summary="preview", path_fixed=[], missing=[], declared_set=[])
        with patch("master.ontology.sync.sync_domain", return_value=stat) as sync:
            out = self.post(ROUTES[6], dict(project="Game", domain="D")).json()
        self.assertFalse(out["applied"])
        sync.assert_called_once_with(self.paths, "D", apply=False)
        report = SimpleNamespace(summary="scan", total_classes=3, assigned=1, adjacent=[],
                                 isolated=[("Obj", 2)], isolated_total=2, notes=[])
        with patch("master.ontology.unassigned.scan", return_value=report) as scan:
            out = self.post(ROUTES[5], dict(project="Game", sample=2)).json()
        scan.assert_called_once_with(self.paths, sample=2)
        self.assertEqual(out["isolated_sample"], [{"name": "Obj", "methods": 2}])

    def test_workshop_results_and_project_are_preserved(self):
        result = {"project": "Game", "dispatchable": [], "workshops": [{"reason": "SSH 실패"}]}
        for route, target in ((ROUTES[7], "master.projects.logic.list_workshops"),
                              (ROUTES[8], "master.projects.workshop_check.check_project_workshops")):
            with patch(target, return_value=result) as core:
                self.assertEqual(self.post(route, {"project": "Game"}).json(), result)
            core.assert_called_once_with("Game")

    def test_domain_field_and_log_tag_routes_use_existing_core(self):
        item = self.package()
        self.post(ROUTES[0], {"project": "Game", "name": "D"})
        out = self.post(ROUTES[10], {"project": "Game", "domain": "D", "summary": "changed"}).json()
        self.assertEqual(out["status"], "ok")
        self.assertIn("changed", (self.paths.context / "_domains/D.md").read_text(encoding="utf-8"))
        out = self.post(ROUTES[12], {"project": "Game", "domain": "D", "tag": "LogD",
                                     "cvar": "D.Debug", "related_invariants": ["Rule"]}).json()
        self.assertEqual(out["status"], "created")
        out = self.post(ROUTES[11], {"project": "Game", "domain": "D"}).json()
        self.assertEqual(out["entries"][0]["related_invariants"], ["Rule"])
        self.assertEqual(self.post(ROUTES[13], {"project": "Game", "domain": "D",
                                               "tag": "LogD"}).json()["status"], "deleted")
        self.assertEqual(yaml_io.read(item)["summary"], "old")

    def test_staging_edit_lock_discard_and_remove_commit_keep_live_until_commit(self):
        item = self.package()
        payload = dict(project="Game", domain="D", kind="objects", name="Obj")
        self.assertEqual(self.post(ROUTES[14], {"project": "Game", "domain": "D"}).json()["status"], "started")
        self.assertEqual(len(self.post(ROUTES[17], {"project": "Game"}).json()["sessions"]), 1)
        edited = self.post(ROUTES[1], dict(payload, patch={"summary": "stage"})).json()
        self.assertTrue(edited["staging"])
        self.assertEqual(yaml_io.read(item)["summary"], "old")
        locked = self.post(ROUTES[4], {"project": "Game", "domain": "D"}).json()
        self.assertEqual(locked["count"], 1)
        self.assertTrue(locked["items"][0]["staging"])
        unlocked = self.post(ROUTES[3], dict(payload, locked=False)).json()
        self.assertTrue(unlocked["staging"])
        self.assertNotIn("verified_by_user", yaml_io.read(item))
        self.assertEqual(self.post(ROUTES[16], {"project": "Game", "domain": "D"}).json()["status"], "discarded")
        self.assertEqual(yaml_io.read(item)["summary"], "old")
        self.post(ROUTES[14], {"project": "Game", "domain": "D"})
        self.post(ROUTES[1], dict(payload, patch={"summary": "committed"}))
        with patch("master.ontology.staging.default_sync", return_value="index once") as index:
            self.assertEqual(self.post(ROUTES[15], {"project": "Game", "domain": "D"}).json()["status"], "committed")
        index.assert_called_once_with(self.paths)
        self.assertEqual(yaml_io.read(item)["summary"], "committed")
        self.post(ROUTES[14], {"project": "Game", "domain": "D"})
        removed = self.post(ROUTES[2], dict(payload, force=True)).json()
        self.assertTrue(removed["staging"])
        self.assertTrue(removed["ok"])
        self.assertTrue(item.exists())
        with patch("master.ontology.staging.default_sync", return_value="index once"):
            self.post(ROUTES[15], {"project": "Game", "domain": "D"})
        self.assertFalse(item.exists())
        self.assertEqual(yaml_io.read(item.parents[2] / "domain.yaml")["objects"], [])

    def test_active_session_blocks_live_writers_and_alias(self):
        self.package()
        self.post(ROUTES[14], {"project": "Game", "domain": "D"})
        blocked = [(ROUTES[10], {"domain": "D", "summary": "changed"}),
                   (ROUTES[12], {"domain": "D", "tag": "T", "cvar": "C"}),
                   (ROUTES[13], {"domain": "D", "tag": "T"}),
                   (ROUTES[18], {"old": "D", "new": "Other", "apply": True}),
                   (ROUTES[19], {"domain": "D", "old": "Obj", "new": "Other", "apply": True}),
                   (ROUTES[6], {"domain": "D", "apply": True})]
        for route, payload in blocked:
            out = self.post(route, dict(payload, project="Game")).json()
            self.assertFalse(out["ok"], (route, out))
        with patch("master.context_search.thesaurus.register") as core:
            alias = self.post("/api/v1/thesaurus/alias", {"project": "Game", "class_name": "Obj",
                                                        "term": "별칭"}).json()
        self.assertEqual(alias["status"], "editing_session_active")
        core.assert_not_called()

    def test_rename_preview_and_server_replanned_apply(self):
        item = self.package()
        payload = {"project": "Game", "domain": "D", "old": "Obj", "new": "NewObj"}
        planned = self.post(ROUTES[19], payload).json()
        self.assertTrue(planned["ok"])
        self.assertFalse(planned["applied"])
        self.assertTrue(item.exists())
        self.assertEqual(self.post(ROUTES[19], dict(payload, plan=planned)).status_code, 422)
        applied = self.post(ROUTES[19], dict(payload, apply=True)).json()
        self.assertTrue(applied["applied"])
        self.assertTrue(item.with_name("NewObj.yaml").exists())
        payload = {"project": "Game", "old": "D", "new": "Renamed"}
        self.assertFalse(self.post(ROUTES[18], payload).json()["applied"])
        self.assertTrue(self.post(ROUTES[18], dict(payload, apply=True)).json()["applied"])
        self.assertTrue((self.paths.ontology / "domains/Renamed/L1/objects/NewObj.yaml").exists())

    def test_resolve_preserves_candidates_and_survives_missing_index(self):
        from master.context_search.thesaurus import Candidate, Resolution, Unresolved
        resolved = Resolution(known={"등록": "KnownClass"}, unresolved=[
            Unresolved("미등록", [Candidate("CandidateClass", "그래프 근거", "Source/Candidate.h")])])
        with patch("master.context_search.search.ContextSearch", side_effect=OSError("색인 없음")), \
                patch("master.context_search.thesaurus.resolve", return_value=resolved) as core:
            response = self.post(ROUTES[9], {"project": "Game", "terms": ["등록", "미등록"]})
        self.assertEqual(response.status_code, 200)
        core.assert_called_once_with(self.paths, ["등록", "미등록"], searcher=None)
        out = response.json()
        self.assertEqual(out["known"], {"등록": "KnownClass"})
        self.assertEqual(out["expansion"], ["KnownClass"])
        self.assertTrue(out["needs_user"])
        self.assertEqual(out["unresolved"][0]["question"], resolved.unresolved[0].question)
        self.assertEqual(out["unresolved"][0]["candidates"], [{
            "class": "CandidateClass", "why": "그래프 근거", "file": "Source/Candidate.h"}])

    def test_create_uses_core_normalized_name_for_boundary(self):
        seed = self.paths.root / "context/_domains"
        seed.mkdir(parents=True)
        outside = self.root / "missing-target.md"
        (seed / "Foo.md").symlink_to(outside)
        with patch("master.ontology.create.create") as core:
            out = self.post(ROUTES[0], {"project": "Game", "name": " Foo "}).json()
            self.assertFalse(out["ok"])
            core.assert_not_called()

        self.assertFalse(outside.exists())
        (seed / "Foo.md").unlink()
        created = self.post(ROUTES[0], {"project": "Game", "name": " Foo "}).json()
        self.assertTrue(created["ok"])
        self.assertEqual(created["domain"], "Foo")
        parent_file = self.root / "parent.md"
        parent_file.write_text("parent", encoding="utf-8")
        (seed / "Parent.md").symlink_to(parent_file)
        with patch("master.ontology.create.create") as core:
            out = self.post(ROUTES[0], {"project": "Game", "name": "Child", "parent": " Parent "}).json()
            self.assertFalse(out["ok"])
            core.assert_not_called()

    def test_stage_symlink_cannot_escape_for_item_or_locked_reads(self):
        self.package()
        outside = self.root / "foreign-stage"
        outside.mkdir(exist_ok=True)
        (self.paths.ontology / "domains/D.staging").symlink_to(outside, target_is_directory=True)
        with patch("master.ontology.edit.locked_items") as read, \
                patch("master.ontology.edit.edit") as write:
            out = self.post(ROUTES[4], {"project": "Game", "domain": "D"}).json()
            self.assertFalse(out["ok"])
            out = self.post(ROUTES[1], {"project": "Game", "domain": " D ", "kind": "objects",
                                      "name": "Obj", "patch": {}}).json()
            self.assertFalse(out["ok"])
            read.assert_not_called()
            write.assert_not_called()

    def test_invalid_payload_and_path_escape_do_not_mutate(self):
        payload = dict(project="Game", domain="D", kind="objects", name="Obj")
        for extra in ({"force": "false"}, {"unexpected": 1}):
            self.assertEqual(self.post(ROUTES[2], dict(payload, **extra)).status_code, 422)
        for domain in ("..", ".", "../other", "/tmp", "D\\other"):
            with patch("master.ontology.edit.remove") as core:
                out = self.post(ROUTES[2], dict(payload, domain=domain)).json()
                self.assertFalse(out["ok"])
                core.assert_not_called()
        outside = self.root / "outside"
        outside.mkdir(exist_ok=True)
        domains = self.paths.ontology / "domains"
        domains.mkdir(parents=True)
        (domains / "D").symlink_to(outside, target_is_directory=True)
        with patch("master.ontology.edit.remove") as core:
            self.assertFalse(self.post(ROUTES[2], payload).json()["ok"])
            core.assert_not_called()


if __name__ == "__main__":
    unittest.main()
