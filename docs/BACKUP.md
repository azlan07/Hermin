# Cakupan backup 0.0.1-beta

Backup/restore dijalankan dari terminal sebagai user pemilik layanan. Tidak ada upload, sinkronisasi cloud, atau endpoint unduhan arsip pada dashboard.

| Komponen | Data yang disalin |
|---|---|
| Hermes | `STACK/hermes/data`: `.env`, config, auth provider/OAuth, Soul, personality/profile, memory, skills, sesi, state SQLite, cron dan pengaturan channel yang tersimpan |
| 9Router | `STACK/9router/data`: database SQLite berisi provider/key/combo/settings/usage, auth, JWT secret, machine-id dan katalog lokal |
| OpenCode | `~/.config/opencode`, `~/.opencode`, `~/.local/share/opencode`, `~/.local/state/opencode`: konfigurasi/provider, auth, agent, skill, memory dan sesi yang tersimpan |
| Skill bersama | `~/.agents/skills` dan `~/.claude/skills`, termasuk konten link yang dibaca saat backup |

Direktori runtime bernama `bin`, `tools`, `installs`, `runtime`, `headroom`, `venv`, `.venv`, `node_modules`, cache/log/backup, direktori Git, socket, PID, file lock dan SQLite WAL/SHM dilewati. Karena penulis dihentikan, database utama harus sudah konsisten. Proses/CLI manual lain yang menulis data harus dihentikan sendiri; command tidak menghentikan proses sembarang berdasarkan nama/port. File executable skill mempertahankan izin execute pemilik; file lain dipulihkan privat dengan mode 0600.

Secret yang disimpan di tempat lain, password manager, keyring OS, custom root di luar cakupan, environment shell, file proyek dan pengaturan systemd/drop-in tidak otomatis dibackup. Bila provider OpenCode memakai environment dari file, letakkan file tersebut dalam `~/.config/opencode` dan buat ulang referensi drop-in pada mesin tujuan. Skill/profil yang menunjuk folder eksternal lain harus dipindahkan terpisah.

## Urutan migrasi

1. Selesaikan pekerjaan agent; backup dengan `python3 manage.py backup`.
2. Simpan arsip secara privat dan pindahkan lewat SSH/SCP ke mesin tujuan. Jangan kirim ke AI/provider atau GitHub.
3. Pada tujuan, ikuti [SETUP](SETUP.md) sampai runtime resmi, clone HERMIN, unit, dan dashboard terpasang. Jangan login/model setup baru bila ingin memakai data lama.
4. Restore arsip ke root tujuan. `--overwrite` diperlukan jika ada file tujuan yang sudah ada; file itu tetap dicadangkan sebelum diganti.
5. Buat/periksa kembali unit dan lokasi executable. Jika aplikasi baru belum memiliki unit, restore tidak memasang atau menyalakannya otomatis.
6. Jalankan `doctor`, nyalakan layanan yang diperlukan, tes model, tools dan satu chat. Periksa path plugin/proyek lama yang mungkin tetap tersimpan di database sesi.

Restore bukan installer runtime. Tidak ada jaminan token OAuth, plugin native, cron yang bergantung pada perangkat, atau model provider akan bekerja tanpa penyesuaian pada host lain. Tinjau cron/skill dan restore hanya arsip yang dipercaya sebelum menjalankan agent.

## Salinan pemulihan restore

`STACK/hermin/backups/pre-restore-<id>/manifest.json` berisi mapping file tujuan ke salinan sebelumnya. Nilai null berarti file baru. Jika ingin membatalkan restore yang sudah berhasil, hentikan layanan terlebih dahulu dan pulihkan mapping tersebut; jangan menimpa database yang sedang aktif. Biarkan token login HERMIN mesin tujuan tetap pada lokasinya.

Checksum SHA-256 mendeteksi isi arsip rusak, bukan membuktikan siapa pembuatnya. Batas ekstraksi saat ini 100.000 file dan 20 GiB; arsip yang lebih besar ditolak. Media penyimpanan dan backup harus tetap diamankan sendiri karena arsip menyimpan rahasia tanpa enkripsi.
