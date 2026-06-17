# jarvis.py - Jarvis Yapay Zeka Asistanı Ana Motoru

import asyncio
import os
import sys
import subprocess
import datetime
import json
import re
import speech_recognition as sr
import ollama
from colorama import init, Fore, Style
import config
import speech
import threading
import time
import queue
from vectordb import VectorDB
import websearch
import websockets
import pyautogui
import win32clipboard
import pygetwindow as gw

# Arayüz Durumu Yayını İçin Global Kuyruk
ui_queue = asyncio.Queue()

async def ui_websocket_worker():
    """Arayüz Sunucusuna durum güncellemelerini göndermek ve girdileri dinlemek için arka plan görevi"""
    while True:
        try:
            async with websockets.connect("ws://127.0.0.1:7474") as ws:
                async def sender():
                    while True:
                        msg = await ui_queue.get()
                        await ws.send(json.dumps(msg))
                        ui_queue.task_done()

                async def receiver():
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            if data.get("type") == "control":
                                action = data.get("action")
                                if action == "toggle_mute":
                                    config.mic_muted = not config.mic_muted
                                    publish_ui("mic_status", "muted" if config.mic_muted else "active")
                                    print(Fore.YELLOW + f"\n[Sistem Kontrol: Mikrofon {'KAPATILDI' if config.mic_muted else 'AÇILDI'}]")
                                elif action == "shutdown":
                                    print(Fore.RED + "\n[Sistem Kontrol: Kapatma isteği alındı...]")
                                    await jarvis_speak("Anlaşıldı Mustafa Efendim, sistemi kapatıyorum.")
                                    await asyncio.sleep(4.0)
                                    os._exit(0)
                        except Exception as e:
                            print(Fore.RED + f"[WS Alıcı Hatası: {e}]")

                await asyncio.gather(sender(), receiver())
        except Exception:
            await asyncio.sleep(2)

def publish_ui(msg_type, value=""):
    """Engelleme yapmadan Arayüz kuyruğuna bir güncelleme gönderir."""
    try:
        ui_queue.put_nowait({"type": msg_type, "value": value})
    except Exception:
        pass

async def jarvis_speak(text, stream_bubble=False):
    """Maksimum akıcılıkla otomatik olarak konuşmak ve arayüz durumunu güncellemek için sarmalayıcı.
    stream_bubble=True: Arayüz girdisi akış tarafından zaten oluşturuldu, mükerrer addChatEntry'yi atla.
    """
    if not text or text.strip() == "":
        return
    publish_ui("state", "SPEAKING")
    # Only push a full 'response' message if this is NOT a streaming sentence
    # (streaming sentences are already shown token-by-token in the UI)
    if not stream_bubble:
        publish_ui("response", text)
    try:
        await speech.speak(text)
    finally:
        publish_ui("state", "IDLE")

async def system_stats_worker():
    """Her 3 saniyede bir saf Python (sıfır SSD diski I/O'su) aracılığıyla CPU, RAM, VRAM istatistiklerini getiren arka plan döngüsü."""
    import ctypes

    # --- VRAM altyapısı: pynvml (NVIDIA) dene, sonra wmi (AMD/Intel), ardından sessiz geri çekilme ---
    _nvml_ok = False
    _gpu_name = "GPU"
    _vram_total_bytes = 12 * 1024 * 1024 * 1024  # default 12 GB

    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        _gpu_name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(_gpu_name, bytes):
            _gpu_name = _gpu_name.decode()
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        _vram_total_bytes = mem_info.total
        _nvml_ok = True
    except Exception:
        pass

    def _get_vram_pynvml():
        try:
            import pynvml
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            used = mem_info.used
            pct = round(used / _vram_total_bytes * 100, 1)
            mb = round(used / 1024 / 1024, 0)
            return pct, int(mb)
        except Exception:
            return 0.0, 0

    while True:
        try:
            import psutil

            # CPU — engellemesiz, çekirdek sayaçlarını kullanır (sıfır disk I/O'su)
            cpu_pct = psutil.cpu_percent(interval=None)

            # RAM — işletim sistemi bellek yöneticisine tek bir sistem çağrısı
            vm = psutil.virtual_memory()
            ram_pct = round(vm.percent, 1)

            # VRAM — işlem içi kütüphane çağrısı, alt işlem yok
            if _nvml_ok:
                vram_pct, vram_mb = await asyncio.to_thread(_get_vram_pynvml)
            else:
                vram_pct, vram_mb = 0.0, 0

            data = {
                "cpu": round(cpu_pct, 1),
                "ram": ram_pct,
                "vram": vram_pct,
                "vram_mb": vram_mb,
                "gpu_name": _gpu_name,
            }
            publish_ui("sys_stats", data)
        except Exception:
            pass
        await asyncio.sleep(3)


# Colorama kütüphanesini başlat
init(autoreset=True)

JARVIS_BANNER = f"""
{Fore.CYAN}{Style.BRIGHT}======================================================================
     ____.  _____  __________   ____.___  _________
    |    | /  _  \\ \\______   \\ |    |   |/   _____/
    |    |/  /_\\  \\ |       _/ |    |   |\\_____  \\ 
/\\__|    /    |    \\|    |   \\ |    |   |/        \\
\\________\\____|__  /|____|_  / |______ /_______  /
                 \\/        \\/        \\/        \\/ 
                  {Fore.WHITE}YOUR OFF-LINE AI EXECUTIVE ASSISTANT
======================================================================
"""

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")

def load_memory():
    """Eksikse başlatarak yerel diskten memory.json dosyasını yükler."""
    if not os.path.exists(MEMORY_FILE):
        default_data = {
            "user_preferences": {
                "tuttugu_takim": "Galatasaray"
            },
            "reminders": []
        }
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)
        return default_data
    
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"user_preferences": {"tuttugu_takim": "Galatasaray"}, "reminders": []}

def save_memory(data):
    """Verileri memory.json dosyasına geri kaydeder."""
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(Fore.RED + f"[Hafıza Kayıt Hatası: {e}]")

def safe_print(text, end="\n"):
    """Türkçe UTF-8 karakterleri için konsol yazdırma uyumluluğunu garanti eder."""
    try:
        print(text, end=end, flush=True)
    except Exception:
        # Belirli karakterleri (emoji gibi) desteklemeyen terminaller için yedek çözüm
        try:
            import sys
            enc = sys.stdout.encoding or 'utf-8'
            clean_text = text.encode(enc, errors='ignore').decode(enc)
            print(clean_text, end=end, flush=True)
        except Exception:
            pass

def clean_for_comparison(text):
    """Son derece kararlı dize kontrolü için Türkçe karakterleri normalize eder ve noktalama işaretlerini temizler."""
    if not text:
        return ""
    text = text.lower()
    # Noktalama işaretlerini dinamik olarak temizle
    text = re.sub(r'[.,:;!?\'"\'"`\-–—_+*\/\\(\\)\\[\\]{}]', '', text)
    replacements = {
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'â': 'a', 'î': 'i', 'û': 'u'
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)
    return text.strip()

def set_clipboard_text(text):
    """Türkçe karakterleri mükemmel şekilde desteklemek için win32clipboard kullanarak metni panoya kopyalar."""
    try:
        win32clipboard.OpenClipboard()
        old_text = None
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            old_text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return old_text
    except Exception as e:
        print(Fore.RED + f"[Pano Kopyalama Hatası: {e}]")
        return None

