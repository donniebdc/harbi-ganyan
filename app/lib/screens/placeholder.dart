import 'package:flutter/material.dart';
import '../theme.dart';

/// İçi sonra doldurulacak bloklar için tutarlı placeholder.
class BlokPlaceholder extends StatelessWidget {
  final String baslik;
  final IconData ikon;
  final String aciklama;
  final String? rozet;
  const BlokPlaceholder({
    required this.baslik,
    required this.ikon,
    required this.aciklama,
    this.rozet,
    super.key,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(ikon, color: HG.altin, size: 54),
          const SizedBox(height: 16),
          Text(baslik,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
          if (rozet != null) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                  color: HG.altin.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8)),
              child: Text(rozet!,
                  style: const TextStyle(
                      color: HG.altin, fontSize: 11, fontWeight: FontWeight.w800)),
            ),
          ],
          const SizedBox(height: 12),
          Text(aciklama,
              textAlign: TextAlign.center,
              style: const TextStyle(color: HG.metinSoluk, fontSize: 13, height: 1.5)),
        ]),
      ),
    );
  }
}

class HakkindaEkrani extends StatefulWidget {
  const HakkindaEkrani({super.key});
  @override
  State<HakkindaEkrani> createState() => _HakkindaEkraniState();
}

class _HakkindaEkraniState extends State<HakkindaEkrani> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Hakkinda')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Uygulama Hakkinda ──
          _BolumBaslik('Harbi Ganyan'),
          SizedBox(height: 10),
          Text(
            'Harbi Ganyan, at yarislarini veri-kanitli bir algoritmik sistemle analiz eden bagimsiz bir mobil uygulamadir.',
            style: TextStyle(color: HG.metin, height: 1.5, fontSize: 13),
          ),
          SizedBox(height: 6),
          Text(
            "Her kosu icin 5 satirlik tahmin (Harbi Favorisi, Surpriz Olmaz, Plase, Bomba, Harbi mi?) ve bu tahminlerden turetilen 6'li ganyan kuponlari uretilir.",
            style: TextStyle(color: HG.metin, height: 1.5, fontSize: 13),
          ),
          SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: HG.kart,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: HG.altin.withValues(alpha: 0.3)),
            ),
            child: Text(
              'Bu uygulama yalnizca analiz ve bilgilendirme amaclidir; bahis tavsiyesi vermez, kazanc garantisi sunmaz.',
              style: TextStyle(color: HG.altinAcik, height: 1.5, fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
          Divider(color: HG.kart2, height: 28),

          // ── Hukuki Metinler ──
          _GenisletilebilirBolum('Kullanim Sartlari', _kullanimSartlari),
          _GenisletilebilirBolum('Gizlilik Politikasi', _gizlilikPolitikasi),
          _GenisletilebilirBolum('KVKK Aydinlatma Metni', _kvkkMetni),
          _GenisletilebilirBolum('Sorumlu Oyun', _sorumluOyun),
          SizedBox(height: 24),
          Text('© 2026 Harbi Ganyan. Tum haklari saklidir.',
              textAlign: TextAlign.center,
              style: TextStyle(color: HG.metinSoluk, fontSize: 11)),
          SizedBox(height: 16),
        ],
      ),
    );
  }
}

class _BolumBaslik extends StatelessWidget {
  final String baslik;
  const _BolumBaslik(this.baslik);
  @override
  Widget build(BuildContext context) {
    return Text(baslik,
        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: HG.altin));
  }
}

class _GenisletilebilirBolum extends StatefulWidget {
  final String baslik;
  final String icerik;
  const _GenisletilebilirBolum(this.baslik, this.icerik);
  @override
  State<_GenisletilebilirBolum> createState() => _GenisletilebilirBolumState();
}

class _GenisletilebilirBolumState extends State<_GenisletilebilirBolum> {
  bool _acik = false;
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      decoration: BoxDecoration(
        color: HG.kart,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        children: [
          InkWell(
            borderRadius: BorderRadius.circular(10),
            onTap: () => setState(() => _acik = !_acik),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
              child: Row(
                children: [
                  Expanded(
                    child: Text(widget.baslik,
                        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                  ),
                  Icon(_acik ? Icons.expand_less : Icons.expand_more,
                      color: HG.metinSoluk, size: 22),
                ],
              ),
            ),
          ),
          if (_acik)
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 14),
              child: Text(widget.icerik,
                  style: const TextStyle(color: HG.metinSoluk, fontSize: 12, height: 1.6)),
            ),
        ],
      ),
    );
  }
}

// ── Hukuki Metin Icerikleri ──

const _kullanimSartlari = '''
1. TARAFLAR
Bu Kullanim Sartlari, Harbi Ganyan mobil uygulamasini gelistiren ve isleten uygulama saglayici ile uygulamayi kullanan gercek kisi (Kullanici) arasinda akdedilmistir.

2. HIZMET TANIMI
Harbi Ganyan, TJK tarafindan yayimlanan at yarisi verilerine dayali olarak istatistiksel analiz, yapay zeka destekli tahmin ve bilgilendirme hizmeti sunan bagimsiz bir mobil uygulamadir.
- Bir bahis sitesi veya bahis aracisi DEGILDIR.
- Yatirim veya kazanc tavsiyesi VERMEZ.
- TJK ile resmi bir bagi BULUNMAMAKTADIR.

3. YAS SINIRI
Uygulama yalnizca 18 yas ve uzeri bireylerin kullanimina aciktir. 18 yasindan kucuklerin kullanimi yasaktir.

4. FIKRI MULKIYET
Uygulamanin tamami uzerindeki tum fikri ve sinai mulkiyet haklari Saglayici\'ya aittir. 5846 sayili FSEK ve 6769 sayili SMK tarafindan korunmaktadir.

5. SORUMLULUK REDDI
Tum analiz ve tahminler yalnizca bilgilendirme amaclidir. Hicbir surette bahis, yatirim veya finansal tavsiye niteligi tasimaz; kazanc garantisi vermez.

6. UYGULANACAK HUKUK
Bu Sartlar Turkiye Cumhuriyeti kanunlarina tabidir. Uyusmazliklarda Turkiye Cumhuriyeti Mahkemeleri yetkilidir.
''';

