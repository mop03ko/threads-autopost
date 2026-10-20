"""Upload reviewed diagrams, verify exact public bytes, then update image cells only."""
import copy
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from editorial_images import eligible, render_briefs
from magnific_generate_batch import r2_client, required_env
from prepare_image_urls import load_queue, save_queue, sync_google_sheet


def main():
    queue_path=Path('queue.json')
    queue=load_queue(queue_path)
    original=copy.deepcopy(queue)
    by_id={p['id']:p for p in queue}
    briefs=json.loads(Path('image-briefs/2026-10-21.json').read_text())
    now=datetime.now(ZoneInfo('Asia/Ulaanbaatar'))
    selected=[b for b in briefs if b['id'] in by_id and eligible(by_id[b['id']],b,now)]
    skipped=[b['id'] for b in briefs if b not in selected]
    output=Path('editorial-output')
    manifest=render_briefs(selected,output)
    client=r2_client()
    bucket=required_env('R2_BUCKET_NAME')
    base=required_env('R2_PUBLIC_BASE_URL').rstrip('/')
    updates=[]
    for item in manifest:
        data=(output/item['file']).read_bytes()
        key=f"threads/posts/editorial/{item['id']}-{item['sha256'][:20]}.jpg"
        url=f'{base}/{key}'
        # Repeat deploys of unchanged diagrams do not churn queue/Sheet cells.
        if by_id[item['id']].get('image_url')==url:
            continue
        client.put_object(Bucket=bucket,Key=key,Body=data,ContentType='image/jpeg',
                          CacheControl='public,max-age=31536000,immutable')
        response=requests.get(url,timeout=45)
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest()!=item['sha256']:
            raise RuntimeError(f"Public image verification failed: {item['id']}")
        by_id[item['id']]['image_url']=url
        updates.append(item['id'])
        item['url']=url
    # Validate the entire Sheet against the snapshot before writing any cell.
    # Sheet is the source of truth: a crash after this write heals on normal sync.
    cells=sync_google_sheet(queue,updates,expected_posts=original)
    if cells != len(updates):
        raise RuntimeError('Image cells were not all synced; queue was not changed.')
    changed=save_queue(queue_path,queue)
    report={'updated':updates,'queue_changes':changed,'sheet_cells':cells,'skipped':skipped,'images':manifest}
    (output/'deployment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    if set(changed)!=set(updates):
        raise RuntimeError('Queue changed concurrently; run normal Sheet sync before publishing.')
    print(f'Verified {len(manifest)} images; updated {cells} Sheet image cells. Skipped IDs: {skipped}')


if __name__=='__main__': main()
