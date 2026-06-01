@echo off
setlocal enabledelayedexpansion

set "WINRAR=C:\Program Files\WinRAR\WinRAR.exe"
set /a count=0
set /a part=1
set "files="

for %%F in (*.*) do (
    if /I not "%%~nxF"=="%~nx0" (
        set /a count+=1
        set "files=!files! "%%F""

        if !count! EQU 10 (
            "%WINRAR%" a -afzip "paket_!part!.zip" !files!
            set /a part+=1
            set /a count=0
            set "files="
        )
    )
)

if not "!files!"=="" (
    "%WINRAR%" a -afzip "paket_!part!.zip" !files!
)

echo.
echo Islem tamamlandi.
pause