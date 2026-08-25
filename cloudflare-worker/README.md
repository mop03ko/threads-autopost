# Cloudflare-оос Threads-д шууд нийтлэх Worker

Энэ Worker нь GitHub Actions runner хүлээлгүйгээр `queue.json`-оос хугацаа болсон
постыг claim хийж, Threads API-д шууд нийтэлнэ. GitHub дахь төлөв нь
`pending -> processing -> posted/failed` дарааллаар солигдоно.

## Шаардлагатай тохиргоо

Cloudflare Worker-ийн **Settings > Variables and Secrets** хэсэгт:

- `GITHUB_TOKEN` — fine-grained PAT; зөвхөн `mop03ko/threads-autopost`
  repository, **Contents: Read and write** эрхтэй.
- `THREADS_ACCESS_TOKEN` — одоогийн урт хугацааны Threads access token.
- `THREADS_USER_ID` — заавал биш; байхгүй бол `/me` API-аас автоматаар авна.

Токеныг оны эцэс хүртэл автоматаар сунгахын тулд:

1. **Storage & Databases > KV > Create** дээр `threads-autopost-state` үүсгэнэ.
2. Worker-ийн **Settings > Bindings > Add > KV Namespace** дээр variable name-ийг
   `STATE` болгож дээрх namespace-тай холбоно.

`STATE` байхгүй үед пост нийтлэгдэнэ, гэхдээ Threads токены шинэ хувилбар
хадгалагдахгүй тул урт хугацаанд заавал холбоно.

## Cron

Cron нь UTC цагаар:

- `30 0,12 * * *` — Улаанбаатарын 08:30, 20:30
- `0 2,5,8,11,14 * * *` — Улаанбаатарын 10:00, 13:00, 16:00, 19:00, 22:00

## Dashboard-оос шинэчлэх

Одоо байгаа Worker-ийн code editor дахь кодыг `src/index.js`-ийн агуулгаар
сольж **Deploy** хийнэ. Дээрх хоёр cron trigger-ийг хэвээр үлдээнэ. Deploy-ийн
дараа Worker URL-ийн `/health` зам `{"ok":true,...}` буцаана.

## Давхар нийтлэх хамгаалалт

GitHub-ийн Contents API-ийн SHA-based optimistic update ашиглаж нэг cron
ажиллагаа л постыг `processing` болгож чадна. Нийтэлсний дараах status commit
алдахад пост `processing` хэвээр үлдэнэ; автоматаар дахин нийтлэхгүй. Энэ нь
төлөв хадгалах үеийн ховор алдаанаас үүсэх duplicate постоос хамгаална.
