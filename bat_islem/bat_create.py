import os

BAT_NAME = "run_tor_scraper.bat"

BAT_CONTENT = r"""@echo off
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
"""

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    bat_path = os.path.join(here, BAT_NAME)

    if os.path.exists(bat_path):
        print(f"[WARN] {BAT_NAME} zaten var, üzerine yazılıyor.")

    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(BAT_CONTENT)

    print(f"[OK] {BAT_NAME} oluşturuldu:")
    print(bat_path)

if __name__ == "__main__":
    main()
