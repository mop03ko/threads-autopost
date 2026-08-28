# Cloudflare-оос Threads-д шууд нийтлэх Worker

Энэ Worker нь GitHub Actions runner хүлээлгүйгээр `queue.json`-оос хугацаа болсон
постыг claim хийж, Threads API-д шууд нийтэлнэ. GitHub дахь төлөв нь
`pending -> processing -> posted/failed` дарааллаар солигдоно.

## Шаардлагатай тохиргоо

Cloudflare Worker-ийн **Settings > Variables and Secrets** хэсэгт (Build
configuration биш, deployed Worker-ийн runtime settings):

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

Нэг Cron Trigger ашиглана:

- `*/5 * * * *` — таван минут тутам queue-г шалгана.

Worker зөвхөн хугацаа болсон `pending` постыг claim хийдэг тул хоосон шалгалт пост
үүсгэхгүй. Яг цагийн trigger алгассан тохиолдолд дараагийн 5 минутын шалгалт
нөхөж нийтэлнэ. Хоцролтын цонх 7 хоног тул trigger саатсанаас пост автоматаар
`skipped` болохгүй.

## Dashboard-оос шинэчлэх

Одоо байгаа Worker-ийн code editor дахь кодыг `src/index.js`-ийн агуулгаар
сольж **Deploy** хийнэ. Дээрх хоёр cron trigger-ийг хэвээр үлдээнэ. Deploy-ийн
дараа Worker URL-ийн `/health` замыг нээнэ. `ready: true`,
`bindings.githubToken: true`, `bindings.threadsAccessToken: true`,
`bindings.state: true` байх ёстой. `lastRun` нь сүүлийн cron ажиллагааны төлвийг
харуулна; secret-ийн утгыг буцаахгүй.

Cron trigger-ийн өөрчлөлт Cloudflare сүлжээнд тархахад 15 минут хүртэл хугацаа
шаардагдаж болно. Wrangler-аар удирдаж байгаа бол Dashboard болон Wrangler-ийг
хольж өөрчлөхгүй, `wrangler.jsonc`-ийг source of truth болгоно.

## Давхар нийтлэх хамгаалалт

GitHub-ийн Contents API-ийн SHA-based optimistic update ашиглаж нэг cron
ажиллагаа л постыг `processing` болгож чадна. Нийтэлсний дараах status commit
алдахад пост `processing` хэвээр үлдэнэ; автоматаар дахин нийтлэхгүй. Энэ нь
төлөв хадгалах үеийн ховор алдаанаас үүсэх duplicate постоос хамгаална.
