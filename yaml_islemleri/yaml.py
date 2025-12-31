# links_to_yaml.py

links = [
    "http://vivsawnkbum46uhlqnsbzlwbsvc4yyi2o7nci6qqafuam3vqwzu652yd.onion/",
    "http://deep6xcucd2o3ubqmuhwxiq37yw3fkroiwt74icyindute5znr2zpuad.onion/product/instagram-account-hacking/",
    "http://deep6xcucd2o3ubqmuhwxiq37yw3fkroiwt74icyindute5znr2zpuad.onion/product/apple-iphone-14/",
    "http://torwikijwqskahohtn35pyfde2uqmgrxgr2fru4mn4rer5muj445dxyd.onion/the-hidden-wiki/",
    "http://torlisthsxo7h65pd2po7kevpzkk4wwf3czylz3izcmsx4jzwabbopyd.onion/",
    "http://vykenniek4sagugiayj3z32rpyrinoadduprjtdy4wharue6cz7zudid.onion/",
    "https://github.com",
    "http://hiddenwep33eg4w225lcdwcez4iefacwpiia6cwg7pfmcz4hvijzbgid.onion/index.php?title=Main_Page",
]

output_file = "targets.yaml"

with open(output_file, "w", encoding="utf-8") as f:
    for link in links:
        f.write(f"- {link}\n")

print(f"[OK] {len(links)} link '{output_file}' dosyasına yazıldı.")
