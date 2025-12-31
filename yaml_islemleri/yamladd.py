# add_targets.py
from pathlib import Path

FILE_NAME = "targets.yaml"

def normalize(url: str) -> str:
    url = url.strip()
    # İstersen otomatik http:// ekleyelim
    if url and not (url.startswith("http://") or url.startswith("https://")):
        url = "http://" + url
    return url

def main():
    path = Path(FILE_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)

    print("Onion linklerini gir (bitirmek için BOŞ satır):")
    links = []

    while True:
        s = input("> ").strip()
        if s == "":
            break
        links.append(normalize(s))

    if not links:
        print("Hiç link girilmedi, çıkılıyor.")
        return

    # Dosyaya ekle (append)
    with path.open("a", encoding="utf-8") as f:
        for url in links:
            f.write(url + "\n")

    print(f"{len(links)} link {FILE_NAME} dosyasına eklendi.")

if __name__ == "__main__":
    main()
