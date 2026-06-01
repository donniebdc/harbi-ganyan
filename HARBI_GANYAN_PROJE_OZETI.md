# HARBI GANYAN - Proje Özeti, İşlem Haritası ve Yol Haritası

Son güncelleme: 01.06.2026 (TJK JSON sonuç altyapısı §14.8 + iç içe kademeler & sonuç çıktıları §14.9)

Bu belge Harbi Ganyan projesinin güncel çalışma haritasıdır. Yeni bir oturumda önce bu dosya okunmalı; ardından kök'teki `ganyan_master.py` ve `toplu_tahmin.py`, sonra `motor/` klasöründeki modüller (`altili_kupon_v2.py`, `altili_uretim.py`, `altili_lib.py`, `pegadrom_ai_txt_topla.py`, `pegadrom_ai_features.py`) incelenmelidir.

---

## 1. Projenin Amacı

Harbi Ganyan, Türkiye at yarışları için veri-kanıtlı tahmin üreten bir sistemdir.

Ana hedefler:

- Günlük yarış programını çekmek.
- Her koşu için 5 satırlı tahmin üretmek.
- Her atın puan dökümünü açıklanabilir biçimde göstermek.
- Her altılı ganyan için akıllı banko stratejisiyle 3 bütçe kademesinde kupon kurmak.
- Mobil uygulamada 1 gün önceden tahmin verebilecek erken mod kurmak.
- Yarış günü AGF geldiğinde tahmini revize edebilecek ikinci mod tutmak.

Temel tasarım ilkesi:

- Her ağırlık ve karar veriyle sınanır.
- At adı eşleştirmede güvenilir kabul edilmez.
- Kritik eşleştirme anahtarı: `(tarih, hipodrom, koşu_no, at_no)`.
- `ganyan_master.py` ve `toplu_tahmin.py` algoritmik olarak senkron kalmalıdır.

---

## 2. Güncel Ana Akış

Günlük kullanım:

```text
python ganyan_master.py
  -> kullanıcı tek tarih girer
  -> sistem önce Pegadrom AI TXT verisini toplar (eksikleri indirir)
  -> atyarisi.com bülten/program verisi çekilir (owner+stablemate dahil)
  -> jokey/orijin indeksleri CSV arşivinden kurulur
  -> yeni algoritma ile 5 satır + eküri notları üretilir
  -> akıllı banko altılı kuponları (3 kademe) kurulur
  -> Harbi_Ganyan_Analiz/<GG-AA-YYYY>/<GG-AA-YYYY>_Tahminler.txt
                                     /<GG-AA-YYYY>_Altili.txt  yazılır
```

Toplu kullanım:

```text
python toplu_tahmin.py
  -> kullanıcı başlangıç ve bitiş tarihi girer
  -> Pegadrom AI TXT verisini toplar (eksikleri indirir)
  -> tarih aralığı boyunca tahmin üretir
  -> HER TARİH için Harbi_Ganyan_Analiz/<tarih>/ altına Tahminler.txt + Altili.txt
  -> AYRICA backtest girdisi olan bulk v5_tahmin_*.txt (KO:/EKURI:/5SATIR:/ATNO:) yazar
```

Önemli güncelleme:

- Artık `ganyan_master.py` veya `toplu_tahmin.py` çalıştırılınca Pegadrom AI TXT toplama adımı otomatik yapılır.
- Bu işlem `pegadrom_ai_txt_topla.collect_range(...)` üzerinden yapılır.
- Varsayılan klasör: `Pegadrom AI Analiz TXT`.
- Varsayılan davranış: var olan TXT dosyasını yeniden yazmaz (`force=False`).

---

## 3. Veri Kaynakları

### 3.1 atyarisi.com API

Kullanım alanları:

- Günün hipodromları.
- Program detayları.
- Koşular, atlar, jokeyler, AGF, bahis/altılı başlangıç bilgisi.
- Bülten analiz puanları.

Kullanılan ana uçlar:

- `ProgramHippodromes?date=YYYY-MM-DD`
- `ProgramDetails?programId=...`
- `GetHorseAnalysisByProgramAndRace?programId=...&raceNo=...`

Kullanılan puanlar:

- `G`: generalScore.
- `Gn`: currentScore. Eski sistemde ana skordaydı; yeni düzende ana skordan çıkarıldı.
- `S`: hourlyScore. Varsa destek sinyali olarak korunur.
- `AGF`: yarış günü geldiğinde güçlü piyasa sinyali.

### 3.2 Pegadrom

Kullanım alanları:

- AI analiz TXT kaynağı.
- Yarış akışı / tempo / konum sıralaması.
- Model puanı.
- Veri güveni.
- Pegadrom galop puanı.
- Pist/mesafe, hız, form, jokey, sınıf gibi açıklayıcı katmanlar.

Kritik bulgu:

- Kullanıcının manuel gözlemi doğrulandı: Pegadrom "Yarış Akışı" ilk 5 evreni kazananı yakalamada çok güçlü.
- Derin testte Pegadrom akış rank skoru tek başına `İlk1/İlk3/İlk4/İlk5 = 33.2% / 72.8% / 81.7% / 87.6%` verdi.
- Pegadrom model puanı tek başına zayıf kaldı; ana kararın tamamı yapılmamalı.
- Pegadrom galop puanı eski galop sistemimizden daha düzenli bir kaynak olarak sisteme dahil edildi, ama ana taşıyıcı sinyal akış sıralamasıdır.

### 3.3 CSV Sonuç Arşivi

Klasör:

- `CSV Sonuçlar/NİSAN`
- `CSV Sonuçlar/MAYIS`

Mevcut kapsam:

- 120 CSV dosyası.
- 2026 Nisan ve 2026 Mayıs yarış sonuçları.
- Backtest, gerçek kazanan, ilk3/ilk4 ölçümü, jokey-şehir ve baba/orijin indeksleri için kullanılır.
- Okunması zor format + sınırlı kapsam nedeniyle birincil sonuç kaynağı artık JSON'dur
  (§3.5, §14.8). CSV yalnızca altılı ÖDEME (ROI) için ek değer taşır; `load_results`
  CSV'yi taban alıp JSON ile tamamlar.

### 3.5 TJK JSON Sonuç Arşivi (birincil sonuç kaynağı)

- Klasör: `Sonuclar JSON/<YYYY-MM-DD>.json` (`motor/tjk_sonuc_topla.py` üretir).
- Kaynak: TJK resmi feed `https://ebayi.tjk.org/s/d/sonuclar/...` (atyarisi.com'un da
  tükettiği statik JSON). at_no doğrudan gelir; köprü gerekmez.
- İçerik: koşu başına kazanan at_no, tam varış sırası (at_no + derece + ganyan + agf),
  eküri, kosmaz, mesafe/pist VE **tüm kombine bahis ikramiyeleri** (altılı/5'li/üçlü
  ganyan, ikili, sıralı ikili, plase, çifte, tabela...).
- Kapsam: CSV'nin olmadığı 2026-02 / 2026-03 dahil tüm test aralığı (Şubat-Mayıs).
- Detay ve teknik notlar: §14.8.

### 3.4 Toplu Tahmin Arşivi

- Eski sürüm ham çıktı arşivi `Toplu Tahminler/` (v1–v7) SİLİNDİ (31.05.2026);
  hiçbir kod okumuyordu, sürüm metrikleri §6.1 tablosunda korunuyor.
- Güncel backtest girdisi: kökteki `v5_tahmin_*.txt` (toplu_tahmin.py üretir).

---

## 4. Güncel Algoritma

Eski modelden çıkarılanlar:

- Eski Liderform/sprint tabanlı galop ağırlığı.
- `galop_guven` sistemi.
- `GLP/GGV/GSP/GGN/GEF/GSY` temelli ana skor etkisi.
- `Gn` puanının ana skor içindeki ağırlığı.

Yeni modelde tutulanlar:

- AGF varsa güçlü piyasa sinyali olarak korunur.
- AGF yoksa erken/mobil modda bülten `G` kullanılır.
- Pegadrom Yarış Akışı ana taşıyıcı sinyal olur.
- Pegadrom galop puanı düşük ağırlıklı destek sinyali olur.
- Pegadrom galop yoksa at için galop puanı nötr kabul edilir: `50`.

Güncel ana skor:

