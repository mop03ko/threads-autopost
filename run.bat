@echo off
REM Threads автомат постлогч - Windows Task Scheduler-т зориулсан
REM Энэ файл өөрийн байрлаж буй хавтас руу шилжээд скриптийг ажиллуулна.

cd /d "%~dp0"

py -3 threads_post.py run --live --sync >> cron.log 2>&1

REM Хэрэв "py" тушаал ажиллахгүй бол дээрх мөрийг тайлбар болгоод
REM доорхийг идэвхжүүлнэ:
REM python threads_post.py run --live --sync >> cron.log 2>&1
