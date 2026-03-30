import json
import csv

with open('chrome_extensions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

with open('chrome_extensions_mini.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=None, separators=(',', ':'))

with open('chrome_extensions.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'name'])
    for item in data:
        writer.writerow([item.get('id', ''), item.get('name', '')])