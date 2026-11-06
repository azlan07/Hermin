# HERMIN 0.0.1-beta

Rilis beta pertama dashboard native untuk Hermes Agent, OpenCode v2, dan 9Router.

- Kontrol layanan, pemilihan model/combo, integrasi OpenCode Web dan statistik usage.
- Skill Manager dengan filter, status, lokasi, pause/aktifkan, validasi ulang dan penghapusan dengan backup.
- Editor Soul, memory, profil pengguna dan environment lokal.
- Installer Linux user systemd, verifikasi startup, backup deployment dan pemeriksaan update GitHub.
- Perintah backup/restore data lokal: provider, API key/OAuth, personality, Soul, memory, skill dan riwayat.
- Copyright utiedev dan tampilan versi beta di dashboard.

## Memasang

Lihat README dan docs/SETUP.md. Restore membutuhkan runtime resmi yang sesuai pada mesin tujuan; binary/virtual environment lama tidak ikut arsip data. Artefak source GitHub tidak menyertakan data pengguna.

## Batas beta

Agent native memakai izin OS user yang menjalankannya. Soul/memory bukan isolasi teknis. Dukungan update dan schema provider mengikuti aplikasi upstream. Arsip data privat tidak dienkripsi, hanya disimpan lokal, dan tidak disertakan sebagai aset rilis.
