# Urutan setup HERMIN + Hermes + OpenCode v2 + 9Router

Panduan untuk **Ubuntu Server 24.04 atau Fedora**, dijalankan melalui Bash sebagai user biasa. Perintah `sudo` hanya untuk paket OS dan pengaturan linger. Installer HERMIN memasang dashboard; runtime ketiga aplikasi dipasang melalui sumber resmi di langkah terpisah.

**Urutannya:** paket OS → direktori dan PATH → Node/npm → clone HERMIN → Hermes → 9Router → OpenCode v2 → unit layanan → pilih setup baru atau restore → start dan verifikasi.

Kalau aplikasi sudah terpasang, lihat [instalasi yang sudah ada](#instalasi-yang-sudah-ada). Jangan menjalankan ulang seluruh panduan pada stack aktif.

## 1. Paket OS dan user

Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3 python3-venv python3-pip build-essential
```

Fedora:

```bash
sudo dnf install -y git curl ca-certificates python3 python3-pip gcc gcc-c++ make
```

Pastikan sesi systemd user dapat diakses:

```bash
whoami
systemctl --user show-environment
sudo loginctl enable-linger "$USER"
```

Jika masuk sebagai root, buat/login ke user instalasi terlebih dahulu. `enable-linger` membuat layanan user dapat hidup setelah reboot tanpa login. Jangan menjalankan installer aplikasi/HERMIN dengan sudo.

## 2. Direktori dan PATH yang konsisten

Root stack **bukan** direktori clone repo. Untuk instalasi baru gunakan struktur ini:

```text
~/server-lokal/
├── stack.env                      # hanya path; tanpa API key
├── hermin/
│   ├── repo/                      # clone github.com/azlan07/Hermin
│   ├── downloads/                 # installer resmi yang ditinjau
│   ├── venv/                      # Python dashboard HERMIN
│   ├── state/
│   └── backups/
├── hermes/
│   ├── app/                       # aplikasi/launcher resmi Hermes
│   ├── data/                      # HERMES_HOME: config, auth, Soul, memory, sesi
│   ├── workspace/
│   ├── security/
│   └── control-dashboard/         # runtime HERMIN, dibuat manage.py
├── 9router/
│   ├── app/                       # source resmi + hasil build
│   └── data/                      # DATA_DIR: database, provider dan key
└── opencode/
    ├── bin/opencode               # symlink executable dari npm, bukan salinan binary
    └── lib/node_modules/          # paket resmi @opencode/cli
```

Buat file path sekali pada mesin baru:

```bash
mkdir -p "$HOME/server-lokal/hermin/downloads"
cat > "$HOME/server-lokal/stack.env" <<'ENV'
export STACK="$HOME/server-lokal"
export HERMIN_REPO="$STACK/hermin/repo"
export HERMES_HOME="$STACK/hermes/data"
export PATH="$STACK/opencode/bin:$HOME/.local/bin:$PATH"
ENV
source "$HOME/server-lokal/stack.env"
mkdir -p "$STACK/hermes/data" "$STACK/hermes/workspace" "$STACK/9router/data"
```

File ini hanya menyimpan lokasi, bukan kredensial. Pada mesin yang sudah mempunyai `stack.env`, tinjau/merge isinya, jangan timpa. Muat file ini pada setiap SSH/shell baru, atau tambahkan baris berikut sekali ke `~/.bashrc`:

```bash
source "$HOME/server-lokal/stack.env"
```

OpenCode tetap memakai lokasi config/data resmi user: `~/.config/opencode`, `~/.opencode`, `~/.local/share/opencode`, dan `~/.local/state/opencode`. Jangan memindahkan direktori itu secara manual.

## 3. Node.js dan npm

9Router memerlukan Node/npm, terpisah dari Python HERMIN. Untuk mesin baru gunakan Node 24 LTS melalui [nvm resmi](https://github.com/nvm-sh/nvm#installing-and-updating). Jika Node yang didukung sudah terpasang, pertahankan instalasi tersebut; tidak perlu memasang nvm lagi.

Unduh installer nvm, tinjau file, lalu jalankan:

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.41.0/install.sh -o "$STACK/hermin/downloads/nvm-install.sh"
bash -n "$STACK/hermin/downloads/nvm-install.sh"
```

Setelah meninjau skrip yang diunduh:

```bash
bash "$STACK/hermin/downloads/nvm-install.sh"
source "$HOME/.nvm/nvm.sh"
nvm install 24
nvm alias default 24
node --version
npm --version
```

Buka shell baru atau source nvm jika `node`/`npm` belum terbaca. Mengganti versi Node pada nvm tidak otomatis membawa paket global dari versi Node sebelumnya. Panduan ini memasang OpenCode pada prefix stack yang tetap untuk menghindari salinan binary yang tertinggal.

## 4. Clone source HERMIN

```bash
git clone https://github.com/azlan07/Hermin.git "$HERMIN_REPO"
cd "$HERMIN_REPO"
```

Jangan clone repo HERMIN langsung ke root data `~/server-lokal` untuk instalasi baru. Folder repo harus berisi source Git; data runtime berada di sebelahnya. Jika clone sudah berada di lokasi lain, tetap gunakan lokasi itu dan sesuaikan `HERMIN_REPO` pada shell; tidak perlu memindahkan/menghapus data.

## 5. Hermes melalui installer resmi

Sumber: [Hermes Agent](https://github.com/NousResearch/hermes-agent), [installer resmi](https://hermes-agent.nousresearch.com/install.sh).

Unduh dan tinjau skrip:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o "$STACK/hermin/downloads/hermes-install.sh"
bash -n "$STACK/hermin/downloads/hermes-install.sh"
```

Setelah ditinjau, jalankan dengan lokasi aplikasi dan data secara eksplisit:

```bash
bash "$STACK/hermin/downloads/hermes-install.sh" \
  --dir "$STACK/hermes/app" \
  --hermes-home "$HERMES_HOME" \
  --skip-setup
hash -r
command -v hermes
hermes --version
"$STACK/hermes/app/.hermes/bin/hermes" --version
```

Opsi `--dir`, `--hermes-home`, dan `--skip-setup` diverifikasi pada skrip resmi saat panduan ini diperbarui. Installer resmi mengurus runtime/dependency Hermes sendiri. `--skip-setup` menunda wizard/provider dan pemasangan gateway agar home data dapat di-restore lebih dulu serta unit tidak dibuat dua kali. Jangan menjalankan pip langsung ke lingkungan internal Hermes.

Server tanpa desktop dapat menambahkan `--skip-computer-use`; ini menonaktifkan pemasangan driver computer-use dan disimpan oleh installer. Jangan tambahkan opsi itu jika memang memerlukan kontrol desktop. Browser/computer-use bukan syarat untuk login model atau dashboard HERMIN.

Jika punya home Hermes lama di `~/.hermes`, jangan membuat dua konfigurasi berbeda. Gunakan home data lama atau migrasikan dengan backup sebelum menghubungkannya ke root stack. Semua CLI dan unit harus memakai `HERMES_HOME` yang sama.

## 6. 9Router melalui source resmi

[9Router resmi](https://github.com/decolua/9router) menyediakan instalasi npm dan alternatif menjalankan source. Integrasi unit HERMIN saat ini memakai **build source resmi** pada `9router/app` supaya lokasi `DATA_DIR` dan server production bisa ditentukan dengan jelas. Tidak perlu sekaligus memasang paket global `9router`.

```bash
git clone https://github.com/decolua/9router.git "$STACK/9router/app"
cd "$STACK/9router/app"
cp -n .env.example .env
npm ci
npm run build
test -f "$STACK/9router/app/.next/standalone/custom-server.js"
```

Ikuti [petunjuk build/deployment upstream](https://github.com/decolua/9router#readme) jika build gagal atau struktur hasilnya berubah. Build dapat memerlukan waktu dan RAM; periksa pesan error sebelum melanjutkan. Postbuild resmi menyalin static/public/custom-server ke direktori standalone. Data provider ditempatkan di `9router/data`, di luar source/build.

Jangan menjalankan `npm run dev` atau server manual bersamaan dengan unit yang akan memakai port 20128. Unit HERMIN membatasi listener ke `127.0.0.1`, bukan ke IP publik.

## 7. OpenCode v2 melalui paket resmi

Sumber: [dokumentasi resmi OpenCode v2](https://opencode.ai/v2/docs/). Paketnya **`@opencode/cli`**. Opsi `--prefix` adalah pengaturan lokasi instalasi npm, [sesuai dokumentasi npm](https://docs.npmjs.com/cli/v11/commands/npm-install/).

```bash
npm install --global --prefix "$STACK/opencode" @opencode/cli
hash -r
command -v opencode
opencode --version
"$STACK/opencode/bin/opencode" --version
opencode service set port 4096
opencode service stop
```

`opencode service stop` di akhir menghentikan daemon manual yang mungkin dibuat CLI selama konfigurasi, agar tidak berebut port dengan unit systemd pada langkah 10. Jalankan blok ini untuk instalasi baru, bukan saat ada pekerjaan aktif.

Output `command -v opencode` seharusnya menunjuk ke `$STACK/opencode/bin/opencode` karena PATH dari langkah 2. Ini paket yang dikelola npm di prefix tersebut, bukan binary yang disalin manual. Installer `opencode-ai`/Snap yang disarankan shell bisa memilih aplikasi/versi lain; ikuti metode v2 di atas untuk integrasi ini.

Kalau muncul `command not found`, **berhenti di sini** dan periksa:

```bash
source "$HOME/server-lokal/stack.env"
hash -r
type -a opencode
ls -l "$STACK/opencode/bin/opencode"
node --version
npm --version
```

Jika pernah memasang OpenCode di PATH lain dan masih berfungsi, tidak perlu membuat instalasi ganda. Gunakan executable yang sama untuk CLI, updater dan unit; sesuaikan `--opencode-bin` saat membuat unit.

## 8. Buat unit layanan, belum dinyalakan

Pastikan executable/build dari langkah 5–7 benar-benar ada. Dari clone HERMIN:

```bash
cd "$HERMIN_REPO"
python3 scripts/setup-services.py --root "$STACK" \
  --hermes-bin "$STACK/hermes/app/.hermes/bin/hermes" \
  --opencode-bin "$STACK/opencode/bin/opencode" \
  --node "$(command -v node)"
systemctl --user daemon-reload
python3 manage.py install --root "$STACK"
```

Langkah ini membuat empat unit aplikasi, tetapi belum menyalakannya. `manage.py install` hanya memasang/menyalakan dashboard **HERMIN**. Script menolak menimpa unit lama; gunakan `--output /tmp/hermin-unit-review` untuk membuat file yang bisa ditinjau terlebih dahulu pada instalasi lama.

Unit systemd tidak membaca `.bashrc` atau otomatis memuat nvm. Agar proses OpenCode/pairing yang dipanggil HERMIN juga menemukan Node, tambahkan PATH pada drop-in HERMIN:

```bash
NODE_BIN="$(dirname "$(command -v node)")"
mkdir -p "$HOME/.config/systemd/user/hermin.service.d"
printf '[Service]\nEnvironment="PATH=%s:%s/opencode/bin:%s/.local/bin:/usr/local/bin:/usr/bin:/bin"\n' \
  "$NODE_BIN" "$STACK" "$HOME" > "$HOME/.config/systemd/user/hermin.service.d/runtime-path.conf"
systemctl --user daemon-reload
systemctl --user restart hermin.service
```

Ini contoh untuk direktori home/root biasa tanpa karakter khusus. Unit aplikasi yang dibuat script sudah menyimpan PATH Node saat setup. Jika versi/lokasi Node diganti, perbarui PATH/drop-in/ExecStart yang menunjuk lokasi lama sebelum restart.

## 9. Pilih konfigurasi baru atau restore

### A. Setup baru tanpa backup

Nyalakan 9Router terlebih dahulu:

```bash
systemctl --user enable --now 9router.service
```

Buka http://127.0.0.1:20128/dashboard melalui browser lokal atau SSH tunnel di langkah 11. Atur password dashboard, sambungkan provider, buat API key, lalu uji satu model yang memang dapat digunakan akun tersebut.

Konfigurasi Hermes pada home yang sudah dipilih:

```bash
hermes setup
hermes model
```

Pilih custom/OpenAI-compatible endpoint `http://127.0.0.1:20128/v1`, API key 9Router, dan model ID yang sudah diuji. Untuk Nous Portal, pilih Nous lalu ikuti device-code login. Jika wizard menawarkan pemasangan gateway otomatis, lewati karena unit sudah dibuat pada langkah 8.

Untuk OpenCode, pada konfigurasi baru yang **belum memiliki** `opencode.json`:

```bash
mkdir -p "$HOME/.config/opencode"
cp -n "$HERMIN_REPO/examples/opencode.json" "$HOME/.config/opencode/opencode.json"
chmod 600 "$HOME/.config/opencode/opencode.json"
```

Kalau file sudah ada, merge bagian provider 9Router dari contoh tersebut secara manual; jangan menimpa konfigurasi lama. Template memakai `{env:OPENAI_API_KEY}`. Buat file kredensial lokal melalui editor, tanpa memasukkan key ke command history:

```bash
if [ ! -e "$HOME/.config/opencode/provider.env" ]; then
  install -m 600 /dev/null "$HOME/.config/opencode/provider.env"
fi
chmod 600 "$HOME/.config/opencode/provider.env"
nano "$HOME/.config/opencode/provider.env"
```

Pengecekan di atas mempertahankan file yang sudah ada. Isi lewat editor: `OPENAI_API_KEY=` diikuti API key lokal, tanpa spasi sebelum/sesudah `=`. Buat referensi untuk layanan OpenCode:

```bash
mkdir -p "$HOME/.config/systemd/user/opencode-web.service.d"
cat > "$HOME/.config/systemd/user/opencode-web.service.d/provider.conf" <<'UNIT'
[Service]
EnvironmentFile=%h/.config/opencode/provider.env
UNIT
systemctl --user daemon-reload
```

Untuk CLI OpenCode pada shell ini juga:

```bash
set -a
source "$HOME/.config/opencode/provider.env"
set +a
```

Source hanya file environment yang dibuat sendiri dan dipercaya. HERMIN mendapatkan key untuk katalog dari config OpenCode atau `.env` Hermes saat key berupa referensi environment. Buka HERMIN → OpenCode untuk memilih model setelah konfigurasi provider tersimpan. Key/cookie/token tetap lokal, bukan di repo.

### B. Migrasi dengan backup lokal

Lewati login/provider setup baru pada bagian A. Setelah runtime/unit/HERMIN dipasang, salin arsip secara privat lalu restore:

```bash
cd "$HERMIN_REPO"
python3 manage.py restore --root "$STACK" --archive /path/privat/backup.tar.gz
```

Ganti path contoh dengan file arsip yang benar. Jika file tujuan sudah ada, tinjau isinya sebelum menambahkan `--overwrite`; salinan pemulihan tetap dibuat. Restore tidak memasang binary/runtime dan tidak menjalankan unit dari arsip. Periksa kembali [cakupan backup](BACKUP.md), khususnya provider OpenCode yang menggunakan file environment: buat ulang drop-in `provider.conf` jika dibutuhkan. Login OAuth kadang perlu diulang pada host baru.

## 10. Nyalakan dan verifikasi

```bash
systemctl --user enable --now 9router.service
systemctl --user enable --now hermes-gateway.service
systemctl --user enable --now hermes-dashboard.service opencode-web.service
cd "$HERMIN_REPO"
python3 manage.py doctor --root "$STACK"
systemctl --user is-active hermin hermes-gateway hermes-dashboard 9router opencode-web
```

Buka HERMIN http://127.0.0.1:1515/. Username adalah user Linux instalasi, password ada di file lokal:

```bash
cat "$STACK/hermes/security/hermin-admin-token"
```

Jangan membagikan token. Tes satu chat di Hermes dan OpenCode serta satu request 9Router. `doctor` mengecek socket/config; tes Python HERMIN yang lolos tidak membuktikan agent, provider, atau runtime lain sudah terpasang/berhasil inferensi.

Jika Hermes web meminta build/dependency, ikuti petunjuk `hermes dashboard --help`/package manager resmi versi tersebut. Unit tidak memakai `--skip-build` agar build pertama tidak dilewati. Lihat [maintenance](MAINTENANCE.md) sebelum update aplikasi.

## 11. Akses SSH / Tailscale

Dari **laptop**, jalankan dengan username/alamat server yang benar:

```bash
ssh -L 1515:127.0.0.1:1515 -L 9119:127.0.0.1:9119 -L 20128:127.0.0.1:20128 -L 4096:127.0.0.1:4096 USER@HOST_TAILSCALE
```

Lalu buka di browser laptop: HERMIN `http://127.0.0.1:1515/`, Hermes `http://127.0.0.1:9119/`, 9Router `http://127.0.0.1:20128/dashboard`. OpenCode dibuka lewat tombol pairing HERMIN. Jika port lokal terpakai, pilih port lokal alternatif untuk HERMIN. Tidak perlu domain/IP publik.

## Instalasi yang sudah ada

- Pertahankan root, repo, data, dan unit yang sudah berjalan. Clone yang telanjur berada di `~/server-lokal` tetap bisa digunakan; jangan menghapus atau memindahkannya sembarangan. Set `HERMIN_REPO` ke direktori yang benar-benar berisi `manage.py` dan `.git`.
- Sebelum update, `cd` ke clone yang benar dan jalankan `git status --short`. Repo kotor ditolak updater untuk melindungi perubahan lokal. Jangan memakai `git reset --hard` atau `git add .` untuk memasukkan folder runtime/kredensial.
- Jika OpenCode sudah dipasang melalui npm global biasa, `command -v opencode` menunjukkan executable yang harus dipakai pada unit. Gunakan `systemctl --user cat opencode-web.service` untuk memeriksa `ExecStart`.
- Untuk error `-bash: /usr/local/bin/opencode: No such file or directory`, jalankan `hash -r`, `type -a opencode`, dan periksa symlink lama. Jika tetap `command not found`, pasang OpenCode v2 dari langkah 7; instalasi HERMIN/Node tidak memasang OpenCode otomatis.
- Setelah lokasi executable berubah, edit unit/drop-in milik instalasi tersebut, `daemon-reload`, dan restart layanan. Script setup tidak menimpa unit lama.

## Troubleshooting

```bash
systemctl --user status hermin hermes-gateway hermes-dashboard 9router opencode-web
journalctl --user -u hermin -u hermes-gateway -u hermes-dashboard -u 9router -u opencode-web -n 100 --no-pager
ss -ltn
```

Port yang dipakai aplikasi lain tidak dibebaskan otomatis. Untuk `systemctl --user` gagal, masuk lewat SSH sebagai user instalasi dan periksa sesi/linger. Untuk Hermes reconnect, bandingkan dashboard langsung dan cek gateway; instalasi lama bisa mempunyai patch port yang perlu ditinjau saat update. Untuk 9Router 401 periksa key/base URL; 404/429/503 dari provider juga dapat berarti model tidak tersedia atau kuota habis. Pada Fedora, periksa denial/label SELinux; jangan mematikan SELinux global untuk memasang panel.
