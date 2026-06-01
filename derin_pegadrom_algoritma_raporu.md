# Derin Pegadrom Algoritma Karşılaştırma Raporu

## Veri Kapsamı

- CSV sonuç koşusu: 1010
- v6 koşusu: 1028
- Pegadrom AI TXT koşusu: 1028
- Ortak ve kazananı eşleşen koşu: 1004
- Eğitim/test ayrımı: 702 / 302
- v6 at çözümleme: 10185/10365

## 1) Tekil Sinyal Gücü

| Sinyal | İlk1 / İlk3 / İlk4 / İlk5 |
|---|---:|
| v6 ANA | 33.3% / 68.6% / 78.2% / 85.4% (n=1004) |
| G genel | 28.7% / 63.2% / 73.1% / 80.4% (n=1004) |
| Gn guncel | 25.3% / 60.1% / 70.8% / 79.3% (n=1004) |
| S saatli | 25.6% / 57.5% / 69.1% / 76.6% (n=1004) |
| AGF | 33.8% / 69.2% / 79.0% / 84.9% (n=1004) |
| Bizim eski GLP | 14.0% / 38.9% / 52.0% / 63.2% (n=1004) |
| Pegadrom model | 23.1% / 51.6% / 61.8% / 72.0% (n=1004) |
| Pegadrom veri guveni | 14.2% / 38.5% / 50.2% / 62.4% (n=1004) |
| Pegadrom galop notr | 15.1% / 38.6% / 49.5% / 59.6% (n=1004) |
| Pegadrom akış rank skoru | 33.2% / 72.8% / 81.7% / 87.6% (n=1004) |
| Pegadrom akış konum | 32.0% / 71.7% / 81.7% / 88.0% (n=1004) |
| Yarış akışı ilk5 direkt | 33.2% / 72.8% / 81.7% / 87.6% (n=1004) |

## 2) Grid / Holdout Aday Algoritmalar

| Aday | Seçilen ağırlıklar | Eğitim İlk5 | Test İlk1/3/4/5 | Tüm veri İlk5 |
|---|---|---:|---:|---:|
| Peg-only: model + galop + akis | peg_galop_neutral=0.1, flow_rank_score=0.9 | 88.0% | 32.1% / 71.2% / 80.1% / 87.4% (n=302) | 87.8% |
| Yeni no-AGF: G + S + PegModel + PegGalop + Akis | G=0.3, flow_rank_score=0.7 | 89.2% | 32.8% / 69.9% / 80.1% / 87.7% (n=302) | 88.7% |
| Yeni AGF'li: AGF + G + S + PegModel + PegGalop + Akis | AGF=0.4, peg_galop_neutral=0.1, flow_rank_score=0.5 | 90.0% | 33.4% / 70.2% / 82.8% / 88.7% (n=302) | 89.6% |
| Kontrol: G + Gn + S | G=0.7, Gn=0.2, S=0.1 | 83.3% | 25.8% / 62.6% / 68.5% / 76.2% (n=302) | 81.2% |
| Kontrol: G + S | G=0.8, S=0.2 | 83.2% | 26.8% / 63.2% / 69.2% / 74.8% (n=302) | 80.7% |

## 3) En İyi Adayın v6'ya Net Katkısı

- En iyi holdout aday: **Yeni AGF'li: AGF + G + S + PegModel + PegGalop + Akis**
- Ağırlıklar: `AGF`=0.4, `peg_galop_neutral`=0.1, `flow_rank_score`=0.5
- Test sonucu: 33.4% / 70.2% / 82.8% / 88.7% (n=302)
- Tüm veri sonucu: 37.3% / 72.3% / 83.1% / 89.6% (n=1004)
- v6 5 satır baseline: 84.3% (n=1004)
- Farklı seçim yaptığı koşu: 841
- v6'nın kaçırıp yeni adayın yakaladığı: 98
- v6'nın yakalayıp yeni adayın bozduğu: 44
- Net katkı: +54 kazanan

## 4) Grup Bazlı İlk5 Karşılaştırması

| Kırılım | Segment | v6 5 satır | Akış ilk5 | En iyi aday |
|---|---|---:|---:|---:|
| group | handikap | 80.9% (n=282) | 84.0% | 85.8% |
| group | kv_grup | 88.3% (n=60) | 93.3% | 95.0% |
| group | maiden | 85.6% (n=202) | 89.1% | 93.1% |
| group | sartli | 85.2% (n=460) | 88.5% | 89.8% |
| track | Kum | 84.1% (n=618) | 87.7% | 90.8% |
| track | Sentetik | 91.9% (n=135) | 89.6% | 91.9% |
| track | Çim | 80.5% (n=251) | 86.5% | 85.7% |
| distance | kisa<=1400 | 81.8% (n=499) | 86.8% | 89.6% |
| distance | orta<=1800 | 84.7% (n=202) | 85.6% | 85.1% |
| distance | uzun>1800 | 88.1% (n=303) | 90.4% | 92.7% |
| field | az<=7 | 95.3% (n=211) | 99.1% | 98.6% |
| field | kalabalik>=12 | 74.2% (n=357) | 80.4% | 83.2% |
| field | orta<=11 | 87.2% (n=436) | 88.1% | 90.6% |

## 5) Bulgular ve Algoritmik Hatalar

- Eski `GLP/GGV` galop sistemi tekil sinyal olarak zayıf kaldığı için tamamen çıkarılmalı; Pegadrom galop puanı yoksa 50 nötr kabul edilmeli.
- `Gn` tek başına ve `G+Gn+S` kontrol modeli, Pegadrom akış/model kombinasyonunun sunduğu ilk5 davranışını yakalamıyor; yeni modelde `Gn` ana bileşen olmamalı.
- Yarış Akışı ilk5, kullanıcının gözlemini doğrulamak için ayrı ölçüldü; ilk5 yakalama davranışı güçlü ama tek başına yeterli formül değil, model ve galopla harmanlanmalı.
- Pegadrom model tek başına favori seçmekte agresif/zayıf kalabiliyor; ilk5 evrenini kurmakta değerli, ana skorun tamamı yapılmamalı.
- Grid araması Pegadrom model puanına nihai formülde ağırlık vermedi; model puanı karar açıklaması/ikincil etiket olarak tutulmalı, ana ilk5 seçimini akış sırası taşıyor.
- AGF'li mod en yüksek sonuç verdi; AGF yokken kullanılacak mobil/erken mod için `G + Akış` sade formülü ayrıca korunmalı.
- Kalabalık koşularda başarı düşüyor; burada akış ilk5 + model + galop karışımı özellikle izlenmeli, 5 satır dışına düşen ama akış ilk5'te olan yüksek ganyanlı adaylar ayrıca işaretlenmeli.

## 6) Önerilen Yeni Yol

- `toplu_tahmin.py` ve `ganyan_master.py` içinde eski galop verisi ve `galop_guven` etkisi kaldırılmalı.
- `Gn` ana skor formülünden çıkarılmalı; bülten tarafında `G` ve varsa `S` korunmalı.
- Pegadrom TXT/HTML parser üretime alınmalı: at_no bazlı `model`, `veri`, `flow_rank`, `flow_pos`, `flow_type`, `galop` alanları saklanmalı.
- İlk uygulanacak skor iki modlu olmalı: AGF varsa `AGF*0.40 + Akış*0.50 + PegGalop*0.10`; AGF yoksa `G*0.30 + Akış*0.70`.
- Uygulama çıktısında ilk5 yanında ayrıca `Akış ilk5 içinde`, `Peg Galop güçlü`, `Model/veri güveni yüksek` gibi açıklayıcı etiketler gösterilmeli.
