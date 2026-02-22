import json
import os

file_path = "c:\\QuranApp\\quran_minified.json"
output_path = "c:\\QuranApp\\page_604_data.json" # Place output in workspace as well

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    page_604_data = [aya for aya in data if aya.get('page') == 604]

    with open(output_path, 'w', encoding='utf-8') as out_f:
        json.dump(page_604_data, out_f, ensure_ascii=False, indent=2)
    print(f"Page 604 data extracted to {output_path}")

except FileNotFoundError:
    print(f"Error: File not found at {file_path}")
except json.JSONDecodeError as e:
    print(f"Error decoding JSON from {file_path}: {e}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
