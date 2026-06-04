import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Harbi Ganyan — Admin (yalnız yönetici). Web admin panelini telefonda açar.
/// Tek kaynak: panel web'de güncellenince burada da güncel olur.
const String adminUrl = 'https://api.harbiganyan.com/admin';
const Color _altin = Color(0xFFE8B339);
const Color _zemin = Color(0xFF0E1116);

void main() => runApp(const AdminApp());

class AdminApp extends StatelessWidget {
  const AdminApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Harbi Ganyan Admin',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
            seedColor: _altin, brightness: Brightness.dark),
        scaffoldBackgroundColor: _zemin,
      ),
      home: const _AdminWebView(),
    );
  }
}

class _AdminWebView extends StatefulWidget {
  const _AdminWebView();
  @override
  State<_AdminWebView> createState() => _AdminWebViewState();
}

class _AdminWebViewState extends State<_AdminWebView> {
  late final WebViewController _c;
  bool _loading = true;
  bool _hata = false;

  @override
  void initState() {
    super.initState();
    _c = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(_zemin)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted: (_) {
          if (mounted) setState(() { _loading = true; _hata = false; });
        },
        onPageFinished: (_) {
          if (mounted) setState(() => _loading = false);
        },
        onWebResourceError: (e) {
          // Yalnız ana çerçeve hatasında uyar (alt kaynak hataları yok sayılır).
          if (e.isForMainFrame == true && mounted) {
            setState(() { _loading = false; _hata = true; });
          }
        },
      ))
      ..loadRequest(Uri.parse(adminUrl));
  }

  void _yenile() {
    setState(() => _hata = false);
    _c.loadRequest(Uri.parse(adminUrl));
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        if (await _c.canGoBack()) {
          _c.goBack();
        } else {
          SystemNavigator.pop(); // geri yığını boşsa uygulamadan çık
        }
      },
      child: Scaffold(
        body: SafeArea(
          child: Stack(
            children: [
              WebViewWidget(controller: _c),
              if (_loading)
                const LinearProgressIndicator(
                    color: _altin, backgroundColor: Colors.transparent),
              if (_hata) _HataKaplama(onYenile: _yenile),
            ],
          ),
        ),
        floatingActionButton: FloatingActionButton.small(
          backgroundColor: _altin,
          onPressed: () => _c.reload(),
          tooltip: 'Yenile',
          child: const Icon(Icons.refresh, color: Colors.black),
        ),
      ),
    );
  }
}

class _HataKaplama extends StatelessWidget {
  final VoidCallback onYenile;
  const _HataKaplama({required this.onYenile});
  @override
  Widget build(BuildContext context) {
    return Container(
      color: _zemin,
      alignment: Alignment.center,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.wifi_off, color: _altin, size: 48),
          const SizedBox(height: 12),
          const Text('Panele ulaşılamadı',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          const Text('İnternet bağlantınızı kontrol edin.',
              style: TextStyle(color: Colors.white70, fontSize: 13)),
          const SizedBox(height: 16),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: _altin, foregroundColor: Colors.black),
            onPressed: onYenile,
            child: const Text('Tekrar Dene'),
          ),
        ],
      ),
    );
  }
}