const _gizlilikPolitikasi = '''
1. TOPLANAN VERILER
- Hesap bilgileri: Ad, soyad, e-posta
- Google hesap bilgileri: Google ile giris yapmaniz halinde yalnizca ad, soyad ve e-posta
- Cihaz bilgileri: Cihaz modeli, isletim sistemi, uygulama surumu
- Kullanim verileri: Uygulama ici etkilesimler (anonim)

2. TOPLAMADIGIMIZ VERILER
- Hassas GPS konumunuzu toplamayiz
- Kredi karti veya odeme bilgileriniz dogrudan tarafimizdan toplanmaz (Google Play uzerinden islenir)
- Google sifrenize veya diger Google hizmetlerinize (Drive, Kisiler vb.) asla erismeyiz

3. UCUNCU TARAF HIZMET SAGLAYICILAR
- Firebase (Auth, Firestore, Cloud Messaging, Analytics) - Google LLC
- Supabase - Supabase Inc.
- Google Play Services - Google LLC
Bu hizmet saglayicilar yalnizca hizmetin ifasi icin gerekli verilere erisir.

4. VERI PAYLASIMI
Kisisel verileriniz satilmaz, kiralanmaz veya ticari amacla paylasilmaz. Yalnizca yasal zorunluluk halinde yetkili mercilerle paylasilabilir.

5. VERI GUVENLIGI
Veri iletimi SSL/TLS sifreleme ile korunur. Sifreler kriptografik yontemlerle hash\'lenerek saklanir.

6. SAKLAMA SURESI
Hesap bilgileri hesabiniz aktif oldugu surece saklanir. Hesap kapatildiktan sonra verileriniz 30 gun icinde silinir.
''';

const _kvkkMetni = '''
6698 sayili Kisisel Verilerin Korunmasi Kanunu (KVKK) Kapsaminda Aydinlatma Metni

1. VERI SORUMLUSU
Harbi Ganyan mobil uygulamasi, KVKK kapsaminda veri sorumlusu sifatiyla hareket etmektedir.

2. ISLENEN KISISEL VERILER
Kimlik (ad, soyad), iletisim (e-posta), musteri islem (abonelik turu), islem guvenligi (IP, cihaz kimligi), pazarlama (bildirim tercihleri).

3. ISLENME AMACLARI
Hesap olusturma ve yonetimi, hizmet sunumu, abonelik yonetimi, push bildirim gonderimi, hizmet gelistirme, anonim istatistik, yasal yukumlulukler.

4. HUKUKI SEBEPLER (KVKK Md. 5)
- Sozlesmenin kurulmasi ve ifasi (Md. 5/2-c)
- Hukuki yukumlulugun yerine getirilmesi (Md. 5/2-c)
- Mesru menfaat (Md. 5/2-f)
- Acik riza (Md. 5/1) – bildirimler ve pazarlama iletisimi icin

5. YURTDISI AKTARIM (KVKK Md. 9)
Verileriniz Firebase (Google LLC, ABD) ve Supabase (Supabase Inc., ABD) altyapilarina aktarilabilmektedir. Her iki sirket de AB-ABD Veri Gizliligi Cercevesi kapsaminda sertifikalidir.

6. KVKK MD. 11 KAPSAMINDAKI HAKLARINIZ
- Verilerinizin islenip islenmedigini ogrenme
- Islenmisse bilgi talep etme
- Islenme amacini ogrenme
- Aktarilan ucuncu kisileri bilme
- Eksik/yanlis verilerin duzeltilmesini isteme
- Verilerin silinmesini veya yok edilmesini isteme
- Otomatik analiz sonucu aleyhe cikan sonuclara itiraz etme
- Kanuna aykiri isleme nedeniyle zararin giderilmesini talep etme

7. BASVURU
Talepleriniz icin: destek@harbiganyan.com
Basvurunuz en gec 30 gun icinde ucretsiz olarak sonuclandirilir.
''';

const _sorumluOyun = '''
HARBI GANYAN BIR BAHIS UYGULAMASI DEGILDIR
Harbi Ganyan, at yarisi verilerine dayali istatistiksel analiz ve bilgilendirme platformudur. Bahis oynatmaz, bahis araciligi yapmaz ve kullanicilari bahse tesvik etmez. Tum analiz ve tahmin icerikleri yalnizca bilgilendirme ve eglence amaclidir.

18 YAS SINIRI
Bu Uygulama yalnizca 18 yas ve uzeri bireyler tarafindan kullanilabilir. Turkiye\'de sans oyunlari 18 yasindan kucuklere yasaktir.

YARDIM KAYNAKLARI
Eger kendinizde veya bir yakininizda kumar bagimliligi belirtileri gozlemliyorsaniz, asagidaki kuruluslardan ucretsiz ve gizli destek alabilirsiniz:

- Yesilay Bagimlilik Danisma Hatti: 115
- RTUK Alo 178 Sikayet ve Bilgi Hatti: 178
- Yesilay Danismanlik Merkezi (YEDAM): yedam.org.tr

HESAP KAPATMA
Uygulama kullaniminizi sonlandirmak isterseniz, uygulama icindeki hesap ayarlarindan hesabinizi dilediginiz zaman silebilirsiniz.
''';
