import 'package:flutter/material.dart';
import '../api/models.dart';
import '../theme.dart';
import 'rozet.dart';

class AltiliKarti extends StatelessWidget {
  final Altili altili;

  /// koşu no -> kazanan at_no (CANLI; koşu sonucundan, altılı tam bitmese de).
  final Map<int, int?> winnerByKno;

  /// koşu no -> kazananın ganyanı.
  final Map<int, double?> ganyanByKno;

  const AltiliKarti(this.altili,
      {this.winnerByKno = const {}, this.ganyanByKno = const {}, super.key});

  int _kademeHits(Kademe k) {
    var h = 0;
    for (final ayak in k.ayaklar) {
      final w = winnerByKno[ayak.kno];
      if (w != null && ayak.secilen.contains(w)) h++;
    }
    return h;
  }

  @override
  Widget build(BuildContext context) {
    final s = altili.sonuc;
    final aralik = altili.legs.isEmpty
        ? ''
        : '${altili.legs.first}-${altili.legs.last}. KOSU';
    final tumSonuc =
        altili.legs.isNotEmpty && altili.legs.every((l) => winnerByKno[l] != null);
    final herhangiSonuc = altili.legs.any((l) => winnerByKno[l] != null);
    final ikramiye = s?.ikramiye;
    // KAZANDIK: tüm ayaklar bitti + en az bir kademe 6/6.
    final tuttu = tumSonuc &&
        altili.kademeler.any((k) => _kademeHits(k) == altili.legs.length);

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
            if (ikramiye != null)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                // Sonucu açıklanmış ikramiye -> turkuaz (farkındalık).
                child: Text(paraFmt(ikramiye),
                    style: const TextStyle(
                        color: HG.camgobegi,
                        fontWeight: FontWeight.w800,
                        fontSize: 14)),
              ),
          ]),
        ]),
        const SizedBox(height: 10),
        for (final k in altili.kademeler)
          _KademeBlok(k, winnerByKno, ganyanByKno, tumSonuc, _kademeHits(k)),
        if (herhangiSonuc)
          _SonucBlok(altili.legs, winnerByKno, tuttu, ikramiye),
      ]),
    );
  }
}

class _KademeBlok extends StatelessWidget {
  final Kademe kademe;
  final Map<int, int?> winnerByKno;
  final Map<int, double?> ganyanByKno;
  final bool tumSonuc;
  final int hits;
  const _KademeBlok(
      this.kademe, this.winnerByKno, this.ganyanByKno, this.tumSonuc, this.hits);

  @override
  Widget build(BuildContext context) {
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
          // Tutturma rozeti yalnız tüm ayaklar sonuçlanınca anlamlı.
          if (tumSonuc) TutturmaRozet(hits),
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
  final int? winner; // bu ayağın kazananı (at_no) — canlı, koşu sonucundan
  final double? ganyan;
  const _AyakSatiri(this.ayak, {this.winner, this.ganyan});

  List<InlineSpan> _spanlar() {
    final spans = <InlineSpan>[];
    for (var i = 0; i < ayak.secilen.length; i++) {
      if (i > 0) spans.add(const TextSpan(text: ' / '));
      final n = ayak.secilen[i];
      final kazandi = winner != null && n == winner;
      spans.add(TextSpan(
        text: kazandi ? '[$n]' : '$n',
        style: TextStyle(
          color: kazandi ? HG.yesil : HG.metin,
          fontWeight: kazandi ? FontWeight.w800 : FontWeight.w400,
        ),
      ));
    }
    // Kaçırdık: kazanan bizim seçimimizde yok -> kırmızı |n|
    if (winner != null && !ayak.secilen.contains(winner)) {
      spans.add(const TextSpan(text: '    '));
      spans.add(TextSpan(
        text: '|$winner|',
        style: const TextStyle(color: HG.kirmizi, fontWeight: FontWeight.w800),
      ));
    }
    return spans;
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 1),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 64,
          child: Text('${ayak.kno}. KOŞU',
              style: const TextStyle(
                  color: HG.metin, fontWeight: FontWeight.w800, fontSize: 13)),
        ),
        Expanded(
          child: RichText(
            text: TextSpan(
                style: const TextStyle(fontSize: 13, height: 1.3),
                children: _spanlar()),
          ),
        ),
        if (winner != null && ganyan != null)
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
}

class _SonucBlok extends StatelessWidget {
  final List<int> legs;
  final Map<int, int?> winnerByKno;
  final bool tuttu;
  final double? ikramiye;
  const _SonucBlok(this.legs, this.winnerByKno, this.tuttu, this.ikramiye);

  @override
  Widget build(BuildContext context) {
    final winners =
        legs.map((l) => winnerByKno[l]?.toString() ?? '?').join('  /  ');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Divider(height: 14, thickness: 3, color: HG.altin),
      const Text('SONUÇLAR',
          style: TextStyle(
              color: HG.metin, fontSize: 15, fontWeight: FontWeight.w800)),
      const SizedBox(height: 4),
      // Çift satır: numaralar SONUÇLAR'ın altında, tam genişlik (taşma yok).
      // Küçük font: ekürili sistemde çok numara gelse de taşmasın.
      Text(winners,
          softWrap: true,
          style: const TextStyle(
              color: HG.altinAcik, fontSize: 12, fontWeight: FontWeight.w700)),
      if (tuttu && ikramiye != null)
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Row(children: [
            const Icon(Icons.emoji_events, size: 18, color: HG.yesil),
            const SizedBox(width: 6),
            Text('KAZANDIK · ${paraFmt(ikramiye)}',
                style: const TextStyle(
                    color: HG.yesil, fontSize: 14, fontWeight: FontWeight.w800)),
          ]),
        ),
      const Divider(height: 14, thickness: 3, color: HG.altin),
    ]);
  }
}
