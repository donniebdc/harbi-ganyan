import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'fcm_setup.dart';
import 'nav_key.dart';
import 'theme.dart';
import 'screens/home.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting('tr');
  await fcmBaslat();
  runApp(const ProviderScope(child: HarbiGanyanApp()));
}

class HarbiGanyanApp extends StatelessWidget {
  const HarbiGanyanApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Harbi Ganyan',
      debugShowCheckedModeBanner: false,
      navigatorKey: navigatorKey,
      theme: HG.tema(),
      home: const HomeEkrani(),
    );
  }
}
