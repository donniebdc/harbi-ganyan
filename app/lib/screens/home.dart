import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../state/auth.dart';
import '../state/content.dart';
import '../state/nav.dart';
import '../theme.dart';
import 'auth_sheet.dart';
import 'bildirimler.dart';
import 'gunun_analizleri.dart';
import 'gun_icerik.dart';
import 'gecmis_analizler.dart';
import 'istatistik.dart';
import 'kosu_analizleri.dart';
import 'uyelik.dart';
import 'placeholder.dart';

/// Bildirimler sayfasını açar (çan ikonu + push deep-link ortak girişi).
void bildirimlerSayfasiniAc(BuildContext context) {
  Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const BildirimlerEkrani()));
}

class HomeEkrani extends ConsumerWidget {
  const HomeEkrani({super.key});

  static const _ekranlar = [
    GununAnalizleri(mod: GunIcerikModu.besli),
    GununAnalizleri(mod: GunIcerikModu.altili),
    GecmisAnalizler(),
    IstatistikEkrani(),
    KosuAnalizleri(),
    UyelikEkrani(),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final index = ref.watch(navIndexProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('HARBI GANYAN',
            style: TextStyle(color: HG.altin, letterSpacing: 1.5)),
        actions: [
          const _BildirimCan(),
          IconButton(
            icon: const Icon(Icons.info_outline),
            tooltip: 'Hakkinda',
            onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const HakkindaEkrani())),
          ),
          const _ProfilButon(),
          const SizedBox(width: 4),
        ],
      ),
      body: IndexedStack(index: index, children: _ekranlar),
      bottomNavigationBar: NavigationBar(
        height: 76,
        backgroundColor: HG.kart,
        indicatorColor: HG.altin.withValues(alpha: 0.2),
        selectedIndex: index,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        onDestinationSelected: (i) => ref.read(navIndexProvider.notifier).sec(i),
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.format_list_numbered),
              selectedIcon: Icon(Icons.format_list_numbered, color: HG.altin),
              label: '5 Satir'),
          NavigationDestination(
              icon: Icon(Icons.casino_outlined),
              selectedIcon: Icon(Icons.casino, color: HG.altin),
              label: '6li'),
          NavigationDestination(
              icon: Icon(Icons.history_outlined),
              selectedIcon: Icon(Icons.history, color: HG.altin),
              label: 'Gecmis'),
          NavigationDestination(
              icon: Icon(Icons.bar_chart_outlined),
              selectedIcon: Icon(Icons.bar_chart, color: HG.altin),
              label: 'Istatistik'),
          NavigationDestination(
              icon: Icon(Icons.insights_outlined),
              selectedIcon: Icon(Icons.insights, color: HG.altin),
              label: 'Kosu'),
          NavigationDestination(
              icon: Icon(Icons.account_circle_outlined),
              selectedIcon: Icon(Icons.account_circle, color: HG.altin),
              label: 'Profil'),
        ],
      ),
    );
  }
}

/// AppBar çan ikonu — yalnızca giriş yapan kullanıcıda görünür.
class _BildirimCan extends ConsumerWidget {
  const _BildirimCan();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    if (!auth.girisli) return const SizedBox.shrink();
    final okunmamis = ref.watch(okunmamisBildirimProvider) > 0;
    // Okunmamış varsa turkuaz + dolu çan; sayfaya girince (okundu) beyaza döner.
    return IconButton(
      icon: Icon(okunmamis ? Icons.notifications_active : Icons.notifications_none,
          color: okunmamis ? HG.camgobegi : HG.metin),
      tooltip: 'Bildirimler',
      onPressed: () => bildirimlerSayfasiniAc(context),
    );
  }
}

class _ProfilButon extends ConsumerWidget {
  const _ProfilButon();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authProvider);
    if (!auth.girisli) {
      return TextButton.icon(
        onPressed: () => authSheetGoster(context),
        icon: const Icon(Icons.login, size: 18, color: HG.altin),
        label: const Text('Giris', style: TextStyle(color: HG.altin)),
      );
    }
    return PopupMenuButton<String>(
      icon: const Icon(Icons.account_circle, color: HG.altin),
      color: HG.kart2,
      onSelected: (v) {
        if (v == 'bildirimler') bildirimlerSayfasiniAc(context);
        if (v == 'profil') ref.read(navIndexProvider.notifier).sec(profilSekme);
        if (v == 'cikis') ref.read(authProvider.notifier).cikis();
      },
      itemBuilder: (_) => [
        PopupMenuItem(
          enabled: false,
          child: Text('${auth.email ?? ''}\nKademe: ${auth.tier.toUpperCase()}',
              style: const TextStyle(color: HG.metin, fontSize: 12)),
        ),
        const PopupMenuDivider(),
        const PopupMenuItem(value: 'profil', child: Text('Profil')),
        const PopupMenuItem(value: 'bildirimler', child: Text('Bildirimler')),
        const PopupMenuItem(value: 'cikis', child: Text('Cikis Yap')),
      ],
    );
  }
}
