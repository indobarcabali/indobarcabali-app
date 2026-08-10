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


def minta(url: str, kunci: str) -> dict:
    req = urllib.request.Request(url, headers={'X-Auth-Token': kunci})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def simpan_crest(tim: dict) -> str:
    """Unduh lambang satu tim kalau belum ada. Mengembalikan path relatifnya."""
    url = tim.get('crest')
    ident = tim.get('id')
    if not url or not ident:
        return ''
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
        kandang = (m.get('homeTeam', {}).get('id') == TIM)
        lawan = (m.get('awayTeam') if kandang else m.get('homeTeam')) or {}
        keluar.append({
            'utc': m.get('utcDate'),
            'lawan': lawan.get('shortName') or lawan.get('name') or '?',
            'crest': simpan_crest(lawan),
            'kandang': kandang,
            'kompetisi': (m.get('competition') or {}).get('name') or '',
        })
    return keluar


def ambil_klasemen(kunci: str) -> list:
    data = minta('https://api.football-data.org/v4/competitions/%s/standings' % LIGA, kunci)

    # Menjelang musim baru, endpoint ini masih mengembalikan tabel AKHIR musim
    # lalu — lengkap 38 pertandingan dan juaranya. Dipajang apa adanya, halaman
    # akan mengumumkan Barca juara dengan 94 poin padahal musimnya belum
    # dimulai. Karena itu musim yang sudah lewat tanggal akhirnya dibuang.
    musim = data.get('season') or {}
    habis = musim.get('endDate') or ''
    if habis and habis < datetime.date.today().isoformat():
        print('Klasemen dilewati: musim %s..%s sudah selesai.'
              % (musim.get('startDate'), habis))
        return []

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
            'crest': simpan_crest(tim),
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
        klasemen = ambil_klasemen(kunci)
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
