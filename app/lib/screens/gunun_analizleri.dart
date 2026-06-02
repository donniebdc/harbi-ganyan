import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../state/auth.dart';
import '../state/content.dart';
import '../state/nav.dart';
import '../theme.dart';
import '../util.dart';
import '../widgets/durumlar.dart';
import '../widgets/paywall.dart';
import 'auth_sheet.dart';
import 'gun_icerik.dart';

class GununAnalizleri extends ConsumerWidget {
  final GunIcerikModu mod;
  const GununAnalizleri({this.mod = GunIcerikModu.tumu, super.key});

  void _paywallAksiyon(BuildContext context, WidgetRef ref, bool girisli) {
    if (!girisli) {
      authSheetGoster(context);
    } else {
      ref.read(navIndexProvider.notifier).sec(profilSekme);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    final gunlerAsync = ref.watch(gunlerProvider);

    return gunlerAsync.when(
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(onTekrar: () => ref.invalidate(gunlerProvider)),
      data: (gunler) {
        GunOzet? gunun;
        for (final g in gunler) {
          if (g.gununAnalizi) {
            gunun = g;
            break;
          }
        }
        gunun ??= gunler.isNotEmpty ? gunler.first : null;
        if (gunun == null) {
          return const BosKutu('Henuz analiz yayinlanmadi.', ikon: Icons.event_busy);
        }
        if (gunun.kilit) {
          return PaywallKart(
              girisli: auth.girisli,
              onAksiyon: () => _paywallAksiyon(context, ref, auth.girisli));
        }
        final date = gunun.date;
        final detay = ref.watch(gunDetayProvider(date));
        return Column(children: [
          _Baslik(date),
          Expanded(
            child: detay.when(
              loading: () => const Yukleniyor(),
              error: (e, _) {
                if (e is KilitliHata) {
                  return PaywallKart(
                      girisli: auth.girisli,
                      onAksiyon: () => _paywallAksiyon(context, ref, auth.girisli));
                }
                return HataKutu(onTekrar: () => ref.invalidate(gunDetayProvider(date)));
              },
              data: (d) => RefreshIndicator(
                color: HG.altin,
                onRefresh: () async => ref.invalidate(gunDetayProvider(date)),
                child: GunIcerik(d, mod: mod),
              ),
            ),
          ),
        ]);
      },
    );
  }
}

class _Baslik extends StatelessWidget {
  final String date;
  const _Baslik(this.date);
  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Row(children: [
          const Icon(Icons.today, color: HG.altin, size: 18),
          const SizedBox(width: 8),
          Text(tarihUzun(date),
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
                color: HG.altin.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(6)),
            child: const Text('CANLI',
                style: TextStyle(
                    color: HG.altin, fontSize: 10, fontWeight: FontWeight.w800)),
          ),
        ]),
      );
}
