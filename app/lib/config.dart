/// Uygulama yapilandirmasi.
///
/// API tabani derleme zamaninda verilebilir:
///   flutter run --dart-define=HG_API=http://10.0.2.2:8000
/// Android emulatorunde host makinesi = 10.0.2.2.
const String apiBase = String.fromEnvironment(
  'HG_API',
  defaultValue: 'https://api.harbiganyan.com',
);
