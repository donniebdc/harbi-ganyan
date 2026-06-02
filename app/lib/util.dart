import 'package:intl/intl.dart';

final _uzun = DateFormat('d MMMM yyyy', 'tr');
final _kisa = DateFormat('d MMM', 'tr');
final _gun = DateFormat('EEE', 'tr');

DateTime _p(String iso) => DateTime.parse(iso);

String tarihUzun(String iso) => _uzun.format(_p(iso));
String tarihKisa(String iso) => _kisa.format(_p(iso));
String gunAdi(String iso) => _gun.format(_p(iso));
