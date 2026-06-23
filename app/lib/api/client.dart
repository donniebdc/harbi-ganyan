import 'dart:async';

import 'package:dio/dio.dart';
import '../config.dart';
import 'models.dart';

typedef RefreshCallback = Future<String?> Function();

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
  RefreshCallback? _refreshCallback;
  Future<String?>? _pendingRefresh;

  ApiClient()
      : _dio = Dio(BaseOptions(
          baseUrl: apiBase,
          connectTimeout: const Duration(seconds: 20),
          receiveTimeout: const Duration(seconds: 30),
        )) {
    _dio.interceptors.add(InterceptorsWrapper(onError: (e, handler) async {
      final req = e.requestOptions;
      final sc = e.response?.statusCode;

      final isAuthEndpoint = req.path.contains('/auth/giris') ||
          req.path.contains('/auth/yenile') ||
          req.path.contains('/auth/kayit') ||
          req.path.contains('/auth/dogrula');

      if (sc == 401 &&
          !isAuthEndpoint &&
          _token != null &&
          _refreshCallback != null &&
          req.extra['refreshed'] != true) {
        final newToken = await _doRefresh();
        if (newToken != null) {
          _token = newToken;
          req.headers['Authorization'] = 'Bearer $newToken';
          req.extra['refreshed'] = true;
          try {
            final r = await _dio.fetch(req);
            return handler.resolve(r);
          } on DioException catch (e2) {
            return handler.next(e2);
          }
        } else {
          return handler.next(e);
        }
      }

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

  Future<String?> _doRefresh() {
    _pendingRefresh ??=
        _refreshCallback!().whenComplete(() => _pendingRefresh = null);
    return _pendingRefresh!;
  }

  void setToken(String? t) => _token = t;
  void setRefreshCallback(RefreshCallback? cb) => _refreshCallback = cb;

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

  // ---- Auth ----
  Future<void> kayit(String email, String sifre) =>
      _dio.post('/auth/kayit', data: {'email': email, 'sifre': sifre});

  Future<Map<String, dynamic>> dogrula(String email, String kod) async {
    final r = await _dio.post('/auth/dogrula', data: {'email': email, 'kod': kod});
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> giris(String email, String sifre, String cihazId) async {
    final r = await _dio.post('/auth/giris',
        data: {'email': email, 'sifre': sifre, 'cihaz_id': cihazId});
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> ben() async {
    try {
      final r = await _dio.get('/auth/ben', options: _opt);
      return r.data as Map<String, dynamic>;
    } on DioException catch (e) {
      final sc = e.response?.statusCode;
      if (sc == 401 || sc == 403) rethrow;
      throw _agHatasi(e, '/auth/ben');
    }
  }

  Future<Map<String, dynamic>> yenile(String refreshToken) async {
    final r = await _dio.post('/auth/yenile',
        data: {'refresh_token': refreshToken});
    return r.data as Map<String, dynamic>;
  }

  Future<void> cikis(String? refreshToken) async {
    try {
      await _dio.post('/auth/cikis',
          data: refreshToken != null ? {'refresh_token': refreshToken} : {},
          options: _opt);
    } catch (_) {}
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

  Future<Map<String, dynamic>> uyelikDogrula(
      String purchaseToken, String productId) async {
    try {
      final r = await _dio.post(
        '/api/uyelik/dogrula',
        data: {'purchase_token': purchaseToken, 'product_id': productId},
        options: _opt,
      );
      return r.data as Map<String, dynamic>;
    } on DioException catch (e) {
      final mesaj =
          e.response?.data?['detail'] as String? ?? 'Satın alma doğrulanamadı.';
      throw AgHatasi(mesaj, statusCode: e.response?.statusCode);
    }
  }

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
