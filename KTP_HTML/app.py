from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
DB_NAME = "kutuphane_yazilim.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ogrenciler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ogrenci_no TEXT UNIQUE,
            ad_soyad TEXT,
            nfc_uid TEXT UNIQUE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kitaplar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barkod TEXT UNIQUE,
            kitap_adi TEXT,
            yazar TEXT,
            stok INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS odunc (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ogrenci_id INTEGER,
            kitap_id INTEGER,
            verilis_tarihi TEXT,
            iade_tarihi TEXT,
            durum TEXT,
            FOREIGN KEY(ogrenci_id) REFERENCES ogrenciler(id),
            FOREIGN KEY(kitap_id) REFERENCES kitaplar(id)
        )
    """)

    # Örnek veriler
    cursor.execute(
        "INSERT OR IGNORE INTO ogrenciler (ogrenci_no, ad_soyad, nfc_uid) VALUES ('101', 'Ahmet Yılmaz', 'NFC001')")
    cursor.execute(
        "INSERT OR IGNORE INTO ogrenciler (ogrenci_no, ad_soyad, nfc_uid) VALUES ('102', 'Zeynep Demir', 'NFC002')")
    cursor.execute(
        "INSERT OR IGNORE INTO kitaplar (barkod, kitap_adi, yazar, stok) VALUES ('8681', 'Nutuk', 'Mustafa Kemal Atatürk', 2)")
    cursor.execute(
        "INSERT OR IGNORE INTO kitaplar (barkod, kitap_adi, yazar, stok) VALUES ('8682', 'Kürk Mantolu Madonna', 'Sabahattin Ali', 2)")

    conn.commit()
    conn.close()


init_db()


# ================= =================
#    SAYFA YÖNLENDİRME ROTALARI
# ================= =================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/admin')
def admin_paneli():
    return render_template('admin.html')


# ================= =================
#   ÖĞRENCİ VE BARKOD API ROTALARI
# ================= =================

@app.route('/api/ogrenci-sorgula', methods=['POST'])
def ogrenci_sorgula():
    data = request.json
    uid = data.get('uid', '').strip()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, ad_soyad, nfc_uid FROM ogrenciler WHERE nfc_uid = ?", (uid,))
    ogrenci = cursor.fetchone()
    conn.close()

    if ogrenci:
        return jsonify({'basarili': True, 'ogrenci': {'id': ogrenci[0], 'ad_soyad': ogrenci[1], 'nfc_uid': ogrenci[2]}})
    return jsonify({'basarili': False, 'mesaj': 'Tanınmayan öğrenci kartı!'})


@app.route('/api/barkod-sorgula', methods=['POST'])
def barkod_sorgula():
    data = request.json
    barkod = data.get('barkod', '').strip()
    ogrenci_id = data.get('ogrenci_id')

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, kitap_adi, stok FROM kitaplar WHERE barkod = ?", (barkod,))
    kitap = cursor.fetchone()

    if not kitap:
        conn.close()
        return jsonify({'basarili': False, 'mesaj': 'Bu barkoda ait kitap bulunamadı!'})

    kitap_id, kitap_adi, stok = kitap
    cursor.execute("SELECT id FROM odunc WHERE ogrenci_id = ? AND kitap_id = ? AND durum = 'Aktif'",
                   (ogrenci_id, kitap_id))
    aktif_kayit = cursor.fetchone()
    conn.close()

    if aktif_kayit:
        return jsonify(
            {'basarili': True, 'tip': 'iade', 'kitap_id': kitap_id, 'kitap_adi': kitap_adi, 'odunc_id': aktif_kayit[0]})
    else:
        if stok <= 0:
            return jsonify({'basarili': False, 'mesaj': f"'{kitap_adi}' adlı kitap stokta yok!"})
        return jsonify({'basarili': True, 'tip': 'odunc', 'kitap_id': kitap_id, 'kitap_adi': kitap_adi})


@app.route('/api/islemi-tamamla', methods=['POST'])
@app.route('/api/islemi-tamamla', methods=['POST'])
def islemi_tamamla():
    data = request.json
    ogrenci_id = data.get('ogrenci_id')
    sepet = data.get('sepet', [])

    if not sepet:
        return jsonify({'basarili': True, 'mesaj': 'İşlem yapılmadan oturum kapatıldı.'})

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    bugun = datetime.now()
    iade_tarihi_dt = bugun + timedelta(days=15)
    iade_tarihi = iade_tarihi_dt.strftime("%Y-%m-%d")
    iade_tarihi_formatli = iade_tarihi_dt.strftime("%d.%m.%Y")
    verilis_tarihi = bugun.strftime("%Y-%m-%d")

    try:
        odunc_var = False
        for item in sepet:
            if item['tip'] == 'odunc':
                cursor.execute(
                    "INSERT INTO odunc (ogrenci_id, kitap_id, verilis_tarihi, iade_tarihi, durum) VALUES (?, ?, ?, ?, 'Aktif')",
                    (ogrenci_id, item['kitap_id'], verilis_tarihi, iade_tarihi))
                cursor.execute("UPDATE kitaplar SET stok = stok - 1 WHERE id = ?", (item['kitap_id'],))
                odunc_var = True
            elif item['tip'] == 'iade':
                cursor.execute("UPDATE odunc SET durum = 'İade Edildi' WHERE id = ?", (item['odunc_id'],))
                cursor.execute("UPDATE kitaplar SET stok = stok + 1 WHERE id = ?", (item['kitap_id'],))

        conn.commit()
        conn.close()

        if odunc_var:
            mesaj = f"İşlem tamamlandı! Son İade Tarihi: {iade_tarihi_formatli}"
        else:
            mesaj = "İade işlemi başarıyla tamamlandı!"

        return jsonify({'basarili': True, 'mesaj': mesaj, 'iade_tarihi': iade_tarihi_formatli})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'basarili': False, 'mesaj': f'Hata oluştu: {str(e)}'})


# ================= =================
#      ADMİN PANELİ API ROTALARI
# ================= =================

@app.route('/api/kitap-ekle', methods=['POST'])
def kitap_ekle():
    data = request.json
    barkod = data.get('barkod', '').strip()
    kitap_adi = data.get('kitap_adi', '').strip()
    yazar = data.get('yazar', '').strip()
    stok = data.get('stok', 1)

    if not barkod or not kitap_adi:
        return jsonify({'basarili': False, 'mesaj': 'Barkod dan kitap adı zorunludur!'})

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO kitaplar (barkod, kitap_adi, yazar, stok)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(barkod) DO UPDATE SET 
            kitap_adi = excluded.kitap_adi,
            yazar = excluded.yazar,
            stok = stok + excluded.stok
        """, (barkod, kitap_adi, yazar, int(stok)))

        conn.commit()
        conn.close()
        return jsonify({'basarili': True, 'mesaj': f"'{kitap_adi}' başarıyla eklendi / güncellendi!"})
    except Exception as e:
        conn.close()
        return jsonify({'basarili': False, 'mesaj': f'Hata oluştu: {str(e)}'})


