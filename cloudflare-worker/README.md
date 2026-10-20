# Threads workflow scheduler

Cloudflare Worker нь 5 минут тутам GitHub-ийн `threads-post.yml` workflow-г
эхлүүлнэ. Нийтлэлийг GitHub Actions хийнэ. Worker өөрөө Threads API дуудахгүй,
queue.json болон токен шинэчлэхгүй.

Шилжүүлэх дараалал: [RELIABILITY.md](../RELIABILITY.md). Хуучин шууд нийтлэгч
Worker-ийг зогсоож, шинэ кодыг deploy хийхгүйгээр шилжилт дуусахгүй.

## Тохиргоо

- Secret `GITHUB_TOKEN`: зөвхөн энэ repository-ийн Actions: read/write эрх.
- Vars: `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_BRANCH`, `GITHUB_WORKFLOW`.
- `DISPATCH_ENABLED=false`: cron dispatch-ийг түр зогсооно.
- KV, Threads токен шаардлагагүй. Root болон энэ хавтасны wrangler config ижил Worker-т зориулагдсан.

Root хавтаснаас `npx wrangler deploy`, эсвэл энэ хавтаснаас мөн тэр тушаалыг ажиллуулна.
`/health` тохиргоог мэдээлнэ. HTTP 200 нь token хүчинтэй, нийтлэл амжилттай гэсэн баталгаа биш.
Dispatch амжилттай бол GitHub HTTP 204 буцаана; үр дүнг Actions болон queue дээр шалгана.

```bash
npm test
```
