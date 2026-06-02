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
import '../widgets/tarih_seridi.dart';
import 'auth_sheet.dart';

/// Koşu Analizleri (VIP) — koşu türlerine göre alt-bahis analizleri.
/// Açılır-kapanır koşu kartları; TJK ganyanı açıklanınca canlı grading
/// (kazanan atlar [] içinde, tutan bahiste net kazanç). Auto-refresh + scroll korunur.
class KosuAnalizleri extends ConsumerStatefulWidget {
  const KosuAnalizleri({super.key});
  @override
  ConsumerState<KosuAnalizleri> createState() => _KosuAnalizleriState();
}

class _KosuAnalizleriState extends ConsumerState<KosuAnalizleri>
    with WidgetsBindingObserver {
  String? _secili;
  Timer? _timer;
  String? _canliDate;
  static const _aralik = Duration(seconds: 60);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    if (s == AppLifecycleState.resumed) _yenile();
  }

  void _yenile() {
    final d = _canliDate;
    if (d == null) return;
    ref.invalidate(gunBahislerProvider(d));
    ref.invalidate(gunlerProvider);
  }

  void _timerAyarla(String? canli) {
    if (canli == _canliDate) return;
    _canliDate = canli;
    _timer?.cancel();
    if (canli != null) _timer = Timer.periodic(_aralik, (_) => _yenile());
  }

  void _kilitAksiyon(bool girisli) {
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
      skipLoadingOnReload: true,
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(onTekrar: () => ref.invalidate(gunlerProvider)),
      data: (gunler) {
        // Geçmiş + bugün + (yayınlanmışsa) yarın — hepsi gösterilir ki geçmiş
        // günlerin alt-bahis analizleri de incelenebilsin. Provider desc sıralı gelir.
        final list = [...gunler]..sort((a, b) => b.date.compareTo(a.date));
        if (list.isEmpty) {
          return const BosKutu('Henüz analiz yayınlanmadı.', ikon: Icons.event_busy);
        }
        final bugunIso = _bugunIso();
        final yarinIso = _yarinIso();
        // Varsayılan seçim: bugün listede ise bugün, değilse en yeni gün.
        final varsayilan =
            list.any((g) => g.date == bugunIso) ? bugunIso : list.first.date;
        final secili = (_secili != null && list.any((g) => g.date == _secili))
            ? _secili!
            : varsayilan;
        final secGun = list.firstWhere((g) => g.date == secili);
        // Canlı yenileme yalnız bugün (aktif, yakında değil).
        final canli = secili == bugunIso && secGun.aktif && !secGun.yakinda;
        WidgetsBinding.instance
            .addPostFrameCallback((_) => _timerAyarla(canli ? secili : null));

        return Column(children: [
          TarihSeridi(
            gunler: list,
            secili: secili,
            onSec: (d) => setState(() => _secili = d),
            ustEtiket: (g) => g.date == bugunIso
                ? 'BUGÜN'
                : (g.date == yarinIso ? 'YARIN' : gunAdi(g.date)),
          ),
          Expanded(child: _icerik(auth, secGun)),
        ]);
      },
    );
  }

  Widget _icerik(AuthState auth, GunOzet secGun) {
    if (secGun.yakinda) {
      return _Bilgi(
          ikon: Icons.schedule,
          baslik: 'Analizler ${secGun.yayinSaati.toString().padLeft(2, '0')}:00 '
              'itibariyle aktif olacaktır',
          metin: 'Yarının koşu analizleri hazırlanıyor.');
    }
    final async = ref.watch(gunBahislerProvider(secGun.date));
    return async.when(
      skipLoadingOnReload: true,
      loading: () => const Yukleniyor(),
      error: (e, _) {
        if (e is KilitliHata) {
          return _VipKilit(
              girisli: auth.girisli,
              onAksiyon: () => _kilitAksiyon(auth.girisli));
        }
        return HataKutu(
            onTekrar: () => ref.invalidate(gunBahislerProvider(secGun.date)));
      },
      data: (gb) {
        final hips = gb.hipodromlar.where((h) => h.bahisler.isNotEmpty).toList();
        if (hips.isEmpty) {
          return const BosKutu('Bu güne ait bahis analizi yok.',
              ikon: Icons.insights);
        }
        return RefreshIndicator(
          color: HG.altin,
          onRefresh: () async => ref.invalidate(gunBahislerProvider(secGun.date)),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
            children: [for (final h in hips) _HipBolum(h)],
          ),
        );
      },
    );
  }
}

