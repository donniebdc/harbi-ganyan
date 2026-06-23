import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';
import '../api/client.dart';
import '../fcm_setup.dart';

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

class AuthState {
  final String? token;
  final String tier;
  final String? email;
  final bool isAdmin;
  const AuthState({this.token, this.tier = 'standart', this.email, this.isAdmin = false});

  bool get girisli => token != null;
  bool get premium => tier == 'vip';
  bool get vip => tier == 'vip';
}

class AuthController extends Notifier<AuthState> {
  final _storage = const FlutterSecureStorage();

  static const _keyToken = 'token';
  static const _keyRefreshToken = 'refresh_token';
  static const _keyTier = 'tier';
  static const _keyEmail = 'email';
  static const _keyCihazId = 'cihaz_id';
  static const _uuid = Uuid();

  ApiClient get _api => ref.read(apiClientProvider);

  @override
  AuthState build() {
    _yukle();
    return const AuthState();
  }

  Future<String> _getCihazId() async {
    var id = await _storage.read(key: _keyCihazId);
    if (id == null) {
      id = _uuid.v4();
      await _storage.write(key: _keyCihazId, value: id);
    }
    return id;
  }

  Future<void> _yukle() async {
    final t = await _storage.read(key: _keyToken);
    if (t == null) return;
    _api.setToken(t);
    _api.setRefreshCallback(_refreshIfNeeded);
    final cTier = await _storage.read(key: _keyTier);
    final cEmail = await _storage.read(key: _keyEmail);
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
      await _storage.write(key: _keyTier, value: me['tier'] as String);
      await _storage.write(key: _keyEmail, value: me['email'] as String? ?? '');
      _pushTokenKaydet();
    } on DioException catch (e) {
      final sc = e.response?.statusCode;
      if (sc == 401 || sc == 403) {
        await cikis(sendToServer: false);
      }
    } catch (_) {}
  }

  Future<void> _pushTokenKaydet() async {
    try {
      final t = await cihazFcmToken();
      if (t != null) await _api.fcmTokenKaydet(t);
    } catch (_) {}
  }

  Future<String?> _refreshIfNeeded() async {
    final rt = await _storage.read(key: _keyRefreshToken);
    if (rt == null) return null;
    try {
      final r = await _api.yenile(rt);
      final newToken = r['token'] as String;
      final newRefresh = r['refresh_token'] as String;
      await _storage.write(key: _keyToken, value: newToken);
      await _storage.write(key: _keyRefreshToken, value: newRefresh);
      _api.setToken(newToken);
      return newToken;
    } on DioException {
      await cikis(sendToServer: false);
      return null;
    }
  }

  Future<void> _kaydet(String token, String refreshToken, String tier, String? email) async {
    await _storage.write(key: _keyToken, value: token);
    await _storage.write(key: _keyRefreshToken, value: refreshToken);
    _api.setToken(token);
    _api.setRefreshCallback(_refreshIfNeeded);
    final me = await _api.ben();
    final sonTier = me['tier'] as String? ?? tier;
    final sonEmail = me['email'] as String? ?? email;
    await _storage.write(key: _keyTier, value: sonTier);
    await _storage.write(key: _keyEmail, value: sonEmail ?? '');
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
    await _kaydet(
      r['token'] as String,
      r['refresh_token'] as String,
      r['tier'] as String,
      email,
    );
  }

  Future<void> giris(String email, String sifre) async {
    final cihazId = await _getCihazId();
    final r = await _api.giris(email, sifre, cihazId);
    await _kaydet(
      r['token'] as String,
      r['refresh_token'] as String,
      r['tier'] as String,
      email,
    );
  }

  Future<void> tierYenile() async {
    try {
      final me = await _api.ben();
      final yeniTier = me['tier'] as String? ?? state.tier;
      await _storage.write(key: _keyTier, value: yeniTier);
      state = AuthState(
        token: state.token,
        tier: yeniTier,
        email: state.email,
        isAdmin: state.isAdmin,
      );
    } catch (_) {}
  }

  Future<void> cikis({bool sendToServer = true}) async {
    if (sendToServer) {
      final rt = await _storage.read(key: _keyRefreshToken);
      try {
        await _api.cikis(rt);
      } catch (_) {}
    }
    await _storage.delete(key: _keyToken);
    await _storage.delete(key: _keyRefreshToken);
    await _storage.delete(key: _keyTier);
    await _storage.delete(key: _keyEmail);
    _api.setToken(null);
    _api.setRefreshCallback(null);
    state = const AuthState();
  }
}

final authProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);
