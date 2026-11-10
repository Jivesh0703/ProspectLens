"""Regression checks for relevance, routing, Vercel, and reviewed CRM writes."""
import json
import os
import unittest
from unittest.mock import patch

import app
import salesforce
import server

REQUEST={'url':'https://example.com/','product':'We help finance teams reconcile subscription payments.','criteria':['Subscription pricing']}
SETTINGS={'VERCEL':'1','VERCEL_URL':'prospectlens-preview.vercel.app','VERCEL_PROJECT_PRODUCTION_URL':'prospectlens.vercel.app','GEMINI_API_KEY':'test-key','SESSION_SECRET':'test-session-secret-at-least-32-characters','SALESFORCE_CLIENT_ID':'test-client','SALESFORCE_CLIENT_SECRET':'test-secret'}


class ExtensionTests(unittest.TestCase):
    def web(self):
        web=server.create_app(SETTINGS,research_runner=lambda data:{'status':'Review draft'})
        web.config['TESTING']=True
        return web

    def test_evidence_relevance_matrix(self):
        # Synthetic labeled quotes evaluate guards, not live model accuracy.
        cases=[
            ('Subscription pricing','Monthly subscriptions renew automatically.',True),
            ('Subscription pricing','Cloud software billed monthly or annually.',True),
            ('Subscription pricing','Our annual company picnic welcomes customer teams.',False),
            ('Subscription pricing','Read our monthly product newsletter.',False),
            ('Subscription pricing','Visit our pricing page to learn more.',False),
            ('International customers','We serve customers in 100 countries.',True),
            ('International customers','Our offices are located around the world.',False),
            ('B2B software company','Our cloud software helps enterprise teams.',True),
            ('B2B software company','Give your teams confidence to collaborate.',False),
            ('B2B software company','Our new website is coming soon.',False),
        ]
        for criterion,quote,expected in cases:
            with self.subTest(quote=quote):
                self.assertEqual(app.direct_support(criterion,[quote]),expected)

    def test_renewal_evidence_does_not_establish_reconciliation_pain(self):
        research=app.Research(REQUEST)
        research.evidence=[{'id':'E1','quote':'Monthly subscriptions renew automatically.','source_url':REQUEST['url'],'retrieved_at':'2026-11-09'}]
        research.finish([{'criterion':'Subscription pricing','evidence_ids':['E1']}],'How does your team struggle with reconciliation?','Finance leader',[])
        result=research.result()
        self.assertIn('If so,',result['hypothesis'])
        self.assertNotIn('struggle',result['outreach_draft'])

    def test_routing_uses_next_model_and_rebuilds_context(self):
        research=app.Research(REQUEST)
        research.model_requests=1
        calls=[]
        def provider(url,body,*args,**kwargs):
            calls.append((url,body))
            if len(calls)==1:
                error=app.InputError('model unavailable');error.status_code=404;raise error
            return {'ok':True}
        with patch.dict(os.environ,{'GEMINI_MODEL':'primary','GEMINI_FALLBACK_MODELS':'secondary'}):
            routed=app.routed_transport(research,provider)
            response=routed('',{'contents':[{'role':'model','parts':[{'thoughtSignature':'old'}]}]},timeout=30)
        self.assertTrue(response['ok'])
        self.assertEqual(research.model_requests,2)
        self.assertIn('/secondary:',calls[1][0])
        self.assertNotIn('thoughtSignature',json.dumps(calls[1][1]))
        self.assertEqual(research.models_used,['primary','secondary'])

    def test_final_fallback_preserves_validation_feedback_and_forces_completion(self):
        research=app.Research(REQUEST)
        research.model_requests=2
        research.event('complete_research',{},'error','Select supplied snippet IDs.')
        calls=[]
        def provider(url,body,*args,**kwargs):
            calls.append(body)
            if len(calls)==1:
                error=app.InputError('Unavailable');error.status_code=404;raise error
            return {'ok':True}
        body={'contents':[], 'tools':[{'functionDeclarations':[{'name':'research_pages'},{'name':'complete_research'}]}]}
        with patch.dict(os.environ,{'GEMINI_MODEL':'primary','GEMINI_FALLBACK_MODELS':'secondary'}):
            app.routed_transport(research,provider)('',body)
        self.assertEqual(research.model_requests,3)
        final=calls[-1]
        self.assertEqual(final['toolConfig']['functionCallingConfig']['allowedFunctionNames'],['complete_research'])
        self.assertEqual([tool['name'] for tool in final['tools'][0]['functionDeclarations']],['complete_research'])
        context=json.loads(final['contents'][0]['parts'][0]['text'])
        self.assertEqual(context['validation_feedback'],['Select supplied snippet IDs.'])

    def test_routing_preserves_budget_and_stops_on_key_error(self):
        for status,initial,expected in [(429,1,3),(401,1,1),(404,3,1)]:
            with self.subTest(status=status,initial=initial):
                research=app.Research(REQUEST);research.model_requests=initial
                error=app.InputError('provider failure');error.status_code=status
                with patch.dict(os.environ,{'GEMINI_MODEL':'one','GEMINI_FALLBACK_MODELS':'two,three'}), patch('app.post_json',side_effect=error) as provider:
                    with self.assertRaises(app.InputError):
                        app.routed_transport(research,provider)('',{},timeout=20)
                self.assertEqual(provider.call_count,expected)
                self.assertLessEqual(research.model_requests,3)

    def test_vercel_preview_production_domains_and_cross_origin(self):
        client=self.web().test_client()
        for hostname in ('prospectlens-preview.vercel.app','prospectlens.vercel.app'):
            response=client.post('/api/research',json=REQUEST,base_url='https://'+hostname,headers={'Origin':'https://'+hostname})
            self.assertEqual(response.status_code,200)
        response=client.post('/api/research',json=REQUEST,base_url='https://prospectlens.vercel.app',headers={'Origin':'https://evil.example'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(client.get('/api/health',base_url='https://evil.example').status_code,400)

    def test_salesforce_oauth_state_and_token(self):
        client=self.web().test_client()
        response=client.get('/api/salesforce/connect',base_url='https://prospectlens.vercel.app')
        self.assertEqual(response.status_code,302)
        self.assertIn('code_challenge=',response.location)
        with client.session_transaction(base_url='https://prospectlens.vercel.app') as session:
            state=session['sf_oauth']['state']
        with patch('salesforce.salesforce_request',return_value={'access_token':'test-token','instance_url':'https://org.my.salesforce.com'}):
            response=client.get('/api/salesforce/callback',query_string={'state':state,'code':'test-code'},base_url='https://prospectlens.vercel.app')
        self.assertEqual(response.status_code,302)
        self.assertNotIn('test-token',response.location)
        self.assertTrue(client.get('/api/salesforce/status',base_url='https://prospectlens.vercel.app').json['connected'])
        self.assertEqual(client.get('/api/salesforce/callback?state=invalid&code=test',base_url='https://prospectlens.vercel.app').status_code,400)

    def test_reviewed_task_creation_and_permissions(self):
        client=self.web().test_client()
        brief={'account':'example.com','hypothesis':'Is reconciliation relevant?','outreach_draft':'A draft for review.','evidence':[{'id':'E1','quote':'Monthly subscriptions.','source_url':'https://example.com/pricing'}]}
        data={'reviewed':True,'account_id':'001000000000001','brief':brief}
        args={'base_url':'https://prospectlens.vercel.app','headers':{'Origin':'https://prospectlens.vercel.app'}}
        self.assertEqual(client.post('/api/salesforce/save',json=data,**args).status_code,401)
        with client.session_transaction(base_url='https://prospectlens.vercel.app') as session:
            session['sf_token']='test-token';session['sf_instance']='https://org.my.salesforce.com'
        with patch('salesforce.salesforce_request',return_value={'success':True,'id':'00T000000000001'}) as provider:
            self.assertEqual(client.post('/api/salesforce/save',json={**data,'reviewed':False},**args).status_code,400)
            provider.assert_not_called()
            response=client.post('/api/salesforce/save',json=data,**args)
            self.assertEqual(response.status_code,201)
            payload=provider.call_args.args[1]
            self.assertEqual(payload['WhatId'],data['account_id'])
            self.assertIn(brief['hypothesis'],payload['Description'])
            self.assertIn('https://example.com/pricing',payload['Description'])
            self.assertIn(brief['outreach_draft'],payload['Description'])
        self.assertEqual(client.post('/api/salesforce/save',json=data,base_url=args['base_url'],headers={'Origin':'https://evil.example'}).status_code,403)

    def test_uncertain_salesforce_outcome_is_not_retried(self):
        client=self.web().test_client()
        with client.session_transaction(base_url='https://prospectlens.vercel.app') as session:
            session['sf_token']='test-token';session['sf_instance']='https://org.my.salesforce.com'
        data={'reviewed':True,'account_id':'001000000000001','brief':{'account':'example.com','hypothesis':'Relevant?','outreach_draft':'Draft','evidence':[{'id':'E1','quote':'Monthly subscriptions','source_url':'https://example.com'}]}}
        with patch('salesforce.salesforce_request',side_effect=TimeoutError()) as provider:
            response=client.post('/api/salesforce/save',json=data,base_url='https://prospectlens.vercel.app',headers={'Origin':'https://prospectlens.vercel.app'})
        self.assertEqual(response.status_code,502)
        self.assertIn('uncertain',response.json['error'])
        self.assertEqual(provider.call_count,1)

    def test_account_search_auth_escaping_and_response(self):
        from urllib.parse import parse_qs, urlsplit
        client=self.web().test_client()
        base='https://prospectlens.vercel.app'
        self.assertEqual(client.get('/api/salesforce/accounts?q=Example',base_url=base).status_code,401)
        with client.session_transaction(base_url=base) as session:
            session['sf_token']='test-token';session['sf_instance']='https://org.my.salesforce.com'
        record={'Id':'001000000000001','Name':"O'Reilly Demo",'Website':'https://example.com','attributes':{'secret':'excluded'}}
        with patch('salesforce.salesforce_request',return_value={'records':[record]}) as provider:
            response=client.get('/api/salesforce/accounts',query_string={'q':"O'Reilly_%"},base_url=base)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['accounts'],[{'id':record['Id'],'name':record['Name'],'website':record['Website']}])
        self.assertEqual(response.json['create_url'],'https://org.my.salesforce.com/lightning/o/Account/new')
        query=parse_qs(urlsplit(provider.call_args.args[0]).query)['q'][0]
        self.assertIn("O\\'Reilly\\_\\%",query)
        self.assertTrue(query.endswith('LIMIT 20'))
        self.assertEqual(provider.call_args.kwargs['headers']['Authorization'],'Bearer test-token')

    def test_account_search_rejects_bad_input_and_handles_expired_session(self):
        from urllib.error import HTTPError
        client=self.web().test_client()
        base='https://prospectlens.vercel.app'
        with client.session_transaction(base_url=base) as session:
            session['sf_token']='test-token';session['sf_instance']='https://org.my.salesforce.com'
        with patch('salesforce.salesforce_request') as provider:
            for query in ('','x','x'*121,'bad\ninput'):
                self.assertEqual(client.get('/api/salesforce/accounts',query_string={'q':query},base_url=base).status_code,400)
            self.assertEqual(client.get('/api/salesforce/accounts?q=Example',base_url=base,headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
            provider.assert_not_called()
        with patch('salesforce.salesforce_request',side_effect=HTTPError('https://org.my.salesforce.com',401,'Expired',{},None)):
            self.assertEqual(client.get('/api/salesforce/accounts?q=Example',base_url=base).status_code,401)
        self.assertFalse(client.get('/api/salesforce/status',base_url=base).json['connected'])

    def test_account_search_empty_results_and_service_failure(self):
        client=self.web().test_client()
        base='https://prospectlens.vercel.app'
        with client.session_transaction(base_url=base) as session:
            session['sf_token']='test-token';session['sf_instance']='https://org.my.salesforce.com'
        with patch('salesforce.salesforce_request',return_value={'records':[]}):
            response=client.get('/api/salesforce/accounts?q=Unknown',base_url=base)
        self.assertEqual(response.json['accounts'],[])
        with patch('salesforce.salesforce_request',side_effect=TimeoutError()):
            response=client.get('/api/salesforce/accounts?q=Unknown',base_url=base)
        self.assertEqual(response.status_code,502)
        self.assertNotIn('test-token',response.get_data(as_text=True))


if __name__=='__main__':
    unittest.main()
