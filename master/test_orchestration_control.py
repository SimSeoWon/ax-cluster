"""요청자 인증 → 제어 라우트 → 상태 → 웹 표시. 운영 파일·네트워크를 사용하지 않는다."""
import asyncio
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from master.work import conductor as C
from master.work import conductor_auth as A
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

    def windows_readiness(self, xml=None, *, xml_rc=0, identity=None, reader=None, mode='codex'):
        class Reg:
            active = 'NS'
        facts = B.HostFacts(host='192.168.0.2', user='janus', path=r'E:\trunk\NS',
                            driven='ssh', role='worker', os='windows',
                            home=r'C:\Users\janus', codex='codex-cli 0.159.3',
                            claude='2.1.0 (Claude Code)', checkout_ok=True)
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
                mode, registry=Reg(), prober=lambda *a: facts,
                reader=reader or (lambda *_a: 'delivered file body'), shell_probe=shell,
                **({'auth_checker': lambda *a, **k: {'ok': True}} if mode == 'claude' else {}))
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

    def test_claude_readiness_on_windows_checks_launcher_registration(self):
        # `#832` — Windows claude 도 세션 1 런처로 파견된다: 등록이 없으면 준비 실패
        got, calls = self.windows_readiness(mode='claude')
        self.assertTrue(got['ok'], got)
        self.assertEqual(calls[:1], ['schtasks /query /tn "AxConductor_NS" /xml'])
        got, _ = self.windows_readiness('ERROR: The system cannot find the file specified.',
                                        xml_rc=1, mode='claude')
        self.assertFalse(got['ok'])
        got, _ = self.windows_readiness(self.launcher_xml().replace('InteractiveToken', 'S4U'),
                                        mode='claude')
        self.assertFalse(got['ok'])

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

    def test_record_antigravity_and_alias(self):
        # 1. antigravity 정본 기록
        C.record_master('antigravity', '테스트 인수')
        rec = C.master_record()
        self.assertEqual(rec['agent'], 'antigravity')
        self.assertEqual(rec['why'], '테스트 인수')
        html = section()
        self.assertIn('마스터 담당: Antigravity', html)

        # 2. agy 별칭 전달 시 antigravity 정규화 저장
        status, data = self.request('POST', '/control/master-conductor', {'agent': 'agy', 'why': '별칭 인수'})
        self.assertEqual(status, 200)
        self.assertEqual(data['master']['agent'], 'antigravity')
        self.assertEqual(C.master_record()['agent'], 'antigravity')

        # 3. 잘못된 agent 거절
        with self.assertRaises(ValueError):
            C.record_master('unknown_agent', '사유')
        status, err = self.request('POST', '/control/master-conductor', {'agent': 'unknown_agent', 'why': '사유'})
        self.assertEqual(status, 400)

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

