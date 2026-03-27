import io
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

# API anahtarları ve ayarlar
# Ortam değişkenlerinden oku; ayarlanmamışsa varsayılan placeholder kullan
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "senin-api-keyin")
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "senin-porcupine-keyin")
WAKE_WORD_KEYWORD_PATH = "hey-aris.ppn"  # Porcupine keyword dosyası
MIC_DEVICE_INDEX = 0
OLED_WIDTH = 128
OLED_HEIGHT = 64
RECORD_DURATION = 5    # Saniye cinsinden kayıt süresi
MAX_HISTORY = 10       # Konuşma geçmişinde tutulacak maksimum mesaj sayısı

# Spotify
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "senin-client-id")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "senin-client-secret")
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8888/callback"

# Hava Durumu
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "senin-weather-api-keyin")
DEFAULT_CITY = "Istanbul"

openai.api_key = OPENAI_API_KEY

# OpenAI istemcisi (TTS ve diğer API çağrıları için)
_openai_client = openai.OpenAI()

# pygame ses mikseri başlat
try:
    pygame.mixer.init()
except Exception as e:
    print(f"[TTS] pygame.mixer başlatılamadı: {e}")

# Spotify istemcisi (spotipy opsiyonel bağımlılık)
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

SYSTEM_PROMPT = """
Sen Aris'sin. Samimi, bazen argo bazen hafif küfürlü ama her zaman eğlenceli bir yapay zeka asistanısın.
Klasik asistan numarası yapmıyorsun, gerçek bir arkadaş gibi davranıyorsun.
Kısa konuş, lafı geveleme. Türkçe konuş.
Gerektiğinde sert ol, gerektiğinde şakacı ol. Ama her zaman samimi ol.
Kullanıcıyı dinliyorsun, umursuyorsun — sadece bunu abartmıyorsun.
"""

# Konuşma geçmişi (son MAX_HISTORY mesaj tutulur)
conversation_history = []

# ============================================================
# --- BÖLÜM 3: OLED YÜZ İFADELERİ (FACE) ---
# ============================================================

# OLED cihazını başlatmaya çalış, bağlı değilse None olarak bırak
oled_device = None
try:
    serial = i2c(port=1, address=0x3C)
    oled_device = ssd1306(serial, width=OLED_WIDTH, height=OLED_HEIGHT)
except Exception as e:
    print(f"[OLED] OLED başlatılamadı, yüz ifadeleri devre dışı: {e}")


def _render_face(draw_func):
    """Verilen çizim fonksiyonunu OLED'e uygular. OLED yoksa sessizce geçer."""
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
    """Bekleme yüzü — nötr ifade."""
    def draw(d):
        # Sol göz
        d.ellipse([30, 20, 50, 38], outline=255)
        d.ellipse([37, 27, 43, 33], fill=255)
        # Sağ göz
        d.ellipse([78, 20, 98, 38], outline=255)
        d.ellipse([85, 27, 91, 33], fill=255)
        # Düz ağız
        d.line([48, 52, 80, 52], fill=255, width=2)
    _render_face(draw)


def show_face_listening():
    """Dinliyor — gözler büyük, dikkatli ifade."""
    def draw(d):
        # Sol göz (büyük)
        d.ellipse([24, 16, 52, 42], outline=255)
        d.ellipse([35, 26, 44, 34], fill=255)
        # Sağ göz (büyük)
        d.ellipse([76, 16, 104, 42], outline=255)
        d.ellipse([87, 26, 96, 34], fill=255)
        # Hafif açık ağız
        d.arc([48, 46, 80, 60], start=0, end=180, fill=255, width=2)
    _render_face(draw)


