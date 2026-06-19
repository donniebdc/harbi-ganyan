# Claude Gecis Raporu

Tarih: 2026-06-19
Proje: Harbi Ganyan Android / Backend
Repo: https://github.com/donniebdc/harbi-ganyan

## Genel Durum

Harbi Ganyan uygulamasi Google Play Store yayinina hazirlik icin guvenlik, build ve GitHub tarafinda duzenlendi. Android release imzalama sirri proje disina alindi, backend production guvenlik kontrolleri eklendi, AAB/APK release buildleri dogrulandi ve kaynak kod GitHub `main` branch'ine push edildi.

Yerel kaynak klasoru:

```text
D:\Android
```

Son Git commit:

```text
82dc78b Initial Play Store ready app source
```

## Yapilan Guvenlik Duzenlemeleri

### Android release imzalama

- Gercek release imzalama dosyalari `app/android` altindan cikarildi.
- Yeni konum:

```text
C:\Users\Kurgu\HarbiGanyanSigning\key.properties
C:\Users\Kurgu\HarbiGanyanSigning\harbi_ganyan_release.jks
```

- Kullanici ortam degiskeni ayarlandi:

```text
HG_KEY_PROPERTIES=C:\Users\Kurgu\HarbiGanyanSigning\key.properties
```

- `app/android/app/build.gradle.kts` guncellendi:
  - `HG_KEY_PROPERTIES` ortam degiskeni varsa dis signing config dosyasini okur.
  - Yoksa geriye uyumluluk icin `android/key.properties` arar.
  - Release build artik debug key'e sessiz dusmez; signing config yoksa hata verir.

- Projede sadece ornek dosya birakildi:

```text
app/android/key.properties.example
```

### Git ignore korumalari

Kok `.gitignore` eklendi ve su dosyalar GitHub disinda birakildi:

- `app/build/`
- `APK/`
- `backend/*.db`
- `backend/.env`
- `app/android/local.properties`
- `app/android/key.properties`
- `app/android/*.jks`
- `app/android/*.keystore`

Ek olarak mevcut `app/.gitignore`, `app/android/.gitignore` ve `backend/.gitignore` korumalari da duruyor.

### Backend production guard

`backend/app/config.py` ve `backend/app/main.py` guncellendi.

Yeni davranis:

- `HG_APP_ENV=production` oldugunda backend asagidaki durumlarda baslamaz:
  - `HG_JWT_SECRET` default degerdeyse.
  - `HG_JWT_SECRET` 32 karakterden kisaysa.
  - `HG_CORS_ORIGINS=*` ise veya bos ise.

Bu sayede production ortam yanlislikla zayif JWT secret veya wildcard CORS ile acilmaz.

### Auth rate limit

`backend/app/api/auth.py` icine basit bellek ici rate limit eklendi.

Kapsam:

- `/auth/kayit`
- `/auth/dogrula`
- `/auth/giris`

Limitler:

```text
kayit: 5 deneme / 15 dakika / e-posta
dogrula: 8 deneme / 15 dakika / e-posta
giris: 10 deneme / 15 dakika / e-posta
```

Not: Bu su an tek process icin bellek ici korumadir. Production'da coklu worker veya yatay olcekleme olacaksa Redis tabanli rate limit daha dogru olur.

## Test ve Dogrulamalar

Eklenen test:

```text
backend/tests/test_security_controls.py
```

Calisan testler:

```powershell
$env:PYTHONPATH='D:\Android\backend'
python -m unittest discover -s 'D:\Android\backend\tests' -v
```

Sonuc:

```text
Ran 4 tests
OK
```

Production guard dogrulamasi:

```powershell
$env:PYTHONPATH='D:\Android\backend'
$env:HG_APP_ENV='production'
$env:HG_JWT_SECRET='12345678901234567890123456789012'
$env:HG_CORS_ORIGINS='https://api.harbiganyan.com'
python -c "import app.main; print('production import ok')"
```

Sonuc:

```text
production import ok
```

Zayif secret ile production import testi:

```powershell
$env:PYTHONPATH='D:\Android\backend'
$env:HG_APP_ENV='production'
$env:HG_JWT_SECRET='dev-secret-change-me'
$env:HG_CORS_ORIGINS='https://api.harbiganyan.com'
python -c "import app.main"
```

Beklenen sonuc:

```text
RuntimeError: HG_JWT_SECRET must be a strong production secret.
```

Backend compile kontrolu:

```powershell
python -m compileall -q 'D:\Android\backend\app' 'D:\Android\backend\tests'
```

Sonuc:

```text
compileall ok
```

## Android Build Durumu

APK release build:

```powershell
$env:HG_KEY_PROPERTIES=Join-Path $env:USERPROFILE 'HarbiGanyanSigning\key.properties'
flutter build apk --release --dart-define=HG_API=https://api.harbiganyan.com
```

Sonuc:

