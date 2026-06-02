import 'package:flutter/material.dart';
import '../api/models.dart';
import '../theme.dart';
import '../widgets/kosu_karti.dart';
import '../widgets/altili_karti.dart';

enum GunIcerikModu { tumu, besli, altili }

class GunIcerik extends StatelessWidget {
  final GunDetay gun;
  final GunIcerikModu mod;
  const GunIcerik(this.gun, {this.mod = GunIcerikModu.tumu, super.key});

  @override
  Widget build(BuildContext context) {
    if (gun.hipodromlar.isEmpty) {
      return const _Bos(mesaj: 'Bu gune ait analiz yok.');
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
      children: [
        for (final h in gun.hipodromlar) _HipodromBolum(h, mod),
      ],
    );
  }
}

class _HipodromBolum extends StatelessWidget {
  final Hipodrom h;
  final GunIcerikModu mod;
  const _HipodromBolum(this.h, this.mod);

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        decoration: BoxDecoration(
          color: HG.kart,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: HG.kart2),
        ),
        child: ExpansionTile(
          initiallyExpanded: true,
          shape: const Border(),
          collapsedShape: const Border(),
          tilePadding: const EdgeInsets.symmetric(horizontal: 14),
          leading: const Icon(Icons.stadium, color: HG.altin),
          title: Text(h.hipodrom,
              style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
          subtitle: Text('${h.kosular.length} kosu · ${h.altililar.length} altili',
              style: const TextStyle(color: HG.metinSoluk, fontSize: 12)),
          childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          children: [
            if (mod != GunIcerikModu.besli && h.altililar.isNotEmpty) ...[
              const _AltBaslik('6\'LI GANYAN KUPONLARI'),
              ...h.altililar.map((a) => AltiliKarti(
                    a,
                    winnerByKno: {
                      for (final k in h.kosular) k.kno: k.sonuc?.kazanan,
                    },
                    ganyanByKno: {
                      for (final k in h.kosular) k.kno: k.sonuc?.ganyan,
                    },
                  )),
            ],
            if (mod != GunIcerikModu.altili) ...[
              const _AltBaslik('5 SATIR TAHMINLER'),
              ...h.kosular.map((k) => KosuKarti(k)),
            ],
          ],
        ),
      ),
    );
  }
}

class _AltBaslik extends StatelessWidget {
  final String metin;
  const _AltBaslik(this.metin);
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(2, 10, 0, 8),
        child: Text(metin,
            style: const TextStyle(
                color: HG.altin,
                fontSize: 11,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.1)),
      );
}

class _Bos extends StatelessWidget {
  final String mesaj;
  const _Bos({required this.mesaj});
  @override
  Widget build(BuildContext context) => Center(
        child: Text(mesaj, style: const TextStyle(color: HG.metinSoluk)),
      );
}
