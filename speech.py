# speech.py - Jarvis Yapay Zeka Ses Motoru (STT & TTS)

import asyncio
import os
import sys
import msvcrt
import time
import speech_recognition as sr
import config
from colorama import init, Fore, Style
from winsdk.windows.media.speechsynthesis import SpeechSynthesizer
from winsdk.windows.media.playback import MediaPlayer

# Colorama kütüphanesini başlat
init(autoreset=True)

# Ses sentezi ve çalma için global değişkenler
_player = None
_synth = None
_calibrated = False

class SpeechInterrupted(Exception):
    """Kullanıcı bir tuşa basarak konuşmayı kestiğinde tetiklenir."""
    pass

def init_synthesis():
    """winsdk ses sentezleyicisini başlatır."""
    global _synth
    if _synth is None:
        _synth = SpeechSynthesizer()
        
        # Microsoft Tolga veya Microsoft Mobile Tolga sesini bul
        tolga_voice = None
        for voice in SpeechSynthesizer.all_voices:
            if "Tolga" in voice.display_name:
                tolga_voice = voice
                break
        
        if tolga_voice:
            _synth.voice = tolga_voice
            print(Fore.CYAN + f"[Ses Sistemi: {tolga_voice.display_name} aktif.]")
        else:
            print(Fore.YELLOW + "[Ses Sistemi: Microsoft Tolga bulunamadı, varsayılan Türkçe ses kullanılıyor.]")

def check_barge_in():
    """Konuşmayı kesmek için Space, Enter veya ESC tuşuna basılıp basılmadığını kontrol eder."""
    if msvcrt.kbhit():
        key = msvcrt.getch()
        # Windows'ta getch byte döndürür. Boşluk b' ', Enter b'\r' (veya b'\n'), ESC b'\x1b'
        if key in [b' ', b'\r', b'\n', b'\x1b']:
            # Klavye arabelleğinde kalan diğer karakterleri temizle
            while msvcrt.kbhit():
                msvcrt.getch()
            return True
    return False

async def speak(text):
    """Metni sentezler ve oynatır, sıfır gecikmeli araya girme (barge-in) desteği sunar."""
    global _player, _synth
    if not text or text.strip() == "":
        return
        
    init_synthesis()
    
    try:
        # Dinlemeyi engellemek için block_listening değişkenini True yap (Kendi Kendini Dinleme Kalkanı)
        config.block_listening = True
        
        # Metni sentezle
        stream = await _synth.synthesize_text_to_stream_async(text)
        
        if _player is None:
            _player = MediaPlayer()
            
        _player.set_stream_source(stream)
        _player.play()
        
        # Çalmanın başlamasını ve bitmesini bekle
        await asyncio.sleep(0.15) # short delay to register the playback state
        
        session = _player.playback_session
        # Oynatma durumları: 0 = Yok, 1 = Açılıyor, 2 = Arabelleğe Alınıyor, 3 = Oynatılıyor, 4 = Duraklatıldı
        while session.playback_state in [1, 2, 3]:
            # Araya girme tuş kontrolü
            if check_barge_in():
                _player.pause()
                print(Fore.RED + "\n[Konuşma Kesildi efendim, dinliyorum...]")
                raise SpeechInterrupted("Interrupted by user.")
            await asyncio.sleep(0.05)
            
    finally:
        # Yankı engelleme süresi için kalkanı 1.0 saniye daha aktif tut
        await asyncio.sleep(1.0)
        config.block_listening = False

def check_whisper_cache():
    """Whisper modelinin yerel Whisper önbellek klasöründe olup olmadığını kontrol eder."""
    user_home = os.path.expanduser("~")
    whisper_cache_path = os.path.join(user_home, ".cache", "whisper")
    model_file = f"{config.WHISPER_MODEL_NAME}.pt"
    
    model_cached = False
    if os.path.exists(whisper_cache_path):
        if model_file in os.listdir(whisper_cache_path):
            model_cached = True
            
    if model_cached:
        print(Fore.GREEN + f"[Ön Yükleme: Model '{config.WHISPER_MODEL_NAME}' sisteminizde zaten yüklü, önbellekten yükleniyor...]")
    else:
        print(Fore.YELLOW + f"[Yükleme: Whisper model '{config.WHISPER_MODEL_NAME}' ilk kez indiriliyor, bu işlem internet hızınıza bağlı olarak biraz sürebilir...]")


def listen():
    """Mikrofonu dinler ve çevrimiçi Google STT kullanarak yazıya döker."""
    global _calibrated
    
    # block_listening veya mic_muted aktifse bekle
    while config.block_listening or getattr(config, "mic_muted", False):
        time.sleep(0.05)
        
    r = sr.Recognizer()
    r.pause_threshold = 2.0
    r.phrase_threshold = 0.15
    r.energy_threshold = 150
    r.dynamic_energy_threshold = False
    
    with sr.Microphone() as source:
        if not _calibrated:
            print(Fore.YELLOW + "\n[Sistem: Mikrofon kalibrasyonu yapılıyor (1.0 sn)...]")
            r.adjust_for_ambient_noise(source, duration=1.0)
            if r.energy_threshold > 250:
                r.energy_threshold = 200
            _calibrated = True
            print(Fore.GREEN + f"[Sistem: Kalibrasyon tamamlandı. Eşik değeri: {r.energy_threshold:.0f}]")
            check_whisper_cache()
            
        sys.stdout.write("\r" + Fore.BLUE + "[Dinleniyor... Konuşun efendim] " + Style.RESET_ALL)
        sys.stdout.flush()
        
        try:
            audio = r.listen(source, timeout=10, phrase_time_limit=25)
        except sr.WaitTimeoutError:
            return ""
        except Exception as e:
            return ""
            
    # Kendi kendini dinleme kalkanını tekrar kontrol et
    if config.block_listening:
        return ""
        
    sys.stdout.write("\r" + Fore.YELLOW + "[Sinyal Algılandı, çözümleniyor...]      " + Style.RESET_ALL)
    sys.stdout.flush()
    
    try:
        # Çevrimiçi Google STT kullanarak deşifre et — sıfır CPU yükü, anında ve mükemmel Türkçe
        sys.stdout.write("\r" + Fore.CYAN + "[🌐 Google STT: Çevrimiçi deşifre ediliyor...]  " + Style.RESET_ALL)
        sys.stdout.flush()
        text = r.recognize_google(audio, language="tr-TR").strip()
        
        # Tek satırlık yazdırma alanını temizle
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()
        return text
    except Exception as e:
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()
        return ""
