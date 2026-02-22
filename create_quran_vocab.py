import json
import re
import os
import sys

# Add the parent directory to the sys.path to import utils
script_dir = os.path.dirname(__file__)
sys.path.append(script_dir)
from utils import normalize_word

def create_quran_vocabulary(quran_data_path, output_vocab_path):
    """
    Extracts all unique and normalized words from the Quran data JSON file.
    """
    unique_words = set()

    try:
        with open(quran_data_path, 'r', encoding='utf-8') as f:
            quran_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Quran data file not found at {quran_data_path}")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {quran_data_path}")
        return

    # Regex to remove specific ayah end markers
    # Covers common markers like U+06DD (End of Ayah), U+FD3E, U+FD3F (Ornate brackets)
    # and the specific numeric markers U+FDFC to U+FDFF (e.g., ﰀ, ﰁ)
    ayah_end_marker_pattern = re.compile(r'[\u06DD\uFD3E\uFD3F\uFDFC-\uFDFF\u06E9\u06ED]') 

    for ayah_entry in quran_data:
        aya_text_raw = ayah_entry.get('aya_text', '')
        
        # Remove ayah end markers
        aya_text_cleaned = ayah_end_marker_pattern.sub('', aya_text_raw)
        
        # Split by any whitespace and filter out empty strings
        # This will separate words and implicitly handle punctuation not part of a word.
        words_in_ayah = [word for word in aya_text_cleaned.split() if word]
        
        for word in words_in_ayah:
            normalized = normalize_word(word)
            if normalized: # Only add non-empty normalized words
                unique_words.add(normalized)
    
    # Sort for consistency, though not strictly necessary for a set.
    sorted_words = sorted(list(unique_words))

    try:
        with open(output_vocab_path, 'w', encoding='utf-8') as f:
            json.dump(sorted_words, f, ensure_ascii=False, indent=4)
        print(f"Successfully created Quran vocabulary with {len(sorted_words)} unique words at {output_vocab_path}")
    except IOError as e:
        print(f"Error writing vocabulary file to {output_vocab_path}: {e}")

if __name__ == "__main__":
    quran_json_file = os.path.join(script_dir, "quran_minified.json")
    output_vocab_file = os.path.join(script_dir, "data", "quran_vocab.json")
    
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_vocab_file), exist_ok=True)

    create_quran_vocabulary(quran_json_file, output_vocab_file)
