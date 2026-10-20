# Post image quality

The October 20 audit checked all 294 distinct image URLs referenced by 3,059 future posts. At that snapshot, 2,041 posts had no image; 11 stock URLs were reused (up to 122 times). Seven requests failed and 26 sources had a short edge below 600 px. A failed request is an observed availability problem, not proof that a source is permanently unavailable. See `image-audit/2026-10-20.json` for affected IDs.

## Reviewed visual pack

`image-briefs/2026-10-21.json` contains 56 explicitly reviewed briefs: all 49 scheduled posts on October 21–27, plus seven later posts whose image requests failed. It adds 21 missing illustrations and replaces 35 existing images. Each brief is tied to the exact text hash and scheduled date.

The 1080×1350 JPEGs use legible Mongolian headings and concrete educational diagrams: aspect ratios, typography, layout, brand systems, print boundaries and workflow decisions. The original cinema diagrams are superseded by the main-poster policy below and are no longer eligible for deployment. Non-cinema sources remain code-native illustrations.

This is not a claim that all 3,059 future posts have new artwork. The audit retains 21 later low-resolution sources for further editorial review. Other repeated stock images and missing visuals outside this pack remain unchanged.

## Deployment

`Deploy reviewed editorial images` runs when the brief or renderer changes, or manually. It shares the publisher's concurrency group. It reads the current Sheet, renders only pending future posts whose text and schedule still match, uploads content-addressed JPEGs to R2, and verifies every public download against its SHA-256. It updates only corresponding image URL cells, then the remote queue. It does not publish posts, edit captions, reset statuses or reschedule anything.

Immediately before the Sheet write, all intended rows must still match the loaded text, date, status and old image URL. If a row changed, the whole image write stops for review. If a crash occurs after the Sheet write, ordinary Sheet sync restores the queue. Re-running unchanged artwork is idempotent. Previously published, processing and review-locked posts cannot receive image updates.

## Ongoing image selection

- Prefer a specific visual explanation over generic desks or decorative geometric objects.
- The AI image batch prioritizes the nearest future scheduled posts, skips non-pending and past posts, and preserves reviewed/manual images. Film posts are excluded from AI generation, diagrams and generic/manual bulk replacement.
- AI prompts call for the actual action or comparison in the post, with recognizable subject matter and safe margins.
- Preserve the whole composition when fitting generated images to 4:5; reject undersized generation output instead of enlarging it blindly.
- Legacy bulk assignment cannot overwrite reviewed/manual URLs, even with `--force`.
- A text or schedule edit during generation invalidates the image update.

To extend the pack, add a reviewed brief with the exact current text hash, date, diagram type, title and takeaway. Render locally with `python editorial_images.py --output /tmp/editorial-preview`, inspect the output, and then deploy through the workflow. Never infer a diagram from a post ID alone.

## Main posters for film posts

Use the film's actual main theatrical poster for posts about its poster or graphic design. Match the film, release year and installment; do not use a still, fan art, a generated imitation or an explanatory diagram as the post image. Preserve the complete original composition, lettering and aspect ratio. Do not crop, add overlays or upscale a small source.

`movie-posters/catalog.json` records reviewed source pages, original image URLs, dimensions and SHA-256 hashes. `movie-posters/posts.json` binds each planned replacement to the exact caption hash and schedule. Generic franchise headings currently use the first film; the Marauder's Map article explicitly uses *Harry Potter and the Prisoner of Azkaban* (2004). The catalog retains the full installment title for review.

`Deploy reviewed movie posters` verifies the pinned source bytes, uploads those exact JPEG bytes to content-addressed R2 paths, verifies public downloads, and changes only eligible pending future image cells. The Sheet write requires unchanged text, schedule, status and prior image. Published posts are never modified or republished by this workflow.

The publisher rejects a recognized film post unless its image path matches that film's reviewed catalog entry. An unknown film requires source review and a catalog entry; it cannot silently fall back to generic imagery. To add a film, review its theatrical poster and installment, add the source/hash/dimensions and title aliases, then add exact post bindings and deploy. A changed source hash requires another visual review.
