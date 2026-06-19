import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../state/content.dart';
import '../util.dart';
import '../widgets/durumlar.dart';
import '../widgets/tarih_seridi.dart';
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
      skipLoadingOnReload: true,
      skipError: true,
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(
          mesaj: e is AgHatasi ? e.mesaj : null,
          hata: e,
          onTekrar: () => ref.invalidate(gunlerProvider)),
      data: (gunler) {
        // Geçmiş = yalnızca GERÇEKTEN geçmiş günler (bugünden önce).
        // "aktif" (bugün/yayınlanmış yarın) VE "yakında" (yarın, henüz 18:00 değil)
        // günler hariç tutulur — yarın/yakında günü Geçmiş'e sızmamalı.
        final gecmis =
            gunler.where((g) => !g.aktif && !g.yakinda).toList();
        if (gecmis.isEmpty) {
          return const BosKutu('Geçmiş analiz bulunamadı.', ikon: Icons.history);
        }
        final secili =
            (_secili != null && gecmis.any((g) => g.date == _secili))
                ? _secili!
                : gecmis.first.date;
        return Column(children: [
          TarihSeridi(
            gunler: gecmis,
            secili: secili,
            onSec: (d) => setState(() => _secili = d),
            ustEtiket: (g) => gunAdi(g.date),
          ),
          Expanded(child: _Detay(secili)),
        ]);
      },
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
      skipLoadingOnReload: true,
      skipError: true,
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(
          mesaj: e is AgHatasi ? e.mesaj : null,
          hata: e,
          onTekrar: () => ref.invalidate(gunDetayProvider(date))),
      data: (GunDetay d) => GunIcerik(d, mod: GunIcerikModu.altili),
    );
  }
}
