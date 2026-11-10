"""Grounded editable scripts; every revision invalidates duration and rules checks."""
import argparse,copy,hashlib,json,math,re,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def validate(request):
    missing=[k for k in ('theme','audience','platform','target_seconds','style') if k not in request or request[k] is None or request[k]=='']
    if missing:return {'error':'missing_input','missing':missing}
    if any(not isinstance(request[k],str) or not request[k].strip() for k in ('theme','audience','platform','style')):return {'error':'invalid_text_input'}
    if type(request['target_seconds']) not in (int,float) or not math.isfinite(request['target_seconds']) or request['target_seconds']<=0:return {'error':'invalid_target_seconds'}
    return None

class Tools:
    def __init__(self,request,catalog,failure='none'):
        self.request,self.catalog,self.failure=request,catalog,failure;self.failed=False
        self.state={'searches':[],'materials':{},'draft':None,'draft_id':None,'revisions':[],'duration':None,'rules':None,'errors':[]}
        if request.get('initial_draft') is not None:
            result=self.propose_script(request['initial_draft']);self.state['initial_draft_validation']=result
    def call(self,action,args):
        schema={'search_materials':{'query'},'propose_script':{'draft'},'estimate_duration':set(),'check_rules':set(),'finish':set(),'request_information':{'reason'}}
        # The live model sometimes sends the draft directly as the arguments object.
        if action == 'propose_script' and set(args) == {'title', 'scenes'}:
            args = {'draft': args}
        if action not in schema or set(args) != schema[action]:
            return {'error': 'invalid_tool_or_arguments', 'expected_keys': sorted(schema.get(action, []))}
        if action in ('search_materials','request_information') and not isinstance(args[next(iter(args))],str):return {'error':'invalid_arguments'}
        failed=(self.failure=='search_always' and action=='search_materials') or (self.failure=='estimate_once' and action=='estimate_duration' and not self.failed) or (self.failure=='estimate_always' and action=='estimate_duration')
        if failed:
            self.failed=True;err={'error':'tool_failure','tool':action,'retryable':self.failure=='estimate_once'};self.state['errors'].append(err);return err
        return getattr(self,action)(**args)
    def search_materials(self,query):
        found=[m for m in self.catalog['materials'] if any(k.lower() in query.lower() for k in m['keywords'])]
        self.state['searches'].append({'query':query,'ids':[m['id'] for m in found]})
        self.state['materials'].update({m['id']:m for m in found})
        return {'materials':found,'neutral_phrases':self.catalog['neutral_phrases'],'rules':self.catalog['rules'],'seconds_per_character':1/self.catalog['characters_per_second']}
    def propose_script(self,draft):
        if not isinstance(draft,dict) or set(draft)!={'title','scenes'} or not isinstance(draft['title'],str) or not isinstance(draft['scenes'],list) or not 1<=len(draft['scenes'])<=12:return {'error':'invalid_draft'}
        for scene in draft['scenes']:
            if not isinstance(scene,dict) or set(scene)!={'visual','narration','source_ids','pause_seconds'}:return {'error':'invalid_scene_fields'}
            if any(not isinstance(scene[k],str) for k in ('visual','narration')) or not isinstance(scene['source_ids'],list) or any(not isinstance(x,str) for x in scene['source_ids']):return {'error':'invalid_scene_types'}
            if type(scene['pause_seconds']) not in (int,float) or not math.isfinite(scene['pause_seconds']) or not 0<=scene['pause_seconds']<=30:return {'error':'invalid_pause'}
        if len(json.dumps(draft,ensure_ascii=False))>10000:return {'error':'draft_too_large'}
        self.state.update(draft=copy.deepcopy(draft),draft_id=digest(draft),duration=None,rules=None)
        self.state['revisions'].append({'draft_id':self.state['draft_id'],'draft':copy.deepcopy(draft)})
        return {'draft_id':self.state['draft_id'],'stored':True,'checks_invalidated':True,'message':'Draft stored only; run duration and rules checks before finish.'}
    def estimate_duration(self):
        if not self.state['draft']:return {'error':'draft_required'}
        times=[]
        for scene in self.state['draft']['scenes']:
            # Chinese-character equivalent heuristic; punctuation and whitespace do not count.
            count=len(re.findall(r'[\w\u4e00-\u9fff]',scene['narration']))
            times.append(round(count/self.catalog['characters_per_second']+scene['pause_seconds'],2))
        total=round(sum(times),2);result={'draft_id':self.state['draft_id'],'scene_seconds':times,'total_seconds':total,'target_seconds':self.request['target_seconds'],'within_limit':total<=self.request['target_seconds'],'excess_seconds':max(0,round(total-self.request['target_seconds'],2))}
        self.state['duration']=result;return result
    def check_rules(self):
        draft=self.state['draft']
        if not draft:return {'error':'draft_required'}
        risks=[];sources=set()
        allowed_titles=set(self.catalog['neutral_titles'])
        if draft['title'] not in allowed_titles:risks.append({'field':'title','reason':'unsupported_title','message':'Use an allowed neutral title; user claims are not evidence.'})
        for i,scene in enumerate(draft['scenes']):
            ids=scene['source_ids'];sources.update(ids)
            if not ids or any(k not in self.state['materials'] for k in ids):risks.append({'scene':i,'reason':'unretrieved_source'});continue
            facts={fact for k in ids for fact in self.state['materials'][k]['facts']}
            allowed=facts|set(self.catalog['neutral_phrases'])
            # Conservative exact sentence grounding; no semantic claims beyond provided sentences.
            sentences=[x.strip() for x in re.split(r'[。！？!?\n]+',scene['narration']) if x.strip()]
            if not sentences or any(x not in allowed for x in sentences):risks.append({'scene':i,'reason':'unsupported_narration','allowed_sentences':sorted(allowed)})
            visuals={v for k in ids for v in self.state['materials'][k]['visuals']}|set(self.catalog['neutral_visuals'])
            if scene['visual'] not in visuals:risks.append({'scene':i,'reason':'unsupported_visual','allowed_visuals':sorted(visuals)})
        combined=json.dumps(draft,ensure_ascii=False)
        for term in self.catalog['rules']['blocked_terms']:
            if term in combined:risks.append({'reason':'blocked_term','term':term})
        result={'draft_id':self.state['draft_id'],'passed':not risks,'risks':risks,'source_ids':sorted(sources)};self.state['rules']=result;return result
    def finish(self):
        state=self.state
        if not state['draft'] or not state['duration'] or not state['rules']:return {'error':'checks_required','message':'Store a draft, estimate duration and check rules.'}
        if state['duration']['draft_id']!=state['draft_id'] or state['rules']['draft_id']!=state['draft_id']:return {'error':'stale_checks'}
        if not state['duration']['within_limit'] or not state['rules']['passed']:return {'error':'validation_failed','duration':state['duration'],'rules':state['rules'],'message':'Revise and recheck or explicitly request_information with why you cannot meet constraints.'}
        return {'finished':True,'status':'completed','reason':'validated_script','script':state['draft'],'duration':state['duration'],'source_ids':state['rules']['source_ids'],'risks':[],'gaps':[]}
    def request_information(self,reason):
        if not reason.strip():return {'error':'reason_required'}
        if not self.state['searches'] and not self.state['errors']:return {'error':'search_required'}
        return {'finished':True,'status':'needs_information','reason':reason,'script':self.state['draft'],'duration':self.state['duration'],'source_ids':self.state['rules']['source_ids'] if self.state['rules'] else [],'risks':self.state['rules']['risks'] if self.state['rules'] else [],'gaps':['tool_failure' if self.state['errors'] else 'no_materials' if not self.state['materials'] else 'constraints_unresolved']}

