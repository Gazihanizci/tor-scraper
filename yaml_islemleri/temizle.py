import os
import shutil

OUTPUT_DIR = "output"

HTML_DIR = os.path.join(OUTPUT_DIR, "html")
SCREENSHOT_DIR = os.path.join(OUTPUT_DIR, "screenshots")

LOG_FILES = [
    "scan_report.log",
    "scan_summary.log",
    "scan_results.json",
]

def safe_remove_dir(path):
    if os.path.exists(path):
        for file in os.listdir(path):
            fp = os.path.join(path, file)
            if os.path.isfile(fp):
                os.remove(fp)
        print(f"[OK] Cleared directory: {path}")
    else:
        print(f"[SKIP] Directory not found: {path}")

def safe_clear_file(path):
    if os.path.exists(path):
        open(path, "w", encoding="utf-8").close()
        print(f"[OK] Cleared file: {path}")
    else:
        print(f"[SKIP] File not found: {path}")

def main():
    print("=== OUTPUT CLEANER ===")

    # HTML çıktıları temizle
    safe_remove_dir(HTML_DIR)

    # Screenshot çıktıları temizle
    safe_remove_dir(SCREENSHOT_DIR)

    # Log / JSON dosyalarını sıfırla
    for log in LOG_FILES:
        safe_clear_file(os.path.join(OUTPUT_DIR, log))

    print("=== CLEAN DONE ===")

if __name__ == "__main__":
    main()
