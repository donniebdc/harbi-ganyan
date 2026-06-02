import 'dart:async';

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

class _GununState extends ConsumerState<GununAnalizleri>
    with WidgetsBindingObserver {
  String? _secili;

  /// Canlı (bugün) günde otomatik yenileme zamanlayıcısı.
  Timer? _canliTimer;

  /// Şu an ekranda gösterilen ve canlı yenilenmesi gereken günün tarihi.
  /// null ise yenilenecek canlı gün yok (yarın/yakında/geçmiş seçili).
  String? _canliDate;

  static const _yenilemeAralik = Duration(seconds: 60);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    _canliTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Uygulama ön plana dönünce 1 kez tazele (canlı gün varsa).
    if (state == AppLifecycleState.resumed) {
      _yenile();
    }
  }

  /// Canlı günün verisini sessizce tazeler. skipLoadingOnReload sayesinde
  /// liste yeniden inşa edilmez; kullanıcının scroll konumu korunur.
  void _yenile() {
    final d = _canliDate;
    if (d == null) return;
    ref.invalidate(gunDetayProvider(d));
    ref.invalidate(gunlerProvider); // aktif/sonuç durumları da güncellensin
  }

  /// Seçili gün canlı (bugün) ise timer'ı kurar; değilse durdurur.
  void _timerAyarla(String? canliDate) {
    if (canliDate == _canliDate) return; // değişiklik yok
    _canliDate = canliDate;
    _canliTimer?.cancel();
    if (canliDate != null) {
      _canliTimer = Timer.periodic(_yenilemeAralik, (_) => _yenile());
    }
  }

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
      // Arka plan yenilemesinde tüm ekranı loading'e düşürme (scroll korunur).
      skipLoadingOnReload: true,
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(onTekrar: () => ref.invalidate(gunlerProvider)),
      data: (gunler) {
        // Gösterilecek günler = bugün (aktif) + yarın (aktif VEYA yakında).
        // Yakında günü şeritte görünür ama içeriği 18:00'e kadar kilitli.
        final gosterilecekler = gunler.where((g) => g.aktif || g.yakinda).toList()
          ..sort((a, b) => a.date.compareTo(b.date));
        if (gosterilecekler.isEmpty) {
          return const BosKutu('Henüz analiz yayınlanmadı.', ikon: Icons.event_busy);
        }
        final bugun = gosterilecekler.first.date; // en küçük tarih = bugün
        // Seçili gün hâlâ listede mi? değilse bugüne dön.
        final secili =
            (_secili != null && gosterilecekler.any((g) => g.date == _secili))
                ? _secili!
                : bugun;
        final secGun = gosterilecekler.firstWhere((g) => g.date == secili);

        // Canlı yenileme yalnızca BUGÜN + içeriği açık (yakında/kilit değil) günde.
        final canli = (secili == bugun && !secGun.yakinda && !secGun.kilit);
        WidgetsBinding.instance.addPostFrameCallback(
            (_) => _timerAyarla(canli ? secili : null));

        return Column(children: [
          if (gosterilecekler.length > 1)
            TarihSeridi(
              gunler: gosterilecekler,
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
    // Yarının analizi DB'de hazır olsa da 18:00'e kadar içerik kilitli (madde 1).
    if (secGun.yakinda) {
      return _YakindaKart(yayinSaati: secGun.yayinSaati);
    }
    if (secGun.kilit) {
      return PaywallKart(
          girisli: auth.girisli,
          onAksiyon: () => _paywallAksiyon(auth.girisli));
    }
    final detay = ref.watch(gunDetayProvider(secGun.date));
    return detay.when(
      // Arka plan yenilemelerinde (timer/foreground) yükleme ekranı gösterme;
      // önceki veriyi koru ki kullanıcının scroll konumu kaybolmasın.
      skipLoadingOnReload: true,
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

/// Yarının analizleri henüz yayınlanmadığında (saat < 18:00) gösterilen kart.
class _YakindaKart extends StatelessWidget {
  final int yayinSaati;
  const _YakindaKart({required this.yayinSaati});
  @override
  Widget build(BuildContext context) {
    final saat = '${yayinSaati.toString().padLeft(2, '0')}:00';
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.schedule, color: HG.altin, size: 56),
            const SizedBox(height: 20),
            Text(
              'Analizler $saat itibariyle aktif olacaktır',
              textAlign: TextAlign.center,
              style: const TextStyle(
                  fontSize: 16, fontWeight: FontWeight.w700, color: HG.metin),
            ),
            const SizedBox(height: 10),
            const Text(
              'Yarının 5 satır ve 6\'lı ganyan analizleri hazırlanıyor. '
              'Yayınlandığında bildirim alacaksınız.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: HG.metinSoluk),
            ),
          ],
        ),
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
