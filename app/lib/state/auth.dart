import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../api/client.dart';
import '../fcm_setup.dart';

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

class AuthState {
  final String? token;
  final String tier; // standart / vip
  final String? email;
  final bool isAdmin;
  const AuthState({this.token, this.tier = 'standart', this.email, this.isAdmin = false});

  bool get girisli => token != null;
  bool get premium => tier == 'vip'; // VIP uyeler premium icerige erisir
  bool get vip => tier == 'vip';
}

class AuthController extends Notifier<AuthState> {
  final _storage = const FlutterSecureStorage();

  ApiClient get _api => ref.read(apiClientProvider);

  @override
  AuthState build() {
    _yukle();
    return const AuthState();
  }

  Future<void> _yukle() async {
    final t = await _storage.read(key: 'token');
    if (t == null) return;
    _api.setToken(t);
    // Önce cache'lenmiş kimlikle iyimser oturum aç — ağ yavaşsa bile kullanıcı
    // "çıkış yapılmış" görmesin. /auth/ben yanıtı gelince state tazelenir.
    final cTier = await _storage.read(key: 'tier');
    final cEmail = await _storage.read(key: 'email');
    if (cTier != null) {
      state = AuthState(token: t, tier: cTier, email: cEmail);
    }
    try {
      final me = await _api.ben();
      state = AuthState(
        token: t,
        tier: me['tier'] as String,
        email: me['email'] as String?,
        isAdmin: me['is_admin'] as bool? ?? false,
      );
      await _storage.write(key: 'tier', value: me['tier'] as String);
      await _storage.write(key: 'email', value: me['email'] as String? ?? '');
      _pushTokenKaydet();
    } on DioException catch (e) {
      final sc = e.response?.statusCode;
      if (sc == 401 || sc == 403) {
        await cikis(); // token gerçekten geçersiz
      }
      // Ağ hatası (response yok / 5xx): oturumu DÜŞÜRME — iyimser state kalır,
      // bir sonraki istek retry interceptor'ı ile zaten yeniden denenir.
    } catch (_) {
      // Beklenmedik hata: oturumu koru (eski davranış sessiz çıkıştı).
    }
  }

  /// Cihazın FCM token'ını backend'e kaydeder (giriş yapılmışsa). Hata sessiz.
  Future<void> _pushTokenKaydet() async {
    try {
      final t = await cihazFcmToken();
      if (t != null) await _api.fcmTokenKaydet(t);
    } catch (_) {
      // push kaydı başarısızsa uygulama akışı etkilenmesin
    }
  }

  Future<void> _kaydet(String token, String tier, String? email) async {
    await _storage.write(key: 'token', value: token);
    _api.setToken(token);
    final me = await _api.ben();
    final sonTier = me['tier'] as String? ?? tier;
    final sonEmail = me['email'] as String? ?? email;
    await _storage.write(key: 'tier', value: sonTier);
    await _storage.write(key: 'email', value: sonEmail ?? '');
    state = AuthState(
      token: token,
      tier: sonTier,
      email: sonEmail,
      isAdmin: me['is_admin'] as bool? ?? false,
    );
    _pushTokenKaydet();
  }

  Future<void> kayit(String email, String sifre) => _api.kayit(email, sifre);

  Future<void> dogrula(String email, String kod) async {
    final r = await _api.dogrula(email, kod);
    await _kaydet(r['token'] as String, r['tier'] as String, email);
  }

  Future<void> giris(String email, String sifre) async {
    final r = await _api.giris(email, sifre);
    await _kaydet(r['token'] as String, r['tier'] as String, email);
  }

  Future<void> cikis() async {
    await _storage.delete(key: 'token');
    await _storage.delete(key: 'tier');
    await _storage.delete(key: 'email');
    _api.setToken(null);
    state = const AuthState();
  }
}

final authProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);
