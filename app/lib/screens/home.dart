import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../state/auth.dart';
import '../state/nav.dart';
import '../theme.dart';
import 'auth_sheet.dart';
import 'gunun_analizleri.dart';
import 'gun_icerik.dart';
import 'gecmis_analizler.dart';
import 'uyelik.dart';
import 'placeholder.dart';

class HomeEkrani extends ConsumerWidget {
  const HomeEkrani({super.key});

  static const _ekranlar = [
    GununAnalizleri(mod: GunIcerikModu.besli),
    GununAnalizleri(mod: GunIcerikModu.altili),
    GecmisAnalizler(),
    BlokPlaceholder(
        baslik: 'Istatistik',
        ikon: Icons.bar_chart,
        aciklama:
            'Tutturma oranlari ve net kar-zarar simulasyonu yakinda.\n5 satir, Simitci, Harbi ve Ortak Bonkor basari yuzdeleri burada olacak.'),
    BlokPlaceholder(
        baslik: 'Kosu Analizleri',
        ikon: Icons.insights,
        rozet: 'VIP',
        aciklama:
            'Ikili, sirali ikili, 3lu, 4lu ve 5li ganyan analizleri yakinda eklenecek.'),
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
        if (v == 'bildirimler') _bildirimleriGoster(context, ref);
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

  Future<void> _bildirimleriGoster(BuildContext context, WidgetRef ref) async {
    final api = ref.read(apiClientProvider);
    try {
      final data = await api.bildirimler();
      final rows = data['bildirimler'] as List? ?? [];
      if (!context.mounted) return;
      showDialog<void>(
        context: context,
        builder: (_) => AlertDialog(
          backgroundColor: HG.kart,
          title: const Text('Bildirimler'),
          content: SizedBox(
            width: 420,
            child: rows.isEmpty
                ? const Text('Henuz bildiriminiz yok.')
                : ListView.separated(
                    shrinkWrap: true,
                    itemBuilder: (_, i) {
                      final b = rows[i] as Map<String, dynamic>;
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(b['baslik'] as String? ?? ''),
                        subtitle: Text(b['mesaj'] as String? ?? ''),
                      );
                    },
                    separatorBuilder: (_, _) => const Divider(color: HG.kart2),
                    itemCount: rows.length,
                  ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Kapat'),
            ),
          ],
        ),
      );
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Bildirimler alinamadi.'),
      ));
    }
  }
}
