try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import io
import json
import os
import time
import wave
import math
import queue
import random
import tempfile
import struct
import threading
import tkinter as tk
import pyaudio
import pygame
import openai
import pvporcupine
import requests
from PIL import Image, ImageDraw
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306

# ============================================================
# --- BÖLÜM 1: CONFIG ---
# ============================================================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "senin-api-keyin")
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "senin-porcupine-keyin")
WAKE_WORD_KEYWORD_PATH = "hey-aris.ppn"
MIC_DEVICE_INDEX = 0
OLED_WIDTH = 128
OLED_HEIGHT = 64
RECORD_DURATION = 5
MAX_HISTORY = 10

# VAD ayarları
VAD_MAX_DURATION = 15    # saniye — maksimum kayıt süresi
VAD_SILENCE_LIMIT = 1.2  # saniye — bu kadar sessizlikte kayıt biter
VAD_MIN_SPEECH = 0.5     # saniye — minimum konuşma süresi

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "senin-client-id")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "senin-client-secret")
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "senin-weather-api-keyin")
DEFAULT_CITY = "Istanbul"

openai.api_key = OPENAI_API_KEY
_openai_client = openai.OpenAI()

try:
    pygame.mixer.init()
except Exception as e:
    print(f"[TTS] pygame.mixer başlatılamadı: {e}")

_spotify = None
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    _spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope="user-modify-playback-state user-read-playback-state user-read-currently-playing",
    ))
except Exception as e:
    print(f"[SPOTIFY] Spotify başlatılamadı: {e}")

# ============================================================
# --- BÖLÜM 2: KİŞİLİK (PERSONALITY) ---
# ============================================================

SYSTEM_PROMPT = """Sen Aris'sin — gerçek bir arkadaş gibi konuşan bir yapay zeka.

Tarz:
- Günlük Türkçe kullan: "ya", "kanka", "lan", "nbr", "aynen" gibi ifadeler doğal gelsin, her cümlede değil.
- "Tabii ki!", "Elbette!", "Kesinlikle!" gibi klişe asistan başlangıçları kullanma. Her yanıt farklı bir tonla başlasın.
- Genellikle 1-2 cümle yeter. Kısa ve öz ol.
- Önemli bir konu varsa biraz açıkla, ama akademik dile girme.
- İlginç bir şey duyunca "ya ciddi misin", "haha dur bir dakika", "yok artık" gibi tepkiler verebilirsin.
- Emoji kullanma — sadece çok uygunsa 1 tane.
- Her zaman Türkçe yaz.
"""

conversation_history = []

# Wake event — simülasyon modunda butona basılınca tetiklenir
_wake_event = threading.Event()

# ============================================================
# --- BÖLÜM 3: OLED YÜZ İFADELERİ (FACE) ---
# ============================================================

oled_device = None
try:
    serial = i2c(port=1, address=0x3C)
    oled_device = ssd1306(serial, width=OLED_WIDTH, height=OLED_HEIGHT)
except Exception as e:
    print(f"[OLED] OLED başlatılamadı, yüz ifadeleri devre dışı: {e}")


def _render_face(draw_func):
    if oled_device is None:
        return
    try:
        image = Image.new("1", (OLED_WIDTH, OLED_HEIGHT), 0)
        draw = ImageDraw.Draw(image)
        draw_func(draw)
        oled_device.display(image)
    except Exception as e:
        print(f"[OLED] Yüz çizilirken hata: {e}")


def show_face_idle():
    def draw(d):
        d.ellipse([30, 20, 50, 38], outline=255)
        d.ellipse([37, 27, 43, 33], fill=255)
        d.ellipse([78, 20, 98, 38], outline=255)
        d.ellipse([85, 27, 91, 33], fill=255)
        d.line([48, 52, 80, 52], fill=255, width=2)
    _render_face(draw)


def show_face_listening():
    def draw(d):
        d.ellipse([24, 16, 52, 42], outline=255)
        d.ellipse([35, 26, 44, 34], fill=255)
        d.ellipse([76, 16, 104, 42], outline=255)
        d.ellipse([87, 26, 96, 34], fill=255)
        d.arc([48, 46, 80, 60], start=0, end=180, fill=255, width=2)
    _render_face(draw)


