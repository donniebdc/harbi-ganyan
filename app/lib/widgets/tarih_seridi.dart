import 'package:flutter/material.dart';
import '../api/models.dart';
import '../theme.dart';
import '../util.dart';

/// Yatay kaydırmalı tarih şeridi. Hem Geçmiş hem Aktif (Bugün/Yarın) bloklarında kullanılır.
class TarihSeridi extends StatelessWidget {
  final List<GunOzet> gunler;
  final String secili;
  final void Function(String) onSec;

  /// Üst küçük etiket (ör. gün adı "Cum" veya "BUGÜN"/"YARIN"). Verilmezse gün adı.
  final String Function(GunOzet g)? ustEtiket;
  const TarihSeridi({
    required this.gunler,
    required this.secili,
    required this.onSec,
    this.ustEtiket,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 72,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        itemCount: gunler.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (_, i) {
          final g = gunler[i];
          final aktif = g.date == secili;
          final ust = ustEtiket?.call(g) ?? gunAdi(g.date);
          return InkWell(
            onTap: () => onSec(g.date),
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: 68,
              decoration: BoxDecoration(
                color: aktif ? HG.altin : HG.kart,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: aktif ? HG.altin : HG.kart2),
              ),
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                Text(ust,
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: aktif ? Colors.black54 : HG.metinSoluk)),
                const SizedBox(height: 2),
                Text(tarihKisa(g.date),
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w800,
                        color: aktif ? Colors.black : HG.metin)),
              ]),
            ),
          );
        },
      ),
    );
  }
}
