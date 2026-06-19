import 'package:flutter/material.dart';
import '../theme.dart';

/// VIP kilidi ekrani (Gunun Analizleri standart kademeye kapali).
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
          const Text("Gunun Analizleri VIP'e Ozel",
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          const SizedBox(height: 10),
          const Text(
              "Yaklasan gunun 5 satir tahminleri ve 6'li ganyan kuponlari "
              'VIP uyelere aciktir. Gecmis analizleri ve istatistikleri '
              'ucretsiz inceleyebilirsiniz.',
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
              child: Text(girisli ? "VIP'e Yukselt" : 'Giris Yap / Uye Ol',
                  style: const TextStyle(fontWeight: FontWeight.w800)),
            ),
          ),
        ]),
      ),
    );
  }
}
