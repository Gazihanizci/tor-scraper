# Tor-Scraper

Tor-Scraper, Tor ağı üzerinden hedef URL’leri tarayan ve erişilebilirlik durumlarını analiz ederek başarılı isteklerden dönen HTML içeriklerini arşivleyen bir web tarama aracıdır.

Proje, yüksek performanslı bir **Go (Golang)** tarama motoru ve kullanıcı dostu bir **Python (PyQt5)** grafik arayüzden oluşmaktadır.

---

## Özellikler
- Tor SOCKS5 proxy (127.0.0.1:9150) üzerinden anonim tarama
- Aktif / pasif URL tespiti
- HTML çıktılarının dosya olarak kaydedilmesi
- Detaylı loglama ve JSON raporlama
- Live Server benzeri lokal HTML önizleme
- Go goroutine tabanlı ölçeklenebilir yapı

---

## Kurulum

**Gereksinimler**
- Go 1.20+
- Python 3.10+
- Tor Browser

```powershell
go mod init tor-scraper
go get golang.org/x/net/proxy
go build -o tor-scraper.exe

## Kullanım
go run . -targets targets.yaml -out output -proxy 127.0.0.1:9150 -workers 1 -timeout 20s -check-tor=false
