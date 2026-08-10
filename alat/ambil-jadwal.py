#!/usr/bin/env python3
"""
Mengambil jadwal pertandingan dan klasemen dari football-data.org, lalu
menuliskannya ke jadwal.json beserta lambang tim ke folder crest/.

Dijalankan GitHub Actions, BUKAN dari peramban pengunjung — dengan begitu
kunci API tersimpan sebagai rahasia repo dan tidak pernah sampai ke publik.

Keluarannya berkas terpisah, sengaja TIDAK menyunting index.html: halaman itu
disalin dari repo aplikasi setiap kali ada perubahan, jadi suntingan otomatis
di sana akan tertimpa tanpa disadari.

Lambang tim ikut diunduh, bukan ditaut ke server football-data.org: halaman
ini sudah menanam font dan fotonya sendiri supaya tidak bergantung pada host
lain saat dibuka, dan lambang tidak perlu jadi pengecualian.

Kalau pengambilan gagal, berkas lama DIBIARKAN apa adanya. Halaman sudah
menyembunyikan pertandingan yang tanggalnya lewat, jadi berkas basi akan
mengosongkan diri sendiri — jauh lebih baik daripada menimpanya dengan
daftar kosong setiap kali API sedang bermasalah.
"""
import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

TIM = 81          # FC Barcelona
LIGA = 'PD'       # Primera Division — termasuk paket gratis football-data.org
JUMLAH = 5        # jumlah AKHIR yang ditulis ke jadwal.json
CALON = 10        # kandidat internal sebelum digabung+diurut+dipotong ke JUMLAH
AKAR = pathlib.Path(__file__).resolve().parent.parent
TUJUAN = AKAR / 'jadwal.json'
CREST = AKAR / 'crest'

# --- Sumber kedua: TheSportsDB, mengisi yang TIDAK ADA di paket gratis
# football-data.org — Copa del Rey, Supercopa de España, laga persahabatan.
# Dipastikan lewat pengujian langsung, bukan dokumentasi: paket gratis
# football-data.org terbukti TIDAK mengembalikan laga-laga itu sama sekali.
#
# Kunci "3" adalah kunci UJI publik TheSportsDB, dibagi bersama semua
# pengguna gratis — bukan kunci produksi. Karena itu sumber ini best-effort
# murni: dibungkus try/except Exception yang luas (bukan jenis per-jenis
# seperti football-data di bawah), dan kegagalannya TIDAK PERNAH menjatuhkan
# keseluruhan pengambilan. football-data.org tetap sumber utama.
TSDB_TIM = 133739   # id FC Barcelona di TheSportsDB
TSDB_KUNCI = '3'
TSDB_WAKTU = 10     # detik — pendek: sumber opsional tidak boleh menyandera Action

# Daftar IZIN, bukan daftar larang: hanya liga di sini yang diterima dari
# TheSportsDB. LaLiga dan Liga Champions SENGAJA tidak masuk — itu sudah
# ditangani football-data.org dengan data lebih kaya (matchday, TLA resmi),
# dan mengizinkannya di sini berisiko menduplikasi laga yang sama dari dua
# sumber sekaligus.
TSDB_KOMPETISI = {
    'Club Friendlies': 'Laga Persahabatan',
    'Copa del Rey': 'Copa del Rey',
    'Supercopa de Espana': 'Supercopa',
    'UEFA Super Cup': 'Piala Super Eropa',
    'FIFA Club World Cup': 'Piala Dunia Antarklub',
}

# football-data.org menandai pertandingan yang jam mainnya sudah pasti sebagai
# TIMED dan yang belum pasti sebagai SCHEDULED — menyaring salah satunya saja
# membuat hasil kosong padahal datanya ada.
SELESAI = {'FINISHED', 'AWARDED', 'CANCELLED', 'POSTPONED', 'SUSPENDED'}

