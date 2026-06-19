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
      skipError: true,
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(
          mesaj: e is AgHatasi ? e.mesaj : null,
          hata: e,
          onTekrar: () => ref.invalidate(gunlerProvider)),
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
      skipError: true,
      loading: () => const Yukleniyor(),
      error: (e, _) {
        if (e is KilitliHata) {
          return _VipKilit(
              girisli: auth.girisli,
              onAksiyon: () => _kilitAksiyon(auth.girisli));
        }
        return HataKutu(
            mesaj: e is AgHatasi ? e.mesaj : null,
            hata: e,
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
          subtitle: const Text('TJK RESMİ ALT OYUNLARI',
              style: TextStyle(
                  color: HG.altin,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.3)),
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
          subtitle: Text('${bahisler.length} ALT OYUN',
              style: const TextStyle(
                  color: HG.altin,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.3)),
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

  bool get _plase => b.tip == 'PLASE';

  /// Kolon i için gerçek kazanan at_no kümesi (yeşil [ ] işareti).
  Set<int> _winset(int i) {
    final s = b.sonuc;
    if (s == null || i >= s.kazanan.length) return const {};
    return s.kazanan[i].toSet();
  }

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
          // Başlık + ANALİZ BAŞARILI/BAŞARISIZ rozeti
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(
              child: Text(b.ad,
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, fontSize: 14)),
            ),
            if (sonuc != null) _AnalizRozet(sonuc.tuttu),
          ]),
          const SizedBox(height: 8),
          ..._kolonSatirlari(),
          const SizedBox(height: 8),
          // N MİSLİ | TL (camgöbeği)
          Text('${b.misli} MİSLİ | ${_para(b.kuponBedeli * b.misli)} TL',
              style: const TextStyle(
                  color: HG.camgobegi,
                  fontWeight: FontWeight.w800,
                  fontSize: 13)),
          if (sonuc != null) ...[
            const SizedBox(height: 8),
            const Divider(height: 1, color: HG.kart2),
            const SizedBox(height: 8),
            ..._sonucSatirlari(sonuc),
          ],
        ],
      ),
    );
  }

  /// Kolon satırları: "1. KOLON   2 / [4] / 8" (kazanan yeşil). Plase tek atı
  /// etiketsiz gösterir; çok-ayakta koşu no etiketi.
  List<Widget> _kolonSatirlari() {
    final out = <Widget>[];
    final tekKolon = b.kolonlar.length <= 1;
    for (var i = 0; i < b.kolonlar.length; i++) {
      final nos = b.kolonlar[i];
      final win = _winset(i);
      String? etiket;
      if (b.aile == 'ayak') {
        etiket = (i < b.legs.length) ? '${b.legs[i]}. KOŞU' : 'AYAK ${i + 1}';
      } else if (!tekKolon) {
        etiket = '${i + 1}. KOLON';
      }
      out.add(Padding(
        padding: const EdgeInsets.only(bottom: 3),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (etiket != null)
            SizedBox(
              width: 74,
              child: Text(etiket,
                  style: const TextStyle(
                      color: HG.metinSoluk,
                      fontSize: 12,
                      fontWeight: FontWeight.w700)),
            ),
          Expanded(child: _kolonNumaralar(nos, win)),
        ]),
      ));
    }
    return out;
  }

  /// "2 / [4] / 8" — kazananlar yeşil köşeli parantez.
  Widget _kolonNumaralar(List<int> nos, Set<int> win) {
    final spans = <InlineSpan>[];
    for (var i = 0; i < nos.length; i++) {
      if (i > 0) {
        spans.add(const TextSpan(
            text: ' / ', style: TextStyle(color: HG.metinSoluk)));
      }
      final no = nos[i];
      final kazanan = win.contains(no);
      spans.add(TextSpan(
        text: kazanan ? '[$no]' : '$no',
        style: TextStyle(
            color: kazanan ? HG.yesil : HG.metin,
            fontWeight: kazanan ? FontWeight.w800 : FontWeight.w600),
      ));
    }
    return RichText(
      text: TextSpan(style: const TextStyle(fontSize: 13.5), children: spans),
    );
  }

  /// KAZANAN (sarı) / İKRAMİYE (sarı) / KAZANÇ (yeşil, ayrı satır) satırları.
  List<Widget> _sonucSatirlari(BahisSonuc s) {
    final out = <Widget>[];
    // KAZANAN: gerçekleşen kazanan no'lar (yalnız numara).
    final flat = <int>[for (final c in s.kazanan) ...c];
    if (flat.isNotEmpty) {
      out.add(_sonucSatir('KAZANAN', flat.map((no) => '$no').join(' / ')));
    }
    // İKRAMİYE: tutarsa her zaman; tutmadıysa Plase hariç (resmi ödeme biliniyorsa).
    final ikr = s.ikramiye;
    if (ikr != null && (s.tuttu || !_plase)) {
      // Sonucu açıklanmış ikramiye -> turkuaz (farkındalık).
      out.add(_sonucSatir('İKRAMİYE', _para(ikr), renk: HG.camgobegi));
      if (s.tuttu) {
        // KAZANÇ ayrı satır + yeşil
        out.add(_sonucSatir(
            'KAZANÇ', '${_para(ikr)} * ${b.misli} = ${_para(s.net ?? ikr * b.misli)}',
            renk: HG.yesil));
      }
    }
    return out;
  }

  Widget _sonucSatir(String etiket, String deger, {Color renk = HG.altin}) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 3),
      child: RichText(
        text: TextSpan(
          style: TextStyle(
              color: renk, fontSize: 12.5, fontWeight: FontWeight.w700),
          children: [
            TextSpan(text: '$etiket : '),
            TextSpan(
                text: deger, style: const TextStyle(fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}

/// ANALİZ BAŞARILI / BAŞARISIZ rozeti (kartın sağ üstü).
class _AnalizRozet extends StatelessWidget {
  final bool basarili;
  const _AnalizRozet(this.basarili);
  @override
  Widget build(BuildContext context) {
    return Text(basarili ? 'ANALİZ BAŞARILI' : 'ANALİZ BAŞARISIZ',
        style: TextStyle(
            color: basarili ? HG.yesil : HG.kirmizi,
            fontSize: 10,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.2));
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
