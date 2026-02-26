# -*- coding: utf-8 -*-
"""
utils.py - Helper functions, constants, and normalization logic for the Quran Tasmee App.
"""

import os
import sys
import ctypes # NEW: For Windows power management
import re
import json # NEW: Import json for settings management
import threading # NEW: For non-blocking sound playback
import time # NEW: For time tracking
import difflib

# --- NEW: Add ffmpeg to PATH for pydub when running standalone ---
# This helps pydub find ffmpeg, especially when running this script directly.
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle.
    if hasattr(sys, '_MEIPASS'):
        bundle_dir = sys._MEIPASS
    else:
        bundle_dir = os.path.dirname(sys.executable)
else:
    # Running in a normal Python environment
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

ffmpeg_dir_to_add = os.path.join(bundle_dir, 'ffmpeg')
if os.path.isdir(ffmpeg_dir_to_add):
    os.environ["PATH"] = ffmpeg_dir_to_add + os.pathsep + os.environ["PATH"]

# Global variables for rate-limiting sound playback
_last_error_sound_play_time = 0
_error_sound_lock = threading.Lock()

AudioSegment = None
pydub_play = None
PYDUB_AVAILABLE = False
_pydub_loaded = False

def load_pydub():
    """Lazy load pydub to speed up app startup."""
    global AudioSegment, pydub_play, PYDUB_AVAILABLE, _pydub_loaded
    if _pydub_loaded: return
    
    try:
        from pydub import AudioSegment as AS
        from pydub.playback import play as pp
        AudioSegment = AS
        pydub_play = pp
        PYDUB_AVAILABLE = True
        print("DEBUG: Pydub loaded successfully.")
        
        # Configure FFmpeg path
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                bundle_dir = sys._MEIPASS
            else:
                bundle_dir = os.path.dirname(sys.executable)
            
            ffmpeg_dir = os.path.join(bundle_dir, 'ffmpeg')
            if os.path.exists(ffmpeg_dir):
                os.environ["FFMPEG_PATH"] = ffmpeg_dir
                AudioSegment.converter = os.path.join(ffmpeg_dir, 'ffmpeg.exe')
                AudioSegment.ffprobe   = os.path.join(ffmpeg_dir, 'ffprobe.exe')
    except ImportError:
        print("!!! Pydub not found.")
        PYDUB_AVAILABLE = False
    finally:
        _pydub_loaded = True


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS # type: ignore
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

try:
    from PyQt5.QtGui import QColor
except ImportError:
    QColor = None

# --- NEW: Centralized resource paths ---
DEFAULT_FONT_SIZE = 22
DEFAULT_BG_COLOR = "#e6f2ff"

# Use resource_path to ensure files are found in both dev and PyInstaller EXE
ERROR_SOUND_PATH = resource_path(os.path.join("sounds", "error.wav"))
UTHMAN_FONT_FILE = resource_path(os.path.join("fonts", "uthmanic_hafs_v20.ttf"))
AYAH_NUMBER_FONT_FILE = resource_path(os.path.join("fonts", "uthmanic.ttf")) # <--- NEW LINE
QURAN_DATA_FILE = resource_path(os.path.join("data", "quran-data.json"))
QURAN_TEXT_BY_PAGE_FILE = resource_path(os.path.join("data", "quran_text_by_page.json"))
MINI_AYA_DICT_NOSH_FILE = resource_path(os.path.join("data", "mini_aya_dict_nosh.json"))
MINI_WORDS_DICT_FULL_FILE = resource_path(os.path.join("data", "mini_words_dict_full.json"))
QURAN_VOCAB_FILE = resource_path(os.path.join("data", "quran_vocab.json"))
QURAN_META_FILE = resource_path(os.path.join("data", "quran_meta.xml")) # مسار ملف البيانات الوصفية
QURAN_TEXT_DISPLAY_FONT_FILE = os.path.join("fonts", "trado.ttf") # Path to the default Quranic text display font.
QURAN_WORD_MEANINGS_FILE = resource_path(os.path.join("data", "words_meanings.json")) # Updated to new file

# Settings file path
if sys.platform.startswith('win'):
    # Windows: %APPDATA%/QuranApp/settings.json
    _app_data_dir = os.path.join(os.environ['APPDATA'], "QuranApp")
else:
    # Linux/macOS: ~/.config/QuranApp/settings.json
    _app_data_dir = os.path.join(os.path.expanduser('~'), '.config', "QuranApp")

# Ensure the application data directory exists
os.makedirs(_app_data_dir, exist_ok=True)

QURAN_APP_SETTINGS_FILE = os.path.join(_app_data_dir, "settings.json")

