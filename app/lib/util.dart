import 'package:intl/intl.dart';

final _uzun = DateFormat('d MMMM yyyy', 'tr');
final _kisa = DateFormat('d MMM', 'tr');
final _gun = DateFormat('EEE', 'tr');

DateTime _p(String iso) => DateTime.parse(iso);

String tarihUzun(String iso) => _uzun.format(_p(iso));
String tarihKisa(String iso) => _kisa.format(_p(iso));
String gunAdi(String iso) => _gun.format(_p(iso));

final _saat = DateFormat('HH:mm', 'tr');

/// Bildirim zaman bilgisi: "14:32 · bugün" / "dün 09:10" / "28 May 14:32".
/// Sunucu created_at'i yerel saat (Europe/Istanbul) kabul edilir.
String bildirimZaman(DateTime? t) {
  if (t == null) return '';
  final now = DateTime.now();
  final bugun = DateTime(now.year, now.month, now.day);
  final gunu = DateTime(t.year, t.month, t.day);
  final farkGun = bugun.difference(gunu).inDays;
  final saat = _saat.format(t);
  if (farkGun == 0) return '$saat · bugün';
  if (farkGun == 1) return 'dün $saat';
  return '${_kisa.format(t)} $saat';
}
