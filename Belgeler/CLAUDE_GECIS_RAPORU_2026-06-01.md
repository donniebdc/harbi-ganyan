# CLAUDE CODE GEÇİŞ RAPORU - 2026-06-01

Bu rapor, Codex oturumunda yapılan son işleri ve Claude Code tarafında devam edilmesi gereken noktaları özetler.

## 1. Bağlam

Çalışma klasörü:

```text
D:\Ganyan Gemini
```

Kritik güncel dosyalar:

- `Belgeler/HARBI_GANYAN_PROJE_OZETI.md`
- `.agents/skills/harbi_ganyan/SKILL.md`
- `ganyan_master.py`
- `toplu_tahmin.py`
- `motor/altili_kupon_v2.py`
- `motor/altili_uretim.py`
- `motor/kupon_kacan_analiz.py`
- `motor/tahmin_sonuc_karsilastir.py`
- `motor/altili_bes_satir_derin_analiz.py`
- `Raporlar/altili_bes_satir_derin_analiz_raporu.md`

Kullanıcı hedefi:

- 5 satırlı tahminlerde yakalanan kazananları 6'lı ganyan kuponlarına daha doğru aktarmak.
- Simitçi, Harbi ve Ortaklı kuponlarını iç içe tutmak:
  - `Simitçi ⊆ Harbi`
  - `Harbi ⊆ Ortaklı`
- Bütçe bantları:
  - Simitçi: 400-600 TL
  - Harbi: 1000-1600 TL
  - Ortaklı: 1600-2500 TL

## 2. Bu Oturumda Yapılanlar

### 2.1 15.03.2026 ADANA Eksik Görünen 5 Satır İncelemesi

Kullanıcı `D:\Ganyan Gemini\TahminSonuçları\2026-03-15.txt` dosyasında ADANA 2. koşudan sonra 5 satırlı tahmin karşılaştırmasının görünmediğini bildirdi.

Kontrol edilen dosyalar:

- `TahminSonuçları/2026-03-15.txt`
- `Harbi_Ganyan_Analiz/15-03-2026/15-03-2026_Tahminler.txt`
- `Harbi_Ganyan_Analiz/15-03-2026/15-03-2026_Altili.txt`
- `Sonuclar JSON/2026-03-15.json`

Sonuç:

- Tahmin dosyasında ADANA 1-8 koşularının tamamı var.
- Sorun tahmin üretiminde değil.
- TJK sonuç JSON'u `--force` ile yeniden çekildi:

```text
python motor\tjk_sonuc_topla.py 2026-03-15 2026-03-15 --force --delay 0.2
```

- Resmi TJK feed ADANA için sadece 2 koşu sonucu döndürüyor.
- IZMIR için 9 koşu sonucu dönüyor.
- Bu yüzden `TahminSonuçları/2026-03-15.txt` ADANA bölümünde 2. koşudan sonra 5 satır karşılaştırma bloğu basılmıyor.

Benzer dosya taraması:

- `TahminSonuçları` içinde altılı sonuç satırında `?` kalan tek dosya `2026-03-15.txt`.
- Bu dosyadaki `?` sebebi yine ADANA sonuç feed'inin 2 koşuyla sınırlı dönmesi.

### 2.2 Üç Testin Özeti

Önceki analiz scripti:

```text
motor/altili_bes_satir_derin_analiz.py
```

Rapor:

```text
Raporlar/altili_bes_satir_derin_analiz_raporu.md
```

Kullanıcının istediği üç test:

| Test | Mantık | Sonuç |
|---|---|---:|
| Test 1 | Her 6'lıda en az 1 banko; diğer ayakları daha geniş yaz | 125/433, %28.9 |
| Test 2 | En az 1 banko + bir ayakta max 2 favori; kalan ayakları genişlet | 125/433, %28.9 |
| Test 3 | Handikap / maiden / şartlı koşuları mümkün olduğunca genişlet | 147/433, %33.9 |
| Test 3, 3000 TL | Aynı mantık, daha yüksek üst bütçe | 149/433, %34.4 |

Mevcut eski Ortaklı referansı:

```text
107/433 = %24.7
```

En güvenli grid adayı:

```text
ortakli_2500_sadece_ekle = 115/433 = %26.6
```

Bu aday mevcut Ortaklı kuponu bozmaz, sadece 2500 TL'ye kadar eksik 5 satır atlarını ekler ve analizde kayıp üretmez.