def basic_draft(catalog,material,target=30):
    fact=material['facts'][0]
    minimum=len(re.findall(r'[\w\u4e00-\u9fff]',fact))/catalog['characters_per_second']
    if target<5:
        scenes=[{'visual':material['visuals'][0],'narration':fact+'。','source_ids':[material['id']],'pause_seconds':0}]
    else:
        cta=catalog['neutral_phrases'][0]
        speech=minimum+len(re.findall(r'[\w\u4e00-\u9fff]',cta))/catalog['characters_per_second']
        hold=max(0,min(25,round((target-2-speech)/2,2)))
        scenes=[{'visual':material['visuals'][0],'narration':fact+'。','source_ids':[material['id']],'pause_seconds':hold},
                {'visual':catalog['neutral_visuals'][-1],'narration':cta+'。','source_ids':[material['id']],'pause_seconds':hold}]
    return {'title':catalog['neutral_titles'][0],'scenes':scenes}

class MockModel:
    mode='mock';model='scripted-test-double'
    def decide(self,context,history):
        s=context['state'];action,args='search_materials',{'query':context['request']['theme']}
        last=history[-1]['observation'] if history else {}
        if last.get('error')=='tool_failure':
            if last['retryable']:action,args=history[-1]['action'],history[-1]['arguments']
            else:action,args='request_information',{'reason':'业务工具不可用，不能声称脚本已验证。'}
        elif s['searches']:
            if not s['materials']:action,args='request_information',{'reason':'没有检索到产品事实，请补充素材或调整主题。'}
            elif not s['draft']:action,args='propose_script',{'draft':basic_draft(context['catalog'],next(iter(s['materials'].values())),context['request']['target_seconds'])}
            elif not s['duration']:action,args='estimate_duration',{}
            elif not s['rules']:action,args='check_rules',{}
            elif not s['duration']['within_limit'] or not s['rules']['passed']:
                simple=basic_draft(context['catalog'],next(iter(s['materials'].values())),context['request']['target_seconds'])
                if digest(simple)==s['draft_id']:action,args='request_information',{'reason':'最小事实脚本仍无法满足时长，请调整目标。'}
                else:action,args='propose_script',{'draft':simple}
            else:action,args='finish',{}
        return {'action':action,'arguments':args,'decision_summary':'Offline scripted policy, not model decision evidence.'}

