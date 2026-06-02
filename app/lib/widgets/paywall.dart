import 'package:flutter/material.dart';
import '../theme.dart';

/// Premium kilidi ekranı (Günün Analizleri standart kademeye kapalı).
class PaywallKart extends StatelessWidget {
  final bool girisli;
  final VoidCallback onAksiyon;
  const PaywallKart({required this.girisli, required this.onAksiyon, super.key});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
                color: HG.altin.withValues(alpha: 0.12), shape: BoxShape.circle),
            child: const Icon(Icons.workspace_premium, color: HG.altin, size: 48),
          ),
          const SizedBox(height: 18),
          const Text('Günün Analizleri Premium\'a Özel',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 10),
          const Text(
              'Yaklaşan günün 5 satır tahminleri ve 6\'lı ganyan kuponları '
              'Premium ve VIP üyelere açıktır. Geçmiş analizleri ve istatistikleri '
              'ücretsiz inceleyebilirsiniz.',
              textAlign: TextAlign.center,
              style: TextStyle(color: HG.metinSoluk, fontSize: 13, height: 1.4)),
          const SizedBox(height: 22),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              style: FilledButton.styleFrom(
                  backgroundColor: HG.altin,
                  foregroundColor: Colors.black,
                  padding: const EdgeInsets.symmetric(vertical: 14)),
              onPressed: onAksiyon,
              child: Text(girisli ? 'Premium\'a Yükselt' : 'Giriş Yap / Üye Ol',
                  style: const TextStyle(fontWeight: FontWeight.w800)),
            ),
          ),
        ]),
      ),
    );
  }
}
