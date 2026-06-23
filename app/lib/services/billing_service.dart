import 'dart:async';
import 'package:in_app_purchase/in_app_purchase.dart';

const String kVipHaftalik = 'vip_haftalik';
const String kVipAylik = 'vip_aylik';
const Set<String> kUrunler = {kVipHaftalik, kVipAylik};

class BillingService {
  static final BillingService _instance = BillingService._();
  factory BillingService() => _instance;
  BillingService._();

  final InAppPurchase _iap = InAppPurchase.instance;
  StreamSubscription<List<PurchaseDetails>>? _sub;
  final _ctrl = StreamController<PurchaseDetails>.broadcast();

  Stream<PurchaseDetails> get satinAlmalar => _ctrl.stream;

  Future<bool> kullanilabilir() => _iap.isAvailable();

  Future<void> baslat() async {
    _sub ??= _iap.purchaseStream.listen((purchases) {
      for (final p in purchases) {
        _ctrl.add(p);
      }
    });
  }

  Future<List<ProductDetails>> urunleriGetir() async {
    final resp = await _iap.queryProductDetails(kUrunler);
    return resp.productDetails;
  }

  Future<bool> satinAl(ProductDetails urun) async {
    final params = PurchaseParam(productDetails: urun);
    return _iap.buyNonConsumable(purchaseParam: params);
  }

  void tamamla(PurchaseDetails purchase) {
    if (purchase.pendingCompletePurchase) {
      _iap.completePurchase(purchase);
    }
  }

  void dispose() {
    _sub?.cancel();
    _ctrl.close();
  }
}
