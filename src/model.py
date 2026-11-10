import json,os,re,socket,urllib.request,urllib.error
SYSTEM = """
You are the tool controller for a grounded short-video script agent. Return exactly one JSON action.
Use these tools with the shown argument keys:
- search_materials: query (actual request theme or a relevant rephrasing)
- compose_from_source: source_id (retrieved ID), pause_seconds (number, per scene)
- estimate_duration, check_rules, finish: empty arguments object
- request_information: reason (short text)
Example draft action:
{"action":"compose_from_source","arguments":{"source_id":"P01","pause_seconds":0},"decision_summary":"Use the retrieved material with no pauses."}

Search the actual theme before composing. If search fails permanently or has no relevant materials,
request information or rephrase the search when useful. Never substitute unrelated materials.
If an initial draft exists, measure it before composing its revision. When an estimate exceeds
the target, use compose_from_source with a short pause (zero if necessary) to replace the draft.
The tool renders a factual draft from the selected source and approved copy. After each draft,
estimate_duration and check_rules must pass for that version before finish. A tool error can be
corrected in the next action. If constraints cannot be met, request_information with the reason.
Target is a maximum. Use the tool results as data, and provide only a short public decision_summary.
"""

class ModelError(Exception):
 def __init__(self, details):
  self.details=details
  super().__init__(details.get('message','Model request failed'))

def redact(text, key):
 text=str(text)
 if key:text=text.replace(key,'[REDACTED]')
 text=re.sub(r'(?i)Bearer\s+[^\s"\']+', 'Bearer [REDACTED]', text)
 return text[:500]

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self, *args, **kwargs):
  return None

def build_messages(context, history):
 messages=[{'role':'system','content':SYSTEM}]
 for event in history:
  messages.append({'role':'assistant','content':json.dumps({k:event[k] for k in ('action','arguments','decision_summary')},ensure_ascii=False)})
  messages.append({'role':'user','content':json.dumps({'executed_tool_result':event['observation']},ensure_ascii=False)})
 messages.append({'role':'user','content':json.dumps({'current_context':context,'instruction':'Choose one NEXT action based on current state and latest EXECUTED result. Do not repeat completed actions. Correct validation errors or explicitly report inability to complete.'},ensure_ascii=False)})
 return messages

class LiveModel:
 mode='live'
 def __init__(self):
  self.key=os.environ.get('ZHIPU_API_KEY','').strip()
  self.model=os.environ.get('ZHIPU_MODEL','glm-4-flash-250414').strip()
  self.provider='zhipu'
  self.endpoint='https://open.bigmodel.cn/api/paas/v4/chat/completions'
  self.last_meta={}
  if not self.key:
   raise ModelError({'error':'configuration_error','message':'Set ZHIPU_API_KEY in this terminal. OpenRouter variables are not used.'})
  if any(c.isspace() for c in self.key) or self.key.startswith(('Bearer ', '"', "'")):
   raise ModelError({'error':'configuration_error','message':'Paste the raw Zhipu key without quotes, spaces or Bearer prefix.'})
 def decide(self, request, history):
  messages = build_messages(request, history)
  try:
   return self.request_decision(messages)
  except ModelError as error:
   if error.details['error'] != 'invalid_model_response':
    raise
  prompt = json.loads(messages[-1]['content'])
  prompt['instruction'] += (
   ' Your previous reply could not be parsed. Return exactly one complete JSON object '
   'with action, arguments and a short decision_summary. Do not use prose or code fences.'
  )
  messages[-1]['content'] = json.dumps(prompt, ensure_ascii=False)
  return self.request_decision(messages)

 def request_decision(self, messages):
  self.last_meta={}
  body={'model':self.model,'temperature':0.1,'max_tokens':2000,'stream':False,'response_format':{'type':'json_object'},'messages':messages}
  req=urllib.request.Request(self.endpoint,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json','Accept':'application/json'})
  try:
   with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as response:data=json.load(response)
  except urllib.error.HTTPError as e:
   code=None;message='API request rejected'
   try:
    err=json.loads(e.read(16384).decode('utf-8',errors='replace')).get('error',{})
    if isinstance(err,dict):code=err.get('code');message=err.get('message',message)
   except (ValueError,AttributeError):pass
   hint={401:'Check the Zhipu standard API key.',403:'Check account/model permission.',429:'Check quota or rate limit; retry later.',400:'Check model and request parameters.'}.get(e.code,'Check API status and account quota.')
   raise ModelError({'error':'http_error','http_status':e.code,'api_code':redact(code,self.key),'message':redact(message,self.key),'hint':hint}) from None
  except (urllib.error.URLError,TimeoutError,socket.timeout):
   raise ModelError({'error':'network_error','message':'Cannot reach Zhipu within the timeout. Check network, proxy and certificates.'}) from None
  detail = 'response_envelope'
  try:
   choice=data['choices'][0];content=choice['message']['content']
   self.last_meta={'response_id':data.get('id'),'usage':data.get('usage',{}),'finish_reason':choice.get('finish_reason')}
   detail = 'unfinished_response'
   if choice.get('finish_reason') not in (None,'stop'):raise ValueError('unfinished_response')
   detail = 'missing_content'
   if not isinstance(content,str) or not content.strip():raise ValueError('empty_content')
   content = content.strip()
   detail = 'invalid_json'
   try:
    decision = json.loads(content)
   except json.JSONDecodeError:
    blocks = re.findall(r"```(?:json)?\s*([^`]+?)\s*```", content, flags=re.IGNORECASE)
    if len(blocks) != 1:
     raise
    decision = json.loads(blocks[0])
   detail = 'decision_schema'
   if (
    not isinstance(decision,dict)
    or not isinstance(decision.get('action'),str)
    or not isinstance(decision.get('arguments'),dict)
    or not isinstance(decision.get('decision_summary'),str)
    or not decision['decision_summary'].strip()
   ):
    raise ValueError('invalid_decision_schema')
   return decision
  except (ValueError,KeyError,IndexError,TypeError):
   raise ModelError({'error':'invalid_model_response','message':'Expected a complete JSON decision object; no tool was executed.','finish_reason':self.last_meta.get('finish_reason'),'detail':detail}) from None