### 2.3 Test 3 Mantığı Üretime Alındı

Değiştirilen ana dosya:

```text
motor/altili_kupon_v2.py
```

Eklenen fonksiyon:

```python
apply_test3_tip_genis_ortakli()
```

Üretim mantığı:

- Ortaklı üst bütçe 2200 TL'den 2500 TL'ye çıkarıldı.
- Ortaklı kupon Harbi kuponu zorunlu taban alıyor.
- Yani `Harbi ⊆ Ortaklı` kuralı bozulmuyor.
- Genişletme sırası:
  1. Handikap / maiden / şartlı ayakları önce 5 ata, sonra 6-7 ata genişlet.
  2. Kalan bütçeyle 5 satırda olup kupona girmeyen atları ekle.
  3. Bütçe kalırsa aynı riskli koşu tiplerini `CAP=8` sınırına kadar derinleştir.

Teknik veri taşıma değişiklikleri:

- `motor/altili_uretim.py`
  - `legs` içine `race_type`, `race_subtype`, `bes_nos` taşındı.
- `toplu_tahmin.py`
  - `bes_secim` oluşturulup `kosu_verileri[kno]['bes_nos']` içine yazıldı.
  - `race_type` ve `race_subtype` kupon verisine yazıldı.
- `ganyan_master.py`
  - Aynı veri taşıma tekli tahmin tarafına da eklendi.
- `motor/kupon_kacan_analiz.py`
  - Karşılaştırma üreticisi için `leg_from_race()` artık `bes_nos` taşıyor.

### 2.4 Toplu Tahmin Yeniden Üretildi

Çalıştırılan komut:

```text
python toplu_tahmin.py
Başlangıç: 01.02.2026
Bitiş: 30.05.2026
```

Üretilen çıktılar:

- `Harbi_Ganyan_Analiz/<GG-AA-YYYY>/<GG-AA-YYYY>_Tahminler.txt`
- `Harbi_Ganyan_Analiz/<GG-AA-YYYY>/<GG-AA-YYYY>_Altili.txt`
- `Toplu Tahminler/v5_tahmin_01022026-30052026.txt`
- `TahminSonuçları/<YYYY-MM-DD>.txt`

Son kontrol:

- `TahminSonuçları`: 119 dosya.
- Tarih aralığı: `2026-02-01` - `2026-05-30`.
- `2026-05-30` için ANKARA, İZMİR ve DİYARBAKIR altılı blokları üretildi.
- `?` kalan sonuç dosyası: sadece `2026-03-15.txt`.

Derleme kontrolü:

```text
python -m py_compile motor\altili_kupon_v2.py motor\altili_uretim.py motor\kupon_kacan_analiz.py toplu_tahmin.py ganyan_master.py motor\tahmin_sonuc_karsilastir.py
```

Başarılı.

## 3. Güncel Üretim Sonucu

Son `TahminSonuçları` sanity sayımı:

| Kademe | 6/6 | Oran |
|---|---:|---:|
| Simitçi | 58/435 | %13.3 |
| Harbi | 95/435 | %21.8 |
| Ortaklı | 112/435 | %25.7 |

Genel doğru ayak dağılımı:

```text
0/6 = 3
1/6 = 4
2/6 = 35
3/6 = 119
4/6 = 368
5/6 = 511
6/6 = 265
```

Not:

- Bu dağılım üç kademe toplam satırlarını içerir.
- Ortaklı üretim sonucu eski sisteme göre yükseldi.
- Eski mevcut Ortaklı / herhangi biri: `107/433 = %24.7`
- Güncel üretim Ortaklı: yaklaşık `112/435 = %25.7`
- Net artış: yaklaşık `+5 kupon`, `+1.0 / +1.2 puan`.

## 4. Yapılamayan / Eksik Kalan Nokta

Analizdeki serbest Test 3 sonucu çok daha yüksekti:

```text
147/433 = %33.9
```

Fakat üretime birebir taşınmadı. Sebep:

- Analizdeki serbest Test 3, iç içe kupon kuralını tam korumuyordu.
- Kullanıcının ana ürün kuralı ise şu:

```text
Simitçi ⊆ Harbi ⊆ Ortaklı
```

Bu kural korununca Test 3'ün agresif dağıtımı sınırlanıyor ve güncel üretim `112/435` seviyesinde kalıyor.

Bu kritik karar noktasıdır:

