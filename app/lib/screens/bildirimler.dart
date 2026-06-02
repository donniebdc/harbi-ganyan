import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/models.dart';
import '../state/content.dart';
import '../theme.dart';
import '../util.dart';
import '../widgets/durumlar.dart';

/// Bildirimler sayfası (Güncelleme v3): gelen tüm bildirimler en yeniden en
/// eskiye, her birinde zaman bilgisi. Sunucu en fazla 30 kayıt döner.
/// Push'a tıklanınca (deep-link) buraya gelinir.
class BildirimlerEkrani extends ConsumerWidget {
  const BildirimlerEkrani({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(bildirimlerProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Bildirimler',
            style: TextStyle(color: HG.altin, letterSpacing: 1.0)),
      ),
      body: async.when(
        loading: () => const Yukleniyor(),
        error: (e, _) =>
            HataKutu(onTekrar: () => ref.invalidate(bildirimlerProvider)),
        data: (rows) {
          if (rows.isEmpty) {
            return const BosKutu('Henüz bildiriminiz yok.',
                ikon: Icons.notifications_none);
          }
          return RefreshIndicator(
            color: HG.altin,
            onRefresh: () async => ref.invalidate(bildirimlerProvider),
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
              itemCount: rows.length,
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (_, i) => _BildirimKart(rows[i]),
            ),
          );
        },
      ),
    );
  }
}

class _BildirimKart extends StatelessWidget {
  final BildirimOzet b;
  const _BildirimKart(this.b);

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: HG.kart,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: HG.kart2),
      ),
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.notifications_active,
                  color: HG.altin, size: 16),
              const SizedBox(width: 8),
              Expanded(
                child: Text(b.baslik,
                    style: const TextStyle(
                        fontWeight: FontWeight.w800, fontSize: 14)),
              ),
              const SizedBox(width: 8),
              Text(bildirimZaman(b.createdAt),
                  style: const TextStyle(
                      color: HG.metinSoluk, fontSize: 11)),
            ],
          ),
          const SizedBox(height: 6),
          Text(b.mesaj,
              style: const TextStyle(color: HG.metin, fontSize: 13, height: 1.35)),
        ],
      ),
    );
  }
}