def show_face_thinking():
    """Düşünüyor — soru işareti gözler, çatılmış kaşlar."""
    def draw(d):
        # Sol kaş (çatılmış)
        d.line([24, 18, 50, 24], fill=255, width=2)
        # Sağ kaş (çatılmış)
        d.line([78, 24, 104, 18], fill=255, width=2)
        # Sol göz (? gibi)
        d.ellipse([28, 22, 50, 42], outline=255)
        d.text((34, 26), "?", fill=255)
        # Sağ göz (? gibi)
        d.ellipse([78, 22, 100, 42], outline=255)
        d.text((84, 26), "?", fill=255)
        # Düz ağız
        d.line([48, 54, 80, 54], fill=255, width=2)
    _render_face(draw)


def show_face_talking():
    """Konuşuyor — gülümseyen, hareketli ağız."""
    def draw(d):
        # Sol göz
        d.ellipse([28, 18, 50, 38], outline=255)
        d.ellipse([35, 25, 43, 33], fill=255)
        # Sağ göz
        d.ellipse([78, 18, 100, 38], outline=255)
        d.ellipse([85, 25, 93, 33], fill=255)
        # Açık gülümseyen ağız
        d.arc([40, 44, 88, 62], start=0, end=180, fill=255, width=3)
        d.line([40, 53, 88, 53], fill=255, width=1)
    _render_face(draw)


def show_face_happy():
    """Mutlu — kapanan gözler, büyük gülümseme."""
    def draw(d):
        # Sol göz (kapanmış — yay)
        d.arc([28, 24, 50, 40], start=180, end=0, fill=255, width=3)
        # Sağ göz (kapanmış — yay)
        d.arc([78, 24, 100, 40], start=180, end=0, fill=255, width=3)
        # Büyük gülümseme
        d.arc([32, 42, 96, 62], start=0, end=180, fill=255, width=3)
    _render_face(draw)


# ============================================================
# --- BÖLÜM 4: SIYAH GUI (tkinter) ---
# ============================================================

# GUI durum kuyruğu (thread-safe iletişim)
_gui_queue = queue.Queue()
_gui_root = None

# Göz animasyon parametreleri
_EYE_BASE_LEFT = (160, 160)   # Sol göz merkezi (x, y)
_EYE_BASE_RIGHT = (320, 160)  # Sağ göz merkezi (x, y)
_EYE_W = 60                   # Göz genişliği (yarıçap yatay)
_EYE_H = 50                   # Göz yüksekliği (yarıçap dikey)
_PUPIL_R = 14                 # Göz bebeği yarıçapı


