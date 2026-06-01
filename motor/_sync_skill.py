# -*- coding: utf-8 -*-
"""SKILL.md gövdesini HARBI_GANYAN_PROJE_OZETI.md ile senkronlar (UTF-8 güvenli).
Frontmatter sabit ve temiz; gövde kanonik dokümandan alınır."""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_PATHS = [
    os.path.join(BASE, ".claude", "skills", "harbi_ganyan", "SKILL.md"),
    os.path.join(BASE, ".agents", "skills", "harbi_ganyan", "SKILL.md"),
]
OZET = os.path.join(BASE, "Belgeler", "HARBI_GANYAN_PROJE_OZETI.md")

FRONTMATTER = (
    "name: harbi-ganyan\n"
    "description: Türkiye at yarışı tahmin sistemi Harbi Ganyan'ın proje haritası, "
    "mimarisi ve yol haritası. Bu skill'i ganyan tahmin algoritması, at yarışı backtest, "
    "Pegadrom entegrasyonu, ganyan_master.py veya toplu_tahmin.py veya motor/ klasöründeki "
    "modüller üzerinde çalışırken, 5 satırlı tahmin sistemi, altılı ganyan kupon stratejisi, "
    "akıllı banko, eküri (stablemate) işleme, banko analizi veya bu projeye dair herhangi bir "
    "kod/analiz işi yaparken kullan. Proje bağlamı, kanıtlanmış ağırlıklar, veri kaynakları "
    "(atyarisi.com, Pegadrom, CSV arşivi), klasör yapısı (kök + motor/ + Harbi_Ganyan_Analiz/), "
    "karar kuralları ve sıradaki görevler bu belgededir.\n"
    "---\n\n"
)


def main():
    body = open(OZET, "r", encoding="utf-8").read()
    body = body[body.index("# HARBI GANYAN"):]
    content = FRONTMATTER + body
    for sp in SKILL_PATHS:
        if os.path.isdir(os.path.dirname(sp)):
            open(sp, "w", encoding="utf-8").write(content)
            print(f"senkronlandı: {sp}")
        else:
            print(f"atlandı (klasör yok): {sp}")


if __name__ == "__main__":
    main()
