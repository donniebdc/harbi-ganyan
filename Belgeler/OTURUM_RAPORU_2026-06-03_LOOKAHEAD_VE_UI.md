# Oturum Raporu — 2026-06-03 (Look-ahead düzeltmesi + Backtest doğrulama + UI detayları)

Bu belge bu oturumda yapılan TÜM işleri yarınki ofis oturumuna eksiksiz aktarır.
Branch: `analiz/altili-aktarim-optim`. VPS: `root@141.98.115.217`. Backend port **8001**.

---

## 0. Bağlam / kaynak doğrusu
- **Lokal = kaynak doğrusu.** Her değişiklik lokalde yapıldı, GitHub'a push edildi,
  oradan VPS'e dağıtıldı. Yarın ofiste: `git fetch && git checkout analiz/altili-aktarim-optim && git pull`.
- VPS yalnız çalışan backend (`/opt/harbi_ganyan_backend`) + engine (`/opt/harbi_ganyan_engine`).
- İlgili önceki belgeler: `LOOKAHEAD_BULGU_VE_DUZELTME_2026-06-03.md`,
  `CANLI_TAKIP_SISTEMI_2026-06-03.md`, `ALTILI_FARK_ANALIZI_2026-06-03.md`.

---

## 1. KRİTİK: Look-ahead (geleceği görme) bulgusu ve düzeltmesi  (commit `ad63a55`)

### Sorun
Canlı takip gün içinde **tüm günü** yeniden üretiyordu (`run_full`, force Pegadrom).
Pegadrom `ai-analiz` sayfaları CANLI: koşu bitince atların **Form** dizisine gerçek
varış derecesi eklenir, **Yarış Akışı** gerçek varışa göre kısmen yeniden dizilir.
Akış ANA skorunda ~0.50 ağırlık taşıdığından, **koşulmuş koşular koşu-sonrası veriyle
yeniden analiz edilince gerçek kazanan favori oluyordu** (Elazığ 06-03 4. koşu: #5
YAĞIZALP koşu öncesi akış-rank 10/favori değil → koşu sonrası akış-rank 1/FAV/ANA 106).

### Çözüm — bir koşu BAŞLADIKTAN sonra analizi hiçbir katmanda değişmez
- **G1** (`motor/pegadrom_ai_txt_topla.py` → `collect_range(..., skip=set)`): `force=True`
  olsa bile `skip` setindeki (başlamış) koşuların TXT'si KORUNUR. Koşu-sonrası akış motora
  girmez. Skip seti `daily_pipeline._baslamis_kosu_skip(iso)` ile DB'den hesaplanır
  (`(HIP_ASCII_UPPER, kno)`; Elazığ→ELAZIG eşlemesi `fold().upper()`).
- **G2** (`backend/export/import_to_db.py` → `import_payload(db, payload, freeze=True, now_tr=None)`):
  zaman-bazlı dondurmalı **birleştirme** (delete-and-rewrite YERİNE):
  - Şehir ilk koşu **−30 dk** → o şehrin 5-satır (`kosu_bes`) + altılı analizi DONAR.
  - Her koşu **−5 dk** → o koşunun alt-bahis (`kosu_bahis`) analizi DONAR.
  - Sonuç alanları (kazanan/ganyan/ikramiye/tuttu/net) HER ZAMAN güncellenir.
  - `freeze=False` → bilinçli replay (tam yeniden-yazım): manuel `--uret`, `--export-only`,
    `import_to_db` CLI.
  - Eşikler: `LOCK_5SAT_DK=30`, `LOCK_ALT_DK=5`.