# Nama resmi di API bukan nama yang dikenal orang. 'Primera Division' itu nama
# administratif; yang tertera di lambang dan disebut suporter adalah LaLiga.
NAMA_KOMPETISI = {
    'Primera Division': 'LaLiga',
    'Primera División': 'LaLiga',
    'UEFA Champions League': 'Champions League',
    'Copa del Rey': 'Copa del Rey',
    'Supercopa de Espana': 'Supercopa',
    'Supercopa de España': 'Supercopa',
}

# Nama babak yang dipakai suporter, bukan konstanta API. Sengaja pendek: label
# ini muncul di baris jadwal yang sempit, di samping jam.
BABAK_TETAP = {
    'PRELIMINARY': 'Kualifikasi', 'QUALIFICATION': 'Kualifikasi',
    'PLAYOFFS': 'Playoff', 'PLAY_OFF_ROUND': 'Playoff', 'PLAYOFF_ROUND_1': 'Playoff',
    'LAST_32': '32 Besar', 'ROUND_OF_32': '32 Besar',
    'LAST_16': '16 Besar', 'ROUND_OF_16': '16 Besar',
    'QUARTER_FINALS': 'Perempat Final', 'SEMI_FINALS': 'Semifinal',
    'THIRD_PLACE': 'Perebutan Tempat Ketiga', 'FINAL': 'Final',
}


def minta(url: str, kunci: str) -> dict:
    req = urllib.request.Request(url, headers={'X-Auth-Token': kunci})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def simpan_lambang(url: str, ident, awalan: str = '') -> str:
    """Unduh satu lambang kalau belum ada. Mengembalikan path relatifnya."""
    if not url or not ident:
        return ''
    ident = '%s%s' % (awalan, ident)
    ext = '.svg' if url.lower().endswith('.svg') else '.png'
    nama = '%s%s' % (ident, ext)
    berkas = CREST / nama
    if berkas.exists():                       # lambang klub praktis tak berubah
        return 'crest/' + nama
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            isi = r.read()
        if not isi:
            return ''
        CREST.mkdir(exist_ok=True)
        berkas.write_bytes(isi)
        print('  lambang baru: %s (%d B)' % (nama, len(isi)))
        return 'crest/' + nama
    except Exception as e:                    # lambang gagal bukan alasan gagal total
        print('  lambang %s gagal: %s' % (ident, e))
        return ''


def babak_dari(m: dict) -> str:
    """Label babak yang siap dicetak: 'Jornada 3', 'Grup C', 'Perempat Final'.

    Dirakit di sini, bukan di halaman, supaya aturan penamaan hidup di satu
    tempat bersama NAMA_KOMPETISI — dan supaya nama babak kompetisi gugur tidak
    perlu ditebak dari nomor pekan yang memang tidak ada di sana.
    """
    tahap = (m.get('stage') or '').upper()
    pekan = m.get('matchday')
    if tahap in ('', 'REGULAR_SEASON'):
        return 'Jornada %s' % pekan if pekan else ''
    if tahap == 'LEAGUE_STAGE':                    # format Liga Champions baru
        return 'Fase Liga %s' % pekan if pekan else 'Fase Liga'
    if tahap == 'GROUP_STAGE':
        grup = (m.get('group') or '').replace('GROUP_', '').strip()
        return ('Grup %s' % grup) if grup else 'Fase Grup'
    if tahap in BABAK_TETAP:
        return BABAK_TETAP[tahap]
    if tahap.startswith('ROUND_'):                 # Copa del Rey: ROUND_1..ROUND_5
        return 'Babak ' + tahap.rsplit('_', 1)[-1]
    return tahap.replace('_', ' ').title()


def sisi_tim(tim: dict) -> dict:
    """Satu tim seperti yang dipakai kartu jadwal: nama, singkatan, lambang.

    `tla` ikut disertakan supaya halaman punya pilihan untuk nama yang terlalu
    panjang bagi kartu sempit di ponsel ("Real Valladolid" -> "VLL"). Singkatan
    ini datang dari football-data.org, bukan karangan sendiri — jadi yang tampil
    adalah singkatan resmi yang memang dipakai orang.
    """
    return {
        'nama': tim.get('shortName') or tim.get('name') or '?',
        'tla': tim.get('tla') or '',
        'crest': simpan_lambang(tim.get('crest'), tim.get('id')),
    }


