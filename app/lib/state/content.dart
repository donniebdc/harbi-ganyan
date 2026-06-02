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
