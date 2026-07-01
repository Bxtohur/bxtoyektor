<div align="center">

<img src="assets/app.png" width="120" alt="bxtoyektor logo">

# bxtoyektor

**Aplikasi desktop untuk mencari & mem-preview dokumen bukti fisik, lalu menampilkannya ke proyektor dengan mode dua layar.**

Cari cepat → cek di laptop → tampilkan ke proyektor. Kontrol penuh dari operator, layar asesor tetap bersih.

[⬇️ Download Installer](../../releases/latest) · [Fitur](#-fitur) · [Cara Pakai](#-cara-pakai) · [Build dari Source](#-build-dari-source)

</div>

---

## ✨ Fitur

- **Sumber data fleksibel** — pindai satu **folder besar** secara rekursif, atau baca file **Excel** (deteksi kolom otomatis per-sheet).
- **Pencarian instan** — hasil muncul saat mengetik, toleran typo (fuzzy), dengan filter kategori.
- **Preview banyak format langsung di aplikasi:**
  | Jenis | Format |
  |-------|--------|
  | Dokumen | PDF, DOCX/DOC, PPTX/PPT |
  | Gambar | PNG, JPG, GIF, BMP, WEBP |
  | Video | MP4, MKV, MOV, AVI, WEBM, M4V |
- **PDF scroll menerus** seperti PDF viewer biasa — scroll bebas, zoom (tombol / `Ctrl` + scroll / `Ctrl` +/−).
- **Mode dua layar (laptop + proyektor):**
  - Konfirmasi **2 langkah**: cek dulu di laptop, baru **"Tampilkan ke Proyektor"**.
  - **Sinkron persis** — scroll & zoom di laptop mengikuti di proyektor (walau resolusi beda).
  - **Video ikut terkontrol** — play/pause/seek dari laptop mengatur proyektor; suara dari satu sumber (tanpa dobel).
  - **Fullscreen bersih total** — tanpa judul/kontrol apa pun di layar asesor.
- **Deteksi monitor kedua** otomatis, dengan pintasan keyboard (`Ctrl+F`, `←/→`, `F11`).

## 📥 Cara Pakai (Pengguna)

1. Download **`bxtoyektor-Setup.exe`** dari halaman [**Releases**](../../releases/latest).
2. Jalankan installer (per-user, **tidak butuh hak admin**).
3. Buka **bxtoyektor** dari Start Menu.
4. Klik **Buka Folder…** (atau **Buka Excel…**) untuk memuat dokumen.
5. Cari → klik dokumen untuk preview → **Buka Jendela Presentasi** → **Tampilkan ke Proyektor**.

> **Preview PPTX/DOCX** butuh [LibreOffice](https://www.libreoffice.org/) terpasang (gratis).
> PDF, gambar, dan video tetap jalan tanpa LibreOffice.

## 🛠️ Build dari Source

Butuh **Python 3.11+** (Windows 10/11).

```powershell
git clone https://github.com/Bxtohur/bxtoyektor.git
cd bxtoyektor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py                    # jalankan aplikasi
```

Membuat installer sendiri:

```powershell
python assets/make_icon.py                        # ikon → assets/app.ico
pyinstaller --noconfirm --clean build.spec        # → dist/bxtoyektor/
&"$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer.iss
#                                                 → installer_output/bxtoyektor-Setup.exe
```

Pengembangan:

```powershell
pytest                    # tes logika (parser, search, model, folder scanner)
ruff check src tests      # lint
```

## 🧱 Tech Stack

PySide6 (Qt) · PyMuPDF (render PDF) · LibreOffice headless (Office → PDF) ·
QtMultimedia/ffmpeg (video) · openpyxl (Excel) · rapidfuzz (fuzzy search) ·
PyInstaller + Inno Setup (distribusi).

## 📁 Struktur Proyek

```
src/data     → baca & normalisasi sumber (folder / Excel) → DocumentItem
src/search   → index pencarian in-memory (substring + fuzzy)
src/render   → render PDF/Office/gambar → gambar per-halaman
src/ui       → jendela operator, jendela proyektor, viewer, video, worker
src/window_manager.py → koordinasi 2 jendela (Qt signal/slot)
```

## 📄 Lisensi

Proyek internal. Hubungi pemilik repo untuk pemakaian di luar organisasi.