def ambil_jadwal(kunci: str) -> list:
    hari_ini = datetime.date.today()
    data = minta('https://api.football-data.org/v4/teams/%d/matches'
                 '?dateFrom=%s&dateTo=%s'
                 % (TIM, hari_ini, hari_ini + datetime.timedelta(days=90)), kunci)
    semua = data.get('matches', [])
    print('Jadwal: API mengembalikan %d pertandingan dalam 90 hari.' % len(semua))
    if semua:
        ragam = {}
        for m in semua:
            ragam[m.get('status')] = ragam.get(m.get('status'), 0) + 1
        print('  status yang ada: %s' % ragam)

    keluar = []
    for m in sorted(semua, key=lambda x: x.get('utcDate') or ''):
        if m.get('status') in SELESAI:
            continue
        if len(keluar) >= CALON:   # dipotong ke JUMLAH setelah digabung dgn TSDB
            break
        rumah = m.get('homeTeam') or {}
        tamu = m.get('awayTeam') or {}
        komp = m.get('competition') or {}
        kandang = (rumah.get('id') == TIM)
        lawan = tamu if kandang else rumah
        keluar.append({
            'utc': m.get('utcDate'),
            # Kedua tim disimpan utuh dan berurutan, bukan cuma "lawan":
            # tata letaknya menampilkan tuan rumah di kiri dan tamu di kanan,
            # dan urutan itu tidak bisa dipulihkan dari satu nama saja.
            'home': sisi_tim(rumah),
            'away': sisi_tim(tamu),
            'kandang': kandang,
            'lawan': lawan.get('shortName') or lawan.get('name') or '?',
            'matchday': m.get('matchday'),
            'babak': babak_dari(m),
            # Kadang tidak dikirim paket gratis; halaman menyembunyikan
            # barisnya sendiri kalau kosong, bukan mencetak tempat kosong.
            'venue': m.get('venue') or '',
            'kompetisi': NAMA_KOMPETISI.get(komp.get('name') or '', komp.get('name') or ''),
            'liga_lambang': simpan_lambang(komp.get('emblem'), komp.get('code') or komp.get('id'), 'liga-'),
        })
    return keluar


def ambil_jadwal_tsdb() -> list:
    """Laga di luar LaLiga/UCL: Copa del Rey, Supercopa, laga persahabatan.

    Best-effort murni — lihat catatan di TSDB_TIM di atas. Kegagalan apa pun
    (jaringan, format tak terduga, rate limit) menghasilkan daftar kosong,
    tidak pernah exception yang menjatuhkan pengambilan football-data.
    """
    try:
        url = ('https://www.thesportsdb.com/api/v1/json/%s/eventsnext.php'
               '?id=%d' % (TSDB_KUNCI, TSDB_TIM))
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=TSDB_WAKTU) as r:
            data = json.load(r)
        acara = data.get('events') or []
        print('TheSportsDB: %d acara mendatang.' % len(acara))
    except Exception as e:
        print('::warning::TheSportsDB gagal diambil (%s). Dilewati.' % e)
        return []

    def sisi(nama, ident, badge):
        return {
            'nama': nama or '?',
            'tla': '',   # TheSportsDB tidak menyediakan singkatan resmi
            'crest': simpan_lambang(badge, ident, 'tsdb'),
        }

    keluar = []
    for acr in acara:
        liga = acr.get('strLeague') or ''
        if liga not in TSDB_KOMPETISI:
            continue   # di luar daftar izin — termasuk menolak LaLiga/UCL
        utc = acr.get('strTimestamp')
        if not utc:
            continue
        try:
            babak = ''
            ronde = acr.get('intRound')
            if ronde and str(ronde).isdigit() and int(ronde) > 0:
                babak = 'Babak %s' % ronde
            keluar.append({
                'utc': utc.replace(' ', 'T') + ('Z' if not utc.endswith('Z') else ''),
                'home': sisi(acr.get('strHomeTeam'), acr.get('idHomeTeam'), acr.get('strHomeTeamBadge')),
                'away': sisi(acr.get('strAwayTeam'), acr.get('idAwayTeam'), acr.get('strAwayTeamBadge')),
                'kandang': str(acr.get('idHomeTeam')) == str(TSDB_TIM),
                'matchday': None,
                'babak': babak,
                'venue': acr.get('strVenue') or '',
                'kompetisi': TSDB_KOMPETISI[liga],
                'liga_lambang': simpan_lambang(acr.get('strLeagueBadge'), acr.get('idLeague'), 'tsdb-liga-'),
            })
        except Exception as err:  # satu acara aneh tidak boleh menjatuhkan yang lain
            print('  acara TheSportsDB dilewati (%s): %s' % (err, acr.get('strEvent')))
    return keluar


