import json
import csv

additional_apps = [{"id": "ghbmnnjooekpmoecnnnilnnbdlolhkhi", "name": "Google Docs Offline"},
                   {"id": "nmhdhpibnnopknkmonacoephklnflpho", "name": "Unknown"},
                   {"id": "elhekieabhbkpmcefcoobjddigjcaadp", "name": "Unknown"},
                   {"id": "gmgoamodcdcjnbaobigkjelfplakmdhh", "name": "Unknown"}
                   ]

with open('chrome_extensions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

with open('chrome_extensions_mini.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=None, separators=(',', ':'))

# Sort the data by 'id' before writing to CSV
sorted_data = sorted(data, key=lambda x: x.get('id', ''))

with open('chrome_extensions.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'name'])
    for item in sorted_data:  # Use sorted_data instead of data
        writer.writerow([item.get('id', ''), item.get('name', '')])