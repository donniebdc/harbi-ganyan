import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../state/auth.dart';
import '../theme.dart';
import 'auth_sheet.dart';

class _Paket {
  final String key, ad, fiyat;
  final List<String> ozellikler;
  const _Paket(this.key, this.ad, this.fiyat, this.ozellikler);
}

/// Kademe sirasi: yalniz UST pakete talep edilebilir (standart<vip).
const _rank = {'standart': 0, 'vip': 1};

const _paketler = [
  _Paket('standart', 'Standart', 'Ucretsiz', [
    'Gecmis Analizler',
    'Istatistikler',
    'Uygulamayi kesfet',
  ]),
  _Paket('vip', 'VIP', 'Haftalik 250 TL', [
    'Standart paketindeki her sey',
    'Gunluk Tahminler (5 Satir)',
    '6 li Ganyan Tahminleri',
    'Sonuc bildirimleri',
    'Oncelikli destek',
  ]),
];

class UyelikEkrani extends ConsumerWidget {
  const UyelikEkrani({super.key});

  Future<void> _sec(BuildContext context, WidgetRef ref, _Paket p) async {
    final auth = ref.read(authProvider);
    if (p.key == 'standart') return;
    if (!auth.girisli) {
      await authSheetGoster(context);
      return;
    }
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        backgroundColor: HG.kart2,
        content: Text('${p.ad} uyelik talebiniz alindi. Admin/odeme onayi sonrasi aktiflesir.'),
      ));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Uyelik Paketleri',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        Text('Mevcut: ${auth.tier.toUpperCase()}${auth.email != null ? " · ${auth.email}" : " · anonim"}',
            style: const TextStyle(color: HG.metinSoluk, fontSize: 12)),
        const SizedBox(height: 16),
        ..._paketler.map((p) => _PaketKarti(
              paket: p,
              aktif: auth.tier == p.key,
              talepEdilebilir:
                  (_rank[p.key] ?? 0) > (_rank[auth.tier] ?? 0),
              onSec: () => _sec(context, ref, p),
            )),
        const SizedBox(height: 8),
        const Text(
            'Uyelik aktivasyonu admin panelinden veya odeme entegrasyonu tamamlandiginda otomatik yapilir.',
            style: TextStyle(color: HG.metinSoluk, fontSize: 11)),
      ],
    );
  }
}

class _PaketKarti extends StatelessWidget {
  final _Paket paket;
  final bool aktif;
  final bool talepEdilebilir;
  final VoidCallback onSec;
  const _PaketKarti(
      {required this.paket,
      required this.aktif,
      required this.talepEdilebilir,
      required this.onSec});

  @override
  Widget build(BuildContext context) {
    final vip = paket.key == 'vip';
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: HG.kart,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: aktif ? HG.altin : (vip ? HG.altin.withValues(alpha: 0.4) : HG.kart2),
            width: aktif ? 2 : 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(paket.ad,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(width: 8),
          if (aktif)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                  color: HG.yesil.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6)),
              child: const Text('AKTIF',
                  style: TextStyle(
                      color: HG.yesil, fontSize: 10, fontWeight: FontWeight.w800)),
            ),
          const Spacer(),
          Text(paket.fiyat,
              style: const TextStyle(
                  color: HG.altinAcik, fontWeight: FontWeight.w700, fontSize: 14)),
        ]),
        const SizedBox(height: 12),
        ...paket.ozellikler.map((o) => Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(children: [
                const Icon(Icons.check, size: 16, color: HG.yesil),
                const SizedBox(width: 8),
                Expanded(child: Text(o, style: const TextStyle(fontSize: 13))),
              ]),
            )),
        if (talepEdilebilir) ...[
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: vip ? HG.altin : HG.kart2,
                  foregroundColor: vip ? Colors.black : HG.metin,
                  padding: const EdgeInsets.symmetric(vertical: 12)),
              onPressed: onSec,
              child: Text('${paket.ad} Talep Et',
                  style: const TextStyle(fontWeight: FontWeight.w800)),
            ),
          ),
        ],
      ]),
    );
  }
}
