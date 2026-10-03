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

    def windows_readiness(self, xml=None, *, xml_rc=0, identity=None, reader=None):
        class Reg:
            active = 'NS'
        facts = B.HostFacts(host='192.168.0.2', user='janus', path=r'E:\trunk\NS',
                            driven='ssh', role='worker', os='windows',
                            home=r'C:\Users\janus', codex='codex-cli 0.159.3',
                            checkout_ok=True)
        calls = []
        def shell(_host, _user, command, **_kwargs):
            calls.append(command)
            if command.startswith('schtasks /query'):
                return xml_rc, self.launcher_xml() if xml is None else xml
            self.assertEqual(command, 'whoami /user /fo csv /nh')
            return 0, ('"DESKTOP\\janus","S-1-5-21-123-1001"'
                       if identity is None else identity)
        with patch.object(B, 'workshops', return_value=[
                ('192.168.0.2', 'janus', r'E:\trunk\NS', 'ssh', 'worker', '')]):
            got = REAL_WORKER_MODE_READINESS(
                'codex', registry=Reg(), prober=lambda *a: facts,
                reader=reader or (lambda *_a: 'delivered file body'), shell_probe=shell)
        return got, calls

    @staticmethod
    def launcher_xml():
        return '''<?xml version="1.0" encoding="UTF-16"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
 <Principals><Principal id="Author"><UserId>DESKTOP\\janus</UserId>
  <LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel>
 </Principal></Principals>
 <Settings><Enabled>true</Enabled></Settings>
 <Actions Context="Author"><Exec>
  <Command>C:\\Users\\janus\\AppData\\Local\\Programs\\Python\\Python310\\pythonw.exe</Command>
  <Arguments>"E:\\trunk\\NS\\.ax\\lib\\axmaster\\clientside\\session1_conductor.py"</Arguments>
 </Exec></Actions>
</Task>'''

    def test_codex_readiness_checks_registered_interactive_launcher(self):
        got, calls = self.windows_readiness()
        self.assertTrue(got['ok'])
        self.assertEqual(calls, ['schtasks /query /tn "AxConductor_NS" /xml',
                                 'whoami /user /fo csv /nh'])
        self.assertIn('별도 실행 검증', got['note'])

    def test_codex_readiness_accepts_registered_sid(self):
        xml = self.launcher_xml().replace('DESKTOP\\janus', 'S-1-5-21-123-1001')
        self.assertTrue(self.windows_readiness(xml)[0]['ok'])

    def test_codex_readiness_accepts_task_scheduler_defaults_and_console_python(self):
        xml = self.launcher_xml().replace('<RunLevel>LeastPrivilege</RunLevel>', '')
        xml = xml.replace('<Enabled>true</Enabled>', '').replace('pythonw.exe', 'python.exe')
        self.assertTrue(self.windows_readiness(xml)[0]['ok'])

    def test_codex_readiness_rejects_invalid_registration(self):
        good = self.launcher_xml()
        variants = [
            ('Session0', good.replace('InteractiveToken', 'S4U'), '로그인 사용자 세션'),
            ('elevated', good.replace('LeastPrivilege', 'HighestAvailable'), 'LIMITED'),
            ('disabled', good.replace('<Enabled>true', '<Enabled>false'), '비활성화'),
            ('account', good.replace('DESKTOP\\janus', 'DESKTOP\\user'), '실행 계정'),
            ('sid', good.replace('DESKTOP\\janus', 'S-1-5-21-123-1002'), '실행 계정'),
            ('context', good.replace('Context="Author"', 'Context="Other"'), '실행 주체'),
            ('python', good.replace('pythonw.exe', 'cmd.exe'), '실행 파일'),
            ('relative-python', good.replace(r'C:\Users\janus\AppData\Local\Programs\Python\Python310\pythonw.exe',
                                             'pythonw.exe'), '실행 파일'),
            ('rooted-python', good.replace('C:\\Users\\janus', '\\Users\\janus'), '실행 파일'),
            ('old-launcher', good.replace('session1_conductor.py', 'worker_daemon.py'), '실행 경로'),
            ('checkout', good.replace('E:\\trunk\\NS\\', 'E:\\trunk\\다른프로젝트\\'), '실행 경로'),
            ('extra-args', good.replace('</Arguments>', ' --command test</Arguments>'), '실행 경로'),
            ('xml', '<broken', 'XML 형식 오류'),
            ('empty', '', 'XML 형식 오류'),
            ('missing-principal', good.replace('<Principal id="Author">', '<Other>').replace('</Principal>', '</Other>'),
             'principal/Exec'),
            ('extra-action', good.replace('</Actions>', '<Exec /></Actions>'), 'principal/Exec'),
        ]
        for label, xml, reason in variants:
            with self.subTest(label=label):
                got, _ = self.windows_readiness(xml)
                self.assertFalse(got['ok'])
                self.assertIn(reason, '\n'.join(got['hosts'][0]['problems']))

    def test_codex_readiness_rejects_invalid_identity(self):
        for identity in ('', '"DESKTOP\\janus"', '"DESKTOP\\janus","S-1-5-21-123-1001","extra"',
                         '"DESKTOP\\janus,"S-1-5-21-123-1001"'):
            with self.subTest(identity=identity):
                got, _ = self.windows_readiness(identity=identity)
                self.assertFalse(got['ok'])
                self.assertIn('실행 계정', '\n'.join(got['hosts'][0]['problems']))

    def test_codex_readiness_accepts_account_case_difference(self):
        xml = self.launcher_xml().replace('DESKTOP\\janus', 'desktop\\JANUS')
        self.assertTrue(self.windows_readiness(xml)[0]['ok'])

    def test_codex_readiness_reports_missing_registration_and_ssh_failure(self):
        for output in ('ERROR: The system cannot find the file specified.', 'SSH connection failed'):
            with self.subTest(output=output):
                got, calls = self.windows_readiness(output, xml_rc=1)
                self.assertFalse(got['ok'])
                self.assertIn(output, got['hosts'][0]['problems'][0])
                self.assertEqual(len(calls), 1)

    def test_codex_readiness_requires_project_skill_and_launcher(self):
        reads = []
        def read(_facts, path):
            reads.append(path)
            return 'skill body' if path.endswith('SKILL.md') else ''
        got, _ = self.windows_readiness(reader=read)
        self.assertFalse(got['ok'])
        self.assertIn(r'E:\trunk\NS\.agents\skills\ax-work\SKILL.md', reads)
        self.assertIn('런처 파일', got['hosts'][0]['problems'][0])
        got, calls = self.windows_readiness(reader=lambda *_args: '')
        self.assertFalse(got['ok'])
        self.assertEqual(calls, [])

    def test_codex_readiness_linux_uses_project_skill_without_windows_query(self):
        class Reg:
            active = 'NS'
        facts = B.HostFacts(host='192.168.0.43', user='sim', path='/home/sim/trunk/NS',
                            driven='ssh', role='worker', os='linux', home='/home/sim',
                            codex='codex-cli 0.154.0', checkout_ok=True)
        reads = []
        def read(_facts, path):
            reads.append(path)
            return 'skill body'
        with patch.object(B, 'workshops', return_value=[
                ('192.168.0.43', 'sim', '/home/sim/trunk/NS', 'ssh', 'worker', '')]):
            got = REAL_WORKER_MODE_READINESS('codex', registry=Reg(),
                prober=lambda *a: facts, reader=read,
                shell_probe=lambda *_a, **_k: self.fail('Linux는 Windows sandbox probe 대상 아님'))
        self.assertTrue(got['ok'])
        self.assertEqual(reads, ['/home/sim/trunk/NS/.agents/skills/ax-work/SKILL.md'])

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
