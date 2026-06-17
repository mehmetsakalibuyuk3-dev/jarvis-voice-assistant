# simulate_conversation.py - Jarvis Seviye 2+ için kapsamlı çok turlu diyalog çalıştırıcısı
import asyncio
import sys
import os
import re

# Bu betiğin dizinini sys.path'e ekle
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import jarvis
import speech
import config
import ollama

test_inputs = [
    "Merhaba.",
    "vs code aç",
    "youtube'u aç",
    "google'ı aç",
    "google'da Victor Osimhen ara",
    "youtube'da Galatasaray marşı oynat",
    "test simülasyonunu çalıştır",
    "Bugün nasılsın?",
    "Haftaya çarşamba saat 20:00'de maça gideceğim, takvime kaydet.",
    "Yakın zamanda planımız var mı, listeler misin?",
    "Benim tuttuğum takım hangisi biliyor musun?",                               # tuttugu_takim tercihini kontrol et
    "Benim en sevdiğim renk ne?",                                                  # En sevdiği rengi sor (bilinmiyor)
    "En sevdiğim renk Sarı Kırmızı.",                                              # En sevdiği rengi öğret
    "Şimdi tekrar soruyorum, benim en sevdiğim renk hangisiymiş?",                 # En sevdiği rengi sor (öğrenildi)
    "Pazartesi günü akşam saat 8.00'de türkçe final sabrın var.",                  # Fonetik Whisper kayması 1
    "Çarşamba günü akşam saat 9'da matematik finalsin ardında var.",               # Fonetik Whisper kayması 2
    "Sınavlarım ne zaman, hangisi önce?",                                          # Tarih karşılaştırma sorusu
    "çayı neden hatırlatmadın bana?",                                              # Şikayet sitem kalkanı testi
    "2 numaralı planımı iptal et.",                                                # Belirli dizin silme testi
    "Planlarımı tekrar listeler misin, hangisi silindi?",                          # Silmeyi doğrula
    "Yarın sabah saat 10:00'da diş randevum var, not al.",                         # Randevu isim normalleştirici testi
    "Benim adımı biliyor musun?",                                                  # 'name' tercihini kontrol et
    "tüm planları temizle.",                                                       # Temizleme testi
    "sistemi kapat."                                                               # Çıkış
]

input_index = 0

def mock_listen():
    global input_index
    if input_index < len(test_inputs):
        inp = test_inputs[input_index]
        input_index += 1
        return inp
    return ""

async def mock_speak(text):
    # TTS oynatma simülasyonu için dinamik çıktı
    return False

# Başsız (headless) simülasyon testi sırasında fiziksel pencerelerin açılmasını önlemek için subprocess.Popen'ı taklit et (mock)
import subprocess
def mock_popen(args, *extra_args, **kwargs):
    safe_print = getattr(jarvis, 'safe_print', print)
    from colorama import Fore, Style
    safe_print(Fore.YELLOW + f"[MOCK RUN COMMAND]: {args}" + Style.RESET_ALL)
    
    # Yürütme çıktısını simüle etmek için sahte bir işlem nesnesi döndür
    class MockProcess:
        returncode = 0
        def communicate(self, timeout=None):
            return "Simulated Frame Output:\n  frame  0: state=IDLE      vol=0.000 speaking=False voiceGrow=0.000 scale=1.000\n  frame  1: state=SPEAKING  vol=0.050 speaking=True  voiceGrow=0.180 scale=1.126\nTEST COMPLETED SUCCESSFUL", ""
        def kill(self):
            pass
    return MockProcess()

# speech modülünü ve subprocess'i dinamik olarak yamala
speech.listen = mock_listen
speech.speak = mock_speak
jarvis.subprocess.Popen = mock_popen

async def run_simulation():
    # jarvis'in içe aktarmalarındaki speech.listen ve speech.speak işlevlerini de geçersiz kıl
    jarvis.speech.listen = mock_listen
    jarvis.speech.speak = mock_speak
    
    # Temiz bir test için yeni bir bellek başlat
    memory = jarvis.load_memory()
    memory["reminders"] = []
    memory["user_preferences"] = {
        "tuttugu_takim": "Galatasaray",
        "name": "Mustafa Efendi"
    }
    jarvis.save_memory(memory)
    
    print("==================================================")
    print("  JARVIS SEVİYE 2+ EXHAUSTIVE MULTI-TURN SIMULATION")
    print("==================================================")
    
    try:
        await jarvis.main()
    except KeyboardInterrupt:
        print("\n[Simülasyon]: Klavye kesmesi ile kapatıldı.")
    except Exception as e:
        print(f"\n[Simülasyon Hatası]: {e}")
        
    print("\n==================================================")
    print("      SİMÜLASYON SÜRECİ BAŞARIYLA TAMAMLANDI")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_simulation())
