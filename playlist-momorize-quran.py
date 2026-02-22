# -*- coding: utf-8 -*-
"""
quran_app_canvas.py - برنامج تسميع وحفظ القرآن (PyQt5 + VLC + Vosk)
عرض صفحتين على QGraphicsScene كل كلمة مستورة بمستطيل أسود يُغيّر لونه (أخضر/أحمر شفاف)
يدعم التكبير/التصغير، استخدام خطك (C:/QuranApp/fonts/uthmanic.ttf)
يتكامل مع Vosk لو مثبت وموجود الموديل.
"""


import sys, os, json, queue, re, threading, difflib # Added difflib
from PyQt5.QtWidgets import (  # type: ignore
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFrame,
    QLabel, QSpinBox, QComboBox, QColorDialog, QFontDialog, QMessageBox, QSlider,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsPathItem, QTextEdit,
    QDialog, QFormLayout, QLineEdit, QCheckBox, QDialogButtonBox, QFileDialog, QGroupBox
)
from PyQt5.QtGui import QFont, QFontDatabase, QColor, QBrush, QPen, QPainter, QFontMetrics, QPainterPath
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, QMarginsF # type: ignore

# optional playsound for error feedback
try:
    from playsound import playsound # type: ignore
    PLAYSOUND_AVAILABLE = True
except ImportError:
    PLAYSOUND_AVAILABLE = False

# optional vosk import (may not be installed)
try: 
    from vosk import Model, KaldiRecognizer
    VOSK_INSTALLED = True
except Exception:
    Model = None
    KaldiRecognizer = None
    VOSK_INSTALLED = False

# optional sounddevice (may not be installed)
try: 
    # This explicit import can help PyInstaller find the necessary binaries
    import _sounddevice_data
    import sounddevice as sd # type: ignore
    SD_AVAILABLE = True
except Exception as e:
    print(f"Error importing sounddevice: {e}. Audio capture will be disabled.")
    sd = None
    SD_AVAILABLE = False

# NEW: Import webrtcvad for Voice Activity Detection
try:
    import webrtcvad
    VAD_AVAILABLE = True
    print("✓ مكتبة فلتر الضوضاء (webrtcvad) جاهزة.")
except ImportError:
    webrtcvad = None
    VAD_AVAILABLE = False
    print("!!! مكتبة 'webrtcvad' غير مثبتة. سيتم تعطيل فلتر الضوضاء.")

# --- تعديل: إضافة مكتبة VLC ---
try:
    # هذا الكود يفترض أن ملفات libvlc.dll, libvlccore.dll ومجلد plugins
    # موجودة في نفس مجلد البرنامج.
    import vlc
    VLC_AVAILABLE = True
    print("✓ مكتبة VLC جاهزة.")
except (ImportError, OSError) as e:
    vlc = None
    VLC_AVAILABLE = False
    print(f"!!! خطأ في تحميل مكتبة VLC: {e}\n"
          "سيتم تعطيل ميزات تشغيل الصوت. تأكد من وجود ملفات VLC في مجلد البرنامج.")
# --- نهاية التعديل ---

import time, logging # For dynamic interval timing

# Add this code at the top of quran- tasmee.py (usually after the import statements):
import os 
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# ---------- Config ----------
DEFAULT_FONT_SIZE = 17
DEFAULT_BG_COLOR = "#fffbe6" # Changed to match other apps
VOSK_MODEL_PATH = resource_path("vosk-model-ar")
UTHMAN_FONT_PATH = resource_path(os.path.join("fonts", "uthmanic.ttf"))
QURAN_DATA_PATH = resource_path("quran_minified.json")
ERROR_SOUND_PATH = resource_path("error.mp3") # Path to a short error sound


_re_diacritics = re.compile(r'[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED\u0670\u0640]')
_re_not_arabic = re.compile(r'[^\u0600-\u06FF0-9\s]')

