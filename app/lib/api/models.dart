// API JSON modelleri (backend serialize.py ile aynı şema).

double? _d(dynamic v) => v == null ? null : (v as num).toDouble();

class GunOzet {
  final String date;
  final List<HipOzet> hipodromlar;
  final bool sonuclandi;
  final bool gununAnalizi;
  final bool aktif;
  final bool kilit;
  final bool yakinda; // yarın ama henüz 18:00 olmadı (içerik kilitli, şeritte görünür)
  final int yayinSaati;

  GunOzet.fromJson(Map<String, dynamic> j)
      : date = j['date'] as String,
        hipodromlar = (j['hipodromlar'] as List)
            .map((e) => HipOzet.fromJson(e as Map<String, dynamic>))
            .toList(),
        sonuclandi = j['sonuclandi'] as bool? ?? false,
        gununAnalizi = j['gunun_analizi'] as bool? ?? false,
        aktif = j['aktif'] as bool? ?? (j['gunun_analizi'] as bool? ?? false),
        kilit = j['kilit'] as bool? ?? false,
        yakinda = j['yakinda'] as bool? ?? false,
        yayinSaati = j['yayin_saati'] as int? ?? 18;
}

class HipOzet {
  final String hipodrom;
  final int nKosu, nAltili, nAltiliSonuc;
  HipOzet.fromJson(Map<String, dynamic> j)
      : hipodrom = j['hipodrom'] as String,
        nKosu = j['n_kosu'] as int,
        nAltili = j['n_altili'] as int,
        nAltiliSonuc = j['n_altili_sonuc'] as int;
}

class GunDetay {
  final String date;
  final DateTime? sonAnaliz; // en son (yeniden) üretim zamanı (TR)
  final String? sonAnalizSebep;
  final List<Hipodrom> hipodromlar;
  GunDetay.fromJson(Map<String, dynamic> j)
      : date = j['date'] as String,
        sonAnaliz = (j['son_analiz'] as String?) != null
            ? DateTime.tryParse(j['son_analiz'] as String)
            : null,
        sonAnalizSebep = j['son_analiz_sebep'] as String?,
        hipodromlar = (j['hipodromlar'] as List)
            .map((e) => Hipodrom.fromJson(e as Map<String, dynamic>))
            .toList();
}

class Hipodrom {
  final String hipodrom;
  final double birim;
  final List<Kosu> kosular;
  final List<Altili> altililar;
  Hipodrom.fromJson(Map<String, dynamic> j)
      : hipodrom = j['hipodrom'] as String,
        birim = (j['birim'] as num).toDouble(),
        kosular = (j['kosular'] as List)
            .map((e) => Kosu.fromJson(e as Map<String, dynamic>))
            .toList(),
        altililar = (j['altililar'] as List)
            .map((e) => Altili.fromJson(e as Map<String, dynamic>))
            .toList();
}

class Kosu {
  final int kno;
  final String pist, mesafe, saat, raceType, raceSubtype;
  final int? nAt;
  final List<Bes> bes;
  final KosuSonuc? sonuc;
  Kosu.fromJson(Map<String, dynamic> j)
      : kno = j['kno'] as int,
        pist = j['pist'] as String? ?? '',
        mesafe = (j['mesafe'] ?? '').toString(),
        saat = j['saat'] as String? ?? '',
        raceType = j['race_type'] as String? ?? '',
        raceSubtype = j['race_subtype'] as String? ?? '',
        nAt = j['n_at'] as int?,
        bes = (j['bes'] as List)
            .map((e) => Bes.fromJson(e as Map<String, dynamic>))
            .toList(),
        sonuc = j['sonuc'] == null
            ? null
            : KosuSonuc.fromJson(j['sonuc'] as Map<String, dynamic>);
}

