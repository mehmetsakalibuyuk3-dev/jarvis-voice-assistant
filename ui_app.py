import os
import sys
import webview

def main():
    # index.html dosyasının mutlak yolunu dinamik olarak çöz
    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(current_dir, 'jarvis_ui', 'index.html')
    
    if not os.path.exists(html_path):
        print(f"[Error] HTML file not found at {html_path}")
        sys.exit(1)
        
    # Yerel dosyaların Edge/WebView2 tarafından önbelleğe alınmasını önlemek için dinamik Cache-Buster enjeksiyonu
    try:
        import re
        import time
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        ts = int(time.time())
        content = re.sub(r'style\.css\?v=[^\'\"]+', f'style.css?v={ts}', content)
        content = re.sub(r'script\.js\?v=[^\'\"]+', f'script.js?v={ts}', content)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[UI App] Cache-buster injected successfully (ts={ts}).")
    except Exception as ce:
        print(f"[UI App WARNING] Cache-buster failed: {ce}")
        
    url = f"file:///{html_path.replace(os.sep, '/')}"
    print(f"[UI App] Loading URL: {url}")
    
    # Görkemli, çerçevesiz ve yüksek kaliteli bir webview penceresi oluştur
    window = webview.create_window(
        title="JARVIS AGI HUD",
        url=url,
        width=1366,
        height=768,
        frameless=True,
        easy_drag=True,
        background_color='#030708',
        on_top=False
    )
    
    # Güncellemeler sırasında önbellek sorunlarını önlemek için webview'ı gizli modda (private mode) başlat
    webview.start(private_mode=True, debug=False)

if __name__ == '__main__':
    main()
