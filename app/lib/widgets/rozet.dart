import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../theme.dart';

final _tl = NumberFormat.decimalPattern('tr');

String paraFmt(num? v) => v == null ? '-' : '${_tl.format(v)} TL';

/// 6'lı kademe tutturma rozeti (6/6 TUTTU / N/6).
class TutturmaRozet extends StatelessWidget {
  final int? hits;
  const TutturmaRozet(this.hits, {super.key});

  @override
  Widget build(BuildContext context) {
    final tuttu = hits == 6;
    final renk = tuttu ? HG.yesil : (hits == 5 ? HG.altin : HG.metinSoluk);
    final etiket = hits == null ? '—' : (tuttu ? '6/6 TUTTU' : '$hits/6');
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: renk.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: renk.withValues(alpha: 0.5)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (tuttu) const Icon(Icons.check_circle, size: 13, color: HG.yesil),
        if (tuttu) const SizedBox(width: 3),
        Text(etiket, style: TextStyle(color: renk, fontSize: 11, fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

/// 5-satır isabet rozeti.
class BesRozet extends StatelessWidget {
  final bool? hit;
  const BesRozet(this.hit, {super.key});
  @override
  Widget build(BuildContext context) {
    if (hit == null) return const SizedBox.shrink();
    final renk = hit! ? HG.yesil : HG.kirmizi;
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(hit! ? Icons.check_circle : Icons.cancel, size: 14, color: renk),
      const SizedBox(width: 4),
      Text(hit! ? '5 Satır İsabet' : '5 Satır Iska',
          style: TextStyle(color: renk, fontSize: 11, fontWeight: FontWeight.w600)),
    ]);
  }
}
