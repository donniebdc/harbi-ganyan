# Günlük Pipeline — Cron / systemd

`daily_pipeline.py` mevcut tahmin motorunu çalıştırır, yapısal JSON'a çevirir ve DB'ye yazar.

## Modlar
| Komut | Ne yapar | Ağ |
|---|---|---|
| `daily_pipeline.py` | Yarının analizini üretir (full) | Evet |
| `daily_pipeline.py 2026-06-03` | Belirli günü üretir (full) | Evet |
| `daily_pipeline.py --results-only` | Son 7 günün sonucunu tazele + reimport | Evet |
| `daily_pipeline.py --export-only 2026-05-01 2026-05-30` | Var olan tahmin/sonuçtan export+import | Hayır |

## crontab (VPS)
```cron
# Ertesi günün analizleri — her gün 09:00 (vizyon: D-1 09:00 → D analizi)
0 9 * * * cd /opt/harbiganyan && /opt/harbiganyan/.venv/bin/python backend/cron/daily_pipeline.py >> /var/log/harbiganyan/daily.log 2>&1

# Gün-içi sonuç tazeleme — yarış saatleri 11:00–23:00 her 10 dk
*/10 11-23 * * * cd /opt/harbiganyan && /opt/harbiganyan/.venv/bin/python backend/cron/daily_pipeline.py --results-only >> /var/log/harbiganyan/results.log 2>&1
```

## systemd timer (alternatif)
`/etc/systemd/system/harbiganyan-daily.service`
```ini
[Unit]
Description=Harbi Ganyan günlük analiz üretimi
[Service]
Type=oneshot
WorkingDirectory=/opt/harbiganyan
Environment=HG_DATABASE_URL=postgresql+psycopg2://hg:pass@localhost/harbiganyan
ExecStart=/opt/harbiganyan/.venv/bin/python backend/cron/daily_pipeline.py
```
`/etc/systemd/system/harbiganyan-daily.timer`
```ini
[Unit]
Description=Harbi Ganyan günlük tetikleyici
[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true
[Install]
WantedBy=timers.target
```
Etkinleştir: `systemctl enable --now harbiganyan-daily.timer`

Sonuç tazeleme için benzer bir `harbiganyan-results.timer` (`OnCalendar=*-*-* 11..23:00/10`) kullanılabilir.
