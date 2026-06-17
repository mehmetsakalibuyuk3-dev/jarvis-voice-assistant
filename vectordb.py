# vectordb.py - Saf Python ile Hafif ve Thread-Safe Vektör Veri Tabanı (C++ Derleyicisi Gerektirmez)
import os
import json
import datetime
import threading
import ollama

class VectorDB:
    def __init__(self, db_path=None, model="nomic-embed-text"):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "vector_store.json")
        self.db_path = db_path
        self.model = model
        self.lock = threading.Lock()
        self.store = []
        self.load()

    def load(self):
        """Yerel JSON dosyasından vektör veri tabanını yükler."""
        with self.lock:
            if not os.path.exists(self.db_path):
                self.store = []
                return
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self.store = json.load(f)
            except Exception:
                self.store = []

    def save(self):
        """Vektör veri tabanını güvenli bir şekilde diske geri kaydeder."""
        with self.lock:
            try:
                # Çökme durumunda bozulmayı önlemek için geçici dosya üzerinden kaydet
                temp_path = self.db_path + ".tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self.store, f, ensure_ascii=False, indent=2)
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
                os.rename(temp_path, self.db_path)
            except Exception as e:
                print(f"[Vektör Kayıt Hatası: {e}]")

    def _get_embedding(self, text):
        """Kalıcı VRAM kilidi ile vektör oluşturmak için yerel Ollama embeddings API'sini sorgular."""
        try:
            res = ollama.embeddings(model=self.model, prompt=text, keep_alive=-1)
            return res.get("embedding", None)
        except Exception as e:
            # nomic-embed-text eksikse veya ollama çevrimdışıysa yedek önlem
            print(f"[Embedding Çekim Hatası: {e}]")
            return None

    def add(self, text, metadata=None):
        """İsteğe bağlı meta verilerle vektör deposuna yeni bir metin parçası ekler."""
        if not text or text.strip() == "":
            return False
            
        vector = self._get_embedding(text)
        if not vector:
            return False
            
        if metadata is None:
            metadata = {}
        metadata["timestamp"] = metadata.get("timestamp", datetime.datetime.now().isoformat())
        
        entry = {
            "text": text.strip(),
            "vector": vector,
            "metadata": metadata
        }
        
        with self.lock:
            # Birebir aynı olan kopyaların eklenmesini önle
            exists = False
            for item in self.store:
                if item["text"] == entry["text"]:
                    exists = True
                    break
            if not exists:
                self.store.append(entry)
                
        self.save()
        return True

    @staticmethod
    def _cosine_similarity(v1, v2):
        """İki vektör arasındaki kosinüs benzerliğini hesaplar."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
            
        dot_product = sum(x * y for x, y in zip(v1, v2))
        mag1 = sum(x * x for x in v1) ** 0.5
        mag2 = sum(x * x for x in v2) ** 0.5
        
        if mag1 == 0.0 or mag2 == 0.0:
            return 0.0
            
        return dot_product / (mag1 * mag2)

    def search(self, query_text, k=3, min_similarity=0.35):
        """Kosinüs benzerliği kullanarak semantik arama gerçekleştirir ve en alakalı k adet belgeyi döndürür."""
        if not query_text or query_text.strip() == "":
            return []
            
        query_vector = self._get_embedding(query_text)
        if not query_vector:
            return []
            
        results = []
        with self.lock:
            for item in self.store:
                similarity = self._cosine_similarity(query_vector, item["vector"])
                if similarity >= min_similarity:
                    results.append({
                        "text": item["text"],
                        "metadata": item["metadata"],
                        "similarity": similarity
                    })
                    
        # Benzerlik oranına göre azalan şekilde sırala
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:k]
