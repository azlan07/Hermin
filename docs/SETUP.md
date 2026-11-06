# Setup stack native baru

Panduan ini untuk user Linux biasa dan direktori baru. Untuk instalasi lama, pertahankan unit/data yang sudah berjalan dan cukup install HERMIN. Paket agent didapat langsung dari sumber resmi; akun dan provider harus dikonfigurasi sendiri.

## 1. Runtime

Pasang Node 24 LTS melalui metode resmi yang sesuai distro, lalu pastikan `node --version` dan `npm --version` berhasil. Siapkan direktori:

```sh
export STACK="$HOME/server-lokal"
mkdir -p "$STACK/hermes/data" "$STACK/hermes/workspace" "$STACK/9router/data"
```

## 2. Hermes

Ikuti [installer resmi Hermes](https://github.com/NousResearch/hermes-agent#installation). Simpan dan baca skrip instalasi sebelum menjalankannya:

```sh
curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o /tmp/hermes-install.sh
bash /tmp/hermes-install.sh
```

Buka shell baru jika installer memperbarui PATH. Gunakan home data yang konsisten saat setup, CLI, dan layanan:

```sh
export HERMES_HOME="$STACK/hermes/data"
hermes setup
hermes model
```

Model 9Router dapat diatur setelah langkah berikutnya. Jika ingin mempertahankan home Hermes lama, jangan membuat setup baru; hubungkan direktori lama ke `$STACK/hermes/data` saat direktori tujuan masih kosong. Jangan menimpa dua home yang sama-sama berisi data. Login Nous menggunakan device code di `hermes model`.

Hermes web memerlukan dukungan dashboard pada instalasi resmi. Jalankan `hermes dashboard --help` dan ikuti petunjuk instalasi dependency Hermes bila komponen web belum tersedia. HERMIN tidak menjalankan pip langsung di lingkungan Hermes.

## 3. 9Router

Source dan data dipisahkan agar build/update tidak mengganti akun provider:

```sh
git clone https://github.com/decolua/9router.git "$STACK/9router/app"
cd "$STACK/9router/app"
npm ci
npm run build
```

Build versi yang diuji menghasilkan `.next/standalone/custom-server.js` dan menyalin aset lewat postbuild resmi. Lihat [petunjuk deployment upstream](https://github.com/decolua/9router#readme) jika struktur build berubah. HERMIN tidak memodifikasi source 9Router.

## 4. OpenCode v2

Gunakan **v2**, bukan installer v1. Lihat [dokumentasi resmi v2](https://opencode.ai/v2/docs/).

```sh
npm install -g @opencode/cli
opencode --version
opencode service set port 4096
```

Jika npm global membutuhkan root, gunakan pengelola Node per user; jangan mengubah kepemilikan direktori sistem. Jangan menyalin binary OpenCode ke lokasi kedua karena salinan itu tidak ikut ter-update. HERMIN memakai binary dari PATH bila salinan legacy `opencode/bin/opencode` tidak ada.

## 5. Layanan user

Dari clone repo HERMIN, buat unit untuk executable yang sudah dipasang:

```sh
cd "$HOME/Hermin"
python3 scripts/setup-services.py --root "$STACK"
systemctl --user daemon-reload
systemctl --user enable --now 9router.service
```

Script menolak menimpa unit yang sudah ada. Gunakan `--output /tmp/hermin-units` untuk membuat unit yang bisa diperiksa lebih dulu. Opsi `--hermes-bin`, `--opencode-bin`, dan `--node` menerima path executable khusus. Unit menangkap lokasi executable, bukan nomor versi Python internal Hermes.

Buka http://127.0.0.1:20128/dashboard, atur password dashboard 9Router, sambungkan provider, buat API key, lalu tes satu model di 9Router. Jangan menganggap semua model yang tercantum pasti bisa dipakai akun tersebut.

Atur Hermes dengan `HERMES_HOME="$STACK/hermes/data" hermes model`: pilih endpoint OpenAI-compatible/custom `http://127.0.0.1:20128/v1`, API key 9Router, dan model ID yang baru diuji. Sesudah HERMIN terpasang, model dan key juga dapat dikelola dari UI.

Untuk konfigurasi awal OpenCode, merge [contoh provider](../examples/opencode.json) ke `~/.config/opencode/opencode.json` melalui OpenCode atau editor. Jangan menimpa config lama. `apiKey` memakai `{env:OPENAI_API_KEY}`. Simpan nilai key ke environment layanan OpenCode melalui file lokal mode 0600 dan drop-in systemd:

```ini
# ~/.config/systemd/user/opencode-web.service.d/provider.conf
[Service]
EnvironmentFile=%h/.config/opencode/provider.env
```

Isi `~/.config/opencode/provider.env` dengan `OPENAI_API_KEY=` diikuti key lokal. Buat direktori drop-in bila belum ada. Alternatif konfigurasi/provider auth mengikuti OpenCode v2; jangan simpan key dalam repo. Untuk CLI OpenCode, ekspor key pada shell tersebut juga. HERMIN membaca key untuk discovery dari config OpenCode atau `.env` Hermes jika memakai referensi environment.

Kemudian:

```sh
systemctl --user daemon-reload
systemctl --user enable --now hermes-gateway.service
systemctl --user enable --now hermes-dashboard.service opencode-web.service
python3 manage.py install --root "$STACK"
python3 manage.py doctor --root "$STACK"
```

Buka HERMIN → OpenCode untuk memilih model dari katalog. Tes satu chat pada kedua agent. Sesuaikan konfigurasi provider dengan versi OpenCode bila schema upstream berubah.

## Jika belum berjalan

```sh
systemctl --user status hermin hermes-gateway hermes-dashboard 9router opencode-web
journalctl --user -u hermin -u hermes-gateway -u hermes-dashboard -u 9router -u opencode-web -n 100 --no-pager
ss -ltn
```

- Port dipakai: identifikasi prosesnya; jangan mematikan proses lain sembarangan.
- `systemctl --user` gagal: masuk sebagai user instalasi lewat SSH, pastikan sesi user aktif dan linger tersedia bila diperlukan.
- Hermes reconnect: periksa gateway/dashboard lebih dulu. Bandingkan web langsung pada 9119 dengan panel. Instalasi lama bisa memiliki patch port gateway yang harus ditinjau saat update, lihat maintenance.
- 9Router 401: periksa key dan base URL. Error provider 404/429/503 tidak otomatis berarti HERMIN bermasalah.
- SELinux: lihat audit denial dan label file. Jangan menonaktifkan SELinux secara global untuk memasang dashboard.
