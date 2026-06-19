import 'package:flutter/material.dart';
import '../theme.dart';

class Yukleniyor extends StatelessWidget {
  const Yukleniyor({super.key});
  @override
  Widget build(BuildContext context) =>
      const Center(child: CircularProgressIndicator(color: HG.altin));
}

class BosKutu extends StatelessWidget {
  final String mesaj;
  final IconData ikon;
  const BosKutu(this.mesaj, {this.ikon = Icons.inbox_outlined, super.key});
  @override
  Widget build(BuildContext context) => Center(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(ikon, color: HG.metinSoluk, size: 44),
          const SizedBox(height: 10),
          Text(mesaj, style: const TextStyle(color: HG.metinSoluk)),
        ]),
      );
}

class HataKutu extends StatelessWidget {
  final VoidCallback onTekrar;
  final String? mesaj;
  final Object? hata;
  const HataKutu({required this.onTekrar, this.mesaj, this.hata, super.key});
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.wifi_off, color: HG.metinSoluk, size: 44),
            const SizedBox(height: 10),
            Text(mesaj ?? 'Bağlantı hatası',
                textAlign: TextAlign.center,
                style: const TextStyle(color: HG.metinSoluk)),
            if (hata != null) ...[
              const SizedBox(height: 6),
              Text('${hata.runtimeType}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: HG.metinSoluk, fontSize: 10)),
            ],
            const SizedBox(height: 12),
            OutlinedButton(onPressed: onTekrar, child: const Text('Tekrar dene')),
          ]),
        ),
      );
}