# --- NEW: Hardcoded Surah Names (Backup) ---
SURAH_NAMES = [
    "الفاتحة", "البقرة", "آل عمران", "النساء", "المائدة", "الأنعام", "الأعراف", "الأنفال", "التوبة", "يونس",
    "هود", "يوسف", "الرعد", "إبراهيم", "الحجر", "النحل", "الإسراء", "الكهف", "مريم", "طه",
    "الأنبياء", "الحج", "المؤمنون", "النور", "الفرقان", "الشعراء", "النمل", "القصص", "العنكبوت", "الروم",
    "لقمان", "السجدة", "الأحزاب", "سبأ", "فاطر", "يس", "الصافات", "ص", "الزمر", "غافر",
    "فصلت", "الشورى", "الزخرف", "الدخان", "الجاثية", "الأحقاف", "محمد", "الفتح", "الحجرات", "ق",
    "الذاريات", "الطور", "النجم", "القمر", "الرحمن", "الواقعة", "الحديد", "المجادلة", "الحشر", "الممتحنة",
    "الصف", "الجمعة", "المنافقون", "التغابن", "الطلاق", "التحريم", "الملك", "القلم", "الحاقة", "المعارج",
    "نوح", "الجن", "المزمل", "المدثر", "القيامة", "الإنسان", "المرسلات", "النبأ", "النازعات", "عبس",
    "التكوير", "الانفطار", "المطففين", "الانشقاق", "البروج", "الطارق", "الأعلى", "الغاشية", "الفجر", "البلد",
    "الشمس", "الليل", "الضحى", "الشرح", "التين", "العلق", "القدر", "البينة", "الزلزلة", "العاديات",
    "القارعة", "التكاثر", "العصر", "الهمزة", "الفيل", "قريش", "الماعون", "الكوثر", "الكافرون", "النصر",
    "المسد", "الإخلاص", "الفلق", "الناس"
]

# ---------- Settings Management ----------
def load_settings() -> dict:
    """Loads application settings from a JSON file."""
    if os.path.exists(QURAN_APP_SETTINGS_FILE):
        try:
            with open(QURAN_APP_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading settings from {QURAN_APP_SETTINGS_FILE}: {e}")
            # Fallback to default settings if loading fails
    return {} # Return empty dict if file not found or error occurred

def save_settings(settings: dict):
    """Saves application settings to a JSON file."""
    try:
        with open(QURAN_APP_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
    except IOError as e:
        print(f"Error saving settings to {QURAN_APP_SETTINGS_FILE}: {e}")


# ---------- Text Normalization ----------

# NEW: Mapping for special Quranic words (Huroof Muqatta'at)
# Maps the likely spoken/transcribed form to the actual Quranic symbol.
# This helps match speech-to-text output with the source text.
SPECIAL_WORD_MAPPINGS = {
    "الف لام ميم": "الٓمٓ",
    "الف لام ميم صاد": "الٓمٓصٓ",
    "الف لام را": "الٓر",
    "الف لام ميم را": "الٓمٓر",
    "كاف ها يا عين صاد": "كٓهيعٓصٓ",
    "طا ها": "طه",
    "طه": "طه",
    "طا سين ميم": "طسٓمٓ",
    "طا سين": "طسٓ",
    "يا سين": "يسٓ",
    "ياسين": "يسٓ",
    "صاد": "صٓ",
    "حا ميم": "حٓمٓ",
    "عين سين قاف": "عٓسٓقٓ",
    "قاف": "قٓ",
    "نون": "نٓ",
}

# Keep Madda (U+0653) for special words, but remove other diacritics.
_re_diacritics = re.compile(r'[\u0610-\u061A\u064B-\u0652\u0654-\u065F\u06D6-\u06ED\u0640]')
_re_not_arabic = re.compile(r'[^\u0600-\u06FF0-9\s]')

def normalize_word(s: str) -> str:
    """
    Normalizes an Arabic word. It first checks for special Quranic letter combinations
    (like 'Alif-Lam-Mim') and then applies general normalization rules like removing
    diacritics and unifying character forms.
    """
    if not s:
        return ""
    
    # First, do a simple clean of the input string for matching
    s_for_mapping = s.strip()
    s_for_mapping = s_for_mapping.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")

    # If the input from STT is a spelled-out version, replace it with the Quranic symbol
    # before proceeding with the full normalization. This allows both the spoken form
    # and the written form to resolve to the same normalized string.
    if s_for_mapping in SPECIAL_WORD_MAPPINGS:
        s = SPECIAL_WORD_MAPPINGS[s_for_mapping]

    # --- NEW: Explicitly replace dagger/superscript alef with regular alef ---
    s = s.replace("\u0670", "\u0627") # ٰ -> ا

    # Now, apply standard heavy normalization to whatever string we have ('s')
    s = _re_diacritics.sub("", s)
    s = _re_not_arabic.sub("", s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    s = s.replace("ة", "ه")
    s = s.replace("ى", "ي")
    s = s.replace("ـ", "") # Remove tatweel
    return "".join(s.split()) # Remove any spaces

def calculate_similarity(word1: str, word2: str) -> float:
    """Calculates the similarity between two normalized words using SequenceMatcher."""
    # Normalization is assumed to be done before calling this
    if not word1 or not word2:
        return 0.0
    return difflib.SequenceMatcher(None, word1, word2).ratio()

# --- NEW: WakeLock Class to prevent Windows Sleep ---
class WakeLock:
    """
    Prevents Windows from going to sleep while the application is active (recording or playing).
    Uses SetThreadExecutionState API.
    """
    def __init__(self):
        self.active = False

    def enable(self):
        if self.active: return
        if sys.platform == 'win32':
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED = 0x80000003
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
            self.active = True

    def disable(self):
        if not self.active: return
        if sys.platform == 'win32':
            # ES_CONTINUOUS = 0x80000000
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            self.active = False
