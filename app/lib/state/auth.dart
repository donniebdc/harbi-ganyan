import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../api/client.dart';

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient());

class AuthState {
  final String? token;
  final String tier; // standart / premium / vip
  final String? email;
  final bool isAdmin;
  const AuthState({this.token, this.tier = 'standart', this.email, this.isAdmin = false});

  bool get girisli => token != null;
  bool get premium => tier == 'premium' || tier == 'vip';
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
    try {
      final me = await _api.ben();
      state = AuthState(
        token: t,
        tier: me['tier'] as String,
        email: me['email'] as String?,
        isAdmin: me['is_admin'] as bool? ?? false,
      );
    } catch (_) {
      await cikis();
    }
  }

  Future<void> _kaydet(String token, String tier, String? email) async {
    await _storage.write(key: 'token', value: token);
    _api.setToken(token);
    final me = await _api.ben();
    state = AuthState(
      token: token,
      tier: me['tier'] as String? ?? tier,
      email: me['email'] as String? ?? email,
      isAdmin: me['is_admin'] as bool? ?? false,
    );
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
    _api.setToken(null);
    state = const AuthState();
  }
}

final authProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);