def show_face_thinking():
    def draw(d):
        d.line([24, 18, 50, 24], fill=255, width=2)
        d.line([78, 24, 104, 18], fill=255, width=2)
        d.ellipse([28, 22, 50, 42], outline=255)
        d.text((34, 26), "?", fill=255)
        d.ellipse([78, 22, 100, 42], outline=255)
        d.text((84, 26), "?", fill=255)
        d.line([48, 54, 80, 54], fill=255, width=2)
    _render_face(draw)


def show_face_talking():
    def draw(d):
        d.ellipse([28, 18, 50, 38], outline=255)
        d.ellipse([35, 25, 43, 33], fill=255)
        d.ellipse([78, 18, 100, 38], outline=255)
        d.ellipse([85, 25, 93, 33], fill=255)
        d.arc([40, 44, 88, 62], start=0, end=180, fill=255, width=3)
        d.line([40, 53, 88, 53], fill=255, width=1)
    _render_face(draw)


def show_face_happy():
    def draw(d):
        d.arc([28, 24, 50, 40], start=180, end=0, fill=255, width=3)
        d.arc([78, 24, 100, 40], start=180, end=0, fill=255, width=3)
        d.arc([32, 42, 96, 62], start=0, end=180, fill=255, width=3)
    _render_face(draw)


# ============================================================
# --- BÖLÜM 4: SIYAH GUI (tkinter) ---
# ============================================================

_gui_queue = queue.Queue()
_gui_root = None

_EYE_BASE_LEFT = (160, 160)
_EYE_BASE_RIGHT = (320, 160)
_EYE_W = 70
_EYE_H = 60
_PUPIL_R = 12