```text
AGF varsa:
  ANA = AGF * 0.40 + Pegadrom Yarış Akışı * 0.50 + Pegadrom Galop * 0.10

AGF yoksa:
  ANA = G * 0.30 + Pegadrom Yarış Akışı * 0.70

Jokey düzeltmesi (SADECE 10-13 atlı sahalarda):
  ANA += 0.20 * jokey_skoru * 100

12+ SEGMENT-KAPILI GALOP (01.06.2026 eklendi — §4.1):
  n_at >= 12 ise yukarıdaki market+akış formülü yerine:
  ANA = market * 0.25 + Akış * 0.45
        + galop.en_iyi(nötr=50) * 0.10
        + galop.istikrar(nötr=50) * 0.15
        + galop.en_iyi(eksik=0) * 0.05
  (market = AGF varsa AGF, yoksa G. Tüm normlar koşu-içi min-max 0-100.)
  Jokey düzeltmesi 12-13 atlı sahalarda bunun ÜZERİNE ayrıca uygulanır.
  n_at <= 11 ise baseline (üstteki formül) aynen korunur.
```

Notlar:

- Derin grid/holdout testinde AGF'li en iyi aday: `AGF=0.4`, `flow_rank_score=0.5`, `peg_galop_neutral=0.1`.
- AGF'siz modda sade ve güçlü aday: `G=0.3`, `flow_rank_score=0.7`.
- Pegadrom model puanı çıktı ve açıklama tarafında tutulur; grid sonucunda nihai ağırlık ana formülde baskın çıkmadı.

Jokey sinyali (31.05.2026 eklendi — segment kısıtlı):

- `jokey_skoru` (jokey-şehir kazanma oranı) v4'te kullanılıyordu, Pegadrom yazımında ana skordan düşmüştü; CSV arşivinden hâlâ hesaplanıyordu ama skora katılmıyordu.
- 1010 koşu + holdout testinde jokey'i ana skora eklemek SADECE 10-13 atlı sahalarda sağlam kazanç verdi: 5 satır %89.9 → %90.5 (tüm veri +0.6, holdout +1.5).
- `<=9` atlı sahalarda nötr, `14+` atlı sahalarda ZARARLI (holdout -2.2). Bu yüzden jokey yalnızca 10-13 segmentinde, `k=0.20` ağırlıkla uygulanır.
- Top4 testinde jokey daha büyük görünüyordu (+0.8/+1.4) ama 5 satır metriğinde net katkı küçük: jokey'in top4'e kattığı kazananları zaten HAR satırı yakalıyordu. Gerçek ürün metriği (5 satır) baz alındı.
- `ganyan_master.py` ve `toplu_tahmin.py` `hesapla()` fonksiyonları bu kuralda senkron.

### 4.1 12+ Segment-Kapılı Galop (01.06.2026)

Codex turundan sonra `pegadrom_skorlar.json` içindeki `galop` alt-alanları (`en_iyi`, `istikrar`) 1004 koşu / 212 altılı evreninde test edildi. İki adımlı doğrulama yapıldı:

**1. grid7 altılı iddiası REDDEDİLDİ.** JSON geniş testindeki `grid7` adayı (Market 0.25 + Akış 0.45 + galop ~0.30) holdout'ta (n=47) çıpayı %72.3 → %76.6, Ortaklı'yı %21 → %27.7 göstermişti. Tam 220-altılı evrende (n=212) bu **replike olmadı**: çıpa %62.7 → %62.3, Ortaklı %25.0 → %23.6 (**-3 altılı**). 47-örneklemli aşırı-uyum. (Rapor: `grid7_altili_dogrula_raporu.md`.)

**2. Aynı sinyal SADECE kalabalık koşularda 5'liyi ve altılıyı düzeltti.** Galop'u global değil, segment-kapılı uygulayınca (`seg12_g7`):

| Metrik | baseline | seg12_g7 (üretimde) |
|---|---:|---:|
| ≤9 5-satır | %95.2 | %95.2 (değişmez) |
| 10-13 5-satır | %89.7 | %90.8 (+1.1) |
| 14+ 5-satır | %78.0 | %79.8 (+1.8) |
| Genel 5-satır | %90.3 | %91.0 (+0.7) |
| HAR | %40.5 | %42.7 (+2.2) |
| Altılı çıpa | %62.7 | %64.2 (+1.5) |
| 3 kupondan biri | 53/212 | 54/212 (+1) |

Global uygulanınca İlk1 ve ≤9 bozuluyordu; `n_at >= 12` kapısı bunu önler (≤11 koşu baseline ile matematiksel olarak aynı). Karar: **12+ eşik üretime alındı.** (Rapor: `seg14_galop_dogrula_raporu.md`.)

Uyarı: galop ağırlıkları (grid7) train verisinde seçildi; tam-evren ölçümü kısmen in-sample → kazancın büyüklüğü iyimser kabul edilmeli. Yön (14+ +1.8 holdout / +2.78 JSON-raporu) tutarlı olduğu için kabul edildi. Mütevazı ama gerçek kazanç.

---

## 5. 5 Satır Mantığı

5 satır isimleri sabit kalır:

1. Harbi Ganyan Favorisi
2. Kazanırsa Sürpriz Olmaz
3. Kupona Yazılabilir
4. Bomba!
5. Harbi mi?

Seçim mantığı:

- İlk 4 satır ana skor sıralamasından gelir.
- 5. satır (`Harbi mi?`) artık **segmentli** seçilir (1010 koşu simülasyonuyla kanıtlandı):
  - Kalabalık koşu (**14+ at**) → top4-dışı adaylar içinden **en iyi Pegadrom akış rank**ı (en küçük `peg_flow_rank`).
  - Diğer koşular (**≤13 at**) → **ana skor 5. atı**.
- Her satır tek at verir.

Eski kritik bulgu:

- 4. satırı "galop bombası" yapmak başarıyı düşürdü.
- 4. satırın ana skor 4. atı olması 5 satır isabetini yükseltti.

HAR (5. satır) kritik bulgusu (v7 → güncel):

- v6/v7'deki **galop-tabanlı HAR** (galop-ilk3 veya en yüksek galop), top4-dışı kazananın yalnızca **%19.4**'ünü yakalıyordu — sistemin en zayıf halkası.
- 9 farklı HAR kuralı 1010 koşuda test edildi. Galop kuralı **en kötü** çıktı.
- Segmentli kural (14+ → akış rank, ≤13 → ana 5.) top4-dışı yakalamayı **%38.8**'e çıkardı.
- Gerçek v7 satırları üzerinde doğrulama: **5 satır %87.0 → %90.0 (+3.0)**. Segment kırılımı: ≤9 at +1.4, 10-13 at +5.0, 14+ at +3.2.
- Test edilen diğer adaylar (genel 5 satır Δ): `agf` +2.5, `flow_score` +2.2, `flow5+agf` +2.0, `model` +0.3.

EKÜRİ (31.05.2026, §14.6): 5 satırdan ikisi eküri ortağıysa her ikisi `(eküri: …)`
işaretlenir ve altına `➕ Eküri dışı olasılık` ek atı önerilir. Eküri = `stablemate` bayrağı.

---

## 6. Performans ve Karar Kanıtları

### 6.1 Eski sürüm evrimi

| Sürüm | İlk3 | İlk4 | 5 Satır | Ana değişiklik |
|---|---:|---:|---:|---|
| v1/v2 | %59.0 | %70.2 | - | Karma bonus/ceza sistemi |
| v3 | %65.1 | %70.3 | %78.5 | Veri-kanıtlı ana skor |
| v4 | %66.6 | %72.6 | %79.2 | Jokey-şehir düzeltmesi |
| v5 | %66.6 | %76.0 | %82.0 | 4. satır ana skor 4 oldu |
| v6 | %66.5 | %75.8 | %81.8 | Galop B planı denendi, başarılı olmadı |
| v7 | - | - | %87.0 | Pegadrom akış ana skora entegre (AGF 0.4 + akış 0.5 + galop 0.1) |
| v7+HAR | - | - | **%90.0** | HAR segmentli: 14+ → akış rank, ≤13 → ana 5. (galop HAR kaldırıldı) |

Not: v7/v7+HAR oranları düzeltilmiş ölçümle (kazanan = en hızlı derece, isabet at ismiyle) hesaplandı; eski sürümlerin tablosu kendi tarihsel ölçümünden gelir.

### 6.2 Pegadrom üçlü karşılaştırma

Kaynaklar:

- `pegadrom_skorlar.json`
- `CSV Sonuçlar`
- `v5_tahmin_*.txt` (eskiden `Toplu Tahminler/toplu tahmin v6.txt`; arşiv silindi)
- `Pegadrom AI Analiz TXT`

Eşleşme kuralı:

- `(tarih, hipodrom, koşu_no, at_no)`
- At ismi eşleştirme anahtarı değildir.

Kapsam:

- CSV sonuç koşusu: 1010.
- v6 koşusu: 1028.
- Pegadrom AI TXT koşusu: 1028.
- Ortak ve kazananı eşleşen koşu: 1004.
- Üçlü eşleşen at kaydı: 10028.

