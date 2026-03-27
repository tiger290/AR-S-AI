import os
import time
import wave
import tempfile
import struct
import pyaudio
import pyttsx3
import openai
import pvporcupine
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
TTS_VOICE = "tr"       # Türkçe ses
OLED_WIDTH = 128
OLED_HEIGHT = 64
RECORD_DURATION = 5    # Saniye cinsinden kayıt süresi
MAX_HISTORY = 10       # Konuşma geçmişinde tutulacak maksimum mesaj sayısı

openai.api_key = OPENAI_API_KEY

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
# --- BÖLÜM 4: KONUŞMADAN METİNE (STT) ---
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
# --- BÖLÜM 5: AI BEYİN (BRAIN) ---
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
# --- BÖLÜM 6: METİNDEN KONUŞMAYA (TTS) ---
# ============================================================

# pyttsx3 motorunu başlat
_tts_engine = None
try:
    _tts_engine = pyttsx3.init()
    # Türkçe ses motoru için hız ve ses ayarı
    _tts_engine.setProperty("rate", 165)
    _tts_engine.setProperty("volume", 1.0)
    # Türkçe ses varsa ayarla (dil kodu veya isimde "turkish" geçiyorsa)
    voices = _tts_engine.getProperty("voices")
    for voice in voices:
        voice_id_lower = voice.id.lower()
        voice_name_lower = voice.name.lower()
        if (
            f"_{TTS_VOICE}_" in voice_id_lower
            or voice_id_lower.endswith(f"_{TTS_VOICE}")
            or "turkish" in voice_name_lower
        ):
            _tts_engine.setProperty("voice", voice.id)
            break
except Exception as e:
    print(f"[TTS] pyttsx3 başlatılamadı: {e}")


def speak(text):
    """
    Verilen metni pyttsx3 ile seslendirir.
    Motor başlatılamadıysa sadece ekrana yazar.
    """
    if not text:
        return
    print(f"[ARİS] {text}")
    if _tts_engine is None:
        return
    try:
        _tts_engine.say(text)
        _tts_engine.runAndWait()
    except Exception as e:
        print(f"[TTS] Seslendirilirken hata: {e}")


# ============================================================
# --- BÖLÜM 7: WAKE WORD ---
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
# --- BÖLÜM 8: ANA DÖNGÜ (MAIN) ---
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("  ARİS başlatılıyor... 🤖")
    print("=" * 50)

    # Başlangıç mesajı
    show_face_happy()
    speak("Merhaba! Aris burada. 'Hey Aris' diyerek beni uyandırabilirsin.")

    while True:
        try:
            # Bekleme yüzü göster
            show_face_idle()

            # Wake word bekle
            detected = wait_for_wake_word()
            if not detected:
                continue

            # Dinleme moduna geç
            show_face_listening()
            speak("Evet?")

            # Ses kaydet
            audio_file = record_audio(duration=RECORD_DURATION)

            # Düşünme yüzü
            show_face_thinking()

            # Konuşmadan metne çevir
            user_text = speech_to_text(audio_file)

            if not user_text:
                speak("Seni anlayamadım, tekrar söyler misin?")
                continue

            print(f"[KULLANICI] {user_text}")

            # AI yanıt al
            response = get_response(user_text)

            if not response:
                speak("Bir şeyler ters gitti, birazdan tekrar dene.")
                continue

            # Konuşma yüzü göster ve yanıtı söyle
            show_face_talking()
            speak(response)

            # Kısa bir duraklama, ardından mutlu yüz
            time.sleep(0.5)
            show_face_happy()
            time.sleep(1)

        except KeyboardInterrupt:
            print("\n[ARİS] Görüşürüz! 👋")
            show_face_idle()
            break
        except Exception as e:
            print(f"[HATA] Beklenmedik bir hata oluştu: {e}")
            time.sleep(2)