def musim_dari(tanggal_iso: str) -> int:
    """Tahun awal musim untuk satu tanggal. Musim Eropa mulai Juli/Agustus,
    jadi laga Januari 2027 masih milik musim 2026."""
    t = datetime.date.fromisoformat(tanggal_iso[:10])
    return t.year if t.month >= 7 else t.year - 1


def ambil_klasemen(kunci: str, musim: int) -> list:
    # Musimnya DIMINTA secara tegas, tidak dibiarkan menjadi default. Tanpa
    # parameter ini, menjelang musim baru endpoint tetap mengembalikan tabel
    # AKHIR musim lalu — lengkap 38 pertandingan dan juaranya — sehingga
    # halaman mengumumkan Barca juara 94 poin padahal musimnya belum dimulai.
    # Percobaan sebelumnya menyaring lewat season.endDate dan gagal, karena
    # isi lapangan itu ternyata tidak seperti dugaan. Meminta musim yang sama
    # dengan jadwalnya tidak bergantung pada tafsiran apa pun.
    data = minta('https://api.football-data.org/v4/competitions/%s/standings'
                 '?season=%d' % (LIGA, musim), kunci)
    m = data.get('season') or {}
    print('Klasemen: musim diminta %d, dilaporkan %s..%s, matchday %s'
          % (musim, m.get('startDate'), m.get('endDate'), m.get('currentMatchday')))

    blok = None
    for s in data.get('standings', []):
        if s.get('type') == 'TOTAL':
            blok = s
            break
    baris = (blok or {}).get('table', [])
    print('Klasemen: %d tim.' % len(baris))
    if baris and not any((b.get('playedGames') or 0) > 0 for b in baris):
        print('Klasemen dilewati: belum ada pertandingan dimainkan.')
        return []

    keluar = []
    for b in baris:
        tim = b.get('team') or {}
        keluar.append({
            'pos': b.get('position'),
            'tim': tim.get('shortName') or tim.get('name') or '?',
            'crest': simpan_lambang(tim.get('crest'), tim.get('id')),
            'main': b.get('playedGames'),
            'sg': b.get('goalDifference'),
            'poin': b.get('points'),
            'kami': tim.get('id') == TIM,
        })
    return keluar


def uji_babak() -> None:
    """`python3 alat/ambil-jadwal.py --uji` — tidak menyentuh jaringan."""
    kasus = [
        ({'stage': 'REGULAR_SEASON', 'matchday': 3}, 'Jornada 3'),
        ({'stage': None, 'matchday': 7}, 'Jornada 7'),
        ({'stage': 'REGULAR_SEASON', 'matchday': None}, ''),
        ({'stage': 'LEAGUE_STAGE', 'matchday': 1}, 'Fase Liga 1'),
        ({'stage': 'GROUP_STAGE', 'group': 'GROUP_C', 'matchday': 2}, 'Grup C'),
        ({'stage': 'GROUP_STAGE', 'matchday': 2}, 'Fase Grup'),
        ({'stage': 'LAST_16'}, '16 Besar'),
        ({'stage': 'QUARTER_FINALS'}, 'Perempat Final'),
        ({'stage': 'FINAL'}, 'Final'),
        ({'stage': 'ROUND_3'}, 'Babak 3'),
        ({'stage': 'SOMETHING_NEW'}, 'Something New'),
    ]
    for masuk, harap in kasus:
        keluar = babak_dari(masuk)
        assert keluar == harap, '%r -> %r, seharusnya %r' % (masuk, keluar, harap)
    print('uji babak: %d kasus lolos.' % len(kasus))