Tekil sinyaller:

| Sinyal | İlk1 / İlk3 / İlk4 / İlk5 |
|---|---:|
| v6 ANA | 33.3% / 68.6% / 78.2% / 85.4% |
| AGF | 33.8% / 69.2% / 79.0% / 84.9% |
| G genel | 28.7% / 63.2% / 73.1% / 80.4% |
| Gn güncel | 25.3% / 60.1% / 70.8% / 79.3% |
| S saatli | 25.6% / 57.5% / 69.1% / 76.6% |
| Bizim eski GLP | 14.0% / 38.9% / 52.0% / 63.2% |
| Pegadrom model | 23.1% / 51.6% / 61.8% / 72.0% |
| Pegadrom galop nötr | 15.1% / 38.6% / 49.5% / 59.6% |
| Pegadrom akış rank skoru | 33.2% / 72.8% / 81.7% / 87.6% |

Hibrit holdout sonucu:

| Aday | Seçilen ağırlık | Test İlk1/3/4/5 | Tüm veri İlk5 |
|---|---|---:|---:|
| Peg-only | flow 0.9 + galop 0.1 | 32.1% / 71.2% / 80.1% / 87.4% | 87.8% |
| AGF'siz yeni | G 0.3 + flow 0.7 | 32.8% / 69.9% / 80.1% / 87.7% | 88.7% |
| AGF'li yeni | AGF 0.4 + flow 0.5 + galop 0.1 | 33.4% / 70.2% / 82.8% / 88.7% | 89.6% |

Net karar:

- Pegadrom dahil edilmeli.
- En değerli sinyal Pegadrom model değil, Yarış Akışı sıralamasıdır.
- Pegadrom galop eski galop sistemimizin yerine kullanılmalı, ama düşük ağırlıkla.
- `Gn` ve eski galop güven sistemi yanıltıcı olduğu için ana skordan çıkarıldı.

---

## 7. Eklenen Dosyalar ve Rolleri

### `pegadrom_ai_txt_topla.py`

Görev:

- Tarih aralığına göre Pegadrom `ai-analiz` sayfalarını çeker.
- Yerli hipodromları Pegadrom menüsünden bulur.
- Her koşuyu okunabilir TXT olarak kaydeder.

Parser düzeltmesi (31.05.2026):

- Pegadrom `/galoplar` menü markup'ını yeniledi; eski `gunun_hipodromlari()` regex'i (`<strong>...<small>N ko`) artık eşleşmiyordu ve "yerli hipodrom bulunamadı" hatası veriyordu (örn. 31.05.2026 İSTANBUL+ADANA kaçırılıyordu).
- Regex yerine BeautifulSoup tabanlı dayanıklı yöntem: `hip=XXX` içeren tüm `<a>` linklerini gez, metindeki "N koşu" ifadesinden koşu sayısını al, `TR_HIPODROMLAR` ile yerli filtrele.
- Doğrulandı: 31.05→İSTANBUL 10/ADANA 9, 28.05→ANKARA 9/IZMIR 9, 01.04→ISTANBUL 8/ELAZIG 8, gelecek tarih→boş.

Çıktı yapısı:

```text
Pegadrom AI Analiz TXT/
  YYYY-MM-DD/
    HIPODROM/
      kosu_01_ai_analiz.txt
      kosu_02_ai_analiz.txt
    index.txt
```

Özellikler:

- `YYYY-MM-DD` ve `GG.AA.YYYY` tarih formatlarını kabul eder.
- Mevcut dosyaları varsayılan olarak atlar.
- `--force` verilirse yeniden yazar.
- Hatalı koşularda `kosu_XX_HATA.txt` üretir.

### `pegadrom_ai_features.py`

Görev:

- Pegadrom AI TXT klasörünü parse eder.
- At bazlı özellik sözlüğü üretir.

Başlıca alanlar:

- `peg_model`
- `peg_veri`
- `peg_flow_rank`
- `peg_flow_score`
- `peg_flow_type`
- açıklayıcı reason/sinyal alanları

### `motor/sonuc_analizi.py`

Görev:

- 5 satırlı tahminleri CSV sonuçlarıyla eşleyip 5 satırdaki atların kaçıncı bitirdiğini yazar.
- Analiz aracı; üretim akışında değil.

### Altılı kupon (motor/altili_kupon_v2.py + altili_uretim.py)

- `altili_kupon.py` (eski v1 brute-force kupon) SİLİNDİ. Güncel sistem `motor/altili_kupon_v2.py`
  (akıllı banko, KUPON_TIERS, build_tier, select_with_ekuri) + `motor/altili_uretim.py`
  (hipodrom_altili_bloku, dosya yazımı). Detay: §14.5 ve §14.6.

### Karşılaştırma raporları (scriptler arşivden çıkarıldı)

- `pegadrom_karsilastirma_raporu.md` ve `derin_pegadrom_algoritma_raporu.md` korunur.
- Bu raporları üreten tek seferlik scriptler (`pegadrom_karsilastirma.py`, `derin_pegadrom_karsilastirma.py`) 31.05.2026 temizliğinde silindi.
- Bulgular bu özetin 6. bölümünde zaten kayıtlı.

### `pegadrom_skorlar.json`

Görev:

- Pegadrom galop/model kaynaklarından toplanmış JSON skor arşivi.
- Eski karşılaştırma ve galop sayfası puanı için kullanılır.

### `pegadrom_ai_analiz_2026-05-29_ISTANBUL_1.txt`

Görev:

- Kullanıcının verdiği örnek Pegadrom sayfasının okunabilir TXT çıktısı.
- Parser ve TXT formatının ilk doğrulama örneği.

---

## 8. Güncellenen Ana Dosyalar

### `ganyan_master.py`

Rol:

- Tek tarihli günlük tahmin motoru.
- Kullanıcıya okunabilir günlük çıktı üretir.
- Altılı kupon önerir.

Son değişiklikler:

- `pegadrom_ai_txt_topla` import edildi.
- `DEFAULT_OUT`, `DEFAULT_DELAY`, `collect_range` kullanılıyor.
- Çalışınca önce ilgili tarihin Pegadrom AI TXT verisini topluyor.
- Toplama sonrası `load_ai_txt_root(...)` ile Pegadrom özellikleri yeniden yükleniyor.
- Eski galop güven sistemi kaldırıldı.
- `Gn` ana skordan çıkarıldı.
- Yeni skor: AGF varsa `AGF*0.40 + Akış*0.50 + PegGalop*0.10`, AGF yoksa `G*0.30 + Akış*0.70`.

### `toplu_tahmin.py`

Rol:

- Tarih aralığı için toplu tahmin/backtest motoru.
- Parse edilebilir `KO:`, `5SATIR:`, `ATNO:` satırları üretir.

Son değişiklikler:

- `pegadrom_ai_txt_topla` import edildi.
- Çalışınca önce girilen tarih aralığına ait Pegadrom AI TXT dosyalarını topluyor.
- Toplama sonrası Pegadrom özellikleri yeniden yükleniyor.
- Eski galop bileşenleri ana skordan çıkarıldı.
- Çıktıya Pegadrom alanları eklendi:
  - `PEGGLP`
  - `PEGMOD`
  - `AKIS`
  - `AKS`

---

## 9. Klasör ve Dosya Haritası

Ana klasör:

```text
D:\Ganyan Gemini
```

Kök klasör (SADECE 2 py + md + veri klasörleri — 31.05.2026 reorg):

```text
D:\Ganyan Gemini\
  ganyan_master.py          # canlı günlük motor (kök'te kalan tek üretim py)
  toplu_tahmin.py           # tarih aralığı backtest motoru (kök'te kalan tek py)
  *.md                      # tüm rapor/özet belgeleri kök'te
  v5_tahmin_*.txt           # backtest girdi arşivi (parse-edilebilir)
  pegadrom_skorlar.json
```

`motor/` — tüm algoritmik + yardımcı py ve kalibrasyon verisi:

