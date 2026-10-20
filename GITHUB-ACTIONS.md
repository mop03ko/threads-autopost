# GitHub Actions дээр ажиллуулах

Компьютер асаалттай байх шаардлагагүй болно. GitHub-ийн сервер 10 минут тутам
ажиллаж, Google Sheet-ээс уншаад, хугацаа болсон постыг нийтэлнэ.

**Ашиглалт**: давтамжтай ажилладаг тул Actions-ийн usage болон тухайн plan-ийн хязгаарыг хянана.

---

## Юу бэлдэх вэ

- GitHub бүртгэл
- Локал дээр аль хэдийн ажиллаж байгаа тохиргоо (token.json үүссэн байх)

---

## 1. Repo үүсгэх

https://github.com/new руу орно.

`[ ]` Repository name: `threads-autopost`

`[ ]` **Private** сонгоно (заавал, дотор нь постын агуулга байна)

`[ ]` **Create repository** дарна

---

## 2. Файлаа байршуулах

Локал хавтастаа PowerShell нээгээд:

```powershell
cd C:\Users\NewTech\Downloads\threads-autopost

git init
git add .
git commit -m "Анхны хувилбар"
git branch -M main
git remote add origin https://github.com/ТАНЫ_НЭР/threads-autopost.git
git push -u origin main
```

> `.gitignore` дотор `.env` болон `token.json` орсон тул нууц мэдээлэл
> repo руу орохгүй. Push хийсний дараа GitHub дээрээс шалгаж баталгаажуулна уу.

Git суулгаагүй бол: https://git-scm.com/download/win

---

## 3. Secrets тохируулах

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Дараах тавыг нэмнэ:

| Нэр | Утга |
|---|---|
| `THREADS_APP_ID` | `.env` файлын дотроос |
| `THREADS_APP_SECRET` | `.env` файлын дотроос |
| `THREADS_SHEET_ID` | `1nVy7ZcU-3XyTcAKaPkP7V6DZq5XvXZRy3sQ4uhS__6Y` |
| `THREADS_ACCESS_TOKEN` | доорх тушаалаар гаргана |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google service account key-ийн бүтэн JSON |

Токеноо гаргах:

```powershell
py -3 threads_post.py token-export --out token.txt
notepad token.txt
```

Notepad дотор гарсан урт текстийг хуулж `THREADS_ACCESS_TOKEN` secret болгоно.
**Дараа нь token.txt файлыг устгана**:

```powershell
del token.txt
```

### Google Sheet-ийн төлөвийг автоматаар шинэчлэх

Пост Threads-д амжилттай орсны дараа Sheet-ийн `төлөв` нүдийг `posted`
болгохын тулд Google service account нэг удаа тохируулна.

1. Google Cloud Console дээр project үүсгээд **Google Sheets API**-г идэвхжүүлнэ.
2. **IAM & Admin → Service Accounts** хэсгээс service account үүсгэнэ.
3. Тухайн service account-д JSON key үүсгэж татна.
4. Google Sheet-ээ service account JSON доторх `client_email` хаягтай
   **Editor** эрхээр хуваалцана.
5. JSON файлын бүтэн агуулгыг GitHub Actions secret дээр
   `GOOGLE_SERVICE_ACCOUNT_JSON` нэрээр хадгална.

Service account нь унших, төлөв бичихэд ашиглагдана. Secret байхгүй үед
зөвхөн нийтэд нээлттэй CSV fallback ашиглана; Sheet хаалттай бол нийтлэл зогсоно. Тохируулсны дараа:

- амжилттай нийтлэгдсэн пост → `posted`
- нийтлэхэд алдаа гарсан пост → `failed`
- хэт хоцорч алгассан пост → `skipped`
- нийтэлсэн эсэх нь тодорхойгүй пост → `needs_review`

---

## 4. Токен автоматаар сунгах (сонголт, гэхдээ зөвлөж байна)

Токен 60 хоног тутам дуусдаг. Автоматаар сунгаж, шинэ утгыг Secret руу
бичихийн тулд нэг PAT хэрэгтэй.

