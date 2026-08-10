/* Service worker halaman muka Indobarca Bali.

   Tujuannya satu: menghapus layar putih saat aplikasi dibuka dari layar
   utama. Layar peluncur iOS sudah benar (navy berlogo), tapi iOS
   melepasnya begitu WebView siap — sementara halamannya sendiri masih
   diunduh dari jaringan, 79 KB, setiap kali diluncurkan. Selama unduhan
   itulah putihnya muncul, dan tidak ada yang bisa diperbuat dari dalam
   halaman yang belum tiba. Dengan berkas ini halaman disajikan dari
   perangkat, jadi tidak ada jeda jaringan sama sekali.

   KONSEKUENSI YANG DISENGAJA: setelah pembaruan diterbitkan, pintasan di
   layar utama masih menampilkan versi lama SATU KALI, lalu memperbarui
   diri diam-diam untuk peluncuran berikutnya. Itu harga yang dibayar
   untuk tampil seketika. Kalau perlu melihat versi terbaru saat itu juga,
   buka lewat Safari biasa, bukan lewat pintasan.

   Menaikkan VERSI memaksa seluruh isi tersimpan dibuang dan diambil ulang.
*/
const VERSI = 'ib-1';
const INTI = 'inti-' + VERSI;   // kerangka: yang dibutuhkan layar pertama
const ISI = 'isi-' + VERSI;     // foto dan lambang yang menyusul belakangan

/* Hanya yang dibutuhkan layar pertama untuk tampil utuh. Foto lain dan
   lambang tim menyusul sendiri saat pertama kali dipakai — memuat 2,2 MB
   foto di muka justru menghabiskan kuota orang untuk yang belum tentu
   dilihat. */
const KERANGKA = [
  '/',
  '/aset/inter.woff2',
  '/aset/fg.woff2',
  '/aset/logo.png',
  '/foto/hero.jpg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(INTI)
      .then((c) => c.addAll(KERANGKA))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((nama) => Promise.all(
        nama.filter((n) => !n.endsWith(VERSI)).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  const url = new URL(req.url);

  /* Hanya GET dari domain sendiri.

     /app SENGAJA dilewati sepenuhnya: itu aplikasi Apps Script yang alamat
     penyebarannya berganti tiap rilis. Menyajikan versi tersimpan di sana
     berarti anggota membuka aplikasi yang salah — jauh lebih merugikan
     daripada layar putih sekejap. */
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname === '/app' || url.pathname.startsWith('/app/')) return;

  /* Jadwal pertandingan harus sesegar mungkin; isi tersimpan cuma jaring
     pengaman saat jaringan mati. */
  if (url.pathname === '/jadwal.json') {
    e.respondWith(
      fetch(req)
        .then((r) => {
          const salinan = r.clone();
          caches.open(ISI).then((c) => c.put(req, salinan));
          return r;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  /* Sisanya: sajikan dari perangkat lebih dulu — itulah yang menghapus
     layar putih — lalu perbarui diam-diam untuk peluncuran berikutnya. */
  e.respondWith(
    caches.match(req).then((tersimpan) => {
      const jaringan = fetch(req)
        .then((r) => {
          if (r && r.ok && r.type === 'basic') {
            const salinan = r.clone();
            const wadah = KERANGKA.indexOf(url.pathname) >= 0 ? INTI : ISI;
            caches.open(wadah).then((c) => c.put(req, salinan));
          }
          return r;
        })
        .catch(() => tersimpan);
      return tersimpan || jaringan;
    })
  );
});
