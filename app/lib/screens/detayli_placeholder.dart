import 'package:flutter/material.dart';
import '../theme.dart';

class DetayliPlaceholder extends StatelessWidget {
  const DetayliPlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.rocket_launch_outlined, color: HG.altin, size: 64),
            const SizedBox(height: 20),
            const Text(
              'Koşu bazlı Tahminler\nÇok Yakında...',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: HG.altin,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Her kosu icin detayli analiz ve tahminler\nuzerinde calisiyoruz.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: HG.metinSoluk,
                fontSize: 13,
                height: 1.5,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
