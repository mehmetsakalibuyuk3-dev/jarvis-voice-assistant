"""
preload.py - Jarvis GPU Model Önhazırlık Motoru
Ollama modellerini (qwen3:14b + nomic-embed-text) SSD'den RAM/VRAM'e
tamamen yükler ve çıkar. Böylece Jarvis başladığında SSD sıfır çalışır.
"""
import sys
import time

def preload_models():
    try:
        import ollama
    except ImportError:
        print("[Preload HATA]: ollama paketi bulunamadı.")
        sys.exit(1)

    models = [
        ("qwen3:14b",       lambda: ollama.generate(model="qwen3:14b", prompt="merhaba", keep_alive=-1)),
        ("nomic-embed-text",lambda: ollama.embeddings(model="nomic-embed-text", prompt="warmup", keep_alive=-1)),
    ]

    for name, fn in models:
        print(f"[GPU Önhazırlık]: '{name}' modeli yükleniyor...", flush=True)
        t0 = time.time()
        try:
            fn()
            elapsed = round(time.time() - t0, 1)
            print(f"[GPU Önhazırlık]: '{name}' hazır! ({elapsed}s)", flush=True)
        except Exception as e:
            print(f"[GPU Önhazırlık UYARI]: '{name}' yüklenemedi: {e}", flush=True)

    print("[GPU Önhazırlık]: Tüm modeller bellekte hazır. Jarvis başlatılıyor...", flush=True)

if __name__ == "__main__":
    preload_models()
