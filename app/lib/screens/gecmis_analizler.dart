import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/models.dart';
import '../state/content.dart';
import '../theme.dart';
import '../util.dart';
import '../widgets/durumlar.dart';
import 'gun_icerik.dart';

class GecmisAnalizler extends ConsumerStatefulWidget {
  const GecmisAnalizler({super.key});
  @override
  ConsumerState<GecmisAnalizler> createState() => _GecmisState();
}

class _GecmisState extends ConsumerState<GecmisAnalizler> {
  String? _secili;

  @override
  Widget build(BuildContext context) {
    final gunlerAsync = ref.watch(gunlerProvider);
    return gunlerAsync.when(
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(onTekrar: () => ref.invalidate(gunlerProvider)),
      data: (gunler) {
        // Geçmiş = günün analizi dışındaki (yayınlanmış) günler.
        final gecmis = gunler.where((g) => !g.gununAnalizi).toList();
        if (gecmis.isEmpty) {
          return const BosKutu('Geçmiş analiz bulunamadı.', ikon: Icons.history);
        }
        final secili = _secili ?? gecmis.first.date;
        return Column(children: [
          _TarihSeridi(
            gunler: gecmis,
            secili: secili,
            onSec: (d) => setState(() => _secili = d),
          ),
          Expanded(child: _Detay(secili)),
        ]);
      },
    );
  }
}

class _TarihSeridi extends StatelessWidget {
  final List<GunOzet> gunler;
  final String secili;
  final void Function(String) onSec;
  const _TarihSeridi(
      {required this.gunler, required this.secili, required this.onSec});

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
          return InkWell(
            onTap: () => onSec(g.date),
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: 64,
              decoration: BoxDecoration(
                color: aktif ? HG.altin : HG.kart,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: aktif ? HG.altin : HG.kart2),
              ),
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                Text(gunAdi(g.date),
                    style: TextStyle(
                        fontSize: 11,
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

class _Detay extends ConsumerWidget {
  final String date;
  const _Detay(this.date);
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detay = ref.watch(gunDetayProvider(date));
    return detay.when(
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(onTekrar: () => ref.invalidate(gunDetayProvider(date))),
      data: (GunDetay d) => GunIcerik(d, mod: GunIcerikModu.altili),
    );
  }
}
