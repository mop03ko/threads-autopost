# Windows дээр суулгах заавар

README.md доторх тушаалууд Linux/Mac-д зориулагдсан. Windows дээр
дараах ялгаатай тушаалуудыг ашиглана.

---

## Тушаалын харьцуулалт

| Заавар дээр | Windows дээр |
|---|---|
| `python3` | `py -3` |
| `pip install ...` | `py -3 -m pip install ...` |
| `cp .env.example .env` | `copy .env.example .env` |
| `pwd` | `cd` |
| `which python3` | `where py` |
| `crontab -e` | **Task Scheduler** (доор үзнэ үү) |
| bash | **PowerShell** |

---

## 1. Python байгаа эсэхийг шалгах

**Эхлэх** товч дарж `PowerShell` гэж бичээд нээнэ.

```powershell
py -3 --version
```

`Python 3.11.x` гэх мэт хариу гарвал бэлэн. Алдаа гарвал:

1. https://www.python.org/downloads/ орж татна
2. Суулгах үед **"Add python.exe to PATH"** нүдийг **заавал** тэмдэглэнэ
3. PowerShell-ээ хааж дахин нээгээд дээрх тушаалыг дахин шалгана

---

## 2. Файлаа задлах

`threads-autopost.zip`-ийг **Downloads** доторх ZIP дээр баруун товч дарж
**Extract All** сонгоно.

Санал болгох байршил (замд монгол үсэг, хоосон зай байхгүй байх нь дээр):

```
C:\threads-autopost
```

---

## 3. Тэр хавтас руу орох

PowerShell дээр:

```powershell
cd C:\threads-autopost
```

Зөв газартаа байгаа эсэхийг шалгана:

```powershell
dir
```

`threads_post.py`, `queue.json`, `README.md` харагдах ёстой.

---

## 4. Хамаарлаа суулгах

```powershell
py -3 -m pip install -r requirements.txt
```

**Алдаа гарвал:**

`pip` олдохгүй бол:
```powershell
py -3 -m ensurepip --upgrade
```

Эрхийн алдаа гарвал:
```powershell
py -3 -m pip install --user -r requirements.txt
```

---

## 5. Тохиргооны файл үүсгэх

```powershell
copy .env.example .env
notepad .env
```

Notepad нээгдэнэ. Гурван мөрийг бөглөөд **Ctrl+S** дарж хадгална:

```
THREADS_APP_ID=таны_апп_id
THREADS_APP_SECRET=таны_нууц_түлхүүр
THREADS_REDIRECT_URI=https://localhost/threads-auth
```

---

## 6. Шалгах

```powershell
py -3 threads_post.py doctor
py -3 threads_post.py show --next 3
```

---

## 6a. Google Sheet-ээс засах (сонголт)

Sheet-ээ **Share → Anyone with the link → Viewer** болгоод, `.env` дотор
`THREADS_SHEET_ID` мөрийг бөглөнө. Дараа нь:

```powershell
py -3 threads_post.py sync
```

`run.bat` дотор `--sync` туг аль хэдийн орсон тул Task Scheduler ажиллах
бүрд Sheet-ээс автоматаар татна. Утаснаасаа засварласан пост дараагийн
ажиллагаанд шууд тусна.

---

## 6b. Постоо засах (вэб интерфейс)

```powershell
py -3 threads_post.py editor
```

Браузер автоматаар нээгдэнэ. Бичвэр, цаг, төлөв, зургийн холбоосыг эндээс
засна. JSON гараар засах шаардлагагүй.

Хаахдаа PowerShell цонхон дээр **Ctrl+C** дарна.

---

## 7. Эрх авах

```powershell
py -3 threads_post.py auth-url
```

Хэвлэгдсэн холбоосыг браузерт нээж зөвшөөрөөд, кодоо хуулж:

```powershell
py -3 threads_post.py exchange --code ЭНД_КОДОО
```

---

## 8. Туршилт

```powershell
py -3 threads_post.py run
```

`--live` туггүй тул юу ч нийтлэгдэхгүй.

---

## 8b. Хоцорсон постыг гараар нийтлэх

```powershell
py -3 threads_post.py list                 # id-г олно
py -3 threads_post.py run --live --id 1    # тэр постыг яг одоо
```

Хоцорсон бүгдийг нийтлэх бол:

```powershell
py -3 threads_post.py run --live --force
```

---

## 9. Автоматжуулах (Task Scheduler)

Windows дээр `crontab` байхгүй. Оронд нь **Task Scheduler** ашиглана.
Багцад `run.bat` файл бэлэн орсон.

### Хялбар арга: нэг тушаалаар бүртгэх

PowerShell-ийг **Administrator эрхээр** нээнэ (Эхлэх → PowerShell дээр
баруун товч → **Run as administrator**), дараа нь:

```powershell
schtasks /create /tn "ThreadsAutoPost" /tr "C:\threads-autopost\run.bat" /sc minute /mo 10 /f
```

Энэ нь 10 минут тутам ажиллах даалгавар үүсгэнэ.

**Шалгах:**

```powershell
schtasks /query /tn "ThreadsAutoPost"
```

**Гараар нэг удаа ажиллуулж турших:**

```powershell
schtasks /run /tn "ThreadsAutoPost"
```

Дараа нь бүртгэлээ харна:

```powershell
Get-Content C:\threads-autopost\cron.log -Tail 20
```

**Устгах бол:**

```powershell
schtasks /delete /tn "ThreadsAutoPost" /f
```

### Гар аргаар (Task Scheduler цонхоор)

1. Эхлэх → `Task Scheduler` бичиж нээнэ
2. Баруун талаас **Create Task**
3. **General** таб: нэр `ThreadsAutoPost`
4. **Triggers** таб → **New**:
   - Begin the task: `On a schedule`
   - `Daily`, давтах: **Repeat task every 10 minutes** for a duration of **1 day**
5. **Actions** таб → **New**:
   - Action: `Start a program`
   - Program/script: `C:\threads-autopost\run.bat`
6. **Conditions** таб: "Start the task only if the computer is on AC power"
   нүдийг **арилгана** (ноутбук батерейгаар ажиллаж байхад ч постлохын тулд)
7. **OK** дарж хадгална

---

## Windows-т онцгой анхаарах зүйлс

**Компьютер унтарсан үед пост тавигдахгүй.**
Windows унтуулах (sleep) горимд орсон ч даалгавар ажиллахгүй. Сонголтууд:

- Тохиргоо → Систем → Тэжээл → **Унтуулах: Хэзээ ч үгүй**
- Эсвэл сард 5 доллароос эхлэх VPS ашиглах (тогтвортой хувилбар)

**Скрипт 90 минутын хамгаалалттай.**
Компьютер унтраад эргэж асахад 90 минутаас их хоцорсон постыг алгасна.
Тиймээс шөнө унтраасан ч өглөөний пост буруу цагт гарахгүй.

**Замд монгол үсэг бүү оруул.**
`C:\Хэрэглэгч\Ажил\...` гэх мэт зам зарим тохиолдолд алдаа өгдөг.
`C:\threads-autopost` гэсэн энгийн зам найдвартай.

**Notepad UTF-8.**
`.env` эсвэл `queue.json` файлыг Notepad-аар засвал хадгалахдаа
**Encoding: UTF-8** сонгоно. Монгол үсэг эвдрэхээс сэргийлнэ.
Илүү сайн нь VS Code ашиглах (танд суусан байна).
