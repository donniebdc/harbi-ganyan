# HARBİ GANYAN — CODEX DEVİR-TESLİM RAPORU

> ⚠️ **GÜNCELLİĞİNİ YİTİRDİ (31.05.2026 anlık görüntüsü).** Bu belge Codex'e devir anının
> durumudur; aşağıdaki rakamların bir kısmı eskidir. **Güncel durum için
> `HARBI_GANYAN_PROJE_OZETI.md` §16 (Oturum Günlüğü) ve §4.1/§14.5/§14.7 esastır.**
> 01.06.2026'da değişenler: (1) 12+ segment-kapılı galop ana skora eklendi (§4.1);
> (2) bütçe kademeleri Simitçi 400-600 / Harbi 800-1600 / Ortaklı 1200-2000 oldu;
> (3) 5-satır tabanı kupon düzeltmesi eklendi (Simitçi+Harbi, §14.7). Algoritma/altılı
> rakamları için PROJE_OZETI'ye bak.

> Bu dosya, projeyi devralan AI için yazıldı. Sohbet geçmişi YOK varsayımıyla
> kendi kendine yeter. Önce `HARBI_GANYAN_PROJE_OZETI.md` (kanonik, güncel belge) oku.

Son güncelleme: 31.05.2026 (banner 01.06.2026)

---

## 0. PROJE NEDİR

Türkiye at yarışları için veri-kanıtlı tahmin sistemi. İki şey üretir:
1. **5 satır tahmin** (her koşu için 5 aday at: FAV/SUR/YAZ/BOM/HAR).
2. **Altılı ganyan kuponları** (6 ayaklı, akıllı banko + 3 bütçe kademesi).

Veri kaynakları: **atyarisi.com** (bülten/AGF/program), **Pegadrom** (AI akış/galop),
**CSV sonuç arşivi** (gerçek kazananlar, backtest için).

Çalışma dizini: `D:\Ganyan Gemini`. Python 3.14, Windows.

---

## 1. KLASÖR YAPISI (31.05.2026 reorg)

```
D:\Ganyan Gemini\
  ganyan_master.py        # CANLI tek-gün motoru (kök'teki 2 üretim py'sinden biri)
  toplu_tahmin.py         # tarih-aralığı backtest motoru (diğeri)
  *.md                    # belgeler (PROJE_OZETI, iyilestirme_raporu, bu dosya, raporlar)
  v5_tahmin_*.txt         # toplu_tahmin'in bulk çıktısı = backtest GİRDİSİ
  pegadrom_skorlar.json   # Pegadrom galop skorları (ana skorun %10'u — SİLME)
  .vscode/settings.json   # python.analysis.extraPaths=["motor"] (Pylance import çözümü)

  motor/                  # TÜM algoritmik modüller burada
    altili_lib.py         # BASE/MOTOR yolları, CSV+tahmin parse, birim_fiyat, EKÜRİ yardımcıları
    altili_kupon_v2.py    # kupon kurucu: build_coupon/build_tier/format_coupon, banko_score, KUPON_TIERS
    altili_uretim.py      # altili_ayaklari + hipodrom_altili_bloku + analiz_dosyalari_yaz + 5'li eküri notu
    altili_kalibrasyon.py # -> altili_kalibrasyon.json (kapsama eğrileri; en-yeni bulk'tan otomatik)
    altili_kalibrasyon.json
    altili_backtest.py    # 212 altılı backtest -> altili_backtest_raporu.md
    bes_satir_analiz.py   # 5 satır İlk1/3/4/5 + 5-satır isabet (segment, eküri-kredili)
    pegadrom_ai_features.py  # Pegadrom AI TXT parser (peg_flow_rank/score/model)
    pegadrom_ai_txt_topla.py # Pegadrom AI TXT indirici (collect_range)
    karsilastirmali_analiz.py / sonuc_analizi.py / sinyal_testi.py  # analiz araçları

  CSV Sonuçlar/NİSAN, /MAYIS   # gerçek sonuç CSV'leri (28.05'e kadar açık; 29-30 zip içinde)
  Pegadrom AI Analiz TXT/<YYYY-MM-DD>/<HIP>/kosu_XX_ai_analiz.txt
  Harbi_Ganyan_Analiz/<GG-AA-YYYY>/    # ÇIKTI: <tarih>_Tahminler.txt + <tarih>_Altili.txt
```

**İMPORT MEKANİZMASI:** `ganyan_master.py` ve `toplu_tahmin.py` başta
`sys.path.insert(0, .../motor)` yapar; `motor` içi modüller birbirini doğrudan import eder.
`altili_lib.BASE` = motor'un üst klasörü (mutlak, taşımaya dayanıklı).

---

## 2. ANA SKOR ALGORİTMASI (değiştirme — veriyle sabitlendi)