class ClaudeAuthTests(unittest.TestCase):
    def setUp(self):
        self.facts = B.HostFacts(host='auth-test-worker', user='sim', path='/work/a project',
                                 home='/home/sim', os='linux', driven='ssh', role='worker',
                                 claude='2.1.222', checkout_ok=True)
        self.raw = ''
        self.calls = []
        self.writes = []
        self.response = (0, '{"loggedIn": true, "email": "secret@example.com", "token": "secret-token"}')
        A._revoked.discard(A._key(self.facts))
        self.addCleanup(lambda: A._revoked.discard(A._key(self.facts)))

    def read(self, facts, path):
        self.assertEqual(path, A.cache_path(facts))
        return self.raw

    def write(self, facts, rel, text, *, base):
        self.assertEqual(rel, A.CACHE_REL)
        self.assertEqual(base, 'home')
        self.writes.append(text)
        self.raw = text

    def shell(self, host, user, command, **kwargs):
        self.calls.append(command)
        self.assertEqual(kwargs, {'timeout': 30})
        return self.response

    def check(self, stamp=100000, **kwargs):
        return A.check_claude_auth(self.facts, reader=self.read, writer=self.write,
                                   shell_probe=self.shell, now=stamp, **kwargs)

    def test_missing_record_and_ttl_boundary(self):
        got = self.check()
        self.assertTrue(got['ok'])
        self.assertFalse(got['cached'])
        self.assertTrue(self.check(100000)['cached'])
        self.assertTrue(self.check(100000 + A.TTL - 1)['cached'])
        self.assertFalse(self.check(100000 + A.TTL)['cached'])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0], "cd '/work/a project' && claude auth status 2>&1")
        self.assertNotIn('secret', ''.join(self.writes))

    def test_bad_future_or_wrong_worker_records_recheck(self):
        self.check()
        good = json.loads(self.raw)
        variants = ['broken', '[]', json.dumps({**good, 'checked_at': 100001}),
                    json.dumps({**good, 'checked_at': float('nan')}),
                    json.dumps({**good, 'checked_at': True}),
                    json.dumps({**good, 'user': 'other'}),
                    json.dumps({**good, 'host': 'other'}),
                    json.dumps({**good, 'ok': 'true'}),
                    json.dumps({**good, 'schema': 2})]
        for raw in variants:
            with self.subTest(raw=raw):
                self.raw = raw
                self.assertFalse(self.check()['cached'])

    def test_failures_reuse_only_normalized_reason_and_force_rechecks(self):
        for response, code in [((1, '{"loggedIn":false,"email":"secret"}'), 'auth'),
                               ((0, '{"loggedIn":false}'), 'auth'),
                               ((0, '{"loggedIn":"true"}'), 'json'),
                               ((0, 'secret token non-json'), 'json'),
                               ((1, 'secret CLI error'), 'exit')]:
            with self.subTest(code=code, response=response):
                self.response = response
                got = self.check(force=True)
                self.assertFalse(got['ok'])
                self.assertEqual(got['failure_type'], code)
                self.assertTrue(self.check()['cached'])
                self.assertNotIn('secret', self.raw + got['reason'])
        self.response = (0, '{"loggedIn":true}')
        self.assertTrue(self.check(force=True)['ok'])

    def test_probe_exception_does_not_expose_error(self):
        def shell(*args, **kwargs):
            raise TimeoutError('secret token')
        got = A.check_claude_auth(self.facts, reader=self.read, writer=self.write,
                                   shell_probe=shell, now=100000)
        self.assertEqual(got['failure_type'], 'probe')
        self.assertNotIn('secret', self.raw + got['reason'])

    def test_remote_read_or_write_failure_is_fail_closed(self):
        def fail(*args, **kwargs):
            raise OSError('secret')
        got = A.check_claude_auth(self.facts, reader=fail, writer=self.write,
                                   shell_probe=self.shell, now=100000)
        self.assertFalse(got['ok'])
        self.assertEqual(self.calls, [])
        self.check()
        got = A.invalidate_claude_auth(self.facts, writer=fail, now=100000)
        self.assertEqual(got['failure_type'], 'storage')
        self.assertNotIn('secret', got['reason'])
        # A failed invalidation write must not reuse the old healthy remote record.
        self.response = (1, '{"loggedIn":false}')
        self.assertFalse(self.check()['ok'])
        self.assertEqual(len(self.calls), 2)

    def test_runtime_invalidation_and_force_after_login(self):
        self.check()
        A.invalidate_claude_auth(self.facts, writer=self.write, now=100001)
        got = self.check(100002)
        self.assertFalse(got['ok'])
        self.assertTrue(got['cached'])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.check(100002, force=True)['ok'])

    def test_windows_path_and_command(self):
        self.facts.os = 'windows'
        self.facts.home = r'C:\Users\sim'
        self.facts.path = r'C:\trunk\A Project'
        got = self.check()
        self.assertTrue(got['ok'])
        self.assertEqual(A.cache_path(self.facts), r'C:\Users\sim\.cache\ax-dispatch\claude-auth.json')
        self.assertEqual(self.calls[0], 'cd /d "C:\\trunk\\A Project" && claude auth status 2>&1')

    def test_concurrent_first_commands_share_one_probe(self):
        barrier = threading.Barrier(4)
        results = []
        def worker():
            barrier.wait()
            results.append(self.check())
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(results), 4)
        self.assertTrue(all(result['ok'] for result in results))
        self.assertEqual(len(self.calls), 1)

    def test_readiness_reports_auth_failure_without_changing_mode_policy(self):
        class Reg:
            active = 'AXCluster'
        with patch.object(B, 'workshops', return_value=[
                (self.facts.host, self.facts.user, self.facts.path, 'ssh', 'worker', '')]):
            got = REAL_WORKER_MODE_READINESS('claude', registry=Reg(),
                prober=lambda *args: self.facts, reader=lambda *args: 'skill',
                auth_checker=lambda *args, **kwargs: {'ok': False, 'reason': A.AUTH_FAILED})
        self.assertFalse(got['ok'])
        self.assertIn(A.AUTH_FAILED, got['hosts'][0]['problems'])


if __name__=='__main__': unittest.main()
