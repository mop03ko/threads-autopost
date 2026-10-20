"""Finite, explicitly reviewed catch-up: reconcile one existing post and publish eight missing posts."""
import copy
import difflib
import hashlib
import io
import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import requests

import publishing
import threads_post as app
from audit_failed_posts import normalized, timeline
from magnific_generate_batch import r2_client, required_env
from prepare_image_urls import load_queue, save_queue, sync_google_sheet
from queue_store import remote_store
from recovery_art import RecoveryCard, brief_for

PLAN_PATH=Path('recovery/2026-10-21.json')
MODE_PATH=Path('.github/recovery-batch.json')


def candidates(plan,queue):
    by_id={p['id']:p for p in queue}; selected=[]
    for expected in plan['posts']:
        actual=by_id.get(expected['id'])
        if not actual or actual.get('text')!=expected['text'] or actual.get('scheduled_at')!=expected['scheduled_at']:
            raise RuntimeError(f"Post {expected['id']}: reviewed text or schedule changed.")
        if actual['status']=='posted':
            if not actual.get('threads_id'): raise RuntimeError('Posted state lacks evidence.')
            continue
        if actual['status']!='failed':
            raise RuntimeError(f"Post {expected['id']}: state {actual['status']} requires review.")
        selected.append(expected)
    return selected


def assert_absent(selected,items):
    published=[normalized(p.get('text')) for p in items]
    for post in selected:
        for value in (post['original_text'],post['text']):
            text=normalized(value)
            if any(difflib.SequenceMatcher(None,text,other).ratio()>=.85 for other in published):
                raise RuntimeError(f"Post {post['id']}: possible existing publication; no retry allowed.")


def reconcile(plan,token):
    evidence=plan['reconcile']
    live=app.api('GET',f"{app.GRAPH}/{evidence['threads_id']}",params={
        'access_token':token,'fields':'id,text,timestamp,permalink'})
    if live.get('id')!=evidence['threads_id'] or normalized(live.get('text'))!=normalized(evidence['original_text']):
        raise RuntimeError('Existing-post evidence no longer matches.')
    stamp=datetime.fromisoformat(live['timestamp']).astimezone(app.TZ).strftime('%Y-%m-%d %H:%M')
    def update(queue):
        target=next(p for p in queue if p['id']==evidence['id'])
        if normalized(target['text'])!=normalized(evidence['original_text']):
            raise RuntimeError('Existing post text changed in queue.')
        if target['status']=='posted' and target.get('threads_id')==live['id']: return
        if target['status']!='failed': raise RuntimeError('Existing post state changed.')
        target.update(status='posted',threads_id=live['id'],permalink=live['permalink'],
                      posted_at=stamp,publication_phase='published',reconciled_from='Threads API exact text match')
        target.pop('error',None)
    _,queue=remote_store().update(update,'Reconcile confirmed existing Threads post 447 [skip ci]')
    app.update_google_sheet_status(queue)
    return live


def prepare(selected):
    path=Path('queue.json');queue=load_queue(path);original=copy.deepcopy(queue)
    by_id={p['id']:p for p in queue}
    client=r2_client();bucket=required_env('R2_BUCKET_NAME');base=required_env('R2_PUBLIC_BASE_URL').rstrip('/')
    changed=[];manifest=[]
    for post in selected:
        image=RecoveryCard(brief_for(post)).render();output=io.BytesIO()
        image.save(output,'JPEG',quality=94,optimize=True,subsampling=0)
        data=output.getvalue();digest=hashlib.sha256(data).hexdigest()
        key=f"threads/posts/editorial/recovery-{post['id']}-{digest[:20]}.jpg";url=f'{base}/{key}'
        client.put_object(Bucket=bucket,Key=key,Body=data,ContentType='image/jpeg',CacheControl='public,max-age=31536000,immutable')
        response=requests.get(url,timeout=45);response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest()!=digest: raise RuntimeError('Image verification failed.')
        if by_id[post['id']].get('image_url')!=url:
            by_id[post['id']]['image_url']=url;changed.append(post['id'])
        manifest.append({'id':post['id'],'image_url':url,'sha256':digest})
    cells=sync_google_sheet(queue,changed,expected_posts=original,expected_statuses=('failed',))
    if cells!=len(changed): raise RuntimeError('Image Sheet sync incomplete.')
    saved=save_queue(path,queue)
    if set(saved)!=set(changed): raise RuntimeError('Concurrent queue change; review before publishing.')
    return manifest


