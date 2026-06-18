# JARVIS: Offline AI Voice Assistant with WebGL HUD

JARVIS is a fully local, offline voice-controlled AI assistant. It integrates a local Large Language Model (LLM) and Embedding model with a futuristic holographic WebGL HUD (Heads-Up Display) and OS-level automation controls. 

Designed for speed and offline privacy, JARVIS bypasses external API dependencies entirely by running models locally via Ollama.
[Proje Tanıtım Videosunu İzlemek İçin Tıklayın](https://youtu.be/mUKLuC3RcMs)
---

## 🚀 Key Features

- **完全本地运行 (100% Offline & Local):** Powered by Ollama (`qwen3:14b` for chat, `nomic-embed-text` for embeddings). No internet required.
- **Real-Time Token Streaming:** Implements a custom `asyncio.Queue` + daemon thread architecture in Python to stream generated tokens to the UI over WebSockets in real-time (typewriter effect) with sub-100ms response time.
- **GPU VRAM Preloading:** Includes a startup manager (`preload.py`) that preloads LLM and embedding models into GPU memory before the assistant starts, eliminating initial SSD load spikes.
- **Futuristic WebGL HUD:** Responsive 3D holographic interface built with Three.js, streaming microphone visualization, real-time CPU/GPU monitoring, and interactive bubble layout.
- **Local RAG Memory:** Automatically embeds and stores user conversations locally using a lightweight Vector Store for persistent memory.
- **Voice-Command OS Automation:** Controls web browsers, plays media, executes searches, and manages browser history (backward, forward, refresh) instantly and silently.

---

## 🛠️ Architecture & Technologies

- **Backend:** Python 3.11+, `asyncio`, `websockets`, `pyautogui`, `psutil`
- **Speech processing:** `edge-tts` (TTS), `SpeechRecognition` (STT)
- **AI / LLM Core:** `Ollama` (`qwen3:14b` & `nomic-embed-text`)
- **Frontend UI:** JavaScript (ES6+), Three.js (WebGL), Vanilla CSS3, HTML5
- **Automation:** Keyboard & mouse emulation via `pyautogui`

---

## 📂 Project Structure

```text
├── jarvis.py             # Core voice assistant engine & WebSocket server
├── speech.py             # Text-To-Speech (TTS) and Speech-To-Text (STT) wrappers
├── vectordb.py           # Local vector database and RAG implementation
├── preload.py            # GPU VRAM warm-up daemon
├── config.py             # App configurations, mappings, and prompt settings
├── jarvis_ui/            # Three.js 3D Holographic HUD frontend
│   ├── index.html
│   ├── script.js         # WebGL logic & WebSocket client
│   └── style.css         # Futuristic HUD styles
├── JARVIS.bat            # Windows startup script
└── .gitignore            # Git exclusion rules
```

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com/) installed and running.
- Pull the required models:
  ```bash
  ollama pull qwen3:14b
  ollama pull nomic-embed-text
  ```

### Installation
1. Clone this repository:
   ```bash
   git clone <your-repository-url>
   cd jarvis-voice-assistant
   ```
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Run the application:
   Double-click `JARVIS.bat` or run:
   ```bash
   python jarvis.py
   ```
