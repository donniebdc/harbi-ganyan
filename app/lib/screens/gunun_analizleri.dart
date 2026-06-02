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
import '../widgets/tarih_seridi.dart';
import 'auth_sheet.dart';
import 'gun_icerik.dart';

/// Aktif analizler (bugün + yayınlanmışsa yarın). 5 satır / 6'lı sekmeleri bunu kullanır.
/// Üstte tarih şeridi (BUGÜN / YARIN), içerik premium-kilitli.
class GununAnalizleri extends ConsumerStatefulWidget {
  final GunIcerikModu mod;
  const GununAnalizleri({this.mod = GunIcerikModu.tumu, super.key});

  @override
  ConsumerState<GununAnalizleri> createState() => _GununState();
}

class _GununState extends ConsumerState<GununAnalizleri> {
  String? _secili;

  void _paywallAksiyon(bool girisli) {
    if (!girisli) {
      authSheetGoster(context);
    } else {
      ref.read(navIndexProvider.notifier).sec(profilSekme);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    final gunlerAsync = ref.watch(gunlerProvider);

    return gunlerAsync.when(
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(onTekrar: () => ref.invalidate(gunlerProvider)),
      data: (gunler) {
        // Aktif günler = bugün + (yayınlanmışsa) yarın; artan sırada (bugün ilk).
        final aktifler = gunler.where((g) => g.aktif).toList()
          ..sort((a, b) => a.date.compareTo(b.date));
        if (aktifler.isEmpty) {
          return const BosKutu('Henüz analiz yayınlanmadı.', ikon: Icons.event_busy);
        }
        final bugun = aktifler.first.date; // en küçük aktif tarih = bugün
        // Seçili gün hâlâ aktif mi? değilse bugüne dön.
        final secili =
            (_secili != null && aktifler.any((g) => g.date == _secili))
                ? _secili!
                : bugun;
        final secGun = aktifler.firstWhere((g) => g.date == secili);

        return Column(children: [
          if (aktifler.length > 1)
            TarihSeridi(
              gunler: aktifler,
              secili: secili,
              onSec: (d) => setState(() => _secili = d),
              ustEtiket: (g) => g.date == bugun ? 'BUGÜN' : 'YARIN',
            ),
          _Baslik(date: secili, bugun: secili == bugun),
          Expanded(child: _icerik(auth, secGun)),
        ]);
      },
    );
  }

  Widget _icerik(AuthState auth, GunOzet secGun) {
    if (secGun.kilit) {
      return PaywallKart(
          girisli: auth.girisli,
          onAksiyon: () => _paywallAksiyon(auth.girisli));
    }
    final detay = ref.watch(gunDetayProvider(secGun.date));
    return detay.when(
      loading: () => const Yukleniyor(),
      error: (e, _) {
        if (e is KilitliHata) {
          return PaywallKart(
              girisli: auth.girisli,
              onAksiyon: () => _paywallAksiyon(auth.girisli));
        }
        return HataKutu(
            onTekrar: () => ref.invalidate(gunDetayProvider(secGun.date)));
      },
      data: (d) => RefreshIndicator(
        color: HG.altin,
        onRefresh: () async => ref.invalidate(gunDetayProvider(secGun.date)),
        child: GunIcerik(d, mod: widget.mod),
      ),
    );
  }
}

class _Baslik extends StatelessWidget {
  final String date;
  final bool bugun;
  const _Baslik({required this.date, required this.bugun});
  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
        child: Row(children: [
          Icon(bugun ? Icons.today : Icons.event, color: HG.altin, size: 18),
          const SizedBox(width: 8),
          Text(tarihUzun(date),
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
                color: HG.altin.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(6)),
            child: Text(bugun ? 'CANLI' : 'YARIN',
                style: const TextStyle(
                    color: HG.altin, fontSize: 10, fontWeight: FontWeight.w800)),
          ),
        ]),
      );
}
