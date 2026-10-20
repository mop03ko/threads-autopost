"""Read the authenticated Threads timeline to review legacy failed queue entries."""
import difflib
import json
import os
import re
import unicodedata
from pathlib import Path

import threads_post as app
from queue_store import remote_store

TARGET_IDS = (817,447,835,700,836,837,848,853,856)


def normalized(text):
    return re.sub(r'\W+', '', unicodedata.normalize('NFKC',text or '').casefold())


def timeline(token):
    posts=[]; after=None; seen=set()
    for _ in range(30):
        params={'access_token':token,'fields':'id,text,timestamp,permalink','limit':100}
        if after: params['after']=after
        data=app.api('GET',f'{app.GRAPH}/me/threads',params=params)
        if not isinstance(data.get('data'),list): raise RuntimeError('Timeline response lacks data.')
        posts.extend(data['data'])
        paging=data.get('paging') or {}
        if not paging.get('next'): return posts
        after=(paging.get('cursors') or {}).get('after')
        if not after or after in seen: raise RuntimeError('Timeline pagination incomplete.')
        seen.add(after)
    raise RuntimeError('Timeline exceeds audit limit; refusing incomplete duplicate check.')


def candidate_matches(post,items):
    text=normalized(post['text'])
    ranked=sorted(((difflib.SequenceMatcher(None,text,normalized(p.get('text'))).ratio(),p)
                   for p in items),key=lambda pair:pair[0],reverse=True)
    return [{'similarity':round(score,4),**p} for score,p in ranked[:3]]


def main():
    queue,_=remote_store().read()
    items=timeline(os.environ['THREADS_ACCESS_TOKEN'])
    report={'timeline_count':len(items),'complete':True,'earliest':min((p.get('timestamp','') for p in items),default=''),
            'posts':[{'queue_id':p['id'],'queue_status':p['status'],'old_text':p['text'],
                      'matches':candidate_matches(p,items)} for p in queue if p['id'] in TARGET_IDS]}
    Path('failed-post-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__': main()
