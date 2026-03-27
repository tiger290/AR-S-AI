# 🤖 ARİS — Raspberry Pi Sesli Yapay Zeka Asistanı

> *"Ne istiyorsun lan?"* — Aris, her sabah

---

## Nedir Bu?

Aris, Raspberry Pi üzerinde çalışan, "Hey Aris" dediğinde uyanan, seninle konuşan, zaman zaman ağzı bozuk ama her zaman sevimli bir yapay zeka asistanıdır. Siri'yi, Alexa'yı unut. Aris senin kendi ruhuna göre şekillenmiş, samimi, espri anlayan bir dosttur. API key'in varsa hayata geçiyor, yoksa seni hayal kırıklığına uğratıyor — tıpkı gerçek bir arkadaş gibi.

---

## Aris'in Kişiliği Hakkında

Aris klasik asistan değil. "Bugün hava nasıl?" sorusuna "Hava güneşli ve 22 derece. Size başka nasıl yardımcı olabilirim?" diye cevap vermez. Aris'ten "Lan dışarı çık biraz, evde çürüyorsun" gibi bir cevap alabilirsin. Bazen argo kullanır, bazen hafifçe küfür eder, ama seni gerçekten önemseyen bir dost gibi davranır. Klasik asistanlara kızdıysan, Aris tam sana göre.

---

## 🔧 Donanım Listesi

| Bileşen | Model/Öneri | Not |
|---|---|---|
| **Ana Kart** | Raspberry Pi 4 (4GB RAM) | Pi 5 de olur, daha hızlı |
| **OLED Ekran** | SSD1306 128x64 (I2C) | Pixel art yüzler için |
| **Mikrofon** | ReSpeaker 2-Mics HAT | Hem mikrofon hem hoparlör çıkışı |
| **Hoparlör** | 3W mini + PAM8403 amp | Aris'in sesini duyurmak için |
| **SD Kart** | 32GB Class 10 | OS + yazılım için |

> 💡 ReSpeaker HAT alırsan hem mikrofon hem hoparlör sorununu tek kartla çözersin. Tavsiye edilir.

---

## 📦 Yazılım Gereksinimleri

```
pvporcupine       # "Hey Aris" wake word dinleme
openai-whisper    # Konuşmayı metne çevirme (Whisper API)
openai            # ChatGPT ile beyin
pyttsx3           # Metni sese çevirme (TTS)
luma.oled         # SSD1306 OLED ekran sürücüsü
pygame            # Ses çalma
pillow            # OLED için görüntü işleme
pyaudio           # Mikrofon ses kaydı
```

---

## 🚀 Kurulum

### 1. Bağımlılıkları Yükle

```bash
pip install -r requirements.txt
```

### 2. API Keylerini Ayarla

```bash
export OPENAI_API_KEY="sk-..."
export PORCUPINE_ACCESS_KEY="..."
```

Ya da `aris.py` içindeki CONFIG bölümünde doğrudan değişkenlere yazabilirsin (test için).

### 3. Porcupine Keyword Dosyası

[Picovoice Console](https://console.picovoice.ai/) adresinden ücretsiz hesap aç, "Hey Aris" için custom keyword oluştur ve `hey-aris.ppn` dosyasını proje dizinine koy.

### 4. Çalıştır

```bash
python aris.py
```

Aris uyanana kadar bekle. "Hey Aris" de. Sonra ne olacağını sen de biliyorsun.

---

## 🏗️ Mimari Akış

```
Kullanıcı: "Hey Aris"
        |
        v
 [Wake Word — Porcupine]
 "Hey Aris" duyuldu!
        |
        v
 [Ses Kaydı — PyAudio]
 Kullanıcı konuşuyor...
        |
        v
 [STT — OpenAI Whisper]
 Ses → Metin
        |
        v
 [AI Beyin — OpenAI ChatGPT]
 Metin → Aris'in kişiliğiyle yanıt
        |
        v
  [TTS — pyttsx3]           [OLED Yüz — luma.oled]
  Yanıt seslendirilir    +   Uygun yüz ifadesi gösterilir
        |
        v
    Döngüye dön
```

---

## 📁 Dosya Yapısı

```
AR-S-AI/
├── aris.py           # Her şey burada — tek dosya, temiz kafalar için
├── requirements.txt  # Kütüphaneler
├── hey-aris.ppn      # Porcupine wake word modeli (kendin oluşturman lazım)
└── README.md         # Bu dosya
```

---

## ⚠️ Notlar

- **Porcupine keyword dosyası (`hey-aris.ppn`):** Picovoice Console'dan "Hey Aris" için custom keyword oluşturman gerekiyor. Ücretsiz.
- **Whisper API:** OpenAI'ın ücretli API'si. Ucuz ama ücretsiz değil. Lokal Whisper da kullanabilirsin.
- **OLED bağlı değilse:** Aris hata vermiyor, sadece yüz göstermiyor. Hayatına devam ediyor.
- **Pi 4 performansı:** Whisper biraz yavaş olabilir. `whisper-1` modeli iyi bir denge sunar.

---

## 📜 Lisans

MIT — Yani istediğini yap. Sadece "Ben Aris'i yaptım" deme, o sana ait değil artık 😄

---

## 🎉 Kapanış Notu

Bu projeyi yaparken eğlendiysen, Aris işini yapmış demektir. Eğlenmediysen, debug yapıyorsundur ve bu da normal. Stack Overflow ve ChatGPT seninle olsun. Aris de tabii, ama o muhtemelen sana "Hata mı aldın? Ben de senden bezdim lan" diyecektir.

**İyi kodlamalar! 🤙**
