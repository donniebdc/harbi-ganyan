import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

@pragma('vm:entry-point')
Future<void> _arkaplanMesajIsle(RemoteMessage message) async {
  // Arka plan/terminated: 'notification' tipli mesajlar Android tarafından
  // otomatik gösterilir; burada ek işleme gerekmiyor.
}

/// Firebase'i başlatır, bildirim iznini ister, arka plan handler'ını bağlar.
/// main() içinde runApp'tan ÖNCE çağrılır. Firebase yoksa sessizce geçer.
Future<void> fcmBaslat() async {
  try {
    await Firebase.initializeApp();
    FirebaseMessaging.onBackgroundMessage(_arkaplanMesajIsle);
    await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );
  } catch (_) {
    // Firebase yapılandırılmamışsa uygulama yine de çalışsın.
  }
}

/// Cihazın güncel FCM token'ı (backend'e kayıt için). Alınamazsa null.
Future<String?> cihazFcmToken() async {
  try {
    return await FirebaseMessaging.instance.getToken();
  } catch (_) {
    return null;
  }
}
