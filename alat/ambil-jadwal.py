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
JUMLAH = 5
AKAR = pathlib.Path(__file__).resolve().parent.parent
TUJUAN = AKAR / 'jadwal.json'
CREST = AKAR / 'crest'

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
        if len(keluar) >= JUMLAH:
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
            'kompetisi': NAMA_KOMPETISI.get(komp.get('name') or '', komp.get('name') or ''),
            'liga_lambang': simpan_lambang(komp.get('emblem'), komp.get('code') or komp.get('id'), 'liga-'),
        })
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


def main() -> None:
    kunci = os.environ.get('FOOTBALL_DATA_KEY', '').strip()
    if not kunci:
        sys.exit('FOOTBALL_DATA_KEY tidak diatur.')

    try:
        pertandingan = ambil_jadwal(kunci)
    except urllib.error.HTTPError as e:
        # Peringatan GitHub, bukan sekadar cetakan: kegagalan yang cuma
        # tercetak di log terlalu mudah luput karena langkahnya tetap hijau.
        print('::warning::Jadwal ditolak: HTTP %s %s' % (e.code, e.reason))
        return
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        print('::warning::Jadwal gagal diambil (%s). Berkas lama dibiarkan.' % e)
        return

    if not pertandingan:
        print('::warning::Tidak ada pertandingan mendatang. Berkas lama dibiarkan.')
        return

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
    main()
