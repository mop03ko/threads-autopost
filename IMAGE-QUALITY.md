# Post image quality

The October 20 audit checked all 294 distinct image URLs referenced by 3,059 future posts. At that snapshot, 2,041 posts had no image; 11 stock URLs were reused (up to 122 times). Seven requests failed and 26 sources had a short edge below 600 px. A failed request is an observed availability problem, not proof that a source is permanently unavailable. See `image-audit/2026-10-20.json` for affected IDs.

## Reviewed visual pack

`image-briefs/2026-10-21.json` contains 56 explicitly reviewed briefs: all 49 scheduled posts on October 21–27, plus seven later posts whose image requests failed. It adds 21 missing illustrations and replaces 35 existing images. Each brief is tied to the exact text hash and scheduled date.

The 1080×1350 JPEGs use legible Mongolian headings and concrete educational diagrams: aspect ratios, typography, layout, brand systems, print boundaries and workflow decisions. Cinema illustrations are original design studies, clearly labeled as diagrams rather than film frames. Rendered sources are code-native illustrations, not cropped stock photography.

This is not a claim that all 3,059 future posts have new artwork. The audit retains 21 later low-resolution sources for further editorial review. Other repeated stock images and missing visuals outside this pack remain unchanged.

## Deployment

`Deploy reviewed editorial images` runs when the brief or renderer changes, or manually. It shares the publisher's concurrency group. It reads the current Sheet, renders only pending future posts whose text and schedule still match, uploads content-addressed JPEGs to R2, and verifies every public download against its SHA-256. It updates only corresponding image URL cells, then the remote queue. It does not publish posts, edit captions, reset statuses or reschedule anything.

Immediately before the Sheet write, all intended rows must still match the loaded text, date, status and old image URL. If a row changed, the whole image write stops for review. If a crash occurs after the Sheet write, ordinary Sheet sync restores the queue. Re-running unchanged artwork is idempotent. Previously published, processing and review-locked posts cannot receive image updates.

## Ongoing image selection

- Prefer a specific visual explanation over generic desks or decorative geometric objects.
- The AI image batch now prioritizes the nearest future scheduled posts, skips non-pending and past posts, and preserves reviewed/manual images. Cinema-analysis posts need a reviewed brief.
- AI prompts call for the actual action or comparison in the post, with recognizable subject matter and safe margins.
- Preserve the whole composition when fitting generated images to 4:5; reject undersized generation output instead of enlarging it blindly.
- Legacy bulk assignment cannot overwrite reviewed/manual URLs, even with `--force`.
- A text or schedule edit during generation invalidates the image update.

To extend the pack, add a reviewed brief with the exact current text hash, date, diagram type, title and takeaway. Render locally with `python editorial_images.py --output /tmp/editorial-preview`, inspect the output, and then deploy through the workflow. Never infer a diagram from a post ID alone.