def restore_clipboard_text(old_text):
    """Eski pano içeriğini geri yükler."""
    if old_text is None:
        return
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(old_text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
    except Exception:
        pass

def clean_typing_prefixes(text):
    """Yazılacak metinden yaygın konuşma öneklerini kaldırır."""
    prefixes = [
        r"^(?:arama|yazı|yazi)\s+(?:çubuğuna|cubuguna|yerine|alanına|alanina|kutusuna)\s*",
        r"^(?:youtube|google|tarayıcı|tarayici)(?:\'a|\'e|a|e|da|de| \'\s*a| \'\s*e)?\s*",
        r"^(?:ekrana|metin\s+olarak|yazılı\s+olarak|bana|lütfen|lutfen|şunu|sunu|şöyle|soyle)\s*",
    ]
    clean_text = text
    for pref in prefixes:
        clean_text = re.sub(pref, "", clean_text, flags=re.IGNORECASE)
    return clean_text.strip()

def extract_typing_text(user_speech):
    """Kullanıcının sesli komutundan yazılacak temiz metni çıkarır, komut öneklerini ve soneklerini temizler."""
    # Pattern 1: "<text> yazıp/yazip [optional search words]"
    m = re.search(r"^(.+?)\s+(?:yazıp|yazip)(?:\s+.*)?$", user_speech, flags=re.IGNORECASE)
    if m:
        return clean_typing_prefixes(m.group(1).strip())
        
    # Pattern 2: "<text> yaz ve [optional search words]"
    m = re.search(r"^(.+?)\s+yaz\s+ve(?:\s+.*)?$", user_speech, flags=re.IGNORECASE)
    if m:
        return clean_typing_prefixes(m.group(1).strip())
        
    # Pattern 3: "<text> yaz/yazın/yazsana"
    m = re.search(r"^(.+?)\s+(?:yaz|yazın|yazin|yazsana)(?:\s+(?:lütfen|lutfen|misin|misiniz|sana|zahmet))?$", user_speech, flags=re.IGNORECASE)
    if m:
        return clean_typing_prefixes(m.group(1).strip())
        
    # Pattern 4: "yaz/yazdır/yazsana <text>"
    m = re.search(r"^(?:yaz|yazdır|yazdir|yazsana)\s+(.+)$", user_speech, flags=re.IGNORECASE)
    if m:
        return clean_typing_prefixes(m.group(1).strip())
        
    return None

async def ensure_target_window_active():
    """Eğer aktif pencere Jarvis'in kendisiyse, odağı otomatik olarak tarayıcıya veya aktif uygulamaya geçirir."""
    try:
        win = gw.getActiveWindow()
        active_title = win.title.lower() if (win and win.title) else ""
        
        # Aktif pencere Jarvis, komut satırı veya boşsa odağı değiştirmeliyiz
        if not active_title or any(k in active_title for k in ["jarvis", "agi hud", "voice assistant", "select windows powershell"]):
            # Search for browser or other common applications
            target_win = None
            for w in gw.getAllWindows():
                if w.title:
                    t_lower = w.title.lower()
                    # Tarayıcı, metin düzenleyici veya yaygın bir uygulama olup olmadığını kontrol et
                    is_candidate = any(b in t_lower for b in [
                        "chrome", "edge", "firefox", "brave", "opera", "yandex", "browser",
                        "youtube", "google", "visual studio code", "code", "spotify", "discord", "notepad"
                    ])
                    # Jarvis'in kendisine odaklanmadığımızdan emin ol
                    if is_candidate and not any(k in t_lower for k in ["jarvis", "agi hud", "voice assistant"]):
                        target_win = w
                        break
            
            if target_win:
                safe_print(Fore.YELLOW + f"[Sistem: Odak '{target_win.title}' penceresine aktarılıyor...]")
                try:
                    target_win.activate()
                except Exception:
                    try:
                        target_win.restore()
                        target_win.activate()
                    except Exception:
                        pass
                await asyncio.sleep(0.25)  # Wait for OS window transition
    except Exception as e:
        print(f"[Odağı Aktarma Hatası: {e}]")

def correct_phonetic_mishearings(text):
    """Whisper Türkçe fonetik yanlış algılamalarını otomatik olarak düzeltir (Seviye 2+ yükseltmesi)."""
    if not text:
        return ""
    
    # Boşlukları standartlaştır
    cleaned = re.sub(r'\s+', ' ', text).strip()
    
    replacements = {
        # Yüksek öncelikli çok kelimeli yanlış algılamalar
        r"\byağ\s+git\b": "yahu git",
        r"\byag\s+git\b": "yahu git",
        r"\bdüzgün\s+araştırma\b": "düzgün araştır",
        r"\bduzgun\s+arastirma\b": "düzgün araştır",
        r"\bdüzgün\s+arama\b": "düzgün ara",
        r"\bduzgun\s+arama\b": "düzgün ara",
        r"\bvictor\s+osman\b": "Victor Osimhen",
        r"\bviktor\s+osman\b": "Victor Osimhen",
        r"\bviktor\s+osimhen\b": "Victor Osimhen",
        r"\bvictor\s+oshimen\b": "Victor Osimhen",
        r"\bviktor\s+oshimen\b": "Victor Osimhen",
        r"\bşampiyonlarla\s+ilgili\b": "Şampiyonlar Ligi",
        r"\bsampiyonlarla\s+ilgili\b": "Şampiyonlar Ligi",
        r"\bşampiyonlarla\b": "Şampiyonlar Ligi",
        r"\bsampiyonlarla\b": "Şampiyonlar Ligi",
        r"\bşampiyonlar\s+gibi\s+aç\b": "Şampiyonlar Ligi",
        r"\bsampiyonlar\s+gibi\s+ac\b": "Şampiyonlar Ligi",
        r"\bşampiyonlar\s+yiyemez\b": "Şampiyonlar Ligi",
        r"\bsampiyonlar\s+yiyemez\b": "Şampiyonlar Ligi",
        r"\bmaç\s+finale\b": "final maçı",
        r"\bmac\s+finale\b": "final maçı",
        r"\bparis\s+maçı\b": "PSG maçı",
        r"\bparis\s+maci\b": "PSG maçı",
        r"\bparis\s+saint-germain\b": "PSG",
        r"\bparis\s+saint\s+germain\b": "PSG",
        
        r"\bfinalsin\s+ardinda\s+var\b": "final sınavım var",
        r"\bfinalsin\s+ardinda\b": "final sınavı",
        r"\bfinalsin\s+ardında\s+var\b": "final sınavım var",
        r"\bfinalsin\s+ardında\b": "final sınavı",
        r"\bmatematik\s+finalsin\s+ardinda\s+var\b": "matematik final sınavım var",
        r"\bmatematik\s+finalsin\s+ardında\s+var\b": "matematik final sınavım var",
        
        # Tek kelimelik ve genel fonetik eşlemeler
        r"\bsabrin\s+var\b": "sınavım var",
        r"\bsabrın\s+var\b": "sınavım var",
        r"\bsabri\s+var\b": "sınavım var",
        r"\bsabrı\s+var\b": "sınavım var",
        r"\bsabrim\s+var\b": "sınavım var",
        r"\bsabrım\s+var\b": "sınavım var",
        r"\bsinavdin\b": "sınavım",
        r"\bsınavdın\b": "sınavım",
        r"\bsinavdi\b": "sınavı",
        r"\bsınavdı\b": "sınavı",
        r"\bfinal\s+sabrin\b": "final sınavı",
        r"\bfinal\s+sabrın\b": "final sınavı",
        r"\bfinal\s+sabrim\b": "final sınavı",
        r"\bfinal\s+sabrım\b": "final sınavı",
        r"\bsabrın\b": "sınavın",
        r"\bsabrin\b": "sınavın",
        r"\bsabrım\b": "sınavım",
        r"\bsabrim\b": "sınavım",
        r"\bsabrı\b": "sınavı",
        r"\bsabri\b": "sınavı"
    }
    
    for pattern, rep in replacements.items():
        cleaned = re.sub(pattern, rep, cleaned, flags=re.IGNORECASE)
        
    return cleaned

def normalize_subject_noun(text):
    """Standart Türkçe takvim formatına uyması için konu isimlerinin eklerini akıllıca temizler ve normalleştirir."""
    if not text:
        return ""
    
    words = text.split()
    if not words:
        return ""
        
    last_word = words[-1].lower()
    
    # Sınav normalleştirici
    if any(s in last_word for s in ["sinav", "sınav"]):
        if len(words) > 1:
            words[-1] = "Sınavı"
        else:
            words[-1] = "Sınav"
            
    # Ders normalleştirici
    elif "ders" in last_word:
        if len(words) > 1:
            words[-1] = "Dersi"
        else:
            words[-1] = "Ders"
            
    # Maç normalleştirici
    elif any(m in last_word for m in ["mac", "maç"]):
        if len(words) > 1:
            words[-1] = "Maçı"
        else:
            words[-1] = "Maç"
            
    # Toplantı normalleştirici
    elif any(t in last_word for t in ["toplanti", "toplantı"]):
        if len(words) > 1:
            words[-1] = "Toplantısı"
        else:
            words[-1] = "Toplantı"
            
    # Yüzme normalleştirici
    elif any(y in last_word for y in ["yuzme", "yüzme"]):
        words[-1] = "Yüzme"
        
    # Randevu normalleştirici
    elif "randevu" in last_word:
        if len(words) > 1:
            words[-1] = "Randevusu"
        else:
            words[-1] = "Randevu"
            
    # Premium görünüm için her kelimenin baş harfini büyük yap
    capitalized_words = []
    for w in words:
        w_cap = w[0].upper() + w[1:] if len(w) > 1 else w.upper()
        capitalized_words.append(w_cap)
        
    return " ".join(capitalized_words)

def clean_reminder_subject(subject_text):
    """Ses girişinden tarih/saat ifadelerini ve eylem fiillerini çıkarmak için ultra premium konu temizleyici."""
    if not subject_text:
        return "Etkinlik"
    
    # Önce konunun kendisindeki fonetik yanlış algılamaları düzelt
    cleaned = correct_phonetic_mishearings(subject_text)
    
    # 0. Kelimeleri ayırmak ve düzgün \b eşleşmelerine izin vermek için noktalamaları temizle ve boşluklarla değiştir
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # 1. Göreli ve tam tarih ifadelerini ve eklerini kaldır (tam Türkçe unicode desteği ile)
    date_patterns = [
        # İsteğe bağlı Türkçe ekleri olan haftanın günleri (uyumlaştırılmış)
        r"\b(pazartesi|salı|sali|çarşamba|carsamba|perşembe|persembe|cuma|cumartesi|pazar)(?:\s*günü|gunu)?(?:ye|ya|e|a|de|da|te|ta|nı|ni|nu|nü|nın|nin|nun|nün|yı|yi|yu|yü)?\b",
        # İsteğe bağlı ekleri olan yılın ayları
        r"\b(ocak|şubat|subat|mart|nisan|mayıs|mayis|haziran|temmuz|ağustos|agustos|eylül|eylul|ekim|kasım|kasim|aralık|aralik)(?:\s*ayı|ayi)?(?:e|a|de|da|te|ta|nı|ni|nu|nü|nın|nin|nun|nün|yı|yi|yu|yü)?\b",
        # Göreli tarih anahtar kelimeleri
        r"\b(bugün|bugun|yarın|yarin|dün|dun|haftaya|gelecek|öbür|obur\s*gün|gun)\b",
        # Genel tarih tanımlayıcıları
        r"\b(günü|gunu|günleri|gunleri|tarihi|tarihinde|tarihindeki|tarihli)\b",
    ]
    for pattern in date_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        
    # 2. Süre kalıplarını kaldır (örn. 5 dakika sonra)
    cleaned = re.sub(r"\b\d+\s*(?:dakika|dk|saniye|saat|gün|gun|hafta|ay)\s*(?:sonra|önce|once)?\b", "", cleaned, flags=re.IGNORECASE)
    
    # 3. Zaman kelimelerini ve zaman biçimlerini kaldır (saat 8'de, akşam 9'da, 20:00'de vb.)
    time_patterns = [
        # "saat 20 00 de", "saat 8 de" vb. durumları eşleştir
        r"\bsaat\s*\d{1,2}(?:\s*[\.:\s]\s*\d{2})?\s*(?:de|da|te|ta|ye|ya)?\b",
        # "20 00 de", "8 de" gibi bağımsız saatleri eşleştir
        r"\b\d{1,2}(?:\s*[\.:\s]\s*\d{2})?\s*(?:de|da|te|ta|ye|ya)?\b",
        # Genel zaman anahtar kelimeleri
        r"\b(saat|saatleri|saatlerinde|akşam|aksam|sabah|öğlen|oglen|gece|öğle|ogle|ikindi|sahur|iftar|civarı|civari|civarında|civarinda|sularında|sularinda|gibi|buçuk|bucuk|buçukta|bucukta|bir|iki|üç|uc|dört|dort|beş|bes|altı|alti|yedi|sekiz|dokuz|on|onbir|oniki)\b",
    ]
    for pattern in time_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        
    # 4. Yardımcı eylem fiillerini ve planları kaldır
    action_patterns = [
        r"\b(gideceğim|gidecegim|gideceğiz|gidecegiz|yapacağım|yapacagim|yapacağız|yapacagiz|yapılacak|yapilacak|edeceğim|edecegim|edeceğiz|edecegiz|yapmak|gitmek|etmek|olmak)\b",
        r"\b(istiyorum|planlıyorum|planliyorum|düşünüyorum|dusunuyorum|gerekiyor|lazım|lazim)\b",
        r"\b(hatırlat|hatirlat|söyle|soyle|kaydet|planla|unuttur)[a-zA-ZçıöğüşİĞÜŞÖÇ]*\b",
        r"\b(not\s*al|kur|ekle|unutturma|unutmadan|haber\s*ver|takvim|takvime|takvimi|ajanda|ajandaya|hatırlatıcı|hatirlatici|hatırlatıcıya|hatirlaticiya|plana|planı|plani|notlar|notları|notlari|notu|nota|bana|beni|sana|seni|onu|ona|şunu|sunu|şuna|suna|bunu|buna|şimdi|simdi|bir|bi)\b",
        r"\b(var|yok|durumda|olacak)\b",
    ]
    for pattern in action_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        
    # 5. Bağımsız Türkçe ek kırıntılarını kaldır (örn. "de", "da", "te", "ta", "e", "a", "yi", "ya")
    cleaned = re.sub(r"\b(de|da|te|ta|e|a|yı|yi|yu|yü|ya|ın|in|un|ün|ndaki|ndeki|daki|deki|günkü|gunku)\b", "", cleaned, flags=re.IGNORECASE)
    
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # 6. Akıllı isim normalleştirmesini uygula
    cleaned = normalize_subject_noun(cleaned)
    
    return cleaned if cleaned else "Etkinlik"



# --- VEKTÖREL RAG VE ASENKRON İNDEKSLEME SİSTEMİ ---
vectordb = VectorDB()
rag_queue = queue.Queue()

def scrape_url_text(url):
    """httpx/urllib yedekli, sıfır bağımlılıklı HTML düz metin çıkarıcı."""
    import re
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    html = ""
    try:
        import httpx
        with httpx.Client(timeout=12.0, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            html = resp.text
    except Exception as e1:
        # Standart urllib kütüphanesine geri dön
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as response:
                html = response.read().decode('utf-8', errors='ignore')
        except Exception as e2:
            return None, f"Bağlantı hatası: {e1} | {e2}"

    if not html:
        return None, "Boş içerik."

    # HTML içeriğini ayrıştır ve temizle
    html = re.sub(r"<(script|style|noscript|header|footer|nav|iframe)[^>]*>([\s\S]*?)<\/\1>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    entities = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&icirc;": "î", "&acirc;": "â",
        "&ccedil;": "ç", "&ouml;": "ö", "&uuml;": "ü", "&silde;": "ş",
        "&gilde;": "ğ"
    }
    for ent, rep in entities.items():
        text = text.replace(ent, rep)
    
    text = re.sub(r"\s+", " ", text).strip()
    
    if len(text) < 50:
        return None, "Sayfa içeriği çok kısa veya boş."
        
    chunks = []
    chunk_size = 700
    overlap = 100
    
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        chunks.append(chunk)
        start += chunk_size - overlap
        
    return chunks, None

def rag_background_worker():
    """Sohbetleri dizine eklemek ve web sitelerini asenkron olarak öğrenmek için arka plan işçi iş parçacığı (0ms gecikme)."""
    while True:
        try:
            task = rag_queue.get()
            if task is None:
                break
                
            task_type = task[0]
            
            if task_type == "chat":
                # Sohbet sırasını dizine ekle: ("chat", user_text, assistant_text)
                _, user_t, assistant_t = task
                combined_text = f"Kullanıcı: {user_t}\nJarvis: {assistant_t}"
                timestamp = datetime.datetime.now().strftime("%d %B %Y %H:%M")
                vectordb.add(combined_text, {"source": "Sohbet Geçmişi", "timestamp": timestamp})
                
            elif task_type == "web":
                # Web belgesini dizine ekle: ("web", url)
                _, url = task
                print(Fore.YELLOW + f"\n[RAG Sistem: '{url}' adresi arka planda inceleniyor...]")
                chunks, err = scrape_url_text(url)
                if err:
                    print(Fore.RED + f"\n[RAG Sistem Hatası: '{url}' kazınamadı: {err}]")
                else:
                    success_count = 0
                    timestamp = datetime.datetime.now().strftime("%d %B %Y %H:%M")
                    for chunk in chunks:
                        if vectordb.add(chunk, {"source": url, "timestamp": timestamp}):
                            success_count += 1
                    print(Fore.GREEN + f"\n[RAG Sistem: '{url}' başarıyla belleğe kaydedildi! {success_count} parça indekslendi.]")
                    
            rag_queue.task_done()
        except Exception as err:
            print(Fore.RED + f"\n[RAG Arka Plan Hatası: {err}]")
            time.sleep(2)



def clean_chinese(text):
    """Dil karışmasını önlemek için tüm Çince karakterleri dinamik olarak kaldırır."""
    if not text:
        return ""
    return re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', '', text)

def parse_turkish_number(text):
    """Sıra sayı ifadeleri desteğiyle, Türkçe yazılmış sayı dizelerini tam sayılara dönüştürür."""
    numbers = {
        "bir": 1, "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10,
        "yirmi": 20, "otuz": 30, "kirk": 40, "elli": 50, "altmis": 60, "yetmis": 70, "seksen": 80, "doksan": 90,
        "yuz": 100, "birinci": 1, "ikinci": 2, "ucuncu": 3, "dorduncu": 4, "besinci": 5
    }
    cleaned = clean_for_comparison(text)
    if cleaned.isdigit():
        return int(cleaned)
    return numbers.get(cleaned, None)

def parse_turkish_date(text, relative_to=None):
    """Türkçe sesli sorgulardaki göreli ve kesin tarih terimlerini ayrıştırır."""
    if relative_to is None:
        relative_to = datetime.date.today()
        
    text_norm = clean_for_comparison(text)
    
    if "bugun" in text_norm:
        return relative_to
    if "yarin" in text_norm:
        return relative_to + datetime.timedelta(days=1)
        
    # Göreli uzaklık ayrıştırma (örn. 5 gün sonra)
    match_days = re.search(r"(\d+|[a-z]+)\s*gun\s*sonra", text_norm)
    if match_days:
        num = parse_turkish_number(match_days.group(1))
        if num:
            return relative_to + datetime.timedelta(days=num)
            
    match_weeks = re.search(r"(\d+|[a-z]+)\s*hafta\s*sonra", text_norm)
    if match_weeks:
        num = parse_turkish_number(match_weeks.group(1))
        if num:
            return relative_to + datetime.timedelta(weeks=num)

    match_months = re.search(r"(\d+|[a-z]+)\s*ay\s*sonra", text_norm)
    if match_months:
        num = parse_turkish_number(match_months.group(1))
        if num:
            # Approx 30 days per month
            return relative_to + datetime.timedelta(days=num * 30)

    # Belirli bir haftanın günü hesaplaması (örn. haftaya Çarşamba, bu Cuma)
    weekdays = {
        "pazartesi": 0, "carsamba": 2, "persembe": 3, "cumartesi": 5, "pazar": 6, "sali": 1, "cuma": 4
    }
    
    # Sort by key length descending so longer names (e.g. "cumartesi") are checked before substrings ("cuma")
    for day_name, day_idx in sorted(weekdays.items(), key=lambda x: len(x[0]), reverse=True):
        if day_name in text_norm:
            current_day_idx = relative_to.weekday()
            days_ahead = day_idx - current_day_idx
            
            if "haftaya" in text_norm or "gelecek" in text_norm:
                days_ahead += 7
            elif days_ahead <= 0:
                # Eğer gün bu hafta zaten geçmişse, varsayılan olarak haftaya aynı güne ayarla
                days_ahead += 7
                
            return relative_to + datetime.timedelta(days=days_ahead)

            
    # Tam ay adlarını dene (örn. 25 Ağustos)
    months_tr = {
        "ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6,
        "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12
    }
    for m_name, m_num in months_tr.items():
        if m_name in text_norm:
            # Önce gelen basamakları bul
            digit_match = re.search(r"\b(\d{1,2})\b", text_norm)
            if digit_match:
                day = int(digit_match.group(1))
                year = relative_to.year
                # Eğer hedef tarih mevcut yılda zaten geçmişse, sonraki yılı hedefle
                target = datetime.date(year, m_num, day)
                if target < relative_to:
                    target = datetime.date(year + 1, m_num, day)
                return target
                
    return relative_to

def parse_time(text):
    """Türkçe'deki doğal zaman ifadelerini (örn. akşam 8'de, sekiz buçukta) standart SS:DD biçimine dönüştürür."""
    text_norm = clean_for_comparison(text)
    
    # "20:00" veya "08.30" gibi standart kalıplarla eşleştir
    match = re.search(r"(\d{1,2})[\.:](\d{2})", text)
    if match:
        h = int(match.group(1))
        m = int(match.group(2))
        if "aksam" in text_norm and h < 12:
            h += 12
        elif "sabah" in text_norm and h == 12:
            h = 0
        return f"{h:02d}:{m:02d}"
        
    # Metinsel Türkçe zaman ayrıştırıcı
    numbers = {
        "iki": 2, "uc": 3, "dort": 4, "bes": 5, "alti": 6, "yedi": 7, "sekiz": 8, "dokuz": 9,
        "on": 10, "on bir": 11, "on iki": 12
    }
    
    hour = None
    for key, val in numbers.items():
        if re.search(rf"\b{key}\b", text_norm):
            hour = val
            break
            
    if hour is None:
        # Yalnızca önünde "saat" varsa veya arkasından "bucuk" geliyorsa "bir" kelimesini kontrol et
        if re.search(r"\bsaat\s+bir\b", text_norm) or re.search(r"\bbir\s+bucuk\b", text_norm):
            hour = 1
            
    # "saat 8 de" gibi rakamlı saatleri eşleştir
    digit_match = re.search(r"\bsaat\s*(\d{1,2})\b", text_norm)
    if digit_match:
        hour = int(digit_match.group(1))
        
    if hour is not None:
        minute = 0
        if "bucuk" in text_norm:
            minute = 30
        if "aksam" in text_norm or "gece" in text_norm or "oglen" in text_norm:
            if hour < 12:
                hour += 12
        return f"{hour:02d}:{minute:02d}"
        
    # Göreli dakika ayarlamalarını eşleştir (örn. 5 dakika sonra)
    match_rel = re.search(r"(\d+|[a-z]+)\s*(?:dakika|dk)\s*sonra", text_norm)
    if match_rel:
        num = parse_turkish_number(match_rel.group(1))
        if num:
            future_time = datetime.datetime.now() + datetime.timedelta(minutes=num)
            return f"{future_time.hour:02d}:{future_time.minute:02d}"
            
    return None

def get_turkish_datetime():
    """Yerelleştirilmiş Türkçe sistem tarihi ve saati dizelerini dinamik olarak oluşturur (0ms gecikme)."""
    now = datetime.datetime.now()
    months = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
    }
    days = {
        0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe", 4: "Cuma", 5: "Cumartesi", 6: "Pazar"
    }
    month_tr = months[now.month]
    day_tr = days[now.weekday()]
    return f"{now.day} {month_tr} {now.year} {day_tr} saat {now.hour:02d}:{now.minute:02d}"

def get_turkish_day_name(date_obj):
    """Herhangi bir tarih nesnesi için belirlenmiş Türkçe gün adlarını hesaplar."""
    days = {
        0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe", 4: "Cuma", 5: "Cumartesi", 6: "Pazar"
    }
    return days[date_obj.weekday()]

async def speak_stream(stream, user_query="", allow_help_offer=True):
    """Ollama'dan GERÇEK ZAMANLI olarak harf harf (token-by-token) arayüz güncellemeleriyle metin akışı gerçekleştirir.
    
    Kök neden çözümü: 'for chunk in stream' ifadesi, asyncio olay döngüsünü donduran BLOKE EDİCİ senkron bir çağrıdır — WebSocket işçisi bunun içinde asla çalışamaz.
    Çözüm: Ollama yineleyicisini bir daemon thread içinde çalıştır, her token'ı call_soon_threadsafe aracılığıyla bir asyncio.Queue kuyruğuna besle, ardından 'await get()' ile tüket.
    Bu, her token arasında olay döngüsünü serbest bırakır, böylece WebSocket mesajları anında gönderebilir.
    """
    full_reply = ""
    sentence_buffer = ""
    sentence_split_rx = re.compile(r'([^.!?]+[.!?]+)\s*')
    _SENTINEL = object()  # unique end-of-stream marker

    banned_endings = [
        "yardimci olabilir miyim", "yardimci olabilirim", "baska bir arzu", "baska bir konuda",
        "baska bir istek", "baska yardim", "yardim ister misiniz", "hangi konuda daha fazla bilgi",
        "siz nasilsiniz", "her sey yolunda mi", "bilgi vermemi ister misiniz", "baska bir seyde yardimci",
        "yardimci olabilirim mi", "yardimci olmakta memnun", "size nasil daha fazla", "baska bir seyle yardimci",
        "abone olmayi unutmayin", "abone olmayi", "thanks for watching", "izlediginiz icin tesekkurler"
    ]

    # Arayüzde canlı akan bir sohbet balonu aç
    publish_ui("stream_start", "")

    # ── TEMEL ÇÖZÜM: Bloke edici Ollama yineleyicisini arka plan thread'inde çalıştır ──
    loop = asyncio.get_event_loop()
    token_q: asyncio.Queue = asyncio.Queue()

    def _ollama_reader():
        """Bir daemon thread içinde çalışır: Ollama akışını okur ve asenkron kuyruğu besler."""
        try:
            for chunk in stream:
                raw = chunk['message']['content']
                raw = clean_chinese(raw)
                raw = re.sub(r'<\|im_start\|>|<\|im_end\|>|<\|im_sep\|>|im_start|im_end|echangpt|illaume', '', raw)
                if raw:
                    loop.call_soon_threadsafe(token_q.put_nowait, raw)
        except Exception:
            pass
        finally:
            loop.call_soon_threadsafe(token_q.put_nowait, _SENTINEL)

    reader = threading.Thread(target=_ollama_reader, daemon=True)
    reader.start()

    # ── Token'ları asenkron olarak tüket — her token arasında olay döngüsünü serbest bırakır ──
    while True:
        content = await token_q.get()   # yields to event loop → WS worker runs → token sent NOW
        if content is _SENTINEL:
            break

        # Token'ı anında arayüze gönder (WebSocket işçisi bunu bir sonraki olay döngüsü tikinde alacaktır)
        publish_ui("stream_token", content)

        sentence_buffer += content

        matches = list(sentence_split_rx.finditer(sentence_buffer))
        if matches:
            last_end = 0
            for match in matches:
                sentence = match.group(1).strip()
                last_end = match.end()

                cleaned_sentence = clean_for_comparison(sentence)
                should_play = True

                if "galatasaray" in cleaned_sentence or "futbol" in cleaned_sentence or "mac durumu" in cleaned_sentence:
                    if not any(k in clean_for_comparison(user_query) for k in ["galatasaray", "skor", "mac", "futbol", "sonuc", "gol"]):
                        should_play = False

                if any(phrase in cleaned_sentence for phrase in ["nasil geciyor", "gorusmek ister misiniz", "ilginizi cekiyor mu", "arzu eder misiniz"]):
                    should_play = False

                if re.search(r'[\u4e00-\u9fff]', sentence):
                    should_play = False

                if any(be in cleaned_sentence for be in banned_endings):
                    should_play = False

                contains_help_stem = any(stem in cleaned_sentence for stem in ["yardim", "bilgi", "arzu", "istek"])
                contains_action_verb = any(verb in cleaned_sentence for verb in ["verebilirim", "olabilirim", "ister", "istersiniz", "var mi", "memnun"])
                if contains_help_stem and contains_action_verb:
                    if len(sentence.split()) <= 6:
                        should_play = False

                # Yazım / çeviri düzeltmeleri
                if "gununuz ne kadar guzel geciyormus gibi" in cleaned_sentence:
                    sentence = "Gününüzün harika geçtiğini umuyorum efendim."
                elif "gununuz harika gecmesini" in cleaned_sentence:
                    sentence = "Gününüzün harika geçmesini dilerim efendim."
                elif "sistem bilgisiye" in cleaned_sentence:
                    sentence = sentence.replace("sistem bilgisiye", "sistem bilgisine")
                elif "hilmet" in cleaned_sentence:
                    sentence = sentence.replace("hilmet", "hizmet")
                if "rahmetli" in cleaned_sentence:
                    sentence = sentence.replace("rahmetli", "memnuniyetle")
                if "super bariyerler" in cleaned_sentence:
                    sentence = sentence.replace("super bariyerler", "engeller")
                if "super bariyer" in cleaned_sentence:
                    sentence = sentence.replace("super bariyer", "engel")

                if should_play:
                    safe_print(Fore.CYAN + sentence + " ", end="")
                    full_reply += sentence + " "
                    try:
                        await jarvis_speak(sentence, stream_bubble=True)
                    except speech.SpeechInterrupted:
                        raise

            sentence_buffer = sentence_buffer[last_end:]

    # Kalan tampon bellek (noktalama işareti olmayan son parça)
    if sentence_buffer.strip():
        cleaned_sent = clean_for_comparison(sentence_buffer)
        should_play = True

        if "galatasaray" in cleaned_sent or "futbol" in cleaned_sent or "mac durumu" in cleaned_sent:
            if not any(k in clean_for_comparison(user_query) for k in ["galatasaray", "skor", "mac", "futbol", "sonuc", "gol"]):
                should_play = False

        if any(phrase in cleaned_sent for phrase in ["nasil geciyor", "gorusmek ister misiniz", "ilginizi cekiyor mu", "arzu eder misiniz"]):
            should_play = False

        if any(be in cleaned_sent for be in banned_endings):
            should_play = False

        contains_help_stem = any(stem in cleaned_sent for stem in ["yardim", "bilgi", "arzu", "istek"])
        contains_action_verb = any(verb in cleaned_sent for verb in ["verebilirim", "olabilirim", "ister", "istersiniz", "var mi", "memnun"])
        if contains_help_stem and contains_action_verb:
            if len(sentence_buffer.split()) <= 6:
                should_play = False

        if "rahmetli" in cleaned_sent:
            sentence_buffer = sentence_buffer.replace("rahmetli", "memnuniyetle")
        if "super bariyer" in cleaned_sent:
            sentence_buffer = sentence_buffer.replace("super bariyer", "engel")

        if should_play:
            safe_print(Fore.CYAN + sentence_buffer.strip() + " ", end="")
            full_reply += sentence_buffer.strip() + " "
            await jarvis_speak(sentence_buffer.strip(), stream_bubble=True)

    print()  # newline to prevent STT carriage-return overlap
    return full_reply


def reminder_checker_thread_func():
    """Aktif hatırlatıcıları her 10 saniyede bir kontrol edip tetiklemek için arka plan işletim sistemi thread'i (listen() engellemesinden etkilenmez)."""
    while True:
        try:
            time.sleep(10)
            
            # Belleği yükle
            memory = load_memory()
            reminders = memory.get("reminders", [])
            
            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M")
            
            updated = False
            for rem in reminders:
                if rem.get("status", "active") == "active":
                    rem_date = rem.get("date")
                    rem_time = rem.get("time")
                    
                    try:
                        rem_dt = datetime.datetime.strptime(f"{rem_date} {rem_time}", "%Y-%m-%d %H:%M")
                        # Eğer hatırlatıcı zamanı geldiyse veya geçtiyse (ve makul 1 saatlik aralık içindeyse)
                        if rem_dt <= now and (now - rem_dt).total_seconds() < 3600:
                            rem["status"] = "fired"
                            updated = True
                            
                            subject = rem.get("subject", "Etkinlik")
                            
                            # Konuya göre özel premium uyarı mesajları
                            subj_lower = clean_for_comparison(subject)
                            if "cay" in subj_lower:
                                alert_msg = "Mustafa Efendim, çayınız hazır, afiyet olsun."
                            elif "kahve" in subj_lower:
                                alert_msg = "Mustafa Efendim, kahveniz hazır, afiyet olsun."
                            elif "yemek" in subj_lower or "sofra" in subj_lower:
                                alert_msg = "Mustafa Efendim, yemeğiniz hazır, afiyet olsun."
                            elif "ders" in subj_lower or "sinav" in subj_lower:
                                alert_msg = f"Mustafa Efendim, '{subject}' vaktiniz geldi, başarılar dilerim."
                            elif "mac" in subj_lower:
                                alert_msg = f"Mustafa Efendim, '{subject}' saati geldi, şanlı zaferler dilerim."
                            elif "su" in subj_lower:
                                alert_msg = "Mustafa Efendim, su içme vaktiniz geldi."
                            else:
                                alert_msg = f"Mustafa Efendim, hatırlatıcınızın vakti geldi: {subject}."
                            
                            # Kendi kendini dinleme kalkanı için dinlemeyi geçici olarak engelle
                            config.block_listening = True
                            
                            safe_print(Fore.RED + Style.BRIGHT + f"\n\n[HATIRLATICI ALARMI: {subject} zamanı geldi!]")
                            safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + alert_msg)
                            
                            try:
                                # Bu arka plan thread'inde yeni bir olay döngüsünde asenkron konuşmayı çalıştır
                                publish_ui("state", "SPEAKING")
                                asyncio.run(speech.speak(alert_msg))
                            except Exception as alert_err:
                                print(f"[Alarm Çalma Hatası: {alert_err}]")
                            finally:
                                publish_ui("state", "IDLE")
                                config.block_listening = False
                                
                    except Exception as parse_err:
                        continue
                        
            if updated:
                save_memory(memory)
                
        except Exception as loop_err:
            time.sleep(10)

