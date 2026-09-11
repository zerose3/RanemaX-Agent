# RANEMAX Device Agent

Script ini yang menghubungkan Android Cloud Phone kamu ke dashboard RANEMAX.
Berbeda dari folder `ranemax` (itu website-nya), folder ini **dijalankan di
dalam cloud phone**, bukan di komputer kamu.

Cara kerjanya: agent ini login ke Supabase pakai akun RANEMAX kamu, lalu
setiap beberapa detik melaporkan status CPU/RAM/storage device ke database,
mengecek file yang perlu di-deploy, dan mengecek task yang perlu dijalankan.

> **Syarat**: RANEMAX kamu harus sudah terhubung ke Supabase (bukan mode
> demo lagi). Lihat README di folder `ranemax` untuk itu dulu.

---

## Langkah-langkah

### 1. Buka Terminal di Cloud Phone

Cloud phone biasanya punya menu **Terminal** atau **Termux** bawaan. Kalau
belum ada, install aplikasi **Termux** dari F-Droid (bukan Play Store, versi
Play Store sudah tidak di-update).

### 2. Install Python

Di Termux, jalankan:

```bash
pkg update -y
pkg install python -y
```

### 3. Pindahkan folder `ranemax-agent` ini ke cloud phone

Beberapa cara:
- Upload lewat fitur file transfer cloud phone kamu (kalau ada)
- Atau `git clone` kalau kamu upload folder ini ke GitHub sendiri
- Atau ketik ulang manual dengan `nano ranemax_agent.py` (kurang praktis
  untuk file sepanjang ini — cara upload lebih disarankan)

### 4. Install dependency Python

Masuk ke folder `ranemax-agent`, lalu:

```bash
pip install -r requirements.txt
```

### 5. Buat file konfigurasi

```bash
cp config.example.json config.json
nano config.json
```

Isi setiap field:

| Field | Isi dengan |
|---|---|
| `supabase_url` | Project URL dari Supabase (sama seperti di `.env.local` website) |
| `supabase_anon_key` | anon public key dari Supabase (sama seperti di `.env.local`) |
| `email` | Email akun yang kamu pakai login di RANEMAX |
| `password` | Password akun yang sama |
| `device_name` | Nama bebas untuk device ini, misal "Pixel 7 Cloud" |
| `device_identifier` | ID unik bebas, misal "pixel7-cloud-01" (jangan sama antar device) |
| `heartbeat_seconds` | Seberapa sering lapor status (default 15 detik) |
| `enable_command_tasks` | Biarkan `false` kecuali kamu paham risikonya (lihat catatan keamanan di bawah) |

Simpan file (di nano: `Ctrl+O`, Enter, lalu `Ctrl+X`).

### 6. Kunci config.json (WAJIB sebelum lanjut)

Secara default, `config.json` menyimpan password akunmu sebagai teks
polos. Kalau cloud phone ini sampai diakses orang lain atau kena
malware, password itu bisa dibaca langsung. Kunci dulu:

```bash
python encrypt_config.py
```

Kamu akan diminta membuat **passphrase** (beda dari password Supabase).
Passphrase ini tidak disimpan di mana pun oleh agent — kamu yang harus
ingat dan ketik ulang setiap kali agent dijalankan. Setelah ini,
`config.json` otomatis dihapus dan diganti `config.enc` (terenkripsi).

> Kalau kamu skip langkah ini, agent tetap bisa jalan (akan muncul
> peringatan tiap start), tapi TIDAK disarankan untuk device yang
> jalan lama/tanpa pengawasan.

### 7. Jalankan agent

```bash
python ranemax_agent.py
```

Kamu akan diminta mengetik passphrase config.enc tadi, lalu:

```
[ranemax-agent] Signing in...
[ranemax-agent] Signed in as your@email.com
[ranemax-agent] Registered new device: pixel7-cloud-01
[ranemax-agent] Device ready. Heartbeat every 15s.
```

Sekarang buka dashboard RANEMAX di browser — device ini akan **otomatis
muncul** di halaman Devices, berstatus Online, dengan CPU/RAM real dari
cloud phone kamu.

Biarkan Terminal ini tetap terbuka/berjalan selama kamu mau device-nya
tetap online. Tutup Terminal (atau `Ctrl+C`) untuk berhenti.

### 8. (Opsional) Supaya tetap jalan di background

Termux akan mati kalau layar HP dikunci lama. Untuk cloud phone yang
memang didesain jalan terus, biasanya ada fitur "keep awake" bawaan
platform cloud phone-nya, atau kamu bisa jalankan lewat `tmux`:

