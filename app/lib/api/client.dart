import 'package:dio/dio.dart';
import '../config.dart';
import 'models.dart';

/// 'Günün Analizleri' premium-kilitli olduğunda fırlatılır (HTTP 403).
class KilitliHata implements Exception {
  final String gerekenTier;
  KilitliHata(this.gerekenTier);
}

class ApiClient {
  final Dio _dio;
  String? _token;

  ApiClient()
      : _dio = Dio(BaseOptions(
          baseUrl: apiBase,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 15),
        ));

  void setToken(String? t) => _token = t;

  Options get _opt => Options(
        headers: _token != null ? {'Authorization': 'Bearer $_token'} : null,
      );

  // ---- İçerik ----
  Future<List<GunOzet>> gunler() async {
    final r = await _dio.get('/gunler', options: _opt);
    return (r.data['gunler'] as List)
        .map((e) => GunOzet.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<GunDetay> gun(String date) async {
    try {
      final r = await _dio.get('/gun/$date', options: _opt);
      return GunDetay.fromJson(r.data as Map<String, dynamic>);
    } on DioException catch (e) {
      if (e.response?.statusCode == 403) {
        throw KilitliHata('premium');
      }
      rethrow;
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
      rethrow;
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
    final r = await _dio.get('/auth/ben', options: _opt);
    return r.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> bildirimler() async {
    final r = await _dio.get('/auth/bildirimler', options: _opt);
    return r.data as Map<String, dynamic>;
  }

  Future<void> bildirimOkundu(int id) =>
      _dio.post('/auth/bildirimler/$id/okundu', options: _opt);

  Future<void> fcmTokenKaydet(String token) => _dio.post('/auth/fcm-token',
      data: {'token': token, 'platform': 'android'}, options: _opt);

  Future<Istatistik> istatistik() async {
    final r = await _dio.get('/istatistik', options: _opt);
    return Istatistik.fromJson(r.data as Map<String, dynamic>);
  }
}