- İç içe kural korunursa daha tutarlı ürün yapısı var ama isabet artışı sınırlı.
- Serbest/agresif Test 3 daha yüksek isabet veriyor ama üst kupon alt kuponu birebir kapsamayabilir.

## 5. Claude Code İçin Önerilen Sonraki İşler

### 5.1 En Güvenli Üretim Adayını Değerlendir

Raporda en güvenli aday:

```text
ortakli_2500_sadece_ekle = 115/433 = %26.6
```

Özelliği:

- Mevcut Ortaklı kuponu bozmaz.
- 2500 TL'ye kadar sadece eksik 5 satır atlarını ekler.
- Analizde kayıp üretmedi: `+8 kazanılan`, `-0 kaybedilen`.

Claude için görev:

- Bu varyantı üretim kodunda opsiyonel veya varsayılan olarak dene.
- Güncel `TahminSonuçları` ile tekrar ölç.
- Eğer `112/435` üstüne net çıkıyorsa Test 3 üretim kuralı yerine bunu kullanmak daha mantıklı olabilir.

### 5.2 İç İçe Kuralı Koruyan Daha İyi Test 3 Türevi Geliştir

Amaç:

- `Simitçi ⊆ Harbi ⊆ Ortaklı` bozulmasın.
- Ama Ortaklı 112/435 seviyesinden 115+ seviyesine çıksın.

Denenecek fikirler:

- Harbi planı taban alınsın.
- Önce mevcut Ortaklı eski greedy planı ile union alınsın.
- Sonra kalan bütçe:
  1. Eksik 5 satır atlarına,
  2. Handikap/maiden/şartlı ayaklara,
  3. 5/6 kaybettiren ayak tiplerine dağıtılsın.

### 5.3 Banko Kuralını Tekrar Ayrı Test Et

Kullanıcı banko görmeyi önemsiyor ama yanlış banko kuponu öldürüyor.

Öneri:

- Banko seçimi ile kupon genişletmeyi ayrı optimize et.
- Her 6'lıda illa banko yerine:
  - güçlü banko,
  - yarı banko,
  - banko yok ama dar ayak
  gibi üç mod test edilmeli.

Önceki testlerde banko agresifliği tek başına bazı kuponları düşürdü.

### 5.4 5/6 Kalan Kuponları Hedefleyen Mikro Analiz

Şu an en büyük fırsat:

```text
5/6 kalan kupon sayısı çok yüksek.
```

Claude için öneri:

- Her 5/6 kalan Ortaklı kuponda kaybeden tek ayağı çıkar.
- O ayağın kazananı:
  - 5 satırda mıydı?
  - ANA rank kaçtı?
  - yarış tipi neydi?
  - n_at kaçtı?
  - fark kaçtı?
  - Pegadrom akış rank kaçtı?
  - AGF sırası kaçtı?
- Bu kayıp ayağa göre hedefli ekleme kuralı çıkar.

Bu genel genişletmeden daha verimli olabilir.

## 6. Dikkat Edilecekler

- Git çalışma ağacında Claude tarafından yapılmış çok sayıda önceki değişiklik var. Geri alınmamalı.
- Kök rapor dosyalarının bir kısmı `Belgeler/` ve `Raporlar/` altına taşınmış görünüyor.
- `git status` çok kalabalık; silinmiş görünen kök rapor dosyaları muhtemelen klasör düzenlemesinden kaynaklı.
- Kod değiştirirken `ganyan_master.py` ve `toplu_tahmin.py` senkron tutulmalı.
- Büyük toplu tahmin çalıştırması yaklaşık 14-15 dakika sürdü.

## 7. Son Karar Özeti

Şu an üretimdeki durum:

- 5 satır ana tahmin algoritması değişmedi.
- Değişen ana şey Ortaklı kupon dağıtımı.
- Ortaklı başarı eskiye göre yükseldi ama Test 3'ün serbest analiz seviyesine ulaşmadı.

Önerilen bir sonraki karar:

```text
Test 3 üretim kuralı mı kalacak,
yoksa ortakli_2500_sadece_ekle varyantı mı üretime alınacak?
```

Veriye göre kısa cevap:

- En güvenli üretim adayı: `ortakli_2500_sadece_ekle`.
- En yüksek teorik sıçrama: serbest `test3_tip_genis_2500`.
- Ürün kuralı korunarak şu anki üretim: sınırlı ama pozitif artış.

