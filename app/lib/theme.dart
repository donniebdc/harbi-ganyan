import 'package:flutter/material.dart';

/// Harbi Ganyan premium tema — koyu zemin + altın vurgu.
class HG {
  static const Color zemin = Color(0xFF0E1116);
  static const Color kart = Color(0xFF181D26);
  static const Color kart2 = Color(0xFF222936);
  static const Color altin = Color(0xFFE8B339);
  static const Color altinAcik = Color(0xFFF4D480);
  static const Color yesil = Color(0xFF35C77A);
  static const Color kirmizi = Color(0xFFE5544B);
  static const Color camgobegi = Color(0xFF35D0D6); // misli | TL satırı
  static const Color metin = Color(0xFFF2F4F8);
  static const Color metinSoluk = Color(0xFF98A2B3);

  // 5-satır slot renkleri
  static const Map<String, Color> slotRenk = {
    'FAV': altin,
    'SUR': Color(0xFF4FA3FF),
    'YAZ': Color(0xFF9B8CFF),
    'BOM': kirmizi,
    'HAR': Color(0xFF35C77A),
  };
  static const Map<String, String> slotAd = {
    'FAV': 'Harbi Favorisi',
    'SUR': 'Sürpriz Olmaz',
    'YAZ': 'Yazılabilir',
    'BOM': 'Bomba',
    'HAR': 'Harbi mi?',
  };
  static const Map<String, String> kademeAd = {
    'simitci': 'Simitçi 6\'lısı',
    'harbi': 'Harbi Ganyan 6\'lısı',
    'ortakli': 'Ortak Bonkör 6\'lı',
  };

  static ThemeData tema() {
    final base = ThemeData.dark(useMaterial3: true);
    return base.copyWith(
      scaffoldBackgroundColor: zemin,
      colorScheme: base.colorScheme.copyWith(
        primary: altin,
        secondary: altinAcik,
        surface: kart,
      ),
      cardColor: kart,
      appBarTheme: const AppBarTheme(
        backgroundColor: zemin,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: TextStyle(
            color: metin, fontSize: 18, fontWeight: FontWeight.w700, letterSpacing: 0.3),
      ),
      textTheme: base.textTheme.apply(bodyColor: metin, displayColor: metin),
      dividerColor: kart2,
    );
  }
}
