"""Reviewed theatrical posters for film posts; never substitute generated art."""
from functools import lru_cache
import json
from pathlib import Path
import unicodedata
from urllib.parse import urlparse


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / 'movie-posters/catalog.json').read_text())


def normalized(value):
    return unicodedata.normalize('NFKC', value).casefold().strip()


def movie_key(post):
    text = normalized(str(post.get('text') or ''))
    headline = text.split('\n', 1)[0]
    if headline.startswith('киноны график дизайн:'):
        headline = headline.split(':', 1)[1].strip()
    # Match a whole film title, including internal colons, before an editorial subtitle.
    choices = sorted(((alias, item['key']) for item in catalog()['films']
                      for alias in item['aliases']), key=lambda pair: len(pair[0]), reverse=True)
    for alias, key in choices:
        name = normalized(alias)
        if headline == name or any(headline.startswith(name + sep) for sep in (':', ' —', ' –', ' -')):
            # This prop first appears in the third film, not the first installment.
            if key == 'harry-potter-2001' and ('мараудер' in text or 'marauder' in text):
                return 'harry-potter-and-the-prisoner-of-azkaban-2004'
            return key
    return None


def is_movie_post(post):
    text = normalized(str(post.get('text') or ''))
    return bool(movie_key(post) or 'киноны график' in text
                or 'киноны постер' in text or 'film poster' in text or 'movie poster' in text)


def poster_path(film):
    return f"/threads/posts/movie-posters/{film['key']}-{film['source_sha256'][:20]}.jpg"


def validate_movie_poster(post):
    if not is_movie_post(post):
        return
    key = movie_key(post)
    film = next((f for f in catalog()['films'] if f['key'] == key), None)
    if not film or urlparse(str(post.get('image_url') or '')).path != poster_path(film):
        raise RuntimeError(f"Post {post['id']}: тухайн киноны баталгаажуулсан үндсэн постер шаардлагатай.")
