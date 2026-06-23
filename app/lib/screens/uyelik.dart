import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:in_app_purchase/in_app_purchase.dart';
import '../services/billing_service.dart';
import '../state/auth.dart';
import '../theme.dart';
import 'auth_sheet.dart';

class _Paket {
  final String productId, ad, fiyat, aciklama;
  const _Paket(this.productId, this.ad, this.fiyat, this.aciklama);
}

const _paketler = [
  _Paket('vip_haftalik', 'VIP Haftalik', '249,99 TL/hafta',
      'Her hafta otomatik yenilenir'),
  _Paket('vip_aylik', 'VIP Aylik', '899,99 TL/ay',
      'En avantajli secim — ayda yalnizca ~225 TL/hafta'),
];

class UyelikEkrani extends ConsumerStatefulWidget {
  const UyelikEkrani({super.key});
  @override
  ConsumerState<UyelikEkrani> createState() => _UyelikEkraniState();
}

class _UyelikEkraniState extends ConsumerState<UyelikEkrani> {
  final _billing = BillingService();
  List<ProductDetails> _urunler = [];
  bool _yukleniyor = false;
  String? _hata;

  @override
  void initState() {
    super.initState();
    _baslat();
  }

  Future<void> _baslat() async {
    await _billing.baslat();
    _billing.satinAlmalar.listen(_satinAlmaGeldi);
    final urunler = await _billing.urunleriGetir();
    if (mounted) setState(() => _urunler = urunler);
  }

  Future<void> _satinAlmaGeldi(PurchaseDetails p) async {
    if (p.status == PurchaseStatus.purchased ||
        p.status == PurchaseStatus.restored) {
      _billing.tamamla(p);
      await _dogrula(p);
    } else if (p.status == PurchaseStatus.error) {
      if (mounted) {
        setState(() {
          _hata = p.error?.message ?? 'Satin alma basarisiz.';
          _yukleniyor = false;
        });
      }
    } else if (p.status == PurchaseStatus.canceled) {
      if (mounted) setState(() => _yukleniyor = false);
    }
  }

  Future<void> _dogrula(PurchaseDetails p) async {
    try {
      await ref
          .read(apiClientProvider)
          .uyelikDogrula(p.purchaseID ?? '', p.productID);
      await ref.read(authProvider.notifier).tierYenile();
      if (mounted) {
        setState(() => _yukleniyor = false);
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          backgroundColor: HG.yesil,
          content: Text('VIP uyeliginiz aktiflestirildi!'),
        ));
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _hata = e.toString();
          _yukleniyor = false;
        });
      }
    }
  }

  Future<void> _sec(String productId) async {
    final auth = ref.read(authProvider);
    if (!auth.girisli) {
      await authSheetGoster(context);
      return;
    }
    final urun = _urunler.where((u) => u.id == productId).firstOrNull;
    if (urun == null) {
      setState(() => _hata = 'Urun yuklenemedi. Lutfen tekrar deneyin.');
      return;
    }
    setState(() {
      _yukleniyor = true;
      _hata = null;
    });
    await _billing.satinAl(urun);
  }

  @override
  Widget build(BuildContext context) {
    final auth = ref.watch(authProvider);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('VIP Uyelik',
            style: Theme.of(context)
                .textTheme
                .titleLarge
                ?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        Text(
            'Mevcut: ${auth.tier.toUpperCase()}${auth.email != null ? " · ${auth.email}" : ""}',
            style: const TextStyle(color: HG.metinSoluk, fontSize: 12)),
        const SizedBox(height: 16),
        if (auth.vip)
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
                color: HG.yesil.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: HG.yesil)),
            child: const Row(children: [
              Icon(Icons.workspace_premium, color: HG.yesil),
              SizedBox(width: 12),
              Text('VIP uyeliginiz aktif.',
                  style: TextStyle(
                      color: HG.yesil, fontWeight: FontWeight.w700)),
            ]),
          )
        else ...[
          const Text(
              'VIP uyelik ile gunluk 5 satir tahmin ve analiz puanlarina erisin.',
              style: TextStyle(color: HG.metinSoluk, fontSize: 13)),
          const SizedBox(height: 16),
          if (_hata != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(_hata!,
                  style:
                      const TextStyle(color: Colors.redAccent, fontSize: 13)),
            ),
          ..._paketler.map((p) => _PaketKarti(
                paket: p,
                onerilen: p.productId == 'vip_aylik',
                yukleniyor: _yukleniyor,
                onSec: () => _sec(p.productId),
              )),
        ],
        const SizedBox(height: 8),
        const Text(
            'Abonelikler Google Play uzerinden yonetilir. Iptal: Google Play → Abonelikler.',
            style: TextStyle(color: HG.metinSoluk, fontSize: 11)),
      ],
    );
  }
}

class _PaketKarti extends StatelessWidget {
  final _Paket paket;
  final bool onerilen;
  final bool yukleniyor;
  final VoidCallback onSec;

  const _PaketKarti(
      {required this.paket,
      required this.onerilen,
      required this.yukleniyor,
      required this.onSec});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: HG.kart,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: onerilen ? HG.altin : HG.kart2, width: onerilen ? 2 : 1),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(paket.ad,
              style:
                  const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
          if (onerilen) ...[
            const SizedBox(width: 8),
            Container(
              padding:
                  const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(
                  color: HG.altin.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6)),
              child: const Text('EN AVANTAJLI',
                  style: TextStyle(
                      color: HG.altin,
                      fontSize: 9,
                      fontWeight: FontWeight.w800)),
            ),
          ],
          const Spacer(),
          Text(paket.fiyat,
              style: const TextStyle(
                  color: HG.altinAcik,
                  fontWeight: FontWeight.w700,
                  fontSize: 13)),
        ]),
        const SizedBox(height: 4),
        Text(paket.aciklama,
            style: const TextStyle(color: HG.metinSoluk, fontSize: 11)),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: HG.altin,
                foregroundColor: Colors.black,
                padding: const EdgeInsets.symmetric(vertical: 12)),
            onPressed: yukleniyor ? null : onSec,
            child: yukleniyor
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.black))
                : Text('${paket.ad} Satin Al',
                    style:
                        const TextStyle(fontWeight: FontWeight.w800)),
          ),
        ),
      ]),
    );
  }
}
