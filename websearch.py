# websearch.py - Jarvis Yapay Zeka Gerçek Zamanlı Web Arama ve Arama Motoru
import urllib.request
import urllib.parse
import re
import html
import json
import os

def augment_football_query(query):
    """
    Türkçe canlı skor/futbol sorgularını, küresel haber ve skor merkezlerinden doğru canlı sonuçları
    çekmek için akıllıca son derece verimli İngilizce gerçek zamanlı anahtar kelimelere genişletir.
    """
    if not query:
        return ""
    
    query_norm = query.lower()
    
    # Bilinen oyuncu isimleri - her zaman güncel bilgiyi ara
    known_players = [
        "osimhen", "mbappe", "ronaldo", "messi", "haaland", "benzema",
        "neymar", "salah", "kane", "bellingham", "vinicius", "saka",
        "icardi", "drogba", "sneijder", "zaha", "tadic", "dzeko",
        "muslera", "akgun", "akturkoglu", "kerem"
    ]
    
    # Oyuncu profili sorgusu → mevcut kulübü ve haberleri ara
    for player in known_players:
        if player in query_norm:
            if any(k in query_norm for k in ["hakkinda", "hakkında", "kim", "nerede", "hangi", "transfer", "takim", "takım", "oynuyor", "bilgi"]):
                # Oyuncu adını uygun forma dönüştür
                player_cap = player.capitalize()
                if player == "osimhen":
                    return "Victor Osimhen current club transfer 2025 2026"
                elif player == "mbappe":
                    return "Kylian Mbappe current club 2025 2026"
                return f"{player_cap} current club transfer news 2026"
    
    # Eğer bu bir futbol/spor skor sorgusuysa, genişlet
    if any(k in query_norm for k in ["maç", "maci", "mac", "skor", "kaç kaç", "kac kac", "final", "şampiyon", "sampiyon"]):
        # Temel takımları belirle
        teams = []
        if "galatasaray" in query_norm:
            teams.append("Galatasaray")
        if any(f in query_norm for f in ["fenerbahce", "fenerbahçe"]):
            teams.append("Fenerbahce")
        if any(b in query_norm for b in ["besiktas", "beşiktaş"]):
            teams.append("Besiktas")
        if "trabzonspor" in query_norm:
            teams.append("Trabzonspor")
        if any(p in query_norm for p in ["paris", "psg"]):
            teams.append("PSG")
        if "arsenal" in query_norm:
            teams.append("Arsenal")
        if "real madrid" in query_norm:
            teams.append("Real Madrid")
        if "bayern" in query_norm:
            teams.append("Bayern Munich")
        if "barcelona" in query_norm:
            teams.append("Barcelona")
            
        if len(teams) >= 2:
            return f"{teams[0]} vs {teams[1]} live score today 2026"
        elif len(teams) == 1:
            return f"{teams[0]} live score match today 2026"
        else:
            if any(c in query_norm for c in ["şampiyonlar ligi", "champions league", "final"]):
                return "UEFA Champions League final live score 30 May 2026"
            return query + " live score today 2026"
            
    return query

