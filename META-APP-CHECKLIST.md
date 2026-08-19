# Meta апп үүсгэх шалгах хуудас

Энэ хуудсыг нээлттэй байлгаад, алхам бүрийг гүйцэтгэсний дараа `[ ]`-г `[x]` болгож тэмдэглэнэ.
Нийт хугацаа: **25-30 минут**.

---

## Алхам 1. Апп үүсгэх

`[ ]` https://developers.facebook.com/apps руу орно

`[ ]` Meta бүртгэлээрээ нэвтэрнэ (Facebook данс шаардлагатай)

`[ ]` Анх удаа бол хөгжүүлэгчийн бүртгэл идэвхжүүлнэ (утасны дугаар баталгаажуулна)

`[ ]` **Create app** товч дарна

`[ ]` **App name**: доорх нэрийг хуулж тавина. Энэ нэр хэнд ч харагдахгүй.

```
mop03ko-autopost
```

`[ ]` **Contact email**: `ebbtbstar@gmail.com`

`[ ]` Use case асуухад **"Access the Threads API"** сонгоно

> Хэрэв энэ сонголт харагдахгүй бол **Other** → **Business** сонгоод,
> апп үүссэний дараа Products хэсгээс **Threads** нэмнэ.

`[ ]` **Create app** дарж баталгаажуулна

---

## Алхам 2. Буцах хаяг тохируулах

`[ ]` Зүүн цэс → **Threads** → **Settings**

Энэ хуудсан дээр **ГУРВАН талбар бүгд бөглөгдсөн байх ёстой**. Аль нэг нь
хоосон бол Meta `Form can't be saved` гэсэн алдаа өгнө.

`[ ]` **Redirect Callback URLs**:

```
https://localhost/threads-auth
```

`[ ]` **Uninstall Callback URL**:

```
https://localhost/threads-uninstall
```

`[ ]` **Delete Callback URL**:

```
https://localhost/threads-delete
```

> **ХАМГИЙН ЧУХАЛ**: Redirect Callback URL нь энгийн текст талбар биш.
> Хаягаа бичсэний дараа **Enter дарж** хаяг нь жижиг хайрцаг (chip) болж
> хувирсныг заавал шалгана. Enter дарахгүй бол Meta уг хаягийг хүлээж
> аваагүй гэж үзэж, форм хадгалагдахгүй.
>
> Сүүлийн хоёр хаяг ажиллах шаардлагагүй. Meta зүгээр л хоосон байхыг
> зөвшөөрдөггүй.

`[ ]` **Save changes** дарна

---

## Алхам 3. Өөрийгөө Tester болгох (энэ алхмыг алгасвал бүх зүйл алдаа өгнө)

`[ ]` Зүүн цэс → **App roles** → **Roles**

`[ ]` **Threads Testers** хэсгээс **Add people** дарна

`[ ]` Хэрэглэгчийн нэрээ бичнэ:

```
mop03ko
```

`[ ]` Урилга илгээнэ

`[ ]` https://www.threads.com/settings/account руу орно

`[ ]` **Website permissions** → **Invites** хэсгээс урилгыг **зөвшөөрнө**

`[ ]` Meta апп руу буцаж, статус нь **Accepted** болсныг шалгана

---

## Алхам 4. Түлхүүрээ авах

> **МАШ ЧУХАЛ**: Meta апп бүрд **хоёр өөр багц түлхүүр** байдаг.
>
> | Хаана | Нэр | Threads-д хэрэглэх үү |
> |---|---|---|
> | App settings → Basic | App ID / App secret | **ҮГҮЙ** |
> | Threads → Settings | **Threads App ID / Threads App secret** | **ТИЙМ** |
>
> Буруу түлхүүр ашиглавал зөвшөөрөл авах үед дараах алдаа гарна:
> `Authorization Failed: No app ID was sent with the request` (код 4476002)

`[ ]` Зүүн цэс → **Threads** → **Settings** (App settings → Basic БИШ)

`[ ]` Хуудсан дээрх **Threads App ID**-г хуулж доор бичнэ:

```
THREADS_APP_ID = ________________________________
```

`[ ]` **Threads App secret** хажуугийн **Show** дарж, нууц үгээ оруулаад хуулна:

```
THREADS_APP_SECRET = ________________________________
```

> **Анхаар**: App secret бол таны данс руу нэвтрэх түлхүүр. Хэнтэй ч
> хуваалцахгүй, чатад бичихгүй, зурган дээр харуулахгүй. Зөвхөн `.env`
> файлдаа хадгална. Санамсаргүй задарсан бол Meta дээрээс **Reset** дарна.

---

## Алхам 5. Хэрэгсэлдээ холбох

`[ ]` `threads-autopost` хавтас руу орно