def publish(selected):
    by_id={p['id']:p for p in remote_store().read()[0]}
    # Only our verified immutable JPEGs may be used in this finite recovery.
    base=required_env('R2_PUBLIC_BASE_URL').rstrip('/')
    for p in selected:
        url=by_id[p['id']].get('image_url') or ''
        if not url.startswith(f"{base}/threads/posts/editorial/recovery-{p['id']}-"):
            raise RuntimeError(f"Post {p['id']}: run image preparation first.")
        response=requests.get(url,timeout=45);response.raise_for_status()
        expected=url.rsplit('-',1)[1].removesuffix('.jpg')
        if hashlib.sha256(response.content).hexdigest()[:20]!=expected:
            raise RuntimeError('Prepared image integrity check failed.')
    for start in range(0,len(selected),app.MAX_POSTS_PER_RUN):
        ids=[p['id'] for p in selected[start:start+app.MAX_POSTS_PER_RUN]]
        print(f'Publishing explicitly approved IDs: {ids}',flush=True)
        try:
            publishing.run(SimpleNamespace(live=True,id=ids,sync=False,force=False),app)
        finally:
            queue,_=remote_store().read();app.update_google_sheet_status(queue)
        if any(p['status']!='posted' for p in queue if p['id'] in ids):
            raise RuntimeError('A selected post was not published; stop before the next batch.')


def verify_results(plan,token):
    queue,_=remote_store().read();by_id={p['id']:p for p in queue};result=[]
    for expected in plan['posts']:
        p=by_id[expected['id']]
        if p['status']!='posted' or not p.get('threads_id'): raise RuntimeError('Publication incomplete.')
        actual=app.api('GET',f"{app.GRAPH}/{p['threads_id']}",params={
            'access_token':token,'fields':'id,text,timestamp,permalink'})
        if normalized(actual.get('text'))!=normalized(expected['text']): raise RuntimeError('Published text mismatch.')
        result.append({'queue_id':p['id'],**actual})
    return result


def main():
    mode=json.loads(MODE_PATH.read_text())['mode'];plan=json.loads(PLAN_PATH.read_text())
    if mode not in ('prepare','publish'): raise RuntimeError('Invalid recovery mode.')
    if mode=='publish' and app.now().strftime('%Y-%m-%d')!=plan['date']:
        raise RuntimeError('This finite recovery authorization has expired.')
    print(f'Recovery mode: {mode}; reading current Sheet.',flush=True)
    app.cmd_sync(None)
    token=os.environ['THREADS_ACCESS_TOKEN']
    print('Reconciling independently confirmed existing post 447.',flush=True)
    existing=reconcile(plan,token)
    selected=candidates(plan,remote_store().read()[0])
    print('Checking the complete live timeline for duplicates.',flush=True)
    assert_absent(selected,timeline(token))
    report={'mode':mode,'reconciled':{'queue_id':447,**existing},'selected':[p['id'] for p in selected]}
    if mode=='prepare':
        print('Preparing and verifying reviewed images.',flush=True)
        report['images']=prepare(selected)
    else:
        publish(selected)
        report['published']=verify_results(plan,app.read_token()['access_token'] if app.TOKEN_FILE.exists() else token)
    Path('recovery-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        # Do not print remote exception details that could contain credentials.
        detail=str(exc) if isinstance(exc,RuntimeError) else type(exc).__name__
        print(f'Recovery stopped: {detail}. Inspect saved queue states before retrying.')
        raise SystemExit(1)
