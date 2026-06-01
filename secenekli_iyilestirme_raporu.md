# Seçenekli İyileştirme Raporu

Kapsam: 01.04.2026 - 30.05.2026  
Kaynaklar: `Harbi_Ganyan_Analiz`, `CSV Sonuçlar`, `Pegadrom AI Analiz TXT`, `pegadrom_skorlar.json`, `v5_tahmin_01042026-30052026.txt`

Bu rapor üretim kodunu değiştirmeden mevcut veri evreninde yapılan simülasyonlara dayanır. 5 satır için 1050 eşleşen koşu, altılı için 220 eşleşen altılı kullanıldı.

---

## 1. Mevcut Durum

### 5 Satırlı Tahmin

| Metrik | Mevcut |
|---|---:|
| İlk1 | %38.0 |
| İlk3 | %73.5 |
| İlk4 | %84.0 |
| İlk5 | %90.2 |
| 5 satır isabet | **%90.4** |

Segment:

| Segment | n | 5 satır |
|---|---:|---:|
| <=9 at | 501 | %95.4 |
| 10-13 at | 374 | %89.6 |
| 14+ at | 175 | %77.7 |

Sonuç: 5 satırda genel oran iyi. Ana açık 14+ kalabalık sahalar.

### Altılı Ganyan

Mevcut üretilmiş kupon dosyaları üzerinden:

| Kademe | İsabet | Ortalama maliyet | Net |
|---|---:|---:|---:|
| Simitçi | 30/220 = %13.6 | 480 TL | +260.222 TL |
| Harbi | 45/220 = %20.5 | 1.547 TL | +530.761 TL |
| Ortaklı | 58/220 = %26.4 | 1.930 TL | +657.987 TL |

---

## 2. 5 Satır İçin Seçenekler

5 satır tarafında mevcut HAR kuralı tekrar test edildi:

- Mevcut HAR: 14+ sahada top4 dışından en iyi Pegadrom akış rank, diğer sahalarda ana skor 5. at.
- Top4 dışı kazanan sayısı: 168.
- HAR yakalama: 67/168 = %39.9.

Test edilen alternatif HAR kuralları:

| HAR kuralı | 5 satır isabet | Mevcuda fark |
|---|---:|---:|
| Mevcut segmentli HAR | **%90.4** | 0 |
| Her koşuda ana skor 5. at | %90.2 | -0.2 puan |
| Her koşuda en iyi akış rank | %89.4 | -1.0 puan |
| Top4 dışı en yüksek AGF | %89.1 | -1.3 puan |
| Top4 dışı en yüksek Pegadrom model | %87.1 | -3.3 puan |
| Top4 dışı en yüksek galop | %87.3 | -3.1 puan |
| Top4 dışı Pegadrom hız | %87.4 - %87.5 | -2.9 puan |

### 5 Satır Kararı

Üretim değişikliği önerisi: **yok**.

Beklenen iyileştirme:

| Seçenek | 5 satır etkisi |
|---|---:|
| Mevcut HAR kuralını koru | 0 |
| Alternatif HAR kurallarına geç | -0.2 ila -3.3 puan |
| 14+ için 6. “geniş kupon adayı” etiketi ekle | 5 satır metriğini değiştirmez; kupon kapsamasına katkı sağlar |

Bu nedenle 5 satırı bozacak bir değişiklik yapılmamalı. İyileştirme altılı kupon tarafında aranmalı.

---

## 3. Altılı İçin Test Edilen Seçenekler

Referans: mevcut sistem.

### Seçenek A - Ortaklı kademeyi ana öneri yapmak

Kod değişikliği gerektirmez; sunum/ürün kararıdır.

| Kademe | Mevcut isabet | Harbi'ye göre fark |
|---|---:|---:|
| Harbi | %20.5 | referans |
| Ortaklı | **%26.4** | **+5.9 puan / göreli +%28.8** |

Etkisi:

- 5 satır: 0.
- Altılı: Harbi yerine Ortaklı ana öneri yapılırsa isabet beklentisi %20.5 -> %26.4.
- Maliyet: ortalama 1.547 TL -> 1.930 TL.