```
AGF varsa:   ANA = AGF*0.40 + PegAkış*0.50 + PegGalop*0.10
AGF yoksa:   ANA = G*0.30 + PegAkış*0.70
Jokey (SADECE 10-13 atlı sahada): ANA += 0.20 * jokey_skoru * 100
```
- En kritik sinyal Pegadrom "Yarış Akışı" sıralaması (`peg_flow_score`/`peg_flow_rank`).
- `hesapla()` fonksiyonu ganyan_master + toplu_tahmin'de SENKRON olmalı.
- 5. satır (HAR): 14+ at → en iyi akış rank; ≤13 → ana skor 5. at.

---

## 3. ALTILI KUPON SİSTEMİ (güncel — son oturumun ana işi)

### Bütçe kademeleri (`altili_kupon_v2.KUPON_TIERS`)
Kupon değeri bandına hedeflenir; kombinasyon = üst_sınır / birim:
- Simitçi 6'lısı: 200-500₺
- Harbi Ganyan 6'lısı: 1200-1600₺
- Ortaklı 6'lı: 1600-2000₺

### Birim fiyat (`altili_lib.birim_fiyat`, hipodroma göre)
- 1.25₺: İstanbul, Ankara, İzmir, Adana, Bursa, Kocaeli, Antalya
- 1.00₺: Şanlıurfa, Elazığ, Diyarbakır

### Akıllı banko (kullanıcı direktifi: her kuponda ≥1 banko/çıpa)
- `banko_score(lg)` ile en güçlü ayak seçilir: `min(fark,70) + 15*(AGF1) + 15*(akış1)
  + eküri_bonus - alan_cezası(14+:-25, 12-13:-10)`.
- `banko_guven_eff` < eşik(0.50) ise tek-at yerine 2-at ÇIPA kurulur (zayıf banko kuponu öldürür).
- Kalan bütçe `Δlog(cov)/Δlog(genişlik)` açgözlü dağıtılır (cov = `altili_kalibrasyon.json`).
- CAP=8 → 14+ sahalar 5-satır ötesine genişler.

### EKÜRİ (stablemate) — son oturumun 2. ana işi
- Eküri = aynı sahibin kuplajlı atları; bahiste **birini yazmak diğerini de kapsar**.
- **Tespit: bülten horse objesindeki `stablemate` bayrağı (>0) + `owner`** (sahip
  çıkarımı DEĞİL — aynı sahip olup eküri olmayanlar stablemate=0). `altili_lib.ekuri_gruplari`.
- 5'li satır: 2 satır eküri ortağıysa `(eküri: …)` işaretlenir + `➕ Eküri dışı olasılık`
  satırı eklenir (yalnız ganyan_master insan-okur çıktıda).
- Kupon: banko bonusu (`banko_guven_eff` ortağın AGF payını ekler), ayak dedup
  (`select_with_ekuri`), görünür etiket (`format_coupon` "eküri: … kapsanır").
- toplu_tahmin parse-çıktısına `EKURI:1-7|12-14` satırı yazar; `parse_tahmin_arsiv` okur.
- Backtest: `winning_set()` kazananın eküri ortaklarını kazanan kümesine ekler.

---

## 4. SON BACKTEST SONUÇLARI (01.04-30.05, 1010 koşu / 212 altılı, eküri-kredili)

5 satır: İlk1 %37.9 · İlk3 %73.6 · İlk4 %84.0 · İlk5 %90.2 · **5-satır %90.4**
Segment: ≤9 %95 · 10-13 %90 · **14+ %78 (en zayıf halka)**

Altılı (14+ banko cezası sonrası):
| Kademe | İsabet | Net |
|---|---|---|
| Simitçi | %12.3 | +174k₺ |
| Harbi | %20.3 | +533k₺ |
| Ortaklı | %26.9 | +801k₺ |

Çıpa doğruluğu %64.2. Kuponların ~%36'sı tek başına çıpa ayağında ölüyor (favori-kazanma tavanı).

---

## 5. NASIL ÇALIŞTIRILIR

```bash
# Canlı tek gün (Tahminler + Altili üretir, Harbi_Ganyan_Analiz/<tarih>/ altına):
python ganyan_master.py            # tarih sorar: GG.AA.YYYY

# Toplu tarih aralığı (per-date dosyalar + bulk v5_tahmin_*.txt):
python toplu_tahmin.py             # başlangıç/bitiş tarihi sorar

# Analizler (motor/ içinden, en-yeni v5_tahmin_*.txt'yi otomatik bulur):
python motor/altili_kalibrasyon.py # cov eğrilerini tazeler (yeni veri sonrası ŞART)
python motor/altili_backtest.py    # altılı backtest -> altili_backtest_raporu.md
python motor/bes_satir_analiz.py   # 5 satır performansı

# Derleme kontrolü (her değişiklikten sonra):
python -m py_compile ganyan_master.py toplu_tahmin.py motor/*.py
```