# FIX: Improve normalization to handle common Quranic script variations.
# This is critical for matching recognized text with the source text.
def normalize_word(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    s = _re_diacritics.sub("", s) # Remove diacritics
    s = _re_not_arabic.sub("", s) # Remove non-Arabic characters
    # Unify different forms of Alef, Teh Marbuta, and Yeh
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    s = s.replace("ة", "ه")
    s = s.replace("ى", "ي")
    # Remove tatweel (the character used for justification)
    s = s.replace("ـ", "")
    return "".join(s.split())

def calculate_similarity(word1: str, word2: str) -> float:
    """Calculates the similarity between two normalized words using SequenceMatcher."""
    # Normalization is assumed to be done before calling this
    if not word1 or not word2:
        return 0.0
    return difflib.SequenceMatcher(None, word1, word2).ratio()

# ---------- Main Application ----------
class QuranCanvasApp(QWidget):
    def __init__(self):
        super().__init__() # Call the constructor of the parent class (QWidget)
        self.setWindowTitle("برنامج القرآن الكريم - التسميع بدون نت")
        
        # load font
        self.bg_color = DEFAULT_BG_COLOR
        self.current_page = 1
        self.scale_factor = 1.0

        # graphics scene/view - Initialize early to prevent resize errors
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.view.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
        self.view.setOptimizationFlag(QGraphicsView.DontSavePainterState, True)
        # use QPainter.Antialiasing for render hints
        self.view.setRenderHints(self.view.renderHints() | QPainter.Antialiasing)
        self.view.setBackgroundBrush(QBrush(QColor(self.bg_color))) # Set background color for the view

        # load font
        self._load_font()
        # basic settings - Prefer a Uthmanic / Quranic font if available
        preferred_fonts = [
            'kfgqpc_hafs_uthmanic _script',
            'UthmanicHafs',
            'Uthmani',
            'Amiri',
            'Scheherazade',
            'Noto Naskh Arabic',
            'Traditional Arabic',
            'Arabic Typesetting'
        ]
        available = set(QFontDatabase().families())
        chosen = None
        for pf in preferred_fonts:
            if pf in available:
                chosen = pf
                break
        if chosen is None:
            chosen = QFont().family()
        self.font_family = "UthmanicHafs" if "UthmanicHafs" in QFontDatabase().families() else chosen
        self.font_size = DEFAULT_FONT_SIZE
        self.page_bg_color = QColor("#FFFACD")

        # Sura & Juz maps for navigation
        self.sura_pages = {}
        self.juz_pages = {}
        self.sura_aya_counts = {} # To store aya count for each sura

        # صفحات/آيات — هنا عيّنت نماذج بسيطة، ويمكن استبدالها بقراءة ملف JSON خارجي (مثل quran_data.json)
        # تنسيق كل عنصر: {"id", "jozz", "page", "sura_no", "sura_name_ar", "aya_no", "aya_text_emlaey", "aya_text"}
        self.pages_content = self._load_quran_data()

        # build indexes
        self.pages_by_number = {}
        for aya in self.pages_content:
            self.pages_by_number.setdefault(aya.get('page',1), []).append(aya)
        self._compute_page_mappings()
        self._compute_sura_aya_counts()


        # store word items: list of dicts {rect_item, text_item, normalized}
        self.word_items = []  # for current page only (recreated on page change)

        # recognition
        self.vosk_ready = False
        self.model = None
        self.recognizer = None
        # initialize recognition only if both vosk and sounddevice are available and model exists
        if VOSK_INSTALLED and SD_AVAILABLE and os.path.exists(VOSK_MODEL_PATH):
            try:
                self._rec_queue = queue.Queue()                
                self.model = Model(model_path=VOSK_MODEL_PATH)
                self.recognizer = KaldiRecognizer(self.model, 16000)
                self.vosk_ready = True

                self._process_timer = QTimer(self)
                self._process_timer.setInterval(80)
                self._process_timer.timeout.connect(self._process_recognitions)
                self._process_timer.start()
            except Exception as e:                
                print(f"Vosk load error: {e}")
        else:
            if not VOSK_INSTALLED:
                print("مكتبة 'vosk' غير مثبتة. التسميع الصوتي معطّل.")
            elif not SD_AVAILABLE:
                print("مكتبة 'sounddevice' غير منصبة. التقاط الصوت معطّل.")
            else:
                print("Vosk model not found at", VOSK_MODEL_PATH)

        self.recording = False
        self.expected_words = []  # normalized words sequence for the page
        self.recitation_range_words = [] # Words for the selected recitation range
        self.word_pos = 0
        self._word_statuses = []
        self.recording_mode = False  # True when recording (hides ayas by default)
        self.show_hint_word = False  # Show next word hint
        self.show_aya_markers = True  # Toggle to show/hide ayas markers
        self.continuous_recitation = True # for auto page turning
        self.page_completed_waiting_for_stop = False # New flag to indicate page is done but waiting for user to stop
        self.recitation_repetitions = 1 # Total repetitions

        # For dynamic speed adjustment
        self.last_words_time = []

        # For VAD
        # FIX: Ensure VAD is initialized with a valid mode (1, 2, or 3)
        # Mode 0 is the least aggressive. We will start with this based on user feedback.
        self.vad = webrtcvad.Vad(0) if VAD_AVAILABLE else None # Start with mode 0

        self.last_partial_word_count = 0 # For handling partial results correctly
        self.live_partial_text = "" # NEW: Accumulates recognized segments for live display
        self.current_repetition = 0 # Current repetition count
        # build UI controls
        self._build_controls()
        
        # Set main layout for the window
        self.setLayout(self.main_layout)
        
        # Flag to prevent nav combo updates from fighting user input
        self._user_navigating = False
        
        # --- تعديل: إضافة متغيرات خاصة بمشغل الصوت وقوائم التشغيل ---
        self.vlc_instance = None
        self.media_player = None
        self.list_player = None
        self.event_manager = None
        self.main_audio_folder = "" # تعديل: لتخزين المجلد الرئيسي
        self.output_folder = ""
        self.files_list = []
        self.start_file = "" # تعديل: لتخزين ملف البداية
        self.end_file = ""   # تعديل: لتخزين ملف النهاية
        # --- تعديل: متغيرات جديدة للتظليل وحفظ الإعدادات ---
        self.range_start_ref = None # (sura, aya)
        self.range_end_ref = None   # (sura, aya)
        self.last_active_ayah_ref = None # (sura, aya)
        self.playlist_with_reps = [] # لتخزين القائمة مع معلومات التكرار
        self.current_playlist_index = -1
        self.AVERAGE_AYAH_DURATION_S = 7 # متوسط مدة الآية بالثواني للحساب التقديري
        self.last_estimate_mode = 'COMPLEX' # لتذكر آخر وضع تم حساب تقديره


        if VLC_AVAILABLE:
            try:
                self.vlc_instance = vlc.Instance()
                self.media_player = self.vlc_instance.media_player_new()
                self.list_player = self.vlc_instance.media_list_player_new()
                self.list_player.set_media_player(self.media_player)
                self.event_manager = self.media_player.event_manager()
                self.event_manager.event_attach(vlc.EventType.MediaPlayerMediaChanged, self.highlight_current_item)

                # Timer لتحديث شريط التقدم
                self.player_update_timer = QTimer(self)
                self.player_update_timer.setInterval(500)
                self.player_update_timer.timeout.connect(self.update_player_progress)
                self.player_update_timer.start()
            except Exception as e:
                print(f"خطأ عند تهيئة VLC: {e}")
        
        # تحميل الإعدادات عند بدء التشغيل
        # --- تعديل: تأخير تحميل الإعدادات لضمان بناء الواجهة أولاً ---
        QTimer.singleShot(100, self.load_settings)

    def on_sura_combo_changed(self, index):
        """Handles the Sura combobox value change.""" 
        sura_no = self.combo_sura.currentData() 
        if sura_no in self.sura_pages:
            target_page = self.sura_pages[sura_no]
            if self.current_page != target_page:
                self._user_navigating = True
                self.on_page_changed(target_page)
                self._user_navigating = False
                self.update_nav_combos()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-render on resize to adjust page layout
        # self.render_page(self.current_page)
        self.render_page(self.current_page)
    def _load_font(self):
        if os.path.exists(UTHMAN_FONT_PATH):
            id_ = QFontDatabase.addApplicationFont(UTHMAN_FONT_PATH)
            families = QFontDatabase.applicationFontFamilies(id_)
            if families:
                print("Loaded font families:", families)
        else:
            print("Font file not found:", UTHMAN_FONT_PATH)

    def _load_quran_data(self):        
        """Load Quran data from JSON file or use empty list if file not found.""" 
        try:
            if os.path.exists(QURAN_DATA_PATH):
                with open(QURAN_DATA_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"Loaded {len(data)} ayas from {QURAN_DATA_PATH}")
                    return data
            else:
                print(f"Quran data file not found at {QURAN_DATA_PATH}")
                return []
        except Exception as e:
            print(f"Error loading Quran data: {e}")
            return []

    def _compute_page_mappings(self):
        """Builds mappings from sura/juz to their starting pages.""" 
        self.sura_pages.clear()
        self.juz_pages.clear()
        # Use a dict to store the first page found for each sura/juz
        first_sura_page = {}
        first_juz_page = {}
        for aya in self.pages_content:
            sura_no = aya.get('sura_no')
            juz_no = aya.get('jozz')
            page_no = aya.get('page')
            if sura_no and sura_no not in self.sura_pages: self.sura_pages[sura_no] = page_no
            if juz_no and juz_no not in self.juz_pages: self.juz_pages[juz_no] = page_no

    def _compute_sura_aya_counts(self):
        """Calculates the number of ayas in each sura.""" 
        self.sura_aya_counts.clear()
        for aya in self.pages_content:
            sura_no = aya.get('sura_no')
            if sura_no:
                try:
                    aya_no = int(aya.get('aya_no', 0))
                    self.sura_aya_counts[sura_no] = max(self.sura_aya_counts.get(sura_no, 0), aya_no)
                except (ValueError, TypeError):
                    continue

    # Build UI controls     
    def _build_controls(self):
        # The main layout for the entire window will be a QVBoxLayout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)
        # --- Row 1: Navigation Controls ---
        nav_layout = QHBoxLayout()
        
        # --- تعديل: إضافة تلميحة عدد الآيات المختارة ---
        self.selected_ayah_count_label = QLabel("عدد الآيات: 0")
        self.selected_ayah_count_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.selected_ayah_count_label.setStyleSheet("color: #2ECC71; margin-left: 10px;") # اللون الأخضر
        nav_layout.addWidget(self.selected_ayah_count_label)
        # --- نهاية التعديل ---

        # --- تعديل: نقل حقل الصفحة إلى نهاية الشريط ---
        page_label = QLabel("الصفحة:")
        page_label.setFont(QFont(self.font_family, 11))
        # Use QLineEdit for page input for a cleaner look 
        self.page_input = QLineEdit(str(self.current_page))
        self.page_input.setFont(QFont("Arial", 14, QFont.Bold))
        self.page_input.setFixedWidth(60) # Set a fixed width for the input box
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.returnPressed.connect(self.on_page_input_enter)
        self.page_input.textChanged.connect(self.on_page_input_changed)
        # Sura combo
        sura_label = QLabel("السورة:")
        sura_label.setFont(QFont(self.font_family, 11))
        self.combo_sura = QComboBox()
        self.combo_sura.setFont(QFont(self.font_family, 11))
        self.combo_sura.setMinimumWidth(180)
        # Populate sura combo
        sorted_suras = sorted(self.sura_pages.items(), key=lambda item: item[1])
        for sura_no, page in sorted_suras:
            # Assuming you have a way to get sura name from number
            # For now, just use the number. You'd need a sura name map.
            sura_name = f"سورة رقم {sura_no}" # Placeholder
            for aya in self.pages_content:
                if aya.get('sura_no') == sura_no:
                    sura_name = aya.get('sura_name_ar', sura_name)
                    break
            self.combo_sura.addItem(sura_name, sura_no)
        self.combo_sura.currentIndexChanged.connect(self.on_sura_combo_changed)

        # Juz spinbox 
        juz_label = QLabel("الجزء:")
        juz_label.setFont(QFont(self.font_family, 11))
        self.spin_juz = QSpinBox()
        self.spin_juz.setRange(1, 30)
        self.spin_juz.setFont(QFont("Arial", 12))
        # Use valueChanged for arrows, editingFinished for typing.
        self.spin_juz.valueChanged.connect(self.on_juz_spin_changed)
        self.spin_juz.editingFinished.connect(self.on_juz_editing_finished)

        nav_layout.addStretch()
        nav_layout.addWidget(sura_label)
        nav_layout.addWidget(self.combo_sura)
        nav_layout.addWidget(juz_label)
        nav_layout.addWidget(self.spin_juz)
        nav_layout.addWidget(page_label)
        nav_layout.addWidget(self.page_input)
 
        # --- تعديل: إضافة تلميحات المدة وعداد التكرار ---
        nav_layout.addStretch()
        # تعديل: فصل التلميحات وتغيير الألوان
        self.duration_label = QLabel("المدة المقدرة: --:--")
        self.duration_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.duration_label.setStyleSheet("color: #3498DB; margin-right: 10px;") # اللون الأزرق

        self.repetition_label = QLabel("التكرار: -/-")
        self.repetition_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.repetition_label.setStyleSheet("color: #E74C3C; margin-right: 10px;") # اللون الأحمر

        nav_layout.addWidget(self.duration_label)
        nav_layout.addWidget(self.repetition_label)
        # --- نهاية التعديل ---


        # --- تعديل: إضافة لوحات التحكم اليمنى واليسرى ---
        # --- لوحة التحكم اليمنى (لإنشاء قوائم التشغيل) ---
        self.right_panel = QWidget()
        self.right_panel.setFixedWidth(300)
        right_layout = QVBoxLayout(self.right_panel)

        # --- تعديل: تغيير آلية اختيار المجلد والشيخ ---
        # 1. اختيار المجلد الرئيسي والشيخ
        folder_group = QGroupBox("1. اختر القارئ")
        folder_layout = QFormLayout(folder_group)
        self.btn_select_main_folder = QPushButton("اختر مجلد القراء...")
        self.btn_select_main_folder.clicked.connect(self.select_main_audio_folder)
        
        self.combo_reciters = QComboBox()
        self.combo_reciters.setEnabled(False)
        self.combo_reciters.currentIndexChanged.connect(self.on_reciter_changed)

        folder_layout.addRow(self.btn_select_main_folder)
        folder_layout.addRow("اختر الشيخ:", self.combo_reciters)
        # --- نهاية التعديل ---

        # 2. نطاق الملفات
        range_group = QGroupBox("2. حدد نطاق الحفظ")
        # --- تعديل: استخدام أزرار لاختيار الملفات ---
        range_layout = QVBoxLayout(range_group)

        start_file_layout = QHBoxLayout()
        self.btn_select_start_file = QPushButton("اختر ملف البداية")
        self.btn_select_start_file.clicked.connect(self.select_start_file)
        self.start_file_label = QLineEdit()
        self.start_file_label.setReadOnly(True)
        start_file_layout.addWidget(self.start_file_label)
        start_file_layout.addWidget(self.btn_select_start_file)

        end_file_layout = QHBoxLayout()
        self.btn_select_end_file = QPushButton("اختر ملف النهاية")
        self.btn_select_end_file.clicked.connect(self.select_end_file)
        self.end_file_label = QLineEdit()
        self.end_file_label.setReadOnly(True)

        self.btn_update_files = QPushButton("تحديث الملفات")
        self.btn_update_files.clicked.connect(self.update_files_list)
        range_layout.addLayout(start_file_layout)
        range_layout.addLayout(end_file_layout)
        range_layout.addWidget(self.btn_update_files)
        # --- نهاية التعديل ---
        # تعطيل نطاق الحفظ في البداية
        range_group.setEnabled(False)
        self.range_group = range_group # للوصول إليه لاحقاً
        end_file_layout.addWidget(self.end_file_label)
        end_file_layout.addWidget(self.btn_select_end_file)

        # 3. خيارات التكرار والتشغيل
        options_group = QGroupBox("3. اختر نظام الحفظ والتشغيل")
        options_layout = QVBoxLayout(options_group)
        self.btn_play_single = QPushButton("تشغيل فردي (للحفظ)")
        self.btn_play_single.setStyleSheet("background-color: #27ae60; color: white;")
        self.btn_play_single.clicked.connect(lambda: self.prepare_and_play("SINGLE"))
        self.btn_play_group = QPushButton("تشغيل جماعي (للمراجعة)")
        self.btn_play_group.setStyleSheet("background-color: #d68910; color: white;")
        self.btn_play_group.clicked.connect(lambda: self.prepare_and_play("GROUP"))
        self.btn_play_complex = QPushButton("تشغيل مركب (تراكمي)")
        self.btn_play_complex.setStyleSheet("background-color: #c0392b; color: white;")
        self.btn_play_complex.clicked.connect(lambda: self.prepare_and_play("COMPLEX"))
        # تعطيل أزرار التشغيل في البداية
        options_group.setEnabled(False)
        self.options_group = options_group # للوصول إليه لاحقاً
        options_layout.addWidget(self.btn_play_single)
        options_layout.addWidget(self.btn_play_group)
        options_layout.addWidget(self.btn_play_complex)

        # --- تعديل: إضافة خيارات التكرار التفصيلية ---
        repeat_group = QGroupBox("4. خيارات التكرار")
        repeat_layout = QFormLayout(repeat_group)
        
        self.spin_single_repeat = QSpinBox()
        self.spin_single_repeat.setRange(1, 100)
        self.spin_single_repeat.setValue(3)
        self.spin_single_repeat.valueChanged.connect(lambda: self.update_session_estimate('SINGLE')) # ربط التغيير
        repeat_layout.addRow("التكرار الفردي:", self.spin_single_repeat)

        self.spin_group_repeat = QSpinBox()
        self.spin_group_repeat.setRange(1, 100)
        self.spin_group_repeat.setValue(3)
        self.spin_group_repeat.valueChanged.connect(lambda: self.update_session_estimate('GROUP')) # ربط التغيير
        repeat_layout.addRow("التكرار الجماعي:", self.spin_group_repeat)

        self.spin_complex_individual = QSpinBox()
        self.spin_complex_individual.setRange(1, 100)
        self.spin_complex_individual.setValue(3)
        self.spin_complex_individual.valueChanged.connect(lambda: self.update_session_estimate('COMPLEX')) # ربط التغيير
        self.spin_complex_group = QSpinBox()
        self.spin_complex_group.setRange(1, 100)
        self.spin_complex_group.setValue(3)
        self.spin_complex_group.valueChanged.connect(self.update_session_estimate) # ربط التغيير
        self.spin_complex_group_size = QSpinBox()
        self.spin_complex_group_size.setRange(2, 100)
        self.spin_complex_group_size.setValue(3)
        self.spin_complex_group_size.valueChanged.connect(lambda: self.update_session_estimate('COMPLEX')) # ربط التغيير
        repeat_layout.addRow("مركب (فردي):", self.spin_complex_individual)
        repeat_layout.addRow("مركب (جماعي):", self.spin_complex_group)
        repeat_layout.addRow("مركب (حجم الربط):", self.spin_complex_group_size)
        # --- نهاية التعديل ---
        
        # --- تعديل: نقل المشغل الصوتي إلى اللوحة اليمنى ---
        player_group = QGroupBox("المشغل الصوتي")
        player_layout = QVBoxLayout(player_group)

        # شريط التقدم والوقت
        progress_layout = QHBoxLayout()
        self.player_current_time_label = QLabel("00:00")
        self.player_progress_slider = QSlider(Qt.Horizontal)
        self.player_total_time_label = QLabel("00:00")
        progress_layout.addWidget(self.player_current_time_label)
        progress_layout.addWidget(self.player_progress_slider)
        progress_layout.addWidget(self.player_total_time_label)

        # أزرار التحكم
        buttons_layout = QHBoxLayout()
        self.btn_player_prev = QPushButton("⏮")
        self.btn_player_prev.clicked.connect(self.player_previous)
        self.btn_player_pause = QPushButton("▶")
        self.btn_player_pause.clicked.connect(self.player_toggle_pause)
        self.btn_player_next = QPushButton("⏭")
        self.btn_player_next.clicked.connect(self.player_next)
        self.btn_player_stop = QPushButton("⏹")
        self.btn_player_stop.clicked.connect(self.player_stop)
        buttons_layout.addWidget(self.btn_player_prev)
        buttons_layout.addWidget(self.btn_player_pause)
        buttons_layout.addWidget(self.btn_player_next)
        buttons_layout.addWidget(self.btn_player_stop)

        # التحكم بالسرعة
        speed_layout = QFormLayout() # استخدام FormLayout لتنسيق أفضل
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setRange(50, 200) # يمثل 0.5x إلى 2.0x
        self.speed_slider.setValue(100)
        self.speed_slider.valueChanged.connect(self.on_speed_changed)
        self.speed_label = QLabel("x1.00")
        speed_layout.addRow("السرعة:", self.speed_slider)
        speed_layout.addRow("", self.speed_label)

        right_layout.addWidget(folder_group)
        right_layout.addWidget(range_group)
        right_layout.addWidget(options_group)
        right_layout.addWidget(repeat_group)
        right_layout.addStretch()
        player_layout.addLayout(progress_layout)
        player_layout.addLayout(buttons_layout)
        player_layout.addLayout(speed_layout)
        right_layout.addWidget(player_group) # إضافة المشغل إلى اللوحة اليمنى
        # --- نهاية التعديل ---

        # --- Noise Sensitivity Slider ---
        self.vad_label = QLabel("حساسية فلتر الضوضاء:")
        self.vad_label.setFont(QFont(self.font_family, 10))
        self.vad_slider = QSlider(Qt.Horizontal)
        self.vad_slider.setRange(0, 3)  # Represents VAD modes 0, 1, 2, 3
        self.vad_slider.setValue(0) # Default to mode 0
        self.vad_slider.valueChanged.connect(self.on_vad_slider_changed)
        self.vad_status_label = QLabel("الأقل حساسية") # New label for status
        self.vad_status_label.setFont(QFont("Arial", 10, QFont.Bold))
        # --- Center Layout (View + Side Buttons) ---
        center_layout = QHBoxLayout()
        center_layout.addWidget(self.view, 1) # The view takes up all available space
 
        # --- Main Content Layout (Side Panels + Center) ---
        main_content_layout = QHBoxLayout()
        main_content_layout.addWidget(self.right_panel) # اللوحة اليمنى
        main_content_layout.addLayout(center_layout, 1) # Center content takes priority 

        # --- تعديل: إضافة شريط سفلي لأزرار الإخفاء والإظهار ---
        bottom_toggle_layout = QHBoxLayout()
        bottom_toggle_layout.addStretch()
        self.btn_toggle_right_panel = QPushButton("إخفاء/إظهار لوحة الحفظ والمشغل")
        self.btn_toggle_right_panel.clicked.connect(lambda: self.right_panel.setVisible(not self.right_panel.isVisible()))
        self.btn_save_settings = QPushButton("حفظ الإعدادات")
        self.btn_save_settings.clicked.connect(self.save_settings)
        bottom_toggle_layout.addWidget(self.btn_save_settings)
        bottom_toggle_layout.addWidget(self.btn_toggle_right_panel)
        bottom_toggle_layout.addStretch()
        # --- نهاية التعديل ---

        # --- تجميع الواجهة النهائية ---
        self.main_layout.addLayout(nav_layout)
        # Main content area
        self.main_layout.addLayout(main_content_layout, 1)
 
        # --- NEW: Recognized Text Debug Bar ---
        self.recognized_text_container = QWidget() # Container to hold the text edit and button
        recognized_text_layout = QHBoxLayout(self.recognized_text_container)
        recognized_text_layout.setContentsMargins(0,0,0,0)
        recognized_text_layout.setSpacing(5)
 
        self.recognized_text_widget = QTextEdit()
        self.recognized_text_widget.setReadOnly(True)
        self.recognized_text_widget.setFont(QFont("Arial", 11))
        self.recognized_text_widget.setStyleSheet("background-color: #FFFFE0; color: #333; border: 1px solid #ccc; padding: 4px; border-radius: 5px;")
        self.recognized_text_widget.hide() # Initially hidden
        # Ensure word wrap is enabled (it's the default, but we make it explicit)
        self.recognized_text_widget.setLineWrapMode(QTextEdit.WidgetWidth)
        # Set a fixed height to show approx 2 lines, the rest is scrollable
        self.recognized_text_widget.setFixedHeight(60)
        self.main_layout.addWidget(self.recognized_text_widget)
 
        self.btn_copy_recognized_text = QPushButton("📋 نسخ النص")
        self.btn_copy_recognized_text.setFont(QFont(self.font_family, 10))
        self.btn_copy_recognized_text.setFixedWidth(100)
        self.btn_copy_recognized_text.clicked.connect(self._copy_recognized_text)
 
        recognized_text_layout.addWidget(self.recognized_text_widget)
        recognized_text_layout.addWidget(self.btn_copy_recognized_text)
        self.main_layout.addWidget(self.recognized_text_container)
        self.recognized_text_container.hide() # Hide the container initially

        # إضافة الشريط السفلي للواجهة
        self.main_layout.addLayout(bottom_toggle_layout)

    def clear_scene(self): 
        self.scene.clear() # Clear all items from the scene
        self.word_items = []
        # Reset expected words for the new page
        self.expected_words = []
        self._word_statuses = []

    # --- تعديل: دالة حساب المدة التقديرية ---
    def update_session_estimate(self, mode=None):
        """تحسب المدة التقديرية للجلسة وتعرضها."""
        if mode:
            self.last_estimate_mode = mode
        
        if not self.files_list:
            self.duration_label.setText("المدة المقدرة: --:--")
            self.repetition_label.setText("التكرار: -/-")
            return

        num_files = len(self.files_list)
        total_plays = 0
        mode_name = ""
        
        # حساب عدد التشغيلات لكل نوع
        if self.last_estimate_mode == 'SINGLE':
            total_plays = num_files * self.spin_single_repeat.value()
            mode_name = "فردي"
        elif self.last_estimate_mode == 'GROUP':
            total_plays = num_files * self.spin_group_repeat.value()
            mode_name = "جماعي"
        elif self.last_estimate_mode == 'COMPLEX':
            complex_individual_plays = num_files * self.spin_complex_individual.value()
            complex_group_plays = 0
            group_size = self.spin_complex_group_size.value()
            for i in range(1, num_files):
                current_group_len = min(i + 1, group_size)
                complex_group_plays += current_group_len * self.spin_complex_group.value()
            total_plays = complex_individual_plays + complex_group_plays
            mode_name = "مركب"

        # حساب المدة بالثواني
        base_duration_s = total_plays * self.AVERAGE_AYAH_DURATION_S
        
        # تعديل المدة بناءً على سرعة التشغيل
        rate = self.speed_slider.value() / 100.0
        adjusted_duration_s = base_duration_s / rate if rate > 0 else 0

        # عرضها في التلميحة
        duration_str = self.format_time(adjusted_duration_s * 1000, show_hours=True)
        self.duration_label.setText(f"المدة ({mode_name}): ~{duration_str}")
        self.repetition_label.setText("التكرار: -/-")

    # --- تعديل: إضافة دوال حفظ وتحميل الإعدادات ---
    def save_settings(self):
        """يحفظ الإعدادات الحالية في ملف JSON."""
        settings = {
            "main_audio_folder": self.main_audio_folder,
            "current_reciter": self.combo_reciters.currentText(),
            "start_file": self.start_file,
            "end_file": self.end_file,
            "single_repeat": self.spin_single_repeat.value(),
            "group_repeat": self.spin_group_repeat.value(),
            "complex_individual": self.spin_complex_individual.value(),
            "complex_group": self.spin_complex_group.value(),
            "complex_group_size": self.spin_complex_group_size.value(),
        }
        try:
            with open("settings.json", "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"فشل حفظ الإعدادات: {e}")

    def load_settings(self):
        """يحمل الإعدادات من ملف JSON عند بدء التشغيل."""
        try:
            if os.path.exists("settings.json"):
                with open("settings.json", "r", encoding="utf-8") as f:
                    settings = json.load(f)

                # استعادة قيم التكرار
                self.spin_single_repeat.setValue(settings.get("single_repeat", 3))
                self.spin_group_repeat.setValue(settings.get("group_repeat", 3))
                self.spin_complex_individual.setValue(settings.get("complex_individual", 3))
                self.spin_complex_group.setValue(settings.get("complex_group", 3))
                self.spin_complex_group_size.setValue(settings.get("complex_group_size", 3))

                # استعادة المجلد والشيخ
                main_folder = settings.get("main_audio_folder")
                if main_folder and os.path.isdir(main_folder):
                    self.main_audio_folder = main_folder
                    subfolders = [f.name for f in os.scandir(main_folder) if f.is_dir()]
                    if subfolders:
                        self.combo_reciters.addItems(subfolders)
                        self.combo_reciters.setEnabled(True)
                        current_reciter = settings.get("current_reciter")
                        if current_reciter in subfolders:
                            self.combo_reciters.setCurrentText(current_reciter)
                        self.on_reciter_changed() # تفعيل باقي الواجهة

                # استعادة ملفات البداية والنهاية
                self.start_file = settings.get("start_file", "")
                self.end_file = settings.get("end_file", "")
                self.start_file_label.setText(self.start_file)
                self.end_file_label.setText(self.end_file)
        except Exception as e:
            print(f"فشل تحميل الإعدادات: {e}")

    # --- تعديل: إضافة دوال المشغل وقوائم التشغيل ---
    def select_main_audio_folder(self):
        """يفتح نافذة لاختيار المجلد الرئيسي الذي يحتوي على مجلدات القراء."""
        folder = QFileDialog.getExistingDirectory(self, "اختر المجلد الرئيسي الذي يحتوي على القراء")
        if folder:
            self.main_audio_folder = folder
            # --- تعديل: تغيير اسم الزر ليعكس اسم المجلد المختار ---
            self.btn_select_main_folder.setText(os.path.basename(folder))
            self.combo_reciters.clear()
            self.combo_reciters.setEnabled(False)
            self.range_group.setEnabled(False)
            self.options_group.setEnabled(False)

            try:
                subfolders = [f.name for f in os.scandir(folder) if f.is_dir()]
                if subfolders:
                    self.combo_reciters.addItems(subfolders)
                    self.combo_reciters.setEnabled(True)
                    self.on_reciter_changed() # تفعيل أول شيخ في القائمة تلقائياً
                else:
                    QMessageBox.warning(self, "مجلد فارغ", "المجلد المختار لا يحتوي على أي مجلدات فرعية (قراء).")
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"لا يمكن قراءة المجلدات الفرعية: {e}")

    def on_reciter_changed(self):
        """يتم استدعاؤها عند اختيار شيخ من القائمة المنسدلة."""
        reciter_name = self.combo_reciters.currentText()
        if self.main_audio_folder and reciter_name:
            folder = os.path.join(self.main_audio_folder, reciter_name)
            self.output_folder = folder
            self.range_group.setEnabled(True)
            self.options_group.setEnabled(True)

    def select_start_file(self):
        """يفتح نافذة لاختيار ملف البداية."""
        file_path, _ = QFileDialog.getOpenFileName(self, "اختر ملف البداية", self.output_folder, "Audio Files (*.mp3)")
        if file_path:
            self.start_file = os.path.basename(file_path)
            self.start_file_label.setText(self.start_file)
            # --- تعديل: الانتقال إلى صفحة آية البداية ---
            try:
                sura_no = int(self.start_file[0:3])
                ayah_no = int(self.start_file[3:6])
                target_page = None
                for aya in self.pages_content:
                    if aya.get('sura_no') == sura_no and int(aya.get('aya_no', 0)) == ayah_no:
                        target_page = aya.get('page')
                        break
                if target_page:
                    self.on_page_changed(target_page)
            except Exception as e:
                print(f"فشل الانتقال إلى الصفحة: {e}")

    def select_end_file(self):
        """يفتح نافذة لاختيار ملف النهاية."""
        file_path, _ = QFileDialog.getOpenFileName(self, "اختر ملف النهاية", self.output_folder, "Audio Files (*.mp3)")
        if file_path:
            self.end_file = os.path.basename(file_path)
            self.end_file_label.setText(self.end_file)

    def update_files_list(self):
        self.files_list.clear()
        try:
            if not self.start_file or not self.end_file:
                QMessageBox.warning(self, "خطأ", "الرجاء اختيار ملف البداية وملف النهاية أولاً.")
                return

            # --- تعديل: قراءة الملفات بين ملفي البداية والنهاية ---
            all_files = sorted([f for f in os.listdir(self.output_folder) if f.endswith('.mp3')])
            
            try:
                start_index = all_files.index(self.start_file)
                end_index = all_files.index(self.end_file)
            except ValueError:
                QMessageBox.critical(self, "خطأ", "لم يتم العثور على الملفات المختارة في مجلد الشيخ.")
                return

            if start_index > end_index:
                QMessageBox.warning(self, "خطأ", "ملف البداية يجب أن يكون قبل ملف النهاية.")
                return

            self.files_list = all_files[start_index : end_index + 1]
            
            # --- تعديل: تخزين مراجع آيات البداية والنهاية للتظليل ---
            self.range_start_ref = (int(self.start_file[0:3]), int(self.start_file[3:6]))
            self.range_end_ref = (int(self.end_file[0:3]), int(self.end_file[3:6]))
            # إعادة رسم الصفحة لتطبيق تظليل النطاق
            self.render_page(self.current_page)
            # --- نهاية التعديل ---
            # --- تعديل: تحديث المدة المقدرة ---
            self.update_session_estimate()
            # --- نهاية التعديل ---
            # --- تعديل: تحديث تلميحة عدد الآيات ---
            self.selected_ayah_count_label.setText(f"عدد الآيات: {len(self.files_list)}")
            # --- نهاية التعديل ---
            QMessageBox.information(self, "تم", f"تم تحديد {len(self.files_list)} ملف.")
        except ValueError:
            QMessageBox.warning(self, "خطأ", "أدخل أرقام صحيحة.")

    def create_playlist_content(self, type_):
        playlist = []
        # يمكنك إضافة منطق التكرار هنا إذا أردت
        self.playlist_with_reps.clear() # تفريغ القائمة الموسعة
        # --- تعديل: استخدام قيم التكرار من الواجهة ---
        try:
            if type_ == "SINGLE":
                repeat = self.spin_single_repeat.value()
                for file in self.files_list:
                    for i in range(repeat):
                        self.playlist_with_reps.append({'file': file, 'rep': i + 1, 'total_reps': repeat})
            elif type_ == "GROUP":
                repeat_group = self.spin_group_repeat.value()
                for i in range(repeat_group):
                    for file in self.files_list:
                        self.playlist_with_reps.append({'file': file, 'rep': i + 1, 'total_reps': repeat_group})
            elif type_ == "COMPLEX":
                repeat_individual = self.spin_complex_individual.value()
                repeat_group = self.spin_complex_group.value()
                group_size = self.spin_complex_group_size.value()
                for i, file in enumerate(self.files_list):
                    for j in range(repeat_individual):
                        self.playlist_with_reps.append({'file': file, 'rep': j + 1, 'total_reps': repeat_individual})
                    if i > 0:
                        start_index = max(0, i - (group_size - 1))
                        group_files = self.files_list[start_index:i+1]
                        for j in range(repeat_group):
                            for group_file in group_files:
                                self.playlist_with_reps.append({'file': group_file, 'rep': j + 1, 'total_reps': repeat_group})
            
            playlist = [item['file'] for item in self.playlist_with_reps]
            return playlist
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ عند إنشاء القائمة: {e}")
            return None

    def prepare_and_play(self, type_):
        """دالة وسيطة لتحديث تقدير الوقت قبل التشغيل."""
        # تحديث تقدير الوقت ليعكس النوع الذي سيتم تشغيله
        self.update_session_estimate(type_)
        self.play_playlist_internal(type_)

    def play_playlist_internal(self, type_):
        if not self.files_list or not self.output_folder:
            QMessageBox.warning(self, "خطأ", "اختر نطاق الملفات ومجلد الحفظ أولاً.")
            return
        if not self.list_player:
            QMessageBox.critical(self, "خطأ VLC", "مشغل القوائم غير جاهز.")
            return

        playlist_content = self.create_playlist_content(type_)
        if not playlist_content: return

        self.current_playlist_index = -1 # إعادة تعيين عداد القائمة
        media_list = self.vlc_instance.media_list_new([os.path.join(self.output_folder, f) for f in playlist_content])
        self.list_player.set_media_list(media_list)
        self.list_player.play()
        self.btn_player_pause.setText("❚❚")

    def highlight_current_item(self, event):
        if not self.media_player: return
        media = self.media_player.get_media()
        if not media: return

        self.current_playlist_index += 1 # زيادة عداد القائمة
        try:
            file_name = os.path.basename(media.get_mrl()) # e.g., "001002.mp3"
            sura_num = int(file_name[0:3])
            ayah_num = int(file_name[3:6])
            current_ayah_ref = (sura_num, ayah_num)

            # --- تعديل: منطق التظليل المتحرك ---
            # 1. إزالة التظليل النشط السابق
            if self.last_active_ayah_ref:
                self.apply_highlight_to_ayah(self.last_active_ayah_ref, QColor(0,0,0,0)) # إزالة التظليل

            # 2. إعادة تطبيق تظليل النطاق (لأن الخطوة السابقة قد تكون أزالته)
            self.apply_highlight_to_ayah(self.range_start_ref, QColor(173, 216, 230, 180)) # أزرق فاتح
            self.apply_highlight_to_ayah(self.range_end_ref, QColor(173, 216, 230, 180))   # أزرق فاتح

            # 3. تطبيق التظليل النشط الجديد
            self.apply_highlight_to_ayah(current_ayah_ref, QColor(255, 255, 0, 150)) # أصفر

            # 4. تحديث مرجع الآية النشطة
            self.last_active_ayah_ref = current_ayah_ref

            # --- تعديل: تحديث عداد التكرار ---
            if 0 <= self.current_playlist_index < len(self.playlist_with_reps):
                info = self.playlist_with_reps[self.current_playlist_index]
                current_rep = info['rep']
                total_reps = info['total_reps']
                self.repetition_label.setText(f"التكرار: {current_rep}/{total_reps}")
            # --- نهاية التعديل ---

        except Exception as e:
            print(f"Error highlighting item: {e}")

    def apply_highlight_to_ayah(self, ayah_ref, color):
        """يطبق لون معين على كل كلمات آية محددة."""
        if not ayah_ref: return
        sura_num, ayah_num = ayah_ref
        for wi in self.word_items:
            if wi.get('sura_no') == sura_num and wi.get('aya_no') == ayah_num:
                wi['rect'].setBrush(QBrush(color))

    def player_toggle_pause(self):
        if not self.media_player: return
        if self.media_player.is_playing():
            self.media_player.pause()
            self.btn_player_pause.setText("▶")
        else:
            self.media_player.play()
            self.btn_player_pause.setText("❚❚")

    def player_next(self):
        if self.list_player: self.list_player.next()

    def player_previous(self):
        if self.list_player: self.list_player.previous()

    def player_stop(self):
        """يوقف قائمة التشغيل تمامًا."""
        if self.list_player:
            self.list_player.stop()
            self.btn_player_pause.setText("▶")
            # إزالة كل التظليلات عند الإيقاف
            self.range_start_ref = self.range_end_ref = self.last_active_ayah_ref = None
            self.repetition_label.setText("التكرار: -/-")
            self.render_page(self.current_page)

    def on_speed_changed(self, value):
        """يتم استدعاؤها عند تغيير مؤشر السرعة."""
        self.set_playback_rate(value)
        self.update_session_estimate() # إعادة حساب المدة المقدرة

    def set_playback_rate(self, value):
        if not self.media_player: return
        rate = value / 100.0
        self.media_player.set_rate(rate)
        self.speed_label.setText(f"x{rate:.2f}")

    def format_time(self, ms, show_hours=False):
        if ms < 0: return "--:--" if not show_hours else "--:--:--"
        seconds = ms // 1000
        mins, secs = divmod(seconds, 60)
        if show_hours:
            hours, mins = divmod(mins, 60)
            return f"{int(hours):02}:{int(mins):02}:{int(secs):02}"
        return f"{int(mins):02}:{int(secs):02}"

    def update_player_progress(self):
        if not self.media_player or not self.media_player.is_playing():
            return

        position = self.media_player.get_position()
        self.player_progress_slider.blockSignals(True)
        self.player_progress_slider.setValue(int(position * 1000))
        self.player_progress_slider.blockSignals(False)

        current_time = self.media_player.get_time()
        total_time = self.media_player.get_length()
        self.player_current_time_label.setText(self.format_time(current_time))
        self.player_total_time_label.setText(self.format_time(total_time))

    def _update_font_sizes(self):
        for wi in self.word_items:
            wi['text'].setFont(QFont(self.font_family, int(self.font_size * self.scale_factor)))

    # --- نهاية دوال المشغل ---

    def render_page(self, page_no: int):
        """Display two pages side-by-side: the current page on the right, next page on the left. 
        Scene size adjusts dynamically to fit content."""
        self.clear_scene()
        
        # Display two pages: current (right side) and next (left side)
        page_left, page_right = page_no + 1, page_no        
        
        # Dynamic frame calculation based on view size
        view_size = self.view.viewport().size() 
        frame_margin = 10 # تقليل الهامش لزيادة طول الصفحة
        # Calculate width based on height to maintain aspect ratio (e.g., 1.4 ratio for height/width)
        frame_height_min = view_size.height() - (frame_margin * 2)
        frame_width = frame_height_min / 1.15 # تعديل النسبة لجعل الصفحة أعرض قليلاً
        
        # Render right page (current page) - RTL positioning (right side)        
        right_x = frame_margin * 2 + frame_width
        y_start = frame_margin
        left_x = frame_margin
        
        # Render both pages and get their required heights
        right_height = self._render_single_page(page_right, right_x, y_start, frame_width, frame_height_min, is_right=True)
        left_height = self._render_single_page(page_left, left_x, y_start, frame_width, frame_height_min, is_right=False)
        
        # Calculate total scene dimensions        
        max_height = max(right_height, left_height)
        scene_width = frame_margin * 3 + frame_width * 2
        scene_height = max_height + frame_margin * 2
        
        # Set scene rect to accommodate all content and fit it
        self.scene.setSceneRect(0, 0, scene_width, scene_height)

    def _render_single_page(self, page_no: int, x_start: float, y_start: float, width: float, height_min: float, is_right: bool):
        """Render a single page in the given region with a frame. Returns the actual height used."""         
        # --- ارسم إطارًا هندسيًا مخصصًا ---
        path = QPainterPath()
        corner_radius = 20  # يمكنك تعديل حجم تقوس الزاوية من هنا

        # ابدأ من الزاوية العلوية اليمنى
        path.moveTo(x_start + width - corner_radius, y_start)
        # ارسم خطًا إلى الزاوية العلوية اليسرى
        path.lineTo(x_start + corner_radius, y_start)
        # ارسم القوس للزاوية العلوية اليسرى
        path.arcTo(x_start, y_start, corner_radius * 2, corner_radius * 2, 90, 90)
        # ارسم خطًا إلى الزاوية السفلية اليسرى
        path.lineTo(x_start, y_start + height_min - corner_radius)
        # ارسم القوس للزاوية السفلية اليسرى
        path.arcTo(x_start, y_start + height_min - (corner_radius * 2), corner_radius * 2, corner_radius * 2, 180, 90)
        # ارسم خطًا إلى الزاوية السفلية اليمنى
        path.lineTo(x_start + width - corner_radius, y_start + height_min)
        # ارسم القوس للزاوية السفلية اليمنى
        path.arcTo(x_start + width - (corner_radius * 2), y_start + height_min - (corner_radius * 2), corner_radius * 2, corner_radius * 2, 270, 90)
        # ارسم خطًا للعودة إلى الزاوية العلوية اليمنى
        path.lineTo(x_start + width, y_start + corner_radius)
        # ارسم القوس الأخير وأغلق الشكل
        path.arcTo(x_start + width - (corner_radius * 2), y_start, corner_radius * 2, corner_radius * 2, 0, 90)
        path.closeSubpath()

        frame_item = QGraphicsPathItem(path)
        # حدد لون وسُمك الإطار (أخضر، سُمك 3 بكسل)
        frame_item.setPen(QPen(QColor("#006400"), 3))  # DarkGreen
        frame_item.setBrush(QBrush(self.page_bg_color))  # لون خلفية الصفحة الداخلية
        self.scene.addItem(frame_item)
             
        ayas = self.pages_by_number.get(page_no, [])
        if not ayas:
            # Empty page
            txt = QGraphicsTextItem("لا توجد آيات")
            txt.setDefaultTextColor(QColor("#999"))
            txt.setFont(QFont(self.font_family, 14))
            txt.setPos(x_start + width/2 - 40, y_start + height_min/2)
            self.scene.addItem(txt)
            return y_start + height_min
 
        # Page margins inside frame
        inner_margin = 10  # Reduced to give more space for content
        content_x = x_start + inner_margin
        content_y = y_start + inner_margin
        content_width = width - inner_margin * 2
        # Line spacing includes font size + extra padding that scales with zoom
        # This prevents overlapping when text is enlarged
        line_spacing = int(self.font_size * self.scale_factor * 1.8) # زيادة التباعد بين السطور
 
        # Decide whether this page starts with a sura that needs the Basmala.
        # If so, render the Basmala as a separate centered line at the top of the
        # page content area (this matches the Mushaf behaviour and avoids
        # injecting an empty/extra line in the wrapped text flow).
        insert_basmala = False
        if ayas:
            first_aya = ayas[0]
            try:
                first_aya_no = int(first_aya.get('aya_no', 0))
                first_sura_no = int(first_aya.get('sura_no', 0))
            except Exception:
                first_aya_no = 0
                first_sura_no = 0
            if first_aya_no == 1 and first_sura_no != 9:
                insert_basmala = True
 
        if insert_basmala:
            basmala_text = 'بسم الله الرحمن الرحيم'
            basmala_font = QFont(self.font_family, int(self.font_size * self.scale_factor * 1.15), QFont.Bold)
            basmala_item = QGraphicsTextItem(basmala_text)
            basmala_item.setFont(basmala_font)
            basmala_item.setDefaultTextColor(QColor("#000000"))
            basmala_w = basmala_item.boundingRect().width()
            basmala_h = basmala_item.boundingRect().height()
            basmala_item.setPos(x_start + (width - basmala_w) / 2, content_y)
            basmala_item.setZValue(2)
            self.scene.addItem(basmala_item)
            # تعديل المسافة بعد البسملة لجعلها أقل
            content_y += basmala_h + (line_spacing * 0.5) # إضافة نصف مسافة السطر فقط
         
        # Build token list from ayas: words, optional basmala insertions, and aya markers
        tokens = []
        last_sura_no = None
        for aya in ayas:
            try:
                current_sura = int(aya.get('sura_no', 0))
            except Exception:
                current_sura = 0
 
            text_raw = aya.get("aya_text", aya.get("aya_text_emlaey", ""))
            
            # If this aya is the first in a new sura (and not sura 1 or 9), insert basmala
            try:
                aya_no = int(aya.get('aya_no', 0))
            except (ValueError, TypeError):
                aya_no = 0
            if last_sura_no is not None and current_sura != last_sura_no:
                if aya_no == 1 and current_sura not in (1, 9) and not text_raw.startswith("بسم الله الرحمن الرحيم"):
                    tokens.append(("بسم الله الرحمن الرحيم", "basmala"))
             
            parts = text_raw.split()
            for p in parts:
                if not normalize_word(p):
                    continue
                if re.match(r'^[\(\)\u0030-\u0039\u0660-\u0669\u06F0-\u06F9]+$', p):
                    continue
                tokens.append((p, False))

            if self.show_aya_markers:             
                tokens.append((str(aya.get('aya_no', '')), "aya_marker"))

            last_sura_no = current_sura
 
        # Build lines with wrapping
        temp_font = QFont(self.font_family, int(self.font_size * self.scale_factor))
        fm = QFontMetrics(temp_font)
 
        lines = []        
        line = []
        line_w = 0
        wrap_width = content_width
        for tok, is_marker in tokens:
            # Handle empty line for spacing
            if is_marker == "empty_line":
                if line:
                    lines.append(line)
                lines.append([("", "empty_line", 0)])
                line = []
                line_w = 0
                continue
            # Special handling for Basmala to ensure it's on its own line
            if is_marker == "basmala":
                if line: # End the current line before the basmala
                    lines.append(line)
                lines.append([(tok, "basmala", 0)]) # Add basmala as a separate line
                line = []
                line_w = 0
                continue

            tok_w = fm.horizontalAdvance(tok) + 8
            if line and (line_w + tok_w) > wrap_width:
                lines.append(line)
                line = [(tok, is_marker, tok_w)]
                line_w = tok_w
            else:
                line.append((tok, is_marker, tok_w))
                line_w += tok_w
        if line:
            lines.append(line)
 
        # Render lines
        y = content_y
        for line in lines:
            if not line:
                y += line_spacing
                continue
 
            line_total_width = sum(tok_w for _, _, tok_w in line)
            # Place tokens right-to-left: start at the right edge and move left.
            cur_x = x_start + width - inner_margin
 
            word_index_in_line = 0
            for token_text, is_marker, tok_w in line:  # Draw tokens in order (not reversed)
                rect_w = tok_w
                # Match rect height to line spacing so no text overlaps between lines
                rect_h = int(self.font_size * self.scale_factor * 1.8) # تعديل ارتفاع المستطيل ليتناسب مع التباعد
                
                if is_marker == "aya_marker":
                    # Draw a circular aya marker and place the verse number inside it
                    num = str(token_text)
                    # size of the circle (based on font size and scale)
                    marker_d = max(12, int(self.font_size * self.scale_factor * 1.1))
                    padding = 6
                    marker_w = marker_d + padding
                    # move cursor left by marker width
                    cur_x -= marker_w                    
 
                    ellipse_x = cur_x + int(padding/2)
                    ellipse_y = y + (rect_h - marker_d) / 2
                    ellipse = QGraphicsEllipseItem(ellipse_x, ellipse_y, marker_d, marker_d)
                    ellipse.setBrush(QBrush(QColor("#8B4513")))
                    ellipse.setPen(QPen(QColor("#8B4513")))
                    ellipse.setZValue(1)
                    self.scene.addItem(ellipse)
 
                    # number text centered inside ellipse
                    num_item = QGraphicsTextItem(num)
                    num_item.setDefaultTextColor(QColor("#ffffff"))
                    num_font = QFont(self.font_family, max(8, int(self.font_size * self.scale_factor * 0.65)))
                    num_item.setFont(num_font)
                    nb = num_item.boundingRect()
                    num_x = ellipse_x + (marker_d - nb.width()) / 2
                    num_y = ellipse_y + (marker_d - nb.height()) / 2 - 1
                    num_item.setPos(num_x, num_y)
                    num_item.setZValue(2)
                    self.scene.addItem(num_item)
                elif is_marker == "empty_line":
                    # This is just for spacing, do nothing visually
                    pass
                elif is_marker == "basmala":
                    # Render Basmala centered on its own line
                    basmala_font = QFont(self.font_family, int(self.font_size * self.scale_factor * 1.15), QFont.Bold)
                    basmala_item = QGraphicsTextItem(token_text)
                    basmala_item.setFont(basmala_font)
                    basmala_item.setDefaultTextColor(QColor("#000000"))
                    basmala_w = basmala_item.boundingRect().width()
                    basmala_h = basmala_item.boundingRect().height()
                    # إضافة هامش علوي قبل البسملة
                    y += line_spacing * 0.5
                    # Center it within the page width
                    basmala_item.setPos(x_start + (width - basmala_w) / 2, y)
                    basmala_item.setZValue(2)
                    self.scene.addItem(basmala_item)
                    # زيادة y بمقدار ارتفاع البسملة مع هامش سفلي لمنع التداخل
                    y += basmala_h + (line_spacing * 0.5)
                else:
                    # move cursor left by token width to position this token
                    cur_x -= rect_w
                     
                    # Draw rectangle and text (word background toggled by recording mode)
                    rect_item = QGraphicsRectItem(cur_x, y, rect_w, rect_h)
                    rect_item.setPen(QPen(Qt.NoPen))
                    # The rectangle is now always transparent initially.
                    # Its color will be set only when a word is marked as correct or incorrect.
                    rect_item.setBrush(QBrush(QColor(0, 0, 0, 0)))
                    rect_item.setZValue(1) # Above page bg, below text

                    text_item = QGraphicsTextItem(token_text) 
                    text_item.setDefaultTextColor(QColor("#000000"))
                    text_font = QFont(self.font_family, int(self.font_size * self.scale_factor))
                    text_item.setFont(text_font)

                    # In recording mode, make the text itself invisible (transparent) 
                    # The colored rect behind it will show the status.
                    if self.recording_mode:
                        # Make text transparent, but it's still there for layout
                        text_item.setDefaultTextColor(QColor(0,0,0,0))
                    else:
                        text_item.setDefaultTextColor(QColor("#000000"))

                    text_item.setPos(cur_x + 4, y + (rect_h - text_item.boundingRect().height()) / 2 - 2)
                    text_item.setZValue(2) # Above rect
 
                    self.scene.addItem(rect_item)                    
                    self.scene.addItem(text_item)
 
                    # Track words for recognition (only normal word tokens)
                    if is_marker is False:
                        nw = normalize_word(token_text)
                        if nw:
                            idx = len(self.word_items)
                            self.word_items.append({
                                    'rect': rect_item,
                                    'text': text_item,
                                    'norm': nw,
                                    'idx': idx,
                                    # إضافة معلومات الآية والسورة لكل كلمة
                                    'sura_no': aya.get('sura_no'),
                                    'aya_no': int(aya.get('aya_no', 0))
                            })
                        word_index_in_line += 1
 
            # زيادة y للسطر التالي، إلا إذا كان السطر يحتوي على بسملة (لأننا عالجنا ارتفاعها بالفعل)
            is_basmala_line = any(is_marker == "basmala" for _, is_marker, _ in line)
            if not is_basmala_line:
                y += line_spacing

        # (Rendering continues...) - recording start logic moved to `start_recording` 
        # Return the absolute bottom Y used by this page (ensure at least the
        # minimum frame height is reported). This lets the caller compute the
        # scene height correctly.
        bottom_y = max(y + inner_margin, y_start + height_min)
        return bottom_y

    def stop_recording(self):
        """Stops the recording and processing immediately."""
        if not self.recording:
            return

        # Immediately stop all recording and processing flags
        self.recording = False
        self.recording_mode = False  # Disable recording mode (show ayas)
        self.show_hint_word = False  # Reset hint

        # --- CRITICAL FIX: Process remaining audio before getting final result --- 
        # First, stop the audio stream to prevent new data from coming in.
        if hasattr(self, 'audio_stream') and self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception as e:
                logging.debug(f"Error closing audio stream: {e}")
        self.audio_stream = None

        # Stop the timer that processes the queue
        if hasattr(self, '_process_timer'):
            self._process_timer.stop()

        # Clear any remaining items in the queue
        while not self._rec_queue.empty():
            try:
                self._rec_queue.get_nowait()
            except queue.Empty:
                break

        # Update UI elements immediately
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_show_hint.setEnabled(False)
        self.repetition_status_label.setText("")
        self.progress("تم إيقاف التسميع.")

        # Re-render the page to show all words with their last known state
        self.render_page(self.current_page)
 
    def _process_and_update_words(self, full_text):
        """Process the full text and update word highlights. Runs in a background thread."""
        # compute score
        correct = sum(1 for s in self._word_statuses if s is True)        
        total = len(self._word_statuses) # Total words expected
        pct = (correct / total * 100) if total else 0.0
        self.progress(f"✓ انتهى: {correct}/{total} صحيح ({pct:.1f}%)")
        # final highlight refresh
        self.recording_mode = False # Set to false before re-rendering to show text
        self.render_page(self.current_page)

    def start_recording(self):
        """Begin recording: prepare expected word list, enable UI and start audio stream."""
        if self.recording:
            return

         
        self.recording = True
        self.recording_mode = True
        self.recitation_repetitions = self.spin_repetitions.value()
        self.current_repetition = 1        

        # --- NEW: Logic to build recitation range ---
        from_sura = self.combo_from_sura.currentData()
        from_aya = self.spin_from_aya.value()
        to_sura = self.combo_to_sura.currentData()
        to_aya = self.spin_to_aya.value()

        self.recitation_range_words = [] 
        in_range = False
        for aya in self.pages_content:
            sura_no = aya.get('sura_no')
            aya_no = int(aya.get('aya_no', 0))

            if sura_no == from_sura and aya_no == from_aya:
                in_range = True
 
            if in_range:
                text_raw = aya.get("aya_text", "")
                parts = text_raw.split()
                for p in parts:
                    nw = normalize_word(p)
                    if not nw or re.match(r'^[\(\)\u0030-\u0039\u0660-\u0669\u06F0-\u06F9]+$', p):
                        continue
                    self.recitation_range_words.append(nw)
 
            if sura_no == to_sura and aya_no == to_aya:
                in_range = False
                break
        
        if not self.recitation_range_words:
            QMessageBox.warning(self, "مدى فارغ", "لم يتم العثور على كلمات في المدى المحدد. يرجى التحقق من أرقام الآيات.")
            self.recording = False # Reset state
            self.recording_mode = False
            return
 
        # CRITICAL FIX: Navigate to the starting page AFTER building the recitation range.
        # This ensures the page is rendered only once with the correct recording state.
        start_page = self.sura_pages.get(from_sura, 1)
        self.on_page_changed(start_page, from_start_recording=True)

        self.word_pos = 0
        self.page_completed_waiting_for_stop = False
        self.last_partial_word_count = 0 # Reset for new recording
        self._word_statuses = [None] * len(self.recitation_range_words)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_show_hint.setEnabled(True)
        self.progress("🎤 جاري التسميع... تحدث الآن")
        self.live_partial_text = "" # Reset for new recording
        self.repetition_status_label.setText(f"{self.current_repetition}/{self.recitation_repetitions}")
 
        # Show and clear the recognized text label
        self.recognized_text_widget.setText("...")
        self.recognized_text_widget.show()
        self.recognized_text_container.show()

        # Ensure the processing timer is running
        if hasattr(self, '_process_timer') and not self._process_timer.isActive():
            self._process_timer.start()
 
        # Start audio stream
        try:
            try:
                if self.recognizer is not None:                    
                    try:
                        # Enable partial results to get words as they are spoken
                        # --- REVERTED: SetGrammar was inaccurate. Re-enable simple partial results. ---
                        # This gets word-by-word updates from the recognizer.
                        self.recognizer.SetWords(True)

                    except Exception as e: 
                        print(f"Could not enable partial results: {e}")

                    try:
                        self.recognizer.Reset()
                    except Exception:
                        pass
            except Exception: 
                pass

            if SD_AVAILABLE:
                self.audio_stream = sd.RawInputStream(
                    samplerate=16000,
                    blocksize=8000,
                    dtype='int16',
                    channels=1,
                    callback=self._audio_callback
                )
                self.audio_stream.start()
            else:
                QMessageBox.warning(self, "صوت غير متاح", "مكتبة sounddevice غير متاحة، التسجيل غير ممكن.")
                self.stop_recording()
        except Exception as e:
            QMessageBox.critical(self, "خطأ في التسجيل", f"فشل بدء التسجيل:\n{e}\n"
                                                         "تأكد من توصيل الميكروفون ومنح الإذن للتطبيق.")
            self.stop_recording()

    def _audio_callback(self, indata, frames, time, status): # This runs in a separate thread 
        if status:            
            print("Audio status:", status)
        if self.recording:
            try:
                self._rec_queue.put(bytes(indata))
            except Exception:
                pass

    def _process_recognitions(self, force_process_all=False): # This runs in the main GUI thread 
        if not self.recording and not force_process_all:
            return
        try:
            while not self._rec_queue.empty():
                data = self._rec_queue.get_nowait()
                if not data:
                    continue
                
                # --- VAD FILTERING ---
                # Only process audio chunks that contain speech.
                # The VAD works with 10, 20, or 30 ms frames. We will check the whole data buffer.
                if self.vad:
                    frame_duration_ms = 30 # VAD supports 10, 20, or 30 ms frames
                    frame_size = int(16000 * (frame_duration_ms / 1000.0) * 2) # bytes per frame
                    is_speech = False
                    # Iterate through the audio data in valid frame sizes
                    for i in range(0, len(data), frame_size):
                        chunk = data[i:i+frame_size]
                        if len(chunk) == frame_size: # Only process full frames
                            if self.vad.is_speech(chunk, 16000):
                                is_speech = True
                                break # Found speech, no need to check further
                    if not is_speech:
                        continue # Skip this entire data block if no speech was detected

                # Process both partial and final results 
                # --- RESTORED LIVE FEEDBACK LOGIC ---
                # We process partial results to give live feedback to the user.
                if self.recognizer.AcceptWaveform(data):
                    # A final result is available (due to a pause).
                    res = json.loads(self.recognizer.Result())
                    text = res.get("text", "")
                    if text:
                        # Accumulate the final text segment for the full session text
                        self.live_partial_text += " " + text
                        self.live_partial_text = self.live_partial_text.strip()
                        self._animate_correction(text)
                        # Reset partial word count after a final result is processed.
                        self.last_partial_word_count = 0 # Reset for the next phrase
                        self.recognized_text_widget.setHtml(f'<i>يسمع الآن:</i><br>{self.live_partial_text}')
                        self.recognized_text_widget.verticalScrollBar().setValue(self.recognized_text_widget.verticalScrollBar().maximum())
                else:
                    # This block handles the live, partial results (text being spoken).
                    res = json.loads(self.recognizer.PartialResult())
                    partial_words = res.get("partial", "").split()
                    new_word_count = len(partial_words) 

                    if new_word_count > self.last_partial_word_count:
                        new_words_to_process = partial_words[self.last_partial_word_count:]
                        self._check_words(" ".join(new_words_to_process), is_final=False)
                        self.last_partial_word_count = new_word_count
 
                    # Update the live text display
                    full_live_text = (self.live_partial_text + " " + " ".join(partial_words)).strip()
                    self.recognized_text_widget.setHtml(f'<i>يسمع الآن:</i><br>{full_live_text}')
                    self.recognized_text_widget.verticalScrollBar().setValue(self.recognized_text_widget.verticalScrollBar().maximum())

        except queue.Empty:
            pass
        except Exception as e:
            print("Processing loop error:", e)
 
    def _reset_for_new_page_continuous(self):
        # Do NOT reset self.word_pos. We need to continue from where we left off in the global list.
        # We just need to re-render the page in recording mode and update the status message. The bug was resetting self.word_pos here.
        # --- CRITICAL FIX ---
        # The previous logic was rebuilding the expected words list based on the new page, which is wrong.
        # The recitation_range_words list should remain unchanged for the entire session.
        self.render_page(self.current_page) # Re-render in recording mode
        self.progress("🎤 جاري التسميع... تحدث الآن") 

    def _reset_word_statuses(self):
        """Helper function to reset word statuses to None."""
        self._word_statuses = [None] * len(self.recitation_range_words)
        
    def _get_page_for_word_index(self, global_word_index):
        """Finds the page number for a global word index within the recitation range."""
        from_sura = self.combo_from_sura.currentData()
        from_aya = self.spin_from_aya.value()
 
        word_count = 0
        in_range = False
        for aya in self.pages_content:
            sura_no = aya.get('sura_no')
            aya_no = int(aya.get('aya_no', 0))
            page_no = aya.get('page')
 
            if sura_no == from_sura and aya_no == from_aya:
                in_range = True

            if in_range:
                parts = [p for p in aya.get("aya_text", "").split() if normalize_word(p) and not re.match(r'^[\(\)\u0030-\u0039\u0660-\u0669\u06F0-\u06F9]+$', p)]
                for _ in parts:
                    if word_count == global_word_index:
                        return page_no
                    word_count += 1
        return None

    def _visible_range_for_page(self, page_no: int): 
        """Return the (start_idx, end_idx) global word indices for words on `page_no` within the current recitation range.

        Returns None if no words from the recitation range are on that page.
        """
        from_sura = self.combo_from_sura.currentData()
        from_aya = self.spin_from_aya.value()
        word_count = 0
        in_range = False 
        start_idx = None
        end_idx = None
        for aya in self.pages_content:
            try:
                aya_sura = aya.get('sura_no')
                aya_no = int(aya.get('aya_no', 0))
            except Exception:
                aya_sura = None
                aya_no = 0
            if aya_sura == from_sura and aya_no == from_aya:
                in_range = True
            if not in_range:
                continue
            parts = [p for p in aya.get("aya_text", "").split() if normalize_word(p) and not re.match(r'^[\(\)\u0030-\u0039\u0660-\u0669\u06F0-\u06F9]+$', p)]
            page = aya.get('page')
            for _ in parts:
                if page == page_no:
                    if start_idx is None:
                        start_idx = word_count
                    end_idx = word_count
                word_count += 1
            # optimization: stop after we pass the page if we already found start
            if start_idx is not None and page > page_no:
                break
        if start_idx is None:
            return None
        return (start_idx, end_idx)

    def _apply_statuses_to_visible(self): 
        """Apply the `_word_statuses` colors to currently visible words only."""
        vr = self._visible_range_for_page(self.current_page)
        if vr is None:
            return
        start_idx, end_idx = vr
        for gi in range(start_idx, min(end_idx + 1, len(self.recitation_range_words))):
            local = self._get_local_word_index(gi)
            if local is None or not (0 <= local < len(self.word_items)):
                continue
            status = None
            try:
                status = self._word_statuses[gi]
            except Exception:
                status = None
            rect = self.word_items[local]['rect']
            text = self.word_items[local]['text']
            text.setDefaultTextColor(QColor("#000000"))
            if status is True:
                rect.setBrush(QBrush(QColor(0, 200, 0, 120)))
            elif status is False:
                rect.setBrush(QBrush(QColor(230, 0, 0, 120)))
            elif status is None:
                rect.setBrush(QBrush(QColor(0, 0, 255, 90)))
            else:
                rect.setBrush(QBrush(QColor(0,0,0,0)))

    def force_flip_now(self): 
        """Force a page flip to the next logical page pair. Called from the UI button."""
        try:
            # Determine the page corresponding to current word_pos
            next_pg = None
            try:
                if getattr(self, 'word_pos', 0) < len(getattr(self, 'recitation_range_words', [])):
                    next_pg = self._get_page_for_word_index(self.word_pos)
            except Exception:
                next_pg = None
 
            if next_pg is None:
                # Fallback: advance by one pair
                target_start = self.current_page + 2
            else:
                target_start = next_pg if (next_pg % 2 == 1) else (next_pg - 1)
 
            if target_start < 1:
                target_start = 1
 
            # Mark that page is completed to avoid duplicate scheduling
            self.page_completed_waiting_for_stop = True
 
            logging.debug(f"[force-flip] user requested flip -> target_start={target_start} current_page={self.current_page} word_pos={getattr(self,'word_pos',None)}")
 
            # Schedule same follow-up actions as auto-flip
            QTimer.singleShot(100, lambda: self._safe_page_change(target_start))
        except Exception as e:
            try:
                logging.debug(f"[force-flip] error: {e}")
            except Exception:
                pass

    def debug_log(self, msg: str):
        """Write a debug message to the configured log file (and fall back to appending).""" 
        try:
            logging.debug(str(msg))
        except Exception:
            try:
                with open(resource_path("quran_tasmee_debug.log"), "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} DEBUG: {msg}\n")
            except Exception:
                pass

    def _safe_page_change(self, target_start): 
        """Call `on_page_changed` safely and schedule follow-ups.

        This prevents uncaught exceptions in page-change callbacks from
        terminating the Qt event loop. It also schedules the same
        follow-up actions (apply statuses, reset debounce flag).
        """
        try:
            self.on_page_changed(target_start)
        except Exception as e:
            try:
                logging.exception(f"[safe-page-change] exception during on_page_changed({target_start}): {e}")
            except Exception:
                pass
        try:
            QTimer.singleShot(120, lambda: self._apply_statuses_to_visible())
            QTimer.singleShot(900, lambda: setattr(self, 'page_completed_waiting_for_stop', False))
        except Exception:
            try:
                logging.exception("[safe-page-change] exception scheduling follow-ups")
            except Exception:
                pass

    def _check_words(self, recognized_text, is_final=False): 
        # This function now only handles live, non-final checks.
        # The final check is done in stop_recording.
        words_to_process = recognized_text.split()

        recognized_words = [normalize_word(w) for w in words_to_process if normalize_word(w)]
        if not recognized_words:
            return

        # --- NEW "INSTANT CORRECTION" LOGIC --- 
        # This logic provides immediate feedback by marking skipped words as wrong.
        rec_idx = 0
        while rec_idx < len(recognized_words) and self.word_pos < len(self.recitation_range_words):
            current_rec_word = recognized_words[rec_idx]
            expected_word_at_pos = self.recitation_range_words[self.word_pos]

            # --- Lookahead Search ---
            # Does the current recognized word match the expected word OR a future one?
            match_found = False
            # Check for a match at the current position first for performance
            if calculate_similarity(current_rec_word, expected_word_at_pos) > 0.65:
                match_found = True
            else:
                # If no direct match, look ahead a few words to see if we skipped something.
                lookahead_limit = min(self.word_pos + 5, len(self.recitation_range_words))
                for i in range(self.word_pos + 1, lookahead_limit):
                    if calculate_similarity(current_rec_word, self.recitation_range_words[i]) > 0.75: # Stricter for lookahead
                        # We found a match for a future word. This means all words between
                        # self.word_pos and i were SKIPPED. Play error sound once for the skip.
                        self._play_error_sound()
                        for j in range(self.word_pos, i):
                            self.mark_word_bad(j) # Mark skipped words as wrong INSTANTLY
                            if j < len(self._word_statuses):
                                self._word_statuses[j] = False
                        self.word_pos = i # Jump the position to the matched word
                        match_found = True
                        break 

            if match_found:
                # Matched the word at self.word_pos. Mark it as correct.
                self.mark_word_ok(self.word_pos)
                if self.word_pos < len(self._word_statuses):
                    self._word_statuses[self.word_pos] = True
                self.word_pos += 1 # Advance to the next expected word
            
            # Always advance the recognized word index
            rec_idx += 1

            # --- Automatic Page Turning (check after potential word_pos update) --- 
            if self.continuous_recitation and self.word_pos < len(self.recitation_range_words):
                # Compute visible global range for the current right page and flip
                # forward by one pair when we've advanced past its last word or
                # when a high percentage of visible words are correct.
                try:
                    logging.debug(f"[auto-flip debug] current_page={self.current_page} word_pos={self.word_pos} rec_range_len={len(self.recitation_range_words)} page_completed_waiting_for_stop={getattr(self,'page_completed_waiting_for_stop',False)}")
                except Exception:
                    pass

                vr = None 
                try:
                    vr = self._visible_range_for_page(self.current_page)
                    try:
                        logging.debug(f"[auto-flip debug] visible range for page {self.current_page} -> {vr}")
                    except Exception:
                        pass
                except Exception as e:
                    try:
                        logging.debug(f"[auto-flip debug] _visible_range_for_page error: {e}")
                    except Exception:
                        pass

                # Only proceed if we obtained a visible-range
                if vr is not None:
                    try:
                        start_idx, end_idx = vr
                    except Exception:
                        start_idx = end_idx = None

                    # The index of the last word on the current page (page on the right)
                    page_end_idx = end_idx if end_idx is not None else -1

                    # --- NEW SIMPLIFIED FLIP LOGIC ---
                    # Flip ONLY when the current word position has advanced beyond the last visible word on the current page.
                    if self.word_pos > page_end_idx and page_end_idx != -1 and not getattr(self, 'page_completed_waiting_for_stop', False):
                        next_pg = None
                        try:
                            # Find the page number for the current word position
                            next_pg = self._get_page_for_word_index(self.word_pos) if self.word_pos < len(self.recitation_range_words) else None
                        except Exception:
                            next_pg = None
                        try:
                            logging.debug(f"[auto-flip debug] computed next_page={next_pg}")
                        except Exception:
                            pass
                        if next_pg is not None:
                            # Ensure we navigate to the correct starting page of the pair (must be odd)
                            target_start = next_pg if (next_pg % 2 == 1) else (next_pg - 1)
                            if target_start < 1:
                                target_start = 1
                            self.page_completed_waiting_for_stop = True
                            try:
                                logging.debug(f"[auto-flip] SCHEDULING FLIP -> target_start={target_start} because word_pos({self.word_pos}) > page_end_idx({page_end_idx})")
                            except Exception:
                                pass
                            QTimer.singleShot(250, lambda: self._safe_page_change(target_start))
 
    def _animate_correction(self, text_chunk):
        """
        Processes a chunk of final recognized text, animating the correction
        word by word for smoother visual feedback.
        """
        words = text_chunk.split()
        if not words:
            return
 
        # Use a timer to process one word at a time from the chunk.
        def process_next_word(word_index=0):
            if word_index < len(words):
                self._check_words(words[word_index], is_final=False) # FIX: Process as non-final to avoid resetting progress
                QTimer.singleShot(50, lambda: process_next_word(word_index + 1))

        process_next_word(0)

    def _play_error_sound(self): 
        if PLAYSOUND_AVAILABLE and os.path.exists(ERROR_SOUND_PATH):
            threading.Thread(target=playsound, args=(ERROR_SOUND_PATH,), daemon=True).start()

    def toggle_hint_word(self):
        """Toggle showing the next word hint during recording."""
        if not self.recording:
            return
        self.show_hint_word = not self.show_hint_word
        if self.show_hint_word:
            self.btn_show_hint.setText("إخفاء الكلمة التالية")
        else:
            self.btn_show_hint.setText("عرض الكلمة التالية")
        self.render_page(self.current_page)  # Re-render with or without hint

    # ---------- marking visuals ----------
    def mark_word_ok(self, index):
        local_index = self._get_local_word_index(index)
        if local_index is not None and 0 <= local_index < len(self.word_items):
            rect = self.word_items[local_index]['rect']
            text = self.word_items[local_index]['text']
            rect.setBrush(QBrush(QColor(0, 200, 0, 120)))  # أخضر شفاف
            text.setDefaultTextColor(QColor("#000000")) # Show the word

    def mark_word_bad(self, index):
        local_index = self._get_local_word_index(index)
        if local_index is not None and 0 <= local_index < len(self.word_items):
            rect = self.word_items[local_index]['rect']
            text = self.word_items[local_index]['text']
            rect.setBrush(QBrush(QColor(230, 0, 0, 120))) # أحمر شفاف
            text.setDefaultTextColor(QColor("#000000")) # Show the word
 
    def mark_word_skipped(self, index):
        local_index = self._get_local_word_index(index)
        if local_index is not None and 0 <= local_index < len(self.word_items):
            word_info = self.word_items[local_index]
            rect = word_info['rect']
            text = word_info['text']
            rect.setBrush(QBrush(QColor(0, 0, 255, 90)))  # أزرق شفاف
            text.setDefaultTextColor(QColor("#000000")) # إظهار نص الكلمة

    def _get_local_word_index(self, global_word_index):
        """Converts a global word index from the recitation range to a local index on the current page."""
        from_sura = self.combo_from_sura.currentData()
        from_aya = self.spin_from_aya.value()
 
        word_count = 0
        local_word_count = 0
        in_range = False
        for aya in self.pages_content:
            sura_no = aya.get('sura_no')
            aya_no = int(aya.get('aya_no', 0))
            page_no = aya.get('page')
 
            if sura_no == from_sura and aya_no == from_aya:
                in_range = True
 
            if in_range:
                parts = [p for p in aya.get("aya_text", "").split() if normalize_word(p) and not re.match(r'^[\(\)\u0030-\u0039\u0660-\u0669\u06F0-\u06F9]+$', p)]
                for _ in parts:
                    if word_count == global_word_index:
                        return local_word_count if page_no in [self.current_page, self.current_page + 1] else None
                    word_count += 1
                    if page_no in [self.current_page, self.current_page + 1]:
                        local_word_count += 1
        return None

    def _update_highlights_final(self):
        """After stopping, re-color all words based on their final status."""
        # Iterate through the entire recitation range status
        for global_index, status in enumerate(self._word_statuses):
            # Find if this word is visible on the current pages
            local_index = self._get_local_word_index(global_index)
            if local_index is None or not (0 <= local_index < len(self.word_items)):
                continue # This word is not on the currently rendered pages
            
            rect = self.word_items[local_index]['rect']
            text = self.word_items[local_index]['text']
            text.setDefaultTextColor(QColor("#000000")) # Ensure all text is visible

            if status is True:
                rect.setBrush(QBrush(QColor(0, 200, 0, 120)))  # Green
            elif status is False:
                rect.setBrush(QBrush(QColor(230, 0, 0, 120)))  # Red
            elif status is None: # Skipped words
                rect.setBrush(QBrush(QColor(0, 0, 255, 90)))  # Blue for skipped
            else:
                # Words that were not reached
                rect.setBrush(QBrush(QColor(0,0,0,0))) # Transparent

   
    def on_page_changed(self, v: int, update_input: bool = True, from_start_recording: bool = False, force_recording_mode: bool = False):
        # Determine the starting (odd) page for the pair.
        start_page = v
        if hasattr(self, 'current_page') and self.current_page == start_page and not from_start_recording:
            return

        # Ensure we are in recording mode if forced
        if force_recording_mode and not self.recording_mode:
            self.recording_mode = True

        if start_page > 1 and start_page % 2 == 0:
            start_page = v - 1
        self.current_page = start_page
        if update_input:
            self.page_input.setText(str(self.current_page))
        self.render_page(self.current_page)
        self.page_completed_waiting_for_stop = False # Reset the flag when page changes
        self.update_nav_combos() 

    def _copy_recognized_text(self):
        """Copies the content of the recognized text widget to the clipboard."""
        QApplication.clipboard().setText(self.recognized_text_widget.toPlainText())
        self.btn_copy_recognized_text.setText("✓ تم النسخ")
        QTimer.singleShot(2000, lambda: self.btn_copy_recognized_text.setText("📋 نسخ النص"))
    # ---------- helpers ----------
    def progress(self, text):
        # simple status (we used QLabel earlier but here reuse window title)
        self.setWindowTitle(f"برنامج القرآن الكريم - التسميع بدون نت — {text}")

    # ---------- navigation ----------
    def on_prev(self):
        # Move back two pages (show previous pair)
        new_page = max(1, self.current_page - 2)
        self.on_page_changed(new_page)

    def on_next(self):
        # Move forward two pages (next pair)
        # maximum starting page is 603 so last pair is 603-604
        new_page = self.current_page + 2
        if new_page > 604:
            new_page = 1 # Loop back to the beginning
        self.on_page_changed(new_page)

    def on_page_input_enter(self):
        try:
            page = int(self.page_input.text())
            if 1 <= page <= 604:
                self.on_page_changed(page)
            else:
                self.page_input.setText(str(self.current_page)) # Revert to current page
        except ValueError:
            self.page_input.setText(str(self.current_page)) # Revert on invalid input

    def on_page_input_changed(self, text: str):
        """Handle live text changes in the page input field."""        
        # If the user is not focused on the input, do nothing.
        # This prevents this from firing when the code itself changes the text.
        if not self.page_input.hasFocus():
            return
        try:
            page = int(text)
            if 1 <= page <= 604:
                self.on_page_changed(page, update_input=False)
        except ValueError:
            # Ignore non-integer input while user is typing
            pass
    def on_juz_spin_changed(self, juz_no: int): 
        if not self.spin_juz.lineEdit().hasFocus():
            self._navigate_to_juz(juz_no)

    def on_juz_changed_deferred(self):
        """This function is called by the timer after the user stops changing the Juz value."""
    def on_juz_editing_finished(self):
        """Handles changes after the user finishes typing in the spinbox."""
        # This signal fires when the user presses Enter or clicks away.
        juz_no = self.spin_juz.value()
        self._navigate_to_juz(juz_no)

    def _navigate_to_juz(self, juz_no: int): 
        """Finds the page for a given Juz and navigates to it."""
        target_page = None
        for juz, page in self.juz_pages.items():
            if int(juz) == int(juz_no):
                target_page = page
                break
        if target_page is not None:
            if self.current_page != target_page:
                self.on_page_changed(target_page)                 

    def on_from_sura_changed(self, index):
        sura_no = self.combo_from_sura.currentData()
        if sura_no in self.sura_aya_counts:
            max_ayas = self.sura_aya_counts[sura_no]
            self.spin_from_aya.setRange(1, max_ayas)

    def on_to_sura_changed(self, index):
        sura_no = self.combo_to_sura.currentData()
        if sura_no in self.sura_aya_counts:
            max_ayas = self.sura_aya_counts[sura_no]
            self.spin_to_aya.setRange(1, max_ayas)
            self.spin_to_aya.setValue(max_ayas) # Default to last aya

    def on_continuous_toggled(self, state):
        self.continuous_recitation = (state == Qt.Checked)

    def update_nav_combos(self):
        """Update Juz and Sura combos to reflect the current page."""
        ayas_on_page = self.pages_by_number.get(self.current_page, [])
        if not ayas_on_page:
            return
        
                 # If the user is actively navigating (e.g., just selected a Juz),
        # don't let this function override their choice, unless we're updating
        # the Sura based on a Juz change.

        # Block signals to prevent loops.
        # If the user is navigating via Sura/Juz controls, we should not
        # fight their selection by resetting the combo/spin that triggered the change.
        self.spin_juz.blockSignals(True)
        self.combo_sura.blockSignals(True)
 
        # Update Juz combo based on the majority Juz on the page
        juz_counts = {}
        for aya in ayas_on_page:
            juz = aya.get('jozz')
            if juz:
                juz_counts[juz] = juz_counts.get(juz, 0) + 1
        
        if juz_counts: 
            # Find the juz with the most ayas on the page
            majority_juz = max(juz_counts, key=juz_counts.get)
            try:
                self.spin_juz.setValue(int(majority_juz))
            except (ValueError, TypeError):
                pass # Ignore if juz is not a valid number
        else: # Fallback to first aya if no majority can be determined
            current_juz = ayas_on_page[0].get('jozz')
            if current_juz is not None:
                self.spin_juz.setValue(int(current_juz))
 
        # Update Sura combo

        current_sura = ayas_on_page[0].get('sura_no')
        if current_sura is not None:
            sura_index = self.combo_sura.findData(current_sura)
            if sura_index != -1:
                self.combo_sura.setCurrentIndex(sura_index)         
 

        # Unblock signals
        self.spin_juz.blockSignals(False)
        self.combo_sura.blockSignals(False)

    # ---------- helpers copied from NET edits ----------
    def _visible_range_for_page(self, page_no: int, include_next_page: bool = True):
        """Return (start_idx, end_idx) global indices for words visible on the given page(s).

        Args:
            page_no: The starting page number (usually the right-side page).
            include_next_page: If True, also includes words from `page_no + 1`.
        """
        from_sura = self.combo_from_sura.currentData()
        from_aya = self.spin_from_aya.value()
        word_count = 0
        in_range = False
        start_idx = None
        end_idx = None

        pages_to_check = {page_no}
        if include_next_page:
            pages_to_check.add(page_no + 1)

        for aya in self.pages_content:
            aya_sura = aya.get('sura_no')
            try:
                aya_no = int(aya.get('aya_no', 0))
            except Exception:
                aya_no = 0
            if aya_sura == from_sura and aya_no == from_aya:
                in_range = True
            if not in_range:
                continue
            parts = [p for p in aya.get("aya_text", "").split() if normalize_word(p) and not re.match(r'^[\(\)\u0030-\u0039\u0660-\u0669\u06F0-\u06F9]+$', p)]
            page = aya.get('page')
            for _ in parts:
                if page in pages_to_check:
                    if start_idx is None:
                        start_idx = word_count
                    end_idx = word_count
                word_count += 1
            # Optimization: stop after we pass the pages if we already found a start index
            if start_idx is not None and page > (page_no + (1 if include_next_page else 0)):
                break
        if start_idx is None:
            return None
        return (start_idx, end_idx)

    def _apply_statuses_to_visible(self):
        """Apply `_word_statuses` colors to currently visible words only.""" 
        vr = None
        try:
            vr = self._visible_range_for_page(self.current_page)
        except Exception:
            vr = None
        if not vr:
            return
        start_idx, end_idx = vr
        for gi in range(start_idx, min(end_idx + 1, len(self.recitation_range_words))):
            local = self._get_local_word_index(gi)
            if local is None or not (0 <= local < len(self.word_items)):
                continue
            status = None
            try:
                status = self._word_statuses[gi]
            except Exception:
                status = None
            rect = self.word_items[local]['rect']
            text = self.word_items[local]['text']
            text.setDefaultTextColor(QColor("#000000"))
            if status is True:
                rect.setBrush(QBrush(QColor(0, 200, 0, 120)))
            elif status is False:
                rect.setBrush(QBrush(QColor(230, 0, 0, 120)))
            elif status is None:
                rect.setBrush(QBrush(QColor(0, 0, 255, 90)))
            else:
                rect.setBrush(QBrush(QColor(0,0,0,0)))

    def force_flip_now(self): 
        """Force a flip to the next logical page pair. Called by the `قلب الآن` button."""
        try:
            logging.debug(f"[force-flip] button clicked current_page={getattr(self,'current_page',None)} word_pos={getattr(self,'word_pos',None)}")
        except Exception:
            pass
        try:
            next_pg = None
            # Always advance by one pair of pages from the current one.
            # This provides a more predictable behavior for the user.
            target_start = self.current_page + 2

            if target_start < 1:
                target_start = 1
            if target_start > 604:
                target_start = 1 # Loop back

            self.page_completed_waiting_for_stop = True
            logging.debug(f"[force-flip] scheduling flip -> target_start={target_start} current_page={self.current_page} word_pos={getattr(self,'word_pos',None)}")
            
            # Use _safe_page_change to handle the navigation and re-apply recording mode visuals
            QTimer.singleShot(100, lambda: self.on_page_changed(target_start, force_recording_mode=True))
        except Exception as e:
            logging.debug(f"[force-flip] error: {e}")

    def debug_log(self, msg: str):
        try:
            logging.debug(str(msg))
        except Exception:
            try:
                with open(resource_path("quran_tasmee_debug.log"), "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} DEBUG: {msg}\n")
            except Exception:
                pass
    # ---------- Settings actions ----------
    def change_bg_color(self): 
        color = QColorDialog.getColor(QColor(self.bg_color), self, "اختر لون الخلفية")        
        if color.isValid():
            self.page_bg_color = color
            self.render_page(self.current_page) # Re-render to apply new background


    def toggle_aya_markers(self):
        """Toggle visibility of verse-number markers inside pages.""" 
        self.show_aya_markers = not self.show_aya_markers
        if self.show_aya_markers:
            self.btn_toggle_aya_markers.setText("إخفاء أرقام الآيات")
        else:
            self.btn_toggle_aya_markers.setText("إظهار أرقام الآيات")
        # re-render current page to apply change
        self.render_page(self.current_page)

    # ---------- zoom ----------
    def zoom_in(self): # Zoom in
        self._update_scale(self.scale_factor * 1.1)

    def zoom_out(self):
        self._update_scale(self.scale_factor / 1.1)

    def zoom_reset(self):
        self._update_scale(1.0)

    def _update_scale(self, new_scale): # Update the scaling factor
        self.scale_factor = new_scale
        self.render_page(self.current_page)
 
    def on_vad_slider_changed(self, value):
        # Update VAD aggressiveness based on slider
        if self.vad:
            # The slider value now directly corresponds to the VAD mode (0, 1, 2, 3)
            self.vad.set_mode(value)
            mode_text = {
                0: "الأقل حساسية",
                1: "متوسطة",
                2: "عالية",
                3: "الأكثر حساسية"
            }
            self.vad_label.setText(f"حساسية فلتر الضوضاء: {mode_text.get(value, '')}")

# ---------- run ---------- 
def main():
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    w = QuranCanvasApp()
    w.resize(1100, 700) # يمكنك تغيير هذه القيم (العرض, الطول)
    w.on_page_changed(1) # Initial render
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