class Bes {
  final String slot, at;
  final int atNo;
  final double ana;
  Bes.fromJson(Map<String, dynamic> j)
      : slot = j['slot'] as String,
        atNo = j['at_no'] as int,
        at = j['at'] as String? ?? '',
        ana = (j['ana'] as num).toDouble();
}

class KosuSonuc {
  final int? kazanan;
  final String kazananAd;
  final double? ganyan;
  final bool? besHit;
  KosuSonuc.fromJson(Map<String, dynamic> j)
      : kazanan = j['kazanan'] as int?,
        kazananAd = j['kazanan_ad'] as String? ?? '',
        ganyan = _d(j['ganyan']),
        besHit = j['bes_hit'] as bool?;
}

class Altili {
  final int idx;
  final List<int> legs;
  final List<Kademe> kademeler;
  final AltiliSonuc? sonuc;
  Altili.fromJson(Map<String, dynamic> j)
      : idx = j['idx'] as int,
        legs = (j['legs'] as List).map((e) => e as int).toList(),
        kademeler = (j['kademeler'] as List)
            .map((e) => Kademe.fromJson(e as Map<String, dynamic>))
            .toList(),
        sonuc = j['sonuc'] == null
            ? null
            : AltiliSonuc.fromJson(j['sonuc'] as Map<String, dynamic>);
}

class Kademe {
  final String ad, key;
  final double bedel;
  final int komb;
  final List<Ayak> ayaklar;
  Kademe.fromJson(Map<String, dynamic> j)
      : ad = j['ad'] as String,
        key = j['key'] as String,
        bedel = (j['bedel'] as num).toDouble(),
        komb = j['komb'] as int,
        ayaklar = (j['ayaklar'] as List)
            .map((e) => Ayak.fromJson(e as Map<String, dynamic>))
            .toList();
}

class Ayak {
  final int kno, width;
  final bool bankoLider;
  final List<int> secilen;
  final List<SecilenAt> secilenAtlar;
  Ayak.fromJson(Map<String, dynamic> j)
      : kno = j['kno'] as int,
        width = j['width'] as int,
        bankoLider = j['banko_lider'] as bool? ?? false,
        secilen = (j['secilen'] as List).map((e) => e as int).toList(),
        secilenAtlar = (j['secilen_atlar'] as List? ?? [])
            .map((e) => SecilenAt.fromJson(e as Map<String, dynamic>))
            .toList();
}

class SecilenAt {
  final int atNo;
  final String at;
  SecilenAt.fromJson(Map<String, dynamic> j)
      : atNo = j['at_no'] as int,
        at = j['at'] as String? ?? '';
}

class AltiliSonuc {
  final List<int?> winners;
  final double? ikramiye;
  final Map<String, int?> tierHits;
  AltiliSonuc.fromJson(Map<String, dynamic> j)
      : winners = (j['winners'] as List).map((e) => e as int?).toList(),
        ikramiye = _d(j['ikramiye']),
        tierHits = (j['tier_hits'] as Map).map(
            (k, v) => MapEntry(k as String, v as int?));
}

// ---- İstatistik ----

class TierIstat {
  final String ad;
  final int toplam, tuttu;
  final double yuzde, maliyet, ikramiye, net;
  TierIstat.fromJson(Map<String, dynamic> j)
      : ad = j['ad'] as String,
        toplam = j['toplam'] as int,
        tuttu = j['tuttu'] as int,
        yuzde = (j['yuzde'] as num).toDouble(),
        maliyet = (j['maliyet'] as num).toDouble(),
        ikramiye = (j['ikramiye'] as num).toDouble(),
        net = (j['net'] as num).toDouble();
}

class IstatistikDonem {
  final int besToplam, besIsabet;
  final double besYuzde;
  final List<TierIstat> tierler;
  IstatistikDonem.fromJson(Map<String, dynamic> j)
      : besToplam = j['bes']['toplam'] as int,
        besIsabet = j['bes']['isabet'] as int,
        besYuzde = (j['bes']['yuzde'] as num).toDouble(),
        tierler = [
          for (final k in const ['simitci', 'harbi', 'ortakli'])
            TierIstat.fromJson(
                (j['tierler'] as Map)[k] as Map<String, dynamic>)
        ];
}