class ArisGUI:
    """Aris için siyah arka planlı tkinter arayüzü."""

    def __init__(self, root):
        self.root = root
        self.root.title("ARİS")
        self.root.configure(bg="black")
        self.root.resizable(False, False)

        # Başlık
        self.label_title = tk.Label(
            root, text="ARİS", font=("Helvetica", 48, "bold"),
            fg="white", bg="black"
        )
        self.label_title.pack(pady=(20, 0))

        # Göz canvas
        self.canvas = tk.Canvas(root, width=480, height=260, bg="black", highlightthickness=0)
        self.canvas.pack(pady=10)

        # Durum yazısı
        self.label_status = tk.Label(
            root, text="Bekliyorum...", font=("Helvetica", 18),
            fg="white", bg="black"
        )
        self.label_status.pack(pady=(0, 20))

        # Animasyon durumu
        self.state = "idle"
        self._blink_open = True
        self._idle_offset = [0, 0]   # [sol_x, sag_x] kayma
        self._idle_target = [0, 0]
        self._idle_step = [0, 0]
        self._idle_count = 0

        # İlk çizim
        self._draw_eyes()

        # Kuyruğu işle
        self._process_queue()

        # Animasyon döngüsünü başlat
        self._animate()

    # ---------- durum güncelleme ----------

    def _process_queue(self):
        """GUI kuyruğundaki durum değişikliklerini uygula."""
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

    # ---------- animasyon ----------

    def _animate(self):
        """Durum bazlı animasyon tick'i (her 80 ms)."""
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
        """Gözleri yavaşça rastgele sağa/sola kaydır."""
        self._idle_count -= 1
        for i in range(2):
            if self._idle_count <= 0 or self._idle_step[i] == 0:
                # Yeni hedef seç
                self._idle_target[i] = random.randint(-18, 18)
                steps = random.randint(15, 30)
                self._idle_step[i] = (self._idle_target[i] - self._idle_offset[i]) / max(steps, 1)
                self._idle_count = steps
            self._idle_offset[i] += self._idle_step[i]
            if abs(self._idle_offset[i] - self._idle_target[i]) < abs(self._idle_step[i]):
                self._idle_offset[i] = self._idle_target[i]
                self._idle_step[i] = 0

    def _animate_talking(self):
        """Konuşurken gözler hafifçe açılıp kapanır (blink)."""
        self._blink_open = not self._blink_open

    # ---------- çizim ----------

    def _draw_eyes(self):
        """Mevcut duruma göre gözleri canvas'a çiz."""
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
            # Gözler yukarı bakar, kaşlar çatılır
            self._draw_eye(lx, ly, ew, eh, pupil_dy=-12)
            self._draw_eye(rx, ry, ew, eh, pupil_dy=-12)
            # Sol kaş (çatılmış)
            self.canvas.create_line(
                lx - ew, ly - eh - 14,
                lx + ew, ly - eh - 4,
                fill="white", width=4
            )
            # Sağ kaş (çatılmış)
            self.canvas.create_line(
                rx - ew, ry - eh - 4,
                rx + ew, ry - eh - 14,
                fill="white", width=4
            )

        elif state == "talking":
            # Blink animasyonu
            if self._blink_open:
                self._draw_eye(lx, ly, ew, eh, pupil_dy=0)
                self._draw_eye(rx, ry, ew, eh, pupil_dy=0)
            else:
                # Yarı kapalı — yatay çizgi
                self._draw_eye_closed(lx, ly, ew)
                self._draw_eye_closed(rx, ry, ew)

        elif state == "happy":
            # Gözler kapalı — mutlu yay
            self._draw_eye_happy(lx, ly, ew)
            self._draw_eye_happy(rx, ry, ew)

        else:  # idle (varsayılan)
            self._draw_eye(lx, ly, ew, eh, pupil_dy=0)
            self._draw_eye(rx, ry, ew, eh, pupil_dy=0)

    def _draw_eye(self, cx, cy, ew, eh, pupil_dy=0):
        """Normal oval göz çiz."""
        self.canvas.create_oval(
            cx - ew, cy - eh, cx + ew, cy + eh,
            outline="white", width=3
        )
        # Göz bebeği
        py = cy + pupil_dy
        self.canvas.create_oval(
            cx - _PUPIL_R, py - _PUPIL_R, cx + _PUPIL_R, py + _PUPIL_R,
            fill="white", outline=""
        )

    def _draw_eye_closed(self, cx, cy, ew):
        """Yarı kapalı göz (yatay çizgi)."""
        self.canvas.create_line(
            cx - ew, cy, cx + ew, cy,
            fill="white", width=4
        )

    def _draw_eye_happy(self, cx, cy, ew):
        """Mutlu göz — aşağıya bakan yay."""
        self.canvas.create_arc(
            cx - ew, cy - _EYE_H // 2, cx + ew, cy + _EYE_H // 2,
            start=0, extent=180, style=tk.ARC, outline="white", width=4
        )


def _gui_thread_func():
    """GUI thread fonksiyonu — ayrı thread'de çalışır."""
    global _gui_root
    try:
        root = tk.Tk()
        _gui_root = root
        ArisGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"[GUI] GUI başlatılamadı: {e}")


def start_gui():
    """GUI'yi ayrı bir daemon thread'de başlat."""
    t = threading.Thread(target=_gui_thread_func, daemon=True)
    t.start()


def set_gui_state(state: str):
    """
    GUI durumunu değiştir. Thread-safe.
    state: "idle" | "listening" | "thinking" | "talking" | "happy"
    """
    try:
        _gui_queue.put_nowait(state)
    except Exception:
        pass


