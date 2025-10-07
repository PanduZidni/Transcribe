# 🎙️ M4A to Text Transcriber (Desktop GUI)

Aplikasi transkripsi audio **berbasis Whisper** untuk mengubah file **M4A/MP3/WAV/FLAC** menjadi teks.  
Dikembangkan dengan antarmuka **GUI (Tkinter)** agar mudah digunakan tanpa perintah terminal.

---

## 🚀 Fitur Utama

✅ Transkripsi audio ke teks secara **lokal** (tidak perlu koneksi internet).  
✅ Mendukung model Whisper: `tiny`, `base`, `small`, `medium`, `large`.  
✅ Opsi pemilihan file audio langsung dari jendela GUI.  
✅ Tampilan progres transkripsi dan area teks hasil otomatis.  
✅ Simpan hasil transkripsi ke file `.txt` dengan satu klik.  
✅ Aman untuk **audio sensitif** — semua proses dilakukan di perangkat lokal.  

---

## 🧩 Arsitektur

| Komponen | File | Deskripsi |
|----------|------|-----------|
| GUI (Desktop) | `m4a_to_text_gui.py` | Aplikasi utama berbasis Tkinter untuk transkripsi lokal. |

---

## ⚙️ Instalasi

Disarankan menggunakan **virtual environment** agar bersih:

```bash
python3 -m venv venv
source venv/bin/activate  # (Linux/macOS)
venv\Scripts\activate     # (Windows)
pip install --upgrade pip

Lalu instal dependensi utama:
pip install openai-whisper pydub

Jika ingin performa lebih cepat di GPU, bisa gunakan:
pip install faster-whisper

Pastikan juga Anda sudah menginstal ffmpeg dan berada di PATH:
https://ffmpeg.org/download.html

🖥️ Cara Menjalankan Aplikasi
python m4a_to_text_gui.py

Jika Tkinter tersedia di sistem Anda, aplikasi GUI akan terbuka secara otomatis.
Lalu:
1. Klik Browse untuk memilih file audio (.m4a, .mp3, .wav, .flac)
2. Pilih model Whisper yang ingin digunakan
3. Klik Transcribe untuk memulai proses
4. Setelah selesai, klik Save Transcript untuk menyimpan hasil

Untuk mempercepat proses:
1. Gunakan GPU + faster-whisper
2. Pilih model lebih kecil (small atau base)
3. Hindari large di CPU-only environment
4. Gunakan file audio berdurasi lebih pendek

🧰 Dependencies

1. Python 3.8+
2. ffmpeg
3. pydub
4. openai-whisper atau faster-whisper
5. tkinter (sudah termasuk di sebagian besar distribusi Python)

🔒 Privasi
Proyek ini dirancang untuk audio sensitif:
1. Tidak ada data yang dikirim ke server pihak ketiga.
2. Semua file dan hasil transkripsi diproses serta disimpan lokal di perangkat Anda.

📄 Lisensi
Proyek ini bersifat open-source di bawah lisensi MIT License.
Silakan digunakan dan dimodifikasi dengan tetap mencantumkan kredit.

👨‍💻 Pengembang
Pandu Zidni

⭐ Kontribusi
Kontribusi dan saran perbaikan sangat diterima!
Silakan fork repository ini, buat branch baru, dan kirim pull request.
