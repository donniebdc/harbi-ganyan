# Look-ahead (Geleceği Görme) Bulgusu + Düzeltme — 2026-06-03

## Özet
Canlı takip, gün içinde **tüm günü yeniden üretiyordu** (`run_full`, `force` Pegadrom).
Pegadrom `ai-analiz` sayfaları CANLI: bir koşu bitince atların **Form** dizisine gerçek
varış derecesi eklenir ve **Yarış Akışı** gerçek varışa göre kısmen yeniden dizilir.
Akış, ANA skorunda **~0.50 ağırlık** taşıdığından, koşulmuş koşular koşu-sonrası
veriyle yeniden analiz edilince **gerçek kazanan favori oluyordu** = look-ahead.

## Kanıt (Elazığ 06.03 4. koşu, koşu 19:30, yeniden üretim 20:50 TR)
| | Koşu ÖNCESİ | Koşu SONRASI (force yeniden indirme) |
|---|---|---|
| Akış 1 | No 1 DOĞAN KHAN | **No 5 YAĞIZALP (kazanan)** |
| #5 akış rank | 10 | **1** |
| #5 Form | `...10-1-2` | `...10-1-2-1` (birincilik eklendi) |
| Motor 5SATIR | #5 favori değil | **FAV=YAĞIZALP, ANA 106, AKIS:1** |

Tüm Mayıs Pegadrom TXT'leri 30.05'te toplu çekilmiş (koşu-sonrası) → girdi kirli.

## Backtest etkisi (NÜANS — "hepsi hileli" DEĞİL)
- Akış-rank-1 = gerçek kazanan: Mayıs **%31.3**, taze 06-03 **%25** → normal favori
  seviyesi/altı. Pegadrom akışı koşu-sonrası sonucu güvenilir biçimde KODLAMIYOR.
- Motorun kirli veriyle 5SATIR FAV tutturma oranı **%35.2**, kazanan-5-satır-içinde
  **%88.6** → şişirilmiş değil; gerçek bir modelin sayıları.
- Form alanı kesin sızdırıyor ama **motor formu kullanmıyor** (yalnız akış-rank + galop).
- Sonuç: backtest sayıları kabaca gerçek; ~birkaç puan iyimser sapma olabilir. Yöntem
  yine de hatalı → ileride yalnız koşu-öncesi snapshot kullanılmalı (AYRI TARTIŞMA).

## Düzeltme — bir koşu BAŞLADIKTAN sonra analizi hiçbir katmanda değişmez
Commit `ad63a55` (branch `analiz/altili-aktarim-optim`).

### G1 — Pegadrom dondurma (`motor/pegadrom_ai_txt_topla.py`)
`collect_range(..., skip=set)`: `force=True` olsa bile `skip` setindeki (başlamış)
koşuların mevcut TXT'si KORUNUR. `(HIP_ASCII_UPPER, kosu_no)`.

### G2 — Import dondurma (`backend/export/import_to_db.py`)
`import_payload(db, payload, freeze=True, now_tr=None)` zaman-bazlı birleştirme:
- **Şehir ilk koşu −30 dk** → o şehrin 5-satır + altılı analizi DONAR (gün-seviyesi).
- **Her koşu −5 dk** → o koşunun alt-bahis analizi DONAR (koşu-bazlı).
- Sonuç alanları (kazanan/ganyan/ikramiye/tuttu/net) HER ZAMAN güncellenir.
- `freeze=False` → bilinçli replay (tam yeniden-yazım): manuel `--uret`, `--export-only`,
  `import_to_db` CLI.
- Eşikler: `LOCK_5SAT_DK=30`, `LOCK_ALT_DK=5`.

### daily_pipeline (`backend/cron/daily_pipeline.py`)
- `run_full(..., freeze=True)`: `_baslamis_kosu_skip(iso)` ile başlamış-koşu skip seti
  hesaplanıp `collect_range`'e geçilir; `export_import`'a `freeze` aktarılır.
- `export_import(isos, freeze=True)`.
- Canlı takip gün-seviyesi (5-satır/6'lı) penceresi **R−10dk → R−30dk**; bu noktadan
  sonra gün-seviyesi yeniden-üretim/bildirim YOK. Alt-bahis taraması her koşu −5dk'ya
  kadar (değişmedi).
- `--results-only` / `--live` artık `freeze=True` (varsayılan) → sonuç-tazeleme analizi
  değiştirmez, yalnız sonuç akıtır (doğru davranış).

## Doğrulama (VPS, izole rollback işlemleri)
- Koşu-sonrası (freeze): 5-satır + alt-bahis DONUK, sonuç (kazanan) akıyor. ✓
- Koşu-öncesi (R−30 öncesi, freeze): analiz tazeleniyor. ✓
- Şehir kilitli + geç koşu (−5dk gelmedi): 5-satır DONUK, alt-bahis GÜNCELLENİYOR. ✓
- Replay (freeze=False): tam yeniden-yazım. ✓
- `_baslamis_kosu_skip('2026-06-03')` → 16 koşu, hip kodları ELAZIG/ISTANBUL (Pegadrom
  klasörleriyle birebir). ✓

Cron servisleri her tetiklenmede taze python başlatır → bir sonraki tick'te yeni kod
devrede; backend restart gerekmedi.

## Sonuç-zamanlaması (kullanıcı maddesi)
`_bekleyen_var` koşu **+2 dk**'da poll'a başlıyor; live timer her 2 dk çalışıyor — yani
"yarış +2dk'da sonuç isteği" KARŞILANIYOR. Gözlenen gecikme bizim cadence'ımızda değil,
TJK resmi `full/<KEY>.json` **ganyan (ikramiye) feed'inin ~10-15 dk gecikmesinde**
(`_bekleyen_var` `ganyan is None`'a takılıyor). Daha erken "gayrı resmi" kazanan göstermek
için provisional feed entegrasyonu + kazanan/ikramiye ayrıştırması gerekir (AYRI İŞ).

## Açık konular (sonraki oturum)
1. **Backtest dürüstlüğü:** koşu-öncesi Pegadrom snapshot'larını dondurarak ileriye dönük
   doğrulama (kullanıcı "sonra tartışalım" dedi).
2. **Gayrı resmi sonuç:** kazananı dividend'den önce göstermek için provisional feed.
