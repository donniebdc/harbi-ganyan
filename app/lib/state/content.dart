import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/models.dart';
import 'auth.dart';

/// Geçmiş Analizler tarih şeridi + günün listesi.
final gunlerProvider = FutureProvider.autoDispose<List<GunOzet>>((ref) {
  ref.watch(authProvider); // token/tier değişince yenile
  return ref.watch(apiClientProvider).gunler();
});

/// Bir günün tam analizleri (KilitliHata fırlatabilir).
final gunDetayProvider =
    FutureProvider.autoDispose.family<GunDetay, String>((ref, date) {
  ref.watch(authProvider);
  return ref.watch(apiClientProvider).gun(date);
});

/// Koşu Analizleri (alt-bahisler) — VIP. KilitliHata fırlatabilir.
final gunBahislerProvider =
    FutureProvider.autoDispose.family<GunBahisler, String>((ref, date) {
  ref.watch(authProvider);
  return ref.watch(apiClientProvider).gunBahisler(date);
});

/// Haftalık + aylık istatistik (tutturma + kâr-zarar).
final istatistikProvider = FutureProvider.autoDispose<Istatistik>((ref) {
  ref.watch(authProvider);
  return ref.watch(apiClientProvider).istatistik();
});

/// Kullanıcının bildirimleri (en yeni -> en eski, sunucu max 30 döner).
final bildirimlerProvider = FutureProvider.autoDispose<List<BildirimOzet>>((ref) async {
  ref.watch(authProvider);
  final data = await ref.watch(apiClientProvider).bildirimler();
  final rows = (data['bildirimler'] as List? ?? []);
  return rows
      .map((e) => BildirimOzet.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Okunmamış bildirim sayısı (çan rozeti turkuaza döner > 0 ise).
final okunmamisBildirimProvider = Provider.autoDispose<int>((ref) {
  final a = ref.watch(bildirimlerProvider);
  return a.maybeWhen(
    data: (rows) => rows.where((b) => !b.okundu).length,
    orElse: () => 0,
  );
});
