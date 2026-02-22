# -*- coding: utf-8 -*-
"""
quran_data_manager.py - Manages loading, processing, and accessing Quran data.
"""

import json
import os
import requests
import xml.etree.ElementTree as ET
from typing import Optional, List, Tuple
from utils import (resource_path, QURAN_DATA_FILE, MINI_WORDS_DICT_FULL_FILE,
                   normalize_word, calculate_similarity, MINI_AYA_DICT_NOSH_FILE,
                   QURAN_TEXT_BY_PAGE_FILE, QURAN_META_FILE, SURAH_NAMES, QURAN_WORD_MEANINGS_FILE)
import re
from word_meaning_manager import WordMeaningManager

class QuranDataManager:
    def __init__(self):
        self.all_ayas = []
        self.aya_dict_nosh = {} # Initialize
        self.words_dict_full = [] # Initialize
        self.full_page_layout_data = {} # To store page layout with coordinates for rendering
        self.all_mushaf_words_flat = [] # NEW: Initialize all_mushaf_words_flat
        self.word_meanings_map = {} # NEW: For word meanings
        
        # Initialize WordMeaningManager for the new DB
        db_path = resource_path(os.path.join("data", "sqlite", "word-wordrasm.sqlite"))
        self.word_meaning_manager = WordMeaningManager(db_path)
        self.page_text_map = {} # NEW: لتخزين بيانات الملف الجديد
        self.titles_map = {} # NEW: Store titles map for renderer access
        
        # --- NEW: ID Mappings for Info Box ---
        self.local_to_global_map = {}
        self.global_to_db_map = {}
        self.global_to_local_map = {}

        # --- NEW: Metadata Maps ---
        self.sura_names_map = {}
        self.juz_start_map = {}
        self.rub_start_map = {}
        
        # --- FIX: Initialize State Variables BEFORE Loading Data ---
        self.pages_by_number = {}
        self.sura_pages = {}
        self.juz_pages = {}
        self.sura_aya_counts = {}
        self.sura_juz_info = {} 
        self.current_rub = 1 
        self.all_words_ordered = []
        self.word_to_global_idx = {}

        self._load_metadata_from_xml() # تحميل البيانات من ملف XML

        self._load_quran_data()
        self._load_word_meanings() # NEW

        # Load dictionaries for find_verse_by_text
        try:
            with open(MINI_AYA_DICT_NOSH_FILE, 'r', encoding='utf-8') as f:
                self.aya_dict_nosh = json.load(f)
            print(f"Loaded aya_dict_nosh from {MINI_AYA_DICT_NOSH_FILE}")
        except FileNotFoundError:
            print(f"!!! Error: {MINI_AYA_DICT_NOSH_FILE} not found. Find verse by text (exact match) will not work.")
        except json.JSONDecodeError as e:
            print(f"!!! Error decoding {MINI_AYA_DICT_NOSH_FILE}: {e}. Find verse by text (exact match) will not work.")

        try:
            with open(MINI_WORDS_DICT_FULL_FILE, 'r', encoding='utf-8') as f:
                self.words_dict_full = json.load(f)
            print(f"Loaded words_dict_full from {MINI_WORDS_DICT_FULL_FILE}")
        except FileNotFoundError:
            print(f"!!! Error: {MINI_WORDS_DICT_FULL_FILE} not found. Find verse by text (sequential match) will not work.")
        except json.JSONDecodeError as e:
            print(f"!!! Error decoding {MINI_WORDS_DICT_FULL_FILE}: {e}. Find verse by text (sequential match) will not work.")
        
        if self.all_ayas:
            self._build_indexes()

    def _load_word_meanings(self):
        """Loads word meanings from the new JSON format."""
        self.word_meanings_map = {}
        
        if not os.path.exists(QURAN_WORD_MEANINGS_FILE):
            print(f"Meanings file not found: {QURAN_WORD_MEANINGS_FILE}")
            return

        try:
            with open(QURAN_WORD_MEANINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 1. Parse the loaded data into a structured lookup
            # Key: (sura, aya), Value: List of (phrase_norm, meaning)
            temp_meanings = {}
            for key, value in data.items():
                try:
                    if ':' not in key: continue
                    sura_str, aya_str = key.split(':')
                    sura, aya = int(sura_str), int(aya_str)
                    
                    # Value format: "word: meaning | word2: meaning2"
                    segments = value.split('|')
                    for seg in segments:
                        if ':' in seg:
                            w, m = seg.split(':', 1)
                            w_norm = normalize_word(w.strip())
                            if w_norm: # Ensure not empty
                                if (sura, aya) not in temp_meanings:
                                    temp_meanings[(sura, aya)] = []
                                temp_meanings[(sura, aya)].append((w_norm, m.strip()))
                except ValueError:
                    continue

            # 2. Map to global word IDs using layout data with improved matching logic
            for page_num, page_data in self.full_page_layout_data.items():
                page_words = [word for line in page_data.get('lines', []) for word in line.get('words', [])]
                
                i = 0
                while i < len(page_words):
                    word_processed_count = 0
                    word = page_words[i]
                    sura = word.get('surah')
                    aya = word.get('ayah')
                    
                    if not sura or not aya:
                        i += 1
                        continue

                    try:
                        sura_int, aya_int = int(sura), int(aya)
                    except (ValueError, TypeError):
                        i += 1
                        continue

                    current_word_norm = normalize_word(word.get('text', ''))

                    # --- Pass 1: Strict multi-word phrase matching ---
                    if current_word_norm and (sura_int, aya_int) in temp_meanings:
                        for phrase, meaning in temp_meanings.get((sura_int, aya_int), []):
                            if phrase.startswith(current_word_norm):
                                remaining_phrase = phrase[len(current_word_norm):]
                                
                                # If it's a perfect match for a single-word phrase
                                if not remaining_phrase:
                                    w_id = word.get('word')
                                    if w_id is not None:
                                        self.word_meanings_map[(sura_int, aya_int, int(w_id))] = meaning
                                        word_processed_count = 1
                                        break

                                # Attempt to greedily match subsequent words for multi-word phrase
                                consumed_words = 1
                                temp_idx = i + 1
                                while remaining_phrase and temp_idx < len(page_words):
                                    next_word_text = page_words[temp_idx].get('text', '')
                                    next_word_norm = normalize_word(next_word_text)
                                    if not next_word_norm: # Skip empty normalized words (like formatting)
                                        temp_idx += 1
                                        consumed_words +=1
                                        continue

                                    if remaining_phrase.startswith(next_word_norm):
                                        remaining_phrase = remaining_phrase[len(next_word_norm):]
                                        consumed_words += 1
                                        temp_idx += 1
                                    else:
                                        break
                                
                                if not remaining_phrase: # Full multi-word phrase matched
                                    for j in range(consumed_words):
                                        w = page_words[i+j]
                                        w_id = w.get('word')
                                        if w_id is not None:
                                            self.word_meanings_map[(int(w.get('surah')), int(w.get('ayah')), int(w_id))] = meaning
                                    word_processed_count = consumed_words
                                    break
                    
                    if word_processed_count > 0:
                        i += word_processed_count
                        continue

                    # --- Pass 2: Lenient fallback for words not part of a successful strict match ---
                    if current_word_norm and (sura_int, aya_int) in temp_meanings:
                        word_id = word.get('word')
                        if word_id is not None:
                            for phrase, meaning in temp_meanings.get((sura_int, aya_int), []):
                                # Check if the dictionary phrase is IN the Quranic word (handles prefixes like و, ف)
                                if phrase in current_word_norm:
                                    self.word_meanings_map[(sura_int, aya_int, int(word_id))] = meaning
                                    break
                    
                    i += 1 # Move to the next word if no match was found

            print(f"Loaded and mapped {len(self.word_meanings_map)} word meanings from new JSON.")

        except Exception as e:
            print(f"Error loading word meanings: {e}")

    def _load_quran_data(self):
        """Loads both text data and rendering data from their respective files."""
        self._load_text_data()
        
        # --- NEW: Load the simple text by page file ---
        try:
            if os.path.exists(QURAN_TEXT_BY_PAGE_FILE):
                with open(QURAN_TEXT_BY_PAGE_FILE, 'r', encoding='utf-8') as f:
                    self.page_text_map = json.load(f)
                print(f"Loaded simple page text from {QURAN_TEXT_BY_PAGE_FILE}")
            else:
                print(f"Simple page text file not found at {QURAN_TEXT_BY_PAGE_FILE}")
        except Exception as e:
            print(f"Error loading simple page text: {e}")
            
        self._load_render_data()

    def _load_text_data(self):
        """Loads Quran text from the consolidated JSON file to populate all_ayas."""
        consolidated_path = resource_path(os.path.join("data", "consolidated_quran_pages.json"))
        try:
            if not os.path.exists(consolidated_path):
                print(f"!!! Consolidated data file not found at {consolidated_path}. Text search might not be optimal.")
                return

            with open(consolidated_path, 'r', encoding='utf-8') as f:
                consolidated_data = json.load(f)
            print(f"Loaded consolidated quran pages from {consolidated_path}")

            self.all_ayas = []
            sura_names = {}  # Cache for sura names
            current_rub = 1
            current_juz = 1

            for page_data in consolidated_data:
                page_no = page_data.get('index')
                for aya_data in page_data.get('ayas', []):
                    if aya_data.get('isSurahName') and 'surahObj' in aya_data:
                        sura_obj = aya_data['surahObj']
                        if sura_obj and 'id' in sura_obj and 'name' in sura_obj:
                            sura_names[sura_obj['id']] = sura_obj['name']
                        # --- NEW: استخراج معلومات الأجزاء من كائن السورة ---
                        if sura_obj and 'id' in sura_obj and 'juzas' in sura_obj:
                            self.sura_juz_info[sura_obj['id']] = sura_obj['juzas']
                        continue

                    if aya_data.get('isBasmala'):
                        continue

                    sura_no = aya_data.get('surah')
                    aya_no_str = aya_data.get('aya')

                    try:
                        aya_no = int(aya_no_str)
                        if not sura_no or aya_no < 1:
                            continue
                    except (ValueError, TypeError, AttributeError):
                        continue

                    words = aya_data.get('words', [])
                    clean_words = [re.sub('<[^<]+?>', '', w) for w in words if w and w not in ['<br>', '&nbsp;']]
                    aya_text = " ".join(clean_words)

                    # --- تحديث الجزء والربع من بيانات XML ---
                    if (sura_no, aya_no) in self.juz_start_map:
                        current_juz = self.juz_start_map[(sura_no, aya_no)]
                    
                    if (sura_no, aya_no) in self.rub_start_map:
                        current_rub = self.rub_start_map[(sura_no, aya_no)]

                    juz_no = current_juz
                    hizb_quarter = current_rub
                    
                    # استخدام اسم السورة من القائمة الثابتة أو الخريطة
                    if 1 <= sura_no <= 114:
                        sura_name = SURAH_NAMES[sura_no - 1]
                    else:
                        sura_name = sura_names.get(sura_no, f"سورة {sura_no}")

                    self.all_ayas.append({
                        "sura_no": sura_no,
                        "aya_no": aya_no,
                        "page": page_no,
                        "juz": juz_no,
                        "hizb_quarter": hizb_quarter,
                        "sura_name_ar": sura_name,
                        "aya_text": aya_text.strip(),
                        "aya_text_emlaey": aya_text.strip(),
                    })

            print(f"Populated {len(self.all_ayas)} ayas from consolidated data.")

        except Exception as e:
            print(f"Error loading consolidated text data: {e}")

    def _load_render_data(self):
        """Loads page layout data with coordinates for rendering."""
        mushaf_rendered_path = resource_path(os.path.join("data", "full_mushaf_pages_with_jozz.json"))
        try:
            if not os.path.exists(mushaf_rendered_path):
                print(f"!!! Comprehensive mushaf layout data file not found at {mushaf_rendered_path}. Page rendering will fail.")
                return

            with open(mushaf_rendered_path, 'r', encoding='utf-8') as f:
                loaded_pages_list = json.load(f)
            print(f"Loaded comprehensive mushaf page data for rendering from {mushaf_rendered_path}")

            # --- NEW: Replace word text with titles from SQLite DB ---
            # Load all titles once for performance
            self.titles_map = self.word_meaning_manager.load_all_word_titles()
            
            # --- NEW: Load ID Mappings ---
            self.local_to_global_map, self.global_to_db_map, self.global_to_local_map = self.word_meaning_manager.load_id_mappings()

            # Convert the list of pages into a dictionary indexed by page_number for O(1) lookup
            self.full_page_layout_data = {page['page_number']: page for page in loaded_pages_list}

            # [OPTIMIZATION] DISABLED: This populates a very large list in memory at startup.
            # self._build_all_mushaf_words_flat()

            # If all_ayas is empty after trying to load text data, populate it from here as a fallback.
            if not self.all_ayas:
                print("Fallback: Populating ayas from render data.")
                current_aya_words = []
                current_sura_name = ""
                
                # Helper to flush current_aya_words into self.all_ayas
                def flush_aya_data(sura_no, aya_no, page_no, juz_no):
                    nonlocal current_aya_words
                    if current_aya_words:
                        aya_text = " ".join([w['text'] for w in current_aya_words])
                        
                        # Fallback for missing sura name
                        sura_name = SURAH_NAMES[sura_no - 1] if 1 <= sura_no <= 114 else f"سورة {sura_no}"

                        # تحديد الربع والحزب (Fallback Logic)
                        if (sura_no, aya_no) in self.rub_start_map:
                            self.current_rub = self.rub_start_map[(sura_no, aya_no)]
                        hizb_quarter = self.current_rub
                        
                        self.all_ayas.append({
                            "sura_no": sura_no,
                            "aya_no": aya_no,
                            "page": page_no,
                            "juz": juz_no,
                            "hizb_quarter": hizb_quarter, # Ensure this is set!
                            "sura_name_ar": sura_name, # Use correct name
                            "aya_text": aya_text,
                            "aya_text_emlaey": aya_text, # Assuming similar for now
                        })
                        current_aya_words = []

                for page_number, page_data in self.full_page_layout_data.items():
                    page_number = page_data.get('page_number')
                    for line_data in page_data.get('lines', []):
                        for word_data in line_data.get('words', []):
                            word_sura = word_data.get('surah')
                            word_aya = word_data.get('ayah')
                            word_juz = word_data.get('juz') # Assuming juz is available at word level or can be inferred from page
                            
                            if not current_aya_words:
                                current_aya_words.append(word_data)
                            elif word_sura == current_aya_words[0].get('surah') and word_aya == current_aya_words[0].get('ayah'):
                                current_aya_words.append(word_data)
                            else:
                                flush_aya_data(
                                    current_aya_words[0].get('surah'),
                                    current_aya_words[0].get('ayah'),
                                    page_number,
                                    current_aya_words[0].get('juz', word_juz)
                                )
                                current_aya_words.append(word_data)

                # Flush any remaining aya data after loop
                if current_aya_words:
                    flush_aya_data(
                        current_aya_words[0].get('surah'),
                        current_aya_words[0].get('ayah'),
                        page_number, # Fixed argument
                        current_aya_words[0].get('juz')
                    )
                print(f"Populated {len(self.all_ayas)} ayas from fallback render data.")


        except Exception as e:
            print(f"Error loading render data: {e}")

    # def _build_all_mushaf_words_flat(self):
    #     """
    #     [OPTIMIZATION] DISABLED: This function is very memory-intensive as it creates a list of all 77,000+ words.
    #     It is replaced by an on-the-fly generation in `build_recitation_range`.
    #     """
    #     self.all_mushaf_words_flat = []
    #     # Pattern to detect if a string consists only of Arabic or Arabic-Indic numerals
    #     arabic_number_pattern = re.compile(r"^[\u0660-\u0669\u06F0-\u06F9]+$") # Arabic and Arabic-Indic numerals

    #     for page_number, page_data in self.full_page_layout_data.items():
    #         for line_data in page_data.get('lines', []):
    #             for word_data in line_data.get('words', []):
    #                 sura = word_data.get('surah')
    #                 aya = word_data.get('ayah')
    #                 word_id_from_json = word_data.get('word') # Use 'word' key as word_id
    #                 text = word_data.get('text')
    #                 
    #                 # Filter out ayah numbers (which are just numbers)
    #                 if text and not arabic_number_pattern.match(text):
    #                     self.all_mushaf_words_flat.append({
    #                         'sura': sura,
    #                         'aya': aya,
    #                         'word_id': word_id_from_json, # Store 'word' from JSON as word_id
    #                         'page_number': page_number,
    #                         'text': text,
    #                         'normalized_text': normalize_word(text)
    #                     })

    def _load_metadata_from_xml(self):
        """Loads Quran metadata (Surah names, Juzs, Hizbs) from XML."""
        # 1. Try loading from XML file first
        if os.path.exists(QURAN_META_FILE):
            try:
                tree = ET.parse(QURAN_META_FILE)
                root = tree.getroot()

                # Surah Names
                for sura in root.findall('suras/sura'):
                    idx = int(sura.get('index'))
                    name = sura.get('name')
                    self.sura_names_map[idx] = name

                # Juz Starts
                for juz in root.findall('juzs/juz'):
                    idx = int(juz.get('index'))
                    sura = int(juz.get('sura'))
                    aya = int(juz.get('aya'))
                    self.juz_start_map[(sura, aya)] = idx

                # Rub (Quarter) Starts
                for quarter in root.findall('hizbs/quarter'):
                    idx = int(quarter.get('index'))
                    sura = int(quarter.get('sura'))
                    aya = int(quarter.get('aya'))
                    self.rub_start_map[(sura, aya)] = idx

                print(f"Loaded metadata from XML: {len(self.sura_names_map)} suras, {len(self.juz_start_map)} juzs, {len(self.rub_start_map)} rubs.")
                
                # Ensure we actually loaded data, otherwise fall through to fallback
                if self.rub_start_map and self.juz_start_map:
                    return # Success

            except Exception as e:
                print(f"Error parsing metadata XML: {e}")

        # 2. Fallback: Use hardcoded/partial data if XML fails
        print("Using fallback metadata (Hardcoded/Partial).")
        
        # Fallback Rub Map (Partial list from previous code)
        starts = [
            (1,1), (2,26), (2,44), (2,60), (2,75), (2,92), (2,106), (2,124), (2,142), (2,158), 
            (2,177), (2,189), (2,203), (2,219), (2,233), (2,243), (2,253), (2,263), (2,272), (2,283),
            (3,15), (3,33), (3,52), (3,75), (3,93), (3,113), (3,133), (3,153), (3,171), (3,186),
            (4,1), (4,12), (4,24), (4,36), (4,58), (4,74), (4,88), (4,100), (4,114), (4,135), (4,148), (4,163),
            (5,1), (5,12), (5,27), (5,41), (5,51), (5,67), (5,82), (5,97),
            (6,1), (6,13), (6,36), (6,59), (6,74), (6,95), (6,111), (6,127), (6,141), (6,151),
            (7,1), (7,31), (7,47), (7,65), (7,88), (7,117), (7,142), (7,156), (7,171), (7,189),
            (8,1), (8,22), (8,41), (8,61), (9,1), (9,19), (9,34), (9,46), (9,60), (9,75), (9,93), (9,111), (9,122),
            (10,1), (10,11), (10,26), (10,53), (10,71), (10,90),
            (11,1), (11,6), (11,24), (11,41), (11,61), (11,84), (11,108),
            (12,1), (12,7), (12,30), (12,53), (12,77), (12,101),
            (13,1), (13,5), (13,19), (13,35), (14,1), (14,10), (14,28),
            (15,1), (15,49), (16,1), (16,30), (16,51), (16,75), (16,90), (16,111),
            (17,1), (17,23), (17,50), (17,70), (17,99),
            (18,1), (18,17), (18,32), (18,51), (18,75), (18,99),
            (19,1), (19,22), (19,59), (20,1), (20,55), (20,83), (20,111),
            (21,1), (21,29), (21,51), (21,83), (22,1), (22,19), (22,38), (22,60),
            (23,1), (23,36), (23,75), (24,1), (24,21), (24,35), (24,53), (25,1), (25,21), (25,53),
            (26,1), (26,52), (26,111), (26,181), (27,1), (27,27), (27,56), (27,82),
            (28,1), (28,12), (28,29), (28,51), (28,76), (29,1), (29,26), (29,46),
            (30,1), (30,31), (30,54), (31,1), (31,22), (32,1), (32,11), (33,1), (33,18), (33,31), (33,51), (33,60)
        ]
        self.rub_start_map = {k: v+1 for v, k in enumerate(starts)}




    def _build_indexes(self):
        """Builds all necessary indexes for fast data retrieval."""
        # Index ayas by page number
        for aya in self.all_ayas:
            self.pages_by_number.setdefault(aya.get('page', 1), []).append(aya)

        # Index start page for each sura from all_ayas
        for aya in self.all_ayas:
            sura_no = aya.get('sura_no')
            page_no = aya.get('page')
            if sura_no and sura_no not in self.sura_pages:
                self.sura_pages[sura_no] = page_no

        # --- تحديث: بناء فهرس صفحات الأجزاء بناءً على البيانات المحملة ---
        # إذا تمكنا من استخراج الأجزاء من الملف، نستخدمها بدلاً من القائمة الثابتة
        if self.sura_juz_info:
            self.juz_pages = {}
            # نحتاج لمعرفة الصفحة الأولى لكل جزء.
            # سنقوم بالمرور على كل الآيات، وعندما نجد آية يبدأ عندها جزء جديد، نسجل صفحتها.
            for aya in self.all_ayas:
                juz = aya.get('juz')
                page = aya.get('page')
                if juz and page and juz not in self.juz_pages:
                    self.juz_pages[juz] = page
        else:
            # Fallback if extraction failed
            self.juz_pages = {
                1: 1, 2: 22, 3: 42, 4: 62, 5: 82, 6: 102, 7: 121, 8: 142, 9: 162,
                10: 182, 11: 202, 12: 222, 13: 242, 14: 262, 15: 282, 16: 302,
                17: 322, 18: 342, 19: 362, 20: 382, 21: 402, 22: 422, 23: 442,
                24: 462, 25: 482, 26: 502, 27: 522, 28: 542, 29: 562, 30: 582
            }
        
        # --- NEW: Build page->juz mapping and retrofit into ayas ---
        self.page_to_juz = {}
        if self.juz_pages:
            # Create a list of (start_page, juz_number) and sort by page
            juz_starts = sorted([(page, juz) for juz, page in self.juz_pages.items()])
            juz_idx = 0
            if juz_starts:
                for page_num in range(1, 605): # Iterate through all pages of the Quran
                    # If we have passed the start page of the next juz, increment index
                    if juz_idx + 1 < len(juz_starts) and page_num >= juz_starts[juz_idx+1][0]:
                        juz_idx += 1
                    self.page_to_juz[page_num] = juz_starts[juz_idx][1]
        
        # Retrofit juz info into all_ayas
        if self.page_to_juz:
            for aya in self.all_ayas:
                page = aya.get('page')
                if page:
                    aya['juz'] = self.page_to_juz.get(page)
        
        # --- NEW: Retrofit Hizb/Rub info into all_ayas ---
        # ضمان تعبئة بيانات الربع والحزب لكل آية بناءً على خريطة البدايات
        if self.rub_start_map:
            current_rub = 1
            for aya in self.all_ayas:
                sura = aya.get('sura_no')
                aya_no = aya.get('aya_no')
                if (sura, aya_no) in self.rub_start_map:
                    current_rub = self.rub_start_map[(sura, aya_no)]
                aya['hizb_quarter'] = current_rub
        
        # Index total aya count for each sura
        for aya in self.all_ayas:
            sura_no = aya.get('sura_no')
            if sura_no:
                try:
                    aya_no = int(aya.get('aya_no', 0))
                    self.sura_aya_counts[sura_no] = max(self.sura_aya_counts.get(sura_no, 0), aya_no)
                except (ValueError, TypeError):
                    continue

    def get_page_layout(self, page_num):
        """
        Gets the layout information (lines, words with coordinates) for a given page number
        from the pre-loaded full mushaf data.
        """
        page_data = self.full_page_layout_data.get(page_num)
        if page_data and isinstance(page_data, dict):
            all_words_by_line = []
            for line_object in page_data.get('lines', []):
                if isinstance(line_object, dict) and 'words' in line_object:
                    all_words_by_line.append(line_object['words'])
            return all_words_by_line
        return []

    def get_sura_name(self, sura_no):
        """Gets the Arabic name of a sura by its number."""
        for aya in self.all_ayas:
            if aya.get('sura_no') == sura_no:
                return aya.get('sura_name_ar', f"سورة رقم {sura_no}")
        return f"سورة رقم {sura_no}"

    def get_ayah_text(self, sura_no, aya_no):
        """Gets the full text of a single ayah."""
        # This is not the most efficient way, but it's fine for this specific use case.
        for aya in self.all_ayas:
            if aya.get('sura_no') == sura_no and aya.get('aya_no') == aya_no:
                return aya.get('aya_text_emlaey', '')
        return ""

    def get_ayah_text_from_titles(self, sura_no, aya_no, page_num):
        """
        Constructs the ayah text by joining words from the titles_map (SQLite data).
        This ensures correct Uthmanic script rendering.
        """
        page_data = self.get_page_layout(page_num)
        words = []
        if page_data:
            for line in page_data:
                for word_item in line:
                    if word_item.get('surah') == sura_no and word_item.get('ayah') == aya_no:
                        # Use the 'word' index to fetch from titles_map
                        w_id = word_item.get('word')
                        # Fetch from titles_map using (sura, aya, word_id)
                        text = self.titles_map.get((sura_no, aya_no, w_id), word_item.get('text'))
                        if text:
                            words.append(text)
        return " ".join(words)

    def get_word_meaning(self, global_idx: str) -> Optional[str]:
        """Retrieves the meaning of a word using its global index string 's:a:w'."""
        if not global_idx:
            return None
        try:
            sura, aya, word_id = map(int, global_idx.split(':'))
            return self.word_meanings_map.get((sura, aya, word_id))
        except (ValueError, KeyError):
            return None

    def get_global_word_id_from_local(self, sura, aya, word):
        """Converts local (sura, aya, word) to global word_id (1-77432)."""
        return self.local_to_global_map.get((sura, aya, word))

    def get_db_ids_from_global(self, global_word_id):
        """Returns (sura_id, aya_id, word_id) as stored in DB for a global ID."""
        return self.global_to_db_map.get(global_word_id)

    def get_basmala_text(self):
        """Returns the text of the Basmala from Surah Al-Fatiha (1:1) using the high-quality titles map."""
        # Try to construct from titles_map (SQLite data) which is the highest quality text used in the app
        # Surah 1, Ayah 1 has 4 words.
        words = []
        for i in range(1, 5): # Words 1, 2, 3, 4
            # titles_map keys are (sura, aya, word)
            w = self.titles_map.get((1, 1, i))
            if w:
                words.append(w)
        
        if len(words) == 4:
            return " ".join(words)
            
        # Fallback
        return "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"

    def build_recitation_range(self, from_sura, from_aya, to_sura, to_aya):
        """Builds the list of words and their context for a given recitation range."""
        recitation_range_words = []
        word_page_map = []
        collecting = False
        # Pattern to detect if a string consists only of Arabic or Arabic-Indic numerals
        arabic_number_pattern = re.compile(r"^[\u0660-\u0669\u06F0-\u06F9]+$")

        # [OPTIMIZATION] Iterate through pages in order to build the range on-the-fly.
        # This avoids storing the massive all_mushaf_words_flat list in memory.
        for page_number in sorted(self.full_page_layout_data.keys()):
            page_data = self.full_page_layout_data[page_number]
            for line_data in page_data.get('lines', []):
                for word_info in line_data.get('words', []):
                    sura_no = word_info.get('surah')
                    aya_no = word_info.get('ayah')
                    text = word_info.get('text')
                    word_id = word_info.get('word') # Use 'word' key as word_id

                    # Skip invalid entries, missing word_id, or ayah markers
                    if not all([sura_no, aya_no, text]) or word_id is None or arabic_number_pattern.match(text):
                        continue

                    # Condition to start collecting
                    if not collecting and sura_no == from_sura and aya_no == from_aya:
                        collecting = True
                    
                    # Condition to stop collecting (after passing the target verse)
                    if collecting and (sura_no > to_sura or (sura_no == to_sura and aya_no > to_aya)):
                        # We have collected everything we need, return immediately.
                        return recitation_range_words, word_page_map

                    if collecting:
                        # Add word to lists
                        original_text = text
                        # The normalization now happens here, just-in-time.
                        normalized_text = normalize_word(original_text)
                        page_for_aya = page_number

                        recitation_range_words.append((original_text, normalized_text))
                        word_page_map.append((page_for_aya, sura_no, aya_no, word_id))

        return recitation_range_words, word_page_map

    def find_verse_by_text(self, text: str):
        """
        Finds all verses containing the given text snippet.
        The search is done by checking if the normalized input text is a substring of
        the normalized verse text, making it robust for partial matches.
        """
        if not text or not self.all_ayas:
            return []

        # Normalize the input text from the user
        normalized_input = normalize_word(text)
        if not normalized_input:
            return []

        matches = []
        found_verses = set()  # To avoid duplicate verses in the results

        # Iterate through all verses in the Quran
        for aya_info in self.all_ayas:
            aya_text = aya_info.get("aya_text_emlaey", "")
            if not aya_text:
                continue

            # Normalize the full text of the verse
            normalized_aya_text = normalize_word(aya_text)

            # Check if the user's input is a substring of the verse text
            if normalized_input in normalized_aya_text:
                sura_no = aya_info.get("sura_no")
                aya_no = aya_info.get("aya_no")

                # Avoid adding the same verse multiple times
                if (sura_no, aya_no) in found_verses:
                    continue
                found_verses.add((sura_no, aya_no))

                # The "similarity" is now based on the length of the match relative
                # to the verse length, which can help in ranking.
                similarity = len(normalized_input) / len(normalized_aya_text) if normalized_aya_text else 0

                matches.append({
                    "sura_no": sura_no,
                    "aya_no": aya_no,
                    "page_no": aya_info.get("page"),
                    "sura_name": aya_info.get("sura_name_ar"),
                    "similarity": similarity,
                    "text": aya_text
                })

        # Sort matches by the length of the matched text, descending.
        # Longer matches are generally more specific and likely what the user wants.
        matches.sort(key=lambda x: len(x['text']), reverse=True)
        
        if matches:
            print(f"Found {len(matches)} match(es) for '{text}'.")
        else:
            print(f"No substring match found for '{text}'.")
            
        return matches

    def get_range_for_unit(self, unit_type, unit_value):
        """
        Returns (start_sura, start_aya, end_sura, end_aya) for a given unit.
        unit_type: 'juz', 'hizb', 'rub'
        unit_value: integer value of the unit
        """
        start_aya = None
        end_aya = None
        
        # Iterate through all ayas to find start and end
        for aya in self.all_ayas:
            match = False
            if unit_type == 'juz':
                if aya.get('juz') == unit_value: match = True
            elif unit_type == 'rub':
                if aya.get('hizb_quarter') == unit_value: match = True
            elif unit_type == 'hizb':
                # Hizb is derived from Rub. 1 Hizb = 4 Rubs.
                rub = aya.get('hizb_quarter')
                if rub:
                    hizb = (rub - 1) // 4 + 1
                    if hizb == unit_value: match = True
            
            if match:
                if start_aya is None:
                    start_aya = aya
                end_aya = aya
        
        if start_aya and end_aya:
            return (start_aya['sura_no'], start_aya['aya_no'], end_aya['sura_no'], end_aya['aya_no'])
        return None

    def get_all_ayats_in_range(self, start_sura_aya: Tuple[int, int], end_sura_aya: Tuple[int, int]) -> List[Tuple[int, int]]:
        """
        Returns a list of (sura_no, aya_no) tuples for all ayahs within the specified range (inclusive).
        """
        print(f"DEBUG HIGHLIGHT: get_all_ayats_in_range called for {start_sura_aya} to {end_sura_aya}")
        if not self.all_ayas:
            print("DEBUG HIGHLIGHT: self.all_ayas is empty in get_all_ayats_in_range.")
            return []
    
        all_ayats_in_range = []
        started_collecting = False
    
        start_sura, start_aya = start_sura_aya
        end_sura, end_aya = end_sura_aya    
        for aya_info in self.all_ayas:
            current_sura = aya_info.get('sura_no')
            current_aya = aya_info.get('aya_no')
    
            if current_sura is None or current_aya is None:
                continue
    
            # Check if we should start collecting
            if not started_collecting:
                if current_sura == start_sura and current_aya == start_aya:
                    started_collecting = True
                
            # If we are collecting, add the current ayah
            if started_collecting:
                all_ayats_in_range.append((current_sura, current_aya))
                
            # Check if we should stop collecting (after adding the end ayah)
            if started_collecting: # Re-check because it might have just started
                if current_sura == end_sura and current_aya == end_aya:
                    break # Stop collecting after including the end ayah
            
        print(f"DEBUG HIGHLIGHT: Found {len(all_ayats_in_range)} ayahs in range {start_sura_aya} to {end_sura_aya}.")
        return all_ayats_in_range

    def get_global_word_id(self, page_num, surah_no, aya_no, word_id_in_aya):
        """
        Generates a unique global identifier for a word.
        """
        # The page_num is not strictly necessary for a globally unique ID if we use sura/aya/word,
        # but it can be useful for debugging or context.
        return f"{surah_no}:{aya_no}:{word_id_in_aya}"
