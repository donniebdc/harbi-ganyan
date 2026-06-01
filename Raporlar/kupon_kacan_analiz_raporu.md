# Kupon Kaçan Analizi — '5 satırda var, kupona girmemiş' kazananlar

- Aralık tahmin koşusu: 1986 | sonuç gün/hip: 244 | altılı gün/hip: 248
- Soru: Kaç 5/6 kuponda kazanan aslında 5-satırımızdaydı ama dar ayak yüzünden dışarıda kaldı?
- Üretim kodu DEĞİŞTİRİLMEDİ.

## Simitçi 6'lısı
- Altılı: 437 | Tam isabet (6/6): 54 (%12.4)
- Doğru ayak dağılımı: 6/6=54, 5/6=147, 4/6=143, 3/6=73, 2/6=16
- Tam 1 ayak kaçan (5/6): 147
  - Bunların **100**'inde kazanan 5-satırımızdaydı (%68.0)
  - Bunların **100**'inde ayak genişliği < kazanan ANA-rank → ayağı genişletsek kupon **6/6 olurdu** (%68.0 of 5/6)
  - 5-satır konumu: SUR=6, YAZ=37, BOM=27, HAR=30, 5-satır DIŞI=47
  - Kazanan ANA-rank dağılımı: #2=6, #3=37, #4=27, #5=31, #6=11, #7=35, 7+=35
  - Kaçan ayak banko/çıpa ayağıydı: 31

## Harbi Ganyan 6'lısı
- Altılı: 437 | Tam isabet (6/6): 93 (%21.3)
- Doğru ayak dağılımı: 6/6=93, 5/6=185, 4/6=112, 3/6=38, 2/6=8
- Tam 1 ayak kaçan (5/6): 185
  - Bunların **112**'inde kazanan 5-satırımızdaydı (%60.5)
  - Bunların **112**'inde ayak genişliği < kazanan ANA-rank → ayağı genişletsek kupon **6/6 olurdu** (%60.5 of 5/6)
  - 5-satır konumu: SUR=10, YAZ=33, BOM=25, HAR=44, 5-satır DIŞI=73
  - Kazanan ANA-rank dağılımı: #2=10, #3=33, #4=25, #5=47, #6=16, #7=54, 7+=54
  - Kaçan ayak banko/çıpa ayağıydı: 56

## Ortaklı 6'lı
- Altılı: 437 | Tam isabet (6/6): 110 (%25.2)
- Doğru ayak dağılımı: 6/6=110, 5/6=193, 4/6=90, 3/6=36, 2/6=7
- Tam 1 ayak kaçan (5/6): 193
  - Bunların **113**'inde kazanan 5-satırımızdaydı (%58.5)
  - Bunların **113**'inde ayak genişliği < kazanan ANA-rank → ayağı genişletsek kupon **6/6 olurdu** (%58.5 of 5/6)
  - 5-satır konumu: SUR=12, YAZ=30, BOM=26, HAR=45, 5-satır DIŞI=80
  - Kazanan ANA-rank dağılımı: #2=12, #3=30, #4=26, #5=45, #6=18, #7=62, 7+=62
  - Kaçan ayak banko/çıpa ayağıydı: 68

## Örnekler — BOM/HAR'da kazananı bulduğumuz ama kupona almadığımız ayaklar (Harbi 6'lısı)
- 2026-03-01 IZMIR K5 alt#1: kazanan No:4 = BOM (ANA#4), ayak genişliği 3 at [✍️ standart], n_at=5 fark=14
- 2026-03-01 IZMIR K5 alt#2: kazanan No:4 = BOM (ANA#4), ayak genişliği 2 at [🎯 yarı banko], n_at=5 fark=14
- 2026-05-01 BURSA K2 alt#1: kazanan No:3 = HAR (ANA#5), ayak genişliği 4 at [⚖️ açık], n_at=9 fark=13
- 2026-05-01 ISTANBUL K3 alt#1: kazanan No:6 = HAR (ANA#5), ayak genişliği 2 at [BANKO], n_at=8 fark=48
- 2026-02-02 BURSA K5 alt#2: kazanan No:12 = HAR (ANA#5), ayak genişliği 4 at [⚖️ açık], n_at=14 fark=18
- 2026-04-02 ANTALYA K2 alt#1: kazanan No:7 = BOM (ANA#4), ayak genişliği 2 at [BANKO], n_at=7 fark=33
- 2026-05-02 ANKARA K3 alt#2: kazanan No:3 = HAR (ANA#5), ayak genişliği 4 at [⚖️ açık], n_at=9 fark=10
- 2026-02-03 ANTALYA K6 alt#1: kazanan No:8 = BOM (ANA#4), ayak genişliği 2 at [BANKO], n_at=8 fark=28
- 2026-02-03 ANTALYA K6 alt#2: kazanan No:8 = BOM (ANA#4), ayak genişliği 3 at [✍️ standart], n_at=8 fark=28
- 2026-03-03 ANTALYA K5 alt#1: kazanan No:4 = BOM (ANA#4), ayak genişliği 1 at [BANKO], n_at=7 fark=43
- 2026-04-03 BURSA K6 alt#1: kazanan No:7 = HAR (ANA#5), ayak genişliği 4 at [⚖️ açık], n_at=11 fark=17
- 2026-04-04 ADANA K6 alt#1: kazanan No:3 = HAR (ANA#5), ayak genişliği 2 at [🎯 yarı banko], n_at=5 fark=9
