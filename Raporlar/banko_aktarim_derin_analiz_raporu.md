# Banko + 5-Satır Aktarım Derin Analizi

Evren: **441** altılı (Harbi_Ganyan_Analiz taze tahmin + TJK JSON sonuç, 01.02–30.05.2026). İç içe kural (Simitçi ⊆ Harbi ⊆ Ortaklı) korunur.

## 1. Aktarım uçurumu: 5 satır buluyor, kupon yansıtamıyor

- 5 satır 6 ayağın **TAMAMINDA** kazananı buluyor: **236/441 (%53.5)** → mükemmel aktarımda 'herhangi bir kupon 6/6' teorik tavanı budur.
- 5 satır ayak dağılımı: 6/6=236, 5/6=149, 4/6=42, 3/6=12, 2/6=2
- ESKİ üretim bunu kupona yalnız **115/441 (%26.1)** olarak yansıtabiliyordu. Uçurumun üç sebebi: (a) zorunlu banko, (b) bütçe tavanı, (c) model tavanı (kazanan 5-satır dışı). Bu rapor (a) ve (b)'yi düzeltir.

## 2. Zorunlu bankonun kanıtlanmış maliyeti

PROD'un her kupona kilitlediği **banko-lider ayağın** favori efektif kazanma olasılığı (kendi + eküri ortağı payı, 441 altılı):

| İstatistik | Favori efektif güven |
|---|---:|
| Medyan | **0.441** (favori medyanda yalnız ~%44 kazanıyor) |
| p25 / p75 | 0.391 / 0.591 |
| p90 / max | 0.591 / 0.673 |

> Yani üretim, favorinin yarıdan fazla kez KAYBETTİĞİ ayaklara bile tek-at banko yazıp üç kuponu birden riske atıyordu. Bu, kullanıcı sezgisini doğruluyor: banko zorunluluğu kaldırılmalı, banko yalnız net üstünlükte yazılmalı.

## 3. Koşullu banko eşik eğrisi (yeni bütçe @2800)

Banko, banko-aday ayağın favori efektif güveni eşiği geçerse yazılır; geçmezse ayak en az 2'ye genişler.

| Eşik | Herhangi 6/6 | Simitçi | Harbi | Ortaklı |
|---|---:|---:|---:|---:|
| force (zorunlu) | 118/441 (%26.8) | 59 | 97 | 118 |
| 0.50 | 122/441 (%27.7) | 60 | 100 | 122 |
| 0.55 (ÜRETİM) | 120/441 (%27.2) | 58 | 98 | 120 |
| 0.58 | 121/441 (%27.4) | 58 | 99 | 121 |
| kapalı (hiç banko) | 119/441 (%27.0) | 56 | 96 | 119 |

**Kritik nüans:** bankoyu *tamamen* kapatmak (hiç banko) koşullu tutmaktan DAHA KÖTÜ. Optimum 'hep banko' da 'hiç banko' da değil — **koşullu banko**. Eşik 0.50–0.58 platosunda sonuç ±1 altılı; **0.55** = 'favori ≥%55 kazanır' net üstünlük (kullanıcı tercihi).

## 4. ESKİ vs YENİ (üretim) — net etki

| Kademe | ESKİ (force@2500) 6/6 | YENİ (0.55@2800) 6/6 | Δ | YENİ ort. bedel |
|---|---:|---:|---:|---:|
| Simitçi 6'lısı | 59/441 (%13.4) | 58/441 (%13.2) | -1 | 589 TL |
| Harbi Ganyan 6'lısı | 97/441 (%22.0) | 98/441 (%22.2) | +1 | 1555 TL |
| Ortaklı 6'lı | 115/441 (%26.1) | 120/441 (%27.2) | +5 | 2516 TL |
| **Herhangi biri** | **115 (%26.1)** | **120 (%27.2)** | **+5** | — |

- Net: **+5 altılı** (%26.1 → **%27.2**). Kazanılan: +21, kaybedilen: -16.
- Banko-killed kayıp (tek-at banko ayağının kuponu tek başına öldürdüğü 5/6): ESKİ 26 → YENİ 24.
- **Zorunlu banko-lider (Ortaklı):** ESKİ 441/441 kupon (her kupona kilitli) → YENİ 127/441 kupon (%28.8 — yalnız net üstünlükte). Banko zorunluluğu kalktı.
- İç içe kural korundu: ESKİ=True, YENİ=True.

## 5. Kalan kayıpların anatomisi (YENİ üretim, Ortaklı 5/6)

- 5/6'da kalan Ortaklı kupon: **185**
- Kaçan kazanan 5-satırdaydı (dağıtımla kurtarılabilir): **102 (%55.1)**
- Kaçan kazanan 5-satır DIŞI (model tavanı, dağıtımla çözülmez): **83 (%44.9)**
- Kaçan slot: DIŞI=83, YAZ=42, HAR=31, BOM=19, SUR=10
- Kaçan kazanan ANA-rank: #2=10, #3=42, #4=19, #5=33, #6=16, #7=24, #8=15, #9=7, #10=5, #11=11, #12=1, #13=1, #16=1
- Saha büyüklüğü: ≤9=102, 14+=34, 10-11=30, 12-13=19
- Koşu tipi: sartli=82, handikap=57, kv_grup=23, maiden=23

## 6. Yol haritası

1. **TAMAM — Koşullu banko (0.55) + Ortaklı @2800.** Üretimde aktif. %26.1 → %27.2. İç içe kural ve bütçe bantları korunur.
2. **Sıradaki cephe = model tavanı.** Kalan kayıpların ~%44'ünde kazanan 5-satır DIŞI. Bu dağıtımla çözülmez; 5-satır/ANA skor modelinin (özellikle BOM/HAR slot seçimi ve kalabalık-saha) iyileştirilmesi gerekir. Akış-ilk5 + yüksek-ganyan adaylarını HAR slotuna taşıma testi önerilir.
3. **Kalabalık-saha genişliği.** 14+ atlı koşularda favori-kazanma düşük; bu ayaklarda taban genişliği (min 2 yerine min 3) ayrı test edilmeli.
4. **Eşik izleme.** 0.55 tutucu; ileride canlı veriyle 0.50'ye çekmek +2 altılı verebilir ama 'net üstünlük' barını düşürür — kullanıcı kararı.
