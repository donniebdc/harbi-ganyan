import 'package:flutter/material.dart';
import '../theme.dart';

/// İçi sonra doldurulacak bloklar için tutarlı placeholder.
class BlokPlaceholder extends StatelessWidget {
  final String baslik;
  final IconData ikon;
  final String aciklama;
  final String? rozet;
  const BlokPlaceholder({
    required this.baslik,
    required this.ikon,
    required this.aciklama,
    this.rozet,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(ikon, color: HG.altin, size: 54),
          const SizedBox(height: 16),
          Text(baslik,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
          if (rozet != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                  color: HG.altin.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8)),
              child: Text(rozet!,
                  style: const TextStyle(
                      color: HG.altin, fontSize: 11, fontWeight: FontWeight.w800)),
            ),
          ],
          const SizedBox(height: 12),
          Text(aciklama,
              textAlign: TextAlign.center,
              style: const TextStyle(color: HG.metinSoluk, fontSize: 13, height: 1.5)),
        ]),
      ),
    );
  }
}

class HakkindaEkrani extends StatelessWidget {
  const HakkindaEkrani({super.key});
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Hakkında')),
      body: ListView(padding: const EdgeInsets.all(20), children: const [
        Text('Harbi Ganyan',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: HG.altin)),
        SizedBox(height: 12),
        Text(
          'Harbi Ganyan, at yarışlarını veri-kanıtlı bir algoritmik sistemle analiz eder. '
          'Her koşu için 5 satırlık tahmin (Harbi Favorisi, Sürpriz Olmaz, Yazılabilir, '
          'Bomba, Harbi mi?) ve bu tahminlerden türetilen 3 kademeli iç içe 6\'lı ganyan '
          'kuponları (Simitçi, Harbi Ganyan, Ortak Bonkör) üretilir.',
          style: TextStyle(color: HG.metin, height: 1.5),
        ),
        SizedBox(height: 16),
        Text('Yasal Uyarı',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
        SizedBox(height: 8),
        Text(
          'Bu uygulama yalnızca analiz ve bilgilendirme amaçlıdır; kazanç garantisi vermez. '
          '(Hukuki metinler ileride güncellenecektir.)',
          style: TextStyle(color: HG.metinSoluk, height: 1.5, fontSize: 13),
        ),
      ]),
    );
  }
}
