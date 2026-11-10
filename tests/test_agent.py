import copy,json,unittest
from src.agent import ROOT,Tools,MockModel,run,basic_draft,validate
from scripts.evaluate import cases
F=json.loads((ROOT/'data/materials.json').read_text());R=json.loads((ROOT/'data/request.json').read_text())
class Tests(unittest.TestCase):
    def test_acceptance_cases(self):
        for name,r,f,failure,status in cases():
            with self.subTest(name=name):self.assertEqual(run(r,f,MockModel(),failure=failure)['status'],status)
    def setup_tools(self):
        t=Tools(R,F);t.search_materials('字幕');t.propose_script(basic_draft(F,F['materials'][0]));return t
    def test_revision_invalidates_checks(self):
        t=self.setup_tools();t.estimate_duration();t.check_rules();d=copy.deepcopy(t.state['draft']);d['scenes'][0]['pause_seconds']=20;t.propose_script(d);self.assertEqual(t.finish()['error'],'checks_required')
    def test_unsupported_numeric_claim(self):
        t=self.setup_tools();t.state['draft']['scenes'][0]['narration']='效率提升80%。';self.assertFalse(t.check_rules()['passed'])
    def test_user_title_is_not_evidence(self):
        t=Tools({**R,'theme':'字幕效率提升50%'},F);t.search_materials('字幕');d=basic_draft(F,F['materials'][0]);d['title']='字幕效率提升50%';t.propose_script(d);self.assertFalse(t.check_rules()['passed'])
    def test_fake_source(self):
        t=self.setup_tools();t.state['draft']['scenes'][0]['source_ids']=['FAKE'];self.assertFalse(t.check_rules()['passed'])
    def test_visual_claim_blocked(self):
        t=self.setup_tools();t.state['draft']['scenes'][0]['visual']='展示效率提升80%';self.assertFalse(t.check_rules()['passed'])
    def test_sum_duration(self):
        t=self.setup_tools();r=t.estimate_duration();self.assertEqual(round(sum(r['scene_seconds']),2),r['total_seconds']);self.assertEqual(r['total_seconds'],28)
    def test_initial_38_revised_28(self):
        _,r,f,fail,_=next(c for c in cases() if c[0]=='overlong');out=run(r,f,MockModel());times=[e['observation']['total_seconds'] for e in out['trace'] if e['action']=='estimate_duration'];self.assertEqual(times,[38,28])
    def test_limits(self):self.assertEqual(run(R,F,MockModel(),max_steps=1)['reason'],'limit_reached')
    def test_bad_target(self):self.assertIsNotNone(validate({**R,'target_seconds':float('nan')}));self.assertIsNotNone(validate({**R,'target_seconds':True}))
    def test_no_false_finish(self):self.assertEqual(Tools(R,F).finish()['error'],'checks_required')
    def test_long_script_cannot_finish(self):
        t=self.setup_tools();t.state['draft']['scenes'][0]['pause_seconds']=30;t.estimate_duration();t.check_rules();self.assertEqual(t.finish()['error'],'validation_failed')
if __name__=='__main__':unittest.main()