/// Bir hipodromun bahisleri — başlangıç koşusuna göre gruplanıp açılır-kapanır.
class _HipBolum extends StatelessWidget {
  final BahisHip h;
  const _HipBolum(this.h);
  @override
  Widget build(BuildContext context) {
    // bas_kosu'ya göre grupla
    final gruplar = <int, List<BahisAnaliz>>{};
    for (final b in h.bahisler) {
      gruplar.putIfAbsent(b.basKosu, () => []).add(b);
    }
    final knos = gruplar.keys.toList()..sort();
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: HG.kart,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: HG.kart2),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          initiallyExpanded: true,
          shape: const Border(),
          collapsedShape: const Border(),
          leading: const Icon(Icons.stadium, color: HG.altin),
          title: Text(h.hipodrom,
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
          subtitle: Text('${h.bahisler.length} bahis analizi',
              style: const TextStyle(color: HG.metinSoluk, fontSize: 12)),
          childrenPadding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
          children: [for (final k in knos) _KosuGrup(k, gruplar[k]!)],
        ),
      ),
    );
  }
}

/// Bir koşunun (bas_kosu) bahisleri — açılır-kapanır alt menü.
class _KosuGrup extends StatelessWidget {
  final int kno;
  final List<BahisAnaliz> bahisler;
  const _KosuGrup(this.kno, this.bahisler);
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: HG.zemin,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: HG.kart2),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          shape: const Border(),
          collapsedShape: const Border(),
          tilePadding: const EdgeInsets.symmetric(horizontal: 12),
          title: Text('$kno. Koşu',
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
          subtitle: Text('${bahisler.length} bahis türü',
              style: const TextStyle(color: HG.metinSoluk, fontSize: 11)),
          childrenPadding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
          children: [for (final b in bahisler) _BahisKart(b)],
        ),
      ),
    );
  }
}

class _BahisKart extends StatelessWidget {
  final BahisAnaliz b;
  const _BahisKart(this.b);

  @override
  Widget build(BuildContext context) {
    final sonuc = b.sonuc;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: HG.kart,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: HG.kart2),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(
              child: Text(
                b.aile == 'ayak' && b.legs.length > 1
                    ? '${b.ad}  (${b.legs.first}-${b.legs.last}. koşu)'
                    : b.ad,
                style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14),
              ),
            ),
            if (sonuc != null) _SonucRozet(sonuc),
          ]),
          const SizedBox(height: 8),
          ..._kolonlar(),
          const SizedBox(height: 8),
          _kuponBilgi(),
          if (sonuc != null && sonuc.tuttu) ...[
            const SizedBox(height: 6),
            _netSatir(sonuc),
          ],
        ],
      ),
    );
  }

  /// Kazanan at_no kümeleri (kolon bazında). Tek bahiste hepsi tek havuzda.
  List<Set<int>> _kazananlar() {
    final s = b.sonuc;
    if (s == null) return [];
    return s.kazanan.map((c) => c.toSet()).toList();
  }

  List<Widget> _kolonlar() {
    final kaz = _kazananlar();
    if (b.aile == 'tek') {
      // tek havuz; kazanan = tüm kazanan kolonların birleşimi
      final winset = <int>{for (final c in kaz) ...c};
      final atlar = (b.secimAtlar)
          .map((e) => e as Map<String, dynamic>)
          .toList();
      return [_atSatiri('Seçilen', atlar, winset)];
    }
    // çok-ayak: her ayak ayrı satır
    final out = <Widget>[];
    for (var i = 0; i < b.secimAtlar.length; i++) {
      final atlar = (b.secimAtlar[i] as List)
          .map((e) => e as Map<String, dynamic>)
          .toList();
      final winset = (i < kaz.length) ? kaz[i] : <int>{};
      final etiket = (i < b.legs.length) ? '${b.legs[i]}. koşu' : 'Ayak ${i + 1}';
      out.add(_atSatiri(etiket, atlar, winset));
    }
    return out;
  }

  Widget _atSatiri(String etiket, List<Map<String, dynamic>> atlar, Set<int> win) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 64,
          child: Text(etiket,
              style: const TextStyle(color: HG.metinSoluk, fontSize: 11)),
        ),
        Expanded(
          child: Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final a in atlar)
                _atCip(a['at_no'] as int, a['at'] as String? ?? '',
                    win.contains(a['at_no'])),
            ],
          ),
        ),
      ]),
    );
  }

  Widget _atCip(int no, String ad, bool kazanan) {
    final metin = ad.isEmpty ? '$no' : '$no $ad';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: kazanan ? HG.yesil.withValues(alpha: 0.18) : HG.kart2,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
            color: kazanan ? HG.yesil : Colors.transparent, width: 1),
      ),
      child: Text(kazanan ? '[ $metin ]' : metin,
          style: TextStyle(
              fontSize: 12,
              fontWeight: kazanan ? FontWeight.w800 : FontWeight.w500,
              color: kazanan ? HG.yesil : HG.metin)),
    );
  }

  Widget _kuponBilgi() {
    return Text(
      '${b.kombinasyon} kombinasyon × ${b.misli} misli  ·  '
      'Kupon ${_para(b.kuponBedeli * b.misli)} TL',
      style: const TextStyle(color: HG.metinSoluk, fontSize: 11.5),
    );
  }

  Widget _netSatir(BahisSonuc s) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: HG.yesil.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        'Ganyan ${_para(s.ganyan ?? 0)} × ${b.misli} misli = '
        '${_para(s.net ?? 0)} TL',
        style: const TextStyle(
            color: HG.yesil, fontWeight: FontWeight.w800, fontSize: 13),
      ),
    );
  }
}

