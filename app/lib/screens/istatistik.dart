import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../state/content.dart';
import '../theme.dart';
import '../widgets/durumlar.dart';
import '../widgets/rozet.dart';

class IstatistikEkrani extends ConsumerStatefulWidget {
  const IstatistikEkrani({super.key});
  @override
  ConsumerState<IstatistikEkrani> createState() => _IstatistikState();
}

class _IstatistikState extends ConsumerState<IstatistikEkrani> {
  bool _aylik = false;

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(istatistikProvider);
    return async.when(
      skipLoadingOnReload: true,
      skipError: true,
      loading: () => const Yukleniyor(),
      error: (e, _) => HataKutu(
          mesaj: e is AgHatasi ? e.mesaj : null,
          hata: e,
          onTekrar: () => ref.invalidate(istatistikProvider)),
      data: (ist) {
        final d = _aylik ? ist.ay : ist.hafta;
        return RefreshIndicator(
          color: HG.altin,
          onRefresh: () async => ref.invalidate(istatistikProvider),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
            children: [
              _gecis(),
              const SizedBox(height: 14),
              _besKart(d),
              const SizedBox(height: 12),
              for (final t in d.tierler) ...[
                _tierKart(t),
                const SizedBox(height: 12),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _gecis() {
    return Container(
      decoration: BoxDecoration(
        color: HG.kart,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: HG.kart2),
      ),
      padding: const EdgeInsets.all(4),
      child: Row(children: [
        _gecisBtn('Haftalık', !_aylik, () => setState(() => _aylik = false)),
        _gecisBtn('Aylık', _aylik, () => setState(() => _aylik = true)),
      ]),
    );
  }

  Widget _gecisBtn(String etiket, bool secili, VoidCallback onTap) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(9),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: secili ? HG.altin : Colors.transparent,
            borderRadius: BorderRadius.circular(9),
          ),
          alignment: Alignment.center,
          child: Text(etiket,
              style: TextStyle(
                  color: secili ? Colors.black : HG.metin,
                  fontWeight: FontWeight.w800,
                  fontSize: 14)),
        ),
      ),
    );
  }

  Widget _besKart(IstatistikDonem d) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: _kutuDeko(HG.altin),
      child: Row(children: [
        const Icon(Icons.format_list_numbered, color: HG.altin, size: 28),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('5 Satır Tahmin',
                style: TextStyle(
                    color: HG.camgobegi, fontWeight: FontWeight.w800, fontSize: 16)),
            const SizedBox(height: 2),
            Text('${d.besIsabet} / ${d.besToplam} koşu isabet',
                style: const TextStyle(
                    color: HG.altin, fontSize: 13, fontWeight: FontWeight.w700)),
          ]),
        ),
        Text('%${d.besYuzde.toStringAsFixed(1)}',
            style: const TextStyle(
                color: HG.yesil, fontWeight: FontWeight.w900, fontSize: 22)),
      ]),
    );
  }

  Widget _tierKart(TierIstat t) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: _kutuDeko(HG.kart2),
      child: Row(children: [
        const Icon(Icons.casino, color: HG.altin, size: 20),
        const SizedBox(width: 10),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(t.ad,
                style: const TextStyle(
                    color: HG.metin, fontWeight: FontWeight.w800, fontSize: 15)),
            const SizedBox(height: 4),
            Text('${t.tuttu} / ${t.toplam} altılı tutturma',
                style: const TextStyle(color: HG.metinSoluk, fontSize: 12)),
          ]),
        ),
        Text('%${t.yuzde.toStringAsFixed(1)}',
            style: const TextStyle(
                color: HG.yesil, fontWeight: FontWeight.w900, fontSize: 22)),
      ]),
    );
  }

  BoxDecoration _kutuDeko(Color kenar) => BoxDecoration(
        color: HG.kart,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: kenar.withValues(alpha: 0.4)),
      );
}