class ArisGUI:
    """Aris için siyah arka planlı tkinter arayüzü."""

    def __init__(self, root):
        self.root = root
        self.root.title("ARİS")
        self.root.configure(bg="black")
        self.root.resizable(False, False)

        self.label_title = tk.Label(
            root, text="ARİS", font=("Helvetica", 48, "bold"),
            fg="white", bg="black"
        )
        self.label_title.pack(pady=(20, 0))

        self.canvas = tk.Canvas(root, width=480, height=280, bg="black", highlightthickness=0)
        self.canvas.pack(pady=10)

        self.label_status = tk.Label(
            root, text="Bekliyorum...", font=("Helvetica", 18),
            fg="white", bg="black"
        )
        self.label_status.pack(pady=(0, 10))

        # Konuş butonu — simülasyon modunda wake word yerine kullanılır
        self.btn_wake = tk.Button(
            root, text="🎤  Konuş", font=("Helvetica", 16, "bold"),
            bg="#1a1a1a", fg="white", activebackground="#333333",
            activeforeground="white", relief="flat", padx=30, pady=12,
            cursor="hand2", command=self._on_wake_button
        )
        self.btn_wake.pack(pady=(0, 20))

        self.state = "idle"
        self._blink_open = True
        self._idle_offset = [0, 0]
        self._idle_target = [0, 0]
        self._idle_step = [0, 0]
        self._idle_count = 0

        self._draw_eyes()
        self._process_queue()
        self._animate()

    def _on_wake_button(self):
        """Konuş butonuna basılınca wake event'i tetikle."""
        _wake_event.set()

    def _process_queue(self):
        try:
            while True:
                new_state = _gui_queue.get_nowait()
                self._set_state(new_state)
        except queue.Empty:
            pass
        self.root.after(50, self._process_queue)

    def _set_state(self, state):
        self.state = state
        status_map = {
            "idle": "Bekliyorum...",
            "listening": "Dinliyorum...",
            "thinking": "Düşünüyorum...",
            "talking": "Konuşuyorum...",
            "happy": "😊",
        }
        self.label_status.config(text=status_map.get(state, ""))
        self._draw_eyes()

    def _animate(self):
        try:
            if self.state == "idle":
                self._animate_idle()
            elif self.state == "talking":
                self._animate_talking()
            self._draw_eyes()
        except Exception:
            pass
        self.root.after(80, self._animate)

    def _animate_idle(self):
        self._idle_count -= 1
        for i in range(2):
            if self._idle_count <= 0 or self._idle_step[i] == 0:
                self._idle_target[i] = random.randint(-18, 18)
                steps = random.randint(15, 30)
                self._idle_step[i] = (self._idle_target[i] - self._idle_offset[i]) / max(steps, 1)
                self._idle_count = steps
            self._idle_offset[i] += self._idle_step[i]
            if abs(self._idle_offset[i] - self._idle_target[i]) < abs(self._idle_step[i]):
                self._idle_offset[i] = self._idle_target[i]
                self._idle_step[i] = 0

    def _animate_talking(self):
        self._blink_open = not self._blink_open

    def _draw_eyes(self):
        self.canvas.delete("all")
        state = self.state

        lx = _EYE_BASE_LEFT[0] + self._idle_offset[0]
        rx = _EYE_BASE_RIGHT[0] + self._idle_offset[1]
        ly = _EYE_BASE_LEFT[1]
        ry = _EYE_BASE_RIGHT[1]

        ew = _EYE_W
        eh = _EYE_H

        if state == "listening":
            ew = int(_EYE_W * 1.3)
            eh = int(_EYE_H * 1.3)
            self._draw_eye(lx, ly, ew, eh, pupil_dy=0)
            self._draw_eye(rx, ry, ew, eh, pupil_dy=0)

        elif state == "thinking":
            self._draw_eye(lx, ly, ew, eh, pupil_dy=-12)
            self._draw_eye(rx, ry, ew, eh, pupil_dy=-12)
            self.canvas.create_line(lx - ew, ly - eh - 14, lx + ew, ly - eh - 4, fill="white", width=4)
            self.canvas.create_line(rx - ew, ry - eh - 4, rx + ew, ry - eh - 14, fill="white", width=4)

        elif state == "talking":
            if self._blink_open:
                self._draw_eye(lx, ly, ew, eh, pupil_dy=0)
                self._draw_eye(rx, ry, ew, eh, pupil_dy=0)
            else:
                self._draw_eye_closed(lx, ly, ew)
                self._draw_eye_closed(rx, ry, ew)

        elif state == "happy":
            self._draw_eye_happy(lx, ly, ew)
            self._draw_eye_happy(rx, ry, ew)

        else:
            self._draw_eye(lx, ly, ew, eh, pupil_dy=0)
            self._draw_eye(rx, ry, ew, eh, pupil_dy=0)

    def _draw_rounded_rect_filled(self, x1, y1, x2, y2, radius=18, color="white"):
        """Dolu yuvarlak köşeli dikdörtgen çizer."""
        r = radius
        self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline="")
        self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline="")
        self.canvas.create_arc(x1, y1, x1 + 2*r, y1 + 2*r, start=90, extent=90, fill=color, outline="", style=tk.PIESLICE)
        self.canvas.create_arc(x2 - 2*r, y1, x2, y1 + 2*r, start=0, extent=90, fill=color, outline="", style=tk.PIESLICE)
        self.canvas.create_arc(x1, y2 - 2*r, x1 + 2*r, y2, start=180, extent=90, fill=color, outline="", style=tk.PIESLICE)
        self.canvas.create_arc(x2 - 2*r, y2 - 2*r, x2, y2, start=270, extent=90, fill=color, outline="", style=tk.PIESLICE)

    def _draw_eye(self, cx, cy, ew, eh, pupil_dy=0):
        """Yuvarlak köşeli kare göz çiz."""
        x1, y1, x2, y2 = cx - ew, cy - eh, cx + ew, cy + eh
        self._draw_rounded_rect_filled(x1, y1, x2, y2, radius=18, color="white")
        py = cy + pupil_dy
        pr = _PUPIL_R
        self.canvas.create_oval(cx - pr, py - pr, cx + pr, py + pr, fill="black", outline="")

    def _draw_eye_closed(self, cx, cy, ew):
        self._draw_rounded_rect_filled(cx - ew, cy - 6, cx + ew, cy + 6, radius=6, color="white")

    def _draw_eye_happy(self, cx, cy, ew):
        self.canvas.create_arc(
            cx - ew, cy - _EYE_H // 2, cx + ew, cy + _EYE_H // 2,
            start=0, extent=180, fill="white", outline="", style=tk.CHORD
        )