`[ ]` `.env.example`-г хуулж `.env` нэртэй болгоно:

```bash
cp .env.example .env
```

`[ ]` `.env` файлыг нээж дээрх хоёр утгаа бичнэ

`[ ]` Хамаарлаа суулгана:

```bash
pip install -r requirements.txt
```

`[ ]` Шалгана:

```bash
python3 threads_post.py doctor
```

Эхний гурван мөр `[OK ]` болсон байх ёстой.

---

## Алхам 6. Эрх авах

`[ ]` Зөвшөөрлийн холбоос гаргана:

```bash
python3 threads_post.py auth-url
```

`[ ]` Холбоосыг браузерт нээж, `mop03ko` дансаараа **зөвшөөрнө**

`[ ]` Браузер `https://localhost/threads-auth?code=AQ...#_` руу шилжинэ.
Хуудас нээгдэхгүй нь хэвийн.

`[ ]` Хаягийн мөрнөөс `code=` ба `#` хоёрын хоорондох текстийг хуулна

`[ ]` Токен болгон солино:

```bash
python3 threads_post.py exchange --code ЭНД_КОДОО_ТАВИНА
```

`[ ]` `@mop03ko` гэсэн нэр хэвлэгдвэл амжилттай

---

## Алхам 7. Туршилт

`[ ]` Бүх зүйл зөв эсэхийг шалгана:

```bash
python3 threads_post.py doctor
```

`[ ]` Туршилтын горимд ажиллуулна (юу ч нийтлэгдэхгүй):

```bash
python3 threads_post.py run
```

`[ ]` Ээлжээ харна:

```bash
python3 threads_post.py list
```

---

## Алхам 8. Автоматжуулах

`[ ]` Хавтасныхаа замыг тэмдэглэнэ:

```bash
pwd
which python3
```

```
ЗАМ = ________________________________
PYTHON = ________________________________
```

`[ ]` `crontab -e` дээр доорх мөрийг нэмнэ (ЗАМ, PYTHON-оо солино):

```cron
*/10 * * * * cd ЗАМ && PYTHON threads_post.py run --live >> cron.log 2>&1
```

`[ ]` Хадгалж гарна

`[ ]` Эхний пост 2026.08.19-ний 08:30-д тавигдана. Тэр өдөр шалгана.

---

## Түгээмэл алдаа: `No app ID was sent with the request`

```
{"error_message":"Authorization Failed: No app ID was sent with the request.","error_code":4476002}
```

**Шалтгаан**: Meta-гийн ерөнхий App ID-г ашигласан. Threads API нь тусдаа
**Threads App ID** шаарддаг.

**Засах**:

1. Meta апп → зүүн цэс → **Threads** → **Settings**
2. Тэндээс **Threads App ID** болон **Threads App secret** хуулна
3. `.env` файлын хоёр мөрийг эдгээрээр солино
4. Дахин оролдоно:

```powershell
py -3 threads_post.py auth-url
```

> Хоёр ID-г ялгах арга: App settings → Basic дээрх ID нь Threads → Settings
> дээрхтэй **өөр тоо** байна. Хоёуланг нь харьцуулж шалгаарай.

---

## Түгээмэл алдаа: `Form can't be saved`

Meta-гийн энэ алдаа нь **аль талбар буруу байгааг хэлдэггүй**. Дарааллаар шалгана:

**Threads → Settings хуудсан дээр бол:**

1. Гурван хаягийн талбар бүгд бөглөгдсөн үү (Redirect, Uninstall, Delete)
2. Redirect хаягийг бичээд **Enter дарсан** уу. Chip болж хувирсан байх ёстой
3. Бүгд `https://` эхэлсэн үү (`http://` зөвшөөрөхгүй)
4. Хоосон зай, монгол үсэг, кирилл тэмдэгт орсон эсэхийг шалгана

**App settings → Basic хуудсан дээр бол:**

1. **Privacy Policy URL** бөглөгдсөн үү (заавал, ажиллах хаяг байх ёстой)
2. **App icon** оруулсан уу (1024x1024 px)
3. **Category** сонгосон уу
4. **App domains** хэсэг Site URL-тэй зөрчилдөж байгаа эсэхийг шалгана

> Privacy Policy URL хэрэгтэй бол үнэгүй үүсгэж болно:
> termsfeed.com эсвэл privacypolicies.com. Эсвэл GitHub Pages дээр
> энгийн хуудас тавьж болно.

---

## Гацвал

Алдааны мессежээ надад бүтнээр нь хуулж илгээнэ үү. App secret агуулсан
мөрийг л хасаад явуулна. Ямар алхам дээр гацсаныг хамт бичвэл хурдан
шийднэ.