```text
motor/
  altili_lib.py             # BASE/MOTOR yolları, CSV+JSON+tahmin parse, load_results, birim_fiyat
  tjk_sonuc_topla.py        # TJK resmi feed sonuç parser -> Sonuclar JSON/<tarih>.json (§14.8) [BİRİNCİL]
  sonuc_txt_uret.py         # Sonuclar JSON -> Sonuçlar Txt/ okunabilir altılı blokları (§14.9-B)
  tahmin_sonuc_karsilastir.py # tahmin↔sonuç -> TahminSonuçları/ karşılaştırma (§14.9-C)
  pegadrom_sonuc_topla.py   # Pegadrom sonuç parser (İKAME EDİLDİ; çapraz-doğrulama arşivi)
  kapsamli_sistem_analizi.py# tam-aralık 5-satır+altılı+sinyal raporu (load_results, START 01.02)
  altili_kupon_v2.py        # kupon kurucu (akıllı banko, KUPON_TIERS, build_tier)
  altili_uretim.py          # altili_ayaklari + hipodrom_altili_bloku + dosya yazımı
  altili_kalibrasyon.py     # -> altili_kalibrasyon.json (kapsama eğrileri)
  altili_kalibrasyon.json   # banko gücü + cov[g] tabloları (load_cal okur)
  altili_backtest.py        # 212 altılı backtest -> altili_backtest_raporu.md (tier_policy uygular)
  bes_satir_analiz.py       # 5 satır İlk1/3/4/5 + 5-satır isabet (segment, eküri-kredili)
  pegadrom_ai_features.py
  pegadrom_ai_txt_topla.py
  pegadrom_json_ai_genis_test.py  # Codex: JSON galop alt-alan grid testi (gölge mod adayları)
  grid7_altili_dogrula.py   # grid7 tam-evren doğrulama (REDDEDİLDİ: 47-örneklem aşırı-uyum)
  seg14_galop_dogrula.py    # 12+/14+ segment-kapılı galop doğrulama (seg12 SEÇİLDİ, §4.1)
  kupon_kacan_analiz.py     # "5-satırda var, kupona girmemiş" kazanan analizi (§14.7)
  kupon_fix_test.py         # 5-satır tabanı düzeltmesi vs baseline (tier politikası, §14.7)
  _sync_skill.py            # SKILL.md gövdesini PROJE_OZETI'den senkronlar (UTF-8 güvenli)
  karsilastirmali_analiz.py # analiz aracı (5 satır vs CSV vs Pegadrom)
  sonuc_analizi.py          # 5 satır isabet ölçümü
  sinyal_testi.py           # bağımsız sinyal fizibilitesi (negatif sonuç arşivi)
```

İMPORT MEKANİZMASI: `ganyan_master.py` ve `toplu_tahmin.py` başta
`sys.path.insert(0, .../motor)` yapar; `motor` içi modüller birbirini doğrudan
import eder. `altili_lib.BASE` = motor'un üst klasörü (mutlak yol, taşımaya dayanıklı).

ÇIKTI KONVANSİYONU (her iki motor): `Harbi_Ganyan_Analiz/<GG-AA-YYYY>/` altına
`<GG-AA-YYYY>_Tahminler.txt` (5 satır + puanlar) ve `<GG-AA-YYYY>_Altili.txt`
(akıllı banko altılı kuponları, 3 kademe). `toplu_tahmin.py` ayrıca bulk
`v5_tahmin_*.txt` (backtest girdisi) üretmeye devam eder.

Veri klasörleri:

```text
CSV Sonuçlar/  (NİSAN/ MAYIS/)        # Nisan-Mayıs sonuç arşivi (altılı ödeme dahil)
Sonuclar JSON/ (YYYY-MM-DD.json)      # TJK sonuç arşivi (§14.8); birincil sonuç kaynağı
Sonuçlar Txt/  (YYYY-MM-DD.txt)       # okunabilir altılı sonuç blokları (§14.9-B)
TahminSonuçları/ (YYYY-MM-DD.txt)     # tahmin↔sonuç karşılaştırma (§14.9-C)
Pegadrom AI Analiz TXT/  (YYYY-MM-DD/ ...)
Harbi_Ganyan_Analiz/     (GG-AA-YYYY/ <...>_Tahminler.txt + <...>_Altili.txt)
```

Mevcut veri kapsamı:

- CSV: 120 dosya (2026-04 / 2026-05).
- Sonuclar JSON: 2026-02-01 - 2026-03-31 backfill + örtüşen günler (Pegadrom).
- Pegadrom AI TXT: 1052+ koşu TXT dosyası.
- Test/tahmin aralığı: 2026-02-01 - 2026-05-30 (Harbi_Ganyan_Analiz: 121 gün).

Temizlik/reorg notu (31.05.2026):

- Eski dönem bağımsız scriptler (`maiden.py`, `sartli.py`, `handikap.py`, `kv_grup.py`, `pegadrom.py`) silindi; üretimde kullanılmıyordu.
- `altili_kupon.py` (v1 kupon üreticisi) silindi; `motor/altili_kupon_v2.py` ile değişti.
- Tüm algoritmik/yardımcı py dosyaları `motor/` alt klasörüne taşındı; kök'te yalnızca `ganyan_master.py` ve `toplu_tahmin.py` kaldı.
- Çıktılar artık `Harbi_Ganyan_Analiz/<tarih>/` altında ayrı Tahminler + Altili dosyaları olarak üretilir.

---

## 10. Çıkarılan veya Pasifleştirilen Yaklaşımlar

### Eski galop sistemi

Neden çıkarıldı:

- Sprint ağırlığı yanıltıcı çıktı.
- Galop güveni ve ağırlık sistemi kazananı ayırt etmekte zayıf kaldı.
- Eski GLP tekil sinyal olarak `İlk1/İlk3/İlk4/İlk5 = 14.0% / 38.9% / 52.0% / 63.2%`.
- Ana skor içine eklenince net iyileştirme getirmedi.

Yerine:

- Pegadrom galop puanı.
- Eksikse nötr `50`.

### Gn ana skor ağırlığı

Neden çıkarıldı:

- Tekil ve kombinasyon testlerinde Pegadrom akışının sağladığı ilk5 davranışını yakalayamadı.
- `G + Gn + S` kontrol modeli yeni Pegadrom akışlı modellere göre geride kaldı.

Yerine:

- AGF yokken `G`.
- AGF varsa `AGF`.
- Her iki modda Pegadrom akışı.

### Pegadrom model puanını ana taşıyıcı yapmak

Neden yapılmadı:

- Tek başına Pegadrom model `İlk1/İlk3/İlk4 = 23.1% / 51.6% / 61.8%`.
- Yarış Akışı açık biçimde daha güçlü.

Yerine:

- Model puanı açıklama, etiketleme ve ikincil kontrol sinyali olarak tutulur.

---

## 11. Karar Kuralları

Eşleştirme:

- CSV, v6, Pegadrom karşılaştırmalarında anahtar: `(tarih, hipodrom, koşu_no, at_no)`.
- At ismi kullanılmaz.

Hipodrom normalizasyonu:

- `İSTANBUL/ISTANBUL`, `İZMİR/IZMIR` gibi Türkçe karakter farkları tek forma indirilir.
- Pegadrom URL tarafında ASCII şehir kullanılır.

Pegadrom sentetik kayıtlar:

- `0` at numarası.
- `KGS` gibi sentetik/koşu geneli kayıtlar.
- Analize dahil edilmez.

Galop:

- Eski sistem ana skorda yok.
- Pegadrom galop varsa kullanılır.
- Yoksa nötr `50`.

Kupon (GÜNCEL — §14.5 Akıllı Banko sistemi geçerlidir):

- Birim fiyat hipodroma göre: 1.25 TL (İstanbul/Ankara/İzmir/Adana/Bursa/Kocaeli/
  Antalya), 1.00 TL (Şanlıurfa/Elazığ/Diyarbakır). Bkz. `altili_lib.birim_fiyat`.
- Kademeler (01.06.2026 GÜNCEL): Simitçi 6'lısı (400-600₺), Harbi Ganyan 6'lısı
  (1000-1600₺), Ortaklı 6'lı (1600-2200₺). Kombinasyon = üst_sınır / birim.
- **İÇ İÇE (SUPERSET) KADEMELER (§14.9):** Harbi ⊇ Simitçi, Ortaklı ⊇ Harbi (ayak-ayak).
  `build_nested_tiers` ile kurulur; üst kademe alt kademenin genişliklerini taban alır,
  banko ayağı sabit. "Kazanan Harbi'de var, Ortaklı'da yok" sorununu yapısal olarak bitirir.
- Akıllı banko: her kuponda lider çıpa ayağı; güçlüyse tek-at banko, zayıfsa 2-at.
- 5-SATIR TABANI (§14.7): `tier_policy(ad)` ile Simitçi+Harbi'de akış-güvenilir
  BOM/HAR atı kupona taşınır (bütçe-nötr); Ortaklı'da kapalı. Net +3/+4/0 kupon.
- Eski garantici/avcı modları ve "ardışık banko" kuralı devre dışı (referans kod).

Kalabalık saha (14+ at) stratejisi (31.05.2026 eklendi):