class Istatistik {
  final IstatistikDonem hafta, ay;
  Istatistik.fromJson(Map<String, dynamic> j)
      : hafta = IstatistikDonem.fromJson(j['hafta'] as Map<String, dynamic>),
        ay = IstatistikDonem.fromJson(j['ay'] as Map<String, dynamic>);
}

// ---- Koşu Analizleri (alt-bahisler) ----

class GunBahisler {
  final String date;
  final List<BahisHip> hipodromlar;
  GunBahisler.fromJson(Map<String, dynamic> j)
      : date = j['date'] as String,
        hipodromlar = (j['hipodromlar'] as List)
            .map((e) => BahisHip.fromJson(e as Map<String, dynamic>))
            .toList();
}

class BahisHip {
  final String hipodrom;
  final List<BahisAnaliz> bahisler;
  BahisHip.fromJson(Map<String, dynamic> j)
      : hipodrom = j['hipodrom'] as String,
        bahisler = (j['bahisler'] as List)
            .map((e) => BahisAnaliz.fromJson(e as Map<String, dynamic>))
            .toList();
}

class BahisAnaliz {
  final String tip, ad, aile;
  final int basKosu;
  final List<int> legs;
  final List<List<int>> kolonlar;
  final List<dynamic> secimAtlar; // tek: [{at_no,at}] ; ayak: [[{at_no,at}],...]
  final int kombinasyon, misli, maxButce;
  final double birim, kuponBedeli;
  final BahisSonuc? sonuc;
  BahisAnaliz.fromJson(Map<String, dynamic> j)
      : tip = j['tip'] as String,
        ad = j['ad'] as String,
        aile = j['aile'] as String? ?? 'tek',
        basKosu = j['bas_kosu'] as int,
        legs = (j['legs'] as List).map((e) => e as int).toList(),
        kolonlar = (j['kolonlar'] as List)
            .map((c) => (c as List).map((e) => e as int).toList())
            .toList(),
        secimAtlar = j['secim_atlar'] as List? ?? [],
        kombinasyon = j['kombinasyon'] as int,
        misli = j['misli'] as int,
        maxButce = j['max_butce'] as int,
        birim = (j['birim'] as num).toDouble(),
        kuponBedeli = (j['kupon_bedeli'] as num).toDouble(),
        sonuc = j['sonuc'] == null
            ? null
            : BahisSonuc.fromJson(j['sonuc'] as Map<String, dynamic>);
}

class BahisSonuc {
  final bool tuttu;
  final double? ikramiye, net;
  final List<List<int>> kazanan; // kolon-bazlı gerçek kazanan at_no'lar
  final Map<int, String> adlar; // yalnız Plase: at_no -> ad
  BahisSonuc.fromJson(Map<String, dynamic> j)
      : tuttu = j['tuttu'] as bool? ?? false,
        ikramiye = _d(j['ikramiye']),
        net = _d(j['net']),
        kazanan = ((j['kazanan'] as List?) ?? [])
            .map((c) => c is List
                ? c.map((e) => e as int).toList()
                : <int>[c as int])
            .toList(),
        adlar = ((j['adlar'] as Map?) ?? {}).map(
            (k, v) => MapEntry(int.parse(k.toString()), v as String? ?? ''));
}

// ---- Bildirimler ----

class BildirimOzet {
  final int id;
  final String baslik, mesaj;
  final bool okundu;
  final DateTime? createdAt;
  BildirimOzet.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        baslik = j['baslik'] as String? ?? '',
        mesaj = j['mesaj'] as String? ?? '',
        okundu = j['okundu'] as bool? ?? false,
        createdAt = j['created_at'] == null
            ? null
            : DateTime.tryParse(j['created_at'].toString());
}
