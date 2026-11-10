import argparse,copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.agent import ROOT,run,MockModel
from src.model import LiveModel,ModelError

def cases():
    f=json.loads((ROOT/'data/materials.json').read_text());r=json.loads((ROOT/'data/request.json').read_text())
    long={'title':'字幕功能演示','scenes':[{'visual':'展示字幕功能界面','narration':'支持字幕。','source_ids':['P01'],'pause_seconds':18} for _ in range(2)]}
    bad=copy.deepcopy(long);bad['scenes'][0]['narration']='效率提升80%。'
    changed=copy.deepcopy(f);changed['materials'][0]['facts']=['支持字幕导出']
    return [('normal',r,f,'none','completed'),('missing_input',{k:v for k,v in r.items() if k!='audience'},f,'none','needs_information'),('no_materials',{**r,'theme':'电动汽车续航'},f,'none','needs_information'),('tool_failure',r,f,'search_always','needs_information'),('overlong',{**r,'initial_draft':long},f,'none','completed'),('unsupported_claim',{**r,'initial_draft':bad},f,'none','completed'),('shorter_target',{**r,'target_seconds':10,'initial_draft':long},f,'none','completed'),('impossible_target',{**r,'target_seconds':0.1},f,'none','needs_information'),('estimate_failure',r,f,'estimate_always','needs_information'),('transient_failure',r,f,'estimate_once','completed'),('replaced_material',r,changed,'none','completed')]

def evaluate(mode,output,selected=None):
    suite=[case for case in cases() if not selected or case[0] in selected]
    model=LiveModel() if mode=='live' else MockModel();out=Path(output);out.mkdir(parents=True,exist_ok=True);records=[]
    for name,r,f,failure,status in suite:
        result=run(r,f,model,failure=failure);state=result.get('state',{});checks={'status':result['status']==status}
        if status=='completed':
            duration = result.get('duration') or {}
            rules = state.get('rules') or {}
            scene_seconds = duration.get('scene_seconds') or []
            checks.update(
                duration=duration.get('within_limit') is True,
                rules=rules.get('passed') is True,
                source_ids=result.get('source_ids') == ['P01'],
                scene_sum=bool(scene_seconds) and round(sum(scene_seconds), 2) == duration.get('total_seconds'),
            )
        if name in ('overlong','shorter_target'):
            estimates=[e['observation'] for e in result['trace'] if e['action']=='estimate_duration' and 'total_seconds' in e['observation']]
            checks['observed_overlong']=bool(estimates) and estimates[0]['total_seconds']==38 and not estimates[0]['within_limit']
            checks['rechecked_revision']=len(estimates)>=2 and estimates[-1]['draft_id']!=estimates[0]['draft_id']
        if name=='unsupported_claim':checks['removed_claim']='80%' not in json.dumps(result.get('script'),ensure_ascii=False)
        if name=='replaced_material':checks['updated_fact']='支持字幕导出' in json.dumps(result.get('script'),ensure_ascii=False)
        if status!='completed':checks['not_claimed_success']=result['status']!='completed'
        folder=out/name;folder.mkdir(exist_ok=True)
        for filename,value in [('input.json',r),('materials.json',f),('output.json',result),('assertions.json',checks)]: (folder/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        records.append({'case':name,'passed':all(checks.values()),'checks':checks});print(name,'PASS' if all(checks.values()) else 'FAIL',flush=True)
        if result.get('reason') == 'model_error':
            observation = result['trace'][-1]['observation']
            print(json.dumps(observation, ensure_ascii=False), flush=True)
            if observation.get('error') in {'http_error', 'network_error', 'configuration_error'}:
                break
    summary={'mode':mode,'expected':len(suite),'executed':len(records),'passed':sum(r['passed'] for r in records),'cases':records}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    (out/'REPORT.md').write_text('# '+mode+' 验收\n\n'+f"通过 {summary['passed']}/{summary['expected']}。\n\n"+'\n'.join(f"- {r['case']}: {r['passed']} — [输入]({r['case']}/input.json)、[资料]({r['case']}/materials.json)、[输出与Trace]({r['case']}/output.json)、[断言]({r['case']}/assertions.json)" for r in records)+'\n\nMock不能证明真实模型决策效果。\n')
    return 0 if summary['passed']==summary['expected'] else 2
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['mock','live'],default='mock');p.add_argument('--output',required=True);p.add_argument('--case',action='append',choices=[case[0] for case in cases()]);a=p.parse_args()
    try:sys.exit(evaluate(a.mode,a.output,a.case))
    except ModelError as e:print(json.dumps(e.details,ensure_ascii=False));sys.exit(2)
