# ALTILI GANYAN BACKTEST RAPORU

Kaynak tahmin: `v5_tahmin_01042026-30052026.txt`  |  Birim: hipodroma göre 1.00 / 1.25 TL

Kademeler: Simitçi 6'lısı (200-500₺), Harbi Ganyan 6'lısı (1200-1600₺), Ortaklı 6'lı (1600-2000₺)

Toplam CSV altılısı: 220

Değerlendirilen altılı (tahmin+sonuç eşleşen): **220**

## Bütçe kademesi sonuçları

| Bütçe | Altılı | İsabet | İsabet % | Ort. Maliyet | Top. Maliyet | Top. Dönüş | Net |
|---|---:|---:|---:|---:|---:|---:|---:|
| Simitçi 6'lısı | 220 | 28 | %12.7 | 480₺ | 105588₺ | 332264₺ | +226676₺ |
| Harbi Ganyan 6'lısı | 220 | 46 | %20.9 | 1545₺ | 339873₺ | 917105₺ | +577232₺ |
| Ortaklı 6'lı | 220 | 60 | %27.3 | 1929₺ | 424338₺ | 1266984₺ | +842646₺ |

## Çıpa ayağı doğruluğu

Her altılıda lider çıpa ayağının (tek-at banko ya da 2-at çıpa) kazananı içerme oranı:

| Bütçe | Banko doğru / toplam | Oran |
|---|---:|---:|
| Simitçi 6'lısı | 144/220 | %65.5 |
| Harbi Ganyan 6'lısı | 144/220 | %65.5 |
| Ortaklı 6'lı | 144/220 | %65.5 |

