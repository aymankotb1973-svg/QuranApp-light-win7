# -*- coding: utf-8 -*-
"""
consolidate_quran_pages.py - A script to combine all individual page data 
into a single JSON file for faster loading.
"""

import json
import os
import glob

def consolidate_pages(input_dir, output_file):
    """
    Reads all JSON files from the input directory, consolidates them into a 
    single list, sorts them by page number, and writes to an output file.
    """
    all_pages_data = []
    # Using glob to find all json files in the directory
    json_files = glob.glob(os.path.join(input_dir, '*.json'))
    
    if not json_files:
        print(f"No JSON files found in directory: {input_dir}")
        return

    print(f"Found {len(json_files)} JSON files to process.")

    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_pages_data.append(data)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode JSON from {file_path}")
        except Exception as e:
            print(f"An error occurred while reading {file_path}: {e}")

    # Sort the pages by the 'index' key, which represents the page number
    if all_pages_data:
        all_pages_data.sort(key=lambda p: p.get('index', 0))

    # Write the consolidated data to the output file
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_pages_data, f, ensure_ascii=False, indent=4)
        print(f"Successfully consolidated all pages into {output_file}")
    except Exception as e:
        print(f"Failed to write consolidated file: {e}")

if __name__ == '__main__':
    # The directory where the 604 JSON files are located
    INPUT_DIRECTORY = r"C:\QuranApp\data\quran-pages"
    # The file path for the combined output
    OUTPUT_FILE = r"C:\QuranApp\data\consolidated_quran_pages.json"
    
    consolidate_pages(INPUT_DIRECTORY, OUTPUT_FILE)