def search_ddg(query, num_results=5):
    """
    DuckDuckGo HTML üzerinde sıfır bağımlılıklı, anahtarsız arama gerçekleştirir.
    Geriye bir sözlük listesi döndürür: [{'title': ..., 'link': ..., 'snippet': ...}]
    """
    augmented = augment_football_query(query)
    # Konsolda arama sorgusunu yazdır, böylece kullanıcı tam olarak ne aradığımızı bilsin!
    if augmented != query:
        print(f"\n[Geliştirilmiş Arama Sorgusu: '{augmented}']")
        
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(augmented)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    )
    
    results = []
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            page_html = response.read().decode('utf-8', errors='ignore')
            
            # Web sonucu bloklarını ayıkla
            blocks = re.findall(r'<div class="[^"]*web-result[^"]*">([\s\S]*?)<div class="clear"></div>', page_html)
            
            for res in blocks[:num_results]:
                # Başlığı ayıkla
                title_match = re.search(r'<a[^>]*class="result__a"[^>]*>([\s\S]*?)</a>', res)
                title = title_match.group(1).strip() if title_match else "No Title"
                title = html.unescape(re.sub(r'<[^>]+>', '', title))
                
                # Özet metni ayıkla
                snippet_match = re.search(r'<a[^>]*class="result__snippet"[^>]*>([\s\S]*?)</a>', res)
                snippet = snippet_match.group(1).strip() if snippet_match else "No Snippet"
                snippet = html.unescape(re.sub(r'<[^>]+>', '', snippet))
                
                # result__a içindeki uddg parametresinden doğrudan yönlendirme URL'sini çıkar
                link = "No Link"
                url_match = re.search(r'href="([^"]+)"', res)
                if url_match:
                    raw_link = url_match.group(1)
                    if "uddg=" in raw_link:
                        parsed_query = urllib.parse.parse_qs(urllib.parse.urlparse(raw_link).query)
                        if "uddg" in parsed_query:
                            link = parsed_query["uddg"][0]
                    else:
                        if raw_link.startswith("//"):
                            link = "https:" + raw_link
                        elif raw_link.startswith("/"):
                            link = "https://duckduckgo.com" + raw_link
                        else:
                            link = raw_link
                
                results.append({
                    "title": title,
                    "link": link,
                    "snippet": snippet
                })
    except Exception as e:
        print(f"[Web Arama Hatası: {e}]")
        
    return results

def is_realtime_query(query_text):
    """
    Sorgunun canlı/gerçek zamanlı bilgi gerektirip gerektirmediğini akıllıca algılar.
    """
    if not query_text:
        return False
        
    query_norm = query_text.lower()
    
    # Check for direct search/realtime trigger keywords
    triggers = [
        # Skor ve maç
        "skor", "maç", "mac", "kaç kaç", "kac kac", "canlı", "canli",
        "puan durumu", "lider kim",
        # Oyuncu ve transfer bilgisi
        "futbolcu", "fıtbolcu", "oyuncu", "transfer", "nerede oynuyor",
        "hangi takimda", "hangi takımda", "hangi kulupte", "hangi kulüpte",
        "hakkinda", "hakkında",  # ← EKLENDİ: "X hakkında" sorgularını yakala
        # Genel bilgi
        "kimdir", "nedir", "neymiş", "neymis",
        # Hava ve haberler
        "hava durumu", "bugün", "bugun",
        "haber", "haberler", "son dakika", "son durum",
        # Arama komutları
        "arama yap", "araştır", "arastir", "internetten bak",
        "webden ara", "araştırır mısın", "sorgula", "güncel", "guncel"
    ]
    
    # Bilinen oyuncular: her zaman güncel bilgiyi getir (eğitim verileri güncelliğini yitirmiştir)
    known_players = [
        "osimhen", "mbappe", "ronaldo", "messi", "haaland", "benzema",
        "neymar", "salah", "kane", "bellingham", "vinicius", "saka",
        "icardi", "drogba", "sneijder", "zaha", "tadic", "dzeko",
        "muslera", "akgun", "akturkoglu", "kerem"
    ]
    for player in known_players:
        if player in query_norm:
            return True
    
    # Kullanıcı açıkça kontrol etmeyi veya aramayı isterse
    for trig in triggers:
        if trig in query_norm:
            return True
            
    # Galatasaray/Fenerbahçe vb. güncel maç sorgularını kontrol et
    teams = ["galatasaray", "fenerbahçe", "fenerbahce", "beşiktaş", "besiktas", "trabzonspor"]
    for team in teams:
        if team in query_norm and any(k in query_norm for k in ["maçı", "maci", "skoru", "oynuyor", "hakkinda", "hakkında"]):
            return True
            
    return False

def is_detailed_research_query(query_text):
    """
    Kullanıcının derin araştırma (tarayıcının tüm sayfaları okuması) isteyip istemediğini algılar.
    """
    if not query_text:
        return False
    query_norm = query_text.lower()
    
    research_triggers = [
        "detaylıca araştır", "detaylı araştır", "detaylica arastir", "detayli arastir",
        "derinlemesine araştır", "iyice araştır", "genişçe araştır", "detaylı bilgi ver"
    ]
    for trig in research_triggers:
        if trig in query_norm:
            return True
    return False