- **daily_pipeline**: `run_full(..., freeze=True)` skip seti + freeze; `export_import(isos,
  freeze=True)`; canlı takip gün-seviyesi penceresi **R−10dk → R−30dk** (bu noktadan sonra
  5-satır/6'lı yeniden üretilmez/bildirilmez). `--results-only`/`--live` artık `freeze=True`
  → sonuç-tazeleme analizi değiştirmez, yalnız sonuç akıtır.

### Doğrulama (VPS, izole rollback işlemleri)
| Senaryo | 5-satır | alt-bahis | sonuç |
|---|---|---|---|
| Koşu sonrası (freeze) | DONUK | DONUK | akıyor |
| Koşu öncesi (R−30 önce) | tazeleniyor | tazeleniyor | akıyor |
| Şehir kilitli + geç koşu (−5dk gelmedi) | DONUK | GÜNCELLENİYOR | akıyor |
| Replay (freeze=False) | yeniden-yazım | yeniden-yazım | akıyor |

Cron her tetiklenmede taze python başlatır → bir sonraki tick'te yeni kod devrede.

---

## 2. Backtest doğrulaması — SONUÇ KULLANILMADI (kanıtlı)
Motorun sonuçla ilintili tek girdisi akış (form motorda kullanılmıyor). 2032 koşuda:

| Sinyal | Kazananın ort. sırası (1=kâhin, rastgele=5.44) | Rank-1 kazanma |
|---|---|---|
| AKIŞ (koşu-sonrası, şüpheli) | **3.07** | %31.7 |
| AGF (TEMİZ koşu-öncesi piyasa) | **2.93** | %36.1 |
| ANA (motor) | 2.77 | %37.4 |

**Akış, temiz AGF'den DAHA KÖTÜ tahmin ediyor** → oracle değil, sonuç kullanılmamış.
Başarı sayıları şişirilmemiş.

### Gerçek başarı sayıları (tüm arşiv)
- **5-satır:** FAV=kazanan **%37.5** (764/2040); kazanan-5-satır-içinde **%89.3** (1822/2040).
- **6'lı (DB, 2026-02-01..06-04, 453 sonuçlanmış kupon):** en az bir kademe 6/6 = **142 (%31)**;
  kademe 6/6: Ortaklı 142, Harbi 119, Simitçi 74. Dağılım `6→142,5→172,4→110,3→23,2→6`.
  Gradyan (Simitçi<Harbi<Ortaklı) sağlıklı.

> Altın standart = ileriye dönük (forward) temiz test. G1 dondurma sayesinde artık her gün
> koşu-öncesi Pegadrom donuyor; birkaç hafta sonra %X sıfır şüpheyle verilebilir.

---

## 3. UI / içerik detayları  (commit sonrası, branch'te)

1. **5-satır jokey adı:** at adının altına kısa jokey adı (API `jockey.name`, ör. "A.H.BAYAR").
   Apranti ise " (ap)" + turkuaz. Boşsa satır yok.
2. **5-satır koşu tipi:** bilgi satırına `typeDescription` (ör. "ŞARTLI 5", "Maiden/DHÖW").
3. **6'lı blok:** `"{kno}. AYAK"` → `"{kno}. KOŞU"` (yanlış ayak-indeksi etiketi düzeltildi).
4. **Turkuaz ikramiyeler:** sonucu açıklanan 6'lı header ikramiyesi + alt-bahis İKRAMİYE
   satırı `HG.camgobegi`.
5. **İstatistik:** "5 Satır Tahmin" turkuaz; altındaki "X / Y koşu isabet" sarı (`HG.altin`).
6. **Bildirim çanı:** okunmamış varsa turkuaz + dolu çan (`notifications_active`); sayfaya
   girince tüm bildirimler okundu işaretlenir (`POST /auth/bildirimler/okundu-hepsi`) →
   ana ekrana dönünce beyaz.

### Veri zinciri (jokey + koşu tipi)
`ganyan_master.py` (ATNO satırına `|JAD:<kısa>|JAP:<0/1>`, KO satırına p[10]=`ktip`) →
`motor/kupon_kacan_analiz._parse_one` (atlar'a `jokey`/`apranti`) →
`build_day_json` (meta `ktip`; bes `jokey`/`apranti`; kosu `ktip`) →
`serialize.kosu_payload` → `models.dart` (Bes.jokey/apranti, Kosu.ktip) →
`kosu_karti.dart`. DB: `kosu.ktip`, `kosu_bes.jokey`, `kosu_bes.apranti` (idempotent ALTER).

> Not: jokey/ktip yalnız YENİ üretimlerde dolar (geçmiş günler donuk; yeniden üretilmez).
> 2026-06-04 yeni motorla üretildi ve DB'de doğrulandı (ktip='ŞARTLI 5', jokey='E.ÇİZİK' vb.).

### Değişen dosyalar (bu batch)
Engine: `ganyan_master.py`, `motor/kupon_kacan_analiz.py`.
Backend: `export/build_day_json.py`, `export/import_to_db.py`, `app/serialize.py`,
`app/models.py`, `app/api/auth.py`.
Mobil: `api/models.dart`, `api/client.dart`, `state/content.dart`, `screens/home.dart`,
`screens/bildirimler.dart`, `screens/istatistik.dart`, `screens/kosu_analizleri.dart`,
`widgets/kosu_karti.dart`, `widgets/altili_karti.dart`. `pubspec.yaml` 1.0.11+12 → **1.0.12+13**.

---

## 4. VPS deploy durumu
- Dağıtılan dosyalar: yukarıdaki engine+backend dosyaları (`/tmp/*.bak` yedekleri var).
- **Migration uygulandı:** `kosu.ktip`, `kosu_bes.jokey`, `kosu_bes.apranti` (ensure_schema ALTER).
- **Backend restart edildi** (yeni ORM + `/auth/bildirimler/okundu-hepsi`). `/gunler` OK.
- **Sahiplik düzeltmesi (ÖNEMLİ):** `/opt/harbi_ganyan_engine` ve `/opt/harbi_ganyan_backend`
  bazı dizinleri eski root çalıştırmalarından root sahipliydi → `chown -R harbiganyan` yapıldı.
  (Belirti: daily.service "Permission denied" Tahminler.txt / out/*.json yazarken.)
- 2026-06-04 yeni motorla yeniden üretildi (jokey/ktip dolu).

---

## 5. Sonuç-zamanlaması (kullanıcı maddesi — zaten karşılanıyor)
`_bekleyen_var` koşu **+2 dk**'da poll'a başlıyor; live timer her 2 dk. Gecikme bizde değil,
TJK resmi `full/<KEY>.json` ganyan(ikramiye) feed'inin ~10-15 dk gecikmesinde
(`_bekleyen_var` `ganyan is None`'a takılı). Daha erken "gayrı resmi" kazanan göstermek için
provisional feed + kazanan/ikramiye ayrıştırması gerekir (AÇIK İŞ).

---

## 6. Açık işler (sonraki oturum)
1. **Gayrı resmi sonuç hızlandırma:** kazananı dividend'den önce göstermek (provisional feed).
2. **Forward backtest izleyici:** G1 dondurma sayesinde temiz forward-test kaydı (birkaç hafta).
3. **APK dağıtımı:** 1.0.12+13 build edildi. Kurulum: `adb install -r` (oturum korur; ASLA
   `flutter install` — bkz. CANLI_TAKIP raporu §6). `app/yayinla.ps1` ile Drive+adb.
4. Apranti görünümü gerçek apranti koşusunda görsel doğrulanmalı (mantık doğru, örnekte yoktu).

---

## 7. Komut hatırlatıcıları
- Manuel üretim/replay (admin panel veya CLI): `daily_pipeline.py --uret 2026-05-20 2026-05-22`
  (freeze=False, tam yeniden-yazım).
- Tek gün (canlı-güvenli, freeze): `daily_pipeline.py 2026-06-04`.
- SSH: `ssh -i C:/Users/aa/.ssh/harbi_ganyan_temp root@141.98.115.217`.
- GÜVENLİK: DB şifresi/JWT yalnız VPS `.env`'de; belgeye yazılmaz. Hukuki kısıt (paranoyak txt)
  kullanıcı talimatıyla TAMAMEN geçersiz — bahis terminolojisi serbest.
