# Harbi Ganyan - APK yayinla: build + yerel kopya + Drive yukleme + guvenli kurulum
# Kullanim:  powershell -ExecutionPolicy Bypass -File app\yayinla.ps1
#   -SkipBuild  : mevcut app-release.apk'yi kullan (yeniden build etme)
#   -NoInstall  : telefona kurma (sadece build + kopya + Drive)
param([switch]$SkipBuild, [switch]$NoInstall)

$ErrorActionPreference = "Stop"
$App   = "E:\Ganyan Gemini\app"
$ApkOut = "$App\build\app\outputs\flutter-apk\app-release.apk"
$LocalDir = "E:\Ganyan Gemini\APK"
$Flutter = "C:\src\flutter\bin\flutter.bat"
$Adb = "C:\Users\Kurgu\AppData\Local\Android\Sdk\platform-tools\adb.exe"
# rclone: PATH'te 'rclone' varsa onu, yoksa winget yolunu kullan
$Rclone = (Get-Command rclone -ErrorAction SilentlyContinue).Source
if (-not $Rclone) {
  $Rclone = (Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter rclone.exe -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
}

# 1) Surum (pubspec.yaml: 'version: 1.0.11+12')
$ver = (Select-String -Path "$App\pubspec.yaml" -Pattern '^\s*version:\s*(.+)$').Matches.Groups[1].Value.Trim()
Write-Host "Surum: $ver" -ForegroundColor Cyan

# 2) Build (release - sabit imza, oturum korunur)
if (-not $SkipBuild) {
  Write-Host "Release APK build ediliyor..." -ForegroundColor Cyan
  & $Flutter build apk --release
  if ($LASTEXITCODE -ne 0) { throw "flutter build basarisiz" }
}
if (-not (Test-Path $ApkOut)) { throw "APK bulunamadi: $ApkOut" }

# 3) Yerel versiyonlu kopya
New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
$LocalApk = "$LocalDir\harbi_ganyan_$ver.apk"
Copy-Item $ApkOut $LocalApk -Force
Write-Host "Yerel kopya: $LocalApk" -ForegroundColor Green

# 4) Google Drive yukleme (rclone gdrive: = hedef klasor, root_folder_id config'te)
if ($Rclone) {
  Write-Host "Drive'a yukleniyor..." -ForegroundColor Cyan
  & $Rclone copyto $LocalApk "gdrive:harbi_ganyan_$ver.apk" --stats-one-line
  if ($LASTEXITCODE -eq 0) { Write-Host "Drive: harbi_ganyan_$ver.apk yuklendi" -ForegroundColor Green }
  else { Write-Warning "Drive yukleme basarisiz (token suresi dolmus olabilir)" }
} else { Write-Warning "rclone bulunamadi, Drive yukleme atlandi" }

# 5) Telefona GUVENLI kurulum (adb install -r = yerinde, imza ayni, OTURUM KORUNUR)
#    ASLA 'flutter install' kullanma -> uygulamayi silip kurar, token gider.
if (-not $NoInstall) {
  $dev = (& $Adb devices) -match "\tdevice$"
  if ($dev) {
    Write-Host "Telefona kuruluyor (adb install -r)..." -ForegroundColor Cyan
    & $Adb install -r $ApkOut
  } else { Write-Warning "Bagli cihaz yok, kurulum atlandi (USB + USB hata ayiklama)" }
}
Write-Host "TAMAM." -ForegroundColor Green
