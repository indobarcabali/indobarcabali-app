#!/usr/bin/env python3
"""
Mengambil jadwal pertandingan FC Barcelona berikutnya dari football-data.org
dan menuliskannya ke jadwal.json.

Dijalankan GitHub Actions, BUKAN dari peramban pengunjung — dengan begitu
kunci API tersimpan sebagai rahasia repo dan tidak pernah sampai ke publik.

Keluarannya berkas terpisah, sengaja TIDAK menyunting index.html: halaman itu
disalin dari repo aplikasi setiap kali ada perubahan, jadi suntingan otomatis
di sana akan tertimpa tanpa disadari.

Kalau pengambilan gagal, berkas lama DIBIARKAN apa adanya. Halaman sudah
menyembunyikan pertandingan yang tanggalnya lewat, jadi berkas basi akan
mengosongkan diri sendiri — jauh lebih baik daripada menimpanya dengan
daftar kosong setiap kali API sedang bermasalah.
"""
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

TIM = 81          # FC Barcelona
JUMLAH = 5
AKAR = pathlib.Path(__file__).resolve().parent.parent
TUJUAN = AKAR / 'jadwal.json'


def ambil(kunci: str) -> list:
    url = ('https://api.football-data.org/v4/teams/%d/matches'
           '?status=SCHEDULED&limit=%d' % (TIM, JUMLAH))
    req = urllib.request.Request(url, headers={'X-Auth-Token': kunci})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)

    keluar = []
    for m in data.get('matches', []):
        kandang = (m.get('homeTeam', {}).get('id') == TIM)
        lawan = (m.get('awayTeam') if kandang else m.get('homeTeam')) or {}
        keluar.append({
            'utc': m.get('utcDate'),
            'lawan': lawan.get('shortName') or lawan.get('name') or '?',
            'kandang': kandang,
            'kompetisi': (m.get('competition') or {}).get('name') or '',
        })
    return keluar


def main() -> None:
    kunci = os.environ.get('FOOTBALL_DATA_KEY', '').strip()
    if not kunci:
        sys.exit('FOOTBALL_DATA_KEY tidak diatur.')

    try:
        pertandingan = ambil(kunci)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as e:
        # Sengaja keluar 0: kegagalan API bukan kegagalan build. Berkas lama
        # tetap dipakai, dan halaman menyaring yang sudah lewat sendiri.
        print('Gagal mengambil jadwal (%s). Berkas lama dibiarkan.' % e)
        return

    if not pertandingan:
        print('API tidak mengembalikan pertandingan. Berkas lama dibiarkan.')
        return

    baru = json.dumps({'pertandingan': pertandingan}, ensure_ascii=False, indent=2) + '\n'
    lama = TUJUAN.read_text() if TUJUAN.exists() else ''
    if baru == lama:
        print('Jadwal tidak berubah.')
        return

    TUJUAN.write_text(baru)
    print('Jadwal diperbarui: %d pertandingan.' % len(pertandingan))
    for p in pertandingan:
        print('  %s  %s %s  (%s)' % (
            p['utc'], 'vs' if p['kandang'] else 'di kandang', p['lawan'], p['kompetisi']))


if __name__ == '__main__':
    main()
