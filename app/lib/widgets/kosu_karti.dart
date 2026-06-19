import 'package:flutter/material.dart';
import '../api/models.dart';
import '../theme.dart';
import 'rozet.dart';

/// Bir koşunun 5-satır tahmini kartı.
class KosuKarti extends StatelessWidget {
  final Kosu kosu;
  const KosuKarti(this.kosu, {super.key});

  @override
  Widget build(BuildContext context) {
    final s = kosu.sonuc;
    final bilgi = [
      if (kosu.ktip.isNotEmpty) kosu.ktip,
      if (kosu.pist.isNotEmpty) kosu.pist,
      if (kosu.mesafe.isNotEmpty) '${kosu.mesafe}m',
      if (kosu.nAt != null) '${kosu.nAt} at',
      if (kosu.saat.isNotEmpty) kosu.saat,
    ].join(' · ');

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: HG.kart,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: HG.kart2),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 8),
          child: Row(children: [
            Container(
              width: 30,
              height: 30,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                  color: HG.altin.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8)),
              child: Text('${kosu.kno}',
                  style: const TextStyle(
                      color: HG.altin, fontWeight: FontWeight.w800, fontSize: 15)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${kosu.kno}. Koşu',
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                if (bilgi.isNotEmpty)
                  Text(bilgi, style: const TextStyle(color: HG.metinSoluk, fontSize: 12)),
              ]),
            ),
            if (s != null) BesRozet(s.besHit),
          ]),
        ),
        const Divider(height: 1, color: HG.kart2),
        ...kosu.bes.map((b) => _slotSatiri(b, s?.kazanan)),
        if (s != null && s.ganyan != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 6, 14, 6),
            child: Text('Kazanan: No ${s.kazanan}  ·  Ganyan ${s.ganyan!.toStringAsFixed(2)} TL',
                style: const TextStyle(color: HG.altinAcik, fontSize: 12, fontWeight: FontWeight.w600)),
          ),
        if (kosu.analizPuanlari.isNotEmpty) _analizPuanlari(kosu.analizPuanlari, s?.kazanan),
      ]),
    );
  }

  Widget _analizPuanlari(List<AnalizPuan> puanlar, int? kazanan) {
    return ExpansionTile(
      tilePadding: const EdgeInsets.symmetric(horizontal: 14),
      childrenPadding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
      dense: true,
      title: const Text('Analiz Puanları',
          style: TextStyle(color: HG.metinSoluk, fontSize: 12, fontWeight: FontWeight.w600)),
      iconColor: HG.metinSoluk,
      collapsedIconColor: HG.metinSoluk,
      children: puanlar.map((p) {
        final kazandi = kazanan != null && p.atNo == kazanan;
        final ekuTag = p.ekuPartnerNos.isNotEmpty
            ? ' [E: ${p.ekuPartnerNos.join(', ')}]'
            : '';
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(children: [
            Container(
              width: 26,
              alignment: Alignment.center,
              padding: const EdgeInsets.symmetric(vertical: 2),
              decoration: BoxDecoration(
                  color: HG.kart2, borderRadius: BorderRadius.circular(5)),
              child: Text('${p.atNo}',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 11)),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(p.at + ekuTag,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: kazandi ? FontWeight.w700 : FontWeight.w400,
                      color: kazandi ? HG.yesil : HG.metin)),
            ),
            Text(p.ana.toStringAsFixed(1),
                style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: kazandi ? HG.yesil : HG.altin)),
          ]),
        );
      }).toList(),
    );
  }

  Widget _slotSatiri(Bes b, int? kazanan) {
    final renk = HG.slotRenk[b.slot] ?? HG.metinSoluk;
    final kazandi = kazanan != null && b.atNo == kazanan;
    final ekuTag = b.ekuPartnerNos.isNotEmpty
        ? ' [E: ${b.ekuPartnerNos.join(', ')}]'
        : '';
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      child: Row(children: [
        Container(width: 4, height: 30, color: renk),
        const SizedBox(width: 10),
        SizedBox(
          width: 96,
          child: Text(HG.slotAd[b.slot] ?? b.slot,
              style: TextStyle(color: renk, fontSize: 11, fontWeight: FontWeight.w700)),
        ),
        Container(
          width: 26,
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(vertical: 2),
          decoration: BoxDecoration(
              color: HG.kart2, borderRadius: BorderRadius.circular(5)),
          child: Text('${b.atNo}',
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(b.at + ekuTag,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      fontSize: 13,
                      fontWeight: kazandi ? FontWeight.w800 : FontWeight.w400,
                      color: kazandi ? HG.yesil : HG.metin)),
              if (b.jokey.isNotEmpty)
                Text(b.apranti ? '${b.jokey} (ap)' : b.jokey,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                        fontSize: 10.5,
                        color: b.apranti ? HG.camgobegi : HG.metinSoluk,
                        fontWeight:
                            b.apranti ? FontWeight.w700 : FontWeight.w400)),
            ],
          ),
        ),
        if (kazandi) const Icon(Icons.emoji_events, size: 16, color: HG.altin),
      ]),
    );
  }
}