Karar: **düşük riskli, hemen uygulanabilir.**

---

### Seçenek B - Tek-at bankoyu AGF kapısına bağlamak

Kural:

- Tek-at banko yalnızca favori aynı zamanda AGF lideri ve AGF eşiği yüksekse açık kalsın.
- Aksi durumda lider ayak 2 atlı çıpaya dönsün.

Simülasyon:

| Kademe | Mevcut | AGF>=40 | AGF>=50 |
|---|---:|---:|---:|
| Simitçi | %13.6 | %13.6 | **%14.5** |
| Harbi | %20.5 | %20.9 | **%22.3** |
| Ortaklı | %26.4 | %26.8 | **%28.2** |

AGF>=50 eşiğinin tahmini katkısı:

| Kademe | Mutlak artış | Göreli artış |
|---|---:|---:|
| Simitçi | +0.9 puan | +%6.7 |
| Harbi | +1.8 puan | +%8.9 |
| Ortaklı | +1.8 puan | +%6.9 |

Ek not:

- Banko/çıpa doğruluğu %64.5 -> %66.8.
- Ortalama maliyet mevcut banda yakın kalıyor.

Karar: **üretime alınmaya en uygun algoritmik değişiklik.**

---

### Seçenek C - 14+ ayaklarda minimum genişlik 6

Kural:

- 14+ atlı ve banko lider olmayan ayaklarda genişlik en az 6 olsun.
- Bütçe aşılırsa diğer ayaklardan daraltma yapılsın.

Simülasyon:

| Kademe | Mevcut | Min14=6 | Mutlak artış | Göreli artış |
|---|---:|---:|---:|---:|
| Simitçi | %13.6 | %14.5 | +0.9 puan | +%6.7 |
| Harbi | %20.5 | %22.7 | +2.3 puan | +%11.1 |
| Ortaklı | %26.4 | %27.7 | +1.4 puan | +%5.2 |

Maliyet:

| Kademe | Mevcut ort. maliyet | Min14=6 ort. maliyet |
|---|---:|---:|
| Simitçi | 480 TL | 618 TL |
| Harbi | 1.547 TL | 1.498 TL |
| Ortaklı | 1.930 TL | 1.884 TL |

Not: Simitçi bandı maliyet olarak aşılabiliyor. Harbi/Ortaklı tarafında daha uygulanabilir.

Karar: **Harbi ve Ortaklı için test edilerek üretime alınabilir; Simitçi için bütçe aşımı kontrolü gerekir.**

---

### Seçenek D - 14+ ayaklarda minimum genişlik 7

Simülasyon:

| Kademe | Mevcut | Min14=7 | Mutlak artış | Göreli artış |
|---|---:|---:|---:|---:|
| Simitçi | %13.6 | %15.5 | +1.8 puan | +%13.3 |
| Harbi | %20.5 | %24.5 | +4.1 puan | +%20.0 |
| Ortaklı | %26.4 | %28.2 | +1.8 puan | +%6.9 |

Maliyet:

| Kademe | Mevcut ort. maliyet | Min14=7 ort. maliyet |
|---|---:|---:|
| Simitçi | 480 TL | 853 TL |
| Harbi | 1.547 TL | 1.712 TL |
| Ortaklı | 1.930 TL | 2.045 TL |

Karar: **isabeti artırıyor ama bütçe bandını aşıyor.** Üretime ancak “geniş/özel riskli gün” modu olarak alınmalı.

---

### Seçenek E - AGF>=50 kapısı + 14+ minimum genişlik 6

Birleşik kural:

- Tek-at banko için AGF>=50 şartı.
- 14+ banko olmayan ayakta minimum 6 at.

Simülasyon:

| Kademe | Mevcut | Birleşik seçenek | Mutlak artış | Göreli artış | Ortalama maliyet |
|---|---:|---:|---:|---:|---:|
| Simitçi | %13.6 | %15.0 | +1.4 puan | +%10.0 | 880 TL |
| Harbi | %20.5 | %24.5 | +4.1 puan | +%20.0 | 1.698 TL |
| Ortaklı | %26.4 | %29.5 | +3.2 puan | +%12.1 | 2.071 TL |

