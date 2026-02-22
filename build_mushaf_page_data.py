import json
import os
from collections import defaultdict

# Assume utils.py exists in the same directory or is importable
# For now, let's define a simple resource_path
def resource_path(relative_path):
    """
    Get the absolute path to a resource, works for dev and for PyInstaller.
    This is a placeholder, adapt if the real utils.resource_path is more complex.
    """
    base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def build_mushaf_page_data():
    print("Starting to build comprehensive Mushaf page data...")

    # Define paths to input and output files
    full_mushaf_layout_path = resource_path(os.path.join("data", "full_mushaf_pages_with_jozz.json"))
    consolidated_quran_path = resource_path(os.path.join("data", "consolidated_quran_pages.json"))
    output_path = resource_path(os.path.join("data", "mushaf_pages_rendered.json"))

    # Load consolidated_quran_pages.json for sura names and aya texts
    consolidated_data = {}
    try:
        with open(consolidated_quran_path, 'r', encoding='utf-8') as f:
            raw_consolidated = json.load(f)
        for page_data in raw_consolidated:
            for aya_data in page_data.get('ayas', []):
                sura_no = aya_data.get('surah')
                aya_no = aya_data.get('aya')
                if sura_no and aya_no:
                    key = (sura_no, int(aya_no))
                    consolidated_data[key] = {
                        'sura_name_ar': aya_data.get('surahObj', {}).get('name'),
                        'aya_text': " ".join(aya_data.get('words', [])) # This might need cleaning
                    }
        print(f"Loaded {len(consolidated_data)} ayas from consolidated_quran_pages.json")
    except FileNotFoundError:
        print(f"Error: consolidated_quran_pages.json not found at {consolidated_quran_path}")
        return
    except Exception as e:
        print(f"Error loading consolidated_quran_pages.json: {e}")
        return

    # Load full_mushaf_pages_with_jozz.json as the base for rendering data
    full_mushaf_layout_data = []
    try:
        with open(full_mushaf_layout_path, 'r', encoding='utf-8') as f:
            full_mushaf_layout_data = json.load(f)
        print(f"Loaded {len(full_mushaf_layout_data)} pages from full_mushaf_pages_with_jozz.json")
    except FileNotFoundError:
        print(f"Error: full_mushaf_pages_with_jozz.json not found at {full_mushaf_layout_path}")
        return
    except Exception as e:
        print(f"Error loading full_mushaf_pages_with_jozz.json: {e}")
        return

    processed_mushaf_data = []

    for page_idx, page_data in enumerate(full_mushaf_layout_data):
        page_number = page_data.get('page_number')
        if not page_number:
            print(f"Warning: Page data at index {page_idx} missing 'page_number'. Skipping.")
            continue

        current_page_info = {
            "page_number": page_number,
            "juz_number": None, # Will be set from first word
            "surahs_on_page": defaultdict(lambda: {"start_aya": float('inf'), "end_aya": float('-inf'), "name": ""}),
            "lines": []
        }
        
        page_first_jozz = None
        page_first_sura = None
        page_first_aya = None
        page_last_sura = None
        page_last_aya = None

        all_words_on_page = [] # To determine page boundaries

        for line_data in page_data.get('lines', []):
            current_line_words = []
            for word_data in line_data.get('words', []):
                sura_no = word_data.get('surah')
                aya_no = word_data.get('ayah')
                jozz_no = word_data.get('jozz')
                word_text = word_data.get('text')
                
                if page_first_jozz is None and jozz_no is not None:
                    page_first_jozz = jozz_no
                
                if sura_no and aya_no:
                    # Update surah info for the page
                    sura_key = (sura_no, aya_no)
                    if page_first_sura is None or (sura_no < page_first_sura) or (sura_no == page_first_sura and aya_no < page_first_aya):
                        page_first_sura = sura_no
                        page_first_aya = aya_no
                    
                    if page_last_sura is None or (sura_no > page_last_sura) or (sura_no == page_last_sura and aya_no > page_last_aya):
                        page_last_sura = sura_no
                        page_last_aya = aya_no

                    # Enrich word with sura name and full aya text (if needed, currently not used directly in word)
                    enriched_word_data = word_data.copy()
                    
                    # Add sura name to page-level surahs_on_page
                    if sura_key in consolidated_data:
                        sura_name = consolidated_data[sura_key]['sura_name_ar']
                        current_page_info["surahs_on_page"][sura_no]["name"] = sura_name

                    current_page_info["surahs_on_page"][sura_no]["start_aya"] = min(
                        current_page_info["surahs_on_page"][sura_no]["start_aya"], aya_no
                    )
                    current_page_info["surahs_on_page"][sura_no]["end_aya"] = max(
                        current_page_info["surahs_on_page"][sura_no]["end_aya"], aya_no
                    )
                    
                    current_line_words.append(enriched_word_data)
                    all_words_on_page.append(enriched_word_data) # Collect all words for page boundaries

            if current_line_words:
                current_page_info["lines"].append({"words": current_line_words})
        
        # Finalize page-level info
        current_page_info["juz_number"] = page_first_jozz
        
        # Convert surahs_on_page from defaultdict to list of dicts for cleaner output
        final_surahs_on_page = []
        for sura_no, info in current_page_info["surahs_on_page"].items():
            final_surahs_on_page.append({
                "sura_no": sura_no,
                "name": info["name"],
                "start_aya": info["start_aya"],
                "end_aya": info["end_aya"]
            })
        current_page_info["surahs_on_page"] = sorted(final_surahs_on_page, key=lambda x: x["sura_no"])
        
        # Add first_sura_aya and last_sura_aya for the entire page
        current_page_info["first_sura_no"] = page_first_sura
        current_page_info["first_aya_no"] = page_first_aya
        current_page_info["last_sura_no"] = page_last_sura
        current_page_info["last_aya_no"] = page_last_aya


        processed_mushaf_data.append(current_page_info)
    
    # Save the processed data
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(processed_mushaf_data, f, ensure_ascii=False, indent=2)
        print(f"Successfully built comprehensive Mushaf page data to {output_path}")
    except Exception as e:
        print(f"Error saving processed data: {e}")

if __name__ == "__main__":
    build_mushaf_page_data()
