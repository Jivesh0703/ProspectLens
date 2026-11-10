"""LLM judge contract and failure-path regression tests, without provider traffic."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import judge
import app

BRIEF={'account':'example.com','product':'We help finance teams reconcile subscription payments.',
       'criteria':['Subscription pricing','International customers'],
       'fit':[{'criterion':'Subscription pricing','evidence_ids':['E1']},{'criterion':'International customers','evidence_ids':[]}],
       'evidence':[{'id':'E1','quote':'Monthly subscriptions renew automatically.','source_url':'https://example.com/pricing'}],
       'hypothesis':'Does your team reconcile subscription payments? If so, is matching invoices a challenge?',
       'outreach_draft':'Your website describes monthly subscriptions. Would a conversation be useful?'}
VERDICT={'fit':[{'criterion':'Subscription pricing','verdict':'supported','evidence_ids':['E1'],'explanation':'Explicit subscription terms.'},
                {'criterion':'International customers','verdict':'unknown','evidence_ids':[],'explanation':'No cited evidence establishes customer geography.'}],
         'outreach':{'verdict':'grounded','explanation':'Only cites the available subscription fact.'},
         'discovery':{'verdict':'appropriate','explanation':'Asks a conditional question instead of assuming pain.'},
         'unsupported_claims':[]}


def response(verdict):
    return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'functionCall':{'name':'submit_evaluation','args':verdict}}]}}]}


class JudgeTests(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'GEMINI_API_KEY':'test-key','GEMINI_MODEL':'gemini-3.5-flash-lite'})
        env.start();self.addCleanup(env.stop)

    def test_supported_and_missing_evidence_receive_separate_verdicts(self):
        with patch('app.post_json',return_value=response(VERDICT)) as provider:
            report=judge.evaluate(BRIEF)
        self.assertEqual(provider.call_count,1)
        self.assertEqual(report['summary']['fit_verdicts'],{'supported':1,'partial':0,'unsupported':0,'unknown':1})
        self.assertFalse(report['summary']['review_required'])
        self.assertEqual(report['rubric_version'],'1.2')
        self.assertEqual(len(report['input_sha256']),64)
        payload=provider.call_args.args[1]
        self.assertEqual(payload['generationConfig']['temperature'],0)
        self.assertIn('untrusted',payload['systemInstruction']['parts'][0]['text'])
        self.assertNotIn('test-key',json.dumps(report))

    def test_weak_evidence_and_unsupported_pain_are_flagged(self):
        brief=copy.deepcopy(BRIEF)
        brief['evidence'][0]['quote']='Our monthly team picnic is popular.'
        brief['outreach_draft']='Your finance team struggles with payment reconciliation.'
        verdict=copy.deepcopy(VERDICT)
        verdict['fit'][0].update(verdict='unsupported',explanation='Monthly event language does not establish subscription billing.')
        verdict['outreach'].update(verdict='needs_review',explanation='Invents reconciliation pain.')
        verdict['unsupported_claims']=[{'section':'outreach','claim':brief['outreach_draft'],'explanation':'No source establishes internal workflow pain.'}]
        report=judge.evaluate(brief,transport=lambda *args,**kwargs:response(verdict))
        self.assertTrue(report['summary']['review_required'])
        self.assertEqual(report['summary']['fit_verdicts']['unsupported'],1)

    def test_withheld_outreach_is_acceptable(self):
        brief=copy.deepcopy(BRIEF);brief['outreach_draft']=None
        verdict=copy.deepcopy(VERDICT);verdict['outreach'].update(verdict='withheld')
        report=judge.evaluate(brief,transport=lambda *args,**kwargs:response(verdict))
        self.assertFalse(report['summary']['review_required'])

    def test_invalid_input_never_calls_provider(self):
        for change in ({'service_error':'Unavailable'},{'criteria':['Duplicate','Duplicate']},{'evidence':[]},{'outreach_draft':42}):
            with self.subTest(change=change),patch('app.post_json') as provider:
                with self.assertRaises(app.InputError):judge.evaluate({**BRIEF,**change})
                provider.assert_not_called()

    def test_judge_cannot_change_criteria_or_invent_citations(self):
        for field,value in [('criterion','Changed criterion'),('evidence_ids',['E999'])]:
            verdict=copy.deepcopy(VERDICT);verdict['fit'][0][field]=value
            with self.subTest(field=field),self.assertRaises(app.InputError):
                judge.evaluate(BRIEF,transport=lambda *args,**kwargs:response(verdict))

    def test_inconclusive_cited_evidence_is_valid_feedback_and_flags_review(self):
        for verdict_name,ids in [('unknown',['E1']),('unknown',[]),('unsupported',[])]:
            verdict=copy.deepcopy(VERDICT)
            verdict['fit'][0].update(verdict=verdict_name,evidence_ids=ids,explanation='The evidence does not establish the full criterion.')
            with self.subTest(verdict=verdict_name,ids=ids):
                report=judge.evaluate(BRIEF,transport=lambda *args,**kwargs:response(verdict))
                self.assertTrue(report['summary']['review_required'])
                self.assertEqual(report['evaluation']['fit'][0]['verdict'],verdict_name)

    def test_positive_judge_verdict_still_requires_evidence(self):
        for verdict_name in ('supported','partial'):
            verdict=copy.deepcopy(VERDICT)
            verdict['fit'][1].update(verdict=verdict_name)
            with self.subTest(verdict=verdict_name),self.assertRaises(app.InputError):
                judge.evaluate(BRIEF,transport=lambda *args,**kwargs:response(verdict))

    def test_unsupported_verdict_on_existing_abstention_does_not_flag_false_disagreement(self):
        verdict=copy.deepcopy(VERDICT)
        verdict['fit'][1].update(verdict='unsupported',explanation='There is no evidence for international customers.')
        report=judge.evaluate(BRIEF,transport=lambda *args,**kwargs:response(verdict))
        self.assertFalse(report['summary']['review_required'])

    def test_judge_claim_must_exist_verbatim_in_the_brief(self):
        verdict=copy.deepcopy(VERDICT)
        verdict['outreach']['verdict']='needs_review'
        verdict['unsupported_claims']=[{'section':'outreach','claim':'Invented sentence','explanation':'Unestablished.'}]
        with self.assertRaises(app.InputError):
            judge.evaluate(BRIEF,transport=lambda *args,**kwargs:response(verdict))

    def test_provider_failure_is_not_a_quality_verdict_and_is_not_retried(self):
        with patch('app.post_json',side_effect=app.ProviderBusyError()) as provider:
            with self.assertRaises(app.InputError):judge.evaluate(BRIEF)
            self.assertEqual(provider.call_count,1)
        for value in ({'candidates':[]},{'candidates':[{'finishReason':'MAX_TOKENS'}]}):
            with self.subTest(value=value),self.assertRaises(app.InputError):
                judge.evaluate(BRIEF,transport=lambda *args,**kwargs:value)

    def test_cli_writes_report_and_protects_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'brief.json';target=Path(directory)/'evaluation.json'
            source.write_text(json.dumps(BRIEF))
            with patch('sys.argv',['evaluate_brief','--input',str(source),'--output',str(target)]),patch('app.load_env'),patch('app.post_json',return_value=response(VERDICT)):
                judge.main()
            self.assertEqual(json.loads(target.read_text())['account'],'example.com')
            self.assertEqual(json.loads(source.read_text()),BRIEF)
            with patch('sys.argv',['evaluate_brief','--input',str(source),'--output',str(source)]),patch('app.post_json') as provider,patch('sys.stderr'):
                with self.assertRaises(SystemExit) as error:judge.main()
                self.assertEqual(error.exception.code,2)
                provider.assert_not_called()

    def test_cli_failure_preserves_existing_report_and_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'brief.json';target=Path(directory)/'evaluation.json'
            source.write_text(json.dumps(BRIEF));target.write_text('previous report')
            with patch('sys.argv',['evaluate_brief','--input',str(source),'--output',str(target)]),patch('app.load_env'),patch('app.post_json',side_effect=app.InputError('Provider unavailable')),patch('sys.stderr'):
                with self.assertRaises(SystemExit):judge.main()
            self.assertEqual(target.read_text(),'previous report')
            self.assertEqual(len(list(Path(directory).iterdir())),2)

    def completed_research(self):
        research=app.Research({'url':'https://example.com','product':BRIEF['product'],'criteria':BRIEF['criteria']})
        research.evidence=[{**copy.deepcopy(BRIEF['evidence'][0]),'retrieved_at':'2026-11-10T00:00:00Z'}]
        research.finish(copy.deepcopy(BRIEF['fit']),BRIEF['hypothesis'],'Finance leader',[])
        research.model_requests=2
        research.models_used=['gemini-3.1-flash-lite']
        return research

    def test_live_run_invokes_judge_and_exports_feedback(self):
        def generate(research,transport):
            prepared=self.completed_research()
            research.evidence=prepared.evidence
            research.finished=prepared.finished
            research.model_requests=2
            research.models_used=prepared.models_used
        with patch('app.run_gemini',side_effect=generate),patch('app.post_json',return_value=response(VERDICT)) as provider:
            result=app.run({'url':'https://example.com','product':BRIEF['product'],'criteria':BRIEF['criteria']},transport=provider)
        self.assertEqual(result['judge_evaluation']['status'],'completed')
        self.assertEqual(result['evaluation_model_requests'],1)
        self.assertEqual(result['total_model_requests'],3)
        self.assertEqual(result['model_requests'],2)
        self.assertIn('## AI quality review',result['markdown'])
        self.assertIn('gemini-3.1-flash-lite',provider.call_args.args[0])
        self.assertLessEqual(provider.call_args.kwargs['timeout'],60)

    def test_judge_outage_preserves_research_and_outreach(self):
        research=self.completed_research()
        original=research.result()
        with patch('app.post_json',side_effect=app.ProviderBusyError()),patch('app.time.sleep'):
            provider=app.post_json
            result=app.attach_evaluation(research,provider)
        self.assertEqual(result['judge_evaluation']['status'],'unavailable')
        self.assertIsNone(result['service_error'])
        self.assertEqual(result['outreach_draft'],original['outreach_draft'])
        self.assertEqual(result['fit'],original['fit'])
        self.assertEqual(result['evaluation_model_requests'],3)
        self.assertEqual(provider.call_count,3)

    def test_live_judge_fails_over_after_503(self):
        research=self.completed_research()
        with patch.dict(os.environ,{'GEMINI_FALLBACK_MODELS':'gemini-3.5-flash-lite'}),patch('app.time.sleep'),patch('app.post_json',side_effect=[app.ProviderBusyError(),response(VERDICT)]) as provider:
            result=app.attach_evaluation(research,provider)
        self.assertEqual(result['judge_evaluation']['status'],'completed')
        self.assertEqual(result['evaluation_model_requests'],2)
        self.assertEqual(result['judge_evaluation']['models_attempted'],['gemini-3.1-flash-lite','gemini-3.5-flash-lite'])
        self.assertIsNone(result['service_error'])

    def test_judge_can_return_to_primary_after_research_used_fallback(self):
        research=self.completed_research()
        with patch.dict(os.environ,{'GEMINI_MODEL':'gemini-3.5-flash-lite','GEMINI_FALLBACK_MODELS':'gemini-3.1-flash-lite'}),patch('app.time.sleep'),patch('app.post_json',side_effect=[app.ProviderBusyError(),response(VERDICT)]) as provider:
            result=app.attach_evaluation(research,provider)
        self.assertEqual(result['judge_evaluation']['models_attempted'],['gemini-3.1-flash-lite','gemini-3.5-flash-lite'])
        self.assertEqual(result['judge_evaluation']['status'],'completed')
        self.assertEqual(provider.call_count,2)

    def test_third_judge_attempt_recovers_within_five_total_requests(self):
        research=self.completed_research()
        with patch('app.time.sleep') as sleep,patch('app.post_json',side_effect=[app.ProviderBusyError(),app.ProviderBusyError(),response(VERDICT)]) as provider:
            result=app.attach_evaluation(research,provider)
        self.assertEqual(result['judge_evaluation']['status'],'completed')
        self.assertEqual(result['total_model_requests'],5)
        self.assertEqual(result['evaluation_model_requests'],3)
        self.assertEqual(provider.call_count,3)
        self.assertEqual(sleep.call_count,2)

    def test_research_repair_leaves_only_two_judge_attempts(self):
        research=self.completed_research();research.model_requests=3
        with patch('app.time.sleep'),patch('app.post_json',side_effect=app.ProviderBusyError()) as provider:
            result=app.attach_evaluation(research,provider)
        self.assertEqual(result['total_model_requests'],5)
        self.assertEqual(provider.call_count,2)

    def test_live_judge_repairs_invalid_response_before_returning_to_ui(self):
        research=self.completed_research()
        invalid=copy.deepcopy(VERDICT)
        invalid['fit'][0]['evidence_ids']=['invented-reference']
        with patch('app.time.sleep'),patch('app.post_json',side_effect=[response(invalid),response(VERDICT)]) as provider:
            result=app.attach_evaluation(research,provider)
        self.assertEqual(result['judge_evaluation']['status'],'completed')
        self.assertEqual(result['evaluation_model_requests'],2)
        self.assertEqual(provider.call_count,2)
        repair=json.loads(provider.call_args.args[1]['contents'][0]['parts'][0]['text'])
        self.assertIn('validation failure',repair['correction_instruction'])
        self.assertIn('subset of the evidence cited',repair['correction_instruction'])
        self.assertEqual(result['judge_evaluation']['evaluation']['outreach']['verdict'],'grounded')

    def test_live_judge_authentication_error_is_not_retried(self):
        research=self.completed_research()
        error=app.InputError('API key rejected');error.status_code=401
        with patch('app.post_json',side_effect=error) as provider:
            result=app.attach_evaluation(research,provider)
        self.assertEqual(result['judge_evaluation']['status'],'unavailable')
        self.assertEqual(provider.call_count,1)

    def test_failed_research_skips_judge(self):
        research=app.Research({'url':'https://example.com','product':BRIEF['product'],'criteria':BRIEF['criteria']})
        research.service_error='Provider unavailable'
        research.fallback('Provider unavailable')
        with patch('app.post_json') as provider:
            result=app.attach_evaluation(research,provider)
        self.assertEqual(result['judge_evaluation']['status'],'skipped')
        self.assertEqual(result['evaluation_model_requests'],0)
        provider.assert_not_called()

    def test_judge_is_skipped_when_workflow_time_is_exhausted(self):
        import time
        research=self.completed_research()
        research.started=time.monotonic()-275
        with patch('app.post_json') as provider:
            result=app.attach_evaluation(research,provider)
        self.assertEqual(result['judge_evaluation']['status'],'unavailable')
        self.assertEqual(result['evaluation_model_requests'],0)
        provider.assert_not_called()


if __name__=='__main__':
    unittest.main()