def start_gui():
    """GUI'yi ana thread'de başlat (macOS tkinter zorunluluğu)."""
    global _gui_root
    try:
        root = tk.Tk()
        _gui_root = root
        ArisGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"[GUI] GUI başlatılamadı: {e}")


def set_gui_state(state: str):
    """GUI durumunu değiştir. Thread-safe."""
    try:
        _gui_queue.put_nowait(state)
    except Exception:
        pass

# ============================================================
# --- BÖLÜM 4b: SPOTIFY & FUNCTION CALLING TOOLS ---
# ============================================================

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": "Spotify'da şarkı veya müzik çal. Kullanıcı müzik dinlemek, şarkı açmak istediğinde kullan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Şarkı adı, sanatçı adı veya arama terimi. Genel müzik isteğinde boş bırak."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pause_music",
            "description": "Spotify'da çalan müziği durdur/pausela.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "next_track",
            "description": "Spotify'da sonraki şarkıya geç.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Bir şehrin hava durumunu öğren.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Şehir adı. Belirtilmezse varsayılan İstanbul."
                    }
                }
            }
        }
    }
]


def _execute_tool(name: str, arguments: dict) -> str:
    """Tool call'ı çalıştır ve sonucu döndür."""
    if name == "play_music":
        if _spotify is None:
            return "Spotify bağlı değil."
        query = arguments.get("query", "") or ""
        try:
            if query and len(query.strip()) > 2:
                results = _spotify.search(q=query, type="track", limit=1)
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    uri = tracks[0]["uri"]
                    _spotify.start_playback(uris=[uri])
                    track_name = tracks[0]["name"]
                    artist = tracks[0]["artists"][0]["name"]
                    return f"{artist} - {track_name} çalınıyor."
                else:
                    return f"'{query}' için şarkı bulunamadı."
            else:
                _spotify.start_playback()
                return "Müzik açıldı."
        except Exception as e:
            print(f"[SPOTIFY] Hata: {e}")
            return "Spotify komutu çalıştırılamadı."

    elif name == "pause_music":
        if _spotify is None:
            return "Spotify bağlı değil."
        try:
            _spotify.pause_playback()
            return "Müzik durduruldu."
        except Exception as e:
            print(f"[SPOTIFY] Hata: {e}")
            return "Müzik durdurulamadı."

    elif name == "next_track":
        if _spotify is None:
            return "Spotify bağlı değil."
        try:
            _spotify.next_track()
            return "Sonraki şarkıya geçildi."
        except Exception as e:
            print(f"[SPOTIFY] Hata: {e}")
            return "Sonraki şarkıya geçilemedi."

    elif name == "get_weather":
        city = arguments.get("city", DEFAULT_CITY) or DEFAULT_CITY
        return get_weather(city)

    return "Bilinmeyen fonksiyon."


# ============================================================
# --- BÖLÜM 4c: HAVA DURUMU ---
# ============================================================

def get_weather(city: str = DEFAULT_CITY) -> str:
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=tr"
        )
        resp = requests.get(url, timeout=5)

        if resp.status_code != 200:
            return f"{city} için hava durumu alınamadı."

        try:
            data = resp.json()
        except Exception:
            return f"{city} için hava durumu alınamadı."

        if "main" not in data:
            return f"{city} için hava durumu alınamadı."

        temp = round(data["main"]["temp"])
        feels = round(data["main"]["feels_like"])
        humidity = data["main"]["humidity"]
        description = data["weather"][0]["description"].capitalize()

        return (
            f"{city} hava durumu: {description}. "
            f"Sıcaklık {temp}°C, hissedilen {feels}°C, nem %{humidity}."
        )
    except Exception as e:
        print(f"[HAVA] Hava durumu alınamadı: {e}")
        return "Hava durumu bilgisi alınamadı."


def _extract_city(text: str) -> str:
    t = text.lower()
    for suffix in ("'da", "'de", "'ta", "'te", " da ", " de ", " ta ", " te "):
        idx = t.find(suffix)
        if idx > 0:
            before = text[:idx].strip()
            words = before.split()
            if words:
                candidate = " ".join(words[-3:]) if len(words) >= 3 else " ".join(words)
                if len(candidate) > 2:
                    return candidate.title()
    return DEFAULT_CITY