@app.route('/api/kitap-sil', methods=['POST'])
def kitap_sil():
    data = request.json
    kitap_id = data.get('id')

    if not kitap_id:
        return jsonify({'basarili': False, 'mesaj': 'Kitap ID eksik!'})

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        # Bağlı ödünç kayıtlarını temizle (çakışma önlemek için)
        cursor.execute("DELETE FROM odunc WHERE kitap_id = ?", (kitap_id,))
        # Kitabı sil
        cursor.execute("DELETE FROM kitaplar WHERE id = ?", (kitap_id,))

        conn.commit()
        conn.close()
        return jsonify({'basarili': True, 'mesaj': 'Kitap başarıyla silindi.'})
    except Exception as e:
        conn.close()
        return jsonify({'basarili': False, 'mesaj': f'Silme hatası: {str(e)}'})


@app.route('/api/tum-kitaplar', methods=['GET'])
def tum_kitaplar():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, barkod, kitap_adi, yazar, stok FROM kitaplar")
    kitaplar = cursor.fetchall()
    conn.close()

    liste = []
    for k in kitaplar:
        liste.append({
            'id': k[0],
            'barkod': k[1],
            'kitap_adi': k[2],
            'yazar': k[3],
            'stok': k[4]
        })
    return jsonify({'basarili': True, 'kitaplar': liste})


if __name__ == '__main__':
    app.run(debug=True)
