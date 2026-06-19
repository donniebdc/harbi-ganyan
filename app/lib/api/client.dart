import 'package:dio/dio.dart';
import '../config.dart';
import 'models.dart';

/// 'Günün Analizleri' premium-kilitli olduğunda fırlatılır (HTTP 403).
class KilitliHata implements Exception {
  final String gerekenTier;
  KilitliHata(this.gerekenTier);
}

/// Ağ / timeout hatalarını sarmalayan özel istisna.
/// [mesaj] kullanıcıya gösterilecek Türkçe açıklama.
class AgHatasi implements Exception {
  final String mesaj;
  final int? statusCode;
  AgHatasi(this.mesaj, {this.statusCode});
  @override
  String toString() => mesaj;
}

class ApiClient {
  final Dio _dio;
  String? _token;

  ApiClient()
      : _dio = Dio(BaseOptions(
          baseUrl: apiBase,
          connectTimeout: const Duration(seconds: 20),
          receiveTimeout: const Duration(seconds: 30),
        )) {
    // Geçici ağ hatalarında (timeout / bağlantı kopması) GET isteklerini
    // artan gecikmeyle 4 kez daha dene — ev bağlantısı / zayıf mobil ağlarda
    // "Bağlantı hatası" ekranlarını azaltır.
    _dio.interceptors.add(InterceptorsWrapper(onError: (e, handler) async {
      final req = e.requestOptions;
      final deneme = (req.extra['retry'] as int?) ?? 0;
      final gecici = e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.receiveTimeout ||
          e.type == DioExceptionType.sendTimeout ||
          e.type == DioExceptionType.connectionError;
      if (gecici && req.method == 'GET' && deneme < 4) {
        await Future.delayed(Duration(milliseconds: 600 * (deneme + 1)));
        req.extra['retry'] = deneme + 1;
        try {
          final r = await _dio.fetch(req);
          return handler.resolve(r);
        } on DioException catch (e2) {
          return handler.next(e2);
        }
      }
      handler.next(e);
    }));
  }

  void setToken(String? t) => _token = t;

  Options get _opt => Options(
        headers: _token != null ? {'Authorization': 'Bearer $_token'} : null,
      );

  // ---- İçerik ----
  Future<List<GunOzet>> gunler() async {
    try {
      final r = await _dio.get('/gunler', options: _opt);
      return (r.data['gunler'] as List)
          .map((e) => GunOzet.fromJson(e as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      throw _agHatasi(e, '/gunler');
    } catch (e) {
      throw AgHatasi('Beklenmeyen hata (/gunler): $e');
    }
  }

  Future<GunDetay> gun(String date) async {
    try {
      final r = await _dio.get('/gun/$date', options: _opt);
      return GunDetay.fromJson(r.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 403) {
        throw KilitliHata('vip');
      }
      if (e.response?.statusCode == 404) {
        throw AgHatasi('Bu güne ait analiz henüz yüklenmedi.', statusCode: 404);
      }
      throw _agHatasi(e, '/gun/$date');
    } catch (e) {
      throw AgHatasi('Beklenmeyen hata (/gun/$date): $e');
    }
  }

  /// Koşu Analizleri (alt-bahisler) — VIP. 403'te KilitliHata('vip').
  Future<GunBahisler> gunBahisler(String date) async {
    try {
      final r = await _dio.get('/gun/$date/bahisler', options: _opt);
      return GunBahisler.fromJson(r.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 403) {
        final d = e.response?.data;
        final tier = (d is Map && d['detail'] is Map)
            ? (d['detail']['gereken_tier'] as String? ?? 'vip')
            : 'vip';
        throw KilitliHata(tier);
      }
      if (e.response?.statusCode == 404) {
        throw AgHatasi('Bu güne ait bahis analizi henüz yüklenmedi.', statusCode: 404);
      }
      throw _agHatasi(e, '/gun/$date/bahisler');
    } catch (e) {
      throw AgHatasi('Beklenmeyen hata (/gun/$date/bahisler): $e');
    }
  }

  // ---- Auth ----
  Future<void> kayit(String email, String sifre) =>
      _dio.post('/auth/kayit', data: {'email': email, 'sifre': sifre});

  Future<Map<String, dynamic>> dogrula(String email, String kod) async {
    final r = await _dio.post('/auth/dogrula', data: {'email': email, 'kod': kod});
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> giris(String email, String sifre) async {
    final r = await _dio.post('/auth/giris', data: {'email': email, 'sifre': sifre});
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> ben() async {
    try {
      final r = await _dio.get('/auth/ben', options: _opt);
      return r.data as Map<String, dynamic>;
    } on DioException catch (e) {
      // 401/403: token geçersiz veya yetkisiz — olduğu gibi fırlat ki
      // auth.dart _yukle() doğru şekilde cikis() yapabilsin.
      final sc = e.response?.statusCode;
      if (sc == 401 || sc == 403) rethrow;
      throw _agHatasi(e, '/auth/ben');
    }
  }

  Future<Map<String, dynamic>> bildirimler() async {
    try {
      final r = await _dio.get('/auth/bildirimler', options: _opt);
      return r.data as Map<String, dynamic>;
    } on DioException catch (e) {
      throw _agHatasi(e, '/auth/bildirimler');
    }
  }

  Future<void> bildirimOkundu(int id) =>
      _dio.post('/auth/bildirimler/$id/okundu', options: _opt);

  Future<void> bildirimleriOkunduHepsi() =>
      _dio.post('/auth/bildirimler/okundu-hepsi', options: _opt);

  Future<void> fcmTokenKaydet(String token) => _dio.post('/auth/fcm-token',
      data: {'token': token, 'platform': 'android'}, options: _opt);

  Future<Istatistik> istatistik() async {
    try {
      final r = await _dio.get('/istatistik', options: _opt);
      return Istatistik.fromJson(r.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw _agHatasi(e, '/istatistik');
    }
  }

  /// Ortak ağ hatası sarmalayıcı — kullanıcıya anlaşılır Türkçe mesaj üretir.
  AgHatasi _agHatasi(DioException e, String yol) {
    final sc = e.response?.statusCode;
    String mesaj;
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.sendTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      mesaj = 'Sunucuya erişilemiyor (zaman aşımı).\nİnternet bağlantınızı kontrol edin.';
    } else if (e.type == DioExceptionType.connectionError) {
      mesaj = 'Bağlantı kurulamadı.\nİnternet bağlantınızı kontrol edin.';
    } else if (sc == 500) {
      mesaj = 'Sunucu hatası (500). Lütfen daha sonra tekrar deneyin.';
    } else if (sc == 502 || sc == 503 || sc == 504) {
      mesaj = 'Sunucu geçici olarak hizmet dışı ($sc). Lütfen bekleyip tekrar deneyin.';
    } else {
      mesaj = 'Bağlantı hatası ($yol).\nLütfen internet bağlantınızı kontrol edip tekrar deneyin.';
    }
    return AgHatasi(mesaj, statusCode: sc);
  }
}