# ============================================================
# --- BÖLÜM 5: KONUŞMADAN METİNE (STT) ---
# ============================================================

def record_audio(duration=RECORD_DURATION):
    """Ses kaydı yap. webrtcvad varsa VAD kullan, yoksa sabit süreli kayda geri dön."""
    audio = pyaudio.PyAudio()
    sample_format = pyaudio.paInt16
    channels = 1
    rate = 16000
    sample_width = audio.get_sample_size(sample_format)
    frames = []

    try:
        import webrtcvad
        vad = webrtcvad.Vad(2)  # aggressiveness 0-3
        chunk = 480  # 30ms at 16000Hz — webrtcvad yalnızca 10ms/20ms/30ms frame destekler

        try:
            stream = audio.open(
                format=sample_format,
                channels=channels,
                rate=rate,
                frames_per_buffer=chunk,
                input=True,
                input_device_index=MIC_DEVICE_INDEX,
            )

            print("[STT] VAD ile dinleniyor...")
            silent_frames = 0
            speech_frames = 0
            speaking = False
            max_frames = int(VAD_MAX_DURATION * rate / chunk)
            silence_limit = int(VAD_SILENCE_LIMIT * rate / chunk)
            min_speech = int(VAD_MIN_SPEECH * rate / chunk)

            for _ in range(max_frames):
                data = stream.read(chunk, exception_on_overflow=False)
                frames.append(data)
                is_speech = vad.is_speech(data, rate)
                if is_speech:
                    speaking = True
                    speech_frames += 1
                    silent_frames = 0
                elif speaking:
                    silent_frames += 1
                    if silent_frames >= silence_limit:
                        print("[STT] Sessizlik algılandı, kayıt bitti.")
                        break

            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"[STT] VAD kayıt hatası: {e}")
            audio.terminate()
            return None

        if speech_frames < min_speech:
            print("[STT] Yeterince ses algılanamadı.")
            audio.terminate()
            return None

    except ImportError:
        # webrtcvad yok, sabit süreli kayda geri dön
        chunk = 1024
        num_frames = int(rate / chunk * duration)
        try:
            stream = audio.open(
                format=sample_format,
                channels=channels,
                rate=rate,
                frames_per_buffer=chunk,
                input=True,
                input_device_index=MIC_DEVICE_INDEX,
            )
            print(f"[STT] Dinleniyor... ({duration} saniye)")
            for _ in range(num_frames):
                data = stream.read(chunk, exception_on_overflow=False)
                frames.append(data)
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"[STT] Ses kaydedilemedi: {e}")
            audio.terminate()
            return None

    audio.terminate()

    if not frames:
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))

    return tmp.name


def speech_to_text(audio_file):
    if audio_file is None:
        return None
    try:
        with open(audio_file, "rb") as f:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="tr",
            )
        return transcript.text.strip()
    except Exception as e:
        print(f"[STT] Whisper API hatası: {e}")
        return None
    finally:
        try:
            os.remove(audio_file)
        except OSError:
            pass


# ==========================================================
# --- BÖLÜM 6: AI BEYİN (BRAIN) ---
# ============================================================

def get_response(user_text):
    global conversation_history

    conversation_history.append({"role": "user", "content": user_text})

    if len(conversation_history) > MAX_HISTORY:
        conversation_history = conversation_history[-MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=_TOOLS,
            max_tokens=250,
            temperature=1.0,
        )
        choice = response.choices[0]

        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            # Tool call yapıldı — çalıştır ve sonucu geri gönder
            messages.append(choice.message)
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception as json_err:
                    print(f"[BRAIN] Tool argümanları parse edilemedi: {json_err}")
                    args = {}
                print(f"[BRAIN] Tool call: {tc.function.name}({args})")
                result = _execute_tool(tc.function.name, args)
                print(f"[BRAIN] Tool result: {result}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

            # Doğal dil yanıt al
            response2 = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=150,
                temperature=1.0,
            )
            reply = response2.choices[0].message.content.strip()
        else:
            reply = choice.message.content.strip()

        conversation_history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"[BRAIN] OpenAI API hatası: {e}")
        return None