# ============================================================
# --- BÖLÜM 4b: SPOTIFY ---
# ============================================================

def handle_spotify_command(text: str) -> bool:
    """
    Spotify komutlarını işler.
    Komut tanındıysa True döner (ana döngü get_response'a geçmez).
    Komut tanınmadıysa False döner.
    """
    if _spotify is None:
        return False

    t = text.lower()

    try:
        # Durdur
        if any(k in t for k in ("müziği durdur", "şarkıyı durdur", "müzik durdur", "durdur")):
            _spotify.pause_playback()
            speak("Müzik durduruldu.")
            return True

        # Sonraki şarkı
        if "sonraki şarkı" in t or "next" in t:
            _spotify.next_track()
            speak("Sonraki şarkıya geçildi.")
            return True

        # Şarkı çal / ara
        play_keywords = ("şarkı aç", "müzik aç", "çal", "şarkısını aç", "müzik çal")
        if any(k in t for k in play_keywords):
            # Şarkı adını bulmaya çalış (lowercase 't' üzerinden hem bul hem çıkar)
            query = None
            for pattern in ("'ı çal", "'i çal", "'u çal", "'ü çal",
                            "şarkısını aç", "çal", "şarkı aç", "müzik aç"):
                idx = t.find(pattern)
                if idx > 0:
                    query = t[:idx].strip()
                    break

            if query and len(query) > 2:
                results = _spotify.search(q=query, type="track", limit=1)
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    uri = tracks[0]["uri"]
                    _spotify.start_playback(uris=[uri])
                    name = tracks[0]["name"]
                    artist = tracks[0]["artists"][0]["name"]
                    speak(f"{artist} - {name} çalınıyor.")
                else:
                    speak(f"'{query}' için şarkı bulunamadı.")
            else:
                # Rastgele / kaldığı yerden devam
                _spotify.start_playback()
                speak("Müzik açıldı.")
            return True

    except Exception as e:
        print(f"[SPOTIFY] Hata: {e}")
        speak("Spotify komutu çalıştırılamadı.")
        return True

    return False


# ============================================================
# --- BÖLÜM 4c: HAVA DURUMU ---
# ============================================================

def get_weather(city: str = DEFAULT_CITY) -> str:
    """
    OpenWeatherMap API ile verilen şehrin hava durumunu sorgular.
    Türkçe açıklama içeren bir string döner.
    """
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
    """
    Kullanıcı cümlesinden şehir adını çıkarmaya çalışır.
    Bulamazsa DEFAULT_CITY döner.
    """
    t = text.lower()
    # "X'da/de/ta/te hava" veya "X hava" gibi kalıplar
    for suffix in ("'da", "'de", "'ta", "'te", " da ", " de ", " ta ", " te "):
        idx = t.find(suffix)
        if idx > 0:
            # Suffix öncesindeki tüm kelimeleri al (çok kelimeli şehir adları için)
            before = text[:idx].strip()
            # Son 1-3 kelimeyi şehir adı olarak değerlendir
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
    """
    PyAudio ile mikrofon kaydı yapar ve geçici bir WAV dosyası oluşturur.
    Dosya yolunu döner.
    """
    audio = pyaudio.PyAudio()
    chunk = 1024
    sample_format = pyaudio.paInt16
    channels = 1
    rate = 16000
    num_frames = int(rate / chunk * duration)
    sample_width = audio.get_sample_size(sample_format)

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
        frames = []
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

    # Geçici WAV dosyası oluştur
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))

    return tmp.name


def speech_to_text(audio_file):
    """
    OpenAI Whisper API kullanarak ses dosyasını metne çevirir.
    Metin string döner, hata varsa None döner.
    """
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
        # Geçici dosyayı temizle
        try:
            os.remove(audio_file)
        except OSError:
            pass


# ============================================================
# --- BÖLÜM 6: AI BEYİN (BRAIN) ---
# ============================================================

