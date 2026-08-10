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
import datetime
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


# Sengaja TIDAK memakai status=SCHEDULED. football-data.org menandai
# pertandingan yang jam mainnya sudah pasti sebagai TIMED, dan yang jadwalnya
# belum pasti sebagai SCHEDULED — menyaring salah satunya saja membuat hasil
# kosong padahal datanya ada. Yang dipakai rentang tanggal, lalu yang sudah
# usai disaring di sini.
SELESAI = {'FINISHED', 'AWARDED', 'CANCELLED', 'POSTPONED', 'SUSPENDED'}


def ambil(kunci: str) -> list:
    hari_ini = datetime.date.today()
    url = ('https://api.football-data.org/v4/teams/%d/matches'
           '?dateFrom=%s&dateTo=%s' % (TIM, hari_ini, hari_ini + datetime.timedelta(days=90)))
    req = urllib.request.Request(url, headers={'X-Auth-Token': kunci})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)

    semua = data.get('matches', [])
    print('API mengembalikan %d pertandingan dalam 90 hari ke depan.' % len(semua))
    if semua:
        dilihat = {}
        for m in semua:
            dilihat[m.get('status')] = dilihat.get(m.get('status'), 0) + 1
        print('  status yang ada: %s' % dilihat)

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
    except urllib.error.HTTPError as e:
        # Peringatan GitHub, bukan sekadar cetakan: kegagalan yang cuma
        # tercetak di log terlalu mudah luput karena langkahnya tetap hijau.
        print('::warning::football-data.org menolak: HTTP %s %s' % (e.code, e.reason))
        try:
            print('  balasan: %s' % e.read().decode()[:300])
        except Exception:
            pass
        return
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        # Sengaja keluar 0: kegagalan API bukan kegagalan build. Berkas lama
        # tetap dipakai, dan halaman menyaring yang sudah lewat sendiri.
        print('::warning::Gagal mengambil jadwal (%s). Berkas lama dibiarkan.' % e)
        return

    if not pertandingan:
        print('::warning::Tidak ada pertandingan mendatang yang bisa dipakai. '
              'Berkas lama dibiarkan.')
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
