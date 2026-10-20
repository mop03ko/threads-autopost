"""Deploy reviewed, source-pinned main posters to pending future film posts only."""
import copy
import hashlib
import io
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image

from movie_posters import catalog, movie_key, poster_path
from magnific_generate_batch import r2_client, required_env
from prepare_image_urls import load_queue, save_queue, sync_google_sheet


def eligible(post, binding, now):
    return (post.get('status') == 'pending'
            and post.get('scheduled_at', '') > now.strftime('%Y-%m-%d %H:%M')
            and post.get('scheduled_at') == binding['scheduled_at']
            and hashlib.sha256(post.get('text', '').encode()).hexdigest() == binding['text_sha256']
            and movie_key(post) == binding['film'])


def download(url):
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=45, headers={
                'User-Agent': 'ThreadsEditorialPosterReview/1.0 (https://github.com/mop03ko/threads-autopost)'})
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            status = getattr(exc.response, 'status_code', None)
            if attempt == 2 or (status is not None and status < 500):
                raise
            time.sleep(attempt + 1)


def verified_poster(film):
    response = download(film['source_url'])
    data = response.content
    if hashlib.sha256(data).hexdigest() != film['source_sha256']:
        raise RuntimeError(f"Poster source changed; review required: {film['key']}")
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        if im.format != 'JPEG' or list(im.size) != film['dimensions']:
            raise RuntimeError(f"Poster format or dimensions changed: {film['key']}")
    # Original bytes: no crop, padding, overlay, generated replacement or upscaling.
    return data


def main():
    queue_path = Path('queue.json')
    queue = load_queue(queue_path)
    original = copy.deepcopy(queue)
    by_id = {p['id']: p for p in queue}
    bindings = json.loads(Path('movie-posters/posts.json').read_text())
    now = datetime.now(ZoneInfo('Asia/Ulaanbaatar'))
    selected = [b for b in bindings if b['id'] in by_id and eligible(by_id[b['id']], b, now)]
    films = {f['key']: f for f in catalog()['films']}
    base = required_env('R2_PUBLIC_BASE_URL').rstrip('/')
    bucket = required_env('R2_BUCKET_NAME')
    client = r2_client()
    # Verify every referenced source and public object before changing any Sheet cell.
    assets = {}
    for key in sorted({b['film'] for b in selected}):
        film = films[key]
        data = verified_poster(film)
        path = poster_path(film)
        url = base + path
        client.put_object(Bucket=bucket, Key=path.lstrip('/'), Body=data,
                          ContentType='image/jpeg', CacheControl='public,max-age=31536000,immutable')
        response = download(url)
        if hashlib.sha256(response.content).hexdigest() != film['source_sha256']:
            raise RuntimeError(f'Public poster verification failed: {key}')
        assets[key] = url
        print(f"Verified poster: {key} ({film['dimensions'][0]}x{film['dimensions'][1]})", flush=True)
    updates = []
    for b in selected:
        post = by_id[b['id']]
        if post.get('image_url') != assets[b['film']]:
            post['image_url'] = assets[b['film']]
            updates.append(post['id'])
    cells = sync_google_sheet(queue, updates, expected_posts=original)
    if cells != len(updates):
        raise RuntimeError('Poster image cells were not all synced; queue was not changed.')
    changed = save_queue(queue_path, queue)
    report = {'updated': updates, 'queue_changes': changed, 'sheet_cells': cells,
              'verified_films': sorted(assets), 'skipped': [b['id'] for b in bindings if b not in selected]}
    Path('movie-poster-deployment.json').write_text(json.dumps(report, indent=2)+'\n')
    if set(changed) != set(updates):
        raise RuntimeError('Queue changed concurrently; sync from Sheet before publishing.')
    print(f'Updated {cells} image cells with {len(assets)} verified main posters. No posts published.')


if __name__ == '__main__':
    main()
