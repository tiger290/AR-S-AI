# 🤖 ARİS — Sesli AI Asistan

Aris, Türkçe konuşan, "Hey Aris" dediğinde uyanan, seninle samimi arkadaş gibi konuşan kişisel bir yapay zeka asistanıdır. Raspberry Pi veya herhangi bir bilgisayarda çalışır.

---

## ✨ Özellikler

- 🖥️ **Tkinter GUI** — Animasyonlu göz ifadeleri, blink, bakış hareketi
- 📺 **OLED Yüz** — SSD1306 128x64 ekranda canlı yüz ifadeleri (idle, listening, thinking, talking, happy)
- 🎵 **Spotify Entegrasyonu** — Şarkı aç/durdur/sonraki, sanatçı ve şarkı araması
- 🌤️ **Hava Durumu** — OpenWeatherMap ile gerçek zamanlı hava durumu bilgisi
- 🎙️ **STT (Konuşmadan Metne)** — OpenAI Whisper API ile yüksek doğruluklu ses tanıma
- 🔊 **TTS (Metinden Konuşmaya)** — OpenAI TTS (`tts-1-hd`, `onyx` sesi) ile doğal konuşma
- 💬 **AI Sohbet** — GPT-4o-mini ile 10 mesajlık konuşma geçmişi, Türkçe kişilik
- 🔔 **Wake Word** — Porcupine ile "Hey Aris" uyandırma kelimesi
- 🔁 **Thread-safe Döngü** — GUI ana thread'de, aris döngüsü ayrı thread'de

---

## 🛠️ Gereksinimler

- **Python 3.10+**
- **Mikrofon** (USB veya 3.5mm)
- **Hoparlör** (3.5mm veya USB)
- **Opsiyonel:** SSD1306 128x64 OLED ekran (I2C bağlantılı)
- **Opsiyonel:** Raspberry Pi 4/5 (masaüstü/laptop da çalışır)

---

## 🚀 Kurulum

### 1. Sanal Ortam Oluştur

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. Bağımlılıkları Kur

```bash
pip install -r requirements.txt
```

### 3. `.env` Dosyası Oluştur

`.env.example` dosyasını kopyalayarak kendi `.env` dosyasını oluştur:

```bash
cp .env.example .env
```

Sonra `.env` dosyasını düzenleyip gerçek API key'lerini yaz:

```
OPENAI_API_KEY=sk-...
PORCUPINE_ACCESS_KEY=...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
OPENWEATHER_API_KEY=...
```

> ⚠️ `.env` dosyası `.gitignore` tarafından engellenir, asla GitHub'a push'lanmaz. Sadece `.env.example` repoda bulunur.

### 4. Porcupine Wake Word Dosyasını Ekle

[Picovoice Console](https://console.picovoice.ai/) adresinden ücretsiz hesap aç, "Hey Aris" için custom keyword oluştur ve `hey-aris.ppn` dosyasını proje dizinine koy.

### 5. Çalıştır

```bash
python aris.py
```

---

## 🔑 API Key'leri Nasıl Alınır?

| Servis | Nereden Alınır | Ücret |
|---|---|---|
| **OpenAI** (Whisper + GPT + TTS) | [platform.openai.com](https://platform.openai.com/api-keys) | Kullandıkça öde |
| **Porcupine** (Wake Word) | [console.picovoice.ai](https://console.picovoice.ai/) | Ücretsiz tier mevcut |
| **Spotify** (Müzik) | [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) | Ücretsiz |
| **OpenWeatherMap** (Hava Durumu) | [openweathermap.org/api](https://openweathermap.org/api) | Ücretsiz tier mevcut |

---

## 🎤 Kullanım

Aris başlatıldıktan sonra iki şekilde konuşmayı başlatabilirsin:

1. **Wake Word:** "Hey Aris" de — Porcupine algılayınca dinlemeye geçer
2. **GUI Butonu:** Ekrandaki "Konuş" butonuna tıkla

Aris dinliyor durumuna geçince sesli komutunu ver. Birkaç saniye içinde yanıt alırsın.

**Örnek komutlar:**
- *"Hava durumu nedir?"*
- *"Weeknd'in şarkısını çal"*
- *"Sonraki şarkıya geç"*
- *"Bu gece ne yapmalıyım?"*

---

## 📁 Proje Yapısı

```
AR-S-AI/
├── aris.py           # Ana uygulama dosyası
├── requirements.txt  # Python bağımlılıkları
├── .env.example      # API key şablonu (gerçek key'ler buraya yazılmaz)
├── .gitignore        # .env ve diğer hassas dosyaları dışlar
├── hey-aris.ppn      # Porcupine wake word modeli (kendin oluşturman lazım)
└── README.md         # Bu dosya
```

### `aris.py` İçindeki Bölümler

| Bölüm | İçerik |
|---|---|
| **BÖLÜM 1: CONFIG** | API key'ler, cihaz ayarları, sabitler |
| **BÖLÜM 2: OLED YÜZ** | luma.oled ile SSD1306 yüz ifadeleri |
| **BÖLÜM 3: GUI** | Tkinter animasyonlu göz arayüzü |
| **BÖLÜM 4: SPOTIFY** | Spotipy ile müzik kontrol fonksiyonları |
| **BÖLÜM 5: HAVA DURUMU** | OpenWeatherMap API entegrasyonu |
| **BÖLÜM 6: STT** | PyAudio kayıt + Whisper API transkripsiyon |
| **BÖLÜM 7: TTS** | OpenAI TTS + pygame ses çalma |
| **BÖLÜM 8: AI BEYİN** | GPT-4o-mini sohbet motoru |
| **BÖLÜM 9: ANA DÖNGÜ** | Wake word + thread yönetimi |

---

## 📜 Lisans

MIT — İstediğini yap. Aris'i fork'la, geliştir, paylaş. 🤙