def run(request,catalog,model,max_steps=14,failure='none'):
    error=validate(request)
    if error:return {'status':'needs_information','reason':error['error'],'gaps':error.get('missing',[error['error']]),'script':None,'trace':[],'model_mode':model.mode}
    if max_steps<1:raise ValueError('max_steps must be positive')
    tools=Tools(request,catalog,failure);trace=[];final={'status':'incomplete','reason':'limit_reached','gaps':['execution_limit']}
    writing_rules = {key: value for key, value in catalog.items() if key != 'materials'}
    for step in range(1,max_steps+1):
        try:
            d=model.decide({'request':request,'state':copy.deepcopy(tools.state),'catalog':writing_rules},trace)
            if not isinstance(d,dict) or not isinstance(d.get('action'),str) or not isinstance(d.get('arguments'),dict) or not isinstance(d.get('decision_summary'),str) or not d['decision_summary'].strip():raise ValueError('invalid_decision')
        except Exception as e:
            trace.append({'step':step,'action':'model_error','arguments':{},'observation':getattr(e,'details',{'error':type(e).__name__}),'decision_summary':'No valid decision.'});final.update(reason='model_error',gaps=['model_error']);break
        observation=tools.call(d['action'],d['arguments']);trace.append({'step':step,'action':d['action'],'arguments':d['arguments'],'observation':observation,'decision_summary':d['decision_summary'][:500],'model_response':getattr(model,'last_meta',{})})
        if observation.get('finished'):final={k:v for k,v in observation.items() if k!='finished'};break
    for i,e in enumerate(trace):e['next_action']=trace[i+1]['action'] if i+1<len(trace) else 'stop:'+final['status']
    return {**final,'timestamp':datetime.now(timezone.utc).isoformat(),'model_mode':model.mode,'model':model.model,'tool_mode':'local_synthetic','max_steps':max_steps,'steps_used':len(trace),'state':tools.state,'trace':trace}

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--data',default=str(ROOT/'data/materials.json'));p.add_argument('--mode',choices=['mock','live'],default='mock');p.add_argument('--output',default='script.json');p.add_argument('--max-steps',type=int,default=14);p.add_argument('--failure',choices=['none','search_always','estimate_once','estimate_always'],default='none');a=p.parse_args()
    try:
        from src.model import LiveModel
        result=run(json.loads(Path(a.input).read_text()),json.loads(Path(a.data).read_text()),LiveModel() if a.mode=='live' else MockModel(),a.max_steps,a.failure)
    except Exception as e:print(json.dumps(getattr(e,'details',{'error':type(e).__name__}),ensure_ascii=False));return 2
    Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k in ('status','reason','script','duration','gaps','risks')},ensure_ascii=False,indent=2));return 0 if result['status']=='completed' else 2
if __name__=='__main__':sys.exit(main())
