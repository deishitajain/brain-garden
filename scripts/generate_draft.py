#!/usr/bin/env python3
"""Generate a draft pack for human review. Never publishes to the website."""
import json, os, re, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

PROMPT = '''You are an editorial assistant for Brain Garden, a playful curiosity app. Search current trustworthy original sources and propose ONE small draft pack connecting a recent verifiable finance, technology or cybersecurity story to two broadly useful ideas and one 3-step rabbit hole. Clearly separate what the source reports from illustrative examples. Each source URL must be a real HTTPS URL you actually used. Do not fabricate quotations, figures, dates, or attribution. Do not give investment recommendations. Text is for human review, never auto-publish.
Return one JSON object only (no markdown fences) matching exactly this structure:
{"format":"brain-garden-content-pack","version":1,"title":"short title","ideas":[{"id":"...","title":"...","domain":"Finance or Technology or Cybersecurity","hook":"...","body":"...","bridge":"...","example":"...","related":["..."],"sources":["https://..."]}],"paths":[{"id":"...","title":"...","desc":"...","items":[{"id":"...","title":"...","tag":"...","question":"...","choices":["...","..."],"responses":["...","..."],"idea":"...","pattern":"...","door":"...","link":"...","sources":["https://..."]}]}]}
Use lowercase unique ids consisting only of letters numbers underscores, 2 to 45 characters. Prefix every ID with the given date string to avoid collisions, but the first character must be a letter. For final path item, door and link can be omitted. Every field is plain text with no angle brackets or ampersands. Provide two plausible choices and explanatory responses per path item. Explain important caveats. Use only URLs appearing in your actual web citations. Avoid celebrity, geography and culture. Include no user data.
'''

def valid_text(x):
    return isinstance(x,str) and 0<len(x)<2000 and not any(c in x for c in '<>&')

def validate(pack, cited):
    def ident(x): return isinstance(x,str) and bool(re.fullmatch(r'[a-z][a-z0-9_-]{1,45}',x))
    def sources(x): return isinstance(x,list) and bool(x) and all(isinstance(u,str) and urlparse(u).scheme=='https' and u in cited for u in x)
    if not isinstance(pack,dict) or pack.get('format')!='brain-garden-content-pack' or pack.get('version')!=1 or not valid_text(pack.get('title')): raise ValueError('Invalid pack header')
    ideas,paths=pack.get('ideas'),pack.get('paths')
    if not isinstance(ideas,list) or not isinstance(paths,list) or not (len(ideas)+len(paths)) or len(ideas)>50 or len(paths)>10: raise ValueError('Invalid pack sizes')
    ids=set()
    def add_id(x):
        if not ident(x) or x in ids: raise ValueError('Invalid or repeated ID')
        ids.add(x)
    for c in ideas:
        if not isinstance(c,dict): raise ValueError('Invalid idea')
        add_id(c.get('id'))
        if not all(valid_text(c.get(k)) for k in ('title','domain','hook','body','bridge','example')) or not isinstance(c.get('related'),list) or not all(valid_text(v) for v in c['related']) or not sources(c.get('sources')): raise ValueError('Invalid idea content or unverified URL')
        if 'next' in c and c['next'] is not None and not ident(c['next']): raise ValueError('Invalid next ID')
        if 'door' in c and not valid_text(c['door']): raise ValueError('Invalid door')
    for p in paths:
        if not isinstance(p,dict): raise ValueError('Invalid path')
        add_id(p.get('id'))
        if not valid_text(p.get('title')) or not valid_text(p.get('desc')) or not isinstance(p.get('items'),list) or not 2<=len(p['items'])<=8: raise ValueError('Invalid path details')
        for i,t in enumerate(p['items']):
            if not isinstance(t,dict): raise ValueError('Invalid path item')
            add_id(t.get('id'))
            if not all(valid_text(t.get(k)) for k in ('title','tag','question','idea','pattern')) or not sources(t.get('sources')): raise ValueError('Invalid item content or unverified URL')
            if not all(isinstance(t.get(k),list) and len(t[k])==2 and all(valid_text(x) for x in t[k]) for k in ('choices','responses')): raise ValueError('Invalid choices or responses')
            if i<len(p['items'])-1 and not all(valid_text(t.get(k)) for k in ('door','link')): raise ValueError('Missing next door')
    return pack

def unpack(response):
    text=[]; cited=set()
    for output in response.get('output',[]):
        if output.get('type')!='message': continue
        for block in output.get('content',[]):
            if block.get('type')!='output_text': continue
            text.append(block.get('text',''))
            for a in block.get('annotations',[]):
                if a.get('type')=='url_citation' and isinstance(a.get('url'),str): cited.add(a['url'])
    raw=''.join(text).strip()
    if raw.startswith('```'): raise ValueError('Model returned markdown, not JSON')
    return validate(json.loads(raw),cited)

def main():
    key=os.environ.get('OPENAI_API_KEY'); model=os.environ.get('OPENAI_MODEL')
    if not key or not model: raise RuntimeError('Set OPENAI_API_KEY and OPENAI_MODEL in the workflow secrets and variables.')
    stamp=datetime.now(timezone.utc).strftime('p%Y%m%d%H%M')
    payload={'model':model,'tools':[{'type':'web_search'}],'input':PROMPT+' ID prefix: '+stamp+'.','max_output_tokens':4500}
    req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
    try:
        with urllib.request.urlopen(req,timeout=150) as res: response=json.load(res)
    except urllib.error.HTTPError as err:
        raise RuntimeError('OpenAI API request failed (HTTP '+str(err.code)+'). Check credentials, model access, and billing.') from err
    if response.get('status')!='completed': raise RuntimeError('Response was not completed; no draft saved.')
    pack=unpack(response)
    dest=Path('drafts'); dest.mkdir(exist_ok=True); path=dest/(stamp+'.json')
    path.write_text(json.dumps(pack,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Draft generated:',path,'— review every claim, source, example, and connection before use.')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print('Draft not generated:',str(e),file=sys.stderr);sys.exit(1)