def main() -> None:
    kunci = os.environ.get('FOOTBALL_DATA_KEY', '').strip()
    if not kunci:
        sys.exit('FOOTBALL_DATA_KEY tidak diatur.')

    try:
        dari_fd = ambil_jadwal(kunci)
    except urllib.error.HTTPError as e:
        # Peringatan GitHub, bukan sekadar cetakan: kegagalan yang cuma
        # tercetak di log terlalu mudah luput karena langkahnya tetap hijau.
        print('::warning::Jadwal ditolak: HTTP %s %s' % (e.code, e.reason))
        return
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print('::warning::Jadwal gagal diambil (%s). Berkas lama dibiarkan.' % e)
        return

    # TheSportsDB murni tambahan: gagal pun football-data.org tetap terbit.
    dari_tsdb = ambil_jadwal_tsdb()

    # Digabung lalu diurut ulang berdasarkan tanggal — hero harus menampilkan
    # laga paling dekat LINTAS SEMUA KOMPETISI, bukan cuma LaLiga/UCL.
    # Dedup HANYA berdasarkan tanggal kalender (UTC): Barça tidak pernah main
    # dua kali di hari yang sama, jadi ini aman dan tidak bergantung pada
    # kecocokan nama tim yang bisa berbeda ejaan antar API. football-data.org
    # diproses lebih dulu supaya jika bentrok, datanya yang lebih kaya
    # (matchday, TLA resmi) yang dipertahankan.
    tanggal_terpakai = set()
    pertandingan = []
    for p in dari_fd + dari_tsdb:
        tgl = (p.get('utc') or '')[:10]
        if not tgl or tgl in tanggal_terpakai:
            if tgl:
                print('  dilewati (bentrok tanggal %s): %s' % (tgl, p.get('kompetisi')))
            continue
        tanggal_terpakai.add(tgl)
        pertandingan.append(p)
    pertandingan.sort(key=lambda x: x['utc'])
    pertandingan = pertandingan[:JUMLAH]

    if not pertandingan:
        print('::warning::Tidak ada pertandingan mendatang. Berkas lama dibiarkan.')
        return
    print('Gabungan: %d dari football-data, %d dari TheSportsDB, %d setelah dedup+potong.'
          % (len(dari_fd), len(dari_tsdb), len(pertandingan)))

    # Klasemen boleh gagal sendiri tanpa menjatuhkan jadwal: kompetisi bisa
    # sedang jeda, atau paketnya tidak mencakup liga ini.
    try:
        klasemen = ambil_klasemen(kunci, musim_dari(pertandingan[0]['utc']))
    except Exception as e:
        print('::warning::Klasemen gagal diambil (%s). Jadwal tetap diperbarui.' % e)
        klasemen = []

    isi = {'pertandingan': pertandingan}
    if klasemen:
        isi['klasemen'] = klasemen

    baru = json.dumps(isi, ensure_ascii=False, indent=2) + '\n'
    lama = TUJUAN.read_text() if TUJUAN.exists() else ''
    if baru == lama:
        print('Tidak ada perubahan.')
        return

    TUJUAN.write_text(baru)
    print('Diperbarui: %d pertandingan, %d baris klasemen.' % (len(pertandingan), len(klasemen)))


if __name__ == '__main__':
    if '--uji' in sys.argv:
        uji_babak()
    else:
        main()
