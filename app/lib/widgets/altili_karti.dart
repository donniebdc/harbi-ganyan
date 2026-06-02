import 'package:flutter/material.dart';
import '../api/models.dart';
import '../theme.dart';
import 'rozet.dart';

class AltiliKarti extends StatelessWidget {
  final Altili altili;

  /// koşu no -> kazananın ganyanı (sonuç geldiyse). Ayak satırında detay göstermek için.
  final Map<int, double?> ganyanByKno;
  const AltiliKarti(this.altili, {this.ganyanByKno = const {}, super.key});

  @override
  Widget build(BuildContext context) {
    final s = altili.sonuc;
    final aralik = altili.legs.isEmpty
        ? ''
        : '${altili.legs.first}-${altili.legs.last}. KOSU';

    // Ayak (koşu no) -> kazanan at_no eşlemesi (sonuç geldiyse).
    final winnerByKno = <int, int>{};
    if (s != null) {
      for (var i = 0; i < altili.legs.length && i < s.winners.length; i++) {
        final w = s.winners[i];
        if (w != null) winnerByKno[altili.legs[i]] = w;
      }
    }
    // En az bir kademe 6/6 tutturduysa kupon kazanmış demektir.
    final tuttu = s != null && s.tierHits.values.any((h) => h == 6);

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 14),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [HG.kart2, HG.kart],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: (tuttu ? HG.yesil : HG.altin).withValues(alpha: 0.45)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.casino, color: HG.altin, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('${altili.idx}. 6\'LI GANYAN',
                style: const TextStyle(
                    color: HG.altin, fontWeight: FontWeight.w800, fontSize: 16)),
          ),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text(aralik,
                style: const TextStyle(
                    color: HG.yesil, fontWeight: FontWeight.w700, fontSize: 12)),
            if (s != null && s.ikramiye != null)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(paraFmt(s.ikramiye),
                    style: const TextStyle(
                        color: HG.altin,
                        fontWeight: FontWeight.w800,
                        fontSize: 14)),
              ),
          ]),
        ]),
        const SizedBox(height: 10),
        for (final k in altili.kademeler)
          _KademeBlok(k, s, winnerByKno, ganyanByKno),
        if (s != null) _SonucBlok(s, tuttu),
      ]),
    );
  }
}

class _KademeBlok extends StatelessWidget {
  final Kademe kademe;
  final AltiliSonuc? sonuc;
  final Map<int, int> winnerByKno;
  final Map<int, double?> ganyanByKno;
  const _KademeBlok(this.kademe, this.sonuc, this.winnerByKno, this.ganyanByKno);

  @override
  Widget build(BuildContext context) {
    final hits = sonuc?.tierHits[kademe.key];
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Divider(height: 12, thickness: 2, color: HG.metin),
        Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
          Expanded(
            child: RichText(
              text: TextSpan(
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800),
                children: [
                  TextSpan(
                    text: (HG.kademeAd[kademe.key] ?? kademe.ad).toUpperCase(),
                    style: const TextStyle(color: HG.yesil),
                  ),
                  const TextSpan(text: '  '),
                  TextSpan(
                    text: paraFmt(kademe.bedel),
                    style: const TextStyle(color: HG.kirmizi),
                  ),
                ],
              ),
            ),
          ),
          if (sonuc != null) TutturmaRozet(hits),
        ]),
        const SizedBox(height: 6),
        for (final ayak in kademe.ayaklar)
          _AyakSatiri(
            ayak,
            winner: winnerByKno[ayak.kno],
            ganyan: ganyanByKno[ayak.kno],
          ),
      ]),
    );
  }
}

class _AyakSatiri extends StatelessWidget {
  final Ayak ayak;
  final int? winner; // bu ayağın kazananı (at_no) — sonuç geldiyse
  final double? ganyan; // kazananın ganyanı
  const _AyakSatiri(this.ayak, {this.winner, this.ganyan});

  @override
  Widget build(BuildContext context) {
    final w = winner;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 1),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 64,
          child: Text('${ayak.kno}. AYAK',
              style: const TextStyle(
                  color: HG.metin, fontWeight: FontWeight.w800, fontSize: 13)),
        ),
        Expanded(
          child: RichText(
            text: TextSpan(
              style: const TextStyle(fontSize: 13, height: 1.25),
              children: _numaralar(),
            ),
          ),
        ),
        if (w != null && ganyan != null)
          Padding(
            padding: const EdgeInsets.only(left: 6),
            child: Text('G ${ganyan!.toStringAsFixed(2)}',
                style: const TextStyle(
                    color: HG.altinAcik,
                    fontSize: 11,
                    fontWeight: FontWeight.w700)),
          ),
      ]),
    );
  }

  List<InlineSpan> _numaralar() {
    final nums = ayak.secilen;
    final spans = <InlineSpan>[];
    for (var i = 0; i < nums.length; i++) {
      if (i > 0) spans.add(const TextSpan(text: ' / '));
      final n = nums[i];
      final kazandi = winner != null && n == winner;
      spans.add(TextSpan(
        text: kazandi ? '[$n]' : '$n',
        style: TextStyle(
          color: kazandi ? HG.yesil : HG.metin,
          fontWeight: kazandi ? FontWeight.w800 : FontWeight.w400,
        ),
      ));
    }
    return spans;
  }
}

class _SonucBlok extends StatelessWidget {
  final AltiliSonuc sonuc;
  final bool tuttu;
  const _SonucBlok(this.sonuc, this.tuttu);

  @override
  Widget build(BuildContext context) {
    final winners = sonuc.winners.map((w) => w?.toString() ?? '?').join(' / ');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Divider(height: 14, thickness: 3, color: HG.altin),
      Row(children: [
        const Text('SONUÇLAR',
            style: TextStyle(
                color: HG.metin, fontSize: 15, fontWeight: FontWeight.w800)),
        const Spacer(),
        Flexible(
          child: Text(winners,
              textAlign: TextAlign.right,
              style: const TextStyle(color: HG.metin, fontSize: 15)),
        ),
      ]),
      if (tuttu && sonuc.ikramiye != null)
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Row(children: [
            const Icon(Icons.emoji_events, size: 18, color: HG.yesil),
            const SizedBox(width: 6),
            Text('KAZANDIK · ${paraFmt(sonuc.ikramiye)}',
                style: const TextStyle(
                    color: HG.yesil, fontSize: 14, fontWeight: FontWeight.w800)),
          ]),
        ),
      const Divider(height: 14, thickness: 3, color: HG.altin),
    ]);
  }
}
