import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:dio/dio.dart';
import '../state/auth.dart';
import '../theme.dart';

Future<void> authSheetGoster(BuildContext context) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: HG.kart,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    builder: (_) => const _AuthSheet(),
  );
}

class _AuthSheet extends ConsumerStatefulWidget {
  const _AuthSheet();
  @override
  ConsumerState<_AuthSheet> createState() => _AuthSheetState();
}

class _AuthSheetState extends ConsumerState<_AuthSheet> {
  static const int _minSifre = 6; // backend KayitReq ile aynı (auth.py)
  bool _kayitMi = false;
  bool _kodAdimi = false;
  bool _yukleniyor = false;
  String? _hata;
  final _email = TextEditingController();
  final _sifre = TextEditingController();
  final _kod = TextEditingController();

  @override
  void dispose() {
    _email.dispose();
    _sifre.dispose();
    _kod.dispose();
    super.dispose();
  }

  String _hataMetni(Object e) {
    if (e is DioException) {
      // Bağlantı/zaman aşımı
      if (e.type == DioExceptionType.connectionTimeout ||
          e.type == DioExceptionType.receiveTimeout ||
          e.type == DioExceptionType.sendTimeout ||
          e.type == DioExceptionType.connectionError) {
        return 'Sunucuya ulaşılamadı. İnternet bağlantınızı kontrol edin.';
      }
      final d = e.response?.data;
      if (d is Map) {
        final detail = d['detail'];
        // 400/401/409 → düz metin
        if (detail is String) return detail;
        // 422 (Pydantic doğrulama) → liste; ilk hatanın msg'ini göster
        if (detail is List && detail.isNotEmpty) {
          final first = detail.first;
          if (first is Map && first['msg'] is String) {
            return (first['msg'] as String)
                .replaceFirst(RegExp(r'^Value error,\s*'), '');
          }
        }
      }
      return 'Sunucu hatası (${e.response?.statusCode ?? '?'}).';
    }
    return 'Bir hata oluştu.';
  }

  Future<void> _calistir(Future<void> Function() f) async {
    setState(() {
      _yukleniyor = true;
      _hata = null;
    });
    try {
      await f();
    } catch (e) {
      setState(() => _hata = _hataMetni(e));
    } finally {
      if (mounted) setState(() => _yukleniyor = false);
    }
  }

  Future<void> _gonder() async {
    final auth = ref.read(authProvider.notifier);
    if (_kayitMi && !_kodAdimi) {
      // İstemci-tarafı doğrulama: sunucuya gitmeden net mesaj göster.
      final email = _email.text.trim();
      if (!email.contains('@') || !email.contains('.')) {
        setState(() => _hata = 'Geçerli bir e-posta adresi girin.');
        return;
      }
      if (_sifre.text.length < _minSifre) {
        setState(() => _hata = 'Şifreniz en az $_minSifre karakter olmalıdır.');
        return;
      }
      await _calistir(() async {
        await auth.kayit(email, _sifre.text);
        setState(() => _kodAdimi = true);
      });
    } else if (_kayitMi && _kodAdimi) {
      await _calistir(() async {
        await auth.dogrula(_email.text.trim(), _kod.text.trim());
        if (mounted) Navigator.pop(context);
      });
    } else {
      await _calistir(() async {
        await auth.giris(_email.text.trim(), _sifre.text);
        if (mounted) Navigator.pop(context);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final alt = media.viewInsets.bottom;        // klavye yüksekliği
    final navBar = media.viewPadding.bottom;    // sistem navigasyon çubuğu
    return Padding(
      // Klavye kapalıyken nav-bar boşluğu eklenir ki "Kayıt ol" çubuğun altında kalmasın.
      padding: EdgeInsets.fromLTRB(20, 18, 20, 20 + alt + (alt > 0 ? 0.0 : navBar)),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
                color: HG.kart2, borderRadius: BorderRadius.circular(2))),
        const SizedBox(height: 16),
        Text(_kayitMi ? (_kodAdimi ? 'Email Doğrulama' : 'Kayıt Ol') : 'Giriş Yap',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
        const SizedBox(height: 16),
        if (!_kodAdimi) ...[
          _alan(_email, 'Email', Icons.mail_outline, klavye: TextInputType.emailAddress),
          const SizedBox(height: 10),
          _alan(_sifre, _kayitMi ? 'Şifre (en az $_minSifre karakter)' : 'Şifre',
              Icons.lock_outline, gizli: true),
        ] else ...[
          Text('${_email.text.trim()} adresine gönderilen 6 haneli kodu girin.',
              style: const TextStyle(color: HG.metinSoluk, fontSize: 13)),
          const SizedBox(height: 10),
          _alan(_kod, 'Doğrulama Kodu', Icons.pin, klavye: TextInputType.number),
        ],
        if (_hata != null) ...[
          const SizedBox(height: 10),
          Text(_hata!, style: const TextStyle(color: HG.kirmizi, fontSize: 13)),
        ],
        const SizedBox(height: 18),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: HG.altin,
                foregroundColor: Colors.black,
                padding: const EdgeInsets.symmetric(vertical: 14)),
            onPressed: _yukleniyor ? null : _gonder,
            child: _yukleniyor
                ? const SizedBox(
                    width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : Text(_kayitMi ? (_kodAdimi ? 'Doğrula' : 'Kod Gönder') : 'Giriş',
                    style: const TextStyle(fontWeight: FontWeight.w800)),
          ),
        ),
        const SizedBox(height: 8),
        if (!_kodAdimi)
          TextButton(
            onPressed: () => setState(() {
              _kayitMi = !_kayitMi;
              _hata = null;
            }),
            child: Text(_kayitMi ? 'Zaten hesabım var · Giriş' : 'Hesabın yok mu? Kayıt ol',
                style: const TextStyle(color: HG.altinAcik)),
          ),
      ]),
    );
  }

  Widget _alan(TextEditingController c, String etiket, IconData ikon,
      {bool gizli = false, TextInputType? klavye}) {
    return TextField(
      controller: c,
      obscureText: gizli,
      keyboardType: klavye,
      style: const TextStyle(color: HG.metin),
      decoration: InputDecoration(
        labelText: etiket,
        labelStyle: const TextStyle(color: HG.metinSoluk),
        prefixIcon: Icon(ikon, color: HG.metinSoluk, size: 20),
        filled: true,
        fillColor: HG.zemin,
        enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: HG.kart2)),
        focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: const BorderSide(color: HG.altin)),
      ),
    );
  }
}