class _SonucRozet extends StatelessWidget {
  final BahisSonuc s;
  const _SonucRozet(this.s);
  @override
  Widget build(BuildContext context) {
    final tuttu = s.tuttu;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: (tuttu ? HG.yesil : HG.kirmizi).withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(tuttu ? '✓ TUTTU' : '✗ TUTMADI',
          style: TextStyle(
              color: tuttu ? HG.yesil : HG.kirmizi,
              fontSize: 10,
              fontWeight: FontWeight.w800)),
    );
  }
}

/// VIP kilidi kartı.
class _VipKilit extends StatelessWidget {
  final bool girisli;
  final VoidCallback onAksiyon;
  const _VipKilit({required this.girisli, required this.onAksiyon});
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
                color: HG.altin.withValues(alpha: 0.12), shape: BoxShape.circle),
            child: const Icon(Icons.diamond, color: HG.altin, size: 48),
          ),
          const SizedBox(height: 18),
          const Text('Koşu Analizleri VIP\'e Özel',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 10),
          const Text(
              'Koşu türlerine göre alt-bahis analizleri (ikili, sıralı, üçlü, '
              'tabela, çoklu ganyan ve daha fazlası) ve canlı sonuç takibi '
              'VIP üyelere açıktır.',
              textAlign: TextAlign.center,
              style: TextStyle(color: HG.metinSoluk, fontSize: 13, height: 1.4)),
          const SizedBox(height: 22),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: HG.altin,
                  foregroundColor: Colors.black,
                  padding: const EdgeInsets.symmetric(vertical: 14)),
              onPressed: onAksiyon,
              child: Text(girisli ? 'VIP\'e Yükselt' : 'Giriş Yap / Üye Ol',
                  style: const TextStyle(fontWeight: FontWeight.w800)),
            ),
          ),
        ]),
      ),
    );
  }
}

class _Bilgi extends StatelessWidget {
  final IconData ikon;
  final String baslik, metin;
  const _Bilgi({required this.ikon, required this.baslik, required this.metin});
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(ikon, color: HG.altin, size: 56),
            const SizedBox(height: 20),
            Text(baslik,
                textAlign: TextAlign.center,
                style: const TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w700, color: HG.metin)),
            const SizedBox(height: 10),
            Text(metin,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 13, color: HG.metinSoluk)),
          ]),
        ),
      );
}

String _iki(int n) => n.toString().padLeft(2, '0');
String _bugunIso() {
  final n = DateTime.now();
  return '${n.year}-${_iki(n.month)}-${_iki(n.day)}';
}

String _yarinIso() {
  final n = DateTime.now().add(const Duration(days: 1));
  return '${n.year}-${_iki(n.month)}-${_iki(n.day)}';
}

String _para(double x) {
  // 12948.06 -> "12.948,06"
  final s = x.toStringAsFixed(2);
  final parts = s.split('.');
  final tam = parts[0];
  final buf = StringBuffer();
  for (var i = 0; i < tam.length; i++) {
    if (i > 0 && (tam.length - i) % 3 == 0) buf.write('.');
    buf.write(tam[i]);
  }
  return '$buf,${parts[1]}';
}