- 14+ atlı sahalar yapısal olarak düşük isabetli: 5 satır ≈ %78.7 (≤9'da %95.1). Bu tavan, mevcut sinyalleri yeniden ağırlıklandırarak kırılamadı (test edildi).
- Günlük çıktıda 14+ koşular `⚠️ DÜŞÜK GÜVEN (kalabalık saha)` etiketiyle işaretlenir.
- Kupon: garantici mod 14+'ı zaten `min(6,n)` genişletiyordu; avcı moda da 14+ için (banko değilse, fark<25) `min(5,n)` genişletme eklendi.

---

## 12. Açık İyileştirme Alanları

Yakın vadede değiştirilebilecekler:

1. Pegadrom model puanı ana formülde sıfır ağırlık aldı; ama açıklayıcı etiketlerde daha görünür kullanılabilir.
2. ✅ Kalabalık koşular: 12+ segment-kapılı galop eklendi (§4.1). 14+ 5-satır %78.0→%79.8.
3. Akış ilk5 içinde olup ana skorda geriye düşen yüksek ganyanlı adaylar ayrıca işaretlenebilir. (Kupon tarafında §14.7 5-satır tabanı tam bunu yapıyor.)
4. `Harbi mi?` satırı daha akıllı seçilebilir: sadece galop değil, akış ilk5 + model/veri güveni + yüksek ganyan birleşimi denenebilir.
5. ✅ Banko eşikleri kalibre edildi (§14.5); banko disiplini (canlı sürprizli ayağı banko yapma) §14.7'de Harbi'ye eklendi.
6. ✅ Bütçe kademeleri parametrik (`KUPON_TIERS`, 01.06.2026 güncel). Kullanıcı bandı veriyor, sistem üst sınıra göre genişliyor.
7. Mobil erken mod için AGF'siz performans ayrıca günlük canlı testle izlenmeli.
8. Pegadrom TXT toplama süresi uzun tarih aralıklarında artabilir; ileride günlük cache/index kontrolü hızlandırılabilir.
9. AÇIK (Codex önerisi): JSON galop "gölge mod" — `pegadrom_skorlar.json` galop alt-alanlarının en iyi adayı ana skora alınmadan, ikinci skor olarak canlı izlenebilir (`CLAUDE_GECIS_RAPORU_2026-05-31.md` §7).
10. AÇIK: Altılı 5/6 kayıplarının ~%43'ü gerçek model tavanı (kazanan ANA rank 6+, 5-satır DIŞI). Bu ancak yeni ortogonal sinyalle kırılır, kupon genişletmeyle değil (§14.7).

---

## 13. Yol Haritası

### Faz 1 - Mevcut üretim düzenini sağlamlaştır

- `ganyan_master.py` günlük çalışma testi.
- `toplu_tahmin.py` tarih aralığı çalışma testi.
- Pegadrom TXT eksik indirme davranışını izle.
- TXT parser alanlarını birkaç rastgele koşuda manuel kontrol et.

### Faz 2 - Yeni algoritmayı yeniden backtest et (DEVAM EDİYOR)

- 2026-04-01 - 2026-05-30 aralığında güncel `toplu_tahmin.py` (eküri dahil) çıktısı üretiliyor.
- CSV sonuçları ile İlk1/İlk3/İlk4/İlk5/5Satır + altılı isabet/maliyet/net ölçülecek (eküri-kredili).
- Çıktı: `Harbi_Ganyan_Analiz/<tarih>/` + bulk `v5_tahmin_01042026-30052026.txt`.

### Faz 3 - Banko ve kupon stratejisi ✅ TAMAMLANDI (§14.5, §14.6)

- Banko gücü gerçek sonuçlarla kalibre edildi (`altili_kalibrasyon.json`): fark x alan
  segmentine göre favori-kazanma + cov[g] kapsama eğrileri.
- Akıllı banko (eşik 0.50) seçildi; eski Garantici/Avcı modları kaldırıldı.
- Eküri (stablemate) banko bonusu + ayak dedup eklendi.
- Açık: backtest banko-isabeti %48-60 ile sınırlı (favori-kazanma ~yazı-tura tavanı).

### Faz 4 - Açıklanabilir çıktı

- Her at için şu etiketler gösterilebilir:
  - Akış ilk5 içinde.
  - Pegadrom galop güçlü.
  - Model/veri güveni yüksek.
  - AGF destekli.
  - Kalabalık koşu riski.
- Kullanıcıya sadece puan değil, neden yazıldığı da anlatılmalı.

### Faz 5 - Mobil uygulama hazırlığı

- AGF'siz erken mod: `G*0.30 + Akış*0.70`.
- Yarış günü revize modu: `AGF*0.40 + Akış*0.50 + PegGalop*0.10`.
- Günlük veri toplama otomasyonu.
- Tahmin/kupon API çıktısı tasarımı.

---

## 14. Yeni Oturum İçin Hızlı Başlangıç

Yeni bir analiz veya kodlama oturumunda sırayla:

1. Bu dosyayı oku: `HARBI_GANYAN_PROJE_OZETI.md`.
2. Ana motorları incele:
   - `ganyan_master.py`
   - `toplu_tahmin.py`
3. Algoritmik altyapıyı incele (`motor/`):
   - `motor/altili_kupon_v2.py`, `motor/altili_uretim.py`, `motor/altili_lib.py`
   - `motor/pegadrom_ai_txt_topla.py`, `motor/pegadrom_ai_features.py`
4. Son raporları oku (kök): `altili_backtest_raporu.md`, `pegadrom_karsilastirma_raporu.md`.
5. Kod değiştirilecekse iki ana dosyayı senkron tut; `motor/` modüllerini ortak kullan.
6. Değişiklik sonrası en az şu kontrolü yap:

```text
python -m py_compile ganyan_master.py toplu_tahmin.py motor/*.py
```

---

## 14.5 Altılı Kupon Sistemi v2 — Akıllı Banko (31.05.2026)

Kullanıcı direktifi: her altılı kuponunda en az 1 banko/çıpa; sürprize açık
koşularda 5-satır ötesindeki atlar da kupona eklenebilmeli; banko = favori
gördüğümüz, rakiplerini geçeceğine inandığımız at.

Yeni dosyalar:

- `altili_lib.py` — v5 tahmin arşivi (KO:/5SATIR:/ATNO:) + CSV gerçek sonuç
  (kazanan/eküri/altılı ödeme) eşleştirme. Anahtar: (tarih,hipodrom,koşu,at_no).
  CSV düz ganyan kazanan regex'i `eküridir.GANYAN(8)` gibi durumları yakalar
  (negatif lookbehind: 3'LÜ/6'LI/5'Lİ hariç). Altılı ayakları = son ayak footer'ından
  geriye 6 koşu.
- `altili_kalibrasyon.py` -> `altili_kalibrasyon.json` — gerçek sonuçlarla ölçülen:
  - `fav[seg_n|seg_fark]` = favori (ANA#1) gerçek kazanma oranı (banko gücü).
  - `cov[seg_n][g]` = kazananın bizim ilk-g ANA sıralamasında olma oranı (kapsama).
  Ölçülen kapsama: ~%90 ayak isabeti için ≤7→4-5 at, 8-13→5 at, 14+→6-7 at.
- `altili_kupon_v2.py` — kupon kurucu (canlı + backtest ortak):
  - Banko AYAĞI SEÇİMİ: `banko_score = min(fark,70) + 15·(ANA1=AGF1) + 15·(ANA1=AKIS1)`
    (212 altılı taramasında en iyi banko-isabeti).
  - AKILLI BANKO (eşik 0.50): lider ayağın favori-kazanma güveni ≥0.50 ise tek-at
    banko, değilse 2-at çıpa. Tek-at banko'yu HER koşuya zorlamak %48 doğruluk →
    kuponların yarısını öldürür; eşikli kurguda tek-at banko %60 doğru.
  - Dağıtım: kalan bütçe `Δlog(cov)/Δlog(genişlik)` açgözlü oranıyla; kalabalık/
    sürprizli ayaklar genişler (CAP=8, 5-satır ötesine taşar), ezici favoriler dar.
- `altili_backtest.py` -> `altili_backtest_raporu.md` — 212 gerçek altılıya karşı
  3 bütçe kademesinde isabet/maliyet/ödeme-dönüşü + banko doğruluğu + politika kıyası.

Backtest sonucu (212 altılı, Nisan–Mayıs, 1000 TL):

| Politika | İsabet | Net | Tek-at banko doğruluğu |
|---|---:|---:|---:|
| Tam zorunlu (her koşu tek-at) | %14.2 | +104k₺ | 102/212 (%48) |
| **Akıllı banko (eşik .50) — SEÇİLDİ** | %18.9 | +344k₺ | 40/67 (%60) |
| Bankosuz (serbest) | %19.8 | +514k₺ | — |

Üretim kararı: `ganyan_master.py` altılı kuponları artık `build_tier` ile
akıllı banko (eşik 0.50) ve 3 bütçe kademesi üretir. Eski `kupon_uret`/
`ayak_genisligi`/garantici-avcı modları devre dışı (kod referans için duruyor).
Net getiriler nadir ama büyük altılı ödemeleriyle gelir; isabet oranı düşük olsa
da pozitif beklenen değer.

BİRİM FİYAT (hipodroma göre, `altili_lib.birim_fiyat`):
- 1.25 TL: İstanbul, Ankara, İzmir, Adana, Bursa, Kocaeli, Antalya
- 1.00 TL: Şanlıurfa, Elazığ, Diyarbakır

BÜTÇE KADEMELERİ (`altili_kupon_v2.KUPON_TIERS`, kupon değeri bandına hedeflenir;
kombinasyon = üst_sınır / birim) — 01.06.2026 güncellendi:
- Simitçi 6'lısı      : 400–600 TL
- Harbi Ganyan 6'lısı : 1000–1600 TL   (iç içe: ⊇ Simitçi)
- Ortaklı 6'lı        : 1600–2200 TL   (iç içe: ⊇ Harbi)

Backtest (212 altılı, hipodrom birim fiyatlı):
- Simitçi      : isabet %12.7, ort. maliyet ~480₺, net pozitif
- Harbi Ganyan : isabet %21.7, ort. maliyet ~1510₺
- Ortaklı      : isabet %23.1, ort. maliyet ~1888₺

Notlar / açık uçlar:

- Backtest, altılı ödemesini 1 birim için brüt dönüş kabul eder (yaklaşık ROI).
- Banko doğruluğu favori-kazanmanın ~yazı-tura oluşuyla sınırlı (oracle tavanı %92,
  ulaşılabilir en iyi tek-pick ~%48-60). Daha iyi banko = yeni ortogonal sinyal gerektirir.
- `toplu_tahmin.py` çıktısı (v5_tahmin_*.txt) backtest'in girdi formatıdır; senkron tut.

## 14.7 5-Satır Tabanı Düzeltmesi (01.06.2026)

Kullanıcı gözlemi: kuponlar çoğunlukla 5/6'da kalıyor. `kupon_kacan_analiz.py` ile
220 altılı analiz edildi: **5/6'da kalan Harbi kuponlarının %57'sinde kazanan aslında
5-satırımızdaydı** (en çok HAR=ANA#5 ve BOM=ANA#4) ama o ayağın kupon genişliği
< kazananın ANA-rankı olduğu için kupona girmemişti. Kök sebep: kupon kurucu ayak
genişliğini GLOBAL `cov[seg][g]` eğrisine göre veriyor; o ayaktaki BOM/HAR atının
bireysel olarak güçlü (akış lideri) olup olmadığına bakmıyor; cov g=2-3'te düzleşince
greedy o ayağı bırakıp bütçeyi başka yere harcıyor. Ayrıca 30 vakada kaçan ayak
zorunlu bankoydu (yüksek fark → banko, ama favori kaybetti, bizim BOM kazandı).

Düzeltme (`altili_kupon_v2.build_coupon`, `bes_floor` parametresi):
- `_flow_kredili_surpriz`: ayağın ANA rank-4/5 atı akış-güvenilirse (flow_rank 1..3)
  = "akış sever ama ANA gömmüş" sürpriz sinyali.
- Greedy'de `floor_bonus`: o ayağı sürprizi kapsayacak ranka taşıyan genişlemeyi
  önceliklendir (bütçe-nötr; max_komb korunur).
- `banko_kac`: canlı sürprizi olan ayağı banko yapmaktan kaçın (banko_score −30).

Tier politikası (`TIER_POLICY`, bütçe rejimine göre — `kupon_fix_test_raporu.md`):

| Tier | Politika | Sonuç (220 altılı) |
|---|---|---|
| Simitçi | floor_only (banko_kac kapalı) | 29→32 (+3), %13.2→%14.5 |
| Harbi | floor + banko disiplini | 45→49 (+4), %20.5→%22.3 |
| Ortaklı | KAPALI (baseline) | 57→57 (bol bütçede düzeltme zarar veriyor) |

Neden tier'a göre: dar/orta bütçede greedy sürprizi düşürüyor, floor ucuza geri alıyor
(net+). Ortaklı'da bütçe (2000) zaten sürprizi kapsıyor; floor sadece dağılımı bozup
iyi ayaklardan width çekiyor (kazandı 5, kaybetti 8 → net−). `altili_uretim.py` ve
`altili_backtest.py` `tier_policy(ad)` ile bu politikayı uygular; canlı + toplu + backtest senkron.

## 14.6 Eküri (Stablemate) Sistemi (31.05.2026)

Eküri = aynı sahibin kuplajlı atları; bahiste **birini yazmak diğerini de kapsar**.
Tespit kaynağı: bülten horse objesindeki **`stablemate`** bayrağı (>0) + `owner`.
Sahip çıkarımından üstündür: aynı sahip olup eküri OLMAYAN atlar stablemate=0 kalır.
CSV beyanlarıyla doğrulandı (01.04 İstanbul koşu5={1,7}, koşu8={12,14} birebir).

Uygulama (motor):
- `altili_lib.ekuri_gruplari(atlar)` -> at_no kümeleri; `ekuri_ortaklari`, `ekuri_serialize/parse`.
- Her iki motor bültenden `owner`+`stablemate` yakalar, eküri gruplarını kurar.
- `toplu_tahmin` parse-edilebilir çıktıya `EKURI:1-7|12-14` satırı yazar; `parse_tahmin_arsiv` okur.

5'li satır (ganyan_master Tahminler):
- 5 satırdan İKİSİ eküri ortağıysa her ikisi `(eküri: <isim>)` ile işaretlenir.
- Altına `➕ Eküri dışı olasılık: No:X <isim>` satırı eklenir (ANA sırasında seçililerle
  eküri OLMAYAN ilk at) — kaybedilen distinct slotu telafi için.

Altılı kupon (altili_kupon_v2):
- BANKO BONUSU: ekürili favorinin efektif güveni = kendi payı + ortağın AGF-payı
  (`banko_guven_eff`); ekürili favori daha güçlü banko (örn. SUPER TOMO %62→%70).
- AYAK DEDUP: `select_with_ekuri` — bir ayakta eküri ortağı zaten yazıldıysa onu atlar,
  yerine sıradaki distinct atı alır (aynı maliyete daha çok kapsama).
- 14+ ALAN CEZASI (31.05.2026): `banko_score` 14+ sahalara -25, 12-13'e -10 ceza uygular;
  kalabalık ayağı banko lider yapmaktan kaçınır (212 altılı: çıpa-doğru %63.2→%64.2,
  Harbi isabet %19.8→%20.3). Bkz. `iyilestirme_raporu.md`.
- GÖRÜNÜR ETİKET: `format_coupon` banko/çıpa satırında "eküri: No:X … da kapsanır"
  ve ayak altında "↳ eküri: … (kuplaj — biri yeter / otomatik kapsanır)" yazar. Bu etiketler
  motorların içindedir; çıktı için ek script gerekmez (eski `altili_yeniden_uret.py` silindi).

NOT: `toplu_tahmin` per-date `Tahminler.txt` PARSE-EDİLEBİLİR formattır; eküri verisi
`EKURI:` satırındadır ama insan-okur "(eküri: …)" işareti + "Eküri dışı olasılık" satırı
yalnızca `ganyan_master`'ın günlük (insan-okur) çıktısındadır.

Backtest değerlendirmesi: `winning_set()` kazananın eküri ortaklarını kazanan kümesine
ekler (1010 koşunun 50'si = %5 kazananı eküri grubunda). Altılı isabeti zaten eküri-kredili.

## 14.8 TJK JSON Sonuç Altyapısı (01.06.2026)

Amaç: Okunması zor CSV sonuç arşivinden kurtulup sistemi JSON sonuçlara bağlamak ve
CSV'nin kapsamadığı tarihleri (01.04.2026 öncesi) de kapsamak. Test aralığı
01.02.2026 - 30.05.2026'ya genişletildi; CSV yalnızca Nisan-Mayıs'ı kapsıyordu.

### Kaynak: TJK resmi statik JSON feed'i

Sonuçlar `atyarisi.com`'un SPA'sını kazımak yerine, onun da tükettiği **TJK resmi
feed**'inden alınır (statik JSON, lazy-load yok, at_no DOĞRUDAN gelir):

```text
https://ebayi.tjk.org/s/d/sonuclar/<YYYYMMDD>/yarislar.json     # yerli+yabancı hipodrom listesi (KEY)
https://ebayi.tjk.org/s/d/sonuclar/<YYYYMMDD>/full/<KEY>.json   # tam sonuç
```

Bir koşunun (`kosular[]`) anahtar alanları:
- `NO` = koşu no; `atlar[]` → `NO`=at_no (resmi program no), `SONUC`=bitiş sırası
  (1=kazanan), `AD`, `DERECE`, `GANYAN`, `EKURI`, `KOSMAZ`, `AGF1`, `JOKEYKODU`.
- `emiParasalNeticeler_tr` = **kombine bahis ikramiyeleri** tek string:
  `GANYAN(3): 2,30TL İKİLİ(3/5): 23,95TL SIRALI İKİLİ(3/5): 27,50TL ...`
  (ALTILI/5'Lİ/4'LÜ/3'LÜ GANYAN, ÜÇLÜ BAHİS, PLASE, PLASE İKİLİ, ÇİFTE, TABELA,
  7'Lİ PLASE/GANYAN dahil — ileride bu oyun tiplerine genişleme için hazır).

Bu kaynak CSV/Pegadrom'a üstündür: at_no hazır (köprü yok), bitiş sırası + derece +
ganyan + eküri + kosmaz + **tüm kombine ikramiyeler** tek üründe gelir.

### Toplayıcı: `motor/tjk_sonuc_topla.py`

```text
python tjk_sonuc_topla.py 2026-02-01 2026-05-30 [--force]
  -> Sonuclar JSON/<YYYY-MM-DD>.json  (gün başına bir dosya, yerli hipodromlar)
```

Çıktı şeması:
```json
{"tarih":"2026-05-15","kaynak":"tjk","hipodromlar":{"ISTANBUL":{"ad":"...","kosular":{
  "1":{"no":1,"n_at":13,"kazanan":3,"ekuri":[[8,11]],"kosmaz":[],
       "mesafe":1000,"pist":"...",
       "siralama":[{"sira":1,"at_no":3,"at":"BARLİN AĞA","derece":"1.05.24",
                    "ganyan":2.30,"jokey_kodu":...,"agf":...}, ...],
       "bahisler":{"raw":"GANYAN(3): 2,30TL ...",
                   "kalemler":[{"tip":"GANYAN","kombinasyon":"3","tutar":2.30}, ...]}}}}}}
```

Doğrulama: 2026-05-15 (İstanbul 9 + Bursa 10 koşu) JSON kazananları CSV ile
**19/19 birebir** uyuştu; eküri, kosmaz ve altılı ikramiye (`12.948,06TL` vb.) doğru.

NOT: `motor/pegadrom_sonuc_topla.py` (Pegadrom kazıyıcı, kosu_kod + X-PGD-Partial
header mekanizması) artık **ikame edildi** (Pegadrom altılı/ikili/üçlü ödeme vermiyordu).
Bağımsız çapraz-doğrulama için arşivde tutuluyor.

### Tüketici tarafı: `altili_lib.py`
- `load_all_json(dir)` — `Sonuclar JSON/*.json` → `load_all_csv` ile **aynı şekil**
  (`kazanan`, `ekuri`, `n_at`, `altililar`, ayrıca `siralama`, `kazanan_ad`).
  **Altılı ödemeleri** TJK bahisler'inden (`6'LI GANYAN`) türetilir → `altililar`
  (idx, last, legs, odeme) dolu gelir; JSON artık altılı ROI dahil tam-özellikli.
  `winning_set()` JSON objeleriyle de çalışır.
- `load_results(prefer="csv")` — **birleşik yükleyici**: CSV taban (doğrulanmış Nisan-Mayıs),
  eksik (tarih,hip) JSON ile tamamlanır. `prefer="json"` tersi (tam aralık TJK).
- **Berabere (dead-heat):** Resmi `GANYAN(n)` ödemesi birden çok at için varsa hepsi
  birinci sayılır → `kazananlar` (build_kosu) + `berabere` (parse_json_sonuc); `winning_set`
  bunları kazanan kümesine katar. (Örn. 2026-04-19 ADANA K4: at 5 ve 10 berabere; CSV
  yalnız 10'u kaydetmişti → TJK JSON daha doğru.)

### Doğrulama (tam aralık)
- Toplam: 119 gün, 1929 koşu, 237 (tarih,hip), 01.02-30.05.2026.
- CSV-örtüşen 1008 koşuda kazanan: 1007 birebir + 1 berabere (TJK lehine doğru) = **%100**.
- TJK bahisler'inden türetilen altılı (ödemeli): 433.

### Tam-aralık skorlamaya bağlanan tüketiciler
- `kupon_kacan_analiz.py`: altılı ayak tanımları artık CSV'den DEĞİL,
  `derive_altililar()` ile `Harbi_Ganyan_Analiz/*/*_Altili.txt` başlıklarından
  ("🎰 HIP …", "ALTILI GANYAN (Koşular A-B)") türetilir → 121 klasör, tam aralık.
  Sonuçlar `load_results(prefer="csv")`'ten.
- `bes_satir_analiz.py`, `kapsamli_sistem_analizi.py`: `load_results(prefer="csv")`'e
  geçti; `kapsamli` START 01.02.2026'ya çekildi.
- DEĞİŞMEDİ (bilerek): `altili_backtest.py` (CSV altılı-ödeme/ROI aracı) ve doğrulama
  harness'leri (`*_dogrula.py`, `kupon_fix_test.py`, `pegadrom_json_ai_genis_test.py`)
  sabit CSV evrenini korur.

## 14.9 İç İçe Kademeler + Sonuç/Karşılaştırma Çıktıları (01.06.2026)

Kullanıcı `ŞABLON ÖRNEKLEM` direktifi — üç parça:

### (A) İç içe (superset) bütçe kademeleri — STRATEJİK HATA DÜZELTMESİ
Önceki kademeler bağımsız kuruluyordu; bir at Harbi ayağında olup Ortaklı ayağında
OLMAYABİLİYORDU (kazanan sürpriz at Harbi'de var, Ortaklı'da yok → mantıksız altılı kaybı).
Düzeltme: kademeler artan bütçeyle **iç içe** kurulur — Ortaklı ⊇ Harbi ⊇ Simitçi (her ayakta).
- `altili_kupon_v2.build_nested_tiers(legs, tiers, birim, cal, banko_esik)`:
  her üst kademe alt kademenin ayak genişliklerini `min_width` TABAN alır ve yalnızca genişler;
  seçim ANA-sıralı prefix olduğundan genişlik ≥ ise seçim otomatik superset olur.
  **Banko ayağı ilk (en dar) kademede seçilir, tüm kademelerde SABİT** (`fixed_banko`).
- `build_coupon`'a `min_width` + `fixed_banko` parametreleri eklendi (geriye-uyumlu; eski
  tekil `build_tier` yolu korunur — backtest/kupon_kacan etkilenmez).
- Bütçeler: Simitçi 400-600, **Harbi 1000-1600**, **Ortaklı 1600-2200** (KUPON_TIERS).
- `altili_uretim.hipodrom_altili_bloku` artık `build_nested_tiers` kullanır → üretimdeki
  tüm altılı kuponları iç içe. Doğrulama: 3 gerçek altılıda S⊆H⊆O = True.

### (B) `Sonuçlar Txt/` — okunabilir sonuç blokları (`motor/sonuc_txt_uret.py`)
`Sonuclar JSON`'u altılı-bazlı okunabilir bloklara çevirir: her ayağın kazananı +
ganyan/ikili/sıralı ikili/çifte/üçlü ödemeleri, altılı sonucu (`w1/.../w6`) + İKRAMİYE
BEDELİ, ve büyük kombineler (5'Lİ/4'LÜ/3'LÜ/7'Lİ GANYAN, TABELA). 119 gün üretildi.

### (C) `TahminSonuçları/` — karşılaştırmalı sonuç (`motor/tahmin_sonuc_karsilastir.py`)
Tahminleri (5 satır) JSON sonuçlarıyla karşılaştırır:
- Her koşu: 5 satır + kazanan slotunda ✅; KAZANAN bahis satırı.
- Her altılı: sonuç + 3 iç içe kupon (`build_nested_tiers` ile YENİDEN kurulur),
  ayak-ayak ✓/✗, kazanan `[parantez]`, ve "TAHMİNİMİZ N'TE KALDI / TUTTU (6/6)".
- Sonuç kaynağı `load_results(prefer="json")`; tahmin kaynağı `parse_tahminler_dir`
  (KO:/5SATIR:/ATNO: parse-edilebilir format = `toplu_tahmin.py` çıktısı).
- NOT: erken Şubat-Mart tahminleri `ganyan_master` insan-okur formatında; karşılaştırma
  için kullanıcı aralığı `toplu_tahmin.py` ile YENİDEN üretmeli (parse-edilebilir format).

## 15. Kritik Hatırlatmalar

- Veriyle test edilmemiş ağırlık üretime alınmaz.
- Eküri SADECE `stablemate` bayrağından tespit edilir; sahip eşitliğinden ÇIKARSANMAZ.
- At adı eşleştirme anahtarı değildir.
- Pegadrom akışı şu an sistemdeki en kritik yeni sinyaldir.
- Eski galop güven sistemi geri getirilmemelidir.
- `Gn` tekrar ana skora eklenmemelidir; önce yeni test gerekir.
- Pegadrom galop eksikse ceza verilmez, nötr kabul edilir.
- `ganyan_master.py` ve `toplu_tahmin.py` ayrı yönlere evrilmemelidir.
- Altılı kuponu artık akıllı banko (eşik 0.50) ile kurulur; tam-zorunlu tek-at
  banko net getiriyi ~3'te 1'e düşürdüğü için seçilmedi (212 altılı backtest).
- Kupon kalibrasyonu (`altili_kalibrasyon.json`) yeni CSV geldikçe yenilenmelidir.
- 12+ segment-kapılı galop SADECE n_at≥12'de açılır; global uygulanırsa İlk1/≤9 bozulur (§4.1).
- 5-satır tabanı düzeltmesi tier'a göredir (`tier_policy`): Ortaklı'da KAPALI; bol bütçede zarar verir (§14.7).
- Altılı kuponları İÇ İÇE kurulur (`build_nested_tiers`): Ortaklı ⊇ Harbi ⊇ Simitçi; banko ayağı tüm kademelerde sabit (§14.9).
- TahminSonuçları karşılaştırması parse-edilebilir tahmin (KO:/5SATIR:/ATNO:) bekler; aralığı `toplu_tahmin.py` ile üret (§14.9-C).
- `pegadrom_skorlar.json` SİLİNMEZ (galop ana skor + 12+ galop alt-alanlarını besler; yedeği yok).
- SKILL.md güncellenirken `motor/_sync_skill.py` kullan (UTF-8 güvenli); PowerShell `Get-Content -Raw` Türkçe'yi bozar.
- Sonuç kaynağı artık JSON+CSV birleşik (`load_results`). `Sonuclar JSON/` SİLİNMEZ (Şubat-Mart'ın tek sonuç kaynağı).
- Birincil sonuç kaynağı TJK resmi feed'i (`tjk_sonuc_topla.py`); at_no doğrudan `NO` alanında gelir, isim/at_id köprüsü gerekmez (§14.8).
- Kombine bahis ikramiyeleri TJK `emiParasalNeticeler_tr`'de; altılı ödemesi JSON `altililar`'a türetilir (ROI tam aralıkta çalışır).
- Pegadrom kazıyıcı ikame edildi (altılı/ikili/üçlü ödeme vermiyordu); `pegadrom_sonuc_topla.py` yalnızca çapraz-doğrulama için.
- Belge güncellenmeden büyük algoritma kararı tamamlanmış sayılmaz.

---

## 16. Oturum Değişiklik Günlüğü

### 01.06.2026 (Claude — Codex turundan sonra)

1. **12+ segment-kapılı galop (§4.1) ÜRETİME ALINDI.** grid7 altılı iddiası tam evrende
   reddedildi (47-örneklem aşırı-uyum); aynı sinyal segment-kapılı uygulanınca 5'liyi
   düzeltti: 14+ %78.0→%79.8, 10-13 %89.7→%90.8, genel %90.3→%91.0, HAR %40.5→%42.7.
   `ganyan_master.hesapla` + `toplu_tahmin.hesapla` senkron; galop `en_iyi`/`istikrar` çekiliyor.
2. **Bütçe kademeleri güncellendi:** Simitçi 400-600, Harbi 800-1600, Ortaklı 1200-2000.
3. **5-satır tabanı kupon düzeltmesi (§14.7) ÜRETİME ALINDI.** Analiz: 5/6'da kalan Harbi
   kuponlarının %57'sinde kazanan 5-satırdaydı ama dar ayak yüzünden dışarıdaydı. Düzeltme
   (`bes_floor`, tier_policy): Simitçi +3 (%14.5), Harbi +4 (%22.3), Ortaklı kapalı.
4. Yeni analiz/test script'leri: `grid7_altili_dogrula.py`, `seg14_galop_dogrula.py`,
   `kupon_kacan_analiz.py`, `kupon_fix_test.py`, `_sync_skill.py`. Raporlar kökte.
5. Codex turu (31.05): altılı TXT şablonu, banko eşik testi, JSON galop geniş testi
   (`CLAUDE_GECIS_RAPORU_2026-05-31.md`). Üretim algoritması o turda değişmemişti.

### 01.06.2026 (Claude — Pegadrom JSON sonuç altyapısı)

1. **`motor/pegadrom_sonuc_topla.py` YAZILDI (§14.8):** Pegadrom `sonuclar`+`galoplar`
   sayfalarından sonuç çeken parser. Çıktı: `Sonuclar JSON/<tarih>.json` (kazanan, eküri,
   n_at, tam varış sırası + ganyan). 2026-05-15 kazananları CSV ile **19/19** doğrulandı.
2. **CSV→JSON geçişi:** `altili_lib.load_all_json` + `load_results(prefer=...)` eklendi
   (CSV ile aynı şekil; `winning_set` uyumlu). Birleşik: CSV taban + JSON tamamlama.
3. **Tam-aralık skorlama:** `kupon_kacan_analiz` artık altılı tanımlarını `_Altili.txt`'ten
   türetiyor (`derive_altililar`) ve `load_results` kullanıyor; `bes_satir_analiz` ve
   `kapsamli_sistem_analizi` de `load_results`'a geçti (START 01.02.2026).
4. **Backfill:** 01.02.2026 - 31.03.2026 sonuçları Pegadrom'dan JSON'a toplandı (CSV'nin
   kapsamadığı aralık). Teknik kilit: lazy body `kosu_kod` + `X-PGD-Partial` header.
5. DEĞİŞMEYEN: `altili_backtest.py` (CSV-ROI) ve doğrulama harness'leri sabit CSV evreninde.

### 01.06.2026 (Claude — sonuç kaynağı TJK feed'ine geçti)

1. **`motor/tjk_sonuc_topla.py` YAZILDI (§14.8) — BİRİNCİL sonuç kaynağı.** Sonuçlar
   atyarisi SPA'sı yerine onun da tükettiği TJK resmi feed'inden
   (`ebayi.tjk.org/s/d/sonuclar/...`) alınır. at_no DOĞRUDAN gelir (köprü yok) +
   **tüm kombine bahis ikramiyeleri** (altılı/5'li/üçlü ganyan, ikili, sıralı ikili,
   plase, çifte, tabela) `emiParasalNeticeler_tr`'de. 19/19 kazanan CSV ile doğrulandı.
2. **`pegadrom_sonuc_topla.py` İKAME EDİLDİ** (Pegadrom kombine ödeme vermiyordu);
   çapraz-doğrulama için arşivde kaldı.
3. **`altili_lib.parse_json_sonuc`** TJK bahisler'inden `altililar` (altılı ödeme) türetir
   → JSON yolu altılı ROI dahil tam-özellikli; CSV'yi tümüyle ikame eder.
4. Tam aralık (01.02 - 30.05.2026) TJK JSON'a toplandı (`--force`, Pegadrom günlerinin üzerine).

### 01.06.2026 (Claude — iç içe kademeler + sonuç/karşılaştırma çıktıları, §14.9)

1. **İÇ İÇE KADEMELER (stratejik hata düzeltmesi):** Altılı kuponları artık
   `build_nested_tiers` ile kurulur — Ortaklı ⊇ Harbi ⊇ Simitçi (ayak-ayak), banko sabit.
   "Kazanan Harbi'de var Ortaklı'da yok" yapısal olarak bitti. `build_coupon`'a
   `min_width`+`fixed_banko` eklendi (geriye-uyumlu).
2. **Bütçeler güncellendi:** Simitçi 400-600, Harbi 1000-1600, Ortaklı 1600-2200.
3. **`Sonuçlar Txt/`** (`sonuc_txt_uret.py`): JSON → okunabilir altılı sonuç blokları
   (kazananlar + tüm bahis ödemeleri + İKRAMİYE BEDELİ). 119 gün üretildi.
4. **`TahminSonuçları/`** (`tahmin_sonuc_karsilastir.py`): 5 satır + iç içe 6'lılar vs
   JSON sonuçları, ✅/✓/✗ işaretli karşılaştırma. Kullanıcı aralığı `toplu_tahmin.py` ile
   yeniden üretince tam çalışır.

