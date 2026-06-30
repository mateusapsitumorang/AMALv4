# AMAL v4 — Automatic Malware Analyzer

**AMAL (Automatic Malware Analyzer) v4** adalah platform *malware analysis sandbox* yang dikembangkan sebagai turunan/*fork* dari [CAPE Sandbox (CAPEv2)](https://github.com/kevoreilly/CAPEv2), dengan kustomisasi tambahan berupa dashboard analitik dan visualisasi yang ditujukan untuk mendukung kebutuhan analisis malware oleh **BSSN (Badan Siber dan Sandi Negara)**.

> !!! Proyek ini berisi komponen yang berinteraksi langsung dengan sampel malware nyata (eksekusi di lingkungan virtual machine). Jalankan **hanya** di lingkungan terisolasi (lab/sandbox jaringan terpisah) dan oleh personel yang memahami risikonya !!!.

## Tentang Proyek

AMAL v4 mewarisi seluruh kapabilitas inti CAPE Sandbox — yaitu eksekusi otomatis sampel malware di dalam mesin virtual terisolasi, pemantauan perilaku (API hooking), ekstraksi payload & konfigurasi (config extraction), serta pelaporan hasil analisis — dan menambahkan lapisan kustomisasi berikut:

- **Dashboard analitik** yang dirombak total (statistik task, deteksi, status analisis) yang sebelumnya tersebar di halaman *Statistics* kini disatukan ke dalam satu halaman Dashboard.
- **Visualisasi graf koneksi jaringan** menggunakan [vis.js](https://visjs.org/) untuk memetakan komunikasi jaringan (host, domain, IP) dari sampel yang dianalisis.
- **Visualisasi pohon proses (process tree)** menggunakan [D3.js](https://d3js.org/) untuk menggambarkan relasi proses yang dibuat oleh malware selama eksekusi.
- **Ekspor laporan ke format DOCX** (`web/web/export_docx.py`) dengan format laporan resmi bertajuk "AMAL — Automatic Malware Analyzer".
- Branding internal (judul halaman admin, issuer OTP, dsb.) disesuaikan menjadi "AMAL v4".
- Bot basis pengetahuan (*Knowledge Base Bot*) berbasis Google Gemini untuk menjawab otomatis isu/pertanyaan di GitHub menggunakan embedding dari dokumentasi proyek.

## Fitur Inti (Warisan dari CAPE Sandbox)

- Analisis dinamis file (Windows, Linux, Android) dan URL secara otomatis di dalam VM
- Ekstraksi payload dan konfigurasi malware (*config extraction*) untuk berbagai keluarga malware
- Deteksi berbasis Yara, Suricata, dan signature CAPE
- Pemetaan ke MITRE ATT&CK dan MBC (Malware Behavior Catalog)
- Dukungan multi-hypervisor: KVM/QEMU (disarankan), VirtualBox, VMware, serta dukungan cloud (Azure, GCP)
- Web UI berbasis Django dengan autentikasi dan dukungan 2FA (OTP)
- REST API (`web/apiv2/`) untuk integrasi/submission otomatis
- Penyimpanan hasil di MongoDB/Elasticsearch, metadata task di PostgreSQL (via SQLAlchemy)
- Modul pelaporan ke berbagai format (JSON, HTML, MAEC, dll.)

## Tech Stack

| Layer                | Teknologi                                      |
|-----------------------|--------------------------------------------------|
| Bahasa utama          | Python 3 (≥3.10)                                |
| Web Framework         | Django                                           |
| Database task         | PostgreSQL (SQLAlchemy)                          |
| Database hasil        | MongoDB / Elasticsearch                          |
| Virtualisasi          | KVM/QEMU, VirtualBox, VMware, Azure, GCP         |
| Visualisasi Dashboard | vis.js (graf jaringan), D3.js (process tree)     |
| Manajemen dependensi  | Poetry / uv                                      |
| Deteksi               | Yara, Suricata, CAPA, signature kustom           |
| Knowledge Base Bot    | Python + FAISS + Google Gemini API               |

## Struktur Proyek (Ringkas)

```
AMALv4/
├── agent/                  # Skrip agen yang berjalan di dalam guest VM
├── analyzer/                # Komponen analisis (monitor, packages) di dalam guest VM
│   ├── linux/
│   └── windows/
├── conf/                    # Konfigurasi default (jangan diedit langsung)
├── custom/                  # Override konfigurasi milik pengguna (custom/conf/)
├── data/                    # Yara rules, CAPA rules, MITRE ATT&CK data, dsb.
├── installer/                # Skrip instalasi (cape2.sh, kvm-qemu.sh, dll.)
├── lib/cuckoo/               # Logika inti (Scheduler, Database, Guest Manager)
├── modules/
│   ├── auxiliary/            # Modul tambahan yang berjalan di host (mis. Sniffer)
│   ├── machinery/             # Driver virtualisasi (KVM, VirtualBox, dsb.)
│   ├── processing/            # Parser hasil analisis mentah
│   ├── reporting/              # Modul ekspor laporan
│   └── signatures/             # Aturan deteksi perilaku malware
├── utils/                    # Utilitas CLI (submit.py, process.py, rooter.py, dll.)
├── web/                       # Aplikasi web Django
│   ├── analysis/               # Tampilan hasil analisis
│   ├── apiv2/                  # REST API
│   ├── dashboard/               # Dashboard analitik & visualisasi (kustomisasi AMAL)
│   ├── submission/              # Form pengajuan sampel
│   └── export_docx.py            # Modul ekspor laporan ke DOCX bermerek AMAL
├── KnowledgeBaseBot/            # Bot auto-jawab isu GitHub berbasis Gemini + FAISS
├── tests/                       # Unit test
├── systemd/                     # Unit file systemd untuk service produksi
├── docs/                        # Dokumentasi (CAPE Book)
├── pyproject.toml               # Dependensi Python (Poetry/uv)
└── requirements.txt
```

## Instalasi

AMAL v4 mengikuti alur instalasi CAPE Sandbox. Disarankan menjalankan di server Linux (Ubuntu LTS) khusus untuk keperluan sandboxing, terpisah dari jaringan produksi.

### Prasyarat

- Server/VM host Linux (disarankan Ubuntu 22.04 LTS)
- Akses `sudo`/root pada host
- Hypervisor: KVM/QEMU (disarankan), atau VirtualBox/VMware
- Python ≥ 3.10
- PostgreSQL
- MongoDB dan/atau Elasticsearch (untuk penyimpanan hasil)
- Resource memadai untuk menjalankan VM analisis (RAM, disk, CPU virtualization extension)

### Instalasi Otomatis (skrip installer)

Proyek menyediakan skrip instalasi all-in-one:

```bash
git clone https://github.com/mateusapsitumorang/AMALv4.git
cd AMALv4
sudo bash installer/cape2.sh -h
```

Jalankan `cape2.sh` dengan opsi sesuai kebutuhan (lihat `installer/README.md` dan dokumentasi di `docs/book/` untuk detail tahapan instalasi, termasuk setup KVM/QEMU melalui `installer/kvm-qemu.sh`).

### Instalasi Manual (ringkas)

1. Clone repository:
   ```bash
   git clone https://github.com/mateusapsitumorang/AMALv4.git
   cd AMALv4
   ```

2. Install dependensi Python (menggunakan `uv` atau Poetry):
   ```bash
   uv venv --python python3.10 venv
   source venv/bin/activate
   uv pip install -r requirements.txt
   ```

3. Salin dan sesuaikan konfigurasi default ke direktori custom:
   ```bash
   bash conf/copy_configs.sh
   ```
   Lakukan override konfigurasi pada `custom/conf/` — **jangan** mengedit langsung file di `conf/default/`.

4. Siapkan database PostgreSQL untuk task management dan MongoDB/Elasticsearch untuk penyimpanan hasil analisis, lalu sesuaikan kredensial pada file konfigurasi terkait (`custom/conf/cuckoo.conf`, `custom/conf/reporting.conf`, dsb.).

5. Jalankan migrasi database web (Django):
   ```bash
   cd web
   python manage.py migrate
   ```

6. Siapkan mesin virtual analisis (guest VM) menggunakan hypervisor pilihan, install agen (`agent/agent.py`) di dalamnya, lalu daftarkan VM tersebut pada konfigurasi `machinery`.

7. Jalankan komponen utama (lihat juga unit `systemd/` untuk deployment sebagai service):
   ```bash
   # Scheduler / pemroses analisis
   python cuckoo.py

   # Web interface
   cd web
   python manage.py runserver 0.0.0.0:8000
   ```

> Untuk instruksi instalasi lengkap dan terperinci (networking, rooter, konfigurasi mesin virtual, dsb.), rujuk dokumentasi resmi CAPE di folder `docs/book/` atau di `docs/README`.

## Menjalankan sebagai Service (systemd)

Direktori `systemd/` menyediakan unit file untuk menjalankan komponen sebagai service produksi, di antaranya:

- `cape.service` — scheduler utama
- `cape-web.service` — antarmuka web
- `cape-processor.service` — pemrosesan hasil analisis
- `cape-rooter.service` — manajemen routing jaringan untuk VM
- `guacd.service` / `guac-web.service` — akses remote desktop (Guacamole) ke VM analisis
- `suricata.service` / `suricata-update.service` — IDS untuk traffic monitoring

Lihat `systemd/README.md` untuk instruksi instalasi unit-unit tersebut.

## Dashboard & Visualisasi (Kustomisasi AMAL)

Modul `web/dashboard/` menyajikan ringkasan statistik task (status pending, running, completed, failed) serta deteksi teratas (*top detections*) dalam satu halaman. Tambahan visualisasi:

- **Network graph (vis.js)** — memetakan relasi koneksi jaringan dari hasil analisis sampel (domain, IP, host yang dihubungi).
- **Process tree (D3.js)** — menampilkan struktur proses yang dibuat/dimodifikasi oleh sampel selama eksekusi di sandbox.

## Ekspor Laporan ke DOCX

Modul `web/web/export_docx.py` menyediakan fungsi ekspor hasil analisis ke dokumen Word (`.docx`) dengan format laporan baku bertajuk **"AMAL — Automatic Malware Analyzer"**, lengkap dengan nomor dokumen (`DOC-AMAL-<task_id>`) dan footer standar.

## Knowledge Base Bot

Folder `KnowledgeBaseBot/` berisi bot auto-jawab berbasis GitHub Actions yang akan otomatis merespons *issue* baru di repository menggunakan basis pengetahuan dari dokumentasi proyek (diindeks dengan FAISS) dan model Google Gemini. Lihat `KnowledgeBaseBot/readme.md` untuk panduan setup (konfigurasi `GITHUB_TOKEN` dan `GEMINI_API_KEY` sebagai GitHub Secrets, lalu menjalankan `build_knowledge_base.py`).

## Pengujian

Unit test tersedia di folder `tests/`, dapat dijalankan dengan `pytest`:

```bash
pytest tests/
```

Modul `agent/` juga memiliki test tersendiri (`agent/test_agent.py`, `agent/pytest.ini`).

## Keamanan

Lihat `SECURITY.md` untuk kebijakan pelaporan kerentanan keamanan proyek ini.

## Lisensi & Atribusi

Proyek ini merupakan turunan dari **CAPE Sandbox (CAPEv2)**, hasil karya Kevin O'Reilly dan kontributor, yang dilisensikan di bawah **GPL-3.0** (lihat `LICENSE`). Atribusi dan riwayat kontribusi pihak ketiga dapat dilihat pada `acknowledgment.md` dan `CITATION.cff`. Kustomisasi tambahan (dashboard, visualisasi, ekspor DOCX bermerek AMAL) dikembangkan di atas basis kode tersebut sesuai dengan ketentuan lisensi yang sama.

Jika menggunakan proyek ini untuk publikasi atau penelitian, mohon sertakan sitasi sesuai `CITATION.cff`.

## Instansi Pengguna

Proyek ini dikembangkan dan digunakan dalam lingkup **Badan Siber dan Sandi Negara (BSSN)** Republik Indonesia untuk mendukung kegiatan analisis malware.

### Dikembangkan oleh

* **Mateus Appuwan Situmorang**
* **Naufal Abrar Rabbani**
* **Farhan Ari Nur Wibisono**
