# -*- coding: utf-8 -*-
"""
new_quran_data_manager.py - Manages loading and accessing Quran page layout data.
"""

import json
import os
from new_utils import resource_path

class QuranDataManager:
    def __init__(self):
        self.full_page_layout_data = {}
        self.sura_pages = {}
        self.juz_pages = {}
        self.sura_aya_counts = {}
        self.all_ayas_meta = [] # Store minimal aya info for indexing

        self._load_render_data()
        self._build_indexes()

    def _load_render_data(self):
        """Loads page layout data and populates a minimal aya list for indexing."""
        mushaf_rendered_path = resource_path(os.path.join("data", "full_mushaf_pages_with_jozz.json"))
        try:
            if not os.path.exists(mushaf_rendered_path):
                print(f"!!! Comprehensive mushaf layout data file not found at {mushaf_rendered_path}. Page rendering will fail.")
                return

            with open(mushaf_rendered_path, 'r', encoding='utf-8') as f:
                loaded_pages_list = json.load(f)
            print(f"Loaded comprehensive mushaf page data for rendering from {mushaf_rendered_path}")

            self.full_page_layout_data = {page['page_number']: page for page in loaded_pages_list}
            
            # Fallback to populate aya metadata from render data for indexes
            processed_ayas = set()
            for page_num, page_data in self.full_page_layout_data.items():
                for line in page_data.get('lines', []):
                    for word in line.get('words', []):
                        sura_no = word.get('surah')
                        aya_no = word.get('ayah')
                        if sura_no and aya_no and (sura_no, aya_no) not in processed_ayas:
                            self.all_ayas_meta.append({
                                'sura_no': sura_no,
                                'aya_no': aya_no,
                                'page': page_num,
                                'juz': page_data.get('juz_number'),
                                'sura_name_ar': page_data.get('sura_name_ar')
                            })
                            processed_ayas.add((sura_no, aya_no))

        except Exception as e:
            print(f"Error loading render data: {e}")

    def _build_indexes(self):
        """Builds indexes for fast navigation."""
        for aya in self.all_ayas_meta:
            sura_no = aya.get('sura_no')
            juz_no = aya.get('juz')
            page_no = aya.get('page')
            
            if sura_no and sura_no not in self.sura_pages:
                self.sura_pages[sura_no] = page_no
            
            if juz_no and juz_no not in self.juz_pages:
                self.juz_pages[juz_no] = page_no # Note: this will only get the first page of a juz

            if sura_no:
                aya_no = int(aya.get('aya_no', 0))
                self.sura_aya_counts[sura_no] = max(self.sura_aya_counts.get(sura_no, 0), aya_no)

    def get_sura_name(self, sura_no):
        """Gets the Arabic name of a sura by its number."""
        # Find the first aya metadata that matches the sura number
        for aya in self.all_ayas_meta:
            if aya.get('sura_no') == sura_no:
                return aya.get('sura_name_ar', f"سورة {sura_no}")
        return f"سورة {sura_no}"


    def get_page_layout(self, page_num):
        """Gets the layout information (lines of words) for a given page number."""
        page_data = self.full_page_layout_data.get(page_num)
        if page_data and isinstance(page_data, dict):
            all_words_by_line = []
            for line_object in page_data.get('lines', []):
                if isinstance(line_object, dict) and 'words' in line_object:
                    all_words_by_line.append(line_object['words'])
            return all_words_by_line
        return []
    
    def get_page_metadata(self, page_num):
        """Gets metadata for a given page, such as Surah name and Juz number."""
        page_data = self.full_page_layout_data.get(page_num)
        if page_data:
            return {
                "sura_name": page_data.get("sura_name_ar"),
                "juz_number": page_data.get("juz_number"),
                "page_number": page_data.get("page_number"),
            }
        return None