# ============================================================
# --- BÖLÜM 7: METİNDEN KONUŞMAYA (TTS) ---
# ============================================================

def speak(text):
    if not text:
        return
    print(f"[ARİS] {text}")
    try:
        response = _openai_client.audio.speech.create(
            model="tts-1",
            voice="shimmer",
            input=text,
        )
        audio_data = io.BytesIO(response.content)
        pygame.mixer.music.load(audio_data)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
    except Exception as e:
        print(f"[TTS] OpenAI TTS hatası: {e}")


# ============================================================
# --- BÖLÜM 8: WAKE WORD ---
# ============================================================

def wait_for_wake_word():
    """
    pvporcupine ile 'Hey Aris' wake word dinler.
    Keyword dosyası yoksa GUI'deki butonu bekler (input() yok!).
    """
    if not os.path.exists(WAKE_WORD_KEYWORD_PATH):
        print("[WAKE WORD] Simülasyon modu — GUI'deki '🎤 Konuş' butonuna bas...")
        _wake_event.wait()   # buton basılana kadar bekle (GUI donmaz)
        _wake_event.clear()  # bir sonraki kullanım için sıfırla
        return True

    porcupine = None
    audio = pyaudio.PyAudio()
    stream = None

    try:
        porcupine = pvporcupine.create(
            access_key=PORCUPINE_ACCESS_KEY,
            keyword_paths=[WAKE_WORD_KEYWORD_PATH],
        )

        stream = audio.open(
            rate=porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=porcupine.frame_length,
            input_device_index=MIC_DEVICE_INDEX,
        )

        print("[WAKE WORD] Dinliyorum... ('Hey Aris' de)")
        show_face_idle()

        while True:
            pcm = stream.read(porcupine.frame_length, exception_on_overflow=False)
            pcm_unpacked = struct.unpack_from("h" * porcupine.frame_length, pcm)
            result = porcupine.process(pcm_unpacked)
            if result >= 0:
                print("[WAKE WORD] 'Hey Aris' duyuldu!")
                return True

    except Exception as e:
        print(f"[WAKE WORD] Porcupine hatası: {e}")
        return True
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        audio.terminate()
        if porcupine is not None:
            porcupine.delete()


# ============================================================
# --- BÖLÜM 9: ANA DÖNGÜ (MAIN) ---
# ============================================================

def aris_loop():
    """Ana döngü — wake word, STT, AI, TTS. Ayrı thread'de çalışır."""
    # GUI'nin başlaması için kısa bekle
    time.sleep(1.5)

    show_face_happy()
    set_gui_state("happy")
    speak("Merhaba! Aris burada. Konuşmak için butona bas.")

    while True:
        try:
            show_face_idle()
            set_gui_state("idle")

            detected = wait_for_wake_word()
            if not detected:
                continue

            show_face_listening()
            set_gui_state("listening")

            audio_file = record_audio(duration=RECORD_DURATION)

            show_face_thinking()
            set_gui_state("thinking")

            user_text = speech_to_text(audio_file)

            if not user_text:
                speak("Seni anlayamadım, tekrar söyler misin?")
                continue

            print(f"[KULLANICI] {user_text}")

            response = get_response(user_text)

            if not response:
                speak("Bir şeyler ters gitti, birazdan tekrar dene.")
                continue

            show_face_talking()
            set_gui_state("talking")
            speak(response)

            time.sleep(0.5)
            show_face_happy()
            set_gui_state("happy")
            time.sleep(1)

        except KeyboardInterrupt:
            print("\n[ARİS] Görüşürüz! 👋")
            show_face_idle()
            set_gui_state("idle")
            break
        except Exception as e:
            print(f"[HATA] Beklenmedik bir hata oluştu: {e}")
            time.sleep(2)


if __name__ == "__main__":
    print("=" * 50)
    print("  ARİS başlatılıyor... 🤖")
    print("=" * 50)

    loop_thread = threading.Thread(target=aris_loop, daemon=True)
    loop_thread.start()

    # GUI'yi ana thread'de başlat (macOS tkinter zorunluluğu)
    start_gui()
    print("[ARİS] GUI kapandı, çıkılıyor.")