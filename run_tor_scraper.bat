@echo off
echo === TOR SCRAPER STARTING ===

REM Çalışılan dizini bat dosyasının olduğu yere al
cd /d %~dp0

REM Tor Scraper'ı parametrelerle çalıştır
tor-scraper.exe ^
  -targets targets.yaml ^
  -out output ^
  -proxy 127.0.0.1:9150 ^
  -workers 1 ^
  -timeout 20s ^
  -check-tor=false ^
  -screenshot=true

echo === FINISHED ===
pause