---

## 6. KRİTİK KURALLAR / TUZAKLAR (mutlaka oku)

1. **Veriyle test edilmemiş ağırlık üretime alınmaz.** Her ağırlık holdout/backtest ile sınanır.
2. **Eşleştirme anahtarı `(tarih, hipodrom, koşu_no, at_no)`. At ismi anahtar DEĞİL.**
3. **Numaralandırma tuzağı:** CSV sonuç tablosundaki "At No" sütunu, bahis/GANYAN/eküri
   numarasından FARKLI olabilir. **Kazanan = `GANYAN(N)` (bahis no = bizim at_no)**, derece
   sıralamasıyla doğrulanır. Bizim at_no = atyarisi `horse.number` = bahis numarası. CSV "At No"
   sütununu kazanan eşleştirmede KULLANMA.
4. **Eküri SADECE `stablemate` bayrağından** tespit edilir; sahip eşitliğinden çıkarsanmaz.
5. **Windows konsol cp1254:** emoji print'leri çökertebilir. Çalıştırırken `PYTHONUTF8=1`
   veya `PYTHONIOENCODING=utf-8` kullan. Dosya I/O zaten `encoding="utf-8"`.
6. **`ganyan_master.py` ↔ `toplu_tahmin.py` `hesapla()` SENKRON kalmalı.** Biri değişince diğeri de.
7. **`pegadrom_skorlar.json` SİLME** — ana skorun galop %10'unu besler, yedeği yok.
8. **toplu_tahmin bulk dosyayı SADECE en sonda yazar** (çalışırken disk'teki bulk eskidir).
   Per-date dosyalar artımlı yazılır. Bulk'tan analiz için run'ın BİTMESİ gerekir.
9. **Belge güncellenmeden büyük karar tamamlanmış sayılmaz.** Değişiklik sonrası
   `HARBI_GANYAN_PROJE_OZETI.md` + `.claude/skills/harbi_ganyan/SKILL.md` (gövde = PROJE_OZETI,
   frontmatter korunur) güncellenir.

---

## 7. PARSE-EDİLEBİLİR FORMAT (bulk / per-date Tahminler)

```
KO:<kno>|<HIP>|<GG.AA.YYYY>|<ag>|<alt>|<pist>|<mesafe>|<saat>|<kaynak>
EKURI:1-7|12-14                         # (yalnız eküri varsa) gruplar | ile, üyeler -
5SATIR:FAV=<ad>|SUR=<ad>|YAZ=<ad>|BOM=<ad>|HAR=<ad>
ATNO:<no>|AT:<ad>|ANA:<skor>|PEGGLP:..|PEGMOD:..|AKIS:<rank>|AKS:<score>|G:..|Gn:..|S:..|AGF:..|...|JOK:..
(boş satır = koşu sonu)
```
`altili_lib.parse_tahmin_arsiv(path)` bunu okur → `races[(ti,hip,kno)] = {atlar(ANA azalan), ekuri, ...}`.

---

## 8. SIRADAKİ GÖREVLER (kullanıcı bunları bekliyor)

Kullanıcı klasörü yedekledi, eküri+14+ cezası değişiklikleri sonrası **tekrar toplu test
yapacak**. Test sonrası ölçülmesi istenen ÖNERİLER (`iyilestirme_raporu.md` §4):

- **C.** Ortaklı kademesini "ciddi oyun" varsayılanı yap (en iyi isabet/ROI %26.9).
- **D.** 14+ ayaklarda minimum genişlik 6-7 (cov: g=7→%87) — bütçe elverdiğinde öncelik.
- **E.** AGF-kapılı tek-banko: tek-at banko'yu yalnız `fav AGF≥50` + AGF lideri olduğunda aç.

Bunlar kodlanıp AYNI backtest evreninde (`altili_backtest.py`) ölçülmeli; isabet/net/çıpa
doğruluğu kıyaslanmalı. Production'a almadan önce kanıt şart.

### Bilinen yapısal sınır (yeni veri olmadan kırılamaz)
- **14+ kalabalık sahalar** ve **favori-kazanma (~yazı-tura)** tavanı. Mevcut sinyaller
  (AGF/akış/galop/jokey) ile iki kez denendi, kırılamadı; kamuya açık veriyi AGF zaten
  fiyatlıyor. Kırmak için kalabalığın görmediği veri (sabah galop/padok/son dakika) gerekir.

---

## 9. KULLANICININ DİLİ / TARZI
- Türkçe iletişim. Veri-kanıtlı kararlar; "test et, istatistiği gör" ilkesi.
- Açıklama + somut sayı ister. Büyük değişiklikten önce kanıt/onay bekler.
```