`[ ]` https://github.com/settings/personal-access-tokens/new руу орно

`[ ]` **Repository access** → **Only select repositories** → `threads-autopost`

`[ ]` **Permissions** → **Repository permissions** → **Secrets** → **Read and write**

`[ ]` Үүсгээд утгыг хуулна

`[ ]` Repo Secrets дээр `GH_PAT` нэрээр нэмнэ

Энэ алхмыг алгасвал 50 хоног тутам `THREADS_ACCESS_TOKEN` secret-ээ гараар
шинэчлэх шаардлагатай болно. Ажиллагаа дуусах дөхөхөд анхааруулга өгнө.

---

## 5. Ажиллуулах

`[ ]` Repo → **Actions** таб

`[ ]` Зүүн талаас **Threads автомат постлолт** сонгоно

`[ ]` **Run workflow** товч дарж гараар нэг удаа ажиллуулна

`[ ]` Ажиллагааны бүртгэлийг нээж алхам бүрийг шалгана

Амжилттай бол цаашид 10 минут тутам өөрөө ажиллана.

---

## Хэрхэн ажилладаг вэ

1. Google Sheet-ийг уншаад бүх мөрийг шалгана. Алдаа байвал нийтлэхгүй.
2. GitHub дахь шинэ queue-г SHA шалгалттай нэгтгэнэ. Хуучин хуулбар төлөвийг дарж бичихгүй.
3. Нийтлэхээс өмнө `processing` төлөвийг GitHub-д хадгална.
4. Контейнер, нийтлэх оролдлого, эцсийн үр дүнг тус тус хадгална.
5. Хариу тодорхойгүй бол `needs_review` болгоно. Автоматаар дахин нийтлэхгүй.
6. Sheet-ийн төлөв болон сунгасан токеныг шинэчилнэ.

Cloudflare Worker мөн энэ workflow-г эхлүүлнэ. Нийтлэгч Python код нэг байна.
Шилжүүлэх дараалал, эрх, алдаа сэргээх заавар: [RELIABILITY.md](RELIABILITY.md).

## Локал болон GitHub хоёрын хамаарал

Live горим бүхэн GitHub дахь нэг ээлжийг ашиглана. Локалд `GITHUB_REPOSITORY`,
`GITHUB_TOKEN` (Contents: read/write) тохируулаад `run --live --sync` ажиллуулна.
`queue.json`-ыг хуучин локал хуулбараар git push хийж болохгүй.
`editor`, `add` нь локал туршилтын хуулбарыг өөрчилнө; автомат нийтлэлийн засварыг Sheet дээр хийнэ.

---

## Хугацааны нарийвчлал

GitHub-ийн хуваарь **5-15 минут хоцорч** ажиллах тохиолдол байдаг. Ачаалал
ихтэй үед 30 минут хүртэл хоцорч болно.

Үүнийг харгалзан workflow дотор хоцролтын хамгаалалтыг **90 минут** болгосон
(локал дээр мөн 90). Тиймээс 08:30-ны пост 08:35, 08:50-д ч гарч болно.

Яг тодорхой минутад гаргах шаардлагатай бол VPS ашиглах нь зөв.

---

## Алдаа засах

**Ажиллагаа улаанаар унтарсан бол**: Actions таб дээрээс тухайн ажиллагааг
нээж, аль алхам дээр унтарсныг харна.

| Алдаа | Шалтгаан |
|---|---|
| `THREADS_ACCESS_TOKEN орчны хувьсагч хоосон` | Secret нэмээгүй, эсвэл нэр буруу |
| `Sheet-ийг уншиж чадсангүй` | Sheet нээлттэй биш, эсвэл ID буруу |
| `Token has expired` | 60 хоног өнгөрсөн. Локал дээр дахин зөвшөөрөл аваад Secret шинэчилнэ |
| `GitHub queue HTTP 403` | Actions-ийн `contents: write` эрх болон branch rules-ийг шалгана |

**Түр зогсоох**: Cloudflare cron-ыг мөн зогсоогоод,  Actions таб → workflow → баруун дээд булангийн цэс →
**Disable workflow**

