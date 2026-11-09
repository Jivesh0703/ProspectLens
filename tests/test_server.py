import copy
import datetime as dt
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import app as core

REQUEST={'url':'https://example.com/','product':'We help finance teams match invoice payments.','criteria':['B2B software company']}
PRODUCTION={'RENDER':'true','APP_ENV':'production','GEMINI_API_KEY':'test-not-a-real-key',
 'RENDER_EXTERNAL_HOSTNAME':'prospectlens.onrender.com',
 'RENDER_EXTERNAL_URL':'https://prospectlens.onrender.com','MAX_DAILY_RESEARCH':'2'}

class ServerTests(unittest.TestCase):
    def make(self,settings=None,runner=None):
        web=server.create_app(settings=copy.deepcopy(PRODUCTION if settings is None else settings),research_runner=runner or (lambda data:{'status':'Review draft','echo_criteria':data['criteria']}))
        web.config['TESTING']=True
        return web
    def post(self,client,**kwargs):
        headers={'Origin':'https://prospectlens.onrender.com','X-Forwarded-Proto':'https',**kwargs.pop('headers',{})}
        return client.post('/api/research',json=kwargs.pop('json',REQUEST),base_url='http://prospectlens.onrender.com',headers=headers,**kwargs)
    def test_health_public_and_does_not_reveal_key_configuration(self):
        response=self.make().test_client().get('/api/health',base_url='http://prospectlens.onrender.com')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json,{'ok':True})
    def test_assets_and_research_are_public_without_login(self):
        client=self.make().test_client()
        for path in ('/','/app.js','/style.css'):
            with client.get(path,base_url='http://prospectlens.onrender.com') as response:
                self.assertEqual(response.status_code,200)
                self.assertNotIn('WWW-Authenticate',response.headers)
        self.assertEqual(self.post(client).status_code,200)
    def test_legacy_auth_configuration_cannot_enable_a_login_gate(self):
        web=self.make({**PRODUCTION,'ACCESS_USERNAME':'reviewer','ACCESS_PASSWORD':'old-test-password'})
        with web.test_client().get('/',base_url='http://prospectlens.onrender.com') as response:
            self.assertEqual(response.status_code,200)
            self.assertNotIn('WWW-Authenticate',response.headers)
    def test_public_assets_served_and_secret_files_not_exposed(self):
        client=self.make().test_client()
        response=client.get('/',base_url='http://prospectlens.onrender.com',headers={})
        self.assertEqual(response.status_code,200)
        self.assertIn(b'ProspectLens',response.data)
        response.close()
        for path in ('/.env','/app.py','/server.py','/../.env'):
            response=client.get(path,base_url='http://prospectlens.onrender.com',headers={})
            self.assertEqual(response.status_code,404)
    def test_render_https_origin_passes_proxy_check(self):
        response=self.post(self.make().test_client())
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['status'],'Review draft')
        self.assertIn('max-age',response.headers['Strict-Transport-Security'])
    def test_cross_origin_and_cross_site_posts_rejected(self):
        client=self.make().test_client()
        self.assertEqual(self.post(client,headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.post(client,headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertEqual(self.post(client,headers={'Origin':'null'}).status_code,403)
    def test_untrusted_host_cannot_use_forwarded_host_to_bypass(self):
        client=self.make().test_client()
        response=client.get('/api/health',base_url='http://evil.example',headers={'X-Forwarded-Host':'prospectlens.onrender.com'})
        self.assertEqual(response.status_code,400)
    def test_daily_limit_bounds_runs_and_health_does_not_consume_it(self):
        web=self.make();client=web.test_client()
        for _ in range(3): client.get('/api/health',base_url='http://prospectlens.onrender.com')
        self.assertEqual(self.post(client).status_code,200)
        self.assertEqual(self.post(client).status_code,200)
        blocked=self.post(client)
        self.assertEqual(blocked.status_code,429)
        self.assertIn('daily',blocked.json['error'])
        self.assertIn('Retry-After',blocked.headers)
        self.assertEqual(web.extensions['research_gate'].used,2)
    def test_daily_limit_resets_at_utc_date_boundary(self):
        web=self.make();gate=web.extensions['research_gate'];gate.used=2;gate.day-=dt.timedelta(days=1)
        self.assertEqual(self.post(web.test_client()).status_code,200)
        self.assertEqual(gate.used,1)
    def test_invalid_input_and_large_body_do_not_consume_research_allowance(self):
        web=self.make();client=web.test_client()
        self.assertEqual(self.post(client,json={}).status_code,400)
        response=client.post('/api/research',data='x'*12001,content_type='application/json',base_url='http://prospectlens.onrender.com',headers={})
        self.assertEqual(response.status_code,413)
        self.assertEqual(web.extensions['research_gate'].used,0)
    def test_wrong_content_type_and_malformed_json_rejected(self):
        client=self.make().test_client()
        headers={}
        self.assertEqual(client.post('/api/research',data='text',base_url='http://prospectlens.onrender.com',headers=headers).status_code,415)
        self.assertEqual(client.post('/api/research',data='{',content_type='application/json',base_url='http://prospectlens.onrender.com',headers=headers).status_code,400)
    def test_only_one_research_runs_while_health_remains_available(self):
        entered=threading.Event();release=threading.Event();results=[]
        def runner(data):
            entered.set();release.wait(5);return {'status':'Review draft'}
        web=self.make(runner=runner)
        worker=threading.Thread(target=lambda:results.append(self.post(web.test_client())))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.post(web.test_client()).status_code,429)
            self.assertEqual(web.test_client().get('/api/health',base_url='http://prospectlens.onrender.com').status_code,200)
        finally:
            release.set();worker.join(3)
        self.assertEqual(results[0].status_code,200)
    def test_runner_error_does_not_leak_details_or_lock_server(self):
        def runner(data): raise RuntimeError('secret internal detail')
        web=self.make(runner=runner)
        with self.assertLogs(web.logger,level='ERROR'):
            response=self.post(web.test_client())
        self.assertEqual(response.status_code,500)
        self.assertNotIn('secret internal detail',response.get_data(as_text=True))
        self.assertTrue(web.extensions['research_gate'].busy.acquire(blocking=False))
        web.extensions['research_gate'].busy.release()
    def test_production_fails_closed_for_missing_secrets(self):
        for changes in ({'GEMINI_API_KEY':''},{'MAX_DAILY_RESEARCH':'0'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.make({**PRODUCTION,**changes})
    def test_local_default_remains_accessible_without_password(self):
        client=self.make({}).test_client()
        with client.get('/') as response:
            self.assertEqual(response.status_code,200)
        response=client.post('/api/research',json=REQUEST,headers={'Origin':'http://localhost'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('Strict-Transport-Security',response.headers)
    def test_waitress_uses_bounded_request_size_and_render_proxy_config(self):
        web=self.make()
        with patch('waitress.serve') as serve:
            server.serve_app(web,'0.0.0.0',10000)
        options=serve.call_args.kwargs
        self.assertEqual(options['port'],10000)
        self.assertEqual(options['threads'],4)
        self.assertEqual(options['max_request_body_size'],12000)
        self.assertFalse(options['clear_untrusted_proxy_headers'])
    def test_render_main_uses_assigned_port_and_public_bind_address(self):
        with patch.dict('os.environ',{**PRODUCTION,'PORT':'12345'},clear=True),patch('app.load_env'),patch('server.create_app') as create,patch('server.serve_app') as serve,patch('sys.argv',['app.py']):
            core.main()
        create.assert_called_once()
        serve.assert_called_once_with(create.return_value,'0.0.0.0',12345)
    def test_research_response_headers_and_custom_domain(self):
        web=self.make({**PRODUCTION,'APP_ORIGIN':'https://accounts.example.com'})
        response=web.test_client().post('/api/research',json=REQUEST,base_url='https://accounts.example.com',headers={'Origin':'https://accounts.example.com'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')

if __name__=='__main__': unittest.main()
