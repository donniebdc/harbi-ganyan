import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../theme.dart';

const _kabulKey = 'sozlesme_kabul';

/// Daha once sozlesme kabul edildi mi?
Future<bool> sozlesmeKabulEdildi() async {
  const storage = FlutterSecureStorage();
  final v = await storage.read(key: _kabulKey);
  return v == '1';
}

/// Ilk acilista sozlesme onay ekrani. Bir kere kabul edilince tekrar gosterilmez.
class IlkAcilisSozlesme extends StatefulWidget {
  final Widget child;
  const IlkAcilisSozlesme({required this.child, super.key});

  @override
  State<IlkAcilisSozlesme> createState() => _IlkAcilisSozlesmeState();
}

class _IlkAcilisSozlesmeState extends State<IlkAcilisSozlesme> {
  bool? _kabulEdildi;

  @override
  void initState() {
    super.initState();
    sozlesmeKabulEdildi().then((v) {
      if (mounted) setState(() => _kabulEdildi = v);
    });
  }

  Future<void> _kabulEt() async {
    const storage = FlutterSecureStorage();
    await storage.write(key: _kabulKey, value: '1');
    if (mounted) setState(() => _kabulEdildi = true);
  }

  @override
  Widget build(BuildContext context) {
    if (_kabulEdildi == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator(color: HG.altin)));
    }
    if (_kabulEdildi == true) return widget.child;

    return Scaffold(
      backgroundColor: HG.zemin,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            children: [
              const SizedBox(height: 40),
              const Icon(Icons.analytics, color: HG.altin, size: 56),
              const SizedBox(height: 16),
              const Text('HARBI GANYAN',
                  style: TextStyle(fontSize: 26, fontWeight: FontWeight.w900, color: HG.altin, letterSpacing: 2)),
              const SizedBox(height: 8),
              const Text('At Yarisi Analiz ve Tahmin Platformu',
                  style: TextStyle(color: HG.metinSoluk, fontSize: 13)),
              const SizedBox(height: 32),
              Expanded(
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: HG.kart,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: ListView(
                    children: const [
                      _Madde('1.', 'Harbi Ganyan bir bahis uygulamasi degildir. Bahis oynatmaz ve kullanicilari bahse tesvik etmez.'),
                      _Madde('2.', 'Tum analiz ve tahminler yalnizca bilgilendirme amaclidir. Kazanc garantisi verilmez.'),
                      _Madde('3.', 'Bu uygulama yalnizca 18 yas ve uzeri bireyler tarafindan kullanilabilir.'),
                      _Madde('4.', 'Uygulamayi kullanarak Kullanim Sartlari, Gizlilik Politikasi ve KVKK Aydinlatma Metni\'ni kabul etmis olursunuz.'),
                      _Madde('5.', 'Analizlere dayanarak alacaginiz tum kararlarin sorumlulugu size aittir.'),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text('Devam ederek yukaridaki kosullari kabul etmis sayilirsiniz.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: HG.metinSoluk, fontSize: 11)),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: HG.altin,
                    foregroundColor: Colors.black,
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  onPressed: _kabulEt,
                  child: const Text('Kabul Ediyorum ve Devam Ediyorum',
                      style: TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                ),
              ),
              const SizedBox(height: 16),
              TextButton(
                onPressed: () => Navigator.of(context).maybePop(),
                child: const Text('Kabul Etmiyorum', style: TextStyle(color: HG.metinSoluk)),
              ),
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }
}

class _Madde extends StatelessWidget {
  final String no, metin;
  const _Madde(this.no, this.metin);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(no, style: const TextStyle(color: HG.altin, fontWeight: FontWeight.w800, fontSize: 14)),
          const SizedBox(width: 8),
          Expanded(child: Text(metin, style: const TextStyle(color: HG.metin, fontSize: 13, height: 1.5))),
        ],
      ),
    );
  }
}
