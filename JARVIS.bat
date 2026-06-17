@echo off
cd /d "%~dp0"
title JARVIS AI - Baslatiliyor...
color 0b

echo ==================================================
echo   JARVIS AI VOICE ASSISTANT
echo ==================================================
echo.

:: --- Python kontrolü ---
set "PYTHON_EXE=python"
python --version >nul 2>&1
if %errorlevel% equ 0 goto python_ok

if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
    goto python_ok
)
echo [Hata]: Python bulunamadi!
pause & exit /b

:python_ok
echo [Sistem]: Python bulundu.

:: --- Sanal ortam kurulumu ---
if exist .venv goto venv_ok
echo [Kurulum]: Sanal ortam olusturuluyor...
"%PYTHON_EXE%" -m venv .venv
if %errorlevel% neq 0 ( echo [Hata]: Sanal ortam olusturulamadi! & pause & exit /b )

:venv_ok
call .venv\Scripts\activate.bat

:: --- Paket kurulumu (sadece eksik olanlar güncellenir, zaten kuruluysa anında geçer) ---
echo [Kutuphane]: Paket kontrolu yapiliyor...
pip install --quiet SpeechRecognition pyaudio winsdk ollama colorama websockets pywebview pygame-ce moderngl pywin32 panda3d PyQt5 psutil pynvml pygetwindow

:: --- Ollama performans değişkenleri ---
set OLLAMA_FLASH_ATTENTION=1
set OLLAMA_GPU_OVERHEAD=0
set OLLAMA_MAX_LOADED_MODELS=2
set OLLAMA_NUM_PARALLEL=1

:: --- Ollama servisi yeniden başlat (doğru env ile) ---
echo [Sistem]: Ollama servisi yeniden baslatiliyor...
taskkill /F /IM ollama.exe >nul 2>&1
timeout /t 2 /nobreak >nul
start /B "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve >nul 2>&1
echo [Sistem]: Ollama baslatildi, servisin hazir olması bekleniyor...
timeout /t 5 /nobreak >nul

:: --- GPU Önhazırlık: modelleri SSD'den VRAM'e yükle (Jarvis açılmadan önce) ---
echo.
echo [GPU Onhazirlik]: Yapay zeka modelleri GPU bellegine yukleniyor...
echo [GPU Onhazirlik]: Bu islem 30-60 sn surebilir. Lutfen bekleyin...
.venv\Scripts\python.exe preload.py
echo.

:: --- UI sunucuları arka planda başlat ---
echo [UI]: Iron Man HUD baslatiliyor...
start /B "" ".venv\Scripts\pythonw.exe" ui_server.py
start /B "" ".venv\Scripts\pythonw.exe" ui_app.py
timeout /t 2 /nobreak >nul

:: --- Jarvis ana motoru ---
echo ==================================================
echo   HAZIR! JARVIS BASLATILIYOR...
echo ==================================================
echo.
title JARVIS AI - Aktif
.venv\Scripts\python.exe jarvis.py

pause