def get_response(user_text):
    """
    OpenAI ChatCompletion API ile Aris'in kişiliğini kullanarak yanıt üretir.
    Konuşma geçmişini korur (son MAX_HISTORY mesaj).
    Yanıt metnini döner, hata varsa None döner.
    """
    global conversation_history

    # Kullanıcı mesajını geçmişe ekle
    conversation_history.append({"role": "user", "content": user_text})

    # Geçmiş çok uzarsa budama yap
    if len(conversation_history) > MAX_HISTORY:
        conversation_history = conversation_history[-MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=200,
            temperature=0.85,
        )
        reply = response.choices[0].message.content.strip()
        # Asistan yanıtını geçmişe ekle
        conversation_history.append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        print(f"[BRAIN] OpenAI API hatası: {e}")
        return None


# ============================================================
# --- BÖLÜM 7: METİNDEN KONUŞMAYA (TTS) ---
# ============================================================

def speak(text):
    """
    Verilen metni OpenAI TTS API (tts-1-hd, onyx) ile seslendirir.
    Jarvis tarzı derin erkek sesi kullanır.
    """
    if not text:
        return
    print(f"[ARİS] {text}")
    try:
        response = _openai_client.audio.speech.create(
            model="tts-1-hd",
            voice="onyx",
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
    Wake word duyulduğunda True döner.
    Keyword dosyası yoksa veya hata oluşursa bilgi verir, True döner (simüle eder).
    """
    # Keyword dosyası var mı kontrol et
    if not os.path.exists(WAKE_WORD_KEYWORD_PATH):
        print(
            "[WAKE WORD] Uyarı: 'hey-aris.ppn' dosyası bulunamadı. "
            "Picovoice Console'dan (https://console.picovoice.ai/) "
            "özel keyword oluşturup bu dizine koymalısın."
        )
        print("[WAKE WORD] Simülasyon modunda devam ediliyor. Başlamak için Enter'a bas...")
        input()
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

if __name__ == "__main__":
    print("=" * 50)
    print("  ARİS başlatılıyor... 🤖")
    print("=" * 50)

    # GUI'yi başlat (ayrı thread)
    start_gui()

    # Başlangıç mesajı
    show_face_happy()
    set_gui_state("happy")
    speak("Merhaba! Aris burada. 'Hey Aris' diyerek beni uyandırabilirsin.")

    while True:
        try:
            # Bekleme moduna geç
            show_face_idle()
            set_gui_state("idle")

            # Wake word bekle
            detected = wait_for_wake_word()
            if not detected:
                continue

            # Dinleme moduna geç
            show_face_listening()
            set_gui_state("listening")
            speak("Evet?")

            # Ses kaydet
            audio_file = record_audio(duration=RECORD_DURATION)

            # Düşünme moduna geç
            show_face_thinking()
            set_gui_state("thinking")

            # Konuşmadan metne çevir
            user_text = speech_to_text(audio_file)

            if not user_text:
                speak("Seni anlayamadım, tekrar söyler misin?")
                continue

            print(f"[KULLANICI] {user_text}")

            # 1) Spotify komutu kontrolü
            if handle_spotify_command(user_text):
                show_face_happy()
                set_gui_state("happy")
                time.sleep(1)
                continue

            # 2) Hava durumu kontrolü
            weather_keywords = ("hava durumu", "hava nasıl", "bugün hava", "yarın hava", "haftaya hava")
            if any(k in user_text.lower() for k in weather_keywords):
                city = _extract_city(user_text)
                weather_text = get_weather(city)
                show_face_talking()
                set_gui_state("talking")
                speak(weather_text)
                show_face_happy()
                set_gui_state("happy")
                time.sleep(1)
                continue

            # 3) Normal AI yanıt
            response = get_response(user_text)

            if not response:
                speak("Bir şeyler ters gitti, birazdan tekrar dene.")
                continue

            # Konuşma moduna geç ve yanıtı söyle
            show_face_talking()
            set_gui_state("talking")
            speak(response)

            # Kısa bir duraklama, ardından mutlu yüz
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