async def main():
    os.system("cls" if os.name == "nt" else "clear")
    safe_print(JARVIS_BANNER)
    
    # Başlangıç kontrolleri
    memory = load_memory()
    
    safe_print(Fore.GREEN + "[Sistem]: RAG Vektör Belleği aktif.")
    # Start UI Architecture
    try:
        python_exe = sys.executable
        subprocess.Popen([python_exe, "ui_server.py"])
        subprocess.Popen([python_exe, "ui_app.py"])
        safe_print(Fore.GREEN + "[Sistem]: Iron Man HUD Arayüzü Başlatıldı.")
    except Exception as e:
        safe_print(Fore.RED + f"[Sistem]: Arayüz başlatılamadı: {e}")
        
    # Arayüz Yayın işçisini başlat
    asyncio.create_task(ui_websocket_worker())
    # Sistem İstatistikleri telemetri işçisini başlat
    asyncio.create_task(system_stats_worker())
    publish_ui("state", "IDLE")
        
    # Daemon arka plan thread'lerini başlat
    t_reminders = threading.Thread(target=reminder_checker_thread_func, daemon=True)
    t_reminders.start()
    
    # RAG dizine ekleme ve öğrenme için yerel arka plan thread'ini başlat
    rag_thread = threading.Thread(target=rag_background_worker, daemon=True)
    rag_thread.start()
    
    # Modeller preload.py tarafından zaten VRAM'e yüklendi — burada tekrar yüklemeye gerek yok.
    print(Fore.GREEN + f"[Sistem: Yapay zeka modelleri zaten hazır (preload.py tarafından yüklendi).]")
    publish_ui("state", "IDLE")

    
    welcome_text = "Merhaba, Mustafa Efendim. Ben yerel asistanınız Jarvis. Çevrimdışı ve ultra hızlı çalışmak için hazırım. Bugün sizin için ne yapabilirim?"
    safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + welcome_text)
    await jarvis_speak(welcome_text)
    
    # Ana Diyalog Döngüsü
    chat_history = []
    pending_schedule = None
    
    while True:
        try:
            publish_ui("state", "LISTENING")
            user_speech = await asyncio.to_thread(speech.listen)
            
            if not user_speech or user_speech.strip() == "":
                continue
            
            publish_ui("transcript", user_speech)
            publish_ui("state", "THINKING")
                
            # Level 2+ Phonetic Correction Sifting
            corrected_speech = correct_phonetic_mishearings(user_speech)
            if corrected_speech != user_speech:
                safe_print(Fore.YELLOW + f"[Düzeltilmiş Ses Girdisi: '{corrected_speech}']")
                user_speech = corrected_speech
                
            safe_print(Fore.GREEN + f"\nSiz: {user_speech}")
            
            norm_speech = clean_for_comparison(user_speech)
            
            # --- Multi-Turn Pending Schedule Handler ---
            if pending_schedule:
                resolved_t = parse_time(user_speech)
                if resolved_t:
                    date_str = pending_schedule["date"]
                    subject = pending_schedule["subject"]
                    
                    new_reminder = {
                        "date": date_str,
                        "time": resolved_t,
                        "subject": subject,
                        "status": "active"
                    }
                    
                    memory = load_memory()
                    memory["reminders"].append(new_reminder)
                    save_memory(memory)
                    
                    pending_schedule = None # Reset state
                    
                    if date_str == datetime.date.today().strftime("%Y-%m-%d"):
                        confirm_reply = "Tamamdır, Mustafa Efendim."
                    else:
                        confirm_reply = f"Tamamdır, Mustafa Efendim. {date_str} tarihli '{subject}' planınızı saat {resolved_t} için takvime kaydettim."
                    safe_print(Fore.GREEN + f"\n[Akıllı Takvim: '{subject}' planı {date_str} saat {resolved_t} için başarıyla kaydedildi.]")
                    safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + confirm_reply)
                    await jarvis_speak(confirm_reply)
                    continue
                else:
                    # Kullanıcı konuyu değiştirdi, bekleyen durumu iptal et
                    pending_schedule = None
            
            # --- 0ms OS CONTROL & APP LAUNCHER INTERCEPTOR ---
            # Güvenli başlatma komutlarının izin verilenler listesi (whitelist)
            app_launch_map = {
                "vscode": ["start", "code"],
                "vs code": ["start", "code"],
                "chrome": ["start", "chrome"],
                "tarayici": ["start", "chrome"],
                "tarayiciyi": ["start", "chrome"],
                "spotify": ["start", "spotify:"],
                "steam": ["start", "steam:"],
                "epic games": ["start", "com.epicgames.launcher:"],
                "epic gamesi": ["start", "com.epicgames.launcher:"],
                "hesap makinesi": ["calc"],
                "hesap makinesini": ["calc"],
                "gorev yoneticisi": ["taskmgr"],
                "gorev yoneticisini": ["taskmgr"],
                "discord": ["start", "discord:"],
                "discordu": ["start", "discord:"],
                "dosya gezgini": ["start", "explorer"],
                "dosya gezginini": ["start", "explorer"],
                "youtube": ["start", "https://www.youtube.com"],
                "youtubeu": ["start", "https://www.youtube.com"],
                "google": ["start", "https://www.google.com"],
                "googlei": ["start", "https://www.google.com"],
                # Hava Durumu — Google Weather
                "hava durumu": ["start", "https://www.google.com/search?q=hava+durumu"],
                "hava durumunu": ["start", "https://www.google.com/search?q=hava+durumu"],
                "hava durumuna": ["start", "https://www.google.com/search?q=hava+durumu"],
                "havaya bak": ["start", "https://www.google.com/search?q=hava+durumu"],
                # Harita / Konum — Google Maps
                "konum": ["start", "https://www.google.com/maps"],
                "konumu": ["start", "https://www.google.com/maps"],
                "harita": ["start", "https://www.google.com/maps"],
                "haritayi": ["start", "https://www.google.com/maps"],
                "haritaya": ["start", "https://www.google.com/maps"],
                "maps": ["start", "https://www.google.com/maps"],
            }


            is_launch_request = False
            launch_cmd = None
            launch_app_name = None
            
            # Match "aç" requests, e.g. "vs code aç", "chrome'u aç", "spotify aç"
            if norm_speech.endswith(" ac") or " ac " in norm_speech or norm_speech == "ac":
                # İzin verilenler listesinden eşleşen uygulama adını bul
                for app_key, cmd_list in app_launch_map.items():
                    if app_key in norm_speech:
                        is_launch_request = True
                        launch_cmd = cmd_list
                        launch_app_name = app_key.upper()
                        break
            
            if is_launch_request and launch_cmd:
                # Direkt aç — konuşma yok, sıfır gecikme
                safe_print(Fore.GREEN + f"\n[Sistem Kontrol: {launch_app_name} açılıyor...]")
                try:
                    if launch_cmd[0] == "start":
                        subprocess.Popen(f"start {launch_cmd[1]}", shell=True)
                    else:
                        subprocess.Popen(launch_cmd, shell=True)
                except Exception as run_err:
                    safe_print(Fore.RED + f"[Sistem Hatası: Uygulama başlatılamadı: {run_err}]")
                continue

            # --- 0ms OS CONTROL & APP CLOSER INTERCEPTOR ---
            app_close_map = {
                "vscode": {"type": "kill", "proc": "code.exe", "name": "VS CODE"},
                "vs code": {"type": "kill", "proc": "code.exe", "name": "VS CODE"},
                "chrome": {"type": "kill", "proc": "chrome.exe", "name": "CHROME"},
                "tarayici": {"type": "kill", "proc": "chrome.exe", "name": "TARAYICI"},
                "tarayiciyi": {"type": "kill", "proc": "chrome.exe", "name": "TARAYICI"},
                "spotify": {"type": "kill", "proc": "Spotify.exe", "name": "SPOTIFY"},
                "steam": {"type": "kill", "proc": "steam.exe", "name": "STEAM"},
                "epic games": {"type": "kill", "proc": "EpicGamesLauncher.exe", "name": "EPIC GAMES"},
                "epic gamesi": {"type": "kill", "proc": "EpicGamesLauncher.exe", "name": "EPIC GAMES"},
                "hesap makinesi": {"type": "kill", "proc": "calc.exe", "name": "HESAP MAKİNESİ"},
                "hesap makinesini": {"type": "kill", "proc": "calc.exe", "name": "HESAP MAKİNESİ"},
                "gorev yoneticisi": {"type": "kill", "proc": "taskmgr.exe", "name": "GÖREV YÖNETİCİSİ"},
                "gorev yoneticisini": {"type": "kill", "proc": "taskmgr.exe", "name": "GÖREV YÖNETİCİSİ"},
                "discord": {"type": "kill", "proc": "Discord.exe", "name": "DISCORD"},
                "discordu": {"type": "kill", "proc": "Discord.exe", "name": "DISCORD"},
                "dosya gezgini": {"type": "shortcut", "key": "alt_f4", "name": "DOSYA GEZGİNİ"},
                "dosya gezginini": {"type": "shortcut", "key": "alt_f4", "name": "DOSYA GEZGİNİ"},
                "youtube": {"type": "shortcut", "key": "ctrl_w", "name": "YOUTUBE"},
                "youtubeu": {"type": "shortcut", "key": "ctrl_w", "name": "YOUTUBE"},
                "google": {"type": "shortcut", "key": "ctrl_w", "name": "GOOGLE"},
                "googlei": {"type": "shortcut", "key": "ctrl_w", "name": "GOOGLE"}
            }

            is_close_request = False
            close_action = None
            close_app_name = None
            
            # Match "kapat" requests, e.g. "google'ı kapat", "youtube kapat", "spotify'ı kapat"
            if any(k in norm_speech for k in [" kapat", " kapansin", " kapatsana", " kapatin"]):
                for app_key, action_dict in app_close_map.items():
                    if app_key in norm_speech:
                        is_close_request = True
                        close_action = action_dict
                        close_app_name = action_dict["name"]
                        break
                        
            if is_close_request and close_action:
                # Direkt kapat — konuşma yok, sıfır gecikme
                safe_print(Fore.GREEN + f"\n[Sistem Kontrol: {close_app_name} kapatılıyor...]")
                try:
                    if close_action["type"] == "kill":
                        subprocess.Popen(f"taskkill /f /im {close_action['proc']}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif close_action["type"] == "shortcut":
                        await ensure_target_window_active()
                        if close_action["key"] == "ctrl_w":
                            pyautogui.hotkey('ctrl', 'w')
                        elif close_action["key"] == "alt_f4":
                            pyautogui.hotkey('alt', 'f4')
                except Exception as run_err:
                    safe_print(Fore.RED + f"[Sistem Hatası: Uygulama kapatılamadı: {run_err}]")
                continue
            typing_text = extract_typing_text(user_speech)
            is_scroll_down = any(phrase in norm_speech for phrase in ["asagi kaydir", "assagi kaydir", "asagi in", "assagi in", "sayfayi asagi", "asagi kay", "assagi kay"])
            is_scroll_up = any(phrase in norm_speech for phrase in ["yukari kaydir", "yukari cik", "sayfayi yukari", "yukari kay"])
            is_click_request = norm_speech in ["sec", "tikla", "sol tikla", "videoyu sec", "videoyu ac", "tiklasana", "tikla"] or (norm_speech == "ac" and not is_launch_request)
            is_enter_request = norm_speech in ["ara", "arat", "arama yap", "enter", "enterla", "entere bas", "enter a bas", "enter tusuna bas", "ara tusuna bas"]
            is_delete_request = norm_speech in ["sil", "geri gel", "backspace bas", "backspace"]
            is_clear_all_request = norm_speech in ["hepsini sil", "yazilani sil", "metni temizle"]
            is_tab_open = norm_speech in ["yeni sekme", "sekme ac", "yeni sekme ac"]
            is_tab_close = norm_speech in ["sekme kapat", "sekmeyi kapat"]
            is_back_request = norm_speech in ["geri", "geri git", "geri don", "geri git", "bir geri", "onceki sayfa", "geri yukle"]
            is_forward_request = norm_speech in ["ileri", "ileri git", "ileri git", "sonraki sayfa"]
            is_refresh_request = norm_speech in ["yenile", "sayfayi yenile", "yeniden yukle", "yeniden yukle", "f5"]

            is_automation = (typing_text is not None) or is_scroll_down or is_scroll_up or is_click_request or is_enter_request or is_delete_request or is_clear_all_request or is_tab_open or is_tab_close or is_back_request or is_forward_request or is_refresh_request

            if is_automation:
                await ensure_target_window_active()

            # 1. Yazma komutlarını çalıştır
            if typing_text:
                press_enter = False
                if any(phrase in norm_speech for phrase in ["yazip ara", "yazip arat", "yaz ve ara", "yaz ve arat", "yazip enter", "yaz ve enter", "yazip arattir"]):
                    press_enter = True
                
                clean_typing_text = typing_text
                suffixes = [
                    r"\s+(?:ve\s+)?(?:ara|arat|enterla|enter\s*a\s*bas|arattır|arattir|araştır|arastir)$",
                    r"\s+yazıp\s+(?:ara|arat|arattır|arattir|araştır|arastir)$",
                    r"\s+yazip\s+(?:ara|arat|arattir|arattır|arastir|arastır)$"
                ]
                for suf in suffixes:
                    clean_typing_text = re.sub(suf, "", clean_typing_text, flags=re.IGNORECASE)
                
                if clean_typing_text:
                    safe_print(Fore.GREEN + f"\n[Klavye Kontrol: '{clean_typing_text}' yazılıyor...]")
                    
                    try:
                        old_clipboard = set_clipboard_text(clean_typing_text)
                        await asyncio.sleep(0.15)
                        
                        # --- Tarayıcılarda Arama Çubuğuna Odaklan (Google, YouTube vb.) ---
                        active_title = ""
                        try:
                            win = gw.getActiveWindow()
                            if win and win.title:
                                active_title = win.title.lower()
                        except Exception:
                            pass
                            
                        is_browser = any(b in active_title for b in ["chrome", "edge", "firefox", "brave", "opera", "youtube", "google", "yandex", "browser"])
                        if is_browser:
                            pyautogui.press('escape')
                            await asyncio.sleep(0.05)
                            pyautogui.press('/')
                            await asyncio.sleep(0.15)
                            
                        pyautogui.hotkey('ctrl', 'v')
                        await asyncio.sleep(0.15)
                        if old_clipboard:
                            restore_clipboard_text(old_clipboard)
                        if press_enter:
                            await asyncio.sleep(0.15)
                            pyautogui.press('enter')
                    except Exception as kbd_err:
                        safe_print(Fore.RED + f"[Klavye Kontrol Hatası: {kbd_err}]")
                    continue

            # 2. Sayfa kaydırma komutlarını çalıştır
            if is_scroll_down:
                safe_print(Fore.GREEN + f"\n[Navigasyon: PageDown]")
                try:
                    pyautogui.press('pagedown')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Klavye Kontrol Hatası: {kbd_err}]")
                continue
            elif is_scroll_up:
                safe_print(Fore.GREEN + f"\n[Navigasyon: PageUp]")
                try:
                    pyautogui.press('pageup')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Klavye Kontrol Hatası: {kbd_err}]")
                continue

            # 2b. Tarayıcı geri / ileri / yenile
            if is_back_request:
                safe_print(Fore.GREEN + f"\n[Navigasyon: Geri (Alt+Sol)]")
                try:
                    pyautogui.hotkey('alt', 'left')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Hata: {kbd_err}]")
                continue
            elif is_forward_request:
                safe_print(Fore.GREEN + f"\n[Navigasyon: İleri (Alt+Sağ)]")
                try:
                    pyautogui.hotkey('alt', 'right')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Hata: {kbd_err}]")
                continue
            elif is_refresh_request:
                safe_print(Fore.GREEN + f"\n[Navigasyon: Yenile (F5)]")
                try:
                    pyautogui.press('f5')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Hata: {kbd_err}]")
                continue

            # 3. Fare tıklama / seçim komutlarını çalıştır
            if is_click_request:
                safe_print(Fore.GREEN + f"\n[Mouse: Sol tıklama]")
                try:
                    pyautogui.click()
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Mouse Kontrol Hatası: {kbd_err}]")
                continue

            # 4. Doğrudan enter/arama komutlarını çalıştır
            if is_enter_request:
                safe_print(Fore.GREEN + f"\n[Klavye: Enter]")
                try:
                    pyautogui.press('enter')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Klavye Kontrol Hatası: {kbd_err}]")
                continue

            # 5. Backspace / metni temizleme komutlarını çalıştır
            if is_clear_all_request:
                safe_print(Fore.GREEN + f"\n[Klavye: Ctrl+A + Backspace]")
                try:
                    pyautogui.hotkey('ctrl', 'a')
                    await asyncio.sleep(0.1)
                    pyautogui.press('backspace')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Klavye Kontrol Hatası: {kbd_err}]")
                continue
            elif is_delete_request:
                safe_print(Fore.GREEN + f"\n[Klavye: Backspace]")
                try:
                    pyautogui.press('backspace')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Klavye Kontrol Hatası: {kbd_err}]")
                continue

            # 6. Tarayıcı sekme kontrollerini çalıştır
            if is_tab_open:
                safe_print(Fore.GREEN + f"\n[Klavye: Ctrl+T (Yeni Sekme)]")
                try:
                    pyautogui.hotkey('ctrl', 't')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Klavye Kontrol Hatası: {kbd_err}]")
                continue
            elif is_tab_close:
                safe_print(Fore.GREEN + f"\n[Klavye: Ctrl+W (Sekme Kapat)]")
                try:
                    pyautogui.hotkey('ctrl', 'w')
                except Exception as kbd_err:
                    safe_print(Fore.RED + f"[Klavye Kontrol Hatası: {kbd_err}]")
                continue

            # --- 0ms WEB SEARCH & ROUTING INTERCEPTOR ---
            # Match "youtube'da [sorgu] aç/ara/oynat/izle"
            youtube_match = re.search(r"youtube(?:\'da|\s+da|\s+)?\s+(.+?)\s*(?:ac|ara|oynat|izle|bul)\b", norm_speech)
            if youtube_match:
                query = youtube_match.group(1).strip()
                safe_print(Fore.GREEN + f"\n[YouTube Arama: '{query}']")
                try:
                    import urllib.parse
                    encoded_query = urllib.parse.quote(query)
                    subprocess.Popen(f"start https://www.youtube.com/results?search_query={encoded_query}", shell=True)
                except Exception as run_err:
                    safe_print(Fore.RED + f"[Sistem Hatası: {run_err}]")
                continue

            # Match "google'da [sorgu] ara/bul/araştır"
            google_match = re.search(r"google(?:\'da|\s+da|\s+)?\s+(.+?)\s*(?:ara|bul|arastir|arastırma)\b", norm_speech)
            if google_match:
                query = google_match.group(1).strip()
                safe_print(Fore.GREEN + f"\n[Google Arama: '{query}']")
                try:
                    import urllib.parse
                    encoded_query = urllib.parse.quote(query)
                    subprocess.Popen(f"start https://www.google.com/search?q={encoded_query}", shell=True)
                except Exception as run_err:
                    safe_print(Fore.RED + f"[Sistem Hatası: {run_err}]")
                continue

            # --- 0ms YEREL BETİK ORKESTRASYON KESİCİ ---
            is_script_run = False
            script_path = None
            script_name = None
            
            if any(k in norm_speech for k in ["test simulasyonunu calistir", "test simulasyonu calistir", "test simulasyonu"]):
                is_script_run = True
                script_path = "test_sim.ps1"
                script_name = "PowerShell Test Simülasyonu"
            elif any(k in norm_speech for k in ["sohbet simulasyonunu calistir", "sohbet simulasyonu calistir", "sohbet simulasyonu"]):
                is_script_run = True
                script_path = "simulate_conversation.py"
                script_name = "Sohbet Simülasyonu"
                
            if is_script_run and script_path:
                confirm_reply = f"Mustafa Efendim, yerel '{script_name}' betiğini hemen çalıştırıyorum. Çıktı sonuçlarını sizin için raporlayacağım."
                safe_print(Fore.GREEN + f"\n[Sistem Kontrol: '{script_name}' arka planda başlatılıyor...]")
                safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + confirm_reply)
                await jarvis_speak(confirm_reply)
                
                publish_ui("state", "THINKING")
                
                try:
                    cwd = os.path.dirname(os.path.abspath(__file__))
                    full_path = os.path.join(cwd, script_path)
                    
                    local_ps_path = os.path.join(cwd, "backups", "seviye_4", "test_sim.ps1")
                    if not os.path.exists(full_path) and os.path.exists(local_ps_path):
                        full_path = local_ps_path
                        
                    if script_path.endswith(".ps1"):
                        proc = subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass", "-File", full_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', cwd=cwd)
                    else:
                        proc = subprocess.Popen([sys.executable, full_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', cwd=cwd)
                    
                    stdout, stderr = proc.communicate(timeout=25)
                    
                    if proc.returncode == 0:
                        report_reply = f"Mustafa Efendim, '{script_name}' simülasyonu başarıyla tamamlandı. Sistemde herhangi bir hata veya sorun tespit edilmedi."
                        safe_print(Fore.GREEN + f"\n[Sistem Kontrol: '{script_name}' başarıyla tamamlandı!]")
                        if stdout:
                            safe_print(Fore.YELLOW + "--- Simülasyon Çıktısı (Özet) ---")
                            lines = [l for l in stdout.splitlines() if l.strip()]
                            for l in lines[:6]:
                                safe_print(Fore.WHITE + "  " + l)
                            if len(lines) > 6:
                                safe_print(Fore.WHITE + "  ...")
                    else:
                        report_reply = f"Mustafa Efendim, üzgünüm ancak '{script_name}' çalıştırılırken bir hata oluştu. Hata detaylarını konsola yazdırdım."
                        safe_print(Fore.RED + f"\n[Sistem Kontrol Hata Kodu {proc.returncode}: '{script_name}' başarısız oldu!]")
                        if stderr:
                            safe_print(Fore.RED + "Hata Çıktısı: " + stderr.strip())
                except subprocess.TimeoutExpired:
                    proc.kill()
                    report_reply = f"Mustafa Efendim, '{script_name}' simülasyonu zaman aşımına uğradı."
                    safe_print(Fore.RED + f"\n[Sistem Kontrol: '{script_name}' zaman aşımına uğradı!]")
                except Exception as run_err:
                    report_reply = f"Mustafa Efendim, simülasyon çalıştırılırken sistemsel bir hata oluştu: {run_err}"
                    safe_print(Fore.RED + f"\n[Sistem Kontrol Hatası: {run_err}]")
                
                publish_ui("state", "IDLE")
                safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + report_reply)
                await jarvis_speak(report_reply)
                continue

            # --- 0ms URL LEARNING INTERCEPTOR ---
            url_match = re.search(r"(https?://[^\s]+)", user_speech)
            if url_match:
                url = url_match.group(1)
                # Varsa URL'nin sonundaki noktalama işaretlerini temizle
                url = url.rstrip(".,;:!?()[]{}")
                rag_queue.put(("web", url))
                confirm_reply = f"Mustafa Efendim, belirttiğiniz web kaynağını ({url}) incelemeye aldım. Arka planda asenkron olarak okuyup hafızama kaydediyorum."
                safe_print(Fore.GREEN + f"\n[RAG Sistem: '{url}' arka plan kuyruğuna eklendi.]")
                safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + confirm_reply)
                await jarvis_speak(confirm_reply)
                continue

            # --- 0ms PURE GREETING INTERCEPTOR ---
            greetings = ["merhaba", "selam", "selamlar", "gunaydin", "iyi gunler", "iyi aksamlar"]
            if norm_speech in greetings:
                greet_reply = "Merhaba, Mustafa Efendim. Hoş geldiniz. Bugün sizin için ne yapabilirim?"
                safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + greet_reply)
                await jarvis_speak(greet_reply)
                # Sohbet geçmişini sade selamlaşmalardan temiz tut
                continue
                
            # --- 0ms HOW ARE YOU INTERCEPTOR ---
            how_are_you_list = ["nasilsin", "nasilsiniz", "naber", "ne haber", "nasil gidiyor", "ne var ne yok", "keyifler nasil"]
            speech_no_jarvis = norm_speech.replace("jarvis", "").strip()
            if speech_no_jarvis in how_are_you_list:
                how_are_you_reply = "Çok iyiyim Mustafa Efendim. Tüm sistemlerim kararlı ve hizmetinizde. Teşekkür ederim."
                safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + how_are_you_reply)
                await jarvis_speak(how_are_you_reply)
                continue
                
            # --- 0ms SYSTEM SHUTDOWN INTERCEPTOR ---
            exit_keywords = ["sistemi kapat", "jarvis kapat", "kendine iyi bak", "cikis yap", "gorusuruz"]
            if any(kw in norm_speech for kw in exit_keywords):
                shutdown_reply = "Anlaşıldı efendim. Tüm sistemler kapatılıyor. İyi günler dilerim, kendinize iyi bakın."
                safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + shutdown_reply)
                await jarvis_speak(shutdown_reply)
                break
                
            # --- 0ms CALENDAR CLEAR INTERCEPTOR ---
            is_wipe_request = (
                (
                    any(p in norm_speech for p in ["plan", "takvim", "hatirlatma", "etkinlik", "hafiza", "ajanda"]) and
                    any(d in norm_speech for d in ["sil", "temizle", "kaldir", "sifirla", "bosalt", "iptal et"]) and
                    any(a in norm_speech for a in ["tum", "hepsini", "tamamini", "komple", "her seyi", "bütün", "butun"])
                ) or (
                    any(w in norm_speech for w in ["hepsini sil", "hepsini temizle", "tamamini sil", "tamamini temizle", "komple sil", "hafizayi sil", "hafızayı sil"])
                )
            )
            if is_wipe_request:
                memory = load_memory()
                memory["reminders"] = []
                save_memory(memory)
                chat_history = []  # Model bellek halüsinasyonlarını önlemek için RAM sohbet geçmişini temizle!
                delete_reply = "Tüm ders planlarını ve takvim hatırlatıcılarını yerel belleğimden tamamen sildim efendim. Sistem temizlendi."
                safe_print(Fore.GREEN + f"\n[Akıllı Takvim: Tüm planlar yerel bellekten başarıyla silindi.]")
                safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + delete_reply)
                await jarvis_speak(delete_reply)
                continue

            # --- Belirli Plan Silme İşlemi ---
            is_specific_delete = (
                any(d in norm_speech for d in ["sil", "kaldir", "iptal", "silmek istiyorum"]) and
                not is_wipe_request
            )
            if is_specific_delete:
                memory = load_memory()
                active_rems = [r for r in memory.get("reminders", []) if r.get("status", "active") == "active"]
                active_rems.sort(key=lambda x: (x.get("date"), x.get("time")))
                
                # Açık dizin numarasını kontrol et (birinci, ikinci, 3., 5 gibi kelimeleri destekle)
                target_idx = None
                match_num = re.search(r"(\d+|bir|iki|uc|dort|bes|alti|yedi|sekiz|dokuz|on|birinci|ikinci|ucuncu|dorduncu|besinci)\s*(?:nolu|numarali|siradaki|\.)?\s*(?:plan|etkinlik|hatirlatma)?", norm_speech)
                if match_num:
                    target_idx = parse_turkish_number(match_num.group(1))
                    
                deleted_any = False
                if target_idx and 1 <= target_idx <= len(active_rems):
                    # Dizine göre iptal et
                    rem_to_delete = active_rems[target_idx - 1]
                    rem_to_delete["status"] = "cancelled"
                    save_memory(memory)
                    deleted_any = True
                    reply = f"Mustafa Efendim, listedeki {target_idx} numaralı '{rem_to_delete.get('subject')}' planınızı başarıyla iptal ettim."
                    safe_print(Fore.GREEN + f"\n[Akıllı Takvim: Plan '{rem_to_delete.get('subject')}' iptal edildi.]")
                    safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + reply)
                    await jarvis_speak(reply)
                else:
                    # Konuyla eşleşen kelimelere göre iptal et
                    for rem in memory.get("reminders", []):
                        if rem.get("status", "active") == "active":
                            rem_sub_norm = clean_for_comparison(rem.get("subject", ""))
                            # Etkinlik türü kelimeleri eşleştir
                            for word in ["mac", "sinav", "ders", "toplanti", "yuzme", "randevu"]:
                                if word in norm_speech and word in rem_sub_norm:
                                    rem["status"] = "cancelled"
                                    deleted_any = True
                                    save_memory(memory)
                                    reply = f"Mustafa Efendim, '{rem.get('subject')}' planınızı listeden başarıyla kaldırdım."
                                    safe_print(Fore.GREEN + f"\n[Akıllı Takvim: Plan '{rem.get('subject')}' iptal edildi.]")
                                    safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + reply)
                                    await jarvis_speak(reply)
                                    break
                            if deleted_any:
                                break
                                
                if deleted_any:
                    continue
                
            # --- DETERMINISTIC TIME/DATE INTERCEPTOR (0ms) ---
            is_current_time_query = (any(k in norm_speech for k in ["saat kac", "saati soyle", "saat kactir"]) or ("saat" in norm_speech and "kac" in norm_speech)) and "kacta" not in norm_speech and not any(ev in norm_speech for ev in ["sinav", "ders", "mac", "toplanti", "yuzme", "plan", "etkinlik", "randevu"])
            is_current_date_query = any(k in norm_speech for k in ["tarih ne", "tarih nedir", "hangi gundeyiz", "bugun gunlerden ne", "bugunun tarihi"]) and "tarihinde" not in norm_speech and not any(ev in norm_speech for ev in ["sinav", "ders", "mac", "toplanti", "yuzme", "plan", "etkinlik", "randevu"])
            
            if is_current_time_query or is_current_date_query:
                time_reply = ""
                now = datetime.datetime.now()
                if is_current_time_query:
                    time_reply = f"Şu an saat tam olarak {now.hour:02d}:{now.minute:02d} efendim."
                else:
                    time_reply = f"Bugün {get_turkish_datetime().split('saat')[0].strip()} efendim."
                    
                safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + time_reply)
                await jarvis_speak(time_reply)
                continue
                
            # --- BAĞLAM HESAPLAMA VE temel gerçeklik listeleri ---
            memory = load_memory()
            
            # Smart Calendar Grounding Injection (Section 8)
            reminder_list_str = ""
            if memory["reminders"]:
                active_rems = [r for r in memory["reminders"] if r.get("status") == "active"]
                if active_rems:
                    # Kronolojik olarak sırala
                    active_rems.sort(key=lambda x: (x.get("date"), x.get("time")))
                    for idx, rem in enumerate(active_rems, 1):
                        d_obj = datetime.datetime.strptime(rem.get("date"), "%Y-%m-%d").date()
                        day_name = get_turkish_day_name(d_obj)
                        
                        days_left = (d_obj - datetime.date.today()).days
                        if days_left == 0:
                            remaining_str = "Bugün"
                        elif days_left == 1:
                            remaining_str = "Yarın"
                        elif days_left > 1:
                            remaining_str = f"{days_left} gün kaldı"
                        else:
                            remaining_str = f"{abs(days_left)} gün önce geçti"
                            
                        reminder_list_str += f"\n  {idx}. [{rem.get('date')} {day_name} Saat: {rem.get('time')} ({remaining_str})] Konu: {rem.get('subject')}"
                else:
                    reminder_list_str = " Yok"
            else:
                reminder_list_str = " Yok"
                
            # --- PRE-PROCESSOR SCHEDULING INTERCEPTOR ---
            is_query_or_list_attempt = any(k in norm_speech for k in ["sirala", "listele", "goster", "neler var", "var mi", "ne zaman", "hangisi"])
            is_scheduling_attempt = False
            
            # Anti-Complaint Shield: ignore scheduling triggers on user complaints
            is_complaint = any(kw in norm_speech for kw in ["hani", "neden", "unuttun", "hatirlatmadin", "yapmadin"])
            
            # Takvim sorgularını/sorularını planlama girişimlerinden hariç tut
            is_question = any(q in norm_speech for q in [
                "var mi", "ne zaman", "saat kac", "kacta", "kactaydi", "ne zamandi", "hangi gun", "hangi saatte",
                "kac gun", "kac gun kalmis", "kac gun var", "neler var", "listele", "sirala", "goster", 
                "ne var", "kim", "nedir", "neymis", "anlat", "soyle", "bilgi ver", "kac dakika", "kac saat",
                "kac kac", "kac", "skor", "skoru", "sonuc", "sonuc", "durum", "durumu"
            ])
            
            if not is_query_or_list_attempt and not is_complaint and not is_question and not is_specific_delete and not websearch.is_realtime_query(user_speech):
                is_scheduling_attempt = any(keyword in norm_speech for keyword in [
                    "gidecegim", "gidecegiz", "yapilacak", "rezervasyon", "toplanti", "not al", "hatirla",
                    "dersim var", "dersi var", "dersi", "saatinde", "sinav", "final", "imtihan", "mac", "yuzme",
                    "hatirlat", "sonra", "dakika", "saat", "dk", "unutmadan", "unutturma", "alarm", "surece"
                ])
                
            collision_warning_injected = ""
            
            if is_scheduling_attempt:
                # Resolve date and time
                parsed_d = parse_turkish_date(user_speech)
                parsed_t = parse_time(user_speech)
                
                # Saatsiz plan kontrolü
                if parsed_d and parsed_t is None:
                    # Kullanıcıdan nazikçe saat iste
                    subject_extracted = "Plan"
                    for kw in ["sinav", "ders", "mac", "toplanti", "yuzme", "randevu"]:
                        if kw in norm_speech:
                            subject_extracted = kw.capitalize()
                            break
                            
                    # Apply Akıllı Konu Temizleyici to the subject
                    subject_extracted = clean_reminder_subject(user_speech)
                    
                    pending_schedule = {
                        "date": parsed_d.strftime("%Y-%m-%d"),
                        "subject": subject_extracted
                    }
                    
                    req_text = f"{parsed_d.day} {get_turkish_day_name(parsed_d)} günü için '{subject_extracted}' planınızı takvime ekliyorum Mustafa Efendim, ancak bir saat belirtmediniz. Hatırlatıcıyı saat kaça kurmamı istersiniz?"
                    safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + req_text)
                    await jarvis_speak(req_text)
                    continue
                    
                # Hem tarih hem de saat çözüldüyse çakışmayı kontrol et
                if parsed_d and parsed_t:
                    date_str = parsed_d.strftime("%Y-%m-%d")
                    collision_exists = False
                    for rem in memory["reminders"]:
                        if rem.get("date") == date_str and rem.get("time") == parsed_t and rem.get("status") == "active":
                            collision_warning_injected = f"\n[ÇAKIŞMA UYARISI: {date_str} {parsed_t} zamanındaki '{rem.get('subject')}' planı zaten dolu!]"
                            collision_exists = True
                            break
                            
                    # Ön işlemci ile doğrudan kaydetme
                    has_date_keyword = any(dw in norm_speech for dw in [
                        "bugun", "yarin", "pazartesi", "sali", "carsamba", "persembe", "cuma", "cumartesi", "pazar",
                        "gun sonra", "hafta sonra", "ay sonra", "ocak", "subat", "mart", "nisan", "mayis", "haziran",
                        "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik",
                        "dakika", "dk", "saat", "saniye", "sonra"
                    ])
                    if has_date_keyword and not collision_exists:
                        subject = clean_reminder_subject(user_speech)
                        
                        new_reminder = {
                            "date": date_str,
                            "time": parsed_t,
                            "subject": subject,
                            "status": "active"
                        }
                        
                        # Prevent duplicate entries
                        memory = load_memory()
                        exists = False
                        for rem in memory.get("reminders", []):
                            if rem.get("date") == date_str and rem.get("time") == parsed_t and rem.get("status", "active") == "active":
                                exists = True
                                break
                                
                        if not exists:
                            memory["reminders"].append(new_reminder)
                            save_memory(memory)
                            
                            if date_str == datetime.date.today().strftime("%Y-%m-%d"):
                                confirm_reply = "Tamamdır, Mustafa Efendim."
                            else:
                                try:
                                    d_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                                    day_tr = get_turkish_day_name(d_obj)
                                    months = {
                                        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
                                        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
                                    }
                                    month_tr = months[d_obj.month]
                                    confirm_reply = f"Tamamdır, Mustafa Efendim. {d_obj.day} {month_tr} {day_tr} günü saat {parsed_t} için kaydettim."
                                except Exception:
                                    confirm_reply = f"Tamamdır, Mustafa Efendim. {date_str} günü saat {parsed_t} için kaydettim."
                                    
                            safe_print(Fore.GREEN + f"\n[Akıllı Takvim: '{subject}' planı {date_str} saat {parsed_t} için başarıyla kaydedildi.]")
                            safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL + confirm_reply)
                            await jarvis_speak(confirm_reply)
                            continue
                            
            # Configure Help Offer pruning context
            allow_help_offer = True
            # Strip help offers if simple query
            if len(user_speech.split()) <= 4 or any(k in norm_speech for k in ["saat", "tarih", "gün", "nasılsın", "neredesin", "hava"]):
                allow_help_offer = False
                
            # Live Web Search & Crawling pre-processor
            search_context_str = ""
            is_score_query = any(k in norm_speech for k in ["kac kac", "skor", "sonuc", "gol", "beraberlik", "mac durumu", "canli skor"])
            if websearch.is_realtime_query(user_speech):
                safe_print(Fore.YELLOW + f"\n[İnternet Arama: '{user_speech}' konusu canlı internette araştırılıyor...]")
                is_detailed = websearch.is_detailed_research_query(user_speech)
                num_results = 6 if is_detailed else 4
                
                # ── CANLI SKOR: Önce doğrudan canlı skor sayfasını crawl et ──
                live_score_raw = ""
                if is_score_query:
                    score_urls = [
                        "https://www.sofascore.com/football",
                        "https://www.flashscore.com",
                        "https://www.bbc.com/sport/football/scores-fixtures",
                    ]
                    for score_url in score_urls:
                        try:
                            chunks, err = scrape_url_text(score_url)
                            if chunks and not err:
                                combined = " ".join(chunks[:3])[:2000]
                                live_score_raw += f"\n--- {score_url} ---\n{combined}"
                                safe_print(Fore.GREEN + f"[Canlı Skor: {score_url} başarıyla okundu.]")
                                break  # İlk başarılı kaynak yeterli
                        except Exception as se:
                            continue

                search_results = websearch.search_ddg(user_speech, num_results=num_results)
                if search_results or live_score_raw:
                    search_context_str = "\n[İNTERNET ARAMA SONUÇLARI: "
                    if live_score_raw:
                        search_context_str += f"\n  [CANLI SKOR SAYFALARI (birincil kaynak, tam içerik):{live_score_raw}]"
                    for idx, res in enumerate(search_results, 1):
                        search_context_str += f"\n  Sonuç {idx}: {res['title']}\n    Kaynak: {res['link']}\n    Özet: {res['snippet']}"
                        
                    # Detaylı araştırma modu: En üstteki web sayfalarının tüm içeriğini tara
                    if is_detailed:
                        safe_print(Fore.YELLOW + "[Detaylı Araştırma: En alakalı web sayfalarının içerikleri derinlemesine analiz ediliyor...]")
                        crawled_details = ""
                        crawled_count = 0
                        for res in search_results[:2]:
                            link = res["link"]
                            if link and link.startswith("http"):
                                chunks, err = scrape_url_text(link)
                                if chunks and not err:
                                    crawled_count += 1
                                    combined = " ".join(chunks[:2])
                                    crawled_details += f"\n\n--- Detaylı Sayfa İçeriği ({link}) ---\n{combined[:1200]}..."
                        if crawled_details:
                            search_context_str += crawled_details
                            safe_print(Fore.GREEN + f"[Detaylı Araştırma: {crawled_count} kaynaktan derin bilgi derlendi.]")
                            
                    search_context_str += "\n]"
                else:
                    search_context_str = "\n[İNTERNET ARAMA SONUÇLARI: Canlı internet aramasında sonuç bulunamadı.]"

            # RAG semantic memory retriever
            retrieved_docs = []
            try:
                retrieved_docs = vectordb.search(user_speech, k=3, min_similarity=0.35)
            except Exception as e:
                print(f"[Vektör Arama Hatası: {e}]")
                
            archive_str = ""
            if retrieved_docs:
                archive_str = "\n[ARŞİV BELLEĞİ: "
                for idx, doc in enumerate(retrieved_docs, 1):
                    meta = doc.get("metadata", {})
                    source = meta.get("source", "Sohbet Geçmişi")
                    timestamp = meta.get("timestamp", "")
                    archive_str += f"\n  Kayıt {idx} (Kaynak: {source}, Zaman: {timestamp}): {doc['text']}"
                archive_str += "]"
                
            # Prepare Prompt Context Injection
            sys_info = f"Tarih: {get_turkish_datetime()}"
            dynamic_prefix = f"\n\n[Sistem Bilgisi - {sys_info} | KULLANICI TERCİHLERİ: {json.dumps(memory['user_preferences'])} | YAKLAŞAN PLANLAR:{reminder_list_str}]{collision_warning_injected}{search_context_str}{archive_str}"
            
            full_system_prompt = config.SYSTEM_PROMPT + dynamic_prefix
            
            messages = [{"role": "system", "content": full_system_prompt}]
            messages.extend(chat_history)
            messages.append({"role": "user", "content": user_speech})
            
            safe_print(Fore.CYAN + "Jarvis: " + Style.RESET_ALL, end="")
            
            # Prepare Temperature value dynamically
            is_realtime = websearch.is_realtime_query(user_speech)
            temp_val = 0.1 if is_realtime else 0.5
            # Skor/gerçek zamanlı sorgular: çok kısa çıktı vermeye zorla (maksimum 1-2 cümle)
            max_tokens = 100 if is_score_query else (256 if is_realtime else 1024)
            # Dinamik bağlam penceresi: daha küçük = daha fazla boş VRAM = daha fazla GPU katmanı = daha hızlı
            # Web araması daha fazla metin eklediği için daha fazla bağlama ihtiyaç duyar; basit sorgular küçük kalır
            ctx_size = 3072 if is_realtime else 2048
            
            # Yerel modeli akış (stream) ile sorgula
            try:
                publish_ui("state", "SPEAKING")
                stream = ollama.chat(
                    model=config.OLLAMA_MODEL,
                    messages=messages,
                    stream=True,
                    keep_alive=-1,
                    options={
                        "num_ctx": ctx_size,   # dinamik: 2048 basit / 3072 web araması
                        "num_thread": 8,       # maksimum CPU performansı için iş parçacıklarını 7800X3D'nin 8 fiziksel çekirdeğine kilitle
                        "num_predict": max_tokens,
                        "temperature": temp_val
                    }
                )
                full_reply = await speak_stream(stream, user_query=user_speech, allow_help_offer=allow_help_offer)
                
                # ── SKOR POST-PROCESSOR: Cevabı 1. cümleyle kırp ──
                # Eğer skor sorgusuysa, model yine de uzun cevap verirse sadece ilk cümleyi al
                if is_score_query and full_reply:
                    first_sentence_match = re.search(r'^([^.!?]+[.!?])', full_reply.strip())
                    if first_sentence_match:
                        full_reply = first_sentence_match.group(1).strip()
                
                # --- POST-PROCESSOR: HAFIZA VE TAKVİM ETİKET AYIKLAMA ---
                pref_matches = re.findall(r"\[BELLEK_KAYIT:\s*([^=]+)\s*=\s*([^\]]+)\]", full_reply)
                reminder_matches = re.findall(r"\[TAKTAK_HATIRLAT:\s*tarih=([^\s]+)\s+saat=([^\s]+)\s+konu=([^\]]+)\]", full_reply)
                
                # Bir şikayet sırasında yanlışlıkla tetiklenirse LLM hatırlatıcılarını yoksay
                if is_complaint:
                    reminder_matches = []
                
                # LLM bağlamını temiz tutmak için oturum sohbet geçmişinden etiketleri kaldır
                clean_reply = re.sub(r"\[BELLEK_KAYIT:[^\]]+\]", "", full_reply)
                clean_reply = re.sub(r"\[TAKTAK_HATIRLAT:[^\]]+\]", "", clean_reply).strip()
                
                if pref_matches or reminder_matches:
                    fresh_memory = load_memory()
                    
                    # 1. Tercihleri kaydet
                    for key, val in pref_matches:
                        key = key.strip()
                        val = val.strip()
                        key_norm = clean_for_comparison(key).replace(" ", "_")
                        whitelist = ["tuttugu_takim", "favori_araba", "en_sevdigin_renk", "izledigi_video", "yazilim_dili"]
                        if key_norm in whitelist:
                            fresh_memory["user_preferences"][key_norm] = val
                            safe_print(Fore.GREEN + f"\n[Akıllı Hafıza: '{key_norm}' tercihi '{val}' olarak kaydedildi.]")
                            
                    # 2. Hatırlatıcıları kaydet
                    for date_str, time_str, subject in reminder_matches:
                        date_str = date_str.strip()
                        time_str = time_str.strip()
                        subject = subject.strip()
                        
                        # Hatalı kayıtları önlemek için etiketteki taslak/yer tutucu değerleri doğrula
                        if "YYYY" in date_str or "SS" in time_str or "Etkinlik" in subject:
                            continue
                            
                        # Apply Akıllı Konu Temizleyici
                        subject = clean_reminder_subject(subject)
                        
                        new_reminder = {
                            "date": date_str,
                            "time": time_str,
                            "subject": subject,
                            "status": "active"
                        }
                        
                        # Prevent duplicate entries
                        exists = False
                        for rem in fresh_memory["reminders"]:
                            if rem.get("date") == date_str and rem.get("time") == time_str and rem.get("subject") == subject:
                                exists = True
                                break
                                
                        if not exists:
                            fresh_memory["reminders"].append(new_reminder)
                            safe_print(Fore.GREEN + f"\n[Akıllı Takvim: '{subject}' planı {date_str} saat {time_str} için başarıyla kaydedildi.]")
                            
                    save_memory(fresh_memory)
                
                # Aktif oturum geçmişine ekle
                chat_history.append({"role": "user", "content": user_speech})
                chat_history.append({"role": "assistant", "content": clean_reply})
                
                # Sonsuz hafıza için bu konuşma sırasını asenkron olarak dizine ekle
                rag_queue.put(("chat", user_speech, clean_reply))
                publish_ui("state", "IDLE")
                
            except speech.SpeechInterrupted:
                # Konuşma kullanıcı tarafından kesildi, geçmişi temiz tut ve kontrolü devret
                publish_ui("state", "IDLE")
                continue
            except Exception as e:
                safe_print(Fore.RED + f"\n[Hata oluştu efendim: {e}]")
                publish_ui("state", "IDLE")
                
        except KeyboardInterrupt:
            safe_print(Fore.YELLOW + "\n[Oturum kesildi efendim, kapatıyorum...]")
            break
        except Exception as e:
            safe_print(Fore.RED + f"\n[Hata: {e}]")
            publish_ui("state", "IDLE")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())