Banko ayağının seçildiği alan segmenti (Harbi Ganyan 6'lısı kademesi):

| Alan | Banko doğru / toplam | Oran |
|---|---:|---:|
| ≤7 | 66/94 | %70 |
| 8-9 | 32/50 | %64 |
| 10-11 | 34/52 | %65 |
| 12-13 | 12/19 | %63 |
| 14+ | 0/5 | %0 |

## Banko politikası karşılaştırması (Harbi Ganyan 6'lısı kademesi)

Her altılıda ≥1 banko/çıpa direktifinin maliyeti ve akıllı banko çözümü:

| Politika | İsabet | İsabet % | Top. Maliyet | Top. Dönüş | Net | Tek-at banko doğruluğu |
|---|---:|---:|---:|---:|---:|---:|
| Banko ZORUNLU (her zaman tek-at) | 39/220 | %17.7 | 337488₺ | 627012₺ | +289524₺ | 102/220 (%46) |
| Akıllı banko (eşik 0.50) | 46/220 | %20.9 | 339873₺ | 917105₺ | +577232₺ | 35/55 (%64) |
| Bankosuz (serbest) | 42/220 | %19.1 | 338932₺ | 589655₺ | +250723₺ | — |

## Örnek kuponlar (Harbi Ganyan 6'lısı kademesi)

### 2026-04-01 · ELAZIG · 1. Altılı (Koşu 1-6)
Sonuç: ❌ tutmadı · 1500 komb × 1.00₺ = 1500₺ · ödeme 25422₺

| Ayak | Genişlik | Etiket | Seçilen | Kazanan |
|---|---|---|---|---|
| 1 | 3 | ✍️ standart | 4-7-2 | 1 ✗ |
| 2 | 1 | 🔒 BANKO LİDER | 4 | 2 ✗ |
| 3 | 5 | ⚖️ açık | 1-6-2-8-4 | 1 ✓ |
| 4 | 5 | ⚖️ açık | 1-2-5-11-8 | 1 ✓ |
| 5 | 5 | ⚖️ açık | 2-6-3-8-7 | 8 ✓ |
| 6 | 4 | ⚖️ açık | 3-7-1-6 | 7 ✓ |

### 2026-04-01 · ELAZIG · 2. Altılı (Koşu 3-8)
Sonuç: ✅ TUTTU · 1600 komb × 1.00₺ = 1600₺ · ödeme 2703₺

| Ayak | Genişlik | Etiket | Seçilen | Kazanan |
|---|---|---|---|---|
| 3 | 4 | ⚖️ açık | 1-6-2-8 | 1 ✓ |
| 4 | 5 | ⚖️ açık | 1-2-5-11-8 | 1 ✓ |
| 5 | 5 | ⚖️ açık | 2-6-3-8-7 | 8 ✓ |
| 6 | 2 | 🔑 ÇIPA (yarı-banko) | 3-7 | 7 ✓ |
| 7 | 2 | 🎯 yarı banko | 11-1 | 11 ✓ |
| 8 | 4 | ⚖️ açık | 1-3-6-11 | 6 ✓ |

### 2026-04-01 · ISTANBUL · 1. Altılı (Koşu 1-6)
Sonuç: ❌ tutmadı · 1200 komb × 1.25₺ = 1500₺ · ödeme 38075₺

| Ayak | Genişlik | Etiket | Seçilen | Kazanan |
|---|---|---|---|---|
| 1 | 4 | ⚖️ açık | 3-1-2-8 | 8 ✓ |
| 2 | 3 | ✍️ standart | 2-1-3 | 2 ✓ |
| 3 | 5 | ⚖️ açık | 5-9-1-6-2 | 7 ✗ |
| 4 | 5 | ⚖️ açık | 11-1-9-12-4 | 9 ✓ |
| 5 | 1 | 🔒 BANKO LİDER | 7 | 4 ✗ |
| 6 | 4 | ⚖️ açık | 2-3-1-6 | 2 ✓ |

### 2026-04-01 · ISTANBUL · 2. Altılı (Koşu 3-8)
Sonuç: ❌ tutmadı · 1280 komb × 1.25₺ = 1600₺ · ödeme 27266₺

| Ayak | Genişlik | Etiket | Seçilen | Kazanan |
|---|---|---|---|---|
| 3 | 5 | ⚖️ açık | 5-9-1-6-2 | 7 ✗ |
| 4 | 4 | ⚖️ açık | 11-1-9-12 | 9 ✓ |
| 5 | 1 | 🔒 BANKO LİDER | 7 | 4 ✗ |
| 6 | 4 | ⚖️ açık | 2-3-1-6 | 2 ✓ |
| 7 | 4 | ⚖️ açık | 6-2-8-5 | 1 ✗ |
| 8 | 4 | ⚖️ açık | 4-3-11-9 | 4 ✓ |

### 2026-04-02 · IZMIR · 1. Altılı (Koşu 1-6)
Sonuç: ❌ tutmadı · 1080 komb × 1.25₺ = 1350₺ · ödeme 45304₺

| Ayak | Genişlik | Etiket | Seçilen | Kazanan |
|---|---|---|---|---|
| 1 | 3 | ✍️ standart | 1-4-2 | 7 ✗ |
| 2 | 2 | 🔑 ÇIPA (yarı-banko) | 2-4 | 1 ✗ |
| 3 | 5 | ⚖️ açık | 6-1-8-4-12 | 4 ✓ |
| 4 | 4 | ⚖️ açık | 1-4-3-7 | 4 ✓ |
| 5 | 3 | ✍️ standart | 1-3-2 | 3 ✓ |
| 6 | 3 | ✍️ standart | 4-5-2 | 2 ✓ |

### 2026-04-02 · IZMIR · 2. Altılı (Koşu 3-8)
Sonuç: ✅ TUTTU · 1152 komb × 1.25₺ = 1440₺ · ödeme 3602₺

| Ayak | Genişlik | Etiket | Seçilen | Kazanan |
|---|---|---|---|---|
| 3 | 4 | ⚖️ açık | 6-1-8-4 | 4 ✓ |
| 4 | 4 | ⚖️ açık | 1-4-3-7 | 4 ✓ |
| 5 | 3 | ✍️ standart | 1-3-2 | 3 ✓ |
| 6 | 3 | ✍️ standart | 4-5-2 | 2 ✓ |
| 7 | 2 | 🔑 ÇIPA (yarı-banko) | 5-2 | 2 ✓ |
| 8 | 4 | ⚖️ açık | 1-5-9-10 | 1 ✓ |
