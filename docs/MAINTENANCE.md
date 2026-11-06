# Maintenance dan update

HERMIN dan ketiga aplikasi mempunyai lifecycle terpisah. Updater HERMIN tidak melakukan git pull, pip, npm install, atau migrasi database di aplikasi agent. Username dan root stack mengikuti mesin instalasi, tanpa patch alamat home pada source.

## Sebelum update agent

1. Catat versi Hermes, OpenCode, commit 9Router, dan commit HERMIN. Tutup atau selesaikan percakapan aktif.
2. Hentikan dashboard Hermes dahulu, kemudian gateway, OpenCode web, dan 9Router.
3. Cadangkan data/konfigurasi berikut beserta unit user dan drop-in-nya ke penyimpanan privat di luar Git. Untuk SQLite, hentikan penulis sebelum menyalin, atau gunakan SQLite backup API.
4. Update satu aplikasi, mulai kembali, dan uji model serta tools sebelum melanjutkan aplikasi lain.

Yang perlu dicadangkan:

- `STACK/hermes/data` (termasuk `.env`, config, sesi, memory, skills) dan lokasi aktualnya jika symlink.
- `STACK/hermes/security`, `STACK/9router/data` (termasuk `db/data.sqlite`, JWT secret, key/provider).
- `~/.config/opencode`, `~/.opencode`, `~/.local/share/opencode`, `~/.local/state/opencode`, dan file environment layanan yang dipakai.
- `~/.config/systemd/user` termasuk drop-in, serta metadata `STACK/hermin/state/installation.json`.

Backup memuat kredensial. Simpan dengan izin 0700/0600, jangan unggah ke repo publik.

## Hermes

Gunakan launcher resmi dan home yang sama:

```sh
systemctl --user stop hermes-dashboard.service
systemctl --user stop hermes-gateway.service
HERMES_HOME="$HOME/server-lokal/hermes/data" hermes update
systemctl --user start hermes-gateway.service
systemctl --user start hermes-dashboard.service
```

Jangan memakai path Python di dalam generasi `installs/<hash>/environments/<hash>` pada unit. Launcher resmi memilih lingkungan yang benar. Dependency tambahan diperbaiki melalui mekanisme Hermes resmi sesuai petunjuk CLI versi tersebut; jangan menjalankan pip dari HERMIN.

Instalasi Fedora lama bisa mempunyai perubahan lokal `run_api.start_gateway_api(runner, port=9118)` di `gateway/run_runtime.py`. Periksa `git diff` repo Hermes sebelum update. Jangan membuang perubahan itu tanpa menguji koneksi gateway/dashboard; jangan menerapkan penggantian string otomatis ke source upstream yang sudah berubah. HERMIN sendiri tidak membutuhkan port gateway tetap, tetapi dashboard versi tertentu bisa mengandalkannya. Kebutuhan patch tersebut bergantung pada versi Hermes dan harus ditinjau setelah update.

## 9Router dari source

Setelah backup dan memastikan working tree 9Router bersih:

```sh
systemctl --user stop 9router.service
cd "$HOME/server-lokal/9router/app"
git status --short
git pull --ff-only
npm ci
npm run build
systemctl --user start 9router.service
```

Jangan memakai `git reset --hard` untuk memaksa update. `DATA_DIR` harus tetap menunjuk direktori data di luar source/build. Perubahan format database upstream mungkin membutuhkan pemulihan seluruh backup saat downgrade, bukan hanya checkout commit lama.

## OpenCode v2

```sh
systemctl --user stop opencode-web.service
opencode upgrade
systemctl --user start opencode-web.service
```

Gunakan executable yang sama dengan `ExecStart` unit. Instalasi lama yang memakai salinan binary di `STACK/opencode/bin/opencode` tidak otomatis mengikuti upgrade binary dari PATH. Pilih satu executable resmi yang akan dipelihara; sesuaikan unit dan `HERMIN_OPENCODE_BIN` jika diperlukan. Pastikan versi v2 mendukung `serve --service`, `service set port`, dan `pair --url`.

Jangan menginstal `opencode-ai` v1 ke command yang sama dengan v2 `@opencode/cli`.

## HERMIN

Contoh berikut memakai lokasi clone untuk instalasi baru. Clone lama di lokasi lain tetap dipakai dari lokasi aktualnya.

Menu Layanan native dapat memeriksa commit `main` di GitHub. Pembaruan diterapkan dari terminal:

```sh
cd "$HOME/server-lokal/hermin/repo"
python3 manage.py update --root "$HOME/server-lokal"
```

Tidak ada penjadwalan update otomatis. Perintah menolak working tree kotor, origin yang tidak dikenal, dan histori yang tidak bisa fast-forward. Installer mengetes source, menyimpan backup runtime/unit, memperbarui dependency dashboard yang dipin, dan memverifikasi bahwa listener meminta autentikasi.

Backup deployment ada di `STACK/hermin/backups/deploy-*/manifest.json`. Mapping berisi path tujuan dan salinan file lama; nilai null berarti file belum ada sebelum deployment. Untuk rollback manual, hentikan HERMIN, pulihkan file sesuai manifest (hapus hanya file dengan nilai null yang memang baru dibuat deployment itu), daemon-reload, dan mulai HERMIN. Jangan menimpa database/config agent. Lingkungan Python bisa sudah menerima dependency baru; lihat requirements dari commit sebelum update bila masalahnya ada pada dependency.

## Setelah update

```sh
python3 manage.py doctor --root "$HOME/server-lokal"
systemctl --user is-active hermin hermes-gateway hermes-dashboard 9router opencode-web
journalctl --user -u hermin -u hermes-gateway -u hermes-dashboard -n 80 --no-pager
```

Uji satu chat teks, streaming, penggunaan tool, serta satu gambar pada model yang memang mendukung vision. Periksa discovery model 9Router, penggantian model, dan pairing OpenCode. API provider, login OAuth, kuota, serta kemampuan model tidak dapat dijamin oleh HERMIN.

## Backup skill

Hapus melalui Skill Manager memindahkan folder/file skill ke `STACK/maintenance/backups/skills/<timestamp-id>/`. `manifest.json` mencatat path asal. Pastikan path asal kosong sebelum memindahkannya kembali. Pause mengganti nama `SKILL.md` menjadi `SKILL.md.hermin-paused`; aktifkan sebelum update/reinstall melalui installer lain agar tidak tercipta salinan aktif baru. Sesi lama harus diganti untuk berhenti menggunakan instruksi yang sudah dimuat.

## Keamanan dan privasi

HERMIN adalah admin panel tepercaya dan dapat mengedit file serta layanan user yang menjalankannya. Bind localhost, Basic login, dan CSRF melindungi akses HTTP. Agent native/user yang sama masih dapat membaca file token atau mengubah file user tersebut. Soul/memory bukan isolasi OS. Jangan membuka panel langsung ke internet; gunakan SSH forwarding.