```bash
pkg install tmux -y
tmux new -s ranemax
python ranemax_agent.py
# tekan Ctrl+B lalu D untuk keluar dari tmux tanpa menghentikan script
```

---

## Cara Cepat: Install 1 Perintah (Opsional)

Kalau kamu mau pasang di banyak cloud phone dan malas mengetik langkah
1-8 di atas satu-satu, kamu bisa pakai `install.sh` yang otomatis
melakukan langkah 1-4.

**Ini WAJIB kamu setup sendiri dulu (sekali saja), tidak bisa langsung
dipakai dari sini:**

1. Buka `install.sh`, ganti `RAW_BASE_URL` dengan link repo GitHub kamu
   sendiri (upload folder `ranemax-agent` ini ke GitHub kamu, bisa
   private/public sesuai keinginan — tapi kalau public, pastikan
   `config.json`/`config.enc` tidak ikut ter-upload, sudah ada di
   `.gitignore`).
2. Upload `install.sh` yang sudah diedit itu juga ke repo yang sama.
3. Sekarang di cloud phone manapun, kamu tinggal jalankan:

```bash
curl -fsSL https://raw.githubusercontent.com/USERNAME/REPO/main/install.sh | bash
```

**Kenapa ini beda dari script berbahaya yang saya tolak sebelumnya:**
script ini hanya download file dari repo yang **kamu sendiri yang
upload dan kontrol** — bukan server pihak ketiga yang tidak kamu kenal.
Kamu bisa buka dan baca `install.sh` maupun semua file lain kapan saja
karena semuanya ada di repo kamu sendiri. Script ini juga cuma jalan
**sekali saat instalasi**, tidak diam-diam jalan terus mengambil kode
baru setiap kali agent hidup.

Setelah `install.sh` selesai, tetap lanjutkan manual ke langkah "Buat
file konfigurasi" (isi `config.json`), lalu enkripsi, lalu jalankan
agent seperti biasa.

## Fitur yang sudah jalan

- ✅ Auto-register device ke dashboard (tidak perlu isi form Add Device manual)
- ✅ Update CPU / RAM / Storage usage real setiap heartbeat
- ✅ Status Online otomatis
- ✅ Download file yang di-deploy dari File Deployment (tersimpan di
  folder `deployed_files/`)
- ✅ Menjalankan task bertipe "Sync"

## Yang belum didukung agent versi ini

- ❌ Task "Reboot" (Termux tidak punya izin reboot device)
- ❌ Grid Layout / kontrol layar jarak jauh (butuh app native Android, bukan
  script Termux)
- ❌ Auto mark "Offline" kalau agent mati mendadak — dashboard akan tetap
  menampilkan status terakhir sampai ada yang mengeceknya lagi

## ⚠️ Catatan Keamanan: `enable_command_tasks`

Kalau kamu set `enable_command_tasks: true`, agent akan menjalankan
**perintah shell apa saja** yang dikirim lewat Task Queue dengan tipe
"Command". Ini powerful tapi berisiko: siapapun yang bisa login ke akun
RANEMAX kamu otomatis bisa menjalankan perintah apapun di cloud phone kamu.
Biarkan `false` kecuali kamu benar-benar butuh fitur ini dan paham
risikonya — jaga baik-baik email/password akun RANEMAX kamu.

## 🔒 Pengamanan Tambahan yang Disarankan

**1. Config sudah dienkripsi (lihat langkah 6 di atas) — jangan skip.**
Ini mencegah password kebaca kalau file config diakses tanpa izin.

**2. Pertimbangkan buat akun Supabase terpisah khusus untuk tiap agent**,
bukan pakai akun pribadi kamu yang sama untuk semuanya. Caranya: di
Supabase Authentication → Add User, buat akun kedua (misal
`device1@ranemax.local`). Konsekuensinya: karena RLS di RANEMAX
mengunci data per akun, kamu perlu login ke dashboard pakai akun itu
juga untuk melihat device tersebut (jadi ini cocok kalau tiap device
memang ingin diisolasi total, kurang cocok kalau kamu mau semua device
terlihat di satu dashboard). Untuk kebanyakan kasus, satu akun untuk
semua device kamu sendiri sudah cukup — cukup pastikan config
terenkripsi (poin 1).

**3. Jangan pernah upload folder ini ke repo publik** tanpa memastikan
`config.json`/`config.enc` masuk `.gitignore` (sudah saya siapkan
`.gitignore`-nya, tinggal jangan dihapus).

**4. Kalau curiga device pernah diakses orang lain**, langsung ganti
password akun RANEMAX kamu di Supabase Authentication, lalu buat ulang
`config.enc` dengan password baru di semua device.
