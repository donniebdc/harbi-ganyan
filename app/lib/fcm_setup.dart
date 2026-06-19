import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'nav_key.dart';
import 'screens/bildirimler.dart';

const String _kanalId = 'harbi_ganyan_default';
const String _kanalAd = 'Harbi Ganyan Bildirimleri';

final FlutterLocalNotificationsPlugin _local = FlutterLocalNotificationsPlugin();

const AndroidNotificationChannel _kanal = AndroidNotificationChannel(
  _kanalId,
  _kanalAd,
  description: 'Günün analizleri ve canlı yarış sonuçları bildirimleri',
  importance: Importance.high,
);

@pragma('vm:entry-point')
Future<void> _arkaplanMesajIsle(RemoteMessage message) async {
  // Arka plan/terminated: 'notification' tipli mesajlar Android tarafından
  // (default kanal meta-data'sı ile) otomatik gösterilir.
}

/// Firebase + yerel bildirim kanalı + izin. main()'de runApp'tan ÖNCE çağrılır.
Future<void> fcmBaslat() async {
  try {
    await Firebase.initializeApp();
    FirebaseMessaging.onBackgroundMessage(_arkaplanMesajIsle);

    // Yerel bildirim (foreground'da ekrana düşürmek + kanalı oluşturmak için).
    const initSettings = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    );
    await _local.initialize(initSettings);
    await _local
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(_kanal);

    await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    // Uygulama açıkken (foreground) gelen push'u ekrana düşür.
    FirebaseMessaging.onMessage.listen(_foregroundGoster);

    // Deep-link: push'a tıklanınca Bildirimler sayfasına git.
    // (a) Uygulama arka plandayken tıklandı:
    FirebaseMessaging.onMessageOpenedApp.listen(_pushTiklandi);
    // (b) Uygulama kapalıyken push'la açıldı:
    final ilk = await FirebaseMessaging.instance.getInitialMessage();
    if (ilk != null) {
      WidgetsBinding.instance
          .addPostFrameCallback((_) => _pushTiklandi(ilk));
    }
  } catch (_) {
    // Firebase yapılandırılmamışsa uygulama yine de çalışsın.
  }
}

/// Push'a tıklanınca data.route'a göre yönlendir (şimdilik tek hedef:
/// Bildirimler sayfası). Aynı sayfa üst üste açılmasın diye kontrol edilir.
void _pushTiklandi(RemoteMessage message) {
  final route = message.data['route'];
  if (route != 'bildirimler') return;
  final nav = navigatorKey.currentState;
  if (nav == null) return;
  nav.push(MaterialPageRoute(builder: (_) => const BildirimlerEkrani()));
}

void _foregroundGoster(RemoteMessage message) {
  final n = message.notification;
  if (n == null) return;
  _local.show(
    n.hashCode,
    n.title,
    n.body,
    const NotificationDetails(
      android: AndroidNotificationDetails(
        _kanalId,
        _kanalAd,
        importance: Importance.high,
        priority: Priority.high,
        icon: '@mipmap/ic_launcher',
      ),
    ),
  );
}

/// Cihazın güncel FCM token'ı (backend'e kayıt için). Alınamazsa null.
Future<String?> cihazFcmToken() async {
  try {
    return await FirebaseMessaging.instance.getToken();
  } catch (_) {
    return null;
  }
}