Karar:

- İsabet tarafında en dengeli ciddi artış.
- Fakat üç kademede de hedef üst sınıra yaklaşır veya aşar.
- “Standart üretim” değil, “Genişletilmiş ciddi oyun” modu olarak tasarlanmalı.

---

### Seçenek F - AGF>=50 kapısı + 14+ minimum genişlik 7

Simülasyon:

| Kademe | Mevcut | Birleşik geniş | Mutlak artış | Göreli artış | Ortalama maliyet |
|---|---:|---:|---:|---:|---:|
| Simitçi | %13.6 | %16.8 | +3.2 puan | +%23.3 | 1.320 TL |
| Harbi | %20.5 | %26.8 | +6.4 puan | +%31.1 | 2.118 TL |
| Ortaklı | %26.4 | %30.5 | +4.1 puan | +%15.5 | 2.444 TL |

Karar:

- En yüksek isabet artışı.
- Bütçe bandını belirgin aşıyor.
- Sadece “agresif ortaklı / yüksek bütçe” modu olarak düşünülmeli.

---

## 4. Önerilen Ürün Stratejisi

### Standart sistem

Uygulanacaklar:

1. 5 satır kuralı korunur.
2. Ortaklı kademe “ana/ciddi oyun” olarak öne çıkarılır.
3. Tek-at banko için AGF>=50 kapısı eklenir.

Beklenen etki:

| Alan | Mevcut | Beklenen |
|---|---:|---:|
| 5 satır | %90.4 | %90.4 |
| Harbi altılı | %20.5 | %22.3 |
| Ortaklı altılı | %26.4 | %28.2 |

### Ciddi oyun modu

Uygulanacaklar:

1. AGF>=50 banko kapısı.
2. 14+ ayakta minimum 6 at.
3. Ortaklı kademe varsayılan.

Beklenen etki:

| Alan | Mevcut | Beklenen |
|---|---:|---:|
| 5 satır | %90.4 | %90.4 |
| Harbi altılı | %20.5 | %24.5 |
| Ortaklı altılı | %26.4 | %29.5 |

Maliyet notu: Ortalama Ortaklı maliyeti yaklaşık 2.071 TL olur; mevcut 1.600-2.000 TL bandının biraz üstüne çıkar.

### Agresif ortaklı mod

Uygulanacaklar:

1. AGF>=50 banko kapısı.
2. 14+ ayakta minimum 7 at.
3. Bütçe bandı 2.400-2.600 TL seviyesine çıkarılır.

Beklenen etki:

| Alan | Mevcut | Beklenen |
|---|---:|---:|
| 5 satır | %90.4 | %90.4 |
| Harbi/üst kademe altılı | %20.5 | %26.8 |
| Ortaklı/üst kademe altılı | %26.4 | %30.5 |

Bu seçenek yüksek bütçe ve yüksek varyans modudur.

---

## 5. Nihai Karar Önerisi

Kısa vadede üretime alınacak en mantıklı değişiklik:

```text
AGF>=50 tek-at banko kapısı
+ Ortaklı kademeyi ana öneri yapmak
```

Bu, 5 satırı bozmaz ve altılıda yaklaşık:

- Harbi için +1.8 puan.
- Ortaklı için +1.8 puan.
- Göreli olarak %7-%9 isabet artışı sağlar.

İkinci aşama:

```text
14+ ayaklarda minimum genişlik 6
```

Bu özellikle Harbi/Ortaklı tarafında anlamlıdır:

- Harbi: %20.5 -> %22.7.
- Ortaklı: %26.4 -> %27.7.

Üçüncü aşama / yüksek bütçe:

```text
AGF>=50 + 14+ minimum 6 veya 7
```

En iyi dengeli seçenek:

- AGF>=50 + Min14=6.
- Ortaklı: %26.4 -> %29.5.
- Göreli artış: yaklaşık %12.1.

En yüksek isabet seçeneği:

- AGF>=50 + Min14=7.
- Ortaklı: %26.4 -> %30.5.
- Göreli artış: yaklaşık %15.5.
- Ancak bütçe bandı belirgin artar.

