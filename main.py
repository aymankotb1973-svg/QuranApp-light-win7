# -*- coding: utf-8 -*-
"""
main_window.py - The main window for the Quran Tasmee Application. (Vosk in Worker Thread)

عرض صفحتين على QGraphicsScene كل كلمة مستورة بمستطيل أسود يُغيّر لونه (أخضر/أحمر شفاف)
يدعم التكبير/التصغير، استخدام خطك (C:/QuranApp/fonts/uthmanic.ttf)
يتكامل مع Vosk لو مثبت وموجود الموديل.
"""

import sys
# --- FIX: Python 3.8 Compatibility for adhanpy (zoneinfo) ---
# خدعة التوافق لإصدار 3.8 (Monkey Patching)
try:
    import zoneinfo
except ImportError:
    try:
        from backports import zoneinfo
        sys.modules["zoneinfo"] = zoneinfo
        # print("✓ تم حقن zoneinfo بنجاح")
    except ImportError:
        pass # print("!!! فشل حقن المكتبة - تأكد من تثبيت backports.zoneinfo")

import os
import subprocess

# --- FIX: Suppress console window for subprocesses (ffmpeg/pydub) on Windows ---
# This prevents the black CMD window from popping up when playing Azan
if sys.platform == "win32":
    _original_Popen = subprocess.Popen

    class Popen(subprocess.Popen):
        def __init__(self, args, **kwargs):
            if 'startupinfo' not in kwargs:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                kwargs['startupinfo'] = startupinfo
            super().__init__(args, **kwargs)

    subprocess.Popen = Popen

# --- FIX: Dynamically configure paths for bundled (EXE) and dev environments ---
# This must be done before importing libraries that depend on these paths (pydub, vlc).
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle.
    # Determine the base directory where the executable is located
    if hasattr(sys, '_MEIPASS'):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(sys.executable)

    # Check for _internal folder (New PyInstaller structure)
    # If _internal exists, resources are inside it. Otherwise, they are in the base dir.
    internal_dir = os.path.join(base_dir, '_internal')
    if os.path.isdir(internal_dir):
        bundle_dir = internal_dir
    else:
        bundle_dir = base_dir

    # --- FIX: Add the bundle directory itself to the DLL search path for VLC ---
    if sys.platform == "win32":
        os.add_dll_directory(bundle_dir)
        # print(f"Added main bundle path to DLL search: {bundle_dir}")

    # For VLC, ensure the plugins directory is discoverable
    if sys.platform == "win32":
        vlc_plugins_path = os.path.join(bundle_dir, 'plugins')
        if os.path.isdir(vlc_plugins_path):
            os.add_dll_directory(vlc_plugins_path)
            # print(f"Added VLC plugins path to DLL search: {vlc_plugins_path}")
else:
    # Running in a normal Python environment
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

# Add ffmpeg to PATH for pydub
ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
os.environ["PATH"] += os.pathsep + ffmpeg_path

# --- NEW: Import Prayer & Location Libraries ---
import asyncio
from datetime import datetime, timedelta
import urllib.request # NEW: For Windows 7 Location Fallback

try:
    import geocoder
    GEOCODER_AVAILABLE = True
except ImportError:
    GEOCODER_AVAILABLE = False

# تعريف كلاس Coordinates يدوياً لتجنب مشاكل الاستيراد عند التحميل اللاحق
class Coordinates:
    def __init__(self, latitude, longitude):
        self.latitude = float(latitude)
        self.longitude = float(longitude)

    def __iter__(self):
        return iter((self.latitude, self.longitude))

from typing import List, Optional, Tuple, cast
from ui_builder import UiBuilder  # <-- استيراد بانِي الواجهة
from page_renderer import WordSignals
from page_renderer import PageRenderer, CORRECT_COLOR, INCORRECT_COLOR, PROVISIONAL_INCORRECT_COLOR
from quran_data_manager import QuranDataManager
from translations import TRANSLATIONS # NEW: Import translations
from utils import (resource_path, normalize_word, calculate_similarity,
                   DEFAULT_FONT_SIZE, DEFAULT_BG_COLOR,
                   UTHMAN_FONT_FILE, AYAH_NUMBER_FONT_FILE,
                   QURAN_TEXT_DISPLAY_FONT_FILE, ERROR_SOUND_PATH,
                   PYDUB_AVAILABLE, AudioSegment, pydub_play, load_pydub,
                   load_settings, save_settings, WakeLock, SPECIAL_WORD_MAPPINGS)
from user_profile import UserManager, ProfileDialog, DashboardDialog # NEW: Import User Profile System
from quran_info_manager import QuranInfoManager # NEW: Import Info Manager
from quran_info_dialog import WordInfoDialog # NEW: Import Info Dialog
from PyQt5.QtCore import (Qt, QTimer, QRectF, QPointF, QPoint, QMarginsF, pyqtSignal, QEvent, QThread, pyqtSlot, QSize, QDate,
                          QVariantAnimation, QEasingCurve, QObject, QSettings)
from PyQt5.QtGui import (
    QFont, QFontDatabase, QColor, QBrush, QPen, QPainter, QResizeEvent, QTextCursor, QIcon, QPixmap,
    QTextOption, QKeySequence, QPixmap
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QColorDialog, QFontDialog, QMessageBox, QGroupBox, QStyle,
    QGraphicsView, QGraphicsScene, QPushButton, QLabel, QLineEdit, QTextEdit,
    QDialog, QVBoxLayout, QHBoxLayout, QInputDialog, QComboBox, QDateEdit, QListWidget, QTableWidget, QTableWidgetItem, QDoubleSpinBox, QHeaderView, QSystemTrayIcon, QMenu,
    QCheckBox, QSpinBox, QSlider, QFileDialog, QFormLayout, QCompleter, QGridLayout,
    QScrollArea, QFrame, QShortcut, QGraphicsDropShadowEffect,
    QGraphicsTextItem, QGraphicsRectItem, QToolButton, QTabWidget, QSizePolicy,
    QDialogButtonBox, QSplashScreen
)
from PyQt5.QtWidgets import QMessageBox, QProgressDialog
import sys, traceback, os, json, re, gc, threading, copy, collections, time, queue

# --- NEW: Import Numpy for Voice Trigger ---
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

def clean_device_name(name):
    # إزالة أي نص بين أقواس () مثل (MME/WASAPI) وأي أرقام بين مربعات []
    clean = re.sub(r'\s*\(.*?\)\s*|\[\d+\]', '', name)
    return clean.strip()


# --- NEW: Desktop Prayer Widget ---
class PrayerDesktopWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__() # Make it a top-level window (No parent)
        self.main_window = parent
        
        # Load Settings or Defaults
        self.always_on_top = self.main_window.settings.get("widget_on_top", True)
        self.text_color = self.main_window.settings.get("widget_text_color", "#ffffff")
        self.bg_color = self.main_window.settings.get("widget_bg_color", "#C8141E28") 
        self.font_scale = float(self.main_window.settings.get("widget_font_scale", 1.0))

        self.update_window_flags()
        self.setAttribute(Qt.WA_TranslucentBackground) # Make background transparent
        self.offset = None

        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 15, 20, 15) # Increased margins for better look
        self.layout.setSpacing(2)

        # Labels
        self.prayer_name_label = QLabel("...")
        self.prayer_name_label.setAlignment(Qt.AlignCenter)

        self.remaining_time_label = QLabel("...")
        self.remaining_time_label.setAlignment(Qt.AlignCenter)

        self.layout.addWidget(self.prayer_name_label)
        self.layout.addWidget(self.remaining_time_label)
        
        # --- NEW: Toggle Button for Details ---
        self.toggle_btn = QPushButton("▼")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle_details)
        self.toggle_btn.setStyleSheet(f"background: transparent; border: none; color: {self.text_color}; font-weight: bold; font-size: 14px;")
        self.layout.addWidget(self.toggle_btn)

        # --- NEW: Details Container ---
        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setContentsMargins(0, 5, 0, 0)
        self.details_layout.setSpacing(2)
        self.details_widget.setVisible(False)
        self.layout.addWidget(self.details_widget)
        
        self.apply_styles()

    def update_window_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

    def apply_styles(self):
        # Force repaint to update background color
        self.update()
        
        # Update fonts
        size_name = int(16 * self.font_scale)
        size_time = int(22 * self.font_scale)
        
        self.prayer_name_label.setStyleSheet(f"background:transparent; font-size: {size_name}pt; font-weight: bold; color: {self.text_color};")
        self.remaining_time_label.setStyleSheet(f"background:transparent; font-size: {size_time}pt; font-weight: bold; color: #FF0000;")
        
        if hasattr(self, 'toggle_btn'):
            self.toggle_btn.setStyleSheet(f"background: transparent; border: none; color: {self.text_color}; font-weight: bold; font-size: 14px;")
            
        # Update details labels if they exist
        if hasattr(self, 'details_layout'):
             size_details = max(10, int(14 * self.font_scale))
             for i in range(self.details_layout.count()):
                 item = self.details_layout.itemAt(i)
                 if item and item.widget():
                     item.widget().setStyleSheet(f"background:transparent; font-size: {size_details}pt; color: {self.text_color}; font-weight: bold;")

        self.adjustSize()

    def paintEvent(self, event):
        """Custom paint event to draw the background with rounded corners."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw Background
        if hasattr(self, 'bg_color'):
            c = QColor(self.bg_color)
            painter.setBrush(QBrush(c))
            # Draw a subtle border
            painter.setPen(QPen(QColor(255, 255, 255, 50), 1)) 
            
            # Draw rounded rect covering the whole widget
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 15, 15)

    def contextMenuEvent(self, event):
        """Shows a context menu for quick settings."""
        menu = QMenu(self)
        
        # Toggle Always on Top
        on_top_action = menu.addAction(self.main_window.tr("chk_widget_on_top"))
        on_top_action.setCheckable(True)
        on_top_action.setChecked(self.always_on_top)
        on_top_action.triggered.connect(self.toggle_on_top_from_menu)
        
        menu.addSeparator()
        
        # Hide Widget
        hide_action = menu.addAction(self.main_window.tr("tray_hide_widget"))
        hide_action.triggered.connect(self.hide_self)
        
        menu.exec_(event.globalPos())

    def toggle_on_top_from_menu(self):
        new_state = not self.always_on_top
        self.main_window.on_toggle_widget_on_top(new_state)
        # Sync checkbox in main window
        if hasattr(self.main_window, 'chk_widget_on_top'):
            self.main_window.chk_widget_on_top.setChecked(new_state)

    def hide_self(self):
        self.main_window.on_toggle_widget_visibility(False)
        if hasattr(self.main_window, 'chk_show_widget'):
            self.main_window.chk_show_widget.setChecked(False)

    @pyqtSlot(str, str, str) # Match the signal signature
    def update_times(self, clock_time, prayer_name, remaining_time):
        # We ignore clock_time for this widget
        self.prayer_name_label.setText(prayer_name)
        self.remaining_time_label.setText(remaining_time)
        
        if self.details_widget.isVisible():
             if getattr(self, '_last_prayer_name', '') != prayer_name:
                 self.update_upcoming_list()
                 self._last_prayer_name = prayer_name
        
        self.adjustSize() # Adjust size to content

    def toggle_details(self):
        is_visible = self.details_widget.isVisible()
        self.details_widget.setVisible(not is_visible)
        self.toggle_btn.setText("▲" if not is_visible else "▼")
        if not is_visible:
            self.update_upcoming_list()
        self.adjustSize()

    def refresh_list(self):
        """Refreshes the upcoming prayers list if visible."""
        if self.details_widget.isVisible():
            self.update_upcoming_list()
            self.adjustSize()

    def update_upcoming_list(self):
        # Clear existing
        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        if not self.main_window or not hasattr(self.main_window, 'prayer_times'):
            return

        now = datetime.now()
        
        name_map = {
            "Fajr": self.main_window.tr("prayer_fajr"), 
            "Sunrise": self.main_window.tr("prayer_sunrise"), 
            "Dhuhr": self.main_window.tr("prayer_dhuhr"), 
            "Asr": self.main_window.tr("prayer_asr"), 
            "Maghrib": self.main_window.tr("prayer_maghrib"), 
            "Isha": self.main_window.tr("prayer_isha")
        }
        
        sorted_times = []
        for key, dt in self.main_window.prayer_times.items():
            clean_name = key.replace("_TOMORROW", "")
            if clean_name in name_map:
                sorted_times.append((dt, name_map[clean_name]))
        
        sorted_times.sort(key=lambda x: x[0])
        
        count = 0
        size_details = max(10, int(14 * self.font_scale))
        
        for dt, name_ar in sorted_times:
            if dt > now:
                time_str = dt.strftime("%I:%M %p")
                lbl = QLabel(f"{name_ar}: {time_str}")
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet(f"background:transparent; font-size: {size_details}pt; color: {self.text_color}; font-weight: bold;")
                self.details_layout.addWidget(lbl)
                count += 1
                if count >= 6: break
        
        self.details_layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.pos() - self.offset)

    def mouseReleaseEvent(self, event):
        self.offset = None

# --- NEW: Draggable Label for Floating Toast ---
class DraggableLabel(QLabel):
    """A QLabel that can be moved by clicking and dragging."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.offset = None
        self.setCursor(Qt.SizeAllCursor) # Change cursor to indicate it's movable
        self.user_has_moved = False # NEW: Track if user moved it manually

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() == Qt.LeftButton:
            # mapToParent is crucial to get coordinates relative to the parent widget
            new_pos = self.mapToParent(event.pos() - self.offset)
            self.move(new_pos)
            self.user_has_moved = True # NEW: Mark as moved by user

    def mouseReleaseEvent(self, event):
        self.offset = None

# --- Global Placeholders for Lazy Loading ---
vlc = None
VLC_AVAILABLE = False
sd = None
SD_AVAILABLE = False
AudioSegment = None
PrayerTimes = None
CalculationMethod = None
Madhab = None
PRAYER_CALC_AVAILABLE = False
wdg = None
WINSDK_AVAILABLE = False
arabic_reshaper = None

def fix_arabic_display(text):
    """يقوم بإصلاح مشاكل عرض النص العربي (الحروف المقطعة والاتجاه)."""
    if not text: return text
    global arabic_reshaper

    # --- Dynamic loading of arabic_reshaper ---
    if arabic_reshaper is None:
        try:
            import arabic_reshaper as ar
            arabic_reshaper = ar
            # print("DEBUG: arabic_reshaper loaded dynamically.")
        except ImportError:
            # print("WARNING: arabic_reshaper not available, skipping text reshaping.")
            return text


    # --- FIX: Skip reshaping for Huroof Muqatta'at on Windows 7 ---
    # استثناء الحروف المقطعة من إعادة التشكيل لأنها تظهر مفرطة مع بعض الخطوط
    if text.strip() in SPECIAL_WORD_MAPPINGS.values():
        return text

    if arabic_reshaper is None: return text # Return as is if not loaded yet
    # 1. إعادة تشكيل الحروف (لحام الحروف المقطعة)
    configuration = {
        'delete_harakat': False, # سيب التشكيل زي ما هو عشان المصحف
        'support_zwj': True,      # دعم الربط المعقد
        'shift_harakat_position': True # تحسين موقع التشكيل
    }
    reshaper = arabic_reshaper.ArabicReshaper(configuration=configuration)
    reshaped_text = reshaper.reshape(text)
    
    return reshaped_text

def play_error_sound():
    """Plays an error sound in a non-blocking way."""
    load_pydub() # Ensure pydub is loaded
    if PYDUB_AVAILABLE and ERROR_SOUND_PATH and os.path.exists(ERROR_SOUND_PATH):
        threading.Thread(target=lambda: pydub_play(AudioSegment.from_file(ERROR_SOUND_PATH)), daemon=True).start()

# --- NEW: Custom Font Selection Dialog ---
class FontSelectionDialog(QDialog):
    """
    A custom dialog to select fonts specifically from the project's 'fonts' directory.
    Includes options for Font Family, Size, and Bold weight.
    """
    def __init__(self, current_font_family, current_weight, current_size, parent=None):
        super().__init__(parent)
        # Use parent's tr if available, otherwise fallback
        tr = parent.tr if parent and hasattr(parent, 'tr') else lambda k: k
        
        self.setWindowTitle(tr("change_font_title"))
        self.setFixedSize(350, 200)
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(self)

        # Font Family Selection
        layout.addWidget(QLabel(tr("font_from_project")))
        self.combo_fonts = QComboBox()
        self.available_fonts = self._load_project_fonts()
        self.combo_fonts.addItems(self.available_fonts)
        
        # Set current font if available in the list
        index = self.combo_fonts.findText(current_font_family)
        if index >= 0:
            self.combo_fonts.setCurrentIndex(index)
        layout.addWidget(self.combo_fonts)

        # Font Size Selection
        layout.addWidget(QLabel(tr("font_size")))
        self.spin_size = QSpinBox()
        self.spin_size.setRange(10, 150) # Allow a wide range of sizes
        try:
            # Safely convert to handle integers, floats, and numeric strings
            self.spin_size.setValue(int(float(current_size)))
        except (ValueError, TypeError):
            print(f"WARNING: Invalid font size '{current_size}' loaded from settings. Falling back to default.")
            self.spin_size.setValue(DEFAULT_FONT_SIZE)
        layout.addWidget(self.spin_size)

        # Bold Checkbox
        self.check_bold = QCheckBox(tr("bold_font"))
        # Check if weight is Bold (75) or higher
        self.check_bold.setChecked(current_weight >= QFont.Bold)
        layout.addWidget(self.check_bold)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton(tr("ok"))
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton(tr("cancel"))
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _load_project_fonts(self):
        """Loads fonts from the 'fonts' directory and returns a list of family names."""
        # print("\n--- DEBUG (FontSelectionDialog): جارِ تحميل الخطوط من مجلد المشروع ---")
        fonts_dir = resource_path("fonts")
        font_families = set()
        
        if os.path.exists(fonts_dir):
            # print(f"تم العثور على مجلد الخطوط: {fonts_dir}")
            for filename in os.listdir(fonts_dir):
                if filename.lower().endswith((".ttf", ".otf")):
                    full_path = os.path.join(fonts_dir, filename)
                    # print(f"محاولة تحميل الخط: {filename}")
                    # Try to load the font to get its family name
                    font_id = QFontDatabase.addApplicationFont(full_path)
                    if font_id != -1:
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        # print(f"  -> ✅ تم التحميل بنجاح! رقم الخط: {font_id}, أسماء العائلات: {families}")
                        for family in families:
                            font_families.add(family)
                    # else:
                        # print(f"  -> ❌ فشل تحميل الخط: {filename}. لم يتم العثور على ID.")
        # else:
            # print(f"لم يتم العثور على مجلد الخطوط: {fonts_dir}")
        
        # print(f"--- الخطوط النهائية التي تم التعرف عليها: {sorted(list(font_families))} ---\n")
        return sorted(list(font_families))

    def get_result(self):
        """Returns the selected font family, weight, and size."""
        family = self.combo_fonts.currentText()
        weight = QFont.Bold if self.check_bold.isChecked() else QFont.Normal
        size = self.spin_size.value()
        return family, weight, size

# --- NEW: Font Settings Dialog for Static and Dynamic modes ---
class FontSettingsDialog(QDialog):
    """
    A custom dialog to select font family, weight, and separate sizes for static and dynamic modes.
    """
    def __init__(self, current_family, current_weight, static_size, dynamic_size, parent=None):
        super().__init__(parent)
        tr = parent.tr if parent and hasattr(parent, 'tr') else lambda k: k
        
        self.setWindowTitle(tr("font_settings_title"))
        self.setFixedSize(350, 250)
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QFormLayout(self)

        # Font Family
        self.combo_fonts = QComboBox()
        self.available_fonts = self._load_project_fonts()
        self.combo_fonts.addItems(self.available_fonts)
        index = self.combo_fonts.findText(current_family)
        if index >= 0:
            self.combo_fonts.setCurrentIndex(index)
        layout.addRow(tr("font_type"), self.combo_fonts)

        # Font Weight
        self.check_bold = QCheckBox(tr("bold_font"))
        self.check_bold.setChecked(current_weight >= QFont.Bold)
        layout.addRow(self.check_bold)

        # Static Font Size
        self.spin_static_size = QSpinBox()
        self.spin_static_size.setRange(10, 150)
        self.spin_static_size.setValue(static_size)
        layout.addRow(tr("font_size_static"), self.spin_static_size)

        # Dynamic Font Size
        self.spin_dynamic_size = QSpinBox()
        self.spin_dynamic_size.setRange(10, 150)
        self.spin_dynamic_size.setValue(dynamic_size)
        layout.addRow(tr("font_size_dynamic"), self.spin_dynamic_size)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton(tr("ok"))
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton(tr("cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addRow(btn_layout)

    def _load_project_fonts(self):
        """Loads fonts from the 'fonts' directory and returns a list of family names."""
        # print("\n--- DEBUG (FontSettingsDialog): جارِ تحميل الخطوط من مجلد المشروع ---")
        fonts_dir = resource_path("fonts")
        font_families = set()
        if os.path.exists(fonts_dir):
            # print(f"تم العثور على مجلد الخطوط: {fonts_dir}")
            for filename in os.listdir(fonts_dir):
                if filename.lower().endswith((".ttf", ".otf")):
                    full_path = os.path.join(fonts_dir, filename)
                    # print(f"محاولة تحميل الخط: {filename}")
                    font_id = QFontDatabase.addApplicationFont(full_path)
                    if font_id != -1:
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        # print(f"  -> ✅ تم التحميل بنجاح! رقم الخط: {font_id}, أسماء العائلات: {families}")
                        font_families.update(families)
                    # else:
                        # print(f"  -> ❌ فشل تحميل الخط: {filename}. لم يتم العثور على ID.")
        # else:
            # print(f"لم يتم العثور على مجلد الخطوط: {fonts_dir}")
            
        # print(f"--- الخطوط النهائية التي تم التعرف عليها: {sorted(list(font_families))} ---\n")
        return sorted(list(font_families))

    def get_results(self):
        """Returns the selected font family, weight, and sizes."""
        family = self.combo_fonts.currentText()
        weight = QFont.Bold if self.check_bold.isChecked() else QFont.Normal
        static_size = self.spin_static_size.value()
        dynamic_size = self.spin_dynamic_size.value()
        return family, weight, static_size, dynamic_size

# --- NEW: Speed/Accuracy Improvement ---

# --- NEW: Pulse Animation Manager for Buttons ---
class PulseManager(QObject):
    """
    Manages a breathing/pulsing color animation for a QPushButton to indicate active state.
    """
    def __init__(self, button, active_color="#e6f7ff", default_color="#ffffff", parent=None):
        super().__init__(parent)
        self.button = button
        self.active_color = QColor(active_color)
        self.default_color = QColor(default_color)
        self.original_style = button.styleSheet() if button else ""
        
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(1500) # 1.5 seconds for full cycle
        self.anim.setLoopCount(-1) # Infinite loop
        self.anim.setStartValue(self.default_color)
        self.anim.setKeyValueAt(0.5, self.active_color) # Peak color at 50%
        self.anim.setEndValue(self.default_color)
        self.anim.setEasingCurve(QEasingCurve.InOutSine) # Smooth breathing curve
        self.anim.valueChanged.connect(self.update_style)

    def update_style(self, color):
        if self.button:
            # حساب درجات الألوان للتمويج
            main_color = color.name()
            # إنشاء لون فاتح جداً (أبيض مشرب باللون) للوسط
            glow_light = color.lighter(150).name()
            
            # التنسيق الجمالي الجديد (Gradient + Glow Border)
            self.button.setStyleSheet(f"""
                QPushButton, QPushButton:disabled {{
                    /* 1. تمويج احترافي (من الغامق للفاتح جداً للغامق) */
                    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, 
                                      stop:0 {main_color}, 
                                      stop:0.5 {glow_light}, 
                                      stop:1 {main_color});
                    
                    /* 2. حدود مضيئة واضحة جداً */
                    border: 2px solid {glow_light};
                    border-radius: 12px;
                    
                    /* 3. نص أبيض عريض بظل خفيف لزيادة الوضوح */
                    color: white;
                    font-weight: bold;
                    font-size: 15px;

                    
                    /* 4. حشوة داخلية تعطي فخامة */
                    padding: 8px 15px;
                }}
            """)
            
            # 5. إضافة "هالة" (Glow) حقيقية حول الزرار برمجياً
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(25) # قوة التوهج الخارجي
            shadow.setColor(color)
            shadow.setOffset(0)
            self.button.setGraphicsEffect(shadow)

    def start(self):
        if self.button and self.anim.state() != QVariantAnimation.Running:
            self.original_style = self.button.styleSheet() # Capture latest style before animating
            self.anim.start()

    def stop(self):
        if self.anim.state() == QVariantAnimation.Running:
            self.anim.stop()
            if self.button:
                self.button.setGraphicsEffect(None) # Remove glow
                self.button.setStyleSheet(self.original_style) # Restore original style

# --- NEW: Location Worker Thread (Async Bridge) ---
class LocationWorker(QThread):
    location_found = pyqtSignal(float, float)
    location_failed = pyqtSignal(str)

    def run(self):
        # المحاولة الأولى: استخدام WINSDK (ويندوز 10/11)
        if not WINSDK_AVAILABLE:
            # إذا لم تكن المكتبة موجودة (ويندوز 7)، ننتقل للطريقة البديلة فوراً
            self._get_location_ip()
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if wdg is None:
                 self.location_failed.emit("مكتبة winsdk لم يتم تحميلها بشكل صحيح.")
                 return
            loop.run_until_complete(self._get_location_async())
        except Exception as e:
            # في حالة فشل الطريقة الحديثة، نجرب طريقة الـ IP
            self._get_location_ip()
        finally:
            loop.close()

    async def _get_location_async(self):
        try:
            geolocator = wdg.Geolocator()
            # Request access (might prompt user on Windows)
            access_status = await wdg.Geolocator.request_access_async()
            
            if access_status == wdg.GeolocationAccessStatus.ALLOWED:
                # Get position (timeout after 10 seconds)
                pos = await geolocator.get_geoposition_async()
                lat = pos.coordinate.point.position.latitude
                lng = pos.coordinate.point.position.longitude
                self.location_found.emit(lat, lng)
            else:
                # تم الرفض، نجرب الـ IP
                self._get_location_ip()
        except Exception as e:
            # حدث خطأ، نجرب الـ IP
            self._get_location_ip()

    def _get_location_ip(self):
        """طريقة بديلة لويندوز 7 أو عند فشل المستشعر: تحديد الموقع عبر IP"""
        # محاولة 1: استخدام مكتبة Geocoder (الأكثر دقة)
        if GEOCODER_AVAILABLE:
            try:
                # 'me' uses the current IP to find location
                g = geocoder.ip('me')
                if g.ok and g.latlng:
                    lat, lng = g.latlng
                    self.location_found.emit(lat, lng)
                    return
            except Exception as e:
                print(f"Geocoder error: {e}")

        # محاولة 2: استخدام API مباشر (احتياطي في حال فشل geocoder)
        try:
            # استخدام خدمة مجانية لتحديد الموقع (لا تتطلب مفتاح API)
            with urllib.request.urlopen("http://ip-api.com/json/", timeout=5) as url:
                data = json.loads(url.read().decode())
                if data['status'] == 'success':
                    lat = float(data['lat'])
                    lon = float(data['lon'])
                    self.location_found.emit(lat, lon)
                else:
                    self.location_failed.emit("فشل تحديد الموقع عبر الإنترنت.")
        except Exception as e:
            self.location_failed.emit(f"تعذر تحديد الموقع (Win7/IP): {e}")

# --- NEW: Collapsible Box Class for Sidebar ---
class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        # Header Button
        self.toggle_button = QToolButton(text=title, checkable=True, checked=False) # Collapsed by default
        self.toggle_button.setStyleSheet("""
            QToolButton {
                border: none;
                background-color: #f0f0f0;
                text-align: left;
                padding: 8px;
                font-weight: bold;
                color: #2c3e50;
                border-radius: 4px;
            }
            QToolButton:hover { background-color: #e0e0e0; }
            QToolButton:checked { background-color: #d6eaf8; color: #2980b9; }
        """)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.LeftArrow) # Default arrow for collapsed (RTL)
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.clicked.connect(self.on_pressed)

        # Content Area
        self.content_area = QWidget()
        self.content_area.setVisible(False) # Hidden by default
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 5, 0, 5)
        self.content_layout.setSpacing(5)

        # Main Layout
        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle_button)
        lay.addWidget(self.content_area)

    def on_pressed(self, checked):
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.LeftArrow)
        self.content_area.setVisible(checked)

    def set_content(self, widget):
        self.content_layout.addWidget(widget)

# --- NEW: Advanced Plan Creation Dialog ---
class PlanCreationDialog(QDialog):
    def __init__(self, data_manager, parent=None, content_only=False, plan_data=None):
        super().__init__(parent)
        self.data_manager = data_manager
        self.content_only = content_only
        self.plan_data = plan_data
        
        # Helper for translation
        tr = parent.tr if parent and hasattr(parent, 'tr') else lambda k: k
        self.tr_func = tr

        self.setWindowTitle(tr("create_new_plan_title"))
        self.resize(600, 500)
        self.setLayoutDirection(Qt.RightToLeft)
        
        self.segments = [] # Stores the parts of the plan

        layout = QVBoxLayout(self)

        if not self.content_only:
            # 1. Basic Info
            form_layout = QFormLayout()
            self.name_input = QLineEdit()
            self.name_input.setPlaceholderText(tr("plan_name_placeholder"))
            form_layout.addRow(tr("plan_name"), self.name_input)
            
            self.type_combo = QComboBox()
            self.type_combo.addItem(tr("plan_type_memorization"), "memorization")
            self.type_combo.addItem(tr("plan_type_review"), "review")
            self.type_combo.addItem(tr("plan_type_listening"), "listening")
            self.type_combo.addItem(tr("plan_type_repetition"), "repetition")
            self.type_combo.currentIndexChanged.connect(self.toggle_repetition_ui)
            form_layout.addRow(tr("plan_type"), self.type_combo)
            
            self.start_date_input = QDateEdit()
            self.start_date_input.setDate(QDate.currentDate())
            self.start_date_input.setCalendarPopup(True)
            form_layout.addRow(tr("start_date"), self.start_date_input)
            
            # Auto Repeat Checkbox
            self.chk_auto_repeat = QCheckBox(tr("auto_repeat_plan"))
            self.chk_auto_repeat.setToolTip(tr("auto_repeat_tooltip"))
            form_layout.addRow("", self.chk_auto_repeat)

            # Repetition Target Input (Hidden by default)
            self.rep_target_widget = QWidget()
            rep_layout = QHBoxLayout(self.rep_target_widget)
            rep_layout.setContentsMargins(0,0,0,0)
            self.spin_target_reps = QSpinBox()
            self.spin_target_reps.setRange(1, 10000)
            self.spin_target_reps.setValue(30)
            rep_layout.addWidget(QLabel(tr("target_reps")))
            rep_layout.addWidget(self.spin_target_reps)
            form_layout.addRow(self.rep_target_widget)
            self.rep_target_widget.hide()

            layout.addLayout(form_layout)

        # 2. Content Selection
        content_group = QGroupBox(tr("plan_content_group"))
        content_layout = QVBoxLayout(content_group)
        
        # Controls to add content
        add_controls_layout = QHBoxLayout()
        
        self.combo_add_type = QComboBox()
        self.combo_add_type.addItems([
            tr("content_type_sura"), 
            tr("content_type_juz"), 
            tr("content_type_page_range"), 
            tr("content_type_ayah_range"), 
            tr("content_type_sura_range")
        ])
        self.combo_add_type.currentIndexChanged.connect(self.update_add_ui)
        
        self.stack_widget = QWidget() # Container for dynamic inputs
        self.stack_layout = QHBoxLayout(self.stack_widget)
        self.stack_layout.setContentsMargins(0,0,0,0)
        
        # Sura Input
        self.combo_sura_select = QComboBox()
        # Populate Suras
        sorted_suras = sorted(self.data_manager.sura_pages.items(), key=lambda item: int(item[0]))
        for sura_no, _ in sorted_suras:
            sura_name = self.data_manager.get_sura_name(sura_no)
            self.combo_sura_select.addItem(f"{sura_no} - {sura_name}", sura_no)
            
        # Juz Input
        self.spin_juz_select = QSpinBox()
        self.spin_juz_select.setRange(1, 30)
        
        # Page Range Input
        self.page_range_widget = QWidget()
        page_layout = QHBoxLayout(self.page_range_widget)
        page_layout.setContentsMargins(0,0,0,0)
        self.spin_from_page = QSpinBox()
        self.spin_from_page.setRange(1, 604)
        self.spin_to_page = QSpinBox()
        self.spin_to_page.setRange(1, 604)
        page_layout.addWidget(QLabel(tr("from_page")))
        page_layout.addWidget(self.spin_from_page)
        page_layout.addWidget(QLabel(tr("to_page")))
        page_layout.addWidget(self.spin_to_page)

        # Range Input (Simplified for space)
        self.btn_add_current_range = QPushButton(tr("add_current_range_btn"))
        
        add_controls_layout.addWidget(self.combo_add_type)
        add_controls_layout.addWidget(self.stack_widget)
        
        self.btn_add_segment = QPushButton(tr("add_to_list"))
        self.btn_add_segment.setStyleSheet("background-color: #E0F7FA; font-weight: bold;")
        self.btn_add_segment.clicked.connect(self.add_segment)
        add_controls_layout.addWidget(self.btn_add_segment)
        
        content_layout.addLayout(add_controls_layout)
        
        # List of added segments with ordering buttons
        list_container = QWidget()
        list_layout = QHBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self.segments_list = QListWidget()
        list_layout.addWidget(self.segments_list)
        
        btns_layout = QVBoxLayout()
        self.btn_move_up = QPushButton("🔼")
        self.btn_move_up.clicked.connect(self.move_segment_up)
        self.btn_move_down = QPushButton("🔽")
        self.btn_move_down.clicked.connect(self.move_segment_down)
        self.btn_delete_segment = QPushButton("🗑️")
        self.btn_delete_segment.clicked.connect(self.delete_segment)
        self.btn_sort_segments = QPushButton(tr("sort_list"))
        self.btn_sort_segments.setToolTip(tr("sort_tooltip"))
        self.btn_sort_segments.clicked.connect(self.sort_segments)
        
        btns_layout.addWidget(self.btn_move_up)
        btns_layout.addWidget(self.btn_move_down)
        btns_layout.addWidget(self.btn_sort_segments)
        btns_layout.addWidget(self.btn_delete_segment)
        btns_layout.addStretch()
        
        list_layout.addLayout(btns_layout)
        content_layout.addWidget(list_container)
        
        layout.addWidget(content_group)

        if not self.content_only:
            # 3. Schedule Settings
            schedule_group = QGroupBox(tr("schedule_settings_group"))
            schedule_layout = QVBoxLayout(schedule_group)
            
            # Calculation Mode
            calc_mode_layout = QHBoxLayout()
            self.combo_calc_mode = QComboBox()
            self.combo_calc_mode.addItems([tr("calc_method_daily_amount"), tr("calc_method_duration")])
            self.combo_calc_mode.currentIndexChanged.connect(self.update_schedule_ui)
            calc_mode_layout.addWidget(QLabel(tr("calc_method")))
            calc_mode_layout.addWidget(self.combo_calc_mode)
            schedule_layout.addLayout(calc_mode_layout)

            # Amount / Duration Inputs
            amount_layout = QHBoxLayout()
            self.lbl_amount_duration = QLabel(tr("daily_amount"))
            
            self.spin_daily_amount = QDoubleSpinBox()
            self.spin_daily_amount.setRange(0.25, 100.0)
            self.spin_daily_amount.setSingleStep(0.25)
            self.spin_daily_amount.setValue(2.0)
            self.spin_daily_amount.setSuffix(tr("suffix_page"))
            
            self.spin_duration_days = QSpinBox()
            self.spin_duration_days.setRange(1, 3650)
            self.spin_duration_days.setValue(30)
            self.spin_duration_days.setSuffix(tr("suffix_work_day"))
            self.spin_duration_days.hide()

            amount_layout.addWidget(self.lbl_amount_duration)
            amount_layout.addWidget(self.spin_daily_amount)
            amount_layout.addWidget(self.spin_duration_days)
            schedule_layout.addLayout(amount_layout)

            # Active Days
            days_group = QGroupBox(tr("active_days_group"))
            days_layout = QHBoxLayout(days_group)
            self.days_checkboxes = []
            # Mapping: Mon=1..Sun=7 (Qt). We map checkboxes to these values.
            # Order in UI: Sat, Sun, Mon, Tue, Wed, Thu, Fri
            days_names = [
                (tr("saturday"), 6), (tr("sunday"), 7), (tr("monday"), 1),
                (tr("tuesday"), 2), (tr("wednesday"), 3), (tr("thursday"), 4), (tr("friday"), 5)
            ]
            
            for name, qt_day_idx in days_names:
                chk = QCheckBox(name)
                chk.setChecked(True) # Default all active
                chk.setProperty("day_idx", qt_day_idx)
                days_layout.addWidget(chk)
                self.days_checkboxes.append(chk)
            
            schedule_layout.addWidget(days_group)
            layout.addWidget(schedule_group)

        # 4. Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        # Translate standard buttons
        btn_box.button(QDialogButtonBox.Ok).setText(tr("ok"))
        btn_box.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)
        
        # --- Populate Data if Editing ---
        if self.plan_data:
            self.populate_from_plan(self.plan_data)
        else:
            self.update_add_ui() # Init UI

    def toggle_repetition_ui(self, index):
        is_rep = (self.type_combo.currentData() == "repetition")
        self.rep_target_widget.setVisible(is_rep)

    def populate_from_plan(self, plan):
        """Fills the dialog fields with existing plan data."""
        if not self.content_only:
            self.name_input.setText(plan.get('name', ''))
            idx = self.type_combo.findData(plan.get('type', 'memorization'))
            if idx >= 0: self.type_combo.setCurrentIndex(idx)
            
            # Start date (reset to today for simplicity or keep original?)
            # Usually when editing, we might want to reschedule from today or keep original start.
            # Let's keep today as default for rescheduling, or use the first key in schedule.
            self.start_date_input.setDate(QDate.currentDate())
            
            self.chk_auto_repeat.setChecked(plan.get('auto_repeat', False))
            
            self.spin_target_reps.setValue(plan.get('target_repetitions', 30))
            self.toggle_repetition_ui(0)
            
            # Schedule settings
            # We don't know exact mode from plan dict easily unless we saved it.
            # Assuming we saved 'daily_amount_calculated' and 'duration_days' logic.
            # For now, default to Amount mode with the calculated amount.
            daily_amt = plan.get('daily_amount_calculated', 2.0)
            self.spin_daily_amount.setValue(daily_amt)
            
            # Active days
            active_days = set(plan.get('active_days', [1,2,3,4,5,6,7]))
            for chk in self.days_checkboxes:
                chk.setChecked(chk.property("day_idx") in active_days)

        # Segments
        self.segments = list(plan.get('segments', []))
        self.segments_list.clear()
        for seg in self.segments:
            txt = ""
            if seg['type'] == 'sura': txt = f"سورة: {seg.get('name', seg['val'])}"
            elif seg['type'] == 'juz': txt = f"جزء: {seg['val']}"
            elif seg['type'] == 'page_range': txt = f"صفحات: {seg['from']} إلى {seg['to']}"
            elif seg['type'] == 'surah_range':
                d = "تصاعدي" if seg.get('from_sura') <= seg.get('to_sura') else "تنازلي"
                txt = f"نطاق سور: {seg.get('from_name')} ⬅ {seg.get('to_name')} ({d})"
            else: txt = "النطاق المحدد حالياً"
            self.segments_list.addItem(txt)

        self.update_add_ui() # Init UI

    def update_add_ui(self):
        # Clear layout
        for i in reversed(range(self.stack_layout.count())): 
            self.stack_layout.itemAt(i).widget().setParent(None)
            
        mode_idx = self.combo_add_type.currentIndex()
        if mode_idx == 0: # Sura
            self.stack_layout.addWidget(self.combo_sura_select)
        elif mode_idx == 1: # Juz
            self.stack_layout.addWidget(QLabel(self.tr_func("juz") + ":"))
            self.stack_layout.addWidget(self.spin_juz_select)
        elif mode_idx == 2: # Page Range
            self.stack_layout.addWidget(self.page_range_widget)
        elif mode_idx == 3: # Ayah Range
            # NEW: Full controls for Ayah Range inside the dialog
            self.ayah_range_widget = QWidget()
            ar_layout = QGridLayout(self.ayah_range_widget)
            ar_layout.setContentsMargins(0,0,0,0)
            
            self.combo_plan_from_sura = QComboBox()
            self.spin_plan_from_aya = QSpinBox()
            self.spin_plan_from_aya.setRange(1, 286)
            
            self.combo_plan_to_sura = QComboBox()
            self.spin_plan_to_aya = QSpinBox()
            self.spin_plan_to_aya.setRange(1, 286)
            
            # Populate Suras
            sorted_suras = sorted(self.data_manager.sura_pages.items(), key=lambda item: int(item[0]))
            for sura_no, _ in sorted_suras:
                sura_name = self.data_manager.get_sura_name(sura_no)
                item_text = f"{sura_no} - {sura_name}"
                self.combo_plan_from_sura.addItem(item_text, sura_no)
                self.combo_plan_to_sura.addItem(item_text, sura_no)
            
            # Connect signals
            self.combo_plan_from_sura.currentIndexChanged.connect(self._update_plan_from_aya_limit)
            self.combo_plan_to_sura.currentIndexChanged.connect(self._update_plan_to_aya_limit)
            
            ar_layout.addWidget(QLabel(self.tr_func("from")), 0, 0)
            ar_layout.addWidget(self.combo_plan_from_sura, 0, 1)
            ar_layout.addWidget(self.spin_plan_from_aya, 0, 2)
            
            ar_layout.addWidget(QLabel(self.tr_func("to")), 1, 0)
            ar_layout.addWidget(self.combo_plan_to_sura, 1, 1)
            ar_layout.addWidget(self.spin_plan_to_aya, 1, 2)
            
            self.stack_layout.addWidget(self.ayah_range_widget)
            
            # Init limits
            self._update_plan_from_aya_limit()
            self._update_plan_to_aya_limit()

        elif mode_idx == 4: # Sura Range
            self.combo_sura_start_range = QComboBox()
            self.combo_sura_end_range = QComboBox()
            
            # Populate with Surahs
            sorted_suras = sorted(self.data_manager.sura_pages.items(), key=lambda item: int(item[0]))
            for sura_no, _ in sorted_suras:
                sura_name = self.data_manager.get_sura_name(sura_no)
                item_text = f"{sura_no} - {sura_name}"
                self.combo_sura_start_range.addItem(item_text, sura_no)
                self.combo_sura_end_range.addItem(item_text, sura_no)
            
            # Default: 1 to 114
            self.combo_sura_end_range.setCurrentIndex(113) # Index 113 is Surah 114
            
            self.stack_layout.addWidget(QLabel(self.tr_func("from")))
            self.stack_layout.addWidget(self.combo_sura_start_range)
            self.stack_layout.addWidget(QLabel(self.tr_func("to")))
            self.stack_layout.addWidget(self.combo_sura_end_range)

    def _update_plan_from_aya_limit(self):
        sura_no = self.combo_plan_from_sura.currentData()
        if sura_no in self.data_manager.sura_aya_counts:
            max_ayas = self.data_manager.sura_aya_counts[sura_no]
            self.spin_plan_from_aya.setRange(1, max_ayas)

    def _update_plan_to_aya_limit(self):
        sura_no = self.combo_plan_to_sura.currentData()
        if sura_no in self.data_manager.sura_aya_counts:
            max_ayas = self.data_manager.sura_aya_counts[sura_no]
            self.spin_plan_to_aya.setRange(1, max_ayas)
            self.spin_plan_to_aya.setValue(max_ayas)

    def add_segment(self):
        mode_idx = self.combo_add_type.currentIndex()
        segment = {}
        display_text = ""
        
        if mode_idx == 0: # Sura
            sura_no = self.combo_sura_select.currentData()
            sura_name = self.combo_sura_select.currentText()
            start_p = self.data_manager.sura_pages.get(sura_no, 999)
            segment = {'type': 'sura', 'val': sura_no, 'name': sura_name, 'start_page': start_p}
            display_text = f"{self.tr_func('sura')}: {sura_name}"
            
        elif mode_idx == 1: # Juz
            juz_no = self.spin_juz_select.value()
            start_p = self.data_manager.juz_pages.get(juz_no, 999)
            segment = {'type': 'juz', 'val': juz_no, 'start_page': start_p}
            display_text = f"{self.tr_func('juz')}: {juz_no}"
            
        elif mode_idx == 2: # Page Range
            p_from = self.spin_from_page.value()
            p_to = self.spin_to_page.value()
            start_p = min(p_from, p_to)
            segment = {'type': 'page_range', 'from': start_p, 'to': max(p_from, p_to), 'start_page': start_p}
            display_text = f"{self.tr_func('pages')}: {segment['from']} {self.tr_func('to')} {segment['to']}"

        elif mode_idx == 3: # Ayah Range
            if hasattr(self, 'combo_plan_from_sura'):
                s1 = self.combo_plan_from_sura.currentData()
                a1 = self.spin_plan_from_aya.value()
                s2 = self.combo_plan_to_sura.currentData()
                a2 = self.spin_plan_to_aya.value()
                
                mw = self.parent()
                p1 = 1
                if mw and hasattr(mw, 'get_page_for_sura_aya'):
                    p1 = mw.get_page_for_sura_aya(s1, a1) or 1
                
                segment = {
                    'type': 'verse_range', 
                    'from_sura': s1, 'from_aya': a1,
                    'to_sura': s2, 'to_aya': a2,
                    'start_page': p1
                }
                
                s1_txt = self.combo_plan_from_sura.currentText().split(' - ')[-1]
                s2_txt = self.combo_plan_to_sura.currentText().split(' - ')[-1]
                display_text = f"{self.tr_func('ayahs')}: {s1_txt} ({a1}) ⬅ {s2_txt} ({a2})"
            else:
                segment = {'type': 'current_selection', 'start_page': 0}
                display_text = self.tr_func("current_selection")

        elif mode_idx == 4: # Sura Range
            s1 = self.combo_sura_start_range.currentData()
            s2 = self.combo_sura_end_range.currentData()
            n1 = self.combo_sura_start_range.currentText().split('-')[1].strip()
            n2 = self.combo_sura_end_range.currentText().split('-')[1].strip()
            start_p = self.data_manager.sura_pages.get(s1, 1)
            segment = {'type': 'surah_range', 'from_sura': s1, 'to_sura': s2, 'from_name': n1, 'to_name': n2, 'start_page': start_p}
            dir_text = self.tr_func("ascending") if s1 <= s2 else self.tr_func("descending")
            display_text = f"{self.tr_func('sura_range')}: {n1} ⬅ {n2} ({dir_text})"

        self.segments.append(segment)
        self.segments_list.addItem(display_text)

    def delete_segment(self):
        row = self.segments_list.currentRow()
        if row >= 0:
            self.segments_list.takeItem(row)
            del self.segments[row]

    def move_segment_up(self):
        row = self.segments_list.currentRow()
        if row > 0:
            item = self.segments_list.takeItem(row)
            self.segments_list.insertItem(row - 1, item)
            self.segments_list.setCurrentRow(row - 1)
            # Swap in data list
            self.segments[row], self.segments[row - 1] = self.segments[row - 1], self.segments[row]

    def move_segment_down(self):
        row = self.segments_list.currentRow()
        if row < self.segments_list.count() - 1 and row != -1:
            item = self.segments_list.takeItem(row)
            self.segments_list.insertItem(row + 1, item)
            self.segments_list.setCurrentRow(row + 1)
            # Swap in data list
            self.segments[row], self.segments[row + 1] = self.segments[row + 1], self.segments[row]

    def sort_segments(self):
        """Sorts segments based on their start page."""
        self.segments.sort(key=lambda x: x.get('start_page', 999))
        self.segments_list.clear()
        for seg in self.segments:
            txt = ""
            if seg['type'] == 'sura': txt = f"{self.tr_func('sura')}: {seg.get('name', seg['val'])}"
            elif seg['type'] == 'juz': txt = f"{self.tr_func('juz')}: {seg['val']}"
            elif seg['type'] == 'page_range': txt = f"{self.tr_func('pages')}: {seg['from']} {self.tr_func('to')} {seg['to']}"
            elif seg['type'] == 'surah_range':
                d = self.tr_func("ascending") if seg.get('from_sura') <= seg.get('to_sura') else self.tr_func("descending")
                txt = f"{self.tr_func('sura_range')}: {seg.get('from_name')} ⬅ {seg.get('to_name')} ({d})"
            elif seg['type'] == 'verse_range':
                s1_name = self.data_manager.get_sura_name(seg.get('from_sura'))
                s2_name = self.data_manager.get_sura_name(seg.get('to_sura'))
                txt = f"{self.tr_func('ayahs')}: {s1_name} ({seg.get('from_aya')}) ⬅ {s2_name} ({seg.get('to_aya')})"
            else: txt = self.tr_func("current_selection")
            self.segments_list.addItem(txt)

    def update_schedule_ui(self):
        mode = self.combo_calc_mode.currentIndex()
        if mode == 0: # Daily Amount
            self.lbl_amount_duration.setText(self.tr_func("daily_amount"))
            self.spin_daily_amount.show()
            self.spin_duration_days.hide()
        else: # Duration
            self.lbl_amount_duration.setText(self.tr_func("work_days_count"))
            self.spin_daily_amount.hide()
            self.spin_duration_days.show()

    def get_data(self):
        if self.content_only:
            return {"segments": self.segments}
            
        active_days = [chk.property("day_idx") for chk in self.days_checkboxes if chk.isChecked()]
        return {
            "name": self.name_input.text() or "خطة جديدة",
            "type": self.type_combo.currentData(),
            "start_date": self.start_date_input.date(),
            "calc_mode": "amount" if self.combo_calc_mode.currentIndex() == 0 else "duration",
            "daily_pages": self.spin_daily_amount.value(),
            "duration_days": self.spin_duration_days.value(),
            "segments": self.segments,
            "active_days": active_days,
            "auto_repeat": self.chk_auto_repeat.isChecked(),
            "target_repetitions": self.spin_target_reps.value()
        }

# ---------- Main Application ----------
class QuranCanvasApp(QWidget):
    # --- FIX: Use a signal for thread-safe communication ---
    update_toast_signal = pyqtSignal(str, bool) # NEW: Signal for toast updates from threads
    # NEW: Signal for thread-safe ayah highlighting from VLC thread
    ayah_highlight_signal = pyqtSignal(object, QColor)
    page_highlight_signal = pyqtSignal(int, QColor)
    # NEW: Signal for thread-safe page turning from VLC thread
    page_turn_signal = pyqtSignal(int)

    # NEW SIGNALS FOR HINT LABELS
    update_ayah_count_signal = pyqtSignal(str, str)
    update_duration_signal = pyqtSignal(str, str)
    update_repetition_signal = pyqtSignal(str, str)
    update_clock_signal = pyqtSignal(str, str, str) # Time, Next Prayer Name, Remaining Time
    prayer_times_updated_signal = pyqtSignal() # NEW: Signal when prayer times are recalculated

    # NEW: Signals for report generation
    report_ready = pyqtSignal(str)
    display_report_ready = pyqtSignal(str)
    reset_playback_reveal_signal = pyqtSignal()
    azan_finished_signal = pyqtSignal() # إشارة انتهاء الأذان
    duaa_finished_signal = pyqtSignal() # إشارة انتهاء الدعاء

    def __init__(self, splash=None):
        # print("DEBUG: 1 - بدء تهيئة QuranCanvasApp")
        super().__init__()  # Call the constructor of the parent class (QWidget)
        self.splash = splash
        if self.splash:
            self.splash.showMessage("جاري تهيئة التطبيق...", Qt.AlignHCenter | Qt.AlignBottom, QColor("#FFFFFF"))
            QApplication.processEvents()

        # print("DEBUG: 2 - بعد استدعاء super().__init__()")

        self.permanent_toast_message = ""

        if self.splash:
            self.splash.showMessage("جاري تحميل الإعدادات والبيانات...", Qt.AlignHCenter | Qt.AlignBottom, QColor("#FFFFFF"))
            QApplication.processEvents()
            
        # --- NEW: Load Bundled Default Settings Logic ---
        self.settings = {}
        
        # 1. Try to load bundled defaults (Your custom settings file)
        try:
            bundled_defaults_path = resource_path("default_settings.json")
            if os.path.exists(bundled_defaults_path):
                with open(bundled_defaults_path, 'r', encoding='utf-8') as f:
                    self.settings = json.load(f)
                    # print(f"Loaded bundled default settings from: {bundled_defaults_path}")
        except Exception as e:
            pass # print(f"Note: No bundled default settings found or error: {e}")

        # 2. Load user settings (overrides defaults if exists)
        user_settings = load_settings()
        if user_settings:
            self.settings.update(user_settings)

        # --- NEW: Language and Translation Setup ---
        self.language = self.settings.get("app_language", "ar")
        self.translations = TRANSLATIONS.get(self.language, TRANSLATIONS["ar"]) # Fallback to Arabic

        self.data_manager = QuranDataManager()
        self.wake_lock = WakeLock()

        # --- NEW: Initialize Managers ---
        self.user_manager = UserManager()
        self.info_manager = QuranInfoManager()
        
        # Restore last user and plans
        last_user = self.settings.get("last_user")
        if last_user:
            self.user_manager.current_user = last_user
            self.plans = self.user_manager.get_plans(last_user)
        else:
            # Default to Guest if no user found to ensure features work
            self.user_manager.current_user = "Guest"
            self.user_manager.add_user("Guest")
            self.plans = []

        # --- NEW: Build a (sura, aya) -> page map for fast lookups ---
        self.sura_aya_to_page_map = {}
        if hasattr(self.data_manager, 'pages_by_number'):
            for page_num, ayahs_on_page in self.data_manager.pages_by_number.items():
                for ayah_info in ayahs_on_page:
                    sura = ayah_info.get('sura_no')
                    aya = ayah_info.get('aya_no')
                    if sura is not None and aya is not None:
                        if (sura, aya) not in self.sura_aya_to_page_map:
                            self.sura_aya_to_page_map[(sura, aya)] = int(page_num)
        # --- END NEW --- 
        self.setWindowTitle(self.tr("app_title") + " - Light")
                # --- NEW: Window Icon Animation ---
        self.icon_paths = [
            resource_path("assets/icon.ico"),
            resource_path("assets/icon1.ico"),
            resource_path("assets/icon2.ico"),
            resource_path("assets/icon3.ico")
        ]
        self.icon_objects = [QIcon(p) for p in self.icon_paths if os.path.exists(p)]
        self.icon_index = 0
        
        # Set initial icon
        if self.icon_objects:
            self.setWindowIcon(self.icon_objects[self.icon_index])
        else:
            # Fallback to the original logo if no icons found
            self.setWindowIcon(QIcon(resource_path("assets/logo.png")))

        self.icon_animation_timer = QTimer(self)
        self.icon_animation_timer.setInterval(2000) # 2 seconds
        self.icon_animation_timer.timeout.connect(self._update_window_icon)
        if len(self.icon_objects) > 1:
            self.icon_animation_timer.start()

        # --- NEW: Prayer Times Initialization ---
        self.latitude = self.settings.get("latitude", 30.0444) # Default Cairo
        self.longitude = self.settings.get("longitude", 31.2357)
        self.prayer_times = {}
        self.next_prayer_name = "--"
        self.last_triggered_prayer_time = None # NEW: Prevent double Azan trigger
        self.next_prayer_time = None
        self.azan_folder = resource_path("sounds/azan")
        
        # Clock Timer (Updates every second)
        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1000)
        self.clock_timer.timeout.connect(self._update_clock_and_prayers)
        # self.clock_timer.start() # Moved to end of __init__ to prevent early firing

        # --- NEW: Desktop Prayer Widget ---
        self.prayer_widget = PrayerDesktopWidget(self)
        # Load position
        pos = self.settings.get("prayer_widget_pos")
        if pos and isinstance(pos, list) and len(pos) == 2:
            self.prayer_widget.move(QPoint(pos[0], pos[1]))
        # Show based on setting
        if self.settings.get("show_prayer_widget_on_startup", True):
            self.prayer_widget.show()

        # Connect the signal
        self.update_clock_signal.connect(self.prayer_widget.update_times)
        self.prayer_times_updated_signal.connect(self.prayer_widget.refresh_list)


        # Location Worker
        self.location_worker = LocationWorker()
        self.location_worker.location_found.connect(self._on_location_found)
        self.location_worker.location_failed.connect(self._on_location_failed)

        # load font
        # Initialize internal state variables, loading from settings or using
        # defaults
        self.current_page = 1
        self.rendered_sura_headers = set()
        self.recited_pages = set()
        self.recording = False
        self.recording_mode = False
        self.is_review_mode = False
        self.elapsed_recitation_time = 0
        self.session_debug_log = []
        self._word_statuses = []
        self.recitation_idx_map = {}
        
        self.recitation_duration_timer = QTimer(self)
        self.recitation_duration_timer.setInterval(1000) # 1 second interval
        self.recitation_duration_timer.timeout.connect(self._update_recitation_timer)
        self.azan_timer = QTimer(self)
        self.auto_reveal_timer = QTimer(self)
        self.auto_reveal_timer.timeout.connect(self._on_auto_reveal_tick) # ربط المؤقت بدالة التنفيذ

        # --- NEW: Voice Triggered Review Timers ---
        self.voice_monitor_timer = QTimer(self)
        self.voice_monitor_timer.setInterval(50) # Check volume every 50ms
        self.voice_monitor_timer.timeout.connect(self._on_voice_monitor_tick)
        self.voice_reveal_timer = QTimer(self) # Timer for revealing words
        self.voice_reveal_timer.timeout.connect(self._on_voice_reveal_tick)
        self.current_voice_volume = 0 # Initialize volume

        # --- FIX: Initialize Debounce Timers to prevent crash on input ---
        self.page_input_debounce_timer = QTimer(self)
        self.page_input_debounce_timer.setSingleShot(True)
        self.page_input_debounce_timer.setInterval(800)
        self.page_input_debounce_timer.timeout.connect(self._perform_page_input_update)

        self.juz_input_debounce_timer = QTimer(self)
        self.juz_input_debounce_timer.setSingleShot(True)
        self.juz_input_debounce_timer.setInterval(800)
        self.juz_input_debounce_timer.timeout.connect(self._perform_juz_input_update)

        # --- Playlist / VLC Integration Variables (Moved to top) ---
        self.vlc_instance = None
        self.media_player = None
        self.list_player = None
        self.event_manager = None
        self.main_audio_folder = ""
        self.output_folder = ""
        self.files_list = []
        self.start_file = ""
        self.end_file = ""
        self.range_start_ref = None  # (sura, aya) for highlighting
        self.range_end_ref = None   # (sura, aya) for highlighting
        self.last_active_ayah_ref = None  # (sura, aya) for highlighting
        self.last_highlighted_page = None # NEW: To track which page was last highlighted
        self.last_yellow_highlighted_page = None # NEW: To track the currently yellow-highlighted page
        self._active_ayah_highlight_ref = None # NEW: Stores the (sura, aya) of the currently playing ayah for yellow highlight
        self._highlighted_range_ayats = [] # NEW: To keep track of ayahs currently highlighted in a range
        self._pending_word_highlights = {} # NEW: Stores global_idx:color mappings for words to be highlighted on render
        self.playlist_with_reps = []
        self.current_playlist_index = -1
        self.AVERAGE_AYAH_DURATION_S = 7  # For time estimation
        self.last_estimate_mode = 'COMPLEX'

        # NEW: Playlist-related attributes
        self.selected_reciter_name = ""
        self.selected_reciter_path = ""
        self.reciter_file_system = 'ayah_based'  # NEW: To track reciter's file system ('ayah_based' or 'sura_based')
        self.media_list = None  # VLC media list object

        # Initial app-wide background, possibly overridden by page_bg_color
        self.bg_color = DEFAULT_BG_COLOR
        # NEW: Use the specific default scale from main(), but only if not in
        # settings
        default_scale = 1.0 / (1.1 ** 3)
        self.scale_factor = self.settings.get(
    "scale_factor", default_scale)  # Load or default zoom level
        self.view_mode = self.settings.get("view_mode", "two_pages")  # Load view mode

        # graphics scene/view - Initialize early to prevent resize errors
        # --- FIX: Initialize scene and view BEFORE PageRenderer ---
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)

        # --- NEW: Toast Label for on-screen notifications ---
        self.toast_label = DraggableLabel(self.view) # Child of the view
        self.toast_label.setAlignment(Qt.AlignCenter)
        self.toast_label.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 249, 196, 240); /* Semi-transparent yellow */
                color: #C0392B; /* Red text */
                font-size: 20px;
                font-weight: bold;
                padding: 8px;
                border: 2px solid #F1C40F; /* Gold border */
                border-radius: 8px;
            }
        """)
        # Add a drop shadow for better visibility
        shadow = QGraphicsDropShadowEffect(self.toast_label)
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(5, 5)
        self.toast_label.setGraphicsEffect(shadow)
        self.toast_label.hide()

        # --- NEW: Restore Toast Position ---
        toast_x = self.settings.get("toast_x")
        toast_y = self.settings.get("toast_y")
        if toast_x is not None and toast_y is not None:
            self.toast_label.move(int(toast_x), int(toast_y))
            self.toast_label.user_has_moved = True

        # --- NEW: Initialize the PageRenderer ---
        self.page_renderer = PageRenderer(self)
        # حقن دالة إصلاح النص في الكائن لسهولة الاستخدام داخل PageRenderer
        self.page_renderer.fix_arabic_display = fix_arabic_display
        
        # NEW: Load and apply saved border image path
        loaded_border_image_path = self.settings.get("border_image_path", "assets/page_border17.png")
        if loaded_border_image_path:
            self._apply_border_image_to_renderer(loaded_border_image_path)
        else:
            self.page_renderer.border_pixmap = None # Ensure it's explicitly None if no setting

        self.view.setRenderHints(
    QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.view.setOptimizationFlag(
    QGraphicsView.DontAdjustForAntialiasing, True)
        self.view.setOptimizationFlag(QGraphicsView.DontSavePainterState, True)

        # --- NEW: Enable Scrollbars as needed (Horizontal & Vertical) ---
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # use QPainter.Antialiasing for render hints
        self.view.setRenderHints(
    self.view.renderHints() | QPainter.Antialiasing)
        # NEW: Use saved font family or default
        self.quran_text_display_font_family = self.settings.get(
            "quran_text_display_font_family", "Arabic Typesetting")
        self.font_weight = self.settings.get(
            "font_weight", QFont.Bold) # NEW: Load font weight
        # NEW: Separate font sizes for static and dynamic modes
        self.static_font_size = self.settings.get("static_font_size", 60)
        self.dynamic_font_size = self.settings.get("dynamic_font_size", 48) # Default dynamic to a larger size

        self._load_font()

        # If a font family was loaded from resource_path and it's not the saved one,
        # prioritize the loaded one for the initial display. This ensures that
        # if the user chooses a custom font that isn't built into the app's font folder,
        # it doesn't override the built-in one if available.
        # However, for quran_text_display_font_family, if it was specified by the user
        # through settings, we should use that, otherwise use the default
        # loaded one.
        if not self.quran_text_display_font_family and QURAN_TEXT_DISPLAY_FONT_FILE:
            # This handles the case where there is no saved setting yet, or the saved font couldn't be loaded.
            # We then default to whatever _load_font successfully provided from QURAN_TEXT_DISPLAY_FONT_FILE.
            # We need to make sure _load_font actually loads this value into self.quran_text_display_font_family
            # which it currently does. So, after _load_font, if settings didn't
            # provide one, use the loaded default.
            # No direct change needed here, as _load_font already sets it if it
            # wasn't set by settings.
            pass

        # Ensure quran_text_display_font_family is correctly set, either from settings or default.
        # _load_font will attempt to load the default font into this variable.
        # If settings already set it, _load_font will load the default then it will be overwritten.
        # This order is slightly problematic. Let's adjust _load_font to be
        # more conditional.

        # Set the main UI font_family (self.font_family) to the loaded general Quran text font, or fallback
        # --- REMOVED FALLBACK LOGIC ---
        # The application will now rely exclusively on the fonts loaded from the files.
        # If a font fails to load, its corresponding family string will be empty,
        # which makes debugging easier.
        self.font_family = self.quran_text_font_family

        # NEW: Ratio for Ayah number font size relative to the main font size
        self.ayah_font_size_ratio = 1.0  # Ratio for Ayah number font size

        self.justify_text = self.settings.get("justify_text", True)
        self.hide_text_during_recitation = self.settings.get("hide_text_during_recitation", False)

        # --- NEW: Dynamic Mode Word Spacing ---
        # التحكم في المسافة بين الكلمات في الوضع الديناميكي (بالبكسل)
        # القيمة الافتراضية هنا 5 لتقليل المسافة (يمكنك تعديلها حسب رغبتك)
        self.dynamic_word_spacing = self.settings.get("dynamic_word_spacing", 5)

        self.page_bg_color = QColor(
    self.settings.get(
        "page_bg_color",
         "#FFFFFF"))  # Load or default page background color
        
        # --- NEW: Load Text Color (Default is Black) ---
        self.quran_text_color = QColor(self.settings.get("quran_text_color", "#000000"))
        # --- NEW: Review Text Color (Default is Green) ---
        self.review_text_color = QColor(self.settings.get("review_text_color", "#008000"))

        # --- NEW: Highlight Colors Definition ---
        self.highlight_colors = {
            "yellow": QColor(255, 255, 0, 150),
            "green": QColor(0, 255, 0, 150),
            "blue": QColor(0, 0, 255, 150),
            "red": QColor(255, 0, 0, 150),
            "orange": QColor(255, 165, 0, 150),
            "purple": QColor(128, 0, 128, 150)
        }
        self.playlist_highlight_color = self.highlight_colors.get(self.settings.get("highlight_color_key", "yellow"), self.highlight_colors["yellow"])

        # Apply to view background
        self.view.setBackgroundBrush(QBrush(self.page_bg_color))

        self.playback_review_mode = False # NEW: Flag for Playback Review Mode
        self.revealed_ayahs_in_playback = set() # NEW: Track revealed ayahs
        self.revealed_pages_in_playback = set() # NEW: Track revealed pages
        self.show_aya_markers = self.settings.get(

            "show_aya_markers", True)
        
        # --- NEW: Use UiBuilder to build controls ---
        self.ui_builder = UiBuilder(self)

        # Type hints for widgets created by UiBuilder, to help Pylance
        self.btn_start: Optional[QPushButton] = None
        self.btn_stop: Optional[QPushButton] = None
        self.btn_review: Optional[QPushButton] = None
        self.btn_find_verse: Optional[QPushButton] = None
        self.btn_voice_command: Optional[QPushButton] = None
        self.voice_command_status_label: Optional[QLabel] = None
        self.combo_input_device: Optional[QComboBox] = None
        self.combo_output_device: Optional[QComboBox] = None
        self.btn_copy_recognized_text: Optional[QPushButton] = None
        self.btn_copy_report: Optional[QPushButton] = None
        # For settings
        self.btn_toggle_aya_markers: Optional[QPushButton] = None
        # NEW: For justify text checkbox
        self.check_justify_text: Optional[QCheckBox] = None
        # NEW: For ending the session
        self.btn_end_session: Optional[QPushButton] = None
        
        # Navigation widgets (Initialize to None to avoid AttributeError)
        self.combo_sura: Optional[QComboBox] = None
        self.combo_from_sura: Optional[QComboBox] = None
        self.spin_from_aya: Optional[QSpinBox] = None
        self.combo_to_sura: Optional[QComboBox] = None
        self.spin_to_aya: Optional[QSpinBox] = None
        self.juz_input: Optional[QLineEdit] = None
        
        # Review Tab Widgets
        self.combo_review_from_sura: Optional[QComboBox] = None
        self.spin_review_from_aya: Optional[QSpinBox] = None
        self.combo_review_to_sura: Optional[QComboBox] = None
        self.spin_review_to_aya: Optional[QSpinBox] = None
        self.spin_review_repetitions: Optional[QSpinBox] = None
        self.spin_auto_reveal_pause: Optional[QDoubleSpinBox] = None
        self.btn_auto_reveal_stop: Optional[QPushButton] = None
        self.combo_language: Optional[QComboBox] = None
        self.combo_highlight_color: Optional[QComboBox] = None

        # print("DEBUG: 3 - قبل بناء عناصر التحكم")
        self.volume_slider: Optional[QSlider] = None
        self.volume_label: Optional[QLabel] = None

        if self.splash:
            self.splash.showMessage("جاري بناء الواجهة الرسومية...", Qt.AlignHCenter | Qt.AlignBottom, QColor("#FFFFFF"))
            QApplication.processEvents()
        self.ui_builder.build_controls()
        
        # --- FIX: Prevent Spacebar from clicking buttons (Focus Policy) ---
        if hasattr(self, 'btn_auto_reveal_start') and self.btn_auto_reveal_start:
            self.btn_auto_reveal_start.setFocusPolicy(Qt.NoFocus)
        if hasattr(self, 'btn_auto_reveal_stop') and self.btn_auto_reveal_stop:
            self.btn_auto_reveal_stop.setFocusPolicy(Qt.NoFocus)

        # --- NEW: Add Voice Trigger UI to Review Tab ---
        self.setup_voice_trigger_ui()
        # print("DEBUG: 4 - بعد بناء عناصر التحكم")


        # --- NEW: Initialize Audio Device Selection ---
        self.input_device_index = None
        self.output_device_id = None

        # Populate audio devices now that the UI is ready
        # Use QTimer to ensure UI is fully built before populating
        # --- NEW: Volume Slider Customization (200% + Gradient) ---
        if hasattr(self, 'volume_slider') and self.volume_slider:
            self.volume_slider.setMaximum(200)  # Increase max volume to 200%
            
            # Apply gradient stylesheet for visual warning
            # Green (Safe) -> Yellow (Caution) -> Red (High/Distortion)
            self.volume_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    border: 1px solid #bbb;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #C0392B,       /* Red */
                        stop:0.5 #F1C40F,     /* Yellow */
                        stop:1.0 #27AE60);    /* Green */
                    height: 10px;
                    border-radius: 5px;
                }

                QSlider::sub-page:horizontal {
                    background: transparent; /* Show groove gradient */
                    border-radius: 5px;
                }

                QSlider::add-page:horizontal {
                    background: #e0e0e0; /* Gray out the unselected part */
                    border-radius: 5px;
                }

                QSlider::handle:horizontal {
                    background: #ffffff;
                    border: 1px solid #777;
                    width: 16px;
                    height: 16px;
                    margin: -4px 0;
                    border-radius: 8px;
                }
            """)

        # --- NEW: Logo Animation ---
        self.logo_paths = [
            resource_path("assets/logo.png"),
            resource_path("assets/logo1.png"),
            resource_path("assets/logo2.png"),
            resource_path("assets/logo3.png")
        ]
        self.logo_pixmaps = [QPixmap(p).scaledToHeight(50, Qt.SmoothTransformation) for p in self.logo_paths if os.path.exists(p)]
        self.logo_index = 0

        # --- NEW: Add Custom Styled Header Label ---
        # إنشاء شريط علوي يحتوي على: العنوان + الساعة (يمين) والآية (يسار)
        self.header_widget = QWidget()
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(10, 5, 10, 5)

        self.logo_label = QLabel()
        if self.logo_pixmaps:
            self.logo_label.setPixmap(self.logo_pixmaps[self.logo_index])
        header_layout.addWidget(self.logo_label)

        self.logo_animation_timer = QTimer(self)
        self.logo_animation_timer.setInterval(2000) # 2 seconds
        self.logo_animation_timer.timeout.connect(self._update_logo)
        if len(self.logo_pixmaps) > 1:
            self.logo_animation_timer.start()

        title_label = QLabel()
        title_label.setText("""
            <div style='font-size: 18pt; font-weight: bold; font-family: "Traditional Arabic", "Segoe UI", sans-serif;'>
                <span style='color: #1E8449;'>برنامج يُسْر</span>
                <span style='color: #BA4A00;'>(YUSR)</span>
            </div>
        """)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)

        # --- NEW: Styled Time and Prayer Labels (User Request) ---
        # Time Label with Frame
        self.header_time_label = QLabel("00:00:00")
        self.header_time_label.setAlignment(Qt.AlignCenter)
        self.header_time_label.setStyleSheet("""
            QLabel {
                background-color: #f9f9f9;
                border: 2px solid #3498db;
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
            }
        """)
        header_layout.addWidget(self.header_time_label)
        
        header_layout.addSpacing(10)

        # Prayer Info Label with Frame
        self.header_next_prayer_label = QLabel("...")
        self.header_next_prayer_label.setAlignment(Qt.AlignCenter)
        self.header_next_prayer_label.setStyleSheet("""
            QLabel {
                background-color: #e8f8f5;
                border: 2px solid #16a085;
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 14px;
                font-weight: bold;
                color: #16a085;
            }
        """)
        header_layout.addWidget(self.header_next_prayer_label)
        header_layout.addStretch(1)

        verse_label = QLabel("( وَلَقَدْ يَسَّرْنَا الْقُرْآنَ لِلذِّكْرِ فَهَلْ مِنْ مُدَّكِرٍ )")
        verse_label.setStyleSheet("color: #145A32; font-size: 16pt; font-weight: bold; font-family: 'Traditional Arabic', 'Amiri';")
        verse_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_layout.addWidget(verse_label)

        if hasattr(self, 'main_layout'):
            self.main_layout.insertWidget(0, self.header_widget)

        self._add_profile_button_to_header()
        self._convert_sidebar_to_collapsible()

        # --- NEW: Move Prayer Controls to Header (User Request) ---
        # نقل زر تحديث الموقع إلى الشريط العلوي وإخفاء المجموعة القديمة لتوفير مساحة
        if hasattr(self, 'btn_update_location') and self.btn_update_location:
            # 1. تحديد الحاوية القديمة (المجموعة في السطر الثاني)
            old_parent = self.btn_update_location.parentWidget()
            
            # 2. الحصول على تخطيط الهيدر
            header_layout = self.header_widget.layout()
            
            # 3. نقل الزر إلى الهيدر (بجانب تسمية الوقت)
            # نضعه بعد تسمية الوقت مباشرة ليكون في المنتصف معها
            idx = header_layout.indexOf(self.header_next_prayer_label)
            if idx != -1:
                header_layout.insertWidget(idx + 1, self.btn_update_location)
            
            # 4. تحسين شكل الزر ليناسب الهيدر
            self.btn_update_location.setText("📍") # أيقونة فقط
            self.btn_update_location.setFixedSize(30, 30)
            self.btn_update_location.setToolTip(self.tr("update_location_tooltip"))
            self.btn_update_location.setCursor(Qt.PointingHandCursor)
            self.btn_update_location.setStyleSheet("QPushButton { background-color: transparent; border: none; font-size: 18px; color: #C0392B; } QPushButton:hover { color: #E74C3C; }")
            
            # 5. إخفاء المجموعة القديمة من السطر الثاني إذا كانت GroupBox
            # هذا سيخفي "مجموعة أوقات الصلاة" بالكامل من السطر الثاني
            if old_parent and isinstance(old_parent, QGroupBox):
                old_parent.hide()

        # --- FIX: Ensure recitation navigation buttons are connected ---
        if hasattr(self, 'btn_rec_next') and self.btn_rec_next:
            try: self.btn_rec_next.clicked.disconnect()
            except: pass
            self.btn_rec_next.clicked.connect(self.on_rec_next_page)

        if hasattr(self, 'btn_rec_prev') and self.btn_rec_prev:
            try: self.btn_rec_prev.clicked.disconnect()
            except: pass
            self.btn_rec_prev.clicked.connect(self.on_rec_prev_page)

        # --- NEW: Initialize Pulse Managers ---
        # Define pulse effects for key active buttons
        # Use getattr to safely access buttons that might not be created by UiBuilder in some contexts
        # REMOVED: self.pulse_stop (User wants active state button to pulse, not stop button)
        self.pulse_recitation = PulseManager(getattr(self, 'btn_start', None), active_color="#A9DFBF", default_color="#2ECC71", parent=self)
        self.pulse_review = PulseManager(getattr(self, 'btn_review', None), active_color="#FFCC80", default_color="#e67e22", parent=self)

        # --- NEW: Pulse for Stop/End buttons as requested ---
        self.pulse_stop = PulseManager(getattr(self, 'btn_stop', None), active_color="#FAD7A0", default_color="#F39C12", parent=self)
        self.pulse_end_session = PulseManager(getattr(self, 'btn_end_session', None), active_color="#F5B7B1", default_color="#E74C3C", parent=self)
        
        self.pulse_calibrate = PulseManager(getattr(self, 'btn_calibrate_noise', None), active_color="#e1f5fe", parent=self) # Blueish
        self.pulse_find = PulseManager(getattr(self, 'btn_find_verse', None), active_color="#fff9c4", parent=self) # Yellowish
        self.pulse_cmd = PulseManager(getattr(self, 'btn_voice_command', None), active_color="#e0f2f1", parent=self) # Greenish

        # --- Playlist Pulse Managers ---
        # Updated with correct default colors from ui_builder.py
        self.pulse_play_single = PulseManager(getattr(self, 'btn_play_single', None), active_color="#A9DFBF", default_color="#27ae60", parent=self)
        self.pulse_play_group = PulseManager(getattr(self, 'btn_play_group', None), active_color="#FAD7A0", default_color="#d68910", parent=self)
        self.pulse_play_complex = PulseManager(getattr(self, 'btn_play_complex', None), active_color="#F5B7B1", default_color="#c0392b", parent=self)
        self.pulse_play_page = PulseManager(getattr(self, 'btn_play_page', None), active_color="#d4edda", parent=self)

        # --- NEW: Pulse for Auto Reveal ---
        self.pulse_auto_reveal = PulseManager(getattr(self, 'btn_auto_reveal_start', None), active_color="#D2B4DE", default_color="#8E44AD", parent=self)
        self.pulse_voice_trigger = None # Will be initialized in setup_voice_trigger_ui

        # --- NEW: Modern CSS for Controls ---
        self.setStyleSheet("""
            /* General Controls */
            QPushButton, QLineEdit, QComboBox, QSpinBox {
                background-color: #ffffff;
                border: 1px solid #dcdcdc;
                border-radius: 6px;
                font-size: 13px;
                color: #333333;
                padding: 5px;
            }
            QPushButton {
                padding: 5px 10px;
            }
            
            /* Hover Effects */
            QPushButton:hover, QLineEdit:hover, QComboBox:hover, QSpinBox:hover {
                background-color: #f0f8ff;
                border-color: #1890ff;
                color: #000000;
            }
            
            /* Pressed/Focus Effects */
            QPushButton:pressed {
                background-color: #d6e4ff;
                border-color: #096dd9;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border-color: #1890ff;
                background-color: #ffffff;
            }
            
            /* Disabled State */
            QPushButton:disabled, QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
                background-color: #f5f5f5;
                color: #b8b8b8;
                border-color: #d9d9d9;
            }

            /* Combo Box Dropdown List (The Menu) */
            QComboBox QAbstractItemView {
                border: 1px solid #dcdcdc;
                background-color: #ffffff;
                selection-background-color: #f0f8ff;
                selection-color: #000000;
                outline: 0px;
                padding: 4px;
            }

            /* Scrollbars - Updated for better visibility */
            QScrollBar:vertical {
                border: none;
                background: #f0f0f0;
                width: 16px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #888888;
                min-height: 20px;
                border-radius: 8px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background: #555555;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QScrollBar:horizontal {
                border: none;
                background: #f0f0f0;
                height: 16px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #888888;
                min-width: 20px;
                border-radius: 8px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            
            /* ScrollArea styling */
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        # --- NEW: Add Surah number prefix to Surah ComboBoxes ---
        # This iterates over the items in the combo boxes and prepends the Surah number
        for combo_name in ['combo_sura', 'combo_from_sura', 'combo_to_sura']:
            combo = getattr(self, combo_name, None)
            if combo:
                for i in range(combo.count()):
                    sura_no = combo.itemData(i)
                    text = combo.itemText(i)
                    if sura_no:
                        combo.setItemText(i, f"{sura_no} - {text}")

                # Enable search/filtering
                combo.setEditable(True)
                combo.setInsertPolicy(QComboBox.NoInsert)
                if combo.completer():
                    combo.completer().setCompletionMode(QCompleter.PopupCompletion)
                    combo.completer().setFilterMode(Qt.MatchContains)

        # --- NEW: Connect Juz Input for Debounced Update ---
        if hasattr(self, 'juz_input') and self.juz_input:
            self.juz_input.textChanged.connect(self.on_juz_input_changed)

        # "Play by Page" button and its logic removed as per user request.

        # The programmatically added hint labels were here. They have been removed as per user request.
        
        # Set main layout for the window
        self.setLayout(self.main_layout)

        # Flag to prevent nav combo updates from fighting user input
        self._user_navigating = False

        # Connect the custom signal to its slot
        self.report_ready.connect(self._finish_report_copy)
        self.display_report_ready.connect(self._show_report_in_dialog)
        # NEW: Connect the highlight signal
        self.ayah_highlight_signal.connect(self._handle_ayah_highlight)
        self.page_highlight_signal.connect(self.apply_highlight_to_page)
        # NEW: Connect the page turn signal
        self.page_turn_signal.connect(self.on_page_changed)
        self.reset_playback_reveal_signal.connect(self._reset_playback_reveal) # NEW
        self.update_toast_signal.connect(self.show_toast) # NEW: Connect toast signal
        self.azan_finished_signal.connect(self.on_azan_finished) # ربط إشارة انتهاء الأذان
        self.duaa_finished_signal.connect(self.stop_azan) # ربط إشارة انتهاء الدعاء

        # --- NEW: State tracking for resuming after Azan ---
        self.was_recording_before_azan = False
        self.was_playlist_playing_before_azan = False

        # --- NEW: Populate Azan File Selectors in Settings ---
        if hasattr(self, 'azan_files_layout'):
            prayers = ["Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"]
            self.azan_file_widgets = {}
            self.azan_labels = {}

            for eng_name in prayers:
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                
                ar_name = self.tr(f"prayer_{eng_name.lower()}")
                lbl = QLabel(f"{ar_name}:")
                lbl.setFixedWidth(50)
                
                path_edit = QLineEdit()
                path_edit.setReadOnly(True)
                path_edit.setPlaceholderText(self.tr("default_random"))
                saved_path = self.settings.get(f"azan_file_{eng_name}", "")
                path_edit.setText(saved_path)
                
                btn_browse = QPushButton("...")
                btn_browse.setFixedWidth(30)
                btn_browse.clicked.connect(lambda checked, p=eng_name: self.browse_azan_file(p))
                
                btn_preview = QPushButton("🔊")
                btn_preview.setFixedWidth(30)
                btn_preview.setToolTip(self.tr("test_azan_sound"))
                btn_preview.clicked.connect(lambda checked, p=eng_name: self.preview_azan_file(p))

                row_layout.addWidget(lbl)
                row_layout.addWidget(path_edit)
                row_layout.addWidget(btn_browse)
                row_layout.addWidget(btn_preview)
                
                self.azan_files_layout.addWidget(row_widget)
                self.azan_file_widgets[eng_name] = path_edit
                self.azan_labels[eng_name] = lbl
            
            # --- NEW: Duaa Checkbox ---
            self.check_enable_duaa = QCheckBox(self.tr("enable_duaa"))
            self.check_enable_duaa.setToolTip(self.tr("enable_duaa_tooltip"))
            self.check_enable_duaa.setChecked(self.settings.get("enable_duaa", False))
            self.check_enable_duaa.toggled.connect(self.on_toggle_duaa)
            self.azan_files_layout.addWidget(self.check_enable_duaa)

        # After building controls, apply loaded settings to widgets
        self.apply_loaded_settings_to_ui()
        
        # --- MOVED VLC INIT TO load_heavy_libraries ---

        # Load settings after the UI is fully built and displayed
        # print("DEBUG: 6 - قبل تحميل إعدادات قائمة التشغيل")
        QTimer.singleShot(100, self.load_playlist_settings)
        
        # Calculate initial prayer times (Moved to load_heavy_libraries)
        
        # --- NEW: Fullscreen Shortcut (F11) ---
        self.shortcut_f11 = QShortcut(QKeySequence(Qt.Key_F11), self)
        self.shortcut_f11.activated.connect(self.toggle_fullscreen_mode)

        # --- NEW: Toggle Side Panel Shortcut (Space) ---
        self.shortcut_space = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.shortcut_space.activated.connect(self.toggle_right_panel)
        
        # --- NEW: Create additional global shortcuts ---
        self._create_shortcuts()

        # --- NEW: Start Clock Timer (Moved here to ensure UI is ready) ---
        self.clock_timer.start()

        # --- NEW: System Tray Icon ---
        self._setup_tray_icon()


        # --- NEW: Schedule Heavy Library Loading ---
        # This ensures the UI shows up first, then libraries load.
        QTimer.singleShot(100, self.load_heavy_libraries)

    def tr(self, key, *args):
        """Translates a given key using the loaded language dictionary."""
        text = self.translations.get(key, key)
        if args:
            try:
                return text.format(*args)
            except (IndexError, KeyError):
                return text # Return raw text if format fails
        return text

    def _convert_sidebar_to_collapsible(self):
        """Converts QGroupBox widgets in the right panel to CollapsibleBox widgets."""
        if not hasattr(self, 'right_panel') or not self.right_panel:
            return

        # Helper to process a specific layout
        def process_layout(layout):
            if not layout: return
            # Iterate backwards to safely replace items
            for i in range(layout.count() - 1, -1, -1):
                item = layout.itemAt(i)
                if not item: continue
                widget = item.widget()
                if not widget: continue
                
                if isinstance(widget, QGroupBox):
                    # Found a GroupBox, wrap it
                    title = widget.title()
                    collapsible = CollapsibleBox(title)
                    
                    # Remove GroupBox from layout
                    layout.removeWidget(widget)
                    
                    # Hide original title/frame to avoid duplication
                    widget.setTitle("")
                    widget.setFlat(True) # Optional: remove frame
                    
                    # Add GroupBox to CollapsibleBox
                    collapsible.set_content(widget)
                    
                    # Add CollapsibleBox to original layout
                    layout.insertWidget(i, collapsible)
                elif isinstance(widget, QScrollArea):
                    # Recurse into ScrollAreas
                    if widget.widget() and widget.widget().layout():
                        process_layout(widget.widget().layout())

        # Check if right_panel is a QTabWidget (Tabs for Tasmee, Settings, Playlist)
        if isinstance(self.right_panel, QTabWidget):
            for i in range(self.right_panel.count()):
                tab_widget = self.right_panel.widget(i)
                if tab_widget.layout():
                    process_layout(tab_widget.layout())
        else:
            # Assume it's a single widget with layout
            if self.right_panel.layout():
                process_layout(self.right_panel.layout())

    def load_current_user_plans(self):
        """Loads plans specific to the current user."""
        if self.user_manager.current_user:
            self.plans = self.user_manager.get_plans(self.user_manager.current_user)
        else:
            self.plans = []
        self.refresh_plans_ui()

    def _add_profile_button_to_header(self):
        """Adds a profile/dashboard button to the header widget."""
        if not hasattr(self, 'header_widget'): return
        
        header_layout = self.header_widget.layout()
        
        # Set initial text based on current user
        btn_text = f"👤 {self.user_manager.current_user}" if self.user_manager.current_user else f"👤 {self.tr('my_profile')}"
        self.btn_profile = QPushButton(btn_text)
        self.btn_profile.setCursor(Qt.PointingHandCursor)
        self.btn_profile.setStyleSheet("""
            QPushButton { background-color: #E8F5E9; border: 1px solid #4CAF50; border-radius: 15px; padding: 5px 15px; font-weight: bold; color: #2E7D32; }
            QPushButton:hover { background-color: #C8E6C9; }
        """)
        self.btn_profile.clicked.connect(self.show_dashboard)
        
        # Insert before the stretch at the end
        header_layout.insertWidget(header_layout.count() - 1, self.btn_profile)

    def keyPressEvent(self, event):
        """Handle key press events, specifically for stopping Azan with Escape."""
        if event.key() == Qt.Key_Escape and (getattr(self, 'is_azan_playing', False) or getattr(self, 'is_duaa_playing', False)):
            self.stop_azan()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(QIcon(resource_path("assets/icon.ico")), self)
        
        menu = QMenu(self)
        
        self.toggle_main_window_action = menu.addAction(self.tr("tray_hide_app"))
        self.toggle_main_window_action.triggered.connect(self.toggle_main_window)
        
        self.toggle_widget_action = menu.addAction(self.tr("tray_hide_widget") if self.prayer_widget.isVisible() else self.tr("tray_show_widget"))
        self.toggle_widget_action.triggered.connect(self.toggle_prayer_widget)
        
        menu.addSeparator()
        
        exit_action = menu.addAction(self.tr("tray_exit"))
        exit_action.triggered.connect(self.exit_application)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.toggle_main_window()

    def toggle_main_window(self):
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def toggle_prayer_widget(self):
        if self.prayer_widget.isVisible():
            self.prayer_widget.hide()
            self.toggle_widget_action.setText(self.tr("tray_show_widget"))
        else:
            self.prayer_widget.show()
            self.toggle_widget_action.setText(self.tr("tray_hide_widget"))

    def exit_application(self):
        """Saves settings and cleanly exits the application."""
        # This is where the final save happens
        self.closeEvent = lambda event: event.accept() # Disable hide-to-tray logic
        self.close() # Trigger the original save logic now part of the real close
        QApplication.instance().quit()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, 'toggle_main_window_action'):
            self.toggle_main_window_action.setText(self.tr("tray_show_app"))

    def showEvent(self, event):
        """Handle the window's show event, used here to show profile dialog on first launch."""
        super().showEvent(event)
        if hasattr(self, 'toggle_main_window_action'):
            self.toggle_main_window_action.setText(self.tr("tray_hide_app"))
            
        # Use a flag to ensure this runs only once on the first time the window is shown.
        if not getattr(self, '_first_show_complete', False):
            self._first_show_complete = True
            # Check if we need to show the profile dialog.
            if not self.user_manager.current_user:
                # Use a QTimer to show the dialog after the main window is fully painted.
                QTimer.singleShot(0, self.show_profile_dialog)

    def load_heavy_libraries(self):
        """Loads heavy libraries in the background after UI is shown."""
        # print("DEBUG: Loading heavy libraries...")
        if self.splash:
            self.splash.showMessage("جاري تحميل المكتبات والنماذج...", Qt.AlignHCenter | Qt.AlignBottom, QColor("#FFFFFF"))
            QApplication.processEvents()
            
        global vlc, VLC_AVAILABLE
        global sd, SD_AVAILABLE
        global AudioSegment, PrayerTimes, CalculationMethod, Madhab, PRAYER_CALC_AVAILABLE
        global wdg, WINSDK_AVAILABLE, arabic_reshaper

        # 1. Load Arabic Reshaper
        try:
            import arabic_reshaper as ar
            arabic_reshaper = ar
            # Re-render current page to fix text if it was broken
            self.page_renderer.render_page(self.current_page)
        except ImportError: pass

        # 2. Load VLC
        try:
            import vlc as vlc_lib
            vlc = vlc_lib
            VLC_AVAILABLE = True
            # print("✓ VLC library loaded.")
            # Initialize VLC components
            self.vlc_instance = vlc.Instance()
            self.media_player = self.vlc_instance.media_player_new()
            self.list_player = self.vlc_instance.media_list_player_new()
            self.list_player.set_media_player(self.media_player)
            initial_volume = self.settings.get("volume", 100)
            self.media_player.audio_set_volume(initial_volume)
            player_em = self.media_player.event_manager()
            list_player_em = self.list_player.event_manager()
            list_player_em.event_attach(vlc.EventType.MediaListPlayerNextItemSet, self.handle_item_started)
            player_em.event_attach(vlc.EventType.MediaPlayerEndReached, self.handle_item_finished)
            self.player_update_timer = QTimer(self)
            self.player_update_timer.setInterval(500)
            self.player_update_timer.timeout.connect(self.update_player_progress)
            self.player_update_timer.start()
        except Exception as e:
            pass # print(f"!!! Error loading VLC: {e}")

        # 3. Load SoundDevice
        try:
            import sounddevice as sd_lib
            sd = sd_lib
            SD_AVAILABLE = True
            # Populate devices now that SD is available
            self.populate_audio_devices()
        except Exception: pass

        # 5. Load Prayer Times Libs
        try:
            from adhanpy.PrayerTimes import PrayerTimes as PT
            from adhanpy.calculation.CalculationMethod import CalculationMethod as CM
            from adhanpy.calculation.Madhab import Madhab as M
            PrayerTimes = PT
            CalculationMethod = CM
            Madhab = M
            PRAYER_CALC_AVAILABLE = True
            self._calculate_prayer_times()
        except Exception as e:
            # print(f"!!! Error loading Adhanpy (Prayer Times): {e}")
            # import traceback
            # traceback.print_exc()
            PRAYER_CALC_AVAILABLE = False

        # 6. Load Pydub
        # Pydub is now lazy loaded via utils.load_pydub() when needed
        
        # 7. Load Winsdk
        try:
            import winsdk.windows.devices.geolocation as w_geo
            wdg = w_geo
            WINSDK_AVAILABLE = True
        except ImportError: pass
        
        # print("DEBUG: Heavy libraries loaded.")

    # --- NEW: Voice Trigger Methods ---
    def setup_voice_trigger_ui(self):
        """Adds Voice Trigger controls to the Review Tab."""
        # We hook into the layout where btn_auto_reveal_start is located
        if not hasattr(self, 'btn_auto_reveal_start') or not self.btn_auto_reveal_start:
            return

        parent_widget = self.btn_auto_reveal_start.parentWidget()
        if not parent_widget or not parent_widget.layout():
            return
            
        layout = parent_widget.layout()
        
        # Add Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        
        # Group Box for Voice Trigger
        self.grp_voice_trigger = QGroupBox(self.tr("voice_review_group"))
        self.grp_voice_trigger.setStyleSheet("QGroupBox { font-weight: bold; color: #2E7D32; border: 1px solid #A5D6A7; border-radius: 5px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }")
        g_layout = QVBoxLayout(self.grp_voice_trigger)
        
        # Controls Row
        h_layout = QHBoxLayout()
        
        # Sensitivity (Threshold)
        self.spin_voice_threshold = QDoubleSpinBox()
        self.spin_voice_threshold.setRange(0.1, 100.0) # Increased range for noisy environments
        self.spin_voice_threshold.setSingleStep(0.5)
        self.spin_voice_threshold.setValue(5.0) # Higher default to ignore background noise
        self.spin_voice_threshold.setToolTip(self.tr("voice_sensitivity_tooltip"))
        self.lbl_voice_sensitivity = QLabel(self.tr("voice_sensitivity"))
        h_layout.addWidget(self.lbl_voice_sensitivity)
        h_layout.addWidget(self.spin_voice_threshold)
        
        # Speed
        self.combo_voice_speed = QComboBox()
        self.combo_voice_speed.addItems([self.tr("speed_slow"), self.tr("speed_medium"), self.tr("speed_fast"), self.tr("speed_very_fast")])
        self.combo_voice_speed.setCurrentIndex(1) # Medium default
        self.lbl_voice_speed = QLabel(self.tr("voice_speed"))
        h_layout.addWidget(self.lbl_voice_speed)
        h_layout.addWidget(self.combo_voice_speed)
        
        g_layout.addLayout(h_layout)
        
        # Buttons Layout
        btns_layout = QHBoxLayout()
        
        # Start/Pause Button
        self.btn_voice_trigger_start = QPushButton(self.tr("start_voice_review"))
        self.btn_voice_trigger_start.setCursor(Qt.PointingHandCursor)
        self.btn_voice_trigger_start.setStyleSheet("background-color: #009688; color: white; font-weight: bold; border-radius: 5px; padding: 8px;") # New Teal Color
        self.btn_voice_trigger_start.setFocusPolicy(Qt.NoFocus) # Prevent Spacebar from stopping it
        self.btn_voice_trigger_start.clicked.connect(self.toggle_voice_trigger)
        self.pulse_voice_trigger = PulseManager(self.btn_voice_trigger_start, active_color="#EF9A9A", default_color="#E57373", parent=self)
        btns_layout.addWidget(self.btn_voice_trigger_start)
        
        # Stop Button
        self.btn_voice_trigger_stop = QPushButton(self.tr("stop_voice_review"))
        self.btn_voice_trigger_stop.setCursor(Qt.PointingHandCursor)
        self.btn_voice_trigger_stop.setStyleSheet("background-color: #C0392B; color: white; font-weight: bold; border-radius: 5px; padding: 8px;")
        self.btn_voice_trigger_stop.setFocusPolicy(Qt.NoFocus)
        self.btn_voice_trigger_stop.clicked.connect(lambda: self.stop_voice_trigger(finished=False))
        self.btn_voice_trigger_stop.setEnabled(False)
        btns_layout.addWidget(self.btn_voice_trigger_stop)
        
        g_layout.addLayout(btns_layout)
        
        layout.addWidget(self.grp_voice_trigger)

    def toggle_voice_trigger(self):
        """Toggles the Voice Triggered Review mode (Start/Pause/Resume)."""
        if getattr(self, 'is_voice_trigger_active', False):
            # Active: Toggle Pause/Resume
            if getattr(self, 'voice_trigger_paused', False):
                self.resume_voice_trigger()
            else:
                self.pause_voice_trigger()
        else:
            # Not active: Start
            self.start_voice_trigger()

    def pause_voice_trigger(self):
        self.voice_trigger_paused = True
        self.voice_monitor_timer.stop()
        self.voice_reveal_timer.stop()
        self.btn_voice_trigger_start.setText(self.tr("resume_voice_review"))
        self.pulse_voice_trigger.stop()
        
        # Pause session timer
        if self.recitation_duration_timer.isActive():
            self.recitation_duration_timer.stop()
            
        self.progress(self.tr("voice_review_paused"))

    def resume_voice_trigger(self):
        self.voice_trigger_paused = False
        self.voice_monitor_timer.start()
        self.btn_voice_trigger_start.setText(self.tr("pause_voice_review"))
        self.pulse_voice_trigger.start()
        
        # Resume session timer
        if not self.recitation_duration_timer.isActive():
            self.recitation_duration_timer.start()
            
        self.progress(self.tr("voice_review_active", self.voice_trigger_current_rep, self.voice_trigger_total_reps))

    def start_voice_trigger(self):
        if self.recording:
             QMessageBox.warning(self, "تنبيه", "الرجاء إيقاف التسميع الصوتي أولاً.")
             return
        
        if not NUMPY_AVAILABLE:
             QMessageBox.warning(self, "خطأ", "مكتبة Numpy غير متوفرة. هذه الميزة تتطلب Numpy.")
             return
             
        if not SD_AVAILABLE:
             QMessageBox.warning(self, "خطأ", "مكتبة الصوت (SoundDevice) غير متوفرة.")
             return

        # 1. Build Range
        from_sura = self.combo_review_from_sura.currentData()
        from_aya = self.spin_review_from_aya.value()
        to_sura = self.combo_review_to_sura.currentData()
        to_aya = self.spin_review_to_aya.value()

        _, self.voice_trigger_map = self.data_manager.build_recitation_range(
            from_sura, from_aya, to_sura, to_aya
        )
        
        if not self.voice_trigger_map:
             QMessageBox.warning(self, "تنبيه", "النطاق المحدد لا يحتوي على كلمات.")
             return

        # 2. Setup State
        self.is_voice_trigger_active = True
        self.voice_trigger_paused = False
        self.voice_trigger_index = 0
        self.current_volume_level = 0.0
        self.last_voice_time = 0
        
        # --- NEW: Repetition Logic ---
        self.voice_trigger_current_rep = 1
        self.voice_trigger_total_reps = self.spin_review_repetitions.value()
        
        # --- NEW: Reset and Start Session Timer ---
        self.elapsed_recitation_time = 0
        if hasattr(self, 'recitation_duration_label'):
            self.recitation_duration_label.setText("00:00:00")
        if not self.recitation_duration_timer.isActive():
            self.recitation_duration_timer.start()
        
        # 3. Setup Audio Stream
        try:
            input_dev = self.input_device_index
            # Ensure input_dev is valid (int or None)
            if input_dev is not None and not isinstance(input_dev, int):
                 input_dev = None
                 
            self.voice_stream = sd.InputStream(
                device=input_dev, channels=1, samplerate=44100,
                callback=self._voice_audio_callback
            )
            self.voice_stream.start()
        except Exception as e:
            self.is_voice_trigger_active = False
            QMessageBox.critical(self, "خطأ في المايك", f"تعذر فتح الميكروفون:\n{e}")
            return

        # 4. UI Updates
        self.btn_voice_trigger_start.setText(self.tr("pause_voice_review"))
        self.btn_voice_trigger_stop.setEnabled(True)
        
        # --- FIX: Ensure pulse manager exists before starting ---
        if not self.pulse_voice_trigger and hasattr(self, 'btn_voice_trigger_start'):
             self.pulse_voice_trigger = PulseManager(self.btn_voice_trigger_start, active_color="#EF9A9A", default_color="#E57373", parent=self)
        
        if self.pulse_voice_trigger:
            self.pulse_voice_trigger.start()
            
        self.progress(self.tr("voice_review_active", self.voice_trigger_current_rep, self.voice_trigger_total_reps))
        
        # 5. Start Monitoring
        start_page = self.voice_trigger_map[0][0]
        self.on_page_changed(start_page)
        self._apply_voice_trigger_mask() # Hide text initially
        
        self.voice_monitor_timer.start()

    def stop_voice_trigger(self, finished=False):
        """Stops the Voice Triggered Review session."""
        self.is_voice_trigger_active = False
        self.voice_trigger_paused = False
        self.voice_monitor_timer.stop()
        self.voice_reveal_timer.stop()
        
        # --- NEW: Stop Session Timer ---
        if self.recitation_duration_timer.isActive():
            self.recitation_duration_timer.stop()
        
        # --- FIX: Ensure pulse manager exists before stopping ---
        if self.pulse_voice_trigger:
            self.pulse_voice_trigger.stop()
        
        if hasattr(self, 'voice_stream') and self.voice_stream:
            try:
                self.voice_stream.stop()
                self.voice_stream.close()
            except: pass
            self.voice_stream = None
            
        self.btn_voice_trigger_start.setText(self.tr("start_voice_review"))
        if hasattr(self, 'btn_voice_trigger_stop'):
            self.btn_voice_trigger_stop.setEnabled(False)
        self.page_renderer.render_page(self.current_page) # Reveal all
        self.progress(self.tr("voice_review_stopped"))
        
        # --- NEW: Update Plan Progress if finished successfully ---
        if finished:
            self.update_plan_progress('review')
            self.show_toast(self.tr("voice_review_completed"))

    def _voice_audio_callback(self, indata, frames, time, status):
        """Callback for sounddevice to measure volume."""
        try:
            if status:
                print(f"Voice Trigger Status: {status}")
            # Calculate RMS-like norm
            if NUMPY_AVAILABLE and indata is not None:
                self.current_volume_level = np.linalg.norm(indata) * 10
            else:
                self.current_volume_level = 0
        except Exception as e:
            print(f"Error in voice callback: {e}")
            self.current_volume_level = 0

    def _on_voice_monitor_tick(self):
        """Checks volume level and controls the reveal timer."""
        threshold = self.spin_voice_threshold.value()
        
        if self.current_volume_level > threshold:
            self.last_voice_time = time.time()
            
            # Determine speed based on combo
            speed_idx = self.combo_voice_speed.currentIndex()
            # Intervals in ms: Slow=600, Med=400, Fast=200, Very Fast=100
            intervals = [600, 400, 200, 100]
            interval = intervals[speed_idx]
            
            if not self.voice_reveal_timer.isActive():
                self.voice_reveal_timer.start(interval)
        else:
            # Silence Gap: Stop if silent for more than 300ms
            if time.time() - self.last_voice_time > 0.3:
                if self.voice_reveal_timer.isActive():
                    self.voice_reveal_timer.stop()

    def _on_voice_reveal_tick(self):
        """Reveals the next word."""
        if self.voice_trigger_index >= len(self.voice_trigger_map):
            # --- NEW: Check Repetitions ---
            if self.voice_trigger_current_rep < self.voice_trigger_total_reps:
                self.voice_trigger_current_rep += 1
                self.voice_trigger_index = 0
                
                # Restart from beginning
                start_page = self.voice_trigger_map[0][0]
                if self.current_page != start_page:
                    self.on_page_changed(start_page)
                else:
                    self._apply_voice_trigger_mask() # Re-hide everything
                
                self.show_toast(f"التكرار {self.voice_trigger_current_rep}/{self.voice_trigger_total_reps}")
                self.progress(self.tr("voice_review_active", self.voice_trigger_current_rep, self.voice_trigger_total_reps))
                return

            self.stop_voice_trigger(finished=True)
            self.show_toast(self.tr("voice_review_finished"))
            return

        page_info = self.voice_trigger_map[self.voice_trigger_index]
        
        # Page transition
        if page_info[0] != self.current_page:
             # Simple check for two-page view visibility
             is_visible = (self.view_mode == "two_pages" and 
                          (page_info[0] == self.current_page or page_info[0] == self.current_page + 1 or page_info[0] == self.current_page - 1))
             if not is_visible:
                 self.on_page_changed(page_info[0])
                 self._apply_voice_trigger_mask() # Re-hide on new page
                 return

        if page_info[3] is not None:
            global_idx = f"{page_info[1]}:{page_info[2]}:{page_info[3]}"
            self.page_renderer.update_word_text_color(global_idx, self.quran_text_color)
        
        self.view.viewport().repaint()
        self.voice_trigger_index += 1

    def _apply_voice_trigger_mask(self):
        """Hides words for voice trigger mode."""
        if not hasattr(self, 'voice_trigger_map'): return
        for i, info in enumerate(self.voice_trigger_map):
            if info[0] == self.current_page or (self.view_mode == "two_pages" and info[0] == self.current_page + 1):
                if info[3] is None: continue
                global_idx = f"{info[1]}:{info[2]}:{info[3]}"
                if i < self.voice_trigger_index:
                    self.page_renderer.update_word_text_color(global_idx, self.quran_text_color)
                else:
                    self.page_renderer.update_word_text_color(global_idx, QColor(0, 0, 0, 0))
        self.view.viewport().repaint()

    @pyqtSlot()
    def _update_window_icon(self):
        """Cycles through the window icons for animation."""
        if not hasattr(self, 'icon_objects') or len(self.icon_objects) < 2:
            return
        self.icon_index = (self.icon_index + 1) % len(self.icon_objects)
        self.setWindowIcon(self.icon_objects[self.icon_index])

    @pyqtSlot()
    def _update_logo(self):
        """Cycles through the logo pixmaps for animation."""
        if not hasattr(self, 'logo_pixmaps') or len(self.logo_pixmaps) < 2:
            return
        self.logo_index = (self.logo_index + 1) % len(self.logo_pixmaps)
        if hasattr(self, 'logo_label'):
            self.logo_label.setPixmap(self.logo_pixmaps[self.logo_index])

    # --- NEW: Location & Prayer Methods ---
    def refresh_location(self):
        """Starts the background thread to fetch location from Windows."""
        if self.btn_update_location:
            self.btn_update_location.setEnabled(False)
            # self.btn_update_location.setText("...") # Keep icon or change text
        
        if not hasattr(self, 'location_worker') or self.location_worker is None:
             self.location_worker = LocationWorker()
             self.location_worker.location_found.connect(self._on_location_found)
             self.location_worker.location_failed.connect(self._on_location_failed)
             
        self.location_worker.start()

    @pyqtSlot(float, float)
    def _on_location_found(self, lat, lng):
        self.latitude = lat
        self.longitude = lng
        self.settings["latitude"] = lat
        self.settings["longitude"] = lng
        save_settings(self.settings)
        
        # Update UI spinboxes without triggering signals loop
        if hasattr(self, 'spin_lat'):
            self.spin_lat.blockSignals(True)
            self.spin_lat.setValue(lat)
            self.spin_lat.blockSignals(False)
            
        if hasattr(self, 'spin_lng'):
            self.spin_lng.blockSignals(True)
            self.spin_lng.setValue(lng)
            self.spin_lng.blockSignals(False)

        self._calculate_prayer_times()
        
        if self.btn_update_location:
            self.btn_update_location.setEnabled(True)
        
        self.show_toast(f"تم تحديث الموقع: {lat:.6f}, {lng:.6f}", temporary=True)

    @pyqtSlot(str)
    def _on_location_failed(self, error):
        if self.btn_update_location:
            self.btn_update_location.setEnabled(True)
        # print(f"Location Error: {error}")
        self.show_toast("تعذر تحديد الموقع تلقائياً", temporary=True)

    # --- NEW: Settings Handlers ---
    def on_calc_method_changed(self, index):
        method = self.combo_calc_method.itemData(index)
        self.settings["prayer_calc_method"] = method
        save_settings(self.settings)
        self._calculate_prayer_times()

    def on_time_offset_changed(self, value):
        self.settings["prayer_time_offset"] = value
        save_settings(self.settings)
        self._calculate_prayer_times()

    def on_prayer_adj_changed(self, value):
        """Updates specific prayer adjustments from spinboxes."""
        # We read values directly from spinboxes to ensure we save the correct value for each prayer
        if hasattr(self, 'spin_adj_fajr'): self.settings["adj_fajr"] = self.spin_adj_fajr.value()
        if hasattr(self, 'spin_adj_sunrise'): self.settings["adj_sunrise"] = self.spin_adj_sunrise.value()
        if hasattr(self, 'spin_adj_dhuhr'): self.settings["adj_dhuhr"] = self.spin_adj_dhuhr.value()
        if hasattr(self, 'spin_adj_asr'): self.settings["adj_asr"] = self.spin_adj_asr.value()
        if hasattr(self, 'spin_adj_maghrib'): self.settings["adj_maghrib"] = self.spin_adj_maghrib.value()
        if hasattr(self, 'spin_adj_isha'): self.settings["adj_isha"] = self.spin_adj_isha.value()
        
        save_settings(self.settings)
        self._calculate_prayer_times()

    def on_location_manual_changed(self):
        """Updates location from manual spinboxes."""
        if hasattr(self, 'spin_lat') and hasattr(self, 'spin_lng'):
            self.latitude = self.spin_lat.value()
            self.longitude = self.spin_lng.value()
            self.settings["latitude"] = self.latitude
            self.settings["longitude"] = self.longitude
            save_settings(self.settings)
            self._calculate_prayer_times()

    # --- NEW: Widget Settings Handlers ---
    def on_toggle_widget_visibility(self, checked):
        self.settings["show_prayer_widget_on_startup"] = checked
        save_settings(self.settings)
        if checked:
            self.prayer_widget.show()
        else:
            self.prayer_widget.hide()
        if hasattr(self, 'toggle_widget_action'):
             self.toggle_widget_action.setText(self.tr("tray_hide_widget") if checked else self.tr("tray_show_widget"))

    def on_toggle_widget_on_top(self, checked):
        self.settings["widget_on_top"] = checked
        save_settings(self.settings)
        self.prayer_widget.always_on_top = checked
        self.prayer_widget.update_window_flags()

    def pick_widget_bg_color(self):
        current = QColor(self.prayer_widget.bg_color)
        c = QColorDialog.getColor(current, self, "اختر لون الخلفية", QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self.prayer_widget.bg_color = c.name(QColor.HexArgb)
            self.settings["widget_bg_color"] = self.prayer_widget.bg_color
            save_settings(self.settings)
            self.prayer_widget.apply_styles()
            # Update slider if exists
            if hasattr(self, 'slider_widget_opacity'):
                self.slider_widget_opacity.blockSignals(True)
                self.slider_widget_opacity.setValue(c.alpha())
                self.slider_widget_opacity.blockSignals(False)

    def pick_widget_text_color(self):
        current = QColor(self.prayer_widget.text_color)
        c = QColorDialog.getColor(current, self, "اختر لون النص")
        if c.isValid():
            self.prayer_widget.text_color = c.name()
            self.settings["widget_text_color"] = self.prayer_widget.text_color
            save_settings(self.settings)
            self.prayer_widget.apply_styles()

    def on_widget_scale_changed(self, value):
        self.settings["widget_font_scale"] = value
        save_settings(self.settings)
        self.prayer_widget.font_scale = value
        self.prayer_widget.apply_styles()

    def on_widget_opacity_changed(self, value):
        """Updates widget background opacity."""
        if hasattr(self, 'prayer_widget'):
            c = QColor(self.prayer_widget.bg_color)
            c.setAlpha(value)
            self.prayer_widget.bg_color = c.name(QColor.HexArgb)
            self.settings["widget_bg_color"] = self.prayer_widget.bg_color
            save_settings(self.settings)
            self.prayer_widget.apply_styles()

    def browse_azan_file(self, prayer_name):
        file_path, _ = QFileDialog.getOpenFileName(self, f"اختر ملف أذان {prayer_name}", self.azan_folder, "Audio Files (*.mp3 *.wav)")
        if file_path:
            self.settings[f"azan_file_{prayer_name}"] = file_path
            save_settings(self.settings)
            if prayer_name in self.azan_file_widgets:
                self.azan_file_widgets[prayer_name].setText(file_path)

    def preview_azan_file(self, prayer_name):
        file_path = self.settings.get(f"azan_file_{prayer_name}", "")
        
        # If playing, stop
        if self.media_player and self.media_player.is_playing():
            self.media_player.stop()
            return

        # If no specific file, pick random from default folder to preview default behavior
        if not file_path or not os.path.exists(file_path):
            if os.path.exists(self.azan_folder):
                files = [f for f in os.listdir(self.azan_folder) if f.endswith('.mp3')]
                if files:
                    import random
                    file_path = os.path.join(self.azan_folder, random.choice(files))
        
        if file_path and os.path.exists(file_path) and self.media_player:
            media = self.vlc_instance.media_new(file_path)
            self.media_player.set_media(media)
            self.media_player.play()

    def on_toggle_duaa(self, checked):
        """Updates the enable_duaa setting."""
        self.settings["enable_duaa"] = checked
        save_settings(self.settings)

    def play_azan(self, prayer_name):
        """
        Plays the Azan audio and displays the corresponding image overlay.
        """
        # print(f"DEBUG: Starting Azan sequence for {prayer_name}")
        
        # --- FIX: Save state and Stop any active playback/recording ---
        self.was_recording_before_azan = self.recording
        if self.recording:
            self.stop_recording()
            
        self.was_playlist_playing_before_azan = False
        if self.list_player:
            # Check if playing (3) or paused (4)
            state = self.list_player.get_state()
            if state == vlc.State.Playing:
                self.was_playlist_playing_before_azan = True
                self.player_stop()

        if self.media_player and self.media_player.is_playing():
            self.media_player.stop()

        azan_file = self.settings.get(f"azan_file_{prayer_name.capitalize()}", "")
        if not azan_file or not os.path.exists(azan_file):
            if os.path.exists(self.azan_folder):
                files = [f for f in os.listdir(self.azan_folder) if f.endswith(('.mp3', '.wav'))]
                if files:
                    import random
                    azan_file = os.path.join(self.azan_folder, random.choice(files))

        if not azan_file or not os.path.exists(azan_file):
            # print(f"No Azan file found for {prayer_name} or in default folder.")
            return
            
        self.is_azan_playing = True

        # --- 1. Show Image FIRST (Immediate Visual Feedback) ---
        try:
            if not hasattr(self, 'azan_label'):
                # print("Warning: azan_label not initialized. Creating it now.")
                # Fallback creation if called too early
                self.azan_label = QLabel(self.view)
                self.azan_label.setAlignment(Qt.AlignCenter)
                self.azan_label.setStyleSheet("background-color: transparent;")
                self.azan_label.hide()

            pixmap = QPixmap(resource_path("assets/azan.png"))
            if pixmap.isNull():
                # Fallback style if image missing
                self.azan_label.setText(f"حان الآن وقت صلاة {prayer_name}")
                self.azan_label.setStyleSheet("background-color: rgba(0, 0, 0, 0.9); color: white; font-size: 40px; font-weight: bold;")
            else:
                # --- FIX: Draw Prayer Name on Image ---
                painter = QPainter(pixmap)
                # استخدام خط عريض وواضح
                font = QFont("Traditional Arabic", 40, QFont.Bold)
                painter.setFont(font)
                
                prayer_name_ar = {"fajr": "الفجر", "dhuhr": "الظهر", "asr": "العصر", "maghrib": "المغرب", "isha": "العشاء"}.get(prayer_name.lower(), prayer_name)
                text = f"حان الآن وقت صلاة {prayer_name_ar}"
                
                # رسم النص مع ظل أسود لضمان الوضوح
                text_rect = pixmap.rect()
                text_rect.adjust(0, 20, 0, 0) # إزاحة قليلة للأسفل
                painter.setPen(QColor("black"))
                painter.drawText(text_rect.translated(2, 2), Qt.AlignTop | Qt.AlignHCenter | Qt.TextWordWrap, text)
                painter.setPen(QColor("white"))
                painter.drawText(text_rect, Qt.AlignTop | Qt.AlignHCenter | Qt.TextWordWrap, text)
                painter.end()
                
                self.azan_label.setPixmap(pixmap)

            # Force geometry update to cover full view
            self.azan_label.resize(self.view.size())
            self.azan_label.move(0, 0)
            self.azan_label.setScaledContents(True)
            self.azan_label.show()
            self.azan_label.raise_()
            QApplication.processEvents() # Force UI update
            # print("DEBUG: Azan image shown.")
        except Exception as e:
            pass # print(f"Error showing Azan image: {e}")

        # --- 2. Play Audio and set a timer to hide the overlay ---
        try:
            duration_ms = 180000  # Default 3 minutes

            # Try to get duration from the file itself
            load_pydub() # Ensure pydub is loaded for duration calculation
            if AudioSegment:
                try:
                    audio = AudioSegment.from_file(azan_file)
                    duration_ms = len(audio)
                except Exception as e:
                    print(f"Pydub couldn't get duration for {azan_file}: {e}")

            # Play using VLC if available
            if self.media_player:
                media = self.vlc_instance.media_new(azan_file)
                self.media_player.set_media(media)
                self.media_player.play()
            elif PYDUB_AVAILABLE: # Fallback to pydub for playback
                audio = AudioSegment.from_file(azan_file)
                threading.Thread(target=lambda: pydub_play(audio), daemon=True).start()

            # --- FIX: Use a reliable timer instead of VLC event for single playback ---
            # Disconnect any previous connections to be safe
            try:
                self.azan_timer.timeout.disconnect()
            except TypeError: # No connections
                pass

            # Connect the timer to the finish handler and start it.
            self.azan_timer.setSingleShot(True) # Ensure it fires only once
            self.azan_timer.timeout.connect(self.on_azan_finished)
            self.azan_timer.start(duration_ms + 1000) # Add 1s buffer

        except Exception as e:
            # print(f"Error playing Azan: {e}")
            # traceback.print_exc()
            self.is_azan_playing = False

    def on_azan_finished(self):
        """Called when Azan audio finishes. Checks if Duaa should be played."""
        if self.settings.get("enable_duaa", False):
            self.play_duaa()
        else:
            self.stop_azan()

    def play_duaa(self):
        """Plays the Duaa audio after Azan."""
        # print("Playing Duaa.")
        duaa_file = resource_path("sounds/azan/sharawy_doaa_24.mp3")
        
        if not os.path.exists(duaa_file):
            # print(f"Duaa file not found at: {duaa_file}")
            self.stop_azan()
            return

        self.is_azan_playing = False # Azan part finished
        self.is_duaa_playing = True # Duaa part started
        
        # Update Label (Optional, or keep Azan image)
        # self.azan_label.setText("دعاء ما بعد الأذان") 
        
        try:
            duration_ms = 90000  # Default 90 seconds
            load_pydub()
            if AudioSegment:
                try:
                    audio = AudioSegment.from_file(duaa_file)
                    duration_ms = len(audio)
                except: pass

            if self.media_player:
                media = self.vlc_instance.media_new(duaa_file)
                self.media_player.set_media(media)
                self.media_player.play()
            elif PYDUB_AVAILABLE: # Fallback
                audio = AudioSegment.from_file(duaa_file)
                threading.Thread(target=lambda: pydub_play(audio), daemon=True).start()

            try: self.azan_timer.timeout.disconnect() # Disconnect previous (on_azan_finished)
            except: pass 
            self.azan_timer.timeout.connect(self.stop_azan)
            self.azan_timer.start(duration_ms + 1000) # Add 1s buffer
            
        except Exception as e:
            # print(f"Error playing Duaa: {e}")
            self.stop_azan()

    def stop_azan(self):
        """
        Stops the Azan audio and hides the overlay.
        """
        if not getattr(self, 'is_azan_playing', False) and not getattr(self, 'is_duaa_playing', False):
            return
            
        # print("Stopping Azan.")
        if self.media_player and self.media_player.is_playing():
            # Force stop if we are in Azan mode, regardless of file name
            self.media_player.stop()

        if self.azan_label and self.azan_label.isVisible():
            self.azan_label.hide()
        
        if self.azan_timer and self.azan_timer.isActive():
            self.azan_timer.stop()
            
        # --- NEW: Resume previous state ---
        if self.was_recording_before_azan:
            # Resume Recitation (Tasmee)
            self.start_recording()
            self.was_recording_before_azan = False
            
        elif self.was_playlist_playing_before_azan:
            # Resume Playlist
            if self.playlist_with_reps and self.list_player:
                # Re-create media list (since play_azan hijacked the media_player)
                media_paths = []
                for item in self.playlist_with_reps:
                    f = item['file']
                    if os.path.isabs(f):
                        media_paths.append(f)
                    else:
                        media_paths.append(os.path.join(self.output_folder, f))
                
                media_list = self.vlc_instance.media_list_new(media_paths)
                self.list_player.set_media_list(media_list)
                
                # Restore pulses based on last mode
                if self.last_estimate_mode == "SINGLE": self.pulse_play_single.start()
                elif self.last_estimate_mode == "GROUP": self.pulse_play_group.start()
                elif self.last_estimate_mode == "COMPLEX": self.pulse_play_complex.start()
                elif self.last_estimate_mode == "PAGE_BASED": self.pulse_play_page.start()

                # Resume from last index (decrement because handle_item_started increments)
                resume_index = max(0, self.current_playlist_index)
                self.current_playlist_index = resume_index - 1
                self.list_player.play_item_at_index(resume_index)
            
            self.was_playlist_playing_before_azan = False

        self.is_azan_playing = False
        self.is_duaa_playing = False

    def _calculate_prayer_times(self):
        if not PRAYER_CALC_AVAILABLE:
            self.next_prayer_name = "المكتبة مفقودة"
            return

        method_key = self.settings.get("prayer_calc_method", "egypt")
        user_offset = self.settings.get("prayer_time_offset", 0)

        # خريطة لربط إعداداتنا بطرق حساب adhanpy
        method_map = {
            "egypt": CalculationMethod.EGYPTIAN,
            "makkah": CalculationMethod.UMM_AL_QURA,
            "karachi": CalculationMethod.KARACHI,
            "isna": CalculationMethod.NORTH_AMERICA,
            "mwl": CalculationMethod.MUSLIM_WORLD_LEAGUE
        }
        
        # الحصول على إعدادات الحساب (الافتراضي: المصرية)
        params = method_map.get(method_key, CalculationMethod.EGYPTIAN)
        params.madhab = Madhab.SHAFI # المذهب الشافعي هو الافتراضي

        # --- NEW: High Latitude Rule (احتياطي للمناطق الشمالية) ---
        try:
            from adhanpy.calculation.HighLatitudeRule import HighLatitudeRule
            params.high_latitude_rule = HighLatitudeRule.MIDDLE_OF_THE_NIGHT
        except ImportError:
            pass

        try:
            coords = Coordinates(self.latitude, self.longitude)
            today = datetime.now().date()
            tomorrow = datetime.now() + timedelta(days=1)
            
            # --- FIX: حساب فرق التوقيت لكل يوم على حدة (لمعالجة التوقيت الصيفي بدقة) ---
            def get_offset_hours(d):
                # نستخدم وقت الظهيرة لتجنب مشاكل منتصف الليل عند تغيير التوقيت
                dt = datetime(d.year, d.month, d.day, 12, 0)
                return dt.astimezone().utcoffset().total_seconds() / 3600.0

            offset_today = get_offset_hours(today)
            offset_tomorrow = get_offset_hours(tomorrow)

            # 1. حساب مواقيت اليوم
            pt_today = PrayerTimes(coords, today, params)
            
            # 2. حساب مواقيت الغد
            pt_tomorrow = PrayerTimes(coords, tomorrow, params)
            
            self.prayer_times = {}
            
            # دالة مساعدة لمعالجة وتخزين الأوقات
            def process_times(pt_obj, offset_hours, is_tomorrow=False):
                suffix = "_TOMORROW" if is_tomorrow else ""
                times_map = {
                    "Fajr": pt_obj.fajr,
                    "Sunrise": pt_obj.sunrise,
                    "Dhuhr": pt_obj.dhuhr,
                    "Asr": pt_obj.asr,
                    "Maghrib": pt_obj.maghrib,
                    "Isha": pt_obj.isha
                }
                for name, dt in times_map.items():
                    if dt:
                        # تحويل الوقت من UTC إلى التوقيت المحلي
                        dt = dt + timedelta(hours=offset_hours)

                        # --- FIX: التقريب لأقرب دقيقة (Rounding) ---
                        # إضافة 30 ثانية لضمان أن 12:03:50 تصبح 12:04 بدلاً من 12:03
                        dt = dt + timedelta(seconds=30)
                        dt = dt.replace(second=0, microsecond=0)

                        # تطبيق التعديل اليدوي العام (بالدقائق)
                        total_offset = user_offset
                        
                        # تطبيق التعديل اليدوي الخاص بكل صلاة (إصلاح الفروقات الدقيقة)
                        # Keys in settings: 'adj_fajr', 'adj_sunrise', 'adj_dhuhr', etc.
                        specific_adj_key = f"adj_{name.lower()}"
                        specific_adj = self.settings.get(specific_adj_key, 0)
                        total_offset += specific_adj

                        final_dt = dt + timedelta(minutes=total_offset)
                        # إزالة معلومات المنطقة الزمنية للمقارنة السهلة مع datetime.now()
                        if final_dt.tzinfo is not None:
                            final_dt = final_dt.replace(tzinfo=None)
                        self.prayer_times[f"{name}{suffix}"] = final_dt

            process_times(pt_today, offset_today)
            process_times(pt_tomorrow, offset_tomorrow, is_tomorrow=True)
            
            self._update_next_prayer()
            
            # Force UI update immediately
            self._update_clock_and_prayers()
            
            # Emit signal that times have changed (for widget list)
            self.prayer_times_updated_signal.emit()

        except Exception as e:
            print(f"Error calculating prayer times: {e}")
            self.next_prayer_name = "خطأ في الحساب"

    def _update_next_prayer(self):
        now = datetime.now()
        upcoming = []
        
        name_map = {
            "Fajr": self.tr("prayer_fajr"), "Sunrise": self.tr("prayer_sunrise"), "Dhuhr": self.tr("prayer_dhuhr"), 
            "Asr": self.tr("prayer_asr"), "Maghrib": self.tr("prayer_maghrib"), "Isha": self.tr("prayer_isha")
        }

        for key, dt in self.prayer_times.items():
            # Remove suffix to check name
            clean_name = key.replace("_TOMORROW", "")
            if clean_name in name_map:
                if dt > now:
                    upcoming.append((dt, name_map[clean_name], clean_name)) # Store English name too for file lookup
        
        if upcoming:
            upcoming.sort(key=lambda x: x[0])
            self.next_prayer_time = upcoming[0][0]
            # --- FIX: Include time in the name for display (إضافة الوقت للاسم) ---
            name_ar = upcoming[0][1]
            time_str = self.next_prayer_time.strftime("%I:%M %p")
            self.next_prayer_name = f"{name_ar} ({time_str})"
            self.next_prayer_key = upcoming[0][2] # Store English key (e.g., 'Fajr')
        else:
            # Should not happen with tomorrow's calculation, but as fallback
            self.next_prayer_name = "--"
            self.next_prayer_time = None
            self.next_prayer_key = ""

    def _update_clock_and_prayers(self):
        # --- NEW: Guard against re-entry (منع التكرار أثناء تشغيل الأذان) ---
        if getattr(self, '_is_updating_clock', False):
            return
        self._is_updating_clock = True

        try:
            now = datetime.now()
            current_time_str = now.strftime("%I:%M:%S %p")
            remaining_str = "--:--"
            
            if self.next_prayer_time:
                delta = self.next_prayer_time - now
                total_seconds = int(delta.total_seconds())
                
                if total_seconds <= 0:
                    # --- FIX: Prevent double triggering for the same prayer ---
                    if self.last_triggered_prayer_time != self.next_prayer_time:
                        self.last_triggered_prayer_time = self.next_prayer_time
                        
                        # Trigger Azan
                        if hasattr(self, 'next_prayer_key') and self.next_prayer_key:
                             self.play_azan(self.next_prayer_key.lower())
                    
                    # Recalculate for next prayer
                    self._calculate_prayer_times()
                else:
                    hours, remainder = divmod(total_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    remaining_str = f"{hours:02}:{minutes:02}:{seconds:02}"

            prayer_name_str = str(self.next_prayer_name)
            
            # Update separate labels
            if hasattr(self, 'header_time_label'):
                self.header_time_label.setText(current_time_str)
            if hasattr(self, 'header_next_prayer_label'):
                self.header_next_prayer_label.setText(f"{prayer_name_str} <span style='color: #C0392B;'>{self.tr('remaining_time', remaining_str)}</span>")

            self.update_clock_signal.emit(current_time_str, prayer_name_str, remaining_str)
        finally:
            self._is_updating_clock = False

    def _update_recitation_timer(self):
        """Updates the recitation timer label with elapsed time."""
        self.elapsed_recitation_time += 1
        m, s = divmod(self.elapsed_recitation_time, 60)
        h, m = divmod(m, 60)
        time_str = f"{h:02d}:{m:02d}:{s:02d}"
        
        # Update the label in the top bar (Group 1)
        if hasattr(self, 'recitation_duration_label'):
            self.recitation_duration_label.setText(time_str)
            
        # Update the label in Range Info (Group 2) - User Request
        if hasattr(self, 'duration_label'):
            self.duration_label.setText(time_str)
            self.duration_label.setToolTip(f"مدة الجلسة الحالية: {time_str}")

    def show_help_dialog(self):
        """Displays a dialog with information about the program using a scrollable text area."""
        dialog = QDialog(self)
        dialog.setWindowTitle("دليل المستخدم")
        dialog.setLayoutDirection(Qt.RightToLeft)
        dialog.resize(600, 700)  # Set a reasonable default size

        layout = QVBoxLayout(dialog)

        # Create a scrollable text area
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)

        # Set the message text with HTML formatting
        help_text = """
        <div align="right" dir="rtl">
            <h2 style="color:#2E7D32; text-align:center;">📖 دليل "يُسْر (YUSR) - Light" - رفيقك في رحلة القرآن</h2>
            
            <div style="background-color:#E8F5E9; padding:15px; border-radius: 10px; border: 1px solid #C8E6C9; margin-bottom: 15px;">
                <p style="font-size:14px; margin:0;"><b>أهلاً بك في برنامج يُسْر (YUSR) - Light.</b><br>
                نسخة خفيفة وسريعة مصممة لمساعدتك في مراجعة وتثبيت حفظ القرآن الكريم من خلال أدوات بصرية وسمعية ذكية، دون الحاجة لتقنيات معقدة.</p>
            </div>

            <h3 style="color:#D35400;">🌟 المميزات الرئيسية</h3>
            <ul>
                <li style="margin-bottom:5px;"><b>👁️ المراجعة البصرية (Auto Reveal):</b> نظام ذكي لإخفاء الآيات وإظهارها تدريجياً لاختبار حفظك بصرياً.</li>
                <li style="margin-bottom:5px;"><b>🎧 المراجعة السمعية (Playlist):</b> إنشاء قوائم تشغيل مخصصة لتكرار الآيات والربط بينها.</li>
                <li style="margin-bottom:5px;"><b>📅 خطط الحفظ:</b> نظام متكامل لجدولة الحفظ والمراجعة اليومية.</li>
                <li style="margin-bottom:5px;"><b>🚫 يعمل بدون إنترنت:</b> كافة المميزات تعمل محلياً على جهازك.</li>
            </ul>

            <hr style="border: 1px dashed #ccc;">

            <h3 style="color:#8E44AD;">🎛️ شرح وظائف البرنامج</h3>

            <h4 style="color:#2980B9;">1️⃣ نظام المراجعة (Review Mode)</h4>
            <p>هذه الخاصية هي البديل العملي للتسميع الصوتي، حيث تعتمد على الذاكرة البصرية:</p>
            <ul>
                <li><b>كيف تعمل؟</b> يقوم البرنامج بإخفاء كلمات الصفحة، ثم يبدأ بإظهارها (كشفها) كلمة تلو الأخرى أو آية تلو الأخرى بسرعة تحددها أنت.</li>
                <li><b>الهدف:</b> أن تسبق البرنامج في القراءة! حاول قراءة الآية غيباً قبل أن يظهرها البرنامج على الشاشة.</li>
                <li><b>الإعدادات:</b>
                    <ul>
                        <li><b>سرعة العرض:</b> حدد الوقت المقدر لقراءة الصفحة (مثلاً 30 ثانية).</li>
                        <li><b>التكرار:</b> عدد مرات إعادة عرض النطاق المحدد.</li>
                        <li><b>توقف عند الآية:</b> مدة توقف قصيرة عند نهاية كل آية لالتقاط الأنفاس.</li>
                    </ul>
                </li>
                <li><b>طريقة الاستخدام:</b> اذهب لتبويب "مراجعة"، حدد النطاق (من/إلى)، اضبط السرعة، واضغط "بدء العرض".</li>
            </ul>

            <h4 style="color:#D35400;">2️⃣ المراجعة الصوتية (Voice Trigger) <span style="font-size:10px; background-color:#FFEB3B; padding:2px 5px; border-radius:3px;">جديد</span></h4>
            <p>ميزة تفاعلية تتيح لك تقليب الصفحات أو كشف الكلمات المخفية باستخدام صوتك فقط (بدون إنترنت):</p>
            <ul>
                <li><b>كيف تعمل؟</b> يقوم البرنامج بإخفاء الآيات، وعندما تبدأ بالقراءة (يسمع صوتك)، يقوم بكشف الكلمات تباعاً. إذا سكتَّ، يتوقف العرض.</li>
                <li><b>الفائدة:</b> محاكاة للتسميع على شيخ، حيث لا تظهر الكلمة إلا بعد نطقها.</li>
                <li><b>الإعدادات:</b> يمكنك ضبط "حساسية الصوت" لتجاهل الضوضاء المحيطة (أصوات السيارات أو العصافير).</li>
                <li><b>طريقة الاستخدام:</b> من تبويب "مراجعة"، اضغط "بدء المراجعة الصوتية".</li>
            </ul>

            <h4 style="color:#C0392B;">3️⃣ نظام "البلاي ليست" (التكرار والتحفيظ)</h4>
            <p>لتثبيت الحفظ عبر الاستماع (يتطلب ملفات صوتية):</p>
            <ul>
                <li><b>🔁 تكرار فردي:</b> تكرار الآية الواحدة عدة مرات.</li>
                <li><b>🔁 تكرار جماعي:</b> تكرار المقطع كاملاً.</li>
                <li><b>🔗 التكرار المركب:</b> يقرأ الآية 1، ثم 2، ثم يربط (1+2)، ثم 3، ثم يربط (2+3)... وهكذا.</li>
            </ul>
            <p><i>ملاحظة: يجب توفر ملفات الصوت في مجلد البرنامج (مثل: QuranAudio/Al-Minshawi/001001.mp3).</i></p>

            <h4 style="color:#16A085;">4️⃣ أوقات الصلاة والتنبيهات</h4>
            <ul>
                <li>حساب دقيق لأوقات الصلاة حسب موقعك الجغرافي.</li>
                <li>تنبيهات بصرية وصوتية (أذان) عند دخول الوقت.</li>
                <li>إمكانية تشغيل دعاء ما بعد الأذان تلقائياً.</li>
            </ul>

            <h4 style="color:#27AE60;">5️⃣ إعدادات العرض</h4>
            <ul>
                <li><b>العرض الديناميكي:</b> تكبير الخط ليملأ الشاشة (سطر واحد أو أكثر).</li>
                <li><b>عرض صفحتين:</b> محاكاة مصحف المدينة.</li>
                <li><b>تغيير الألوان والخطوط:</b> تحكم كامل في المظهر لراحة عينيك.</li>
            </ul>

            <h4 style="color:#8E44AD;">6️⃣ نظام الخطط</h4>
            <ul>
                <li>أنشئ خططاً للحفظ أو المراجعة.</li>
                <li>يتابع البرنامج تقدمك يومياً في لوحة "مهمتي اليومية".</li>
                <li>إحصائيات عن أيام الالتزام والاستمرارية (Streak).</li>
            </ul>

            <h4 style="color:#D35400;">7️⃣ معاني الكلمات والتفسير</h4>
            <ul>
                <li>اضغط (كليك شمال) على أي كلمة في المصحف لعرض: المعنى، التفسير الميسر، الإعراب، وأسباب النزول.</li>
            </ul>

            <hr style="border: 1px dashed #ccc;">

            <h4 style="color:#7F8C8D;">فريق العمل</h4>
            <p><b>رؤية وإشراف:</b> أيمن قطب.<br>
            <b>تطوير برمجي:</b> م. أيمن السيد حسين قطب (بمساعدة Gemini AI).</p>
            
            <div style="background-color:#FFF3E0; padding:10px; border-radius: 5px; text-align:center; border: 1px solid #FFE0B2;">
                <p style="color:#E65100; font-weight: bold; margin:0;">هذا العمل صدقة جارية لوجه الله تعالى. لا يجوز بيعه أو استخدامه تجارياً.<br>
                نسألكم الدعاء بظهر الغيب.</p>
            </div>
        </div>
        """
        
        text_edit.setHtml(help_text)
        # Apply style to ensure font size is good
        text_edit.setStyleSheet("QTextEdit { font-size: 13pt; }")

        layout.addWidget(text_edit)

        # Add a close button
        btn_close = QPushButton("موافق")
        btn_close.clicked.connect(dialog.accept)
        # Center the button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)

        dialog.exec_()

    def apply_loaded_settings_to_ui(self):
        """Applies the loaded settings to the UI widgets after they have been built."""
        # Apply scale factor (zoom level)
        self._update_scale(self.scale_factor)

        # Apply page background color
        if self.page_bg_color.isValid():
            self.view.setBackgroundBrush(QBrush(self.page_bg_color))

        # Apply show_aya_markers
        if hasattr(
            self, 'btn_toggle_aya_markers') and self.btn_toggle_aya_markers:
            if self.show_aya_markers:
                self.btn_toggle_aya_markers.setText(self.tr("hide_ayah_markers"))
            else:
                self.btn_toggle_aya_markers.setText(self.tr("show_ayah_markers"))
            self.btn_toggle_aya_markers.setEnabled(
                True)  # Explicitly enable the button
        # Trigger a re-render to reflect the marker visibility
        self.page_renderer.render_page(self.current_page)

        # NEW: Update border image label
        if hasattr(self, 'lbl_current_border_image') and self.lbl_current_border_image:
            loaded_border_image_path = self.settings.get("border_image_path")
            if loaded_border_image_path:
                self.lbl_current_border_image.setText(self.tr("current_border", os.path.basename(loaded_border_image_path)))
            else:
                self.lbl_current_border_image.setText(self.tr("current_border", self.tr("no_border")))

        # Apply Language Setting
        if hasattr(self, 'combo_language') and self.combo_language:
            lang = self.settings.get("app_language", "ar")
            idx = self.combo_language.findData(lang)
            if idx >= 0: self.combo_language.setCurrentIndex(idx)

        # Apply Highlight Color Setting
        if hasattr(self, 'combo_highlight_color') and self.combo_highlight_color:
            color_key = self.settings.get("highlight_color_key", "yellow")
            idx = self.combo_highlight_color.findData(color_key)
            if idx >= 0: self.combo_highlight_color.setCurrentIndex(idx)

        # Apply Widget Opacity Slider
        if hasattr(self, 'slider_widget_opacity'):
            bg_color = self.settings.get("widget_bg_color", "#C8141E28")
            c = QColor(bg_color)
            self.slider_widget_opacity.blockSignals(True)
            self.slider_widget_opacity.setValue(c.alpha())
            self.slider_widget_opacity.blockSignals(False)

    def populate_audio_devices(self):
        """Populates the input and output device comboboxes using sounddevice."""
        # Guard against re-entry (منع التكرار)
        if getattr(self, '_is_populating_devices', False):
            print("DEBUG: populate_audio_devices skipped (re-entry guard).")
            return
        self._is_populating_devices = True

        try:
            # محاولة الوصول المباشر والنهائي للعناصر
            target_input = getattr(self, 'combo_input_device', None)
            target_output = getattr(self, 'combo_output_device', None)

            # لو لسه مش شايفهم، هندور عليهم "بالنوع" جوه الـ UI
            if target_input is None or target_output is None:
                from PyQt5.QtWidgets import QComboBox
                combos = self.findChildren(QComboBox)
                for c in combos:
                    name = c.objectName().lower()
                    # هنعرفهم من مكانهم أو أساميهم البرمجية
                    if "input" in name:
                        target_input = c
                        # Update self reference if missing so other methods can use it
                        if not getattr(self, 'combo_input_device', None):
                            self.combo_input_device = c
                    if "output" in name:
                        target_output = c
                        # Update self reference if missing
                        if not getattr(self, 'combo_output_device', None):
                            self.combo_output_device = c

            # --- FIX: Ensure widgets exist before proceeding ---
            if target_input is None or target_output is None:
                 print("DEBUG: Audio device widgets not found yet.")
                 return

            # Block signals to prevent triggering slots during population
            target_input.blockSignals(True)
            target_output.blockSignals(True)
            
            target_input.clear()
            target_output.clear()
            
            if not SD_AVAILABLE:
                target_input.addItem("مكتبة الصوت غير متاحة")
                target_output.addItem("مكتبة الصوت غير متاحة")
                target_input.setEnabled(False)
                target_output.setEnabled(False)
            else:
                try:
                    # import sounddevice as sd # Already imported globally
                    devices = sd.query_devices()
                    
                    # Get default device indices
                    default_input_idx, default_output_idx = -1, -1
                    try:
                        if isinstance(sd.default.device, (list, tuple)):
                            if len(sd.default.device) > 0: default_input_idx = sd.default.device[0]
                            if len(sd.default.device) > 1: default_output_idx = sd.default.device[1]
                        else:
                            default_input_idx = sd.default.device
                    except Exception:
                        pass

                    input_found = False
                    output_found = False
                    
                    default_input_combo_index = 0
                    default_output_combo_index = 0
                    
                    # --- NEW: Sets to track added names for deduplication ---
                    seen_input_names = set()
                    seen_output_names = set()

                    try:
                        hostapis = sd.query_hostapis()
                    except Exception as e:
                        hostapis = []

                    for i, d in enumerate(devices):
                        name = d.get('name', 'Unknown Device')
                        
                        # --- NEW: Filter out "Mapper" devices ---
                        if "mapper" in name.lower():
                            continue
                            
                        max_in = d.get('max_input_channels', 0)
                        max_out = d.get('max_output_channels', 0)
                        hostapi_idx = d.get('hostapi', -1)

                        # Get API name safely
                        try:
                            if 0 <= hostapi_idx < len(hostapis):
                                api_name = hostapis[hostapi_idx]['name']
                            else:
                                api_name = "Unknown API"
                        except:
                            api_name = "Unknown"

                        # --- Radical Detection Logic (الحل الجذري) ---
                        # 1. Trust channel count if > 0
                        is_input = max_in > 0
                        is_output = max_out > 0
                        
                        # 2. If channels are 0, check name keywords (common in WASAPI/WDM-KS)
                        # This covers devices that don't report channels correctly regardless of API
                        name_lower = name.lower()
                        if not is_input:
                            if any(x in name_lower for x in ['mic', 'input', 'capture', 'recording', 'ميكروفون', 'لاقط', 'إدخال']):
                                is_input = True
                        
                        if not is_output:
                            if any(x in name_lower for x in ['speaker', 'output', 'headphone', 'playback', 'monitor', 'سماعة', 'مكبر', 'إخراج']):
                                is_output = True

                        # Display format: "Name (API) [Index]"
                        display_str = f"{name} ({api_name})"

                        if is_input:
                            original_name = name # Use the 'name' from device info
                            display_name = clean_device_name(original_name)
                            
                            # --- NEW: Deduplication Logic ---
                            if display_name not in seen_input_names:
                                seen_input_names.add(display_name)
                                item_text = f"🎤 {display_name}" # Display cleaned name
                                if i == default_input_idx:
                                    item_text = f"⭐ {item_text}"
                                    default_input_combo_index = target_input.count()
                                # Add item and set its tooltip to the full name
                                target_input.addItem(item_text, i) # Add item with icon, value is index
                                target_input.setItemData(target_input.count() - 1, original_name, Qt.ToolTipRole) # Tooltip and data is original name
                                input_found = True
                        
                        if is_output:
                            original_name = name # Use the 'name' from device info
                            display_name = clean_device_name(original_name)
                            
                            # --- NEW: Deduplication Logic ---
                            if display_name not in seen_output_names:
                                seen_output_names.add(display_name)
                                item_text = f"🔊 {display_name}" # Display cleaned name
                                if i == default_output_idx:
                                    item_text = f"⭐ {item_text}"
                                    default_output_combo_index = target_output.count()
                                # Add item and set its tooltip to the full name
                                target_output.addItem(item_text, i) # Add item with icon, value is index
                                target_output.setItemData(target_output.count() - 1, original_name, Qt.ToolTipRole) # Tooltip and data is original name
                                output_found = True
                    
                    target_input.setEnabled(input_found)
                    target_output.setEnabled(output_found)
                    
                    if not input_found: target_input.addItem("لا يوجد ميكروفون")
                    if not output_found: target_output.addItem("لا توجد سماعات")

                    # --- Restore Selection ---
                    saved_input = self.settings.get("input_device_name")
                    if saved_input:
                        idx = target_input.findText(saved_input)
                        if idx >= 0: target_input.setCurrentIndex(idx)
                        else: target_input.setCurrentIndex(default_input_combo_index)
                    else:
                        target_input.setCurrentIndex(default_input_combo_index)
                        
                    if target_input.count() > 0:
                        self.input_device_index = target_input.currentData()

                    saved_output = self.settings.get("output_device_name")
                    if saved_output:
                        idx = target_output.findText(saved_output)
                        if idx >= 0: target_output.setCurrentIndex(idx)
                        else: target_output.setCurrentIndex(default_output_combo_index)
                    else:
                        target_output.setCurrentIndex(default_output_combo_index)

                except Exception as e:
                    print(f"Error querying devices: {e}")
                    import traceback
                    traceback.print_exc()
                    target_input.addItem("خطأ في الأجهزة")
                    target_output.addItem("خطأ في الأجهزة")

            # Unblock signals
            target_input.blockSignals(False)
            target_output.blockSignals(False)
            
            # Trigger update for output manually after unblocking
            if target_output.count() > 0:
                QTimer.singleShot(0, lambda: self.on_output_device_changed(target_output.currentIndex()))

        except Exception as e:
            print(f"Critical Error in populate_audio_devices: {e}")
            import traceback
            traceback.print_exc()

        finally:
            self._is_populating_devices = False

    def on_output_device_changed(self, index):
        if index < 0 or not self.combo_output_device: return
        
        # Save the full display name to restore selection later
        device_display_name = self.combo_output_device.currentText()
        self.settings["output_device_name"] = device_display_name
        save_settings(self.settings)
        
        # Extract clean name for VLC matching using the stored index
        try:
            dev_idx = self.combo_output_device.itemData(index)
            self.output_device_id = dev_idx # NEW: Store ID for feedback loop
            if dev_idx is not None and SD_AVAILABLE:
                device_info = sd.query_devices(dev_idx)
                raw_name = device_info.get('name', '')
                self._set_vlc_output_device(raw_name)
        except Exception as e:
            print(f"Error getting raw device name: {e}")

    def _set_vlc_output_device(self, target_name):
        """Attempts to set the VLC audio output device by matching the name."""
        if not self.media_player or not VLC_AVAILABLE or not target_name: return
        try:
            mods = self.media_player.audio_output_device_enum()
            if mods:
                device = mods
                while device:
                    description = device.contents.description.decode('utf-8', 'ignore')
                    # Improved matching: case-insensitive
                    if target_name.lower() in description.lower() or description.lower() in target_name.lower():
                        self.media_player.audio_output_device_set(None, device.contents.device)
                        print(f"VLC Output set to: {description}")
                        break
                    device = device.contents.next
                vlc.libvlc_audio_output_device_list_release(mods)
        except Exception as e:
            print(f"Error setting VLC output: {e}")

    def on_volume_changed(self, value):
        """Sets the media player volume and updates the label."""
        if self.media_player:
            self.media_player.audio_set_volume(value)
        if self.volume_label:
            self.volume_label.setText(f"{value}%")
            
            # Change label color based on volume for extra feedback
            if value > 100:
                self.volume_label.setStyleSheet("color: #C0392B; font-weight: bold;") # Red
            elif value > 80:
                self.volume_label.setStyleSheet("color: #F39C12; font-weight: bold;") # Orange
            else:
                self.volume_label.setStyleSheet("color: #27AE60; font-weight: bold;") # Green
        # The setting will be saved on closeEvent

    def on_justify_text_toggled(self, state):
        """Handles toggling of text justification and saves the setting."""
        self.justify_text = (state == Qt.CheckState.Checked)
        self.settings["justify_text"] = self.justify_text
        save_settings(self.settings)
        # Re-render the page to apply justification immediately
        self.page_renderer.render_page(self.current_page)

    def on_dynamic_mode_toggled(self, state):
        """Handles toggling of dynamic display mode."""
        self.view_mode = "dynamic" if state else "two_pages"
        self.settings["view_mode"] = self.view_mode
        save_settings(self.settings)
        self.page_renderer.render_page(self.current_page)

    def on_language_changed(self, index):
        """Handles language change."""
        lang_code = self.combo_language.itemData(index)
        self.settings["app_language"] = lang_code
        save_settings(self.settings)
        
        # --- FIX: Update translations immediately ---
        self.language = lang_code
        self.translations = TRANSLATIONS.get(self.language, TRANSLATIONS["ar"])
        
        # --- NEW: Apply translations to UI immediately ---
        self.retranslate_ui()
        
        self.show_toast(self.tr("lang_saved_message"), temporary=True)

    def on_highlight_color_changed(self, index):
        """Handles highlight color change."""
        color_key = self.combo_highlight_color.itemData(index)
        self.settings["highlight_color_key"] = color_key
        self.playlist_highlight_color = self.highlight_colors.get(color_key, self.highlight_colors["yellow"])
        save_settings(self.settings)

    def retranslate_ui(self):
        """Updates texts of UI elements to the current language."""
        # --- Window Title ---
        self.setWindowTitle(self.tr("app_title") + " - Light")

        # Tabs
        if hasattr(self, 'right_panel') and isinstance(self.right_panel, QTabWidget):
            self.right_panel.setTabText(0, self.tr("plans_tab"))
            self.right_panel.setTabText(1, self.tr("settings_tab"))
            self.right_panel.setTabText(2, self.tr("playlist_tab"))
            self.right_panel.setTabText(3, self.tr("review_tab"))

        # --- Group Boxes (Handles both normal and collapsible) ---
        def set_group_title(group_box, key):
            title = self.tr(key)
            if hasattr(group_box, 'collapsible_box'):
                group_box.collapsible_box.toggle_button.setText(title)
            else:
                group_box.setTitle(title)

        if hasattr(self, 'grp_tasmee_info'): set_group_title(self.grp_tasmee_info, "review_tab")
        if hasattr(self, 'grp_prayer_times'): set_group_title(self.grp_prayer_times, "prayer_times_group")
        if hasattr(self, 'grp_range_info'): set_group_title(self.grp_range_info, "range_info_group")
        if hasattr(self, 'grp_nav'): set_group_title(self.grp_nav, "nav_group")
        if hasattr(self, 'grp_general_settings'): set_group_title(self.grp_general_settings, "general_settings")
        if hasattr(self, 'grp_user_mgmt'): set_group_title(self.grp_user_mgmt, "user_management")
        if hasattr(self, 'grp_display_settings'): set_group_title(self.grp_display_settings, "display_font_settings")
        if hasattr(self, 'grp_prayer_settings'): set_group_title(self.grp_prayer_settings, "prayer_settings_group")
        if hasattr(self, 'grp_widget_settings'): set_group_title(self.grp_widget_settings, "widget_settings_group")
        if hasattr(self, 'grp_select_reciter'): set_group_title(self.grp_select_reciter, "select_reciter_group")
        if hasattr(self, 'grp_select_range'): set_group_title(self.grp_select_range, "select_range_group")
        if hasattr(self, 'options_group'): set_group_title(self.options_group, "playback_mode_group")
        if hasattr(self, 'grp_repeat_options'): set_group_title(self.grp_repeat_options, "repeat_options_group")
        if hasattr(self, 'grp_audio_player'): set_group_title(self.grp_audio_player, "audio_player_group")
        if hasattr(self, 'grp_visual_review'): set_group_title(self.grp_visual_review, "visual_review_group")
        if hasattr(self, 'grp_control'): set_group_title(self.grp_control, "control_group")
        if hasattr(self, 'grp_manual_adj'): set_group_title(self.grp_manual_adj, "manual_adj_group")

        # --- NEW: Voice Trigger Group ---
        if hasattr(self, 'grp_voice_trigger'): set_group_title(self.grp_voice_trigger, "voice_review_group")
        
        if hasattr(self, 'lbl_voice_sensitivity'): self.lbl_voice_sensitivity.setText(self.tr("voice_sensitivity"))
        if hasattr(self, 'lbl_voice_speed'): self.lbl_voice_speed.setText(self.tr("voice_speed"))
        
        if hasattr(self, 'combo_voice_speed'):
            current = self.combo_voice_speed.currentIndex()
            self.combo_voice_speed.setItemText(0, self.tr("speed_slow"))
            self.combo_voice_speed.setItemText(1, self.tr("speed_medium"))
            self.combo_voice_speed.setItemText(2, self.tr("speed_fast"))
            self.combo_voice_speed.setItemText(3, self.tr("speed_very_fast"))
            self.combo_voice_speed.setCurrentIndex(current)

        # --- SpinBox Suffixes/Prefixes ---
        if hasattr(self, 'spin_review_repetitions'): 
            self.spin_review_repetitions.setPrefix(self.tr("repetition_prefix"))
        
        if hasattr(self, 'spin_auto_reveal_time'):
            self.spin_auto_reveal_time.setSuffix(self.tr("suffix_sec_page"))

        if hasattr(self, 'spin_auto_reveal_pause'):
            self.spin_auto_reveal_pause.setSuffix(self.tr("suffix_sec"))
            self.spin_auto_reveal_pause.setToolTip(self.tr("pause_tooltip"))

        if hasattr(self, 'spin_time_offset'):
             self.spin_time_offset.setSuffix(self.tr("suffix_min"))

        # --- Labels ---
        if hasattr(self, 'lbl_count_text'): self.lbl_count_text.setText(self.tr("count_lbl"))
        if hasattr(self, 'lbl_duration_text'): self.lbl_duration_text.setText(self.tr("duration_lbl"))
        if hasattr(self, 'lbl_repetition_text'): self.lbl_repetition_text.setText(self.tr("repetition_lbl"))
        if hasattr(self, 'lbl_page_nav'): self.lbl_page_nav.setText(self.tr("page_lbl"))
        if hasattr(self, 'lbl_sura_nav'): self.lbl_sura_nav.setText(self.tr("sura_lbl"))
        if hasattr(self, 'lbl_juz_nav'): self.lbl_juz_nav.setText(self.tr("juz_lbl"))
        if hasattr(self, 'lbl_interface_lang'): self.lbl_interface_lang.setText(self.tr("interface_language"))
        if hasattr(self, 'lbl_font_setting'): self.lbl_font_setting.setText(self.tr("font"))
        if hasattr(self, 'lbl_highlight_color'): self.lbl_highlight_color.setText(self.tr("highlight_color"))
        if hasattr(self, 'lbl_calc_method'): self.lbl_calc_method.setText(self.tr("calc_method_lbl"))
        if hasattr(self, 'lbl_time_offset'): self.lbl_time_offset.setText(self.tr("time_offset_lbl"))
        if hasattr(self, 'lbl_widget_colors'): self.lbl_widget_colors.setText(self.tr("lbl_widget_colors"))
        if hasattr(self, 'lbl_widget_font_size'): self.lbl_widget_font_size.setText(self.tr("lbl_widget_font_size"))
        if hasattr(self, 'lbl_select_sheikh'): self.lbl_select_sheikh.setText(self.tr("select_sheikh_lbl"))
        if hasattr(self, 'lbl_single_repeat'): self.lbl_single_repeat.setText(self.tr("single_repeat_lbl"))
        if hasattr(self, 'lbl_group_repeat'): self.lbl_group_repeat.setText(self.tr("group_repeat_lbl"))
        if hasattr(self, 'lbl_complex_single'): self.lbl_complex_single.setText(self.tr("complex_single_lbl"))
        if hasattr(self, 'lbl_complex_group'): self.lbl_complex_group.setText(self.tr("complex_group_lbl"))
        if hasattr(self, 'lbl_complex_size'): self.lbl_complex_size.setText(self.tr("complex_size_lbl"))
        if hasattr(self, 'lbl_speed'): self.lbl_speed.setText(self.tr("speed_lbl"))
        if hasattr(self, 'lbl_volume'): self.lbl_volume.setText(self.tr("volume_lbl"))
        if hasattr(self, 'lbl_review_from'): self.lbl_review_from.setText(self.tr("from_lbl"))
        if hasattr(self, 'lbl_review_to'): self.lbl_review_to.setText(self.tr("to_lbl"))
        if hasattr(self, 'lbl_reveal_speed'): self.lbl_reveal_speed.setText(self.tr("reveal_speed_lbl"))
        if hasattr(self, 'lbl_pause_at_ayah'): self.lbl_pause_at_ayah.setText(self.tr("pause_at_ayah_lbl"))
        if hasattr(self, 'lbl_lat'): self.lbl_lat.setText(self.tr("lat_lbl"))
        if hasattr(self, 'lbl_lng'): self.lbl_lng.setText(self.tr("lng_lbl"))
        if hasattr(self, 'lbl_coords_manual'): self.lbl_coords_manual.setText(self.tr("coords_manual_lbl"))
        
        # Prayer Adjustment Labels
        if hasattr(self, 'lbl_adj_fajr'): self.lbl_adj_fajr.setText(self.tr("prayer_fajr"))
        if hasattr(self, 'lbl_adj_sunrise'): self.lbl_adj_sunrise.setText(self.tr("prayer_sunrise"))
        if hasattr(self, 'lbl_adj_dhuhr'): self.lbl_adj_dhuhr.setText(self.tr("prayer_dhuhr"))
        if hasattr(self, 'lbl_adj_asr'): self.lbl_adj_asr.setText(self.tr("prayer_asr"))
        if hasattr(self, 'lbl_adj_maghrib'): self.lbl_adj_maghrib.setText(self.tr("prayer_maghrib"))
        if hasattr(self, 'lbl_adj_isha'): self.lbl_adj_isha.setText(self.tr("prayer_isha"))

        # --- NEW: Update Azan Labels ---
        if hasattr(self, 'azan_labels'):
            for eng_name, lbl in self.azan_labels.items():
                lbl.setText(f"{self.tr(f'prayer_{eng_name.lower()}')}:")
        
        if hasattr(self, 'check_enable_duaa') and self.check_enable_duaa:
            self.check_enable_duaa.setText(self.tr("enable_duaa"))
            self.check_enable_duaa.setToolTip(self.tr("enable_duaa_tooltip"))

        # --- NEW: Update Profile Button ---
        if hasattr(self, 'btn_profile') and self.btn_profile:
             btn_text = f"👤 {self.user_manager.current_user}" if self.user_manager.current_user else f"👤 {self.tr('my_profile')}"
             self.btn_profile.setText(btn_text)

        # Buttons & Labels
        if hasattr(self, 'btn_update_location') and self.btn_update_location: self.btn_update_location.setToolTip(self.tr("update_location_tooltip"))
        if hasattr(self, 'help_button') and self.help_button: self.help_button.setText(self.tr("user_guide"))
        if hasattr(self, 'btn_switch_user') and self.btn_switch_user: self.btn_switch_user.setText(self.tr("switch_user"))
        if hasattr(self, 'btn_zoom_in') and self.btn_zoom_in: self.btn_zoom_in.setText(self.tr("zoom_in"))
        if hasattr(self, 'btn_zoom_out') and self.btn_zoom_out: self.btn_zoom_out.setText(self.tr("zoom_out"))
        if hasattr(self, 'btn_zoom_reset') and self.btn_zoom_reset: self.btn_zoom_reset.setText(self.tr("reset"))
        if hasattr(self, 'btn_change_bg') and self.btn_change_bg: self.btn_change_bg.setText(self.tr("mushaf_bg_color"))
        if hasattr(self, 'btn_change_text_color') and self.btn_change_text_color: self.btn_change_text_color.setText(self.tr("quran_text_color"))
        if hasattr(self, 'btn_select_border_image') and self.btn_select_border_image: self.btn_select_border_image.setText(self.tr("border_image"))
        if hasattr(self, 'btn_change_review_color') and self.btn_change_review_color: self.btn_change_review_color.setText(self.tr("review_text_color"))
        if hasattr(self, 'btn_change_quran_font') and self.btn_change_quran_font: self.btn_change_quran_font.setText(self.tr("change_quran_font"))
        if hasattr(self, 'btn_toggle_aya_markers') and self.btn_toggle_aya_markers: 
            self.btn_toggle_aya_markers.setText(self.tr("hide_ayah_markers") if self.show_aya_markers else self.tr("show_ayah_markers"))
        if hasattr(self, 'check_justify_text') and self.check_justify_text: self.check_justify_text.setText(self.tr("enable_text_justification"))
        if hasattr(self, 'check_dynamic_mode') and self.check_dynamic_mode: self.check_dynamic_mode.setText(self.tr("enable_dynamic_view"))
        
        # Tooltips Updates
        if hasattr(self, 'check_justify_text'): self.check_justify_text.setToolTip(self.tr("justify_tooltip"))
        if hasattr(self, 'check_dynamic_mode'): self.check_dynamic_mode.setToolTip(self.tr("dynamic_view_tooltip"))
        if hasattr(self, 'btn_change_bg'): self.btn_change_bg.setToolTip(self.tr("mushaf_bg_color_tooltip"))
        if hasattr(self, 'btn_change_text_color'): self.btn_change_text_color.setToolTip(self.tr("quran_text_color_tooltip"))
        if hasattr(self, 'btn_change_review_color'): self.btn_change_review_color.setToolTip(self.tr("review_text_color_tooltip"))
        if hasattr(self, 'btn_select_border_image'): self.btn_select_border_image.setToolTip(self.tr("border_image_tooltip"))
        if hasattr(self, 'btn_switch_user'): self.btn_switch_user.setToolTip(self.tr("switch_user_tooltip"))
        if hasattr(self, 'check_playback_review_mode'): self.check_playback_review_mode.setToolTip(self.tr("playback_review_mode_tooltip"))

        # Widget Settings
        if hasattr(self, 'chk_show_widget') and self.chk_show_widget: self.chk_show_widget.setText(self.tr("chk_show_widget"))
        if hasattr(self, 'chk_widget_on_top') and self.chk_widget_on_top: self.chk_widget_on_top.setText(self.tr("chk_widget_on_top"))
        if hasattr(self, 'btn_widget_bg_color') and self.btn_widget_bg_color: self.btn_widget_bg_color.setText(self.tr("btn_widget_bg_color"))
        if hasattr(self, 'btn_widget_text_color') and self.btn_widget_text_color: self.btn_widget_text_color.setText(self.tr("btn_widget_text_color"))
        if hasattr(self, 'lbl_widget_opacity') and self.lbl_widget_opacity: self.lbl_widget_opacity.setText(self.tr("lbl_widget_opacity"))

        # Playlist
        if hasattr(self, 'btn_select_main_folder') and self.btn_select_main_folder: 
            if not self.main_audio_folder: self.btn_select_main_folder.setText(self.tr("select_folder_btn"))
        if hasattr(self, 'btn_select_start_file') and self.btn_select_start_file: self.btn_select_start_file.setText(self.tr("from_btn"))
        if hasattr(self, 'btn_select_end_file') and self.btn_select_end_file: self.btn_select_end_file.setText(self.tr("to_btn"))
        if hasattr(self, 'btn_update_files') and self.btn_update_files: self.btn_update_files.setText(self.tr("update_playlist_btn"))
        if hasattr(self, 'btn_play_single') and self.btn_play_single: self.btn_play_single.setText(self.tr("play_single_btn"))
        if hasattr(self, 'btn_play_group') and self.btn_play_group: self.btn_play_group.setText(self.tr("play_group_btn"))
        if hasattr(self, 'btn_play_complex') and self.btn_play_complex: self.btn_play_complex.setText(self.tr("play_complex_btn"))
        if hasattr(self, 'check_playback_review_mode') and self.check_playback_review_mode: self.check_playback_review_mode.setText(self.tr("playback_review_mode_chk"))

        # Azan File Placeholders
        if hasattr(self, 'azan_file_widgets'):
            for widget in self.azan_file_widgets.values():
                widget.setPlaceholderText(self.tr("default_random"))

        # Review
        if hasattr(self, 'btn_auto_reveal_start') and self.btn_auto_reveal_start: 
            if getattr(self, 'is_auto_reveal_mode', False):
                if self.auto_reveal_timer.isActive():
                     self.btn_auto_reveal_start.setText(self.tr("pause"))
                else:
                     self.btn_auto_reveal_start.setText(self.tr("resume_display"))
            else:
                 self.btn_auto_reveal_start.setText(self.tr("start_reveal_btn"))
        if hasattr(self, 'btn_auto_reveal_stop') and self.btn_auto_reveal_stop: self.btn_auto_reveal_stop.setText(self.tr("stop_btn"))
        
        # Voice Trigger
        if hasattr(self, 'btn_voice_trigger_start') and self.btn_voice_trigger_start:
             if getattr(self, 'is_voice_trigger_active', False):
                 if getattr(self, 'voice_trigger_paused', False):
                     self.btn_voice_trigger_start.setText(self.tr("resume_voice_review"))
                 else:
                     self.btn_voice_trigger_start.setText(self.tr("pause_voice_review"))
             else:
                 self.btn_voice_trigger_start.setText(self.tr("start_voice_review"))
        if hasattr(self, 'btn_voice_trigger_stop') and self.btn_voice_trigger_stop: self.btn_voice_trigger_stop.setText(self.tr("stop_voice_review"))

        # Plans
        if hasattr(self, 'daily_tasks_box') and self.daily_tasks_box: self.daily_tasks_box.toggle_button.setText(self.tr("daily_tasks_title"))
        if hasattr(self, 'plan_mgmt_box') and self.plan_mgmt_box: self.plan_mgmt_box.toggle_button.setText(self.tr("plan_management"))
        if hasattr(self, 'btn_add_plan') and self.btn_add_plan: self.btn_add_plan.setText(self.tr("add_new_plan"))

        # --- Update Combo Boxes ---
        # Highlight Color
        if hasattr(self, 'combo_highlight_color'):
            current_idx = self.combo_highlight_color.currentIndex()
            self.combo_highlight_color.setItemText(0, self.tr("yellow_default"))
            self.combo_highlight_color.setItemText(1, self.tr("green"))
            self.combo_highlight_color.setItemText(2, self.tr("blue"))
            self.combo_highlight_color.setItemText(3, self.tr("red"))
            self.combo_highlight_color.setItemText(4, self.tr("orange"))
            self.combo_highlight_color.setItemText(5, self.tr("purple"))
            self.combo_highlight_color.setCurrentIndex(current_idx)

        # Calc Method
        if hasattr(self, 'combo_calc_method'):
            current_idx = self.combo_calc_method.currentIndex()
            self.combo_calc_method.setItemText(0, self.tr("calc_method_egypt"))
            self.combo_calc_method.setItemText(1, self.tr("calc_method_makkah"))
            self.combo_calc_method.setItemText(2, self.tr("calc_method_karachi"))
            self.combo_calc_method.setItemText(3, self.tr("calc_method_isna"))
            self.combo_calc_method.setItemText(4, self.tr("calc_method_mwl"))
            self.combo_calc_method.setCurrentIndex(current_idx)

        # Language Combo
        if hasattr(self, 'combo_language'):
            current_idx = self.combo_language.currentIndex()
            self.combo_language.setItemText(0, self.tr("arabic"))
            self.combo_language.setItemText(1, self.tr("english"))
            self.combo_language.setCurrentIndex(current_idx)

        # --- Update Tray Icon ---
        if hasattr(self, 'toggle_main_window_action'):
            self.toggle_main_window_action.setText(self.tr("tray_hide_app") if self.isVisible() else self.tr("tray_show_app"))
        if hasattr(self, 'toggle_widget_action'):
            self.toggle_widget_action.setText(self.tr("tray_hide_widget") if self.prayer_widget.isVisible() else self.tr("tray_show_widget"))

        # --- Refresh Plans UI (to update translated texts inside plan cards) ---
        self.refresh_plans_ui()

        # --- NEW: Update Prayer Info ---
        self._update_next_prayer()
        self._update_clock_and_prayers()

    def on_sura_combo_changed(self, index):
        """Handles the Sura combobox value change."""
        if self._user_navigating: return

        # The combo_sura's signals are blocked during programmatic updates,
        # so this only fires on genuine user interaction.
        sura_no = self.combo_sura.currentData()
        if sura_no in self.data_manager.sura_pages:
            target_page = self.data_manager.sura_pages[sura_no]
            if self.current_page != target_page:
                self._user_navigating = True
                try:
                    self.on_page_changed(target_page)
                finally:
                    self._user_navigating = False

    # --- FIX: Correct type hint for resizeEvent ---
    # تم تغيير اسم المتغير a0 إلى event لزيادة الوضوح
    def resizeEvent(self, a0: QResizeEvent):
        super().resizeEvent(a0)  # استدعاء الدالة الأصلية
        # Re-render on resize to adjust page layout
        if self.page_renderer:
            self.page_renderer.render_page(self.current_page)
            
            # --- FIX: Re-apply Masks if active after resize (Critical for Review Mode) ---
            if getattr(self, 'is_auto_reveal_mode', False):
                self._apply_auto_reveal_mask()
            if getattr(self, 'is_voice_trigger_active', False):
                self._apply_voice_trigger_mask()
        
        # --- FIX: Resize Azan label if visible to cover the view ---
        if hasattr(self, 'azan_label') and self.azan_label.isVisible():
            self.azan_label.resize(self.view.size())

    def _load_font(self):
        """Loads fonts... (existing code)"""
        # ... (existing code) ...
        pass

    # --- NEW: Plan Management Logic ---
    def refresh_plans_ui(self):
        """Rebuilds the UI for Daily Tasks and Plan Management."""
        if not hasattr(self, 'daily_tasks_layout') or not hasattr(self, 'plans_list_layout'):
            return

        # 1. Clear existing items
        def clear_layout(layout):
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        clear_layout(self.daily_tasks_layout)
        clear_layout(self.plans_list_layout)

        # 2. Build UI from self.plans
        for i, plan in enumerate(self.plans):
            self._create_plan_widgets(i, plan)

    def copy_plan_data_to_clipboard(self, plan):
        """Copies the raw plan data to clipboard for debugging."""
        try:
            json_str = json.dumps(plan, indent=4, ensure_ascii=False, default=str)
            QApplication.clipboard().setText(json_str)
            self.show_toast("تم نسخ بيانات الخطة للحافظة ✅", temporary=True)
        except Exception as e:
            print(f"Error copying plan data: {e}")
            self.show_toast("فشل نسخ البيانات ❌", temporary=True)

    def _create_plan_widgets(self, index, plan):
        # ... (Existing code start) ...
        plan_type = plan.get('type', 'memorization')
        name = plan.get('name', 'خطة بلا اسم')
        
        # --- NEW: Check for Today's Task ---
        today_str = QDate.currentDate().toString(Qt.ISODate)
        schedule = plan.get('schedule', {})
        today_task = schedule.get(today_str)
        
        if today_task:
            if today_task.get('is_rest_day', False):
                range_str = self.tr("today_rest")
            else:
                # --- Enhanced Detail: Show Surah names and Ayah ranges ---
                pages = today_task.get('pages', '?')
                from_sura = today_task.get('from_sura')
                from_aya = today_task.get('from_aya')
                to_sura = today_task.get('to_sura')
                to_aya = today_task.get('to_aya')
                
                details_text = ""
                if from_sura and to_sura:
                    sura_name_from = self.data_manager.get_sura_name(from_sura)
                    if from_sura == to_sura:
                        details_text = self.tr("sura_name_range", sura_name_from, from_aya, to_aya)
                    else:
                        sura_name_to = self.data_manager.get_sura_name(to_sura)
                        details_text = self.tr("sura_range_arrow", sura_name_from, from_aya, sura_name_to, to_aya)
                
                range_str = f"{details_text}{self.tr('page_prefix', pages)}"
            is_today_active = True
        else:
            # If no task today, show generic info
            range_str = self.tr("no_task_today")
            is_today_active = False
            
        # Only show in "Daily Tasks" if there is a task for today OR user wants to see all
        # For now, we show all but highlight today's status
        
        # --- Color Coding ---
        colors = {
            "memorization": ("#E3F2FD", "#1E88E5", "📘"), # Blue (Hifz)
            "review":       ("#E8F5E9", "#43A047", "📗"), # Green (Review)
            "listening":    ("#F3E5F5", "#8E24AA", "🎧"), # Purple (Listening)
            "repetition":   ("#FFF3E0", "#E65100", "🔁")  # Orange (Repetition)
        }
        bg_color, border_color, icon = colors.get(plan_type, ("#FFFFFF", "#000000", "❓"))

        # --- 1. Task Card (For Daily Tasks Section) ---
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 5px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        
        header_layout = QHBoxLayout()
        title_lbl = QLabel(f"{icon} {name}")
        title_lbl.setStyleSheet(f"font-weight: bold; color: {border_color}; font-size: 14px; border: none;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        
        # Start Button
        btn_start = QPushButton(self.tr("start_btn"))
        btn_start.setCursor(Qt.PointingHandCursor)
        btn_start.setStyleSheet(f"""
            QPushButton {{
                background-color: {border_color}; color: white; border: none; border-radius: 4px; padding: 4px 10px;
            }}
            QPushButton:hover {{ background-color: black; }}
        """)
        btn_start.clicked.connect(lambda checked, p=plan: self.start_plan_task(p))
        header_layout.addWidget(btn_start)
        
        card_layout.addLayout(header_layout)
        
        # Custom display for Repetition Challenge
        if plan_type == "repetition":
            current = plan.get('current_repetitions', 0)
            target = plan.get('target_repetitions', 30)
            pct = int((current / target) * 100) if target > 0 else 0
            info_text = self.tr("progress_lbl", current, target, pct)
        else:
            info_text = self.tr("task_lbl", range_str)

        range_lbl = QLabel(info_text)
        range_lbl.setStyleSheet("color: #555; font-size: 12px; border: none;")
        card_layout.addWidget(range_lbl)

        # Add to daily tasks if active today OR if it's a repetition challenge (always active)
        if is_today_active or plan_type == "repetition": 
            self.daily_tasks_layout.addWidget(card)

        # --- 2. Management Item (For Plan Management Section) ---
        mgmt_item = QWidget()
        mgmt_layout = QHBoxLayout(mgmt_item)
        mgmt_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_name = QLabel(f"{icon} {name}")
        
        btn_details = QPushButton()
        btn_details.setIcon(QIcon(resource_path("assets/table.png")))
        btn_details.setToolTip(self.tr("plan_details_tooltip"))
        btn_details.setFixedWidth(30)
        btn_details.clicked.connect(lambda checked, p=plan: self.view_plan_details(p))
        
        # NEW: Debug Copy Button
        btn_copy_debug = QPushButton()
        btn_copy_debug.setIcon(QIcon(resource_path("assets/copy.png")))
        btn_copy_debug.setToolTip(self.tr("copy_debug_tooltip"))
        btn_copy_debug.setFixedWidth(30)
        btn_copy_debug.setStyleSheet("background-color: #E8F5E9; border: 1px solid #C8E6C9;")
        btn_copy_debug.clicked.connect(lambda checked, p=plan: self.copy_plan_data_to_clipboard(p))
        
        btn_edit = QPushButton()
        btn_edit.setIcon(QIcon(resource_path("assets/create.png")))
        btn_edit.setToolTip(self.tr("edit_plan_tooltip"))
        btn_edit.setFixedWidth(30)
        btn_edit.clicked.connect(lambda checked, idx=index: self.edit_plan(idx))

        btn_delete = QPushButton()
        btn_delete.setIcon(QIcon(resource_path("assets/delete.png")))
        btn_delete.setToolTip(self.tr("delete_plan_tooltip"))
        btn_delete.setFixedWidth(30)
        btn_delete.setStyleSheet("background-color: #FFEBEE; color: #C62828; border: 1px solid #FFCDD2;")
        btn_delete.clicked.connect(lambda checked, idx=index: self.delete_plan(idx))
        
        mgmt_layout.addWidget(lbl_name)
        mgmt_layout.addStretch()
        mgmt_layout.addWidget(btn_copy_debug)
        mgmt_layout.addWidget(btn_details)
        mgmt_layout.addWidget(btn_edit)
        mgmt_layout.addWidget(btn_delete)
        
        self.plans_list_layout.addWidget(mgmt_item)

    def _generate_schedule_logic(self, pages, daily_amount, start_date, active_days_set):
        """Helper to generate schedule dictionary."""
        schedule = {}
        current_date = start_date
        current_page_idx = 0.0
        total_pages_count = len(pages)
        
        # --- FIX: Prevent infinite loop if no active days ---
        if not active_days_set:
            return {}
        
        while current_page_idx < total_pages_count:
            if current_date.dayOfWeek() not in active_days_set:
                # Insert rest day entry
                date_str = current_date.toString(Qt.ISODate)
                day_names = {1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس", 5: "الجمعة", 6: "السبت", 7: "الأحد"}
                day_name = day_names.get(current_date.dayOfWeek(), "")
                schedule[date_str] = {
                    "pages": "راحة", "day_name": day_name, "completed": True, "is_rest_day": True,
                    "from_sura": 0, "from_aya": 0, "to_sura": 0, "to_aya": 0
                }
                current_date = current_date.addDays(1)
                continue
            
            start_idx = int(current_page_idx)
            end_idx = int(current_page_idx + daily_amount)
            if end_idx == start_idx and daily_amount < 1.0: end_idx = start_idx + 1
            end_idx = min(end_idx, total_pages_count)
            
            if daily_amount < 1.0:
                 chunk_pages = [pages[int(current_page_idx)]]
            else:
                 chunk_pages = pages[start_idx:end_idx]
            
            if not chunk_pages: break

            # Range formatting
            ranges = []
            if chunk_pages:
                range_start = chunk_pages[0]
                prev_page = range_start
                for page in chunk_pages[1:]:
                    if page != prev_page + 1:
                        ranges.append(f"{range_start}-{prev_page}" if range_start != prev_page else f"{range_start}")
                        range_start = page
                    prev_page = page
                ranges.append(f"{range_start}-{prev_page}" if range_start != prev_page else f"{range_start}")
            pages_str = "، ".join(ranges)

            start_p = chunk_pages[0]
            end_p = chunk_pages[-1]
            
            ayas_start = self.data_manager.pages_by_number.get(str(start_p), []) or self.data_manager.pages_by_number.get(start_p, [])
            if not ayas_start: break
            first_aya = ayas_start[0]
            
            ayas_end = self.data_manager.pages_by_number.get(str(end_p), []) or self.data_manager.pages_by_number.get(end_p, [])
            if not ayas_end: break
            last_aya = ayas_end[-1]
            
            date_str = current_date.toString(Qt.ISODate)
            day_names = {1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس", 5: "الجمعة", 6: "السبت", 7: "الأحد"}
            day_name = day_names.get(current_date.dayOfWeek(), "")
            
            schedule[date_str] = {
                "from_sura": first_aya['sura_no'], "from_aya": first_aya['aya_no'],
                "to_sura": last_aya['sura_no'], "to_aya": last_aya['aya_no'],
                "pages": pages_str, "day_name": day_name, "completed": False
            }
            current_page_idx += daily_amount
            current_date = current_date.addDays(1)
        return schedule

    def _get_pages_from_segments(self, segments):
        """Helper to extract ordered list of pages from plan segments."""
        all_pages = []
        for seg in segments:
            if seg['type'] == 'sura':
                sura = seg['val']
                start_page = self.data_manager.sura_pages.get(sura)
                next_sura = sura + 1
                end_page = self.data_manager.sura_pages.get(next_sura, 605) - 1
                if start_page:
                    for p in range(start_page, end_page + 1):
                        if p not in all_pages: all_pages.append(p)
            elif seg['type'] == 'juz':
                juz = seg['val']
                start_page = self.data_manager.juz_pages.get(juz)
                next_juz = juz + 1
                end_page = self.data_manager.juz_pages.get(next_juz, 605) - 1
                if start_page:
                    for p in range(start_page, end_page + 1):
                        if p not in all_pages: all_pages.append(p)
            elif seg['type'] == 'page_range':
                for p in range(seg['from'], seg['to'] + 1):
                    if p not in all_pages: all_pages.append(p)
            elif seg['type'] == 'surah_range' or seg['type'] == 'full_quran': # Handle legacy full_quran as well
                # Legacy support for 'full_quran' type
                if seg['type'] == 'full_quran':
                    start_s = 1 if seg.get('direction') == 'normal' else 114
                    end_s = 114 if seg.get('direction') == 'normal' else 1
                else:
                    start_s = seg['from_sura']
                    end_s = seg['to_sura']
                
                step = 1 if start_s <= end_s else -1
                # Range is exclusive at the end, so we add step
                surahs_sequence = range(start_s, end_s + step, step)
                
                for s in surahs_sequence:
                    s_start_page = self.data_manager.sura_pages.get(s)
                    s_end_page = self.data_manager.sura_pages.get(s + 1, 605) - 1
                    if s_start_page:
                        for p in range(s_start_page, s_end_page + 1):
                            if p not in all_pages: all_pages.append(p)
            elif seg['type'] == 'verse_range':
                # Explicit captured range
                p1 = self.get_page_for_sura_aya(seg['from_sura'], seg['from_aya']) or 1
                p2 = self.get_page_for_sura_aya(seg['to_sura'], seg['to_aya']) or 1
                # Add all pages in between
                for p in range(min(p1, p2), max(p1, p2) + 1):
                    if p not in all_pages: all_pages.append(p)

            elif seg['type'] == 'current_selection':
                # Use current selection from main UI
                start_sura = self.combo_from_sura.currentData()
                start_aya = self.spin_from_aya.value()
                end_sura = self.combo_to_sura.currentData()
                end_aya = self.spin_to_aya.value()
                p1 = self.get_page_for_sura_aya(start_sura, start_aya) or 1
                p2 = self.get_page_for_sura_aya(end_sura, end_aya) or 1
                for p in range(min(p1, p2), max(p1, p2) + 1):
                    if p not in all_pages: all_pages.append(p)
        return all_pages

    def add_new_plan_dialog(self):
        """Shows the advanced dialog to add a new plan."""
        self._open_plan_dialog(mode='add')

    def _open_plan_dialog(self, mode, index=None):
        """Helper to open PlanCreationDialog in non-modal mode."""
        # Close existing dialog if open
        if hasattr(self, '_active_plan_dialog') and self._active_plan_dialog and self._active_plan_dialog.isVisible():
            self._active_plan_dialog.close()

        plan_data = None
        content_only = False
        
        if mode == 'edit' and index is not None:
            plan_data = self.plans[index]
        elif mode == 'extend' and index is not None:
            plan_data = self.plans[index]
            content_only = True
            
        dialog = PlanCreationDialog(self.data_manager, self, content_only=content_only, plan_data=plan_data)
        
        # Make it non-modal and stay on top
        dialog.setWindowModality(Qt.NonModal)
        dialog.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        
        # Connect signal
        dialog.accepted.connect(lambda: self._handle_plan_dialog_accepted(dialog, mode, index))
        
        self._active_plan_dialog = dialog
        dialog.show()

    def _handle_plan_dialog_accepted(self, dialog, mode, index):
        """Handles the logic after the user clicks OK in the plan dialog."""
        data = dialog.get_data()
        
        # Common logic: Get pages
        if mode == 'extend':
             new_segments = data['segments']
             target_pages = self._get_pages_from_segments(new_segments)
        else:
             target_pages = self._get_pages_from_segments(data['segments'])
             
        if not target_pages and mode != 'extend':
             self.show_toast("لم يتم تحديد أي صفحات للخطة!")
             return
        if mode == 'extend' and not target_pages:
             return

        msg = ""
        # Logic specific to Add/Edit
        if mode in ['add', 'edit']:
            total_pages_count = len(target_pages)
            active_days_set = set(data['active_days'])
            
            # --- FIX: Ensure at least one active day is selected ---
            if not active_days_set:
                self.show_toast("عفواً، يجب تحديد أيام النشاط (يوم واحد على الأقل).")
                return
            
            if data['calc_mode'] == 'duration':
                target_active_days = data['duration_days']
                if target_active_days <= 0: target_active_days = 1
                daily_amount = total_pages_count / target_active_days
            else:
                daily_amount = data['daily_pages']

            # Generate Schedule
            schedule = self._generate_schedule_logic(target_pages, daily_amount, data['start_date'], active_days_set)

            if mode == 'add':
                new_plan = {
                    "name": data['name'],
                    "type": data['type'],
                    "schedule": schedule,
                    "segments": data['segments'],
                    "active_days": data['active_days'],
                    "daily_amount_calculated": daily_amount,
                    "auto_repeat": data['auto_repeat'],
                    "target_repetitions": data.get('target_repetitions', 30),
                    "current_repetitions": 0,
                    "from_sura": 1, "from_aya": 1, "to_sura": 1, "to_aya": 1 
                }
                self.plans.append(new_plan)
                msg = f"تم إنشاء الخطة: {len(schedule)} يوم عمل ✅"
                
            elif mode == 'edit':
                plan = self.plans[index]
                plan['name'] = data['name']
                plan['type'] = data['type']
                plan['schedule'] = schedule
                plan['segments'] = data['segments']
                plan['active_days'] = data['active_days']
                plan['daily_amount_calculated'] = daily_amount
                plan['auto_repeat'] = data['auto_repeat']
                plan['target_repetitions'] = data.get('target_repetitions', plan.get('target_repetitions', 30))
                msg = "تم تعديل الخطة بنجاح ✅"

        elif mode == 'extend':
            plan = self.plans[index]
            schedule = plan.get('schedule', {})
            if schedule:
                last_date_str = max(schedule.keys())
                last_date = QDate.fromString(last_date_str, Qt.ISODate)
                start_date = last_date.addDays(1)
            else:
                start_date = QDate.currentDate()

            daily_amount = plan.get('daily_amount_calculated', 2.0)
            active_days = set(plan.get('active_days', [1,2,3,4,5,6,7]))
            
            additional_schedule = self._generate_schedule_logic(target_pages, daily_amount, start_date, active_days)
            plan['schedule'].update(additional_schedule)
            plan['segments'].extend(new_segments)
            msg = "تمت إضافة المحتوى للخطة ✅"

        # Save and Refresh
        if self.user_manager.current_user:
            self.user_manager.save_plans(self.user_manager.current_user, self.plans)
        self.refresh_plans_ui()
        self.show_toast(msg)

    def delete_plan(self, index):
        if 0 <= index < len(self.plans):
            del self.plans[index]
            if self.user_manager.current_user:
                self.user_manager.save_plans(self.user_manager.current_user, self.plans)
            self.refresh_plans_ui()

    def edit_plan(self, index):
        """Opens the plan creation dialog with existing data to edit."""
        self._open_plan_dialog(mode='edit', index=index)

    def restart_plan(self, plan):
        """Restarts the plan from today."""
        reply = QMessageBox.question(self, 'إعادة تشغيل الخطة', "هل أنت متأكد من إعادة جدولة الخطة لتبدأ من اليوم؟ سيتم فقدان التقدم الحالي.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            # Re-calculate pages from segments
            all_pages = self._get_pages_from_segments(plan.get('segments', []))
            
            daily_amount = plan.get('daily_amount_calculated', 2.0)
            active_days = set(plan.get('active_days', [1,2,3,4,5,6,7]))
            
            new_schedule = self._generate_schedule_logic(all_pages, daily_amount, QDate.currentDate(), active_days)
            plan['schedule'] = new_schedule
            if self.user_manager.current_user:
                self.user_manager.save_plans(self.user_manager.current_user, self.plans)
            self.refresh_plans_ui()
            self.show_toast("تم إعادة جدولة الخطة ✅")

    def check_auto_repeat(self, plan):
        """Checks if plan is finished and auto-repeat is on, then extends it."""
        if not plan.get('auto_repeat', False):
            return

        schedule = plan.get('schedule', {})
        if not schedule: return

        # Check if all tasks are completed or past
        all_completed = all(task.get('completed', False) for task in schedule.values())
        
        if all_completed:
            # Auto-restart logic
            last_date_str = max(schedule.keys())
            last_date = QDate.fromString(last_date_str, Qt.ISODate)
            next_start_date = last_date.addDays(1)
            
            # Re-calculate pages
            all_pages = self._get_pages_from_segments(plan.get('segments', []))

            daily_amount = plan.get('daily_amount_calculated', 2.0)
            active_days = set(plan.get('active_days', [1,2,3,4,5,6,7]))
            
            new_schedule = self._generate_schedule_logic(all_pages, daily_amount, next_start_date, active_days)
            
            # Append new schedule to existing one? Or replace?
            # User said "starts repeating... automatically". Usually implies extending.
            # But keys must be unique dates.
            plan['schedule'].update(new_schedule)
            if self.user_manager.current_user:
                self.user_manager.save_plans(self.user_manager.current_user, self.plans)
            self.refresh_plans_ui()
            self.show_toast("تم تكرار الخطة تلقائياً 🔄")

            self.refresh_plans_ui()

    def extend_plan(self, index):
        """Adds content to the end of an existing plan."""
        self._open_plan_dialog(mode='extend', index=index)

    def start_plan_task(self, plan):
        """Sets up the app based on the plan and switches to the correct tab."""
        # 1. Determine Target Tab & Switch FIRST
        # Tab 0: Plans, 1: Settings, 2: Playlist, 3: Review
        target_tab_index = 0
        if plan['type'] == 'listening':
            target_tab_index = 2 # Playlist
        elif plan['type'] in ['memorization', 'review', 'repetition']:
            target_tab_index = 3 # Review (Redirected from old Tasmee tab)
        
        if hasattr(self, 'right_panel'):
            self.right_panel.setCurrentIndex(target_tab_index)

        # 2. Determine Range (Check if there is a scheduled task for TODAY)
        today_str = QDate.currentDate().toString(Qt.ISODate)
        schedule = plan.get('schedule', {})
        
        task = schedule.get(today_str)
        msg = ""
        
        if task:
            if task.get('is_rest_day', False):
                msg = "اليوم راحة 🛌"
            else:
                self._apply_range_selection(task['from_sura'], task['from_aya'], task['to_sura'], task['to_aya'], interactive=False)
                msg = self.tr("task_activated_msg", task['pages'])
        else:
            # If no task for today, maybe show the first uncompleted task?
            # For now, just show a message or fallback to plan default
            # Let's try to find the next uncompleted task
            found_next = False
            for date_key in sorted(schedule.keys()):
                if date_key >= today_str and not schedule[date_key]['completed'] and not schedule[date_key].get('is_rest_day', False):
                    task = schedule[date_key]
                    self._apply_range_selection(task['from_sura'], task['from_aya'], task['to_sura'], task['to_aya'], interactive=False)
                    msg = self.tr("no_task_activated_next_msg", date_key)
                    found_next = True
                    break
            
            if not found_next:
                msg = self.tr("plan_completed_msg")

        icon = "🎧" if plan['type'] == 'listening' else "📘"
        self.show_toast(f"{icon} {plan['name']}: {msg}")

    def _load_font(self):
        """
        Loads the Uthmanic fonts from the specified file paths.
        This function ensures that the custom Quranic fonts are available to the application.
        """
        self.quran_text_font_family = ""  # For general UI text (Surah headers, page numbers, etc.)
        self.ayah_number_font_family = ""

        # Load Uthmanic font (used for UI elements and as fallback for Quran
        # text display if specialized font fails)
        uthman_font_path = resource_path(UTHMAN_FONT_FILE)
        if os.path.exists(uthman_font_path):
            try:
                id_ = QFontDatabase.addApplicationFont(uthman_font_path)
                families = QFontDatabase.applicationFontFamilies(id_)
                if families:
                    print("Loaded Uthmanic UI font families:", families)
                    # This will be the general UI font
                    self.quran_text_font_family = families[0]
                    # Fallback for ayah numbers if their specific font fails
                    if not self.ayah_number_font_family:
                        self.ayah_number_font_family = families[0]
                else:
                    print(
                        f"Error: No font families found for Uthmanic UI font {uthman_font_path}")
            except Exception as e:
                print(
                    f"Error loading Uthmanic UI font file {uthman_font_path}: {e}")
        else:
            print("Uthmanic UI font file not found:", uthman_font_path)

        # Load font for main Quran text display (to fix diacritics)
        # Only load if it hasn't been set by settings
        if not self.quran_text_display_font_family:
            # استخدام خط Traditional Arabic كخط افتراضي بناءً على طلب المستخدم
            quran_display_font_path = resource_path(QURAN_TEXT_DISPLAY_FONT_FILE)
            if os.path.exists(quran_display_font_path):
                try:
                    id_ = QFontDatabase.addApplicationFont(
                        quran_display_font_path)
                    families = QFontDatabase.applicationFontFamilies(id_)
                    if families:
                        print(
    "Loaded Quran text display font families (default):",
     families)
                        self.quran_text_display_font_family = families[0]
                    else:
                        print(
                            f"Error: No font families found for Quran text display font {quran_display_font_path}")
                except Exception as e:
                    print(
                        f"Error loading Quran text display font file {quran_display_font_path}: {e}")
            else:
                print(
    "Quran text display font file not found:",
     quran_display_font_path)

        # Load Ayah number font
        ayah_num_font_path = resource_path(AYAH_NUMBER_FONT_FILE)
        if os.path.exists(ayah_num_font_path):
            try:
                id_ = QFontDatabase.addApplicationFont(ayah_num_font_path)
                families = QFontDatabase.applicationFontFamilies(id_)
                if families:
                    print("Loaded Ayah number font families:", families)
                    self.ayah_number_font_family = families[0]
                else:
                    print(
                        f"Error: No font families found for Ayah number font {ayah_num_font_path}")
            except Exception as e:
                print(
                    f"Error loading Ayah number font file {ayah_num_font_path}: {e}")
        else:
            print("Ayah number font file not found:", ayah_num_font_path)

    def view_plan_details(self, plan):
        """Shows a dialog with the full schedule of the plan."""
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle(self.tr("plan_details_title", plan.get('name', '')))
            dialog.resize(700, 600)
            dialog.setLayoutDirection(Qt.RightToLeft)
            
            layout = QVBoxLayout(dialog)
            
            # Create Tabs
            tabs = QTabWidget()
            layout.addWidget(tabs)
            
            # --- Tab 1: Schedule Table ---
            tab_schedule = QWidget()
            layout_schedule = QVBoxLayout(tab_schedule)
            
            table = QTableWidget()
            
            # Restart Button
            btn_restart = QPushButton(self.tr("restart_plan_btn"))
            btn_restart.clicked.connect(lambda: self.restart_plan(plan))
            layout_schedule.addWidget(btn_restart)
            
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels([self.tr("table_date"), self.tr("table_task"), self.tr("table_status")])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setAlternatingRowColors(True)
            
            schedule = plan.get('schedule', {})
            sorted_dates = sorted(schedule.keys())
            
            table.setRowCount(len(sorted_dates))
            
            for i, date_str in enumerate(sorted_dates):
                task = schedule[date_str]
                is_completed = task.get('completed', False)
                status = self.tr("status_done") if is_completed else self.tr("status_pending")
                
                # Format date with Day Name
                date_obj = QDate.fromString(date_str, Qt.ISODate)
                day_names = {1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس", 5: "الجمعة", 6: "السبت", 7: "الأحد"}
                day_name = day_names.get(date_obj.dayOfWeek(), "")
                
                item_date = QTableWidgetItem(f"{date_str} ({day_name})")
                if task.get('is_rest_day', False):
                    item_pages = QTableWidgetItem(self.tr("rest_day"))
                    item_status = QTableWidgetItem("-")
                else:
                    item_pages = QTableWidgetItem(f"ص {task.get('pages', '?')}")
                item_status = QTableWidgetItem(status)
                
                item_date.setTextAlignment(Qt.AlignCenter)
                item_pages.setTextAlignment(Qt.AlignCenter)
                item_status.setTextAlignment(Qt.AlignCenter)
                
                if is_completed:
                    item_status.setForeground(QColor("green"))
                
                table.setItem(i, 0, item_date)
                table.setItem(i, 1, item_pages)
                table.setItem(i, 2, item_status)
            
            layout_schedule.addWidget(table)
            tabs.addTab(tab_schedule, self.tr("schedule_tab"))
            
            # --- Tab 2: Raw Data (JSON) ---
            tab_json = QWidget()
            layout_json = QVBoxLayout(tab_json)
            
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            # Convert plan to JSON string for display/copying
            json_str = json.dumps(plan, indent=4, ensure_ascii=False, default=str)
            text_edit.setText(json_str)
            
            btn_copy = QPushButton(self.tr("copy_debug_btn"))
            btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(json_str))
            
            layout_json.addWidget(text_edit)
            layout_json.addWidget(btn_copy)
            
            tabs.addTab(tab_json, self.tr("raw_data_tab"))
            
            dialog.exec_()
        except Exception as e:
            print(f"Error showing plan details: {e}")
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء عرض التفاصيل: {e}")

    def clear_scene(self):
        """
        Clears all items from the graphics scene, effectively blanking the display.
        """
        """Clears all items from the graphics scene and resets word item tracking."""
        self.scene.clear()
        # word_items is now managed by PageRenderer, but we can clear our
        # reference
        if hasattr(self, 'word_items'):
             self.word_items.clear()

    def stop_recording(self):
        """
        Pauses the recording session temporarily. Stops listening but preserves the state.
        """
        print("DIAGNOSTIC: stop_recording (pause) called.")
        if not self.recording:
            return

        self.wake_lock.disable() # Allow sleep when paused
        if self.recitation_duration_timer.isActive():
            self.recitation_duration_timer.stop()
            
        self.pulse_recitation.stop()
        self.pulse_review.stop()
        self.auto_reveal_timer.stop() # Stop auto reveal
        self.voice_monitor_timer.stop() # Stop voice trigger
        self.voice_reveal_timer.stop()
        self.pulse_auto_reveal.stop() # Stop auto reveal pulse

        self.recording = False  # Set flag to stop audio callback and worker processing

        if hasattr(self, 'audio_stream') and self.audio_stream is not None:
            try:
                self.audio_stream.stop()
                self.audio_stream.close()
            except Exception as e:
                print(f"Error closing audio stream during pause: {e}")
            self.audio_stream = None

        # Update UI for paused state
        self.btn_start.setText("استئناف")  # Resume
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)  # Disable the pause button
        # Make the "End Session" button available
        if hasattr(self, 'btn_end_session'):
            self.btn_end_session.setEnabled(True)
        self.progress(
            "🎤 متوقف مؤقتاً. اضغط 'استئناف' أو 'إنهاء' .")
            
    def start_review(self):
        """Starts the session in Review Mode (Hide text, reveal on speak)."""
        if self.recording:
            return
        self.is_review_mode = True
        self.start_recording()

    def change_review_text_color(self):
        """Opens a dialog to change the text color for Review Mode."""
        current_color = self.review_text_color
        color = QColorDialog.getColor(current_color, self, "اختر لون نص المراجعة")
        if color.isValid():
            self.review_text_color = color
            self.settings["review_text_color"] = self.review_text_color.name()
            save_settings(self.settings)
            # If currently in review mode (paused or active), re-render might be needed if we want immediate update

    def end_recitation_session(self):
        """
        Ends the recitation session completely, marks unrecited words as errors,
        and displays the final report. The UI is left in a "review" state.
        """
        print("DIAGNOSTIC: end_recitation_session called.")

        # If it's currently recording, pause it first to safely stop threads.
        if self.recording:
            self.stop_recording()

        if self.recitation_duration_timer.isActive():
            self.recitation_duration_timer.stop()
            
        self.pulse_recitation.stop()
        self.pulse_review.stop()
        self.auto_reveal_timer.stop() # Stop auto reveal
        self.voice_monitor_timer.stop() # Stop voice trigger
        self.voice_reveal_timer.stop()
        self.pulse_auto_reveal.stop() # Stop auto reveal pulse
        self.permanent_toast_message = ""
        self.toast_label.hide()

        # Show recitation range widget
        if hasattr(self, 'recitation_range_widget'):
            self.recitation_range_widget.show()

        self.recording_mode = False  # Officially end the recitation mode

        # --- NEW: Restore Playback Review Mode ---
        if hasattr(self, '_temp_playback_review_mode_backup'):
            self.playback_review_mode = self._temp_playback_review_mode_backup
            # Update checkbox UI if it exists to keep UI in sync
            if self.check_playback_review_mode:
                self.check_playback_review_mode.blockSignals(True)
                self.check_playback_review_mode.setChecked(self.playback_review_mode)
                self.check_playback_review_mode.blockSignals(False)
            del self._temp_playback_review_mode_backup
        
        # --- FIX: Ensure playback_review_mode is OFF after recitation session ends ---
        # This prevents words from remaining hidden if playback_review_mode was
        # active before the recitation session and was re-enabled.
        self.playback_review_mode = False
        self._reset_playback_reveal() # Clear any previously revealed text

        # --- NEW: Handle Review Mode Cleanup ---
        if self.is_review_mode:
            # Reveal all remaining hidden words so the user can see what was left
            for i in range(self.word_pos, len(self._word_page_map)):
                 page_info = self._word_page_map[i]
                 global_idx = f"{page_info[1]}:{page_info[2]}:{page_info[3]}"
                 self.page_renderer.update_word_text_color(global_idx, self.quran_text_color)
            self.is_review_mode = False

        # --- NEW: Check and Update Repetition Challenge Plans ---
        self.update_plan_progress('recitation')

        # --- NEW: Record Progress for User Profile ---
        if hasattr(self, 'user_manager') and self.user_manager.current_user:
            session_stats = {} # (sura, aya) -> {total: 0, correct: 0}
            
            for i, status in enumerate(self._word_statuses):
                if i < len(self._word_page_map):
                    page, sura, aya, word_id = self._word_page_map[i]
                    key = (sura, aya)
                    if key not in session_stats:
                        session_stats[key] = {'total': 0, 'correct': 0}
                    
                    session_stats[key]['total'] += 1
                    if status is True:
                        session_stats[key]['correct'] += 1
            
            progress_list = []
            for (sura, aya), counts in session_stats.items():
                if counts['total'] > 0:
                    accuracy = (counts['correct'] / counts['total']) * 100
                    # Retrieve page number for this ayah
                    page = self.get_page_for_sura_aya(sura, aya)
                    progress_list.append({
                        'sura': sura,
                        'ayah': aya,
                        'page': page,
                        'accuracy': accuracy
                    })
            
            if progress_list:
                # Pass session duration (converted to seconds)
                self.user_manager.record_session_progress(progress_list, duration_seconds=int(self.elapsed_recitation_time))
                print(f"DEBUG: Recorded progress for {len(progress_list)} ayahs.")

        # --- Finalize and Report ---
        try:
            # --- UPDATE: Confirmed Word System ---
            # We do NOT mark unrecited words (None) as Errors (False).
            # Only words explicitly skipped by the matcher during the session are Errors.
            # Re-render the page to show the final colors for all words.
            # Because recording_mode is now False, this will make all words
            # visible.
            self.page_renderer.render_page(self.current_page)

            # Display the final summary report dialog
            self.display_final_report()

        except Exception as e:
            print(f"Caught error during end_recitation_session cleanup: {e}")

        # --- Set UI to "Review Mode" ---
        # The results (highlights, recognized text) remain on screen.
        # The user can start a new session or interact with the app.
        self.btn_start.setText("▶ سمع")  # "Start New Recitation"
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if hasattr(self, 'btn_end_session'):
            self.btn_end_session.setEnabled(False)
        # The recognized text and copy buttons remain visible for review.

    def update_plan_progress(self, source_type):
        """
        Updates plan progress based on the completed activity.
        source_type: 'recitation' (for Memorization, Review, Repetition) or 'listening' (for Listening plans).
        """
        # 1. Determine the range of the completed activity
        if source_type == 'recitation':
            # Ensure session variables exist
            if not hasattr(self, 'session_from_sura_no'): return
            s_start = (self.session_from_sura_no, self.session_from_aya_no)
            s_end = (self.session_to_sura_no, self.session_to_aya_no)
        elif source_type == 'review':
            # Get range from Review Tab widgets
            if not self.combo_review_from_sura or not self.combo_review_to_sura: return
            s_start = (self.combo_review_from_sura.currentData(), self.spin_review_from_aya.value())
            s_end = (self.combo_review_to_sura.currentData(), self.spin_review_to_aya.value())
        elif source_type == 'listening':
            if not self.range_start_ref or not self.range_end_ref:
                return
            s_start = self.range_start_ref
            s_end = self.range_end_ref
        else:
            return

        # Convert to comparable values (Sura * 1000 + Aya)
        session_start_val = s_start[0] * 1000 + s_start[1]
        session_end_val = s_end[0] * 1000 + s_end[1]
        
        today_str = QDate.currentDate().toString(Qt.ISODate)
        updated = False
        
        for plan in self.plans:
            p_type = plan.get('type', 'memorization')
            
            # Match plan type to source activity
            if source_type == 'recitation':
                if p_type not in ['memorization', 'review', 'repetition']: continue
            elif source_type == 'review':
                if p_type not in ['memorization', 'review', 'repetition']: continue
            elif source_type == 'listening':
                if p_type != 'listening': continue
            
            # --- Handle Repetition Plans (Counter based) ---
            if p_type == 'repetition':
                # Check range coverage (User must cover the plan's range)
                p_start, p_end = self._get_plan_range_bounds(plan)
                if not p_start or not p_end: continue
                plan_start_val = p_start[0] * 1000 + p_start[1]
                plan_end_val = p_end[0] * 1000 + p_end[1]
                
                if session_start_val <= plan_start_val and session_end_val >= plan_end_val:
                    current = plan.get('current_repetitions', 0)
                    target = plan.get('target_repetitions', 30)
                    if current < target:
                        plan['current_repetitions'] = current + 1
                        self.show_toast(f"🎉 تقدم في تحدي '{plan['name']}': {current+1}/{target}")
                        updated = True
                        if plan['current_repetitions'] >= target:
                             self.check_auto_repeat(plan)

            # --- Handle Schedule Plans (Daily Task based) ---
            else:
                schedule = plan.get('schedule', {})
                task = schedule.get(today_str)
                
                if task and not task.get('completed', False) and not task.get('is_rest_day', False):
                    # Check task range
                    t_from_sura = task.get('from_sura')
                    t_from_aya = task.get('from_aya')
                    t_to_sura = task.get('to_sura')
                    t_to_aya = task.get('to_aya')
                    
                    if t_from_sura and t_to_sura:
                        task_start_val = t_from_sura * 1000 + t_from_aya
                        task_end_val = t_to_sura * 1000 + t_to_aya
                        
                        # Check if session covers the task (Session >= Task)
                        if session_start_val <= task_start_val and session_end_val >= task_end_val:
                            task['completed'] = True
                            self.show_toast(f"✅ تم إنجاز ورد اليوم لـ '{plan['name']}'")
                            updated = True
                            self.check_auto_repeat(plan)

        if updated:
            if self.user_manager.current_user:
                self.user_manager.save_plans(self.user_manager.current_user, self.plans)
            self.refresh_plans_ui()

    def _get_plan_range_bounds(self, plan):
        """Helper to calculate the start and end (sura, aya) of a plan based on its segments."""
        segments = plan.get('segments', [])
        if not segments: return None, None
        
        # Get pages from segments
        pages = self._get_pages_from_segments(segments)
        if not pages: return None, None
        
        start_page = min(pages)
        end_page = max(pages)
        
        # Get first aya of start page and last aya of end page
        first_aya = self.data_manager.get_page_start_aya(start_page)
        last_aya = self.data_manager.get_page_end_aya(end_page)
        
        return first_aya, last_aya

    def start_recording(self):
        """
        Initializes and starts the audio recording and speech recognition process.
        Handles both starting a new recitation and resuming a paused one.
        """
        if self.recording:
            return

        self.wake_lock.enable() # Prevent sleep during recording
        # --- NEW: إيقاف أي صوت يعمل (أذان أو تلاوة) عند بدء التسجيل لمنع التداخل ---
        if self.media_player and self.media_player.is_playing():
            self.player_stop()
            self.media_player.stop()

        # --- Session Initialization (only for a new session) ---
        if not self.recording_mode:
            print("DIAGNOSTIC: Starting a NEW recording session. Resetting state and UI.")
            
            # --- NEW: If Auto Reveal is running, stop it completely ---
            if getattr(self, 'is_auto_reveal_mode', False):
                self.stop_auto_reveal()

            # --- RESET UI AND STATE from previous session ---
            if hasattr(self, 'recognized_text_widget'):
                self.recognized_text_widget.hide()
                self.recognized_text_widget.clear()
            if hasattr(self, 'copy_buttons_container'):
                self.copy_buttons_container.hide()
            if hasattr(self, 'btn_rec_next'):
                self.btn_rec_next.hide()
            if hasattr(self, 'btn_rec_prev'):
                self.btn_rec_prev.hide()
            self.repetition_status_label.setText("")
            self.btn_start.setText("▶ سمع")  # Reset button text

            # Reset recitation duration for new session
            self.elapsed_recitation_time = 0
            if hasattr(self, 'recitation_duration_label'):
                self.recitation_duration_label.setText("00:00:00")

            # Hide recitation range widget
            if hasattr(self, 'recitation_range_widget'):
                self.recitation_range_widget.hide()

            # Clear old highlights by re-rendering in non-recording mode
            self.page_renderer.render_page(self.current_page)
            # --- End of Reset Logic ---

            self.recording_mode = True  # Enter recitation mode for the new session
            self.current_repetition = 1

            # --- CAPTURE SESSION RANGE ---
            self.session_from_sura_no = self.combo_from_sura.currentData()
            self.session_from_aya_no = self.spin_from_aya.value()
            self.session_to_sura_no = self.combo_to_sura.currentData()
            self.session_to_aya_no = self.spin_to_aya.value()
            self.session_from_sura_name = self.combo_from_sura.currentText()
            self.session_to_sura_name = self.combo_to_sura.currentText()

            print(
                f"DEBUG_START_REC: Stored Session Range - from {self.session_from_sura_name} ({self.session_from_sura_no}):{self.session_from_aya_no} to {self.session_to_sura_name} ({self.session_to_sura_no}):{self.session_to_aya_no}")

            self.recitation_range_words, self._word_page_map = self.data_manager.build_recitation_range(
                self.session_from_sura_no, self.session_from_aya_no, self.session_to_sura_no, self.session_to_aya_no
            )

            # --- NEW: Apply strict normalization to expected words ---
            # We replace the comparison string (index 1) with our strictly normalized version
            self.recitation_range_words = [
                (item[0], normalize_word(item[0])) + item[2:] 
                for item in self.recitation_range_words
            ]

            if not self.recitation_range_words:
                QMessageBox.warning(
    self, "نطاق فارغ", "نطاق التسميع المحدد لا يحتوي على كلمات.")
                self.recording_mode = False
                return

            # Reset all state variables for the new session
            self.word_pos = 0
            self.page_completed_waiting_for_stop = False
            self.last_partial_word_count = 0
            self._word_statuses = [None] * len(self.recitation_range_words)
            self._word_timings = [
                None] * len(self.recitation_range_words)  # For timing data
            self.history_text = ""
            self.current_partial_text = ""
            self.rendered_sura_headers.clear()

            # NEW: Clear recited pages for new session
            self.recited_pages.clear()
            self.session_debug_log = []     # Clear debug log

            # --- NEW: Review Mode Setup (Hide Words) ---
            if self.is_review_mode:
                print("DEBUG: Starting Review Mode - Hiding text.")
                for i in range(len(self._word_page_map)):
                    page_info = self._word_page_map[i]
                    global_idx = f"{page_info[1]}:{page_info[2]}:{page_info[3]}"
                    # Set text color to transparent to hide it
                    self.page_renderer.update_word_text_color(global_idx, QColor(0, 0, 0, 0))
                # Force render to apply hiding immediately
                self.page_renderer.render_page(self.current_page)

            # Build the map from global word ID to recitation index for
            # click-to-correct
            self.recitation_idx_map = {}
            for i in range(len(self._word_page_map)):
                page, sura, aya, word_id = self._word_page_map[i]
                global_id = f"{sura}:{aya}:{word_id}"
                self.recitation_idx_map[global_id] = i
        else:
            print("DIAGNOSTIC: Resuming a PAUSED recording session.")

        # --- Force Disable Playback Review Mode during Recitation ---
        # This ensures the playlist's "Hide Text" setting doesn't interfere with recitation
        self.playback_review_mode = False

        # --- Start/Resume Audio Processing ---
        self.recording = True
        self.recitation_repetitions = self.spin_repetitions.value()

        # Update UI for active recording
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        if hasattr(self, 'btn_end_session'):
            self.btn_end_session.setEnabled(True)

        # Start pulsing the appropriate button based on mode
        if self.is_review_mode:
            self.pulse_review.start()
        else:
            self.pulse_recitation.start()

        self.progress("🎤 جاري التسميع... تحدث الآن")
        self.repetition_status_label.setText(
            f"التكرار: {self.current_repetition}/{self.recitation_repetitions}")
        # NEW: Set the permanent toast message for the session
        self.show_toast(f"التكرار: {self.current_repetition}/{self.recitation_repetitions}")

        # Start the recitation duration timer
        if not self.recitation_duration_timer.isActive():
            self.recitation_duration_timer.start()

        if hasattr(self, 'recognized_text_widget'):
            self.recognized_text_widget.show()
            self.copy_buttons_container.show()
        if hasattr(self, 'btn_rec_next'):
            self.btn_rec_next.show()
            self.btn_rec_prev.show()

        # Navigate to the correct starting/resuming page
        start_page = self._get_page_for_word_index(self.word_pos)
        if start_page is None:
            start_page = self.data_manager.sura_pages.get(
                self.combo_from_sura.currentData(), 1)

        self.on_page_changed(start_page, from_start_recording=True)

        # In Lite version, we just show a message that this feature is not available
        QMessageBox.warning(
            self,
            "ميزة غير متاحة", "ميزة التسميع الصوتي غير متاحة في هذه النسخة (Lite).\nيرجى استخدام نسخة Pro للحصول على التسميع بالذكاء الاصطناعي.")
        self.stop_recording()

    # --- NEW: Auto Reveal Logic (Property 3) - Fixed Range & Repetition ---
    def on_auto_reveal_time_changed(self, value):
        """Updates the auto reveal time setting."""
        self.settings["auto_reveal_time"] = value
        save_settings(self.settings)

    def toggle_auto_reveal(self):
        """Toggles the standalone Auto Reveal mode between Start, Pause, and Resume."""
        # If a session is not active at all, start a new one.
        if getattr(self, 'is_auto_reveal_mode', False):
            # If a session is active...
            if self.auto_reveal_timer.isActive():
                # ...and it's currently running, pause it.
                self.auto_reveal_timer.stop()
                self.pulse_auto_reveal.stop()
                
                # --- NEW: Pause Session Timer ---
                if self.recitation_duration_timer.isActive():
                    self.recitation_duration_timer.stop()
                
                self.btn_auto_reveal_start.setText(self.tr("resume_display"))
                self.progress(self.tr("auto_reveal_paused"))
            else:
                # ...and it's currently paused, resume it.
                self.auto_reveal_timer.start(self.auto_reveal_interval)
                self.pulse_auto_reveal.start()
                
                # --- NEW: Resume Session Timer ---
                if not self.recitation_duration_timer.isActive():
                    self.recitation_duration_timer.start()
                
                self.btn_auto_reveal_start.setText(self.tr("pause"))
                self.progress(self.tr("auto_reveal_resume", self.auto_reveal_current_rep, self.auto_reveal_total_reps))
        else:
            self.start_auto_reveal()

    def start_auto_reveal(self):
        """Starts the Auto Reveal session based on selected range and repetitions."""
        if self.recording:
             QMessageBox.warning(self, "تنبيه", "الرجاء إيقاف التسميع الصوتي أولاً.")
             return
        
        time_val = self.spin_auto_reveal_time.value()
        if time_val <= 0:
             QMessageBox.warning(self, "تنبيه", "الرجاء تحديد زمن العرض (أكبر من 0).")
             return

        # 1. Build Range from UI
        from_sura = self.combo_review_from_sura.currentData()
        from_aya = self.spin_review_from_aya.value()
        to_sura = self.combo_review_to_sura.currentData()
        to_aya = self.spin_review_to_aya.value()

        # Get words for the specific range
        _, self.auto_reveal_map = self.data_manager.build_recitation_range(
            from_sura, from_aya, to_sura, to_aya
        )
        
        if not self.auto_reveal_map:
             QMessageBox.warning(self, "تنبيه", "النطاق المحدد لا يحتوي على كلمات.")
             return

        # 2. Setup State
        self.is_auto_reveal_mode = True
        self.auto_reveal_is_paused = False
        self.auto_reveal_index = 0
        self.auto_reveal_current_rep = 1
        self.auto_reveal_total_reps = self.spin_review_repetitions.value() # FIX: Use Review Repetitions
        
        # --- NEW: Reset and Start Session Timer ---
        self.elapsed_recitation_time = 0
        if hasattr(self, 'recitation_duration_label'):
            self.recitation_duration_label.setText("00:00:00")
        if not self.recitation_duration_timer.isActive():
            self.recitation_duration_timer.start()
        
        # 3. Calculate Interval (Time per page logic converted to per word)
        # FIX: Input is in seconds, convert to ms (multiply by 1000)
        total_ms_per_page = time_val * 1000
        avg_words_per_page = 130 # Approximate
        self.auto_reveal_interval = int(total_ms_per_page / avg_words_per_page)
        if self.auto_reveal_interval < 50: self.auto_reveal_interval = 50 # Minimum speed cap
        
        # 4. UI Updates
        self.btn_auto_reveal_start.setText(self.tr("pause"))
        self.btn_auto_reveal_stop.setEnabled(True)
        self.pulse_auto_reveal.start()
        
        # 5. Start
        start_page = self.auto_reveal_map[0][0]
        self.on_page_changed(start_page) # This will trigger _apply_auto_reveal_mask
        
        # FIX: Force apply mask in case on_page_changed returned early (same page)
        self._apply_auto_reveal_mask()
        
        self.auto_reveal_timer.start(self.auto_reveal_interval)
        self.progress(self.tr("auto_reveal_start", self.auto_reveal_current_rep, self.auto_reveal_total_reps))

    def stop_auto_reveal(self, finished=False):
        """Stops the Auto Reveal session completely and resets the UI."""
        self.is_auto_reveal_mode = False
        self.auto_reveal_is_paused = False
        self.auto_reveal_timer.stop()
        
        # --- NEW: Stop Session Timer ---
        if self.recitation_duration_timer.isActive():
            self.recitation_duration_timer.stop()
        
        # Reset UI
        if hasattr(self, 'btn_auto_reveal_start'):
            self.btn_auto_reveal_start.setText(self.tr("start_display"))
            self.pulse_auto_reveal.stop()
            self.btn_auto_reveal_stop.setEnabled(False)
        
        # Show text (Reveal all)
        self.page_renderer.render_page(self.current_page)
        self.progress(self.tr("auto_reveal_stopped"))
        
        # --- NEW: Update Plan Progress if finished successfully ---
        if finished:
            self.update_plan_progress('review')
            self.show_toast(self.tr("auto_reveal_finished"))

    def _resume_auto_reveal(self):
        """Resumes the auto reveal timer after a pause (e.g., end of ayah)."""
        if getattr(self, 'is_auto_reveal_mode', False) and not getattr(self, 'auto_reveal_is_paused', False):
            self.auto_reveal_timer.start(self.auto_reveal_interval)

    def _on_auto_reveal_tick(self):
        """Timer tick for Auto Reveal mode."""
        if not getattr(self, 'is_auto_reveal_mode', False):
            self.auto_reveal_timer.stop()
            return

        # Check if finished current range
        if self.auto_reveal_index >= len(self.auto_reveal_map):
            # Check repetitions
            if self.auto_reveal_current_rep < self.auto_reveal_total_reps:
                self.auto_reveal_current_rep += 1
                self.auto_reveal_index = 0
                # Restart from beginning
                start_page = self.auto_reveal_map[0][0]
                if self.current_page != start_page:
                    self.on_page_changed(start_page)
                else:
                    self._apply_auto_reveal_mask() # Re-hide everything on current page
                
                self.progress(self.tr("auto_reveal_start", self.auto_reveal_current_rep, self.auto_reveal_total_reps))
                # --- NEW: Show on-screen toast for repetition ---
                self.show_toast(f"التكرار {self.auto_reveal_current_rep}/{self.auto_reveal_total_reps}")
                return
            else:
                self.stop_auto_reveal(finished=True)
                return

        # Reveal current word
        page_info = self.auto_reveal_map[self.auto_reveal_index]
        
        # Check page transition
        if page_info[0] != self.current_page:
             # Handle two-page view logic
             is_visible = False
             if self.view_mode == "two_pages":
                 if self.current_page % 2 != 0: # Odd page (Right)
                     if page_info[0] == self.current_page + 1: is_visible = True
                 elif self.current_page % 2 == 0: # Even page (Left)
                     if page_info[0] == self.current_page - 1: is_visible = True
             
             if not is_visible:
                 self.on_page_changed(page_info[0])
                 return # Wait for next tick/render

        # Ensure word_id is valid before constructing key
        if page_info[3] is not None:
            global_idx = f"{page_info[1]}:{page_info[2]}:{page_info[3]}"
            try:
                self.page_renderer.update_word_text_color(global_idx, self.quran_text_color)
            except Exception as e:
                print(f"Error revealing word {global_idx}: {e}")
        
        self.view.viewport().repaint() # Force repaint to show word immediately
        self.auto_reveal_index += 1
        
        # --- NEW: Pause at end of Ayah (Breath Pause) ---
        if self.auto_reveal_index < len(self.auto_reveal_map):
            current_info = self.auto_reveal_map[self.auto_reveal_index - 1]
            next_info = self.auto_reveal_map[self.auto_reveal_index]
            
            # Check if Ayah changed (index 2 is Ayah number)
            if current_info[2] != next_info[2]:
                self.auto_reveal_timer.stop()
                
                pause_ms = 1500 # Default
                if hasattr(self, 'spin_auto_reveal_pause') and self.spin_auto_reveal_pause:
                    pause_ms = int(self.spin_auto_reveal_pause.value() * 1000)
                
                QTimer.singleShot(pause_ms, self._resume_auto_reveal)

    def _apply_auto_reveal_mask(self):
        """Hides words that haven't been revealed yet (called on page change)."""
        if not hasattr(self, 'auto_reveal_map'): return
        
        # Iterate over words in the map
        for i, info in enumerate(self.auto_reveal_map):
            # Only affect words on currently visible page(s)
            if info[0] == self.current_page or (self.view_mode == "two_pages" and info[0] == self.current_page + 1):
                if info[3] is None: continue
                
                global_idx = f"{info[1]}:{info[2]}:{info[3]}"
                if i < self.auto_reveal_index:
                    # Revealed (Normal Color)
                    self.page_renderer.update_word_text_color(global_idx, self.quran_text_color)
                else:
                    # Hidden (Transparent)
                    self.page_renderer.update_word_text_color(global_idx, QColor(0, 0, 0, 0))
        
        self.view.viewport().repaint()

    # --- NEW: Unified Toast System (Permanent & Temporary) ---
    def _display_toast_text(self, message):
        """Internal helper to set text, size, and position of the toast."""
        self.toast_label.setText(message)
        self.toast_label.adjustSize()

        if not getattr(self.toast_label, 'user_has_moved', False):
            margin = 20
            self.toast_label.move(margin, margin)
        
        self.toast_label.show()

    def _restore_permanent_toast(self):
        """Called by a timer to restore the permanent message or hide the toast if none exists."""
        if self.permanent_toast_message:
            self._display_toast_text(self.permanent_toast_message)
        else:
            self.toast_label.hide()

    def show_toast(self, message, temporary=False):
        """
        Displays a message overlay.
        - If temporary=False, it sets this as the new permanent message.
        - If temporary=True, it shows the message for a few seconds, then restores the permanent one.
        """
        if not temporary:
            self.permanent_toast_message = message
        
        self._display_toast_text(message)

        if temporary:
            # After 3 seconds, restore the permanent message or hide
            QTimer.singleShot(3000, self._restore_permanent_toast)

    def progress(self, message: str):
        """Updates the repetition status label to show a progress message."""
        if hasattr(self, 'repetition_status_label'):
            self.repetition_status_label.setText(message)

    def _play_error_sound(self):
        """Plays an error sound."""
        play_error_sound()

    def _show_copyable_message(self, icon, title, text, detailed_text=""):
        """Displays a QMessageBox with selectable text."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        if detailed_text:
            # Set the informative text to be a brief summary, and detailed for the full error
            msg_box.setInformativeText("انقر على 'Show Details' لرؤية تفاصيل الخطأ الكاملة.")
            msg_box.setDetailedText(str(detailed_text))
        # This is the crucial part that makes the text copyable
        msg_box.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        msg_box.exec_()

    def _copy_recognized_text(self):
        """Copies the content of the recognized text widget to the clipboard."""
        if self.recognized_text_widget:
            QApplication.clipboard().setText(self.recognized_text_widget.toPlainText())
            button = self.btn_copy_recognized_text
            if button is not None:
                button: QPushButton  # type: ignore
                original_text = button.text()  # Store original text
                button.setText("✓")  # Set to checkmark
                # Use a lambda to capture the button and original_text.
                # Add a check inside the lambda to ensure the button still
                # exists.
                QTimer.singleShot(2000, lambda: button.setText(
                    original_text) if button else None)

    def _copy_recitation_report(self):
        """Generates and copies a detailed report of the last recitation session."""
        if self.btn_copy_report:
            self.btn_copy_report.setEnabled(False)
            self.btn_copy_report.setText("جاري الإنشاء...")

            if not self.recitation_range_words:
                self.btn_copy_report.setText("لا يوجد تقرير")

                def reset_button():
                    if self.btn_copy_report:
                        self.btn_copy_report.setText("📋 نسخ تقرير التسميع")
                        self.btn_copy_report.setEnabled(True)
                QTimer.singleShot(2000, reset_button)
                return

            # 1. Gather all required data using the stored session variables.
            # --- OPTIMIZATION: Slice data up to current word_pos only ---
            # This prevents processing the entire Quran if the range is large.
            limit_index = self.word_pos
            report_data = {
                "from_sura": self.session_from_sura_name,
                "from_aya": self.session_from_aya_no,
                "to_sura": self.session_to_sura_name,
                "to_aya": self.session_to_aya_no,
                "words": self.recitation_range_words[:limit_index],
                "statuses": self._word_statuses[:limit_index],
                "timings": self._word_timings[:limit_index],
                "recited_pages": self.recited_pages.copy(),
                "word_page_map": self._word_page_map[:limit_index],
                "debug_log": self.session_debug_log[:],
                "session_start_index": self.session_start_index, # NEW
                "session_duration": self.elapsed_recitation_time  # Pass session duration
            }

            # 2. Run the report generation in a background thread to avoid
            # freezing the GUI
            threading.Thread(
    target=self._generate_report_background, args=(
        report_data,), daemon=True).start()

    def _generate_report_background(self, data):
        """The actual report generation logic that runs in the background.
        This function MUST NOT access any GUI elements directly."""
        try:
            report_lines = []
            report_lines.append("--- تقرير جلسة التسميع ---")

            # NEW: Get recited pages and word-to-page map
            recited_pages = data.get("recited_pages", set())
            word_page_map = data.get("word_page_map", [])

            # If no pages were recited, show a message and exit.
            if not recited_pages:
                report_lines.append("لم يتم تلاوة أي صفحات في هذه الجلسة.")
                final_report = "\n".join(report_lines)
                self.report_ready.emit(final_report)
                return

            # Determine the actual range that was recited for the report header
            min_recited_page = min(recited_pages) if recited_pages else 0
            max_recited_page = max(recited_pages) if recited_pages else 0
            report_lines.append(
                f"النطاق الفعلي للتلاوة: الصفحات من {min_recited_page} إلى {max_recited_page}")

            # --- Add Session Duration ---
            session_duration_sec = data.get("session_duration", 0)
            m, s = divmod(session_duration_sec, 60)
            h, m = divmod(m, 60)
            report_lines.append(f"⏱️ مدة الجلسة: {h:02d}:{m:02d}:{s:02d}")

            total_words_in_report = 0
            correct_count = 0
            errors = []
            unrecited_indices_in_report = []

            word_statuses = data.get("statuses", [])
            word_timings = data.get("timings", [])

            start_idx = data.get("session_start_index", 0)
            for i, (original_word, _) in enumerate(data['words']):
                # Get the page for the current word
                # If word_page_map is incomplete, handle it gracefully
                if i >= len(word_page_map):
                    continue
                word_page = word_page_map[i][0]

                # --- CORE CHANGE: Only include words from recited pages in the report ---
                if word_page not in recited_pages:
                    continue
                
                # --- NEW: Skip words before the actual start (e.g. jumped over) ---
                if i < start_idx:
                    continue
                
                # This word is on a recited page, so it's part of our report
                total_words_in_report += 1

                timing_info_str = ""
                if i < len(word_timings) and word_timings[i]:
                    start_time, end_time = word_timings[i]
                    # FIX: Check for None before formatting to avoid crash
                    if start_time is not None and end_time is not None:
                        timing_info_str = f" (من {start_time:.2f} إلى {end_time:.2f} ثانية)"
                    else:
                        timing_info_str = ""

                if i < len(word_statuses):
                    status = word_statuses[i]
                    if status is True:
                        correct_count += 1
                    elif status is False:
                        errors.append(
                            f"❌ الكلمة: '{original_word}' (الترتيب: {i+1}){timing_info_str}")
                    else: # status is None, means unrecited within the recited pages
                        unrecited_indices_in_report.append(i)
                else:
                    unrecited_indices_in_report.append(i)
            
            error_count = len(errors)
            unrecited_count = len(unrecited_indices_in_report)

            report_lines.append("-" * 20)
            report_lines.append(
                f"📖 إجمالي الكلمات في الصفحات التي تمت تلاوتها: {total_words_in_report}")
            report_lines.append(f"✅ الكلمات الصحيحة: {correct_count}")
            report_lines.append(f"❌ الأخطاء: {error_count}")
            report_lines.append(
                f"⏭️ الكلمات المتروكة (من الصفحات المتلوة): {unrecited_count}")
            
            accuracy = (
                correct_count / total_words_in_report * 100
            ) if total_words_in_report > 0 else 0
            
            report_lines.append(f"🎯 الدقة: {accuracy:.1f}%")
            report_lines.append("-" * 20)
            
            # The original full range is still useful context.
            report_lines.append(
                f"النطاق المحدد أصلاً: من [{data['from_sura']} - آية {data['from_aya']}] إلى [{data['to_sura']} - آية {data['to_aya']}]")


            if errors or unrecited_count > 0:
                report_lines.append("تفاصيل الأخطاء والكلمات المتروكة:")
                report_lines.extend(errors)
                if unrecited_count > 0:
                    unrecited_words = [
                        f"⏭️ الكلمة: '{data['words'][i][0]}' (الترتيب: {i+1}) - لم تُقرأ" for i in unrecited_indices_in_report
                    ]
                    report_lines.extend(unrecited_words)
            elif correct_count > 0:
                report_lines.append("🎉 ممتاز! لم يتم تسجيل أي أخطاء في الجزء المتلو.")
            else:
                # This case handles when pages were visited but no words were recited
                report_lines.append("لم يتم تسجيل أي كلمات في الجزء المتلو.")

            # --- إضافة سجل التحليل الدقيق (Debug Log) ---
            debug_log = data.get("debug_log", [])
            if debug_log:
                report_lines.append("\n" + "="*40)
                report_lines.append("🔍 سجل التحليل الدقيق (Debug Trace)")
                report_lines.append("="*40)
                
                for entry in debug_log:
                    t_str = time.strftime("%H:%M:%S", time.localtime(entry.get('time', 0)))
                    event = entry.get('event')
                    
                    if event == "PARTIAL":
                        report_lines.append(f"[{t_str}] 🔸 Vosk Partial: {entry.get('text')}")
                    elif event == "FINAL":
                        report_lines.append(f"[{t_str}] 🟢 Vosk Final:   {entry.get('text')}")
                    elif event == "PROCESSED":
                        status_icon = "✅" if entry.get('status') == "ACCEPTED" else "❌"
                        report_lines.append(f"   ⚙️ Word Analysis:")
                        report_lines.append(f"      • Raw Input:      '{entry.get('raw')}'")
                        report_lines.append(f"      • Normalized:     '{entry.get('norm')}'")
                        report_lines.append(f"      • Match Status:   {status_icon} {entry.get('status')} ({entry.get('match_type')})")
                        if entry.get('status') == "ACCEPTED":
                            report_lines.append(f"      • Quran Target:   '{entry.get('target')}'")
                        report_lines.append("-" * 20)

            final_report = "\n".join(report_lines)
            # 3. Emit the signal with the report text. This is thread-safe.
            self.report_ready.emit(final_report)
        except Exception as e:
            print(f"Error generating report in background: {e}")

    def _finish_report_copy(self, report_text: str):
        """Receives the generated report from the background thread, copies it to the clipboard, and updates the button state."""
        try:
            button = self.btn_copy_report
            if button is not None:
                button: QPushButton  # type: ignore
                QApplication.clipboard().setText(report_text)
                button.setText("✓ تم النسخ")
                button.setEnabled(True)
                # Use a lambda to capture the button, making it safer
                QTimer.singleShot(3000, lambda: button.setText(
                    "📋 نسخ تقرير التسميع") if button else None)
        except Exception as e:
            print(f"Error finishing report copy: {e}")

    @pyqtSlot(str)
    def _show_report_in_dialog(self, report_text: str):
        """Creates and shows a dialog with the final report."""
        if not self.isVisible():  # Don't show if window is closing
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("تقرير التسميع")
        dialog.setLayoutDirection(Qt.RightToLeft)
        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setText(report_text)
        # Ensure the text within the QTextEdit is also aligned to the right
        text_edit.setAlignment(Qt.AlignRight)

        close_button = QPushButton("إغلاق")
        close_button.clicked.connect(dialog.accept)

        layout.addWidget(text_edit)
        layout.addWidget(close_button)

        dialog.setLayout(layout)
        dialog.resize(450, 500)
        dialog.exec_()

    def display_final_report(self):
        """Gathers data using the stored session range and starts the background thread to generate the report for display."""
        if not self.recitation_range_words:
            return

        # Use the stored session variables, not the live UI state, to prevent
        # mismatch
        # --- OPTIMIZATION: Slice data up to current word_pos only ---
        limit_index = self.word_pos
        report_data = {
            "from_sura": self.session_from_sura_name,
            "from_aya": self.session_from_aya_no,
            "to_sura": self.session_to_sura_name,
            "to_aya": self.session_to_aya_no,
            "words": self.recitation_range_words[:limit_index],
            "statuses": self._word_statuses[:limit_index],
            "timings": self._word_timings[:limit_index],
            "recited_pages": self.recited_pages.copy(),
            "word_page_map": self._word_page_map[:limit_index],
            "debug_log": self.session_debug_log[:],
            "session_start_index": self.session_start_index, # NEW
            "session_duration": self.elapsed_recitation_time  # Pass session duration
        }
        # Using a new background method to emit the new signal
        threading.Thread(
            target=self._generate_report_for_display_background, args=(
                report_data,), daemon=True).start()

    def _generate_report_for_display_background(self, data):
        """Generates the detailed report text and emits the display_report_ready signal."""
        try:
            report_lines = []
            report_lines.append("--- تقرير جلسة التسميع ---")

            # NEW: Get recited pages and word-to-page map
            recited_pages = data.get("recited_pages", set())
            word_page_map = data.get("word_page_map", [])

            # If no pages were recited, show a message and exit.
            if not recited_pages:
                report_lines.append("لم يتم تلاوة أي صفحات في هذه الجلسة.")
                final_report = "\n".join(report_lines)
                self.display_report_ready.emit(final_report)
                return

            # Determine the actual range that was recited for the report header
            min_recited_page = min(recited_pages) if recited_pages else 0
            max_recited_page = max(recited_pages) if recited_pages else 0
            report_lines.append(
                f"النطاق الفعلي للتلاوة: الصفحات من {min_recited_page} إلى {max_recited_page}")

            # --- Add Session Duration ---
            session_duration_sec = data.get("session_duration", 0)
            m, s = divmod(session_duration_sec, 60)
            h, m = divmod(m, 60)
            report_lines.append(f"⏱️ مدة الجلسة: {h:02d}:{m:02d}:{s:02d}")

            total_words_in_report = 0
            correct_count = 0
            errors = []
            unrecited_indices_in_report = []

            word_statuses = data.get("statuses", [])
            word_timings = data.get("timings", [])

            start_idx = data.get("session_start_index", 0)
            for i, (original_word, _) in enumerate(data['words']):
                # Get the page for the current word
                # If word_page_map is incomplete, handle it gracefully
                if i >= len(word_page_map):
                    continue
                word_page = word_page_map[i][0]

                # --- CORE CHANGE: Only include words from recited pages in the report ---
                if word_page not in recited_pages:
                    continue
                
                # --- NEW: Skip words before the actual start (e.g. jumped over) ---
                if i < start_idx:
                    continue
                
                # This word is on a recited page, so it's part of our report
                total_words_in_report += 1

                timing_info_str = ""
                if i < len(word_timings) and word_timings[i]:
                    start_time, end_time = word_timings[i]
                    # FIX: Check for None before formatting to avoid crash
                    if start_time is not None and end_time is not None:
                        timing_info_str = f" (من {start_time:.2f} إلى {end_time:.2f} ثانية)"
                    else:
                        timing_info_str = ""

                if i < len(word_statuses):
                    status = word_statuses[i]
                    if status is True:
                        correct_count += 1
                    elif status is False:
                        errors.append(
                            f"❌ خطأ/تجاوز: '{original_word}' (الترتيب: {i+1}){timing_info_str}")
                    else: # status is None, means unrecited within the recited pages
                        unrecited_indices_in_report.append(i)
                else:
                    unrecited_indices_in_report.append(i)
            
            error_count = len(errors)
            unrecited_count = len(unrecited_indices_in_report)

            # --- NEW ACCURACY CALCULATION (Based on Attempted Words) ---
            attempted_count = correct_count + error_count
            accuracy = (
                correct_count / attempted_count * 100
            ) if attempted_count > 0 else 0

            report_lines.append("-" * 20)
            report_lines.append(
                f"📖 إجمالي الكلمات في الصفحات التي تمت تلاوتها: {total_words_in_report}")
            report_lines.append(f"✅ الكلمات الصحيحة: {correct_count}")
            report_lines.append(f"❌ الأخطاء (الكلمات المتجاوزة): {error_count}")
            report_lines.append(
                f"⏭️ الكلمات المتبقية (لم يتم الوصول إليها): {unrecited_count}")
            
            report_lines.append(f"🎯 دقة التلاوة (للمقروء فقط): {accuracy:.1f}%")
            report_lines.append("-" * 20)
            
            # The original full range is still useful context.
            report_lines.append(
                f"النطاق المحدد أصلاً: من [{data['from_sura']} - آية {data['from_aya']}] إلى [{data['to_sura']} - آية {data['to_aya']}]")


            if errors or unrecited_count > 0:
                report_lines.append("تفاصيل الأخطاء والكلمات المتروكة:")
                report_lines.extend(errors)
                if unrecited_count > 0:
                    unrecited_words = [
                        f"⏭️ متبقي: '{data['words'][i][0]}' (الترتيب: {i+1})" for i in unrecited_indices_in_report
                    ]
                    report_lines.extend(unrecited_words)
            elif correct_count > 0:
                report_lines.append("🎉 ممتاز! لم يتم تسجيل أي أخطاء في الجزء المتلو.")
            else:
                # This case handles when pages were visited but no words were recited
                report_lines.append("لم يتم تسجيل أي كلمات في الجزء المتلو.")

            # --- إضافة سجل التحليل الدقيق (Debug Log) ---
            debug_log = data.get("debug_log", [])
            if debug_log:
                report_lines.append("\n" + "="*40)
                report_lines.append("🔍 سجل التحليل الدقيق (Debug Trace)")
                report_lines.append("="*40)
                
                for entry in debug_log:
                    t_str = time.strftime("%H:%M:%S", time.localtime(entry.get('time', 0)))
                    event = entry.get('event')
                    
                    if event == "PARTIAL":
                        report_lines.append(f"[{t_str}] 🔸 Vosk Partial: {entry.get('text')}")
                    elif event == "FINAL":
                        report_lines.append(f"[{t_str}] 🟢 Vosk Final:   {entry.get('text')}")
                    elif event == "PROCESSED":
                        status_icon = "✅" if entry.get('status') == "ACCEPTED" else "❌"
                        report_lines.append(f"   ⚙️ Word Analysis:")
                        report_lines.append(f"      • Raw Input:      '{entry.get('raw')}'")
                        report_lines.append(f"      • Normalized:     '{entry.get('norm')}'")
                        report_lines.append(f"      • Match Status:   {status_icon} {entry.get('status')} ({entry.get('match_type')})")
                        if entry.get('status') == "ACCEPTED":
                            report_lines.append(f"      • Quran Target:   '{entry.get('target')}'")
                        report_lines.append("-" * 20)

            final_report = "\n".join(report_lines)
            self.display_report_ready.emit(final_report)
        except Exception as e:
            print(f"Error generating display report in background: {e}")

    def _get_page_for_word_index(self, global_word_index):
        """Helper to get the page number for a global word index."""
        if 0 <= global_word_index < len(self._word_page_map):
            return self._word_page_map[global_word_index][0]
        return None

    def get_page_for_sura_aya(self, sura_no, ayah_no):
        """Helper to get the page number for a sura and ayah using the pre-built map."""
        return self.sura_aya_to_page_map.get((sura_no, ayah_no))

        # --- Playlist Methods ---

    def load_playlist_settings(self):
            """Loads playlist-specific settings from the general settings file."""

            try:

                # The main settings are already loaded into self.settings in
                # __init__

                if self.settings:

                    # Restore repetition values

                    self.spin_single_repeat.setValue(
                        self.settings.get("single_repeat", 3))

                    self.spin_group_repeat.setValue(
                        self.settings.get("group_repeat", 3))

                    self.spin_complex_individual.setValue(
                        self.settings.get("complex_individual", 3))

                    self.spin_complex_group.setValue(
                        self.settings.get("complex_group", 3))

                    self.spin_complex_group_size.setValue(
                        self.settings.get("complex_group_size", 3))

                    # Restore folder and reciter
                    main_folder = self.settings.get("main_audio_folder")

                    if main_folder and os.path.isdir(main_folder):
                        self.main_audio_folder = main_folder
                        self.btn_select_main_folder.setText(
                            os.path.basename(main_folder))
                        subfolders = [
                            f.name for f in os.scandir(main_folder) if f.is_dir()]
                        if subfolders:
                            self.combo_reciters.addItems(subfolders)
                            self.combo_reciters.setEnabled(True)
                            current_reciter = self.settings.get(
                                "current_reciter")
                            if current_reciter in subfolders:
                                self.combo_reciters.setCurrentText(
                                    current_reciter)
                            self.on_reciter_changed()
                    elif main_folder:
                        # If the path exists in settings but is invalid, just clear it silently.
                        # This prevents blocking the startup on a new machine.
                        self.main_audio_folder = ""
                        self.settings["main_audio_folder"] = ""
                        if self.btn_select_main_folder:
                            self.btn_select_main_folder.setText(
                                "اختر المجلد الرئيسي...")
                        if self.combo_reciters:
                            self.combo_reciters.clear()
                            self.combo_reciters.setEnabled(False)

                    # Restore start and end files

                    self.start_file = self.settings.get("start_file", "")

                    self.end_file = self.settings.get("end_file", "")

                    self.start_file_label.setText(self.start_file)

                    self.end_file_label.setText(self.end_file)

                    # If files were loaded, update the list

                    if self.start_file and self.end_file and self.output_folder:

                        self.update_files_list()

            except Exception as e:

                pass # print(f"Failed to load playlist settings: {e}")

    def save_playlist_settings(self):
            """Saves playlist-specific settings to the main settings object before app closes."""

            self.settings["main_audio_folder"] = self.main_audio_folder

            self.settings["current_reciter"] = self.combo_reciters.currentText()

            self.settings["start_file"] = self.start_file

            self.settings["end_file"] = self.end_file

            self.settings["single_repeat"] = self.spin_single_repeat.value()

            self.settings["group_repeat"] = self.spin_group_repeat.value()

            self.settings["complex_individual"] = self.spin_complex_individual.value()

            self.settings["complex_group"] = self.spin_complex_group.value()

            self.settings["complex_group_size"] = self.spin_complex_group_size.value()

    def select_main_audio_folder(self):

            folder = QFileDialog.getExistingDirectory(
    self, "اختر المجلد الرئيسي الذي يحتوي على القراء")

            if folder:

                self.main_audio_folder = folder

                self.btn_select_main_folder.setText(os.path.basename(folder))

                self.combo_reciters.clear()

                self.combo_reciters.setEnabled(False)

                self.range_group.setEnabled(False)

                self.options_group.setEnabled(False)

                try:

                    subfolders = [
    f.name for f in os.scandir(folder) if f.is_dir()]

                    if subfolders:

                        self.combo_reciters.addItems(subfolders)

                        self.combo_reciters.setEnabled(True)

                        self.on_reciter_changed()

                    else:

                        QMessageBox.warning(
    self, "مجلد فارغ", "المجلد المختار لا يحتوي على أي مجلدات فرعية (قراء).")

                except Exception as e:

                    QMessageBox.critical(
    self, "خطأ", f"لا يمكن قراءة المجلدات الفرعية: {e}")

    def on_reciter_changed(self):

            reciter_name = self.combo_reciters.currentText()

            if self.main_audio_folder and reciter_name:

                folder = os.path.join(self.main_audio_folder, reciter_name)

                self.output_folder = folder

                # --- NEW: Auto-detect reciter file system ---
                try:
                    all_files = [f for f in os.listdir(folder) if f.lower().endswith(('.mp3', '.wav'))]
                    if not all_files:
                        self.reciter_file_system = 'ayah_based' # Default
                        # print("DEBUG: No audio files found, defaulting to ayah_based.")
                    else:
                        # Check the format of the first few files to guess the system
                        sample_files = all_files[:10]
                        sura_based_count = 0
                        ayah_based_count = 0
                        page_based_count = 0 # NEW: Counter for page-based files
                        for f in sample_files:
                            basename = os.path.splitext(f)[0]
                            if basename.isdigit():
                                if len(basename) <= 3:
                                    # Ambiguity: could be sura or page. For now, we'll increment page_based_count
                                    # and let the final comparison decide.
                                    page_based_count += 1 
                                elif len(basename) == 6:
                                    ayah_based_count += 1
                        
                        if ayah_based_count > sura_based_count and ayah_based_count > page_based_count:
                            self.reciter_file_system = 'ayah_based'
                            # print("DEBUG: Detected ayah-based file system.")
                        elif page_based_count >= sura_based_count and page_based_count > ayah_based_count: # Prioritize page_based if 3-digit numbers are predominant or tied with sura_based
                            self.reciter_file_system = 'page_based'
                            # print("DEBUG: Detected page-based file system (3-digit numbers assumed to be pages).")
                        elif sura_based_count > ayah_based_count: # Fallback to sura_based if 3-digit numbers were less than ayah-based
                            self.reciter_file_system = 'sura_based'
                            # print("DEBUG: Detected sura-based file system (3-digit numbers assumed to be suras).")
                        else: # Default if no clear majority, or if sura/page are tied
                            self.reciter_file_system = 'page_based' # Default to page-based as requested by user for 3-digit
                            # print("DEBUG: No clear file system detected, defaulting to page-based (3-digit numbers assumed to be pages).")

                except Exception as e:
                    # print(f"Error detecting file system: {e}")
                    self.reciter_file_system = 'ayah_based' # Default on error
                # --- END NEW ---

                self.range_group.setEnabled(True)

                self.options_group.setEnabled(True)

    def select_start_file(self):

            file_path, _ = QFileDialog.getOpenFileName(
    self, "اختر ملف البداية", self.output_folder, "Audio Files (*.mp3 *.wav)")

            if file_path:

                self.start_file = os.path.basename(file_path)

                self.start_file_label.setText(self.start_file)

                try:

                    sura_no = int(self.start_file[0:3])

                    ayah_no = int(self.start_file[3:6])

                    target_page = self.get_page_for_sura_aya(
                        sura_no, ayah_no)

                    if target_page:

                        self.on_page_changed(target_page)

                except Exception as e:

                    pass # print(f"Failed to navigate to page from start file: {e}")

    def select_end_file(self):

            file_path, _ = QFileDialog.getOpenFileName(
    self, "اختر ملف النهاية", self.output_folder, "Audio Files (*.mp3 *.wav)")

            if file_path:

                self.end_file = os.path.basename(file_path)

                self.end_file_label.setText(self.end_file)

    def update_files_list(self):
        """
        Updates the list of files to be played based on self.start_file and self.end_file.
        """
        # print(f"DEBUG HIGHLIGHT: update_files_list called. start_file={self.start_file}, end_file={self.end_file}")
        try:
            start_file = self.start_file
            end_file = self.end_file

            if not start_file or not end_file:
                self._show_copyable_message(QMessageBox.Warning, "نطاق غير مكتمل", "الرجاء تحديد بداية ونهاية النطاق أولاً.")
                # print(f"DEBUG HIGHLIGHT: update_files_list: start_file or end_file is empty.")
                return

            # --- Main Logic ---
            self.files_list.clear()

            if not self.output_folder or not os.path.isdir(self.output_folder):
                self._show_copyable_message(QMessageBox.Critical, "خطأ في المجلد", "مجلد القارئ غير محدد أو غير موجود.")
                # print(f"DEBUG HIGHLIGHT: Output folder invalid: {self.output_folder}")
                return

            # Use natural sort for files to handle unpadded numbers correctly (1, 2, ..., 10)
            def natural_keys(text):
                return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

            all_files = sorted([f for f in os.listdir(self.output_folder) if f.lower().endswith(('.mp3', '.wav'))], key=natural_keys)
            if not all_files:
                self._show_copyable_message(QMessageBox.Critical, "مجلد فارغ", "مجلد القارئ المحدد لا يحتوي على أي ملفات صوتية.")
                # print(f"DEBUG HIGHLIGHT: No MP3 files found in {self.output_folder}")
                return

            try:
                start_index = all_files.index(start_file)
                end_index = all_files.index(end_file)
            except ValueError as e:
                self._show_copyable_message(QMessageBox.Critical, "خطأ في الملفات", "لم يتم العثور على ملف البداية أو النهاية في مجلد القارئ المحدد.", detailed_text=f"Searching for '{start_file}' and '{end_file}' in reciter folder.")
                # print(f"DEBUG HIGHLIGHT: Start or end file not found: {e}")
                return

            if start_index > end_index:
                self._show_copyable_message(QMessageBox.Warning, "خطأ في الترتيب", "ملف البداية يجب أن يكون قبل ملف النهاية.")
                # print("DEBUG HIGHLIGHT: Start file index is greater than end file index.")
                return

            self.files_list = all_files[start_index: end_index + 1]
            
            # --- Update Highlighting References & Navigate ---
            target_page = -1

            if self.reciter_file_system == 'ayah_based':
                try:
                    sura_no = int(start_file[0:3])
                    ayah_no = int(start_file[3:6])
                    end_sura_no = int(end_file[0:3])
                    end_ayah_no = int(end_file[3:6])
                    self.range_start_ref = (sura_no, ayah_no)
                    self.range_end_ref = (end_sura_no, end_ayah_no)
                    target_page = self.get_page_for_sura_aya(sura_no, ayah_no)
                    # print(f"DEBUG HIGHLIGHT: Range refs set: start_ref={self.range_start_ref}, end_ref={self.range_end_ref}. Target page={target_page}")


                except (ValueError, IndexError) as e:
                    self.range_start_ref = None
                    self.range_end_ref = None
                    # print(f"DEBUG HIGHLIGHT: Error setting range refs for ayah_based: {e}")
            elif self.reciter_file_system == 'sura_based':
                try:
                    start_page_num = int(os.path.splitext(start_file)[0])
                    end_page_num = int(os.path.splitext(end_file)[0])
                    target_page = start_page_num

                    if not (1 <= start_page_num <= 604 and 1 <= end_page_num <= 604):
                        raise ValueError("Page numbers out of valid range (1-604)")

                    # Find first ayah of start page
                    ayas_on_start_page = self.data_manager.pages_by_number.get(str(start_page_num), [])
                    if not ayas_on_start_page:
                        raise ValueError(f"No ayahs found for start page {start_page_num}")
                    
                    first_ayah = ayas_on_start_page[0]
                    start_sura_no = first_ayah['sura_no']
                    start_ayah_no = first_ayah['aya_no']

                    # Find last ayah of end page
                    ayas_on_end_page = self.data_manager.pages_by_number.get(str(end_page_num), [])
                    if not ayas_on_end_page:
                        raise ValueError(f"No ayahs found for end page {end_page_num}")

                    last_ayah = ayas_on_end_page[-1]
                    end_sura_no = last_ayah['sura_no']
                    end_ayah_no = last_ayah['aya_no']
                    
                    self.range_start_ref = (start_sura_no, start_ayah_no)
                    self.range_end_ref = (end_sura_no, end_ayah_no)
                    
                    # print(f"DEBUG HIGHLIGHT (PAGE): Range refs set: start_ref={self.range_start_ref}, end_ref={self.range_end_ref}. Target page={target_page}")


                except (ValueError, IndexError, KeyError) as e:
                    self.range_start_ref = None
                    self.range_end_ref = None
                    # print(f"DEBUG HIGHLIGHT (PAGE): Error setting range refs for page-based selection: {e}")
                    self._apply_range_highlight(None, None, QColor(0,0,0,0)) # Clear highlight on error
            elif self.reciter_file_system == 'page_based':
                try:
                    start_page = int(os.path.splitext(start_file)[0])
                    target_page = start_page
                    # print(f"DEBUG HIGHLIGHT (PAGE_BASED): Start page {start_page}")
                except ValueError:
                    target_page = -1
            else:
                 self.range_start_ref = None
                 self.range_end_ref = None
                 # print(f"DEBUG HIGHLIGHT: Unknown reciter file system. Clearing range refs.")
                 
            # Navigate to start of selection
            if target_page != -1:
                if self.current_page != target_page:
                    # print(f"DEBUG HIGHLIGHT: Navigating to target_page {target_page} from {self.current_page}.")
                    self.on_page_changed(target_page)
                else:
                    # Re-render to clear old highlights if any
                    # print(f"DEBUG HIGHLIGHT: Already on target_page {target_page}. Re-rendering to clear old highlights.")
                    self.page_renderer.render_page(self.current_page)
            else:
                # This case might be hit if parsing fails for some reason
                # print(f"DEBUG HIGHLIGHT: Could not determine a target page for navigation from start file '{start_file}'.")
                pass


            self.update_session_estimate('SINGLE')

        except Exception as e:
            import traceback
            self._show_copyable_message(QMessageBox.Critical, "خطأ غير متوقع", f"حدث خطأ أثناء تحديث القائمة: {e}", detailed_text=traceback.format_exc())
            # print(f"DEBUG HIGHLIGHT: update_files_list unexpected error: {e}\n{traceback.format_exc()}")

    def create_playlist_content(self, type_):

        playlist = []

        self.playlist_with_reps.clear()

        try:
            if type_ == "PAGE_BASED":
                # SIMPLIFIED: Play ayahs sequentially instead of concatenating.
                # This is more robust and avoids dependency on ffmpeg/pydub for this feature.
                for file in self.files_list:
                    # Just play each file in the selected range once.
                    self.playlist_with_reps.append({'file': file, 'rep': 1, 'total_reps': 1})

            elif type_ == "SINGLE":

                for file in self.files_list:

                    # Assuming 'repeat' should come from spin_single_repeat
                    repeat = self.spin_single_repeat.value()

                    for i in range(repeat):

                        self.playlist_with_reps.append(
                            {'file': file, 'rep': i + 1, 'total_reps': repeat})

            elif type_ == "GROUP":

                repeat_group = self.spin_group_repeat.value()

                for i in range(repeat_group):

                    for file in self.files_list:

                        self.playlist_with_reps.append(
                            {'file': file, 'rep': i + 1, 'total_reps': repeat_group})

            elif type_ == "COMPLEX":

                repeat_individual = self.spin_complex_individual.value()

                repeat_group = self.spin_complex_group.value()

                group_size = self.spin_complex_group_size.value()

                for i, file in enumerate(self.files_list):

                    for j in range(repeat_individual):

                        self.playlist_with_reps.append(
                            {'file': file, 'rep': j + 1, 'total_reps': repeat_individual})

                    if i > 0:

                        start_index = max(0, i - (group_size - 1))

                        group_files = self.files_list[start_index:i + 1]

                        for j in range(repeat_group):

                            for group_file in group_files:

                                self.playlist_with_reps.append(
                                    {'file': group_file, 'rep': j + 1, 'total_reps': repeat_group})

            playlist = [item['file'] for item in self.playlist_with_reps]

            return playlist

        except Exception as e:

            QMessageBox.critical(
    self, "خطأ", f"حدث خطأ عند إنشاء القائمة: {e}")

            return None

    def prepare_and_play(self, type_):

        # Stop any existing playlist pulses
        self.pulse_play_single.stop()
        self.pulse_play_group.stop()
        self.pulse_play_complex.stop()
        self.pulse_play_page.stop()

        self.update_session_estimate(type_)

        self.play_playlist_internal(type_)

    def play_playlist_internal(self, type_):

        if not self.files_list or not self.output_folder:

            QMessageBox.warning(
    self, "خطأ", "اختر نطاق الملفات ومجلد الحفظ أولاً.")
            return

        if not self.list_player:

            QMessageBox.critical(self, "خطأ VLC", "مشغل القوائم غير جاهز.")
            return

        playlist_content = self.create_playlist_content(type_)

        if not playlist_content: return

        # Clear revealed sets on start
        self.revealed_ayahs_in_playback.clear()
        self.revealed_pages_in_playback.clear()

        self.current_playlist_index = -1

        media_paths = []
        for f in playlist_content:
            if os.path.isabs(f):
                media_paths.append(f)
            else:
                media_paths.append(os.path.join(self.output_folder, f))
        
        media_list = self.vlc_instance.media_list_new(media_paths)
        self.list_player.set_media_list(media_list)
        self.wake_lock.enable() # Prevent sleep during playback
        self.list_player.play()
        
        # Start pulsing the active button based on type
        if type_ == "SINGLE":
            self.pulse_play_single.start()
        elif type_ == "GROUP":
            self.pulse_play_group.start()
        elif type_ == "COMPLEX":
            self.pulse_play_complex.start()
        elif type_ == "PAGE_BASED":
            self.pulse_play_page.start()
            
        self.btn_player_pause.setIcon(QIcon(resource_path("assets/pause.png")))

    @pyqtSlot(object, QColor)
    def _handle_ayah_highlight(self, ayah_ref, color):
        """Thread-safe slot to apply ayah highlight and re-render."""
        # If highlighting (alpha > 0), add to revealed set
        if self.playback_review_mode and color.alpha() > 0:
            self.revealed_ayahs_in_playback.add(ayah_ref)
            
        # This method is guaranteed to run in the main GUI thread.
        self.apply_highlight_to_ayah(ayah_ref, color) # Update state
        # Explicitly re-render the current view to make the change visible
        self.page_renderer.render_page(self.current_page)
        
        # --- NEW: Auto-scroll if highlighting (not clearing) ---
        if color.alpha() > 0 and ayah_ref:
             self.page_renderer.ensure_ayah_visible(ayah_ref[0], ayah_ref[1])

        self.view.viewport().update() # Force an immediate repaint of the viewport

    def handle_item_finished(self, event):
        """
        Called by MediaPlayerEndReached event.
        Its job is to remove the yellow highlight from the ayah that just finished playing.
        """
        if not self.media_player:
            return

        # --- FIX: معالجة انتهاء الأذان والدعاء عبر أحداث VLC ---
        if getattr(self, 'is_azan_playing', False):
            # انتهى الأذان، نطلق الإشارة للانتقال للدعاء
            self.azan_finished_signal.emit()
            return

        if getattr(self, 'is_duaa_playing', False):
            # انتهى الدعاء، نطلق الإشارة للإيقاف
            self.duaa_finished_signal.emit()
            return

        # When an item finishes, we remove its highlight (revert to transparent).
        if self._active_ayah_highlight_ref:
            self.ayah_highlight_signal.emit(self._active_ayah_highlight_ref, QColor(0, 0, 0, 0))

        if self.last_highlighted_page:
            self.page_highlight_signal.emit(self.last_highlighted_page, QColor(0, 0, 0, 0))
            self.last_highlighted_page = None
            
        # --- NEW: Check if Playlist Finished for Plan Update ---
        # If we reached the end of the playlist, mark listening plans as done
        if self.current_playlist_index >= len(self.playlist_with_reps) - 1:
             self.update_plan_progress('listening')

    @pyqtSlot()
    def _reset_playback_reveal(self):
        """Clears revealed text and re-renders for a new repetition cycle."""
        self.revealed_ayahs_in_playback.clear()
        self.revealed_pages_in_playback.clear()
        self.page_renderer.render_page(self.current_page)

    def handle_item_started(self, event):
        """
        Called by MediaListPlayerNextItemSet event, just before a new item plays.
        Its job is to handle page turning and apply the yellow highlight for the new ayah.
        """
        # This event fires before the new item plays. We increment the index to match.
        # The index is initialized to -1 before the playlist starts.
        self.current_playlist_index += 1
        
        if not (0 <= self.current_playlist_index < len(self.playlist_with_reps)):
            return

        try:
            next_item_info = self.playlist_with_reps[self.current_playlist_index]
            file_name = next_item_info['file']

            # --- NEW: Logic to clear revealed text on repetition cycle start ---
            if self.playback_review_mode and self.current_playlist_index > 0:
                prev_item_info = self.playlist_with_reps[self.current_playlist_index - 1]
                
                curr_rep = next_item_info.get('rep', 1)
                prev_rep = prev_item_info.get('rep', 1)
                curr_file = next_item_info.get('file', '')
                prev_file = prev_item_info.get('file', '')
                
                # If repetition increased and file changed (loop back), clear text
                if curr_rep > prev_rep and curr_file != prev_file:
                    self.reset_playback_reveal_signal.emit()
            # -----------------------------------------------------------

            rep_text = f"{next_item_info['rep']}/{next_item_info['total_reps']}"
            self.update_repetition_signal.emit(rep_text, f"التكرار الحالي: {rep_text}")
            self.update_toast_signal.emit(f"التكرار {rep_text}", False)

            if self.reciter_file_system == 'ayah_based' and len(file_name) >= 10 and file_name.lower().endswith(('.mp3', '.wav')):
                sura_num = int(file_name[0:3])
                ayah_num = int(file_name[3:6])
                next_ayah_ref = (sura_num, ayah_num)

                target_page = self.get_page_for_sura_aya(sura_num, ayah_num)
                if target_page:
                    current_spread = {self.current_page}
                    if self.view_mode == 'two_pages':
                        if self.current_page == 1: current_spread.add(2)
                        elif self.current_page % 2 == 0: current_spread.add(self.current_page - 1)
                        elif self.current_page < 604: current_spread.add(self.current_page + 1)
                    
                    if target_page not in current_spread:
                        self.page_turn_signal.emit(target_page)

                self.ayah_highlight_signal.emit(next_ayah_ref, self.playlist_highlight_color)
                self._active_ayah_highlight_ref = next_ayah_ref

            elif self.reciter_file_system == 'page_based':
                try:
                    target_page = int(os.path.splitext(file_name)[0])
                    if self.current_page != target_page:
                        self.page_turn_signal.emit(target_page)
                    
                    self.page_highlight_signal.emit(target_page, self.playlist_highlight_color)
                    self.last_highlighted_page = target_page
                except ValueError:
                    pass

            else: # Logic for sura-based or other file systems
                target_page = -1
                try:
                    if file_name.startswith("page_") and file_name.lower().endswith((".mp3", ".wav")):
                        target_page = int(os.path.splitext(file_name)[0].replace("page_", ""))
                    elif self.reciter_file_system == 'sura_based':
                        target_page = int(os.path.splitext(file_name)[0])
                except (ValueError, IndexError):
                    target_page = -1

                if target_page != -1:
                    if self.current_page != target_page:
                        self.page_turn_signal.emit(target_page)
        except Exception as e:
            print(f"Error in handle_item_started thread: {e}")

    def apply_highlight_to_page(self, page_num, color):
        """Applies a highlight color to all words of a specific page."""
        if self.playback_review_mode and color.alpha() > 0:
            self.revealed_pages_in_playback.add(page_num)
            
        # Try getting ayas with int key first, then string key to be safe
        ayas_on_page = self.data_manager.pages_by_number.get(page_num)
        if not ayas_on_page:
            ayas_on_page = self.data_manager.pages_by_number.get(str(page_num), [])

        if not ayas_on_page:
            return
            
        for ayah_info in ayas_on_page:
            self.apply_highlight_to_ayah((ayah_info['sura_no'], ayah_info['aya_no']), color)

        # Trigger a single re-render after all words on the page have been updated
        self.page_renderer.render_page(self.current_page)

    def _apply_range_highlight(self, start_sura_aya: Tuple[int, int], end_sura_aya: Tuple[int, int], color: QColor, clear_existing: bool = True):
        """
        Applies a highlight color to all ayahs within a specified range.
        If clear_existing is True, it will first clear any previously stored range highlight.
        """
        # print(f"DEBUG HIGHLIGHT: _apply_range_highlight called. start={start_sura_aya}, end={end_sura_aya}, color={color}, clear_existing={clear_existing}")
        if not start_sura_aya or not end_sura_aya:
            # print(f"DEBUG HIGHLIGHT: _apply_range_highlight: Invalid start or end reference.")
            # If the references are None, it means we are trying to clear. Ensure it's cleared.
            if hasattr(self, '_highlighted_range_ayats') and self._highlighted_range_ayats:
                # print(f"DEBUG HIGHLIGHT: Clearing {len(self._highlighted_range_ayats)} previously highlighted ayahs due to invalid range.")
                # We don't call apply_highlight_to_ayah here, just clear the pending highlights
                self._highlighted_range_ayats = []
                self._pending_word_highlights.clear() # Clear pending highlights
            self.page_renderer.render_page(self.current_page) # Ensure a render occurs to clear
            return

        if clear_existing:
            # Clear previous range highlight, if any
            if hasattr(self, '_highlighted_range_ayats') and self._highlighted_range_ayats:
                # print(f"DEBUG HIGHLIGHT: Clearing {len(self._highlighted_range_ayats)} previously highlighted ayahs.")
                # We don't call apply_highlight_to_ayah here, just clear the pending highlights
                self._highlighted_range_ayats = []
                self._pending_word_highlights.clear() # Clear pending highlights


        all_ayats_in_range = self.data_manager.get_all_ayats_in_range(start_sura_aya, end_sura_aya)
        # print(f"DEBUG HIGHLIGHT: get_all_ayats_in_range returned {len(all_ayats_in_range)} ayahs.")

        # Store the highlighted ayats so we can clear them later
        self._highlighted_range_ayats = all_ayats_in_range

        for ayah_ref in all_ayats_in_range:
            self.apply_highlight_to_ayah(ayah_ref, color) # Apply color without immediate render for each ayah
        
        
        pages_to_render = set()
        for ayah_ref in all_ayats_in_range:
            # We need the page number for each ayah.
            # get_page_for_sura_aya is suitable for this.
            page_num = self.get_page_for_sura_aya(ayah_ref[0], ayah_ref[1])
            if page_num:
                pages_to_render.add(page_num)

        # Trigger a render for all affected pages
        # print(f"DEBUG HIGHLIGHT: Triggering page renders for pages: {pages_to_render}")
        for p_num in pages_to_render:
            self.page_renderer.render_page(p_num)

    def apply_highlight_to_ayah(self, ayah_ref, color):
        """Applies a highlight color to all words of a specific ayah."""
        # print(f"DEBUG HIGHLIGHT: apply_highlight_to_ayah called for {ayah_ref} with color {color}.")
        if not ayah_ref: return
        sura_num, ayah_num = ayah_ref

        # [FIX] Use page layout data instead of the disabled all_mushaf_words_flat
        # This avoids the memory overhead of the flat list while still allowing highlighting.
        
        # 1. Find the page for this ayah
        start_page_num = self.get_page_for_sura_aya(sura_num, ayah_num)
        if not start_page_num:
            return

        # Check this page and the next one (in case ayah spans two pages)
        pages_to_check = [start_page_num]
        if start_page_num < 604:
            pages_to_check.append(start_page_num + 1)

        for p_num in pages_to_check:
            page_lines = self.data_manager.get_page_layout(p_num)
            if not page_lines: continue

            for line in page_lines:
                for word_data in line:
                    w_sura = word_data.get('surah')
                    w_aya = word_data.get('ayah')
                    
                    if w_sura == sura_num and w_aya == ayah_num:
                        word_id = word_data.get('word')
                        if word_id is not None:
                            global_idx_str = f"{w_sura}:{w_aya}:{word_id}"
                            self._pending_word_highlights[global_idx_str] = color

    def player_toggle_pause(self):
        if not self.media_player: return
        
        # --- FIX: Prefer list_player control if active ---
        if self.list_player:
            state = self.list_player.get_state()
            # vlc.State.Playing=3, vlc.State.Paused=4
            if state == vlc.State.Playing:
                self.list_player.pause()
                self.btn_player_pause.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
                self.wake_lock.disable()
                return
            elif state == vlc.State.Paused or state == vlc.State.Stopped or state == vlc.State.Ended:
                # Resume or Restart
                self.list_player.play()
                self.btn_player_pause.setIcon(QIcon(resource_path("assets/pause.png")))
                self.wake_lock.enable()
                return

        if self.media_player.is_playing():
            self.media_player.pause()
            self.btn_player_pause.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.wake_lock.disable() # Allow sleep when paused
        else:
            self.media_player.play()
            self.btn_player_pause.setIcon(QIcon(resource_path("assets/pause.png")))
            self.wake_lock.enable() # Prevent sleep when playing

    def player_next(self):
        if self.list_player: self.list_player.next()

    def player_previous(self):
        if self.list_player: self.list_player.previous()

    def player_stop(self):
        if self.list_player:
            self.list_player.stop()
            self.wake_lock.disable() # Allow sleep when stopped
            self.btn_player_pause.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.range_start_ref = self.range_end_ref = self.last_active_ayah_ref = self._active_ayah_highlight_ref = None
            self.last_highlighted_page = None # Clear page highlight tracker
            
            # Stop all playlist pulses
            self.pulse_play_single.stop()
            self.pulse_play_group.stop()
            self.pulse_play_complex.stop()
            self.pulse_play_page.stop()
            self.permanent_toast_message = ""
            self.toast_label.hide()
            
            # NEW: Clear any active range highlight
            # --- FIX: Unconditionally clear all highlights ---
            if hasattr(self, '_pending_word_highlights'):
                self._pending_word_highlights.clear()
            if hasattr(self, '_highlighted_range_ayats'):
                self._highlighted_range_ayats = []

            if self.repetition_label:
                self.repetition_label.setText("-/-")
            # print(f"DEBUG HIGHLIGHT: Triggering page render in player_stop for page {self.current_page}")
            self.page_renderer.render_page(self.current_page)

    def on_speed_changed(self, value):
        self.set_playback_rate(value)
        self.update_session_estimate()

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

    def on_player_slider_moved(self, position):
        """يتم استدعاؤها عند تحريك مؤشر التشغيل يدوياً."""
        if self.media_player:
            # قيمة المؤشر من 0 إلى 1000، نحولها إلى نسبة مئوية (0.0 إلى 1.0)
            self.media_player.set_position(position / 1000.0)

    def update_session_estimate(self, mode=None):
        """Calculates and displays the estimated session duration and updates tooltips."""
        # If recording is active, do not overwrite the actual elapsed time with the estimate
        if self.recording:
            return

        if mode:
            self.last_estimate_mode = mode

        # If there are no files selected, reset the hint labels and tooltips, then exit.
        if not self.files_list:
            self.update_duration_signal.emit("--:--", "المدة الزمنية الإجمالية المقدرة لتشغيل قائمة الحفظ الحالية")
            self.update_repetition_signal.emit("0", "إجمالي عدد مرات تشغيل كل آية في القائمة حسب نظام التكرار المختار")
            self.update_ayah_count_signal.emit("0", "إجمالي عدد الآيات (الملفات الصوتية) في النطاق المحدد")
            return

        num_files = len(self.files_list)
        self.update_ayah_count_signal.emit(f"{num_files}", f"إجمالي عدد الآيات في القائمة: {num_files}")

        total_plays = 0
        mode_name = ""

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
            if group_size > 1:
                for i in range(1, num_files):
                    current_group_len = min(i + 1, group_size)
                    complex_group_plays += current_group_len * self.spin_complex_group.value()
            total_plays = complex_individual_plays + complex_group_plays
            mode_name = "مركب"
        
        # When no mode is specified yet (e.g. after updating range but before playing),
        # at least show the count and a default duration.
        if not mode_name and num_files > 0:
             mode_name = "فردي" # Assume single for estimation
             total_plays = num_files * self.spin_single_repeat.value()


        base_duration_s = total_plays * self.AVERAGE_AYAH_DURATION_S
        rate = self.speed_slider.value() / 100.0 if hasattr(self, 'speed_slider') and self.speed_slider else 1.0
        adjusted_duration_s = base_duration_s / rate if rate > 0 else 0

        duration_str = self.format_time(adjusted_duration_s * 1000, show_hours=True)

        self.update_duration_signal.emit(f"~{duration_str}", f"المدة الزمنية التقديرية للجلسة بنظام '{mode_name}': {duration_str}")
        self.update_repetition_signal.emit(f"{total_plays}", f"إجمالي مرات تشغيل الآيات في هذه الجلسة: {total_plays}")

    def closeEvent(self, event):
        """Saves all settings when the application is closed."""
        try:
            self.wake_lock.disable() # Ensure sleep is allowed on exit
            # print("DIAGNOSTIC: closeEvent called. Saving settings...")
            # Save playlist settings into the main settings dictionary
            if hasattr(self, 'save_playlist_settings'):
                self.save_playlist_settings()

            # Save all other settings that are managed directly, checking for existence
            if hasattr(self, 'scale_factor'):
                self.settings["scale_factor"] = self.scale_factor
            if hasattr(self, 'page_bg_color'):
                self.settings["page_bg_color"] = self.page_bg_color.name()
            if hasattr(self, 'quran_text_color'):
                self.settings["quran_text_color"] = self.quran_text_color.name()
            if hasattr(self, 'review_text_color'):
                self.settings["review_text_color"] = self.review_text_color.name()
            if hasattr(self, 'quran_text_display_font_family'):
                self.settings["quran_text_display_font_family"] = self.quran_text_display_font_family
            if hasattr(self, 'static_font_size'):
                self.settings["static_font_size"] = self.static_font_size
            if hasattr(self, 'dynamic_font_size'):
                self.settings["dynamic_font_size"] = self.dynamic_font_size
            if hasattr(self, 'show_aya_markers'):
                self.settings["show_aya_markers"] = self.show_aya_markers
            if hasattr(self, 'continuous_recitation'):
                self.settings["continuous_recitation"] = self.continuous_recitation
            if hasattr(self, 'recitation_repetitions'):
                self.settings["recitation_repetitions"] = self.recitation_repetitions
            if hasattr(self, 'justify_text'):
                self.settings["justify_text"] = self.justify_text
            if hasattr(self, 'spin_auto_reveal_pause') and self.spin_auto_reveal_pause:
                self.settings["auto_reveal_pause"] = self.spin_auto_reveal_pause.value()
            if hasattr(self, 'dynamic_word_spacing'):
                self.settings["dynamic_word_spacing"] = self.dynamic_word_spacing
            if hasattr(self, 'font_weight'):
                self.settings["font_weight"] = self.font_weight
            if hasattr(self, 'noise_level'):
                self.settings["noise_level"] = self.noise_level
            if hasattr(self, 'view_mode'):
                self.settings["view_mode"] = self.view_mode
            # Save noise gate threshold
            if hasattr(self, 'noise_gate_threshold'):
                self.settings["noise_gate_threshold"] = self.noise_gate_threshold
            
            # --- NEW: Save Toast Position ---
            if hasattr(self, 'toast_label') and getattr(self.toast_label, 'user_has_moved', False):
                self.settings["toast_x"] = self.toast_label.x()
                self.settings["toast_y"] = self.toast_label.y()

            # Save last user
            if hasattr(self, 'user_manager') and self.user_manager.current_user:
                self.settings["last_user"] = self.user_manager.current_user

            # --- NEW: Save Prayer Widget State ---
            if hasattr(self, 'prayer_widget'):
                self.settings["prayer_widget_pos"] = [self.prayer_widget.pos().x(), self.prayer_widget.pos().y()]
                self.settings["show_prayer_widget_on_startup"] = self.prayer_widget.isVisible()

            # Now, save the combined settings dictionary to the file
            save_settings(self.settings)
            
            # Hide to tray instead of closing
            self.hide()
            event.ignore()
            if hasattr(self, 'tray_icon'):
                self.tray_icon.showMessage(self.tr("app_title"), self.tr("app_running_in_bg"), QSystemTrayIcon.Information, 2000)

        except Exception as e:
            pass # print(f"FATAL ERROR during closeEvent: {e}")
        # The event is ignored to keep the app running

    def handle_word_click(self, clicked_word_global_idx_str):
        """
        هذه هي الدالة المحورية لمنطق التسميع بالنقر.
        تُستدعى عند النقر على أي كلمة في الصفحة.
        """
        # print(f"DEBUG: Word clicked: {clicked_word_global_idx_str}")
        # --- NEW: If not recording, show Word Info Popup ---
        if not self.recording_mode:
            # Parse global_idx to get sura, aya, word
            try:
                sura, aya, word = map(int, clicked_word_global_idx_str.split(':'))
                
                # Get Global Word ID from DataManager
                global_word_id = self.data_manager.get_global_word_id_from_local(sura, aya, word)
                if global_word_id:
                    # إغلاق النافذة السابقة إذا كانت مفتوحة لتجنب تكرار النوافذ
                    if hasattr(self, '_word_info_dialog') and self._word_info_dialog and self._word_info_dialog.isVisible():
                        self._word_info_dialog.close()
                    
                    self._word_info_dialog = WordInfoDialog(self.info_manager, self.data_manager, global_word_id, font_family=self.quran_text_display_font_family, parent=self, user_manager=self.user_manager)
                    self._word_info_dialog.show()
            except Exception as e:
                pass # print(f"Error showing word info: {e}")
            return
        
        self.page_renderer.render_page(self.current_page)

    def set_recitation_start(self, global_idx):
        """Sets the start of the recitation range from the context menu."""
        if self.recording:
            self.progress("⚠️ لا يمكن تغيير النطاق أثناء التسميع.")
            return
        try:
            sura, aya, word = map(int, global_idx.split(':'))
            
            # --- NEW: Check active tab to determine target (Tasmee or Playlist) ---
            # Tab 3 is Playlist (Updated index)
            current_idx = self.right_panel.currentIndex() if hasattr(self, 'right_panel') else 0
            
            if current_idx == 2: # Playlist Tab
                 self._set_playlist_range(sura, aya, is_start=True)
            elif current_idx == 3: # Review Tab
                 idx = self.combo_review_from_sura.findData(sura)
                 if idx != -1: self.combo_review_from_sura.setCurrentIndex(idx)
                 self.spin_review_from_aya.setValue(aya)
                 self.progress(self.tr("review_start_set", self.combo_review_from_sura.currentText(), aya))
            else:
                # Update UI (Tasmee)
                idx = self.combo_from_sura.findData(sura)
                if idx != -1:
                    self.combo_from_sura.setCurrentIndex(idx)
                    self.spin_from_aya.setValue(aya)
                    self.progress(self.tr("selection_start_set", self.combo_from_sura.currentText(), aya))
                    # Optional: Play a small sound or visual feedback
        except Exception as e:
            pass # print(f"Error setting start: {e}")

    def set_recitation_end(self, global_idx):
        """Sets the end of the recitation range from the context menu."""
        if self.recording:
            self.progress("⚠️ لا يمكن تغيير النطاق أثناء التسميع.")
            return
        try:
            sura, aya, word = map(int, global_idx.split(':'))
            
            # --- NEW: Check active tab to determine target (Tasmee or Playlist) ---
            current_idx = self.right_panel.currentIndex() if hasattr(self, 'right_panel') else 0
            
            if current_idx == 2: # Playlist Tab
                 self._set_playlist_range(sura, aya, is_start=False)
            elif current_idx == 3: # Review Tab
                 idx = self.combo_review_to_sura.findData(sura)
                 if idx != -1: self.combo_review_to_sura.setCurrentIndex(idx)
                 self.spin_review_to_aya.setValue(aya)
                 self.progress(self.tr("review_end_set", self.combo_review_to_sura.currentText(), aya))
            else:
                # Update UI (Tasmee)
                idx = self.combo_to_sura.findData(sura)
                if idx != -1:
                    # --- FIX: Block signals to prevent auto-reset to max aya ---
                    self.combo_to_sura.blockSignals(True)
                    self.combo_to_sura.setCurrentIndex(idx)
                    
                    # Manually update range for the new sura
                    if sura in self.data_manager.sura_aya_counts:
                        max_ayas = self.data_manager.sura_aya_counts[sura]
                        self.spin_to_aya.setRange(1, max_ayas)
                    
                    self.combo_to_sura.blockSignals(False)
                    self.spin_to_aya.setValue(aya)
                    self.progress(self.tr("selection_end_set", self.combo_to_sura.currentText(), aya))
        except Exception as e:
            pass # print(f"Error setting end: {e}")

    def _set_playlist_range(self, sura, aya, is_start, auto_update=True):
        """Helper to set playlist start/end file based on selected word."""
        if not self.output_folder:
             QMessageBox.warning(self, "تنبيه", "الرجاء اختيار مجلد القارئ أولاً في تبويب البلاي ليست.")
             return

        candidates = []
        
        # Determine filename based on the detected system for the current reciter
        if self.reciter_file_system == 'ayah_based':
            candidates.append(f"{sura:03d}{aya:03d}")
        elif self.reciter_file_system == 'page_based':
            page = self.get_page_for_sura_aya(sura, aya)
            if page:
                candidates.append(f"{page:03d}")
                candidates.append(f"{page}") # Support unpadded (e.g. "1.mp3")
        elif self.reciter_file_system == 'sura_based':
            candidates.append(f"{sura:03d}")
            candidates.append(f"{sura}") # Support unpadded
        
        if not candidates:
            self.progress("⚠️ لم يتم تحديد نظام الملفات أو الصفحة.")
            return

        # Check for extension (.mp3 or .wav)
        final_file = ""
        for base in candidates:
            for ext in ['.mp3', '.wav']:
                if os.path.exists(os.path.join(self.output_folder, base + ext)):
                    final_file = base + ext
                    break
            if final_file: break
        
        if final_file:
            if is_start:
                self.start_file = final_file
                self.start_file_label.setText(final_file)
                self.progress(self.tr("playlist_start_set", final_file))
            else:
                self.end_file = final_file
                self.end_file_label.setText(final_file)
                self.progress(self.tr("playlist_end_set", final_file))
            
            # NEW: Auto-update if both are present
            if self.start_file and self.end_file and auto_update:
                self.update_files_list()
        else:
            target_filename = candidates[0] if candidates else "???"
            self.progress(self.tr("file_not_found", target_filename))

    def set_range_page(self, global_idx):
        """Sets the range to the full page containing the selected word."""
        try:
            sura, aya, word = map(int, global_idx.split(':'))
            page = self.get_page_for_sura_aya(sura, aya)
            if not page: return
            
            # Get ayahs on this page (try int key then str key)
            ayas = self.data_manager.pages_by_number.get(page)
            if not ayas:
                 ayas = self.data_manager.pages_by_number.get(str(page))
            
            if not ayas: return

            first_aya = ayas[0]
            last_aya = ayas[-1]
            
            self._apply_range_selection(first_aya['sura_no'], first_aya['aya_no'], last_aya['sura_no'], last_aya['aya_no'])
        except Exception as e:
            pass # print(f"Error setting page range: {e}")

    def set_range_sura(self, global_idx):
        """Sets the range to the full sura containing the selected word."""
        try:
            sura, aya, word = map(int, global_idx.split(':'))
            # Get max aya for this sura
            max_aya = self.data_manager.sura_aya_counts.get(sura)
            if not max_aya: return

            self._apply_range_selection(sura, 1, sura, max_aya)
        except Exception as e:
            pass # print(f"Error setting sura range: {e}")

    def set_range_juz(self, global_idx):
        """Sets the range to the full Juz containing the selected word."""
        try:
            sura, aya, word = map(int, global_idx.split(':'))
            page = self.get_page_for_sura_aya(sura, aya)
            juz = self.data_manager.page_to_juz.get(page) if page else None
            
            # Fallback: Try getting juz from the ayah data directly if page lookup failed
            if not juz:
                for item in self.data_manager.all_ayas:
                    if item['sura_no'] == sura and item['aya_no'] == aya:
                        juz = item.get('juz')
                        break

            if juz:
                range_vals = self.data_manager.get_range_for_unit('juz', juz)
                if range_vals:
                    self._apply_range_selection(*range_vals)
                    self.progress(self.tr("juz_set", juz))
        except Exception as e:
            pass # print(f"Error setting juz range: {e}")

    def set_range_hizb(self, global_idx):
        """Sets the range to the full Hizb containing the selected word."""
        try:
            sura, aya, word = map(int, global_idx.split(':'))
            target_hizb = None
            for item in self.data_manager.all_ayas:
                if item['sura_no'] == sura and item['aya_no'] == aya:
                    rub = item.get('hizb_quarter') or 1 # Default to 1 if missing
                    if rub: target_hizb = (rub - 1) // 4 + 1
                    break
            
            if target_hizb:
                range_vals = self.data_manager.get_range_for_unit('hizb', target_hizb)
                if range_vals:
                    self._apply_range_selection(*range_vals)
                    self.progress(self.tr("hizb_set", target_hizb))
            else:
                self.progress(self.tr("hizb_info_missing"))
        except Exception as e:
            pass # print(f"Error setting hizb range: {e}")

    def set_range_rub(self, global_idx):
        """Sets the range to the full Rub (Quarter) containing the selected word."""
        try:
            sura, aya, word = map(int, global_idx.split(':'))
            target_rub = None
            for item in self.data_manager.all_ayas:
                if item['sura_no'] == sura and item['aya_no'] == aya:
                    target_rub = item.get('hizb_quarter') or 1 # Default to 1 if missing
                    break
            
            if target_rub:
                range_vals = self.data_manager.get_range_for_unit('rub', target_rub)
                if range_vals:
                    self._apply_range_selection(*range_vals)
                    self.progress(self.tr("rub_set", target_rub))
            else:
                self.progress(self.tr("rub_info_missing"))
        except Exception as e:
            pass # print(f"Error setting rub range: {e}")

    def _apply_range_selection(self, start_sura, start_aya, end_sura, end_aya, interactive=True):
        """Helper to apply start/end range to either Playlist or Tasmee tab."""
        # Check active tab (Tab 2 is Playlist)
        current_idx = self.right_panel.currentIndex() if hasattr(self, 'right_panel') else 0
        
        if current_idx == 2: # Playlist
             if interactive:
                 reply = QMessageBox.question(self, self.tr("playlist_update_confirm"), 
                                              self.tr("playlist_update_msg"),
                                              QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                 if reply == QMessageBox.No:
                     return
             self._set_playlist_range(start_sura, start_aya, is_start=True, auto_update=False)
             self._set_playlist_range(end_sura, end_aya, is_start=False, auto_update=False)
             if self.start_file and self.end_file:
                 self.update_files_list()
        elif current_idx == 3: # Review
             self._set_review_range(start_sura, start_aya, is_start=True)
             self._set_review_range(end_sura, end_aya, is_start=False)
        else: # Tasmee Tab
            # Safety check: If Tasmee widgets are missing (Lite version), don't crash
            if not self.combo_from_sura: return
            
            idx_start = self.combo_from_sura.findData(start_sura)
            if idx_start != -1: self.combo_from_sura.setCurrentIndex(idx_start)
            self.spin_from_aya.setValue(start_aya)
            
            idx_end = self.combo_to_sura.findData(end_sura)
            if idx_end != -1: 
                # --- FIX: Block signals to prevent auto-reset to max aya ---
                self.combo_to_sura.blockSignals(True)
                self.combo_to_sura.setCurrentIndex(idx_end)
                
                # Manually update range for the new sura
                if end_sura in self.data_manager.sura_aya_counts:
                    max_ayas = self.data_manager.sura_aya_counts[end_sura]
                    self.spin_to_aya.setRange(1, max_ayas)
                
                self.combo_to_sura.blockSignals(False)

            self.spin_to_aya.setValue(end_aya)
            
            self.progress(self.tr("range_set_success", start_sura, start_aya, end_sura, end_aya))

    def _set_review_range(self, sura, aya, is_start):
        """Helper to set range in Review tab."""
        if is_start:
            idx = self.combo_review_from_sura.findData(sura)
            if idx != -1: self.combo_review_from_sura.setCurrentIndex(idx)
            self.spin_review_from_aya.setValue(aya)
        else:
            idx = self.combo_review_to_sura.findData(sura)
            if idx != -1: self.combo_review_to_sura.setCurrentIndex(idx)
            self.spin_review_to_aya.setValue(aya)

    def on_page_changed(self, v: int, update_input: bool = True, from_start_recording: bool = False):
        if hasattr(self, 'current_page') and self.current_page == v and not from_start_recording:
            return

        self.current_page = v

        # NEW: Track visited pages during recitation
        if self.recording_mode:
            self.recited_pages.add(self.current_page)
            # Also add the other page in a two-page view
            if self.view_mode == "two_pages":
                if self.current_page == 1:
                    self.recited_pages.add(2)
                elif self.current_page % 2 == 0:
                    self.recited_pages.add(self.current_page - 1)
                elif self.current_page < 604:
                    self.recited_pages.add(self.current_page + 1)

        if update_input:
            self.page_input.setText(str(self.current_page))
        
        self.page_renderer.clear_page_overlays()
        if hasattr(self, 'word_items'):
             self.word_items.clear()
        
        self.session_debug_log.append({
        'event': 'PAGE_CHANGED', 'page': self.current_page, 'time': time.time()
        })
        self.page_renderer.render_page(self.current_page) # Trigger debounced render
        self.page_completed_waiting_for_stop = False
        self.update_nav_combos()
        
        # NEW: Force garbage collection to free up memory from the old page's objects
        gc.collect()
        
        # --- NEW: Apply Auto Reveal Mask if active ---
        if getattr(self, 'is_auto_reveal_mode', False):
            self._apply_auto_reveal_mask()
            
        # --- NEW: Apply Voice Trigger Mask if active ---
        if getattr(self, 'is_voice_trigger_active', False):
            self._apply_voice_trigger_mask()

# ---------- helpers ----------
    def on_rec_next_page(self):
        """Navigates to the next page pair during active recitation."""
        if not self.recording_mode:
            return
        new_page = self.current_page + 2
        if new_page > 604:
            new_page = 1 # Loop back
        self.on_page_changed(new_page)

    def on_rec_prev_page(self):
        """Navigates to the previous page pair during active recitation."""
        if not self.recording_mode:
            return
        self.on_page_changed(max(1, self.current_page - 2))

    def on_prev(self):
        # Move back to the previous spread. Spreads are (1,2), (3,4), etc.
        # Find the start of the current spread (the odd page number)
        current_odd_page = self.current_page
        if current_odd_page % 2 == 0:
            current_odd_page -= 1
        
        new_page = current_odd_page - 2
        if new_page < 1:
            new_page = 1
        
        self.on_page_changed(new_page)

    def on_next(self):
        # Move forward to the next spread. Spreads are (1,2), (3,4), etc.
        # Find the start of the current spread (the odd page number)
        current_odd_page = self.current_page
        if current_odd_page % 2 == 0:
            current_odd_page -= 1

        new_page = current_odd_page + 2
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
        if not self.page_input or not self.page_input.hasFocus():
            return
        
        # استخدام مؤقت (Debounce) لتأخير التحديث قليلاً حتى ينتهي المستخدم من الكتابة
        self.page_input_debounce_timer.start()

    def _perform_page_input_update(self):
        """يتم استدعاؤها بواسطة المؤقت بعد توقف المستخدم عن الكتابة."""
        text = self.page_input.text()
        try:
            page = int(text)
            if 1 <= page <= 604:
                self.on_page_changed(page, update_input=False)
        except ValueError:
            pass

    def on_juz_input_changed(self, text: str):
        """Handle live text changes in the juz input field."""
        if not self.juz_input or not self.juz_input.hasFocus():
            return
        self.juz_input_debounce_timer.start()

    def _perform_juz_input_update(self):
        """Called by timer after user stops typing in juz input."""
        text = self.juz_input.text()
        try:
            juz = int(text)
            if 1 <= juz <= 30:
                self._navigate_to_juz(juz)
        except ValueError:
            pass

    def on_juz_input_enter(self):
        try:
            juz = int(self.juz_input.text())
            if 1 <= juz <= 30:
                self._navigate_to_juz(juz)
            else:
                # Find current juz and revert
                current_juz = self.data_manager.page_to_juz.get(self.current_page)
                self.juz_input.setText(str(current_juz) if current_juz else "")
        except ValueError:
            # Find current juz and revert
            current_juz = self.data_manager.page_to_juz.get(self.current_page)
            self.juz_input.setText(str(current_juz) if current_juz else "")





    def _navigate_to_juz(self, juz_no: int):
        """Finds the page for a given Juz and navigates to it."""
        if self._user_navigating: return
        
        # print(f"DEBUG: _navigate_to_juz called with juz_no={juz_no}")
        target_page = self.data_manager.juz_pages.get(juz_no)
        # print(f"DEBUG: target_page={target_page}, current_page={self.current_page}")
        if target_page is not None:
            if self.current_page != target_page:
                self._user_navigating = True
                try:
                    self.on_page_changed(target_page)
                finally:
                    self._user_navigating = False

    def on_from_sura_changed(self, index):
        sura_no = self.combo_from_sura.currentData()
        if sura_no in self.data_manager.sura_aya_counts:
            max_ayas = self.data_manager.sura_aya_counts[sura_no]
            self.spin_from_aya.setRange(1, max_ayas)

    def on_to_sura_changed(self, index):
        sura_no = self.combo_to_sura.currentData()
        if sura_no in self.data_manager.sura_aya_counts:
            max_ayas = self.data_manager.sura_aya_counts[sura_no]
            self.spin_to_aya.setRange(1, max_ayas)
            self.spin_to_aya.setValue(max_ayas) # Default to last aya

    def on_playback_review_toggled(self, state):
        """Handles toggling of playback review mode (hide text)."""
        self.playback_review_mode = (state == Qt.Checked)
        self.page_renderer.render_page(self.current_page)

    # --- NEW: Review Tab Range Handlers ---
    def on_review_from_sura_changed(self, index):
        sura_no = self.combo_review_from_sura.currentData()
        if sura_no in self.data_manager.sura_aya_counts:
            max_ayas = self.data_manager.sura_aya_counts[sura_no]
            self.spin_review_from_aya.setRange(1, max_ayas)

    def on_review_to_sura_changed(self, index):
        sura_no = self.combo_review_to_sura.currentData()
        if sura_no in self.data_manager.sura_aya_counts:
            max_ayas = self.data_manager.sura_aya_counts[sura_no]
            self.spin_review_to_aya.setRange(1, max_ayas)
            self.spin_review_to_aya.setValue(max_ayas)

    def on_playback_review_toggled(self, state):
        """Handles toggling of playback review mode (hide text)."""
        self.playback_review_mode = (state == Qt.Checked)
        self.page_renderer.render_page(self.current_page)

    def on_continuous_toggled(self, state):
        # FIX: Correct enum comparison
        self.continuous_recitation = (state == Qt.CheckState.Checked) # type: ignore
        # Save setting
        self.settings["continuous_recitation"] = self.continuous_recitation
        save_settings(self.settings)

    def on_recitation_repetitions_changed(self, value: int):
        """Handles changes in the recitation repetitions spinbox and saves the setting."""
        self.recitation_repetitions = value
        self.settings["recitation_repetitions"] = self.recitation_repetitions
        save_settings(self.settings)

    def update_nav_combos(self):
        """Updates all navigation combos (Juz, Sura, and Recitation Range) based on the current page."""
        
        # --- Update Juz Input ---
        if hasattr(self, 'juz_input') and self.juz_input:
            self.juz_input.blockSignals(True)
            current_juz = self.data_manager.page_to_juz.get(self.current_page)
            if current_juz:
                self.juz_input.setText(str(current_juz))
            else:
                self.juz_input.clear() # Clear it if no juz is found for the page
            self.juz_input.blockSignals(False)

        # Get ayas for the current pair of pages
        # Try integer key first (most likely), then string key fallback
        page1_ayas = self.data_manager.pages_by_number.get(self.current_page)
        if not page1_ayas:
            page1_ayas = self.data_manager.pages_by_number.get(str(self.current_page), [])
            
        page2_ayas = self.data_manager.pages_by_number.get(self.current_page + 1)
        if not page2_ayas:
            page2_ayas = self.data_manager.pages_by_number.get(str(self.current_page + 1), [])
            
        all_ayas_on_screen = page1_ayas + page2_ayas
        
        if not all_ayas_on_screen:
            return

        # Block signals to prevent infinite loops or unwanted updates
        if hasattr(self, 'combo_sura') and self.combo_sura: self.combo_sura.blockSignals(True)
        if hasattr(self, 'combo_from_sura') and self.combo_from_sura: self.combo_from_sura.blockSignals(True)
        if hasattr(self, 'spin_from_aya') and self.spin_from_aya: self.spin_from_aya.blockSignals(True)
        if hasattr(self, 'combo_to_sura') and self.combo_to_sura: self.combo_to_sura.blockSignals(True)
        if hasattr(self, 'spin_to_aya') and self.spin_to_aya: self.spin_to_aya.blockSignals(True)

        try:
            sura_counts = {}
            for aya in all_ayas_on_screen:
                sura = aya.get('sura_no')
                if sura:
                    sura_counts[sura] = sura_counts.get(sura, 0) + 1
            
            if sura_counts:
                majority_sura = max(sura_counts, key=lambda k: sura_counts.get(k, 0) or 0)
                if majority_sura is not None and hasattr(self, 'combo_sura') and self.combo_sura:
                    sura_index = self.combo_sura.findData(majority_sura)
                    if sura_index != -1: self.combo_sura.setCurrentIndex(sura_index)

            # --- NEW: Update Recitation Range ---
            start_aya_info = all_ayas_on_screen[0]
            end_aya_info = all_ayas_on_screen[-1]

            from_sura_no = start_aya_info.get('sura_no')
            from_aya_no = start_aya_info.get('aya_no')
            to_sura_no = end_aya_info.get('sura_no')
            to_aya_no = end_aya_info.get('aya_no')

            if from_sura_no is not None and from_aya_no is not None and hasattr(self, 'combo_from_sura') and self.combo_from_sura:
                from_sura_index = self.combo_from_sura.findData(from_sura_no)
                if from_sura_index != -1:
                    self.combo_from_sura.setCurrentIndex(from_sura_index)
                    # FIX: Update range manually since signals are blocked
                    if from_sura_no in self.data_manager.sura_aya_counts:
                        max_ayas = self.data_manager.sura_aya_counts[from_sura_no]
                        if hasattr(self, 'spin_from_aya') and self.spin_from_aya:
                            self.spin_from_aya.setRange(1, max_ayas)
                if hasattr(self, 'spin_from_aya') and self.spin_from_aya:
                    self.spin_from_aya.setValue(from_aya_no)

            if to_sura_no is not None and to_aya_no is not None and not self.recording_mode and hasattr(self, 'combo_to_sura') and self.combo_to_sura: # NEW: Only update if not in recording mode
                to_sura_index = self.combo_to_sura.findData(to_sura_no)
                if to_sura_index != -1:
                    self.combo_to_sura.setCurrentIndex(to_sura_index)
                    # FIX: Update range manually since signals are blocked
                    if to_sura_no in self.data_manager.sura_aya_counts:
                        max_ayas = self.data_manager.sura_aya_counts[to_sura_no]
                        if hasattr(self, 'spin_to_aya') and self.spin_to_aya:
                            self.spin_to_aya.setRange(1, max_ayas)
                if hasattr(self, 'spin_to_aya') and self.spin_to_aya:
                    self.spin_to_aya.setValue(to_aya_no)

        finally:
            # Unblock all signals
            if hasattr(self, 'combo_sura') and self.combo_sura: self.combo_sura.blockSignals(False)
            if hasattr(self, 'combo_from_sura') and self.combo_from_sura: self.combo_from_sura.blockSignals(False)
            if hasattr(self, 'spin_from_aya') and self.spin_from_aya: self.spin_from_aya.blockSignals(False)
            if hasattr(self, 'combo_to_sura') and self.combo_to_sura: self.combo_to_sura.blockSignals(False)
            if hasattr(self, 'spin_to_aya') and self.spin_to_aya: self.spin_to_aya.blockSignals(False)
            
    # ---------- Settings actions ----------
    def change_bg_color(self):
        # Use the scene's current background color as the starting point for the dialog
        current_color = self.scene.backgroundBrush().color()
        color = QColorDialog.getColor(current_color, self, "اختر لون الخلفية")
        if color.isValid():
            self.page_bg_color = color
            self.bg_color = color # Update self.bg_color for consistency
            self.view.setBackgroundBrush(QBrush(self.page_bg_color)) # Changed from scene to view
            # Save setting
            self.settings["page_bg_color"] = self.page_bg_color.name() # Store as hex string
            save_settings(self.settings)

            # --- FIX: Force re-render to apply the new background color immediately ---
            if self.page_renderer:
                self.page_renderer._current_rendered_pages.clear() # Clear the cache of rendered pages
                self.page_renderer.render_page(self.current_page) # Force a full redraw of the current page
    
    def change_quran_text_color(self):
        """Opens a dialog to change the Quran text color."""
        current_color = self.quran_text_color
        color = QColorDialog.getColor(current_color, self, "اختر لون النص القرآني")
        if color.isValid():
            self.quran_text_color = color
            self.settings["quran_text_color"] = self.quran_text_color.name()
            save_settings(self.settings)
            
            # Force re-render to apply the new text color
            if self.page_renderer:
                self.page_renderer._current_rendered_pages.clear()
                self.page_renderer.render_page(self.current_page)

    def select_border_image(self):
        """Allows the user to select a custom border image from the assets folder."""
        initial_path = resource_path("assets")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "اختر صورة الإطار",
            initial_path,
            "Image Files (*.png *.jpg *.jpeg *.gif *.webp)" # Filter for image files
        )
        if file_path:
            # Store only the relative path within assets if possible
            relative_path = os.path.relpath(file_path, resource_path(""))
            
            # Update settings
            self.settings["border_image_path"] = relative_path
            save_settings(self.settings)
            
            # Update UI label
            if self.lbl_current_border_image:
                self.lbl_current_border_image.setText(f"الإطار الحالي: {os.path.basename(file_path)}")
            
            # Apply to page renderer and re-render
            self._apply_border_image_to_renderer(relative_path)
            
            # Force re-render to apply the new border image
            if self.page_renderer:
                self.page_renderer._current_rendered_pages.clear()
                self.page_renderer.render_page(self.current_page)


    def _apply_border_image_to_renderer(self, image_path):
        """Applies the selected border image to the page renderer."""
        full_path = resource_path(image_path)
        if os.path.exists(full_path) and self.page_renderer:
            self.page_renderer.border_pixmap = QPixmap(full_path)
            print(f"DEBUG: Border image set to: {full_path}")
        else:
            self.page_renderer.border_pixmap = None # Clear if invalid
            print(f"WARNING: Border image file not found or invalid: {full_path}")


    def on_change_font_settings(self):
        """Opens a dialog to change all font-related settings."""
        dialog = FontSettingsDialog(self.quran_text_display_font_family, self.font_weight, self.static_font_size, self.dynamic_font_size, self)
        
        if dialog.exec_() == QDialog.Accepted:
            family, weight, static_size, dynamic_size = dialog.get_results()
            
            # Update properties
            self.quran_text_display_font_family = family
            self.font_weight = weight
            self.static_font_size = static_size
            self.dynamic_font_size = dynamic_size
            
            # Save settings
            self.settings["quran_text_display_font_family"] = self.quran_text_display_font_family
            self.settings["font_weight"] = self.font_weight
            self.settings["static_font_size"] = self.static_font_size
            self.settings["dynamic_font_size"] = self.dynamic_font_size
            save_settings(self.settings)
            
            # Re-render the page with the new font
            self.page_renderer.render_page(self.current_page)    
            
    def toggle_aya_markers(self):
        """Toggle visibility of verse-number markers inside pages."""
        self.show_aya_markers = not self.show_aya_markers
        if self.show_aya_markers:
            self.btn_toggle_aya_markers.setText(self.tr("hide_ayah_markers"))
        else:
            self.btn_toggle_aya_markers.setText(self.tr("show_ayah_markers"))
        # print(f"DEBUG: toggle_aya_markers - self.show_aya_markers: {self.show_aya_markers}") # DEBUG
        # Save setting
        self.settings["show_aya_markers"] = self.show_aya_markers
        save_settings(self.settings)
        # re-render current page to apply change
        if hasattr(self, 'page_renderer'):
            self.page_renderer.render_page(self.current_page)

    def on_noise_gate_toggled(self, state):
        """Handles toggling of the noise gate checkbox."""
        self.noise_gate_enabled = (state == Qt.CheckState.Checked)
        # if self.noise_gate_enabled:
        #     print(f"Noise gate enabled with threshold: {self.noise_gate_threshold}")
        # else:
        #     print("Noise gate disabled.")

    # ---------- zoom ----------
    def zoom_in(self): # Zoom in
        self._update_scale(self.scale_factor * 1.1)

    def zoom_out(self):
        self._update_scale(self.scale_factor / 1.1)

    def zoom_reset(self):
        self._update_scale(1.0)

    def _update_scale(self, new_scale): # Update the scaling factor
        self.scale_factor = new_scale
        # Save setting
        self.settings["scale_factor"] = self.scale_factor
        save_settings(self.settings)
        self.page_renderer.render_page(self.current_page)


    def toggle_right_panel(self):
        if self.right_panel:
            self.right_panel.setVisible(not self.right_panel.isVisible())
            # Delay rendering to allow layout to update
            QTimer.singleShot(50, self._fit_page_to_view)

    def toggle_fullscreen_mode(self):
        """Toggles full screen mode and visibility of UI panels (Zen Mode)."""
        if self.isFullScreen():
            self.showMaximized()
            if hasattr(self, 'top_bar_widget'): self.top_bar_widget.show()
            if hasattr(self, 'right_panel'): self.right_panel.show()
            if hasattr(self, 'header_title_label'): self.header_title_label.show()
        else:
            self.showFullScreen()
            if hasattr(self, 'top_bar_widget'): self.top_bar_widget.hide()
            if hasattr(self, 'right_panel'): self.right_panel.hide()
            if hasattr(self, 'header_title_label'): self.header_title_label.hide()
            
        # Adjust page scale to fit the new view size
        QTimer.singleShot(100, self._fit_page_to_view)

    def toggle_feedback(self, checked):
        """Toggles the audio feedback loop."""
        if not SD_AVAILABLE or sd is None:
            if checked:
                self.check_listen_to_device.setChecked(False)
                QMessageBox.warning(self, "خطأ", "مكتبة الصوت غير متاحة.")
            return

        # Stop existing stream if any
        if hasattr(self, 'feedback_stream') and self.feedback_stream:
            try:
                self.feedback_stream.stop()
                self.feedback_stream.close()
            except Exception as e:
                print(f"Error stopping feedback stream: {e}")
            self.feedback_stream = None

        if checked:
            try:
                input_dev = self.input_device_index
                output_dev = getattr(self, 'output_device_id', None)
                
                # If output_device_id is not set, try to get from combo
                if output_dev is None and self.combo_output_device:
                     idx = self.combo_output_device.currentIndex()
                     if idx >= 0:
                         output_dev = self.combo_output_device.itemData(idx)

                def callback(indata, outdata, frames, time, status):
                    if status:
                        print(f"Feedback status: {status}")
                    outdata[:] = indata

                self.feedback_stream = sd.Stream(
                    device=(input_dev, output_dev),
                    samplerate=44100, # Fix: Use standard rate to avoid mismatch/slow audio
                    blocksize=0,      # Let backend decide optimal blocksize
                    dtype='int16',
                    channels=1,
                    callback=callback
                )
                self.feedback_stream.start()
                self.show_toast("تم تفعيل اختبار الصوت 🎤🔊", temporary=True)
            except Exception as e:
                self.check_listen_to_device.setChecked(False)
                QMessageBox.warning(self, "خطأ في الصوت", f"لا يمكن بدء اختبار الصوت:\n{e}")
                self.feedback_stream = None
        else:
             self.show_toast("تم إيقاف اختبار الصوت", temporary=True)

    def decrease_volume(self):
        """Decreases the volume by 5%."""
        if self.volume_slider:
            self.volume_slider.setValue(max(0, self.volume_slider.value() - 5))

    def increase_volume(self):
        """Increases the volume by 5%."""
        if self.volume_slider:
            self.volume_slider.setValue(min(self.volume_slider.maximum(), self.volume_slider.value() + 5))

    def increase_speed(self):
        """Increases playback speed by 5%."""
        if hasattr(self, 'speed_slider') and self.speed_slider:
            self.speed_slider.setValue(min(self.speed_slider.maximum(), self.speed_slider.value() + 5))

    def decrease_speed(self):
        """Decreases playback speed by 5%."""
        if hasattr(self, 'speed_slider') and self.speed_slider:
            self.speed_slider.setValue(max(self.speed_slider.minimum(), self.speed_slider.value() - 5))

    def _create_shortcuts(self):
        """Creates and connects global keyboard shortcuts for the application."""
        # Recitation Control
        self.shortcut_f9 = QShortcut(QKeySequence(Qt.Key_F9), self)
        self.shortcut_f9.activated.connect(self.toggle_play_pause_action)
        
        self.shortcut_f10 = QShortcut(QKeySequence(Qt.Key_F10), self)
        self.shortcut_f10.activated.connect(self.stop_action)

        # Volume Control
        self.shortcut_left = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcut_left.activated.connect(self.decrease_volume)
        
        self.shortcut_right = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcut_right.activated.connect(self.increase_volume)

        # Speed Control
        self.shortcut_plus = QShortcut(QKeySequence(Qt.Key_Plus), self)
        self.shortcut_plus.activated.connect(self.increase_speed)
        self.shortcut_equal = QShortcut(QKeySequence(Qt.Key_Equal), self) # Often the same key as +
        self.shortcut_equal.activated.connect(self.increase_speed)
        
        self.shortcut_minus = QShortcut(QKeySequence(Qt.Key_Minus), self)
        self.shortcut_minus.activated.connect(self.decrease_speed)

    def toggle_play_pause_action(self):
        """Handles F9: Toggles Recitation or Playlist based on active context."""
        # 1. Recitation Mode Priority
        if self.recording_mode:
            if self.btn_stop.isEnabled():
                self.stop_recording()
            elif self.btn_start.isEnabled():
                self.start_recording()
            return

        # 2. Playlist Mode Priority
        if VLC_AVAILABLE and self.list_player:
            state = self.list_player.get_state()
            # vlc.State.Playing=3, vlc.State.Paused=4
            if state == vlc.State.Playing or state == vlc.State.Paused:
                self.player_toggle_pause()
                return

    def stop_action(self):
        """Handles F10: Stops Recitation, Playlist, or Auto Reveal."""
        if self.recording_mode:
            self.end_recitation_session()
        
        if VLC_AVAILABLE and self.list_player:
            state = self.list_player.get_state()
            if state == vlc.State.Playing or state == vlc.State.Paused:
                self.player_stop()

        # NEW: Stop Auto Reveal mode if it's active
        if getattr(self, 'is_auto_reveal_mode', False):
            self.stop_auto_reveal()

    def _fit_page_to_view(self):
        """Renders the page and adjusts scale to fit the view."""
        # Render first to ensure scene content is up to date
        self.page_renderer.render_page(self.current_page)
        
        # Get scene bounds
        scene_rect = self.scene.itemsBoundingRect()
        if scene_rect.width() <= 0 or scene_rect.height() <= 0:
            return

        # Get viewport bounds
        viewport_rect = self.view.viewport().rect()
        
        # Calculate ratios (viewport / scene)
        margin = 20
        available_width = viewport_rect.width() - margin
        available_height = viewport_rect.height() - margin
        
        if available_width > 0 and available_height > 0:
            new_scale = min(available_width / scene_rect.width(), available_height / scene_rect.height())
            self.scale_factor = new_scale
            self.page_renderer._apply_scale()

        # --- FIX: Re-apply masks if active (Critical for Fullscreen/Side Panel toggle) ---
        if getattr(self, 'is_auto_reveal_mode', False):
            self._apply_auto_reveal_mask()
        if getattr(self, 'is_voice_trigger_active', False):
            self._apply_voice_trigger_mask()

    def show_profile_dialog(self):
        """Shows the user selection dialog."""
        dialog = ProfileDialog(self.user_manager, self)
        if dialog.exec_() == QDialog.Accepted:
            self.show_toast(f"مرحباً بك يا {self.user_manager.current_user} 👋")
            if self.btn_profile:
                self.btn_profile.setText(f"👤 {self.user_manager.current_user}")

            # Reload plans for the new user
            self.load_current_user_plans()
            
            # Save last user setting
            self.settings["last_user"] = self.user_manager.current_user
            save_settings(self.settings)

    def show_dashboard(self):
        """Shows the dashboard for the current user."""
        dialog = DashboardDialog(self.user_manager, self)
        dialog.exec_()

    def toggle_right_panel(self):
        if self.right_panel:
            self.right_panel.setVisible(not self.right_panel.isVisible())
            # Delay rendering to allow layout to update
            QTimer.singleShot(50, self._fit_page_to_view)

    def toggle_fullscreen_mode(self):
        """Toggles full screen mode and visibility of UI panels (Zen Mode)."""
        if self.isFullScreen():
            self.showMaximized()
            if hasattr(self, 'top_bar_widget'): self.top_bar_widget.show()
            if hasattr(self, 'right_panel'): self.right_panel.show()
            if hasattr(self, 'header_title_label'): self.header_title_label.show()
        else:
            self.showFullScreen()
            if hasattr(self, 'top_bar_widget'): self.top_bar_widget.hide()
            if hasattr(self, 'right_panel'): self.right_panel.hide()
            if hasattr(self, 'header_title_label'): self.header_title_label.hide()
            
        # Adjust page scale to fit the new view size
        QTimer.singleShot(100, self._fit_page_to_view)

    def toggle_feedback(self, checked):
        """Toggles the audio feedback loop."""
        if not SD_AVAILABLE or sd is None:
            if checked:
                self.check_listen_to_device.setChecked(False)
                QMessageBox.warning(self, "خطأ", "مكتبة الصوت غير متاحة.")
            return

        # Stop existing stream if any
        if hasattr(self, 'feedback_stream') and self.feedback_stream:
            try:
                self.feedback_stream.stop()
                self.feedback_stream.close()
            except Exception as e:
                print(f"Error stopping feedback stream: {e}")
            self.feedback_stream = None

        if checked:
            try:
                input_dev = self.input_device_index
                output_dev = getattr(self, 'output_device_id', None)
                
                # If output_device_id is not set, try to get from combo
                if output_dev is None and self.combo_output_device:
                     idx = self.combo_output_device.currentIndex()
                     if idx >= 0:
                         output_dev = self.combo_output_device.itemData(idx)

                def callback(indata, outdata, frames, time, status):
                    if status:
                        print(f"Feedback status: {status}")
                    outdata[:] = indata

                self.feedback_stream = sd.Stream(
                    device=(input_dev, output_dev),
                    samplerate=44100, # Fix: Use standard rate to avoid mismatch/slow audio
                    blocksize=0,      # Let backend decide optimal blocksize
                    dtype='int16',
                    channels=1,
                    callback=callback
                )
                self.feedback_stream.start()
                self.show_toast("تم تفعيل اختبار الصوت 🎤🔊", temporary=True)
            except Exception as e:
                self.check_listen_to_device.setChecked(False)
                QMessageBox.warning(self, "خطأ في الصوت", f"لا يمكن بدء اختبار الصوت:\n{e}")
                self.feedback_stream = None
        else:
             self.show_toast("تم إيقاف اختبار الصوت", temporary=True)

    def _create_shortcuts(self):
        """Creates and connects global keyboard shortcuts for the application."""
        # Recitation Control
        self.shortcut_f9 = QShortcut(QKeySequence(Qt.Key_F9), self)
        self.shortcut_f9.activated.connect(self.toggle_play_pause_action)
        
        self.shortcut_f10 = QShortcut(QKeySequence(Qt.Key_F10), self)
        self.shortcut_f10.activated.connect(self.stop_action)

        # Volume Control
        self.shortcut_left = QShortcut(QKeySequence(Qt.Key_Left), self)
        self.shortcut_left.activated.connect(self.decrease_volume)
        
        self.shortcut_right = QShortcut(QKeySequence(Qt.Key_Right), self)
        self.shortcut_right.activated.connect(self.increase_volume)

        # Speed Control
        self.shortcut_plus = QShortcut(QKeySequence(Qt.Key_Plus), self)
        self.shortcut_plus.activated.connect(self.increase_speed)
        self.shortcut_equal = QShortcut(QKeySequence(Qt.Key_Equal), self) # Often the same key as +
        self.shortcut_equal.activated.connect(self.increase_speed)
        
        self.shortcut_minus = QShortcut(QKeySequence(Qt.Key_Minus), self)
        self.shortcut_minus.activated.connect(self.decrease_speed)

    def toggle_play_pause_action(self):
        """Handles F9: Toggles Recitation or Playlist based on active context."""
        # 1. Recitation Mode Priority
        if self.recording_mode:
            if self.btn_stop.isEnabled():
                self.stop_recording()
            elif self.btn_start.isEnabled():
                self.start_recording()
            return

        # 2. Playlist Mode Priority
        if VLC_AVAILABLE and self.list_player:
            state = self.list_player.get_state()
            # vlc.State.Playing=3, vlc.State.Paused=4
            if state == vlc.State.Playing or state == vlc.State.Paused:
                self.player_toggle_pause()
                return

    def stop_action(self):
        """Handles F10: Stops Recitation, Playlist, or Auto Reveal."""
        if self.recording_mode:
            self.end_recitation_session()
        
        if VLC_AVAILABLE and self.list_player:
            state = self.list_player.get_state()
            if state == vlc.State.Playing or state == vlc.State.Paused:
                self.player_stop()

        # NEW: Stop Auto Reveal mode if it's active
        if getattr(self, 'is_auto_reveal_mode', False):
            self.stop_auto_reveal()

    def _fit_page_to_view(self):
        """Renders the page and adjusts scale to fit the view."""
        # Render first to ensure scene content is up to date
        self.page_renderer.render_page(self.current_page)
        
        # Get scene bounds
        scene_rect = self.scene.itemsBoundingRect()
        if scene_rect.width() <= 0 or scene_rect.height() <= 0:
            return

        # Get viewport bounds
        viewport_rect = self.view.viewport().rect()
        
        # Calculate ratios (viewport / scene)
        margin = 20
        available_width = viewport_rect.width() - margin
        available_height = viewport_rect.height() - margin
        
        if available_width > 0 and available_height > 0:
            new_scale = min(available_width / scene_rect.width(), available_height / scene_rect.height())
            self.scale_factor = new_scale
            self.page_renderer._apply_scale()

    def show_profile_dialog(self):
        """Shows the user selection dialog."""
        dialog = ProfileDialog(self.user_manager, self)
        if dialog.exec_() == QDialog.Accepted:
            self.show_toast(f"مرحباً بك يا {self.user_manager.current_user} 👋")
            if self.btn_profile:
                self.btn_profile.setText(f"👤 {self.user_manager.current_user}")

            # Reload plans for the new user
            self.load_current_user_plans()
            
            # Save last user setting
            self.settings["last_user"] = self.user_manager.current_user
            save_settings(self.settings)

# ---------- run ----------
def main(app: QApplication, splash: QSplashScreen):
    """
    Main function to initialize and run the Quran Canvas Application.

    Args:
        app (QApplication): The application instance.
        splash (QSplashScreen): The splash screen instance to show during loading.
    """
    w = QuranCanvasApp(splash=splash) # Create an instance of the main application window
    # print("DEBUG: 7 - بعد إنشاء QuranCanvasApp")
    
    # --- FIX: Set initial size to match available screen dimensions ---
    screen_geometry = app.primaryScreen().availableGeometry()
    w.resize(screen_geometry.width(), screen_geometry.height())
    
    # The scale is now loaded or defaulted in __init__ and applied in apply_loaded_settings_to_ui
    # No need to call _update_scale here anymore.

    w.on_page_changed(1) # Render the first page upon startup
    # print("DEBUG: 8 - قبل عرض النافذة")
    
    # Hide the splash screen and show the main window
    splash.finish(w)
    
    w.showMaximized() # Display the window in a maximized state
    sys.exit(app.exec_()) # Start the application event loop

if __name__ == "__main__":
    # --- NEW: Enable High DPI Scaling ---
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    
    app.setLayoutDirection(Qt.RightToLeft)  # Set application direction to Right-to-Left
    
    # --- Splash Screen Setup ---
    try:
        # Create a pixmap for the splash screen from the logo
        logo_path = resource_path("assets/logo.png")
        original_pix = QPixmap(logo_path)
        
        # --- FIX: Check if logo loaded successfully ---
        if original_pix.isNull():
            print(f"Warning: Failed to load splash logo from {logo_path}")
            # Create a fallback pixmap so the splash still has size
            original_pix = QPixmap(500, 500)
            original_pix.fill(Qt.transparent)
            
        # Scale down the logo to a reasonable size (e.g., 300px height)
        splash_pix = original_pix.scaledToHeight(300, Qt.SmoothTransformation)

        # Set background to a soft, pleasing color matching the theme
        # Using a beige color similar to old paper
        splash_bg_color = QColor("#F5F5DC") # Beige color
        
        # Create a new pixmap with the desired background color
        # This prevents the splash screen from having a transparent background if the logo does
        # Make the background slightly larger than the logo to accommodate text
        bg_width = max(splash_pix.width() + 60, 400) # Ensure minimum width
        bg_height = splash_pix.height() + 100
        bg_pixmap = QPixmap(bg_width, bg_height)
        bg_pixmap.fill(splash_bg_color)
        
        # Draw the logo onto the colored background
        painter = QPainter(bg_pixmap)
        # Center the logo pixmap on the background
        x = (bg_width - splash_pix.width()) / 2
        y = 30 # Top margin
        painter.drawPixmap(int(x), int(y), splash_pix)

        # Add loading text below the logo
        font = QFont("Arial", 12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#5D4037")) # A dark brown color for text
        
        # The text to display
        loading_text = "جاري تهيئة المصحف..."
        
        # Get text dimensions to center it
        fm = painter.fontMetrics()
        
        # Position the text below the logo
        text_x = (bg_width - fm.horizontalAdvance(loading_text)) / 2
        text_y = y + splash_pix.height() + 30 # 30 pixels below the logo
        
        painter.drawText(int(text_x), int(text_y), loading_text)

        # Add a simple progress bar outline at the bottom
        progress_bar_rect = QRectF(x, text_y + 15, splash_pix.width(), 6)
        painter.setPen(QPen(QColor("#A1887F"), 2)) # Border color for progress bar
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(progress_bar_rect, 4, 4)
        
        painter.end()

        # Create a QSplashScreen with the new sized pixmap
        splash = QSplashScreen(bg_pixmap, Qt.FramelessWindowHint)
        splash.setEnabled(False) # Don't process mouse events
        splash.setWindowFlags(Qt.FramelessWindowHint) # Removed WindowStaysOnTopHint to allow background work
        
        splash.show()
        app.processEvents()

        # --- NEW: Close PyInstaller Bootloader Splash immediately to show ours ---
        try:
            import pyi_splash  # type: ignore
            if pyi_splash.is_alive():
                pyi_splash.close()
                print("Closed PyInstaller splash screen.")
        except ImportError:
            pass
            
        main(app, splash)
        
    except Exception as e:
        print(f"FATAL ERROR: An unhandled exception occurred during application startup or execution:")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {e}")
        print("Traceback:")
        traceback.print_exc()
        sys.exit(1)