```text
Built build\app\outputs\flutter-apk\app-release.apk
```

AAB release build:

```powershell
$env:HG_KEY_PROPERTIES=Join-Path $env:USERPROFILE 'HarbiGanyanSigning\key.properties'
flutter build appbundle --release --dart-define=HG_API=https://api.harbiganyan.com
```

Sonuc:

```text
Built build\app\outputs\bundle\release\app-release.aab
```

Play Store'a yuklenecek dosya:

```text
D:\Android\app\build\app\outputs\bundle\release\app-release.aab
```

APK imza dogrulamasi:

```powershell
apksigner verify --print-certs D:\Android\app\build\app\outputs\flutter-apk\app-release.apk
```

Sertifika:

```text
CN=Harbi Ganyan, OU=Mobile, O=Harbi Ganyan, L=Istanbul, ST=Istanbul, C=TR
SHA-256: 6d538d375f55452bbb3897cad75350c48aa28e5c9e4d4547fe00110623219e6e
```

## Flutter Analyze Durumu

`flutter analyze` calistirildi ve mevcut koddan gelen 5 uyari bulundu.

Ozet:

- `lib/screens/home.dart`: kullanilmayan import.
- `lib/screens/istatistik.dart`: kullanilmayan import.
- `lib/screens/placeholder.dart`: gereksiz string escape uyarilari.

Bu uyarilar yapilan guvenlik/build degisikliklerinden kaynaklanmiyor. Play Store yayinini dogrudan engellemesi beklenmez, ancak ileride temizlenebilir.

## GitHub Durumu

Yerel repo:

```text
D:\Android
```

Remote:

```text
origin https://github.com/donniebdc/harbi-ganyan.git
```

Remote `main` branch force-with-lease ile yeni kaynak kodla guncellendi.

Remote branchler:

```text
main -> 82dc78b
analiz/altili-aktarim-optim -> eski branch, halen duruyor
```

Not: Eski `analiz/altili-aktarim-optim` branch'i silinmedi. Gerekirse sonradan silinebilir.

## Play Console Durumu

Google Play Developer hesabi icin odeme yapildi. Play Console su anda Google kimlik dogrulamasini bekliyor. Kimlik dogrulamasi tamamlaninca uygulama olusturma butonu aktif hale gelmeli.

Onaydan sonra izlenecek siralama:

1. Play Console'da uygulama olustur.
2. Uygulama adi: `Harbi Ganyan`
3. Varsayilan dil: Turkce
4. Tur: Uygulama
5. Ucret: Ucretsiz
6. Ilk yayin kanali: Dahili test
7. AAB yukle.
8. Gizlilik politikasi URL'si gir.
9. Veri guvenligi formu doldur.
10. Icerik derecelendirme formu doldur.
11. Hedef kitle ve uygulama erisimi formlarini tamamla.

## Legal Dosyalar

IDE'de acik olan legal dosyalar:

```text
legal/gizlilik-politikasi.md
legal/kvkk-aydinlatma-metni.md
legal/kullanim-sartlari.md
legal/sorumlu-oyun.md
```

Bu dosyalar Play Store icin URL olarak yayinlanmali. Onerilen yol:

- GitHub Pages kullanmak.
- Gizlilik politikasi icin herkese acik URL olusturmak.
- Kullanim sartlari, KVKK ve sorumlu oyun metinlerini de ayni sayfa setinde yayinlamak.

## Kalan Isler

- Google kimlik dogrulamasinin tamamlanmasini bekle.
- Legal dosyalari GitHub Pages veya baska bir web host uzerinden URL'ye cevir.
- Play Console uygulama kaydini olustur.
- Store listing icin kisa aciklama, uzun aciklama, ikon, ekran goruntuleri ve feature graphic hazirla.
- Data Safety formu cevaplarini uygulamanin gercek veri kullanimina gore doldur.
- Icerik derecelendirmede uygulamayi analiz/tahmin/icerik uygulamasi olarak konumlandir.
- Magaza metinlerinde "kesin kazandirir", "para kazandirir", "bahis oynatir", "kupon yatir" gibi ifadelerden kacin.
- Uygulamada gercek para ile bahis oynatma, para yatirma/cekme veya bahis operatorune yonlendirme yoksa Play Console uygulama kategorileri ekraninda "Hicbiri" secili kalmali.

## Onemli Notlar

- Release signing dosyalari kaybedilmemeli. `C:\Users\Kurgu\HarbiGanyanSigning` klasoru yedeklenmeli ama GitHub'a yuklenmemeli.
- Play App Signing aktiflestirilirken Google'in verdigi yonergeler dikkatle izlenmeli.
- Production backend icin en az su ortam degiskenleri gerekli:

```text
HG_APP_ENV=production
HG_DATABASE_URL=postgresql+psycopg2://...
HG_JWT_SECRET=<32+ karakter guclu secret>
HG_CORS_ORIGINS=https://api.harbiganyan.com
```

