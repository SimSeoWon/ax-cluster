"""요청자 인증 → 제어 라우트 → 상태 → 웹 표시. 운영 파일·네트워크를 사용하지 않는다."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master.work import conductor as C
from master.client import bundle as B
from master.projects.control_route import ControlApp
from master.auth import BearerAuthMiddleware, REQUESTER_SCOPE, WORKER_SCOPE
from master.webui.orchestration import section
from client.runtime import client_mcp as M

REAL_WORKER_MODE_READINESS = C.worker_mode_readiness

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for obj, field, value in ((C, 'STATE', root/'conductor.json'),
                                  (C.mode, 'STATE', root/'mode.json'),
                                  (C.mode, 'STATE_DIR', root)):
            p = patch.object(obj, field, value); p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {}, clear=True); p.start(); self.addCleanup(p.stop)
        p = patch.object(C, 'worker_mode_readiness',
                         lambda selected: {'ok': True, 'mode': selected, 'hosts': []})
        p.start(); self.addCleanup(p.stop)

    def request(self, method, path, data=None, token='requester'):
        async def fallback(scope, receive, send):
            await send({'type':'http.response.start','status':404,'headers':[]})
            await send({'type':'http.response.body','body':b''})
        app = BearerAuthMiddleware(ControlApp(fallback), 'admin',
              public_prefixes=('/api/v1/',), scoped=(('requester',REQUESTER_SCOPE),('worker',WORKER_SCOPE)))
        result=[]
        async def receive():
            return {'type':'http.request','body':json.dumps(data).encode(), 'more_body':False}
        async def send(event): result.append(event)
        headers=[] if token is None else [(b'authorization',('Bearer '+token).encode())]
        asyncio.run(app({'type':'http','method':method,'path':path,'headers':headers},receive,send))
        return result[0]['status'], json.loads(result[-1]['body'] or b'{}') if result[0]['status']==200 else None

    def test_unauthorized_writes(self):
        for token, expected in ((None,401),('worker',403)):
            status,_=self.request('POST','/control/worker-mode',{'mode':'codex','why':'test'},token)
            self.assertEqual(status,expected)
        self.assertFalse(C.mode.STATE.exists())

    def test_requester_switch_and_environment_precedence(self):
        status,data=self.request('POST','/control/worker-mode',{'mode':'claude','why':'requested'})
        self.assertEqual(status,200); self.assertEqual(data['worker']['mode'],'claude')
        with patch.dict(os.environ, {'AX_WORKER_MODE':'codex'}):
            status,data=self.request('GET','/control/orchestration')
            self.assertEqual(data['worker']['mode'],'codex')
            self.assertEqual(data['worker']['source'],'env')
            self.assertEqual(data['worker']['state']['mode'],'claude')

    def test_invalid_mode_does_not_write(self):
        for payload in ({'mode':'typo','why':'x'}, {'mode':'codex','why':''}, [], {'mode':[],'why':'x'}):
            self.assertEqual(self.request('POST','/control/worker-mode',payload)[0],400)
        self.assertFalse(C.mode.STATE.exists())

    def test_failed_readiness_does_not_change_mode(self):
        with self.assertRaisesRegex(ValueError, '준비되지 않은 워커'):
            C.set_worker('codex', 'test', readiness={
                'ok': False, 'reason': '준비되지 않은 워커: 192.168.0.2'})
        self.assertFalse(C.mode.STATE.exists())

    def test_codex_readiness_checks_real_windows_shell_path(self):
        class Reg:
            active = 'NS'
        facts = B.HostFacts(host='192.168.0.2', user='janus', path=r'E:\\trunk\\NS',
                            driven='ssh', role='worker', os='windows',
                            home=r'C:\\Users\\janus', codex='codex-cli 0.153.4',
                            checkout_ok=True)
        with patch.object(B, 'workshops', return_value=[
                ('192.168.0.2', 'janus', r'E:\\trunk\\NS', 'ssh', 'worker', '')]):
            got = REAL_WORKER_MODE_READINESS(
                'codex', registry=Reg(), prober=lambda *a: facts,
                reader=lambda *_a: 'skill body',
                shell_probe=lambda *_a, **_k: (1, '0xC0000142'))
        self.assertFalse(got['ok'])
        self.assertIn('192.168.0.2', got['reason'])
        self.assertIn('0xC0000142', got['hosts'][0]['problems'][0])

    def test_codex_readiness_passes_only_after_shell_probe(self):
        class Reg:
            active = 'NS'
        facts = B.HostFacts(host='192.168.0.43', user='sim', path='/home/sim/trunk/NS',
                            driven='ssh', role='worker', os='linux', home='/home/sim',
                            codex='codex-cli 0.154.0', checkout_ok=True)
        with patch.object(B, 'workshops', return_value=[
                ('192.168.0.43', 'sim', '/home/sim/trunk/NS', 'ssh', 'worker', '')]):
            got = REAL_WORKER_MODE_READINESS('codex', registry=Reg(),
                prober=lambda *a: facts, reader=lambda *_a: 'skill body',
                shell_probe=lambda *_a, **_k: self.fail('Linux는 Windows sandbox probe 대상 아님'))
        self.assertTrue(got['ok'])

    def test_record_is_distinct_from_worker(self):
        C.set_worker('codex','test')
        status,data=self.request('POST','/control/master-conductor',{'agent':'claude','why':'인수 확인'})
        self.assertEqual(status,200); self.assertEqual(data['master']['agent'],'claude')
        self.assertEqual(C.snapshot()['worker']['mode'],'codex')
        self.assertEqual(C.STATE.stat().st_mode & 0o777,0o600)

    def test_missing_and_broken_record_not_running(self):
        self.assertEqual(C.master_record()['agent'],'unknown')
        C.STATE.write_text('{broken')
        self.assertEqual(C.master_record()['agent'],'unknown')
        self.assertIn('실행 여부는 미확인',section())

    def test_html_escapes_record(self):
        C.record_master('codex','<script>alert(1)</script>')
        html=section()
        self.assertIn('마스터 담당: Codex',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>',html)

    def test_client_routes_all_three_controls(self):
        calls=[]
        def api(*args): calls.append(args); return {'ok':True}
        for tool,method,path in (('get_orchestration','GET','/control/orchestration'),
                                ('set_worker_mode','POST','/control/worker-mode'),
                                ('record_master_conductor','POST','/control/master-conductor')):
            M.dispatch_tool(tool,{'why':'x'},papi=api)
            self.assertEqual(calls[-1][:2],(method,path))
            self.assertIn(tool,[t['name'] for t in M.TOOLS])

    def test_get_cannot_mutate(self):
        self.assertEqual(self.request('GET','/control/worker-mode',token='admin')[0],405)
        self.assertFalse(C.mode.STATE.exists())

if __name__=='__main__': unittest.main()
