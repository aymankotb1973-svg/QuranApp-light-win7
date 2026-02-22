# -*- coding: utf-8 -*-
"""
ui_builder.py - Builds the user interface for the Quran Tasmee App.
"""

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox, QComboBox, QStyle,
    QTextEdit, QWidget, QSlider, QCheckBox, QLineEdit, QSizePolicy, QTabWidget,
    QGroupBox, QFormLayout, QLayout, QScrollArea, QFrame, QDoubleSpinBox, QGridLayout
)
from PyQt5.QtGui import QFont, QPixmap, QIcon
from PyQt5.QtCore import Qt, QTimer
from utils import resource_path

# --- NEW: CollapsibleBox Class for Sidebar Architecture ---
from PyQt5.QtWidgets import QToolButton
class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=False)
        self.toggle_button.setStyleSheet("""
            QToolButton {
                border: none;
                background-color: #ECEFF1;
                text-align: left;
                padding: 8px;
                font-weight: bold;
                color: #455A64;
                border-radius: 4px;
            }
            QToolButton:hover { background-color: #CFD8DC; }
            QToolButton:checked { background-color: #B0BEC5; color: #263238; }
        """)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.LeftArrow)
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.clicked.connect(self.on_pressed)

        self.content_area = QWidget()
        self.content_area.setVisible(False)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 5, 0, 5)
        self.content_layout.setSpacing(5)

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

class UiBuilder:
    def __init__(self, main_window):
        self.main_window = main_window
        self.font_family = main_window.font_family

    def build_controls(self):
        """Builds all UI controls and layouts for the main window."""
        # The main layout for the entire window
        self.main_window.main_layout = QVBoxLayout(self.main_window)
        self.main_window.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_window.main_layout.setSpacing(6)

        # --- Top Command Bar ---
        self.main_window.top_bar_widget = QWidget()
        top_bar_widget = self.main_window.top_bar_widget
        self.main_window.top_bar_widget.setObjectName("topBar")
        stylesheet = f"""
            QWidget#topBar {{
                background-color: #ECEFF1;
                border-bottom: 1px solid #B0BEC5;
            }}
            QGroupBox {{
                font-family: "{self.font_family}";
                font-size: 10pt; /* Uniform GroupBox title size */
                font-weight: bold;
                color: #37474F;
                border: 1px solid #90A4AE;
                border-radius: 4px;
                margin-top: 2px; /* Reduced margin */
                padding-top: 8px; /* Reduced padding */
                padding-bottom: 2px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px; /* Reduced padding */
                background-color: #ECEFF1;
                color: #546E7A;
            }}
            QLabel, QLineEdit, QComboBox, QSpinBox, QPushButton {{
                font-family: "{self.font_family}";
                font-size: 11pt; /* UNIFORM FONT SIZE */
                color: #455A64;
                font-weight: bold; /* Make all text bold for consistency */
            }}
            QLineEdit, QComboBox, QSpinBox, QPushButton {{
                padding: 1px 3px; /* Reduced padding */
                border: 1px solid #B0BEC5;
                border-radius: 3px;
                background-color: white;
            }}
            QPushButton {{ 
                background-color: #e0e0e0; 
                padding: 3px 8px;
            }}
            QLineEdit {{ color: #0D47A1; }}
            QComboBox {{ color: #1A237E; }}
            QSpinBox {{ color: #0D47A1; }}
        """
        top_bar_widget.setStyleSheet(stylesheet)
        top_bar_layout = QHBoxLayout(top_bar_widget)
        top_bar_layout.setContentsMargins(4, 2, 4, 2) # Reduced margins
        top_bar_layout.setSpacing(8) # Reduced spacing

        # --- NEW: Add Logo --- (Moved to Header in quran_tasmee.py)
        # logo_label = QLabel()
        # pixmap = QPixmap(resource_path("assets/logo.png"))
        # logo_label.setPixmap(pixmap.scaledToHeight(55, Qt.SmoothTransformation))
        # top_bar_layout.addWidget(logo_label)
        # top_bar_layout.addSpacing(15)

        # -- Group 1: Tasmee Information --
        self.main_window.grp_tasmee_info = QGroupBox(self.main_window.tr("review_tab"))
        tasmee_info_group = self.main_window.grp_tasmee_info
        tasmee_info_layout = QHBoxLayout(tasmee_info_group)
        tasmee_info_layout.setSpacing(8)
        tasmee_info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.main_window.repetition_status_label = QLabel("")
        self.main_window.repetition_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_window.repetition_status_label.setMinimumWidth(140)
        self.main_window.repetition_status_label.setStyleSheet("color: #D35400;")
        tasmee_info_layout.addWidget(self.main_window.repetition_status_label)
        self.main_window.recitation_duration_label = QLabel("00:00:00")
        self.main_window.recitation_duration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_window.recitation_duration_label.setStyleSheet("color: #2980B9;")
        tasmee_info_layout.addWidget(self.main_window.recitation_duration_label)

        # -- NEW: Prayer Times Group --
        self.main_window.grp_prayer_times = QGroupBox(self.main_window.tr("prayer_times_group"))
        prayer_group = self.main_window.grp_prayer_times
        prayer_layout = QHBoxLayout(prayer_group)
        prayer_layout.setSpacing(10)
        prayer_layout.setContentsMargins(5, 5, 5, 5)

        # Clock Label
        self.main_window.clock_label = QLabel("00:00:00")
        self.main_window.clock_label.setStyleSheet("color: #2C3E50; font-size: 14px; font-weight: bold; font-family: Arial;")
        
        # Next Prayer Label
        self.main_window.next_prayer_label = QLabel(self.main_window.tr("next_prayer_lbl") + " --")
        self.main_window.next_prayer_label.setStyleSheet("color: #27AE60; font-weight: bold;")
        
        # Countdown Label
        self.main_window.prayer_countdown_label = QLabel("(-00:00)")
        self.main_window.prayer_countdown_label.setStyleSheet("color: #C0392B; font-weight: bold;")

        # Update Location Button
        self.main_window.btn_update_location = QPushButton("📍")
        self.main_window.btn_update_location.setToolTip("تحديث الموقع تلقائياً (GPS)")
        self.main_window.btn_update_location.setFixedWidth(30)
        self.main_window.btn_update_location.clicked.connect(self.main_window.refresh_location)

        # prayer_layout.addWidget(self.main_window.clock_label) # Moved to Header
        prayer_layout.addWidget(self.main_window.next_prayer_label)
        prayer_layout.addWidget(self.main_window.prayer_countdown_label)
        prayer_layout.addWidget(self.main_window.btn_update_location)
        
        # Connect update signal
        self.main_window.update_clock_signal.connect(lambda t, n, r: (
            self.main_window.clock_label.setText(t),
            self.main_window.next_prayer_label.setText(f"{self.main_window.tr('next_prayer_lbl')} {n}"),
            self.main_window.prayer_countdown_label.setText(f"({r})")
        ))

        # -- Group 2: Range Information --
        self.main_window.grp_range_info = QGroupBox(self.main_window.tr("range_info_group"))
        range_info_group = self.main_window.grp_range_info
        range_info_layout = QHBoxLayout(range_info_group)
        range_info_layout.setSpacing(5)
        range_info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter) # Align items vertically

        # --- Create All Labels ---
        self.main_window.selected_ayah_count_label = QLabel("0")
        self.main_window.duration_label = QLabel("--:--")
        self.main_window.repetition_label = QLabel("-/-")
        self.main_window.lbl_count_text = QLabel(self.main_window.tr("count_lbl"))
        self.main_window.lbl_duration_text = QLabel(self.main_window.tr("duration_lbl"))
        self.main_window.lbl_repetition_text = QLabel(self.main_window.tr("repetition_lbl"))

        # --- Style All Labels ---
        # The uniform font size is now handled by the main stylesheet for #topBar
        
        # Apply only color styles, as font size and weight are now global
        self.main_window.selected_ayah_count_label.setStyleSheet("color: #2980B9;")
        self.main_window.duration_label.setStyleSheet("color: #27AE60;")
        self.main_window.repetition_label.setStyleSheet("color: #8E44AD;")

        # Connect signals to slots
        self.main_window.update_ayah_count_signal.connect(
            lambda text, tooltip: (
                self.main_window.selected_ayah_count_label.setText(text),
                self.main_window.selected_ayah_count_label.setToolTip(tooltip)
            )
        )
        self.main_window.update_duration_signal.connect(
            lambda text, tooltip: (
                self.main_window.duration_label.setText(text),
                self.main_window.duration_label.setToolTip(tooltip)
            )
        )
        self.main_window.update_repetition_signal.connect(
            lambda text, tooltip: (
                self.main_window.repetition_label.setText(text),
                self.main_window.repetition_label.setToolTip(tooltip)
            )
        )

        # --- Add Styled Widgets to Layout ---
        range_info_layout.addWidget(self.main_window.lbl_count_text)
        range_info_layout.addWidget(self.main_window.selected_ayah_count_label)
        range_info_layout.addSpacing(10)
        range_info_layout.addWidget(self.main_window.lbl_duration_text)
        range_info_layout.addWidget(self.main_window.duration_label)
        range_info_layout.addSpacing(10)
        range_info_layout.addWidget(self.main_window.lbl_repetition_text)
        range_info_layout.addWidget(self.main_window.repetition_label)
        
        # -- Group 3: Navigation --
        self.main_window.grp_nav = QGroupBox(self.main_window.tr("nav_group"))
        nav_group = self.main_window.grp_nav
        nav_layout = QHBoxLayout(nav_group)
        nav_layout.setSpacing(5)
        self.main_window.lbl_page_nav = QLabel(self.main_window.tr("page_lbl"))
        nav_layout.addWidget(self.main_window.lbl_page_nav)
        self.main_window.page_input = QLineEdit(str(self.main_window.current_page))
        self.main_window.page_input.setFixedWidth(50)
        self.main_window.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_window.page_input.returnPressed.connect(self.main_window.on_page_input_enter)
        self.main_window.page_input.textChanged.connect(self.main_window.on_page_input_changed)
        nav_layout.addWidget(self.main_window.page_input)
        nav_layout.addSpacing(10)
        self.main_window.lbl_sura_nav = QLabel(self.main_window.tr("sura_lbl"))
        nav_layout.addWidget(self.main_window.lbl_sura_nav)
        self.main_window.combo_sura = QComboBox()
        self.main_window.combo_sura.setMinimumWidth(150)
        sorted_suras_nav = sorted(self.main_window.data_manager.sura_pages.items(), key=lambda item: item[1])
        for sura_no, page in sorted_suras_nav:
            sura_name = self.main_window.data_manager.get_sura_name(sura_no)
            self.main_window.combo_sura.addItem(sura_name, sura_no)
        self.main_window.combo_sura.currentIndexChanged.connect(self.main_window.on_sura_combo_changed)
        nav_layout.addWidget(self.main_window.combo_sura)
        nav_layout.addSpacing(10)
        self.main_window.lbl_juz_nav = QLabel(self.main_window.tr("juz_lbl"))
        nav_layout.addWidget(self.main_window.lbl_juz_nav)
        self.main_window.juz_input = QLineEdit()
        self.main_window.juz_input.setFixedWidth(50)
        self.main_window.juz_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_window.juz_input.returnPressed.connect(self.main_window.on_juz_input_enter)
        nav_layout.addWidget(self.main_window.juz_input)

        top_bar_layout.addWidget(tasmee_info_group, 1)
        top_bar_layout.addWidget(prayer_group) # Add Prayer Group here
        top_bar_layout.addWidget(range_info_group)
        top_bar_layout.addWidget(nav_group)

        # Add the toggle button for the side panel at the far end
        self.main_window.btn_toggle_rec_panel = QPushButton()
        self.main_window.btn_toggle_rec_panel.setIcon(QIcon(resource_path("assets/chevron.png")))
        self.main_window.btn_toggle_rec_panel.setToolTip("إخفاء/إظهار لوحة التحكم")
        self.main_window.btn_toggle_rec_panel.clicked.connect(self.main_window.toggle_right_panel)
        self.main_window.btn_toggle_rec_panel.setFixedWidth(40) # Make it a small, square-ish button
        # self.main_window.btn_toggle_rec_panel.setStyleSheet("font-size: 16pt; font-weight: bold;") # REMOVED for uniform style
        top_bar_layout.addWidget(self.main_window.btn_toggle_rec_panel)

        # --- Right Panel with Tabs ---
        self.main_window.right_panel = QTabWidget()
        self.main_window.right_panel.setMinimumWidth(330)
        self.main_window.right_panel.setMaximumWidth(360)

        # --- NEW: Tab 0: Plans & Tasks (الخطط والمهام) ---
        plans_tab = QWidget()
        plans_tab_layout = QVBoxLayout(plans_tab)
        plans_tab_layout.setContentsMargins(5, 5, 5, 5)
        plans_tab_layout.setSpacing(10)

        # 1. Top Section: Active Tasks (مهمتي اليومية) - Always Open
        self.main_window.daily_tasks_box = CollapsibleBox(self.main_window.tr("daily_tasks_title"))
        self.main_window.daily_tasks_box.toggle_button.setChecked(True)
        self.main_window.daily_tasks_box.on_pressed(True) # Force open
        
        # Container for Task Cards
        self.main_window.daily_tasks_container = QWidget()
        self.main_window.daily_tasks_layout = QVBoxLayout(self.main_window.daily_tasks_container)
        self.main_window.daily_tasks_layout.setContentsMargins(0, 0, 0, 0)
        self.main_window.daily_tasks_layout.setAlignment(Qt.AlignTop)
        
        self.main_window.daily_tasks_box.set_content(self.main_window.daily_tasks_container)
        plans_tab_layout.addWidget(self.main_window.daily_tasks_box)

        # 2. Bottom Section: Plan Management - Closed by Default
        self.main_window.plan_mgmt_box = CollapsibleBox(self.main_window.tr("plan_management"))
        
        mgmt_content = QWidget()
        mgmt_layout = QVBoxLayout(mgmt_content)
        
        self.main_window.btn_add_plan = QPushButton(self.main_window.tr("add_new_plan"))
        self.main_window.btn_add_plan.setStyleSheet("background-color: #2ECC71; color: white; font-weight: bold; padding: 8px;")
        self.main_window.btn_add_plan.clicked.connect(self.main_window.add_new_plan_dialog)
        mgmt_layout.addWidget(self.main_window.btn_add_plan)

        self.main_window.plans_list_layout = QVBoxLayout() # To hold list of plans for editing
        mgmt_layout.addLayout(self.main_window.plans_list_layout)
        
        self.main_window.plan_mgmt_box.set_content(mgmt_content)
        plans_tab_layout.addWidget(self.main_window.plan_mgmt_box)
        
        plans_tab_layout.addStretch() # Push everything up
        self.main_window.right_panel.addTab(plans_tab, self.main_window.tr("plans_tab"))

        # -- Tab 2: Settings --
        settings_tab = QWidget()
        settings_tab_layout = QVBoxLayout(settings_tab)
        settings_tab_layout.setContentsMargins(0, 0, 0, 0)
        
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.NoFrame)
        
        settings_content = QWidget()
        settings_layout = QVBoxLayout(settings_content)
        settings_layout.setContentsMargins(10, 10, 10, 10)

        # --- 1. Help Button (Moved to Top) ---
        self.main_window.help_button = QPushButton(self.main_window.tr("user_guide"))
        self.main_window.help_button.setCursor(Qt.PointingHandCursor)
        self.main_window.help_button.setStyleSheet("background-color: #E0F2F1; color: #00695C; font-weight: bold; font-size: 14px; padding: 10px; border: 1px solid #4DB6AC; border-radius: 5px;")
        self.main_window.help_button.clicked.connect(self.main_window.show_help_dialog)
        settings_layout.addWidget(self.main_window.help_button)

        # --- 2. General Settings Group (Language) ---
        self.main_window.grp_general_settings = QGroupBox(self.main_window.tr("general_settings"))
        general_group = self.main_window.grp_general_settings
        general_layout = QFormLayout(general_group)
        
        self.main_window.combo_language = QComboBox()
        self.main_window.combo_language.addItem(self.main_window.tr("arabic"), "ar")
        self.main_window.combo_language.addItem(self.main_window.tr("english"), "en")
        self.main_window.combo_language.currentIndexChanged.connect(self.main_window.on_language_changed)
        self.main_window.lbl_interface_lang = QLabel(self.main_window.tr("interface_language"))
        general_layout.addRow(self.main_window.lbl_interface_lang, self.main_window.combo_language)
        settings_layout.addWidget(general_group)

        # --- NEW: User Management Group ---
        self.main_window.grp_user_mgmt = QGroupBox(self.main_window.tr("user_management"))
        user_mgmt_group = self.main_window.grp_user_mgmt
        user_mgmt_layout = QVBoxLayout(user_mgmt_group)
        
        self.main_window.btn_switch_user = QPushButton(self.main_window.tr("switch_user"))
        self.main_window.btn_switch_user.setToolTip(self.main_window.tr("switch_user_tooltip"))
        self.main_window.btn_switch_user.setStyleSheet("background-color: #e9f5ff; border: 1px solid #3498db; font-weight: bold;")
        user_mgmt_layout.addWidget(self.main_window.btn_switch_user)
        
        settings_layout.addWidget(user_mgmt_group)
        
        # --- NEW: Group for Display Settings ---
        self.main_window.grp_display_settings = QGroupBox(self.main_window.tr("display_font_settings"))
        display_settings_group = self.main_window.grp_display_settings
        display_settings_layout = QVBoxLayout(display_settings_group)
        
        self.main_window.lbl_font_setting = QLabel(self.main_window.tr("font"))
        display_settings_layout.addWidget(self.main_window.lbl_font_setting)
        self.main_window.btn_zoom_in = QPushButton(self.main_window.tr("zoom_in"))
        self.main_window.btn_zoom_in.clicked.connect(self.main_window.zoom_in)
        display_settings_layout.addWidget(self.main_window.btn_zoom_in)
        self.main_window.btn_zoom_out = QPushButton(self.main_window.tr("zoom_out"))
        self.main_window.btn_zoom_out.clicked.connect(self.main_window.zoom_out)
        display_settings_layout.addWidget(self.main_window.btn_zoom_out)
        self.main_window.btn_zoom_reset = QPushButton(self.main_window.tr("reset"))
        self.main_window.btn_zoom_reset.clicked.connect(self.main_window.zoom_reset)
        display_settings_layout.addWidget(self.main_window.btn_zoom_reset)

        self.main_window.btn_change_bg = QPushButton(self.main_window.tr("mushaf_bg_color"))
        self.main_window.btn_change_bg.setToolTip(self.main_window.tr("mushaf_bg_color_tooltip"))
        self.main_window.btn_change_bg.clicked.connect(self.main_window.change_bg_color)
        display_settings_layout.addWidget(self.main_window.btn_change_bg)
        
        self.main_window.btn_change_text_color = QPushButton(self.main_window.tr("quran_text_color"))
        self.main_window.btn_change_text_color.setToolTip(self.main_window.tr("quran_text_color_tooltip"))
        self.main_window.btn_change_text_color.clicked.connect(self.main_window.change_quran_text_color)
        display_settings_layout.addWidget(self.main_window.btn_change_text_color)

        # NEW: Border Image Selection
        self.main_window.btn_select_border_image = QPushButton(self.main_window.tr("border_image"))
        self.main_window.btn_select_border_image.setToolTip(self.main_window.tr("border_image_tooltip"))
        self.main_window.btn_select_border_image.clicked.connect(self.main_window.select_border_image)
        display_settings_layout.addWidget(self.main_window.btn_select_border_image)

        self.main_window.lbl_current_border_image = QLabel(self.main_window.tr("current_border", self.main_window.tr("no_border"))) # Will be updated dynamically
        self.main_window.lbl_current_border_image.setWordWrap(True)
        display_settings_layout.addWidget(self.main_window.lbl_current_border_image)

        self.main_window.btn_change_review_color = QPushButton(self.main_window.tr("review_text_color"))
        self.main_window.btn_change_review_color.setToolTip(self.main_window.tr("review_text_color_tooltip"))
        self.main_window.btn_change_review_color.clicked.connect(self.main_window.change_review_text_color)
        display_settings_layout.addWidget(self.main_window.btn_change_review_color)

        # --- NEW: Highlight Color Selection ---
        self.main_window.combo_highlight_color = QComboBox()
        colors = [
            (self.main_window.tr("yellow_default"), "yellow"), 
            (self.main_window.tr("green"), "green"), 
            (self.main_window.tr("blue"), "blue"), 
            (self.main_window.tr("red"), "red"), 
            (self.main_window.tr("orange"), "orange"), 
            (self.main_window.tr("purple"), "purple")
        ]
        for name, key in colors:
            self.main_window.combo_highlight_color.addItem(name, key)
        self.main_window.combo_highlight_color.currentIndexChanged.connect(self.main_window.on_highlight_color_changed)
        self.main_window.lbl_highlight_color = QLabel(self.main_window.tr("highlight_color"))
        display_settings_layout.addWidget(self.main_window.lbl_highlight_color)
        display_settings_layout.addWidget(self.main_window.combo_highlight_color)

        self.main_window.btn_change_quran_font = QPushButton(self.main_window.tr("change_quran_font"))
        self.main_window.btn_change_quran_font.clicked.connect(self.main_window.on_change_font_settings)
        display_settings_layout.addWidget(self.main_window.btn_change_quran_font)

        self.main_window.btn_toggle_aya_markers = QPushButton(self.main_window.tr("hide_ayah_markers"))
        self.main_window.btn_toggle_aya_markers.clicked.connect(self.main_window.toggle_aya_markers)
        display_settings_layout.addWidget(self.main_window.btn_toggle_aya_markers)
        
        self.main_window.check_justify_text = QCheckBox(self.main_window.tr("enable_text_justification"))
        self.main_window.check_justify_text.setToolTip(self.main_window.tr("justify_tooltip"))
        self.main_window.check_justify_text.setChecked(self.main_window.justify_text) # Apply setting
        self.main_window.check_justify_text.stateChanged.connect(self.main_window.on_justify_text_toggled)
        display_settings_layout.addWidget(self.main_window.check_justify_text)
        
        # --- NEW: Dynamic Mode Toggle ---
        self.main_window.check_dynamic_mode = QCheckBox(self.main_window.tr("enable_dynamic_view"))
        self.main_window.check_dynamic_mode.setToolTip(self.main_window.tr("dynamic_view_tooltip"))
        self.main_window.check_dynamic_mode.setChecked(self.main_window.view_mode == "dynamic") # Apply setting
        self.main_window.check_dynamic_mode.toggled.connect(self.main_window.on_dynamic_mode_toggled)
        display_settings_layout.addWidget(self.main_window.check_dynamic_mode)
        settings_layout.addWidget(display_settings_group)
        
        # --- NEW: Prayer Times Settings Group ---
        self.main_window.grp_prayer_settings = QGroupBox(self.main_window.tr("prayer_settings_group"))
        prayer_settings_group = self.main_window.grp_prayer_settings
        prayer_settings_layout = QFormLayout(prayer_settings_group)

        # Calculation Method
        self.main_window.combo_calc_method = QComboBox()
        # Add methods (English keys, Translated display)
        methods = [
            ("egypt", self.main_window.tr("calc_method_egypt")),
            ("makkah", self.main_window.tr("calc_method_makkah")),
            ("karachi", self.main_window.tr("calc_method_karachi")),
            ("isna", self.main_window.tr("calc_method_isna")),
            ("mwl", self.main_window.tr("calc_method_mwl"))
        ]
        for key, name in methods:
            self.main_window.combo_calc_method.addItem(name, key)
        
        # Load saved method
        saved_method = self.main_window.settings.get("prayer_calc_method", "egypt")
        index = self.main_window.combo_calc_method.findData(saved_method)
        if index >= 0:
            self.main_window.combo_calc_method.setCurrentIndex(index)
        
        self.main_window.combo_calc_method.currentIndexChanged.connect(self.main_window.on_calc_method_changed)
        self.main_window.lbl_calc_method = QLabel(self.main_window.tr("calc_method_lbl"))
        prayer_settings_layout.addRow(self.main_window.lbl_calc_method, self.main_window.combo_calc_method)

        # Time Offset (DST/Manual)
        self.main_window.spin_time_offset = QSpinBox()
        self.main_window.spin_time_offset.setRange(-120, 120) # +/- 2 hours
        self.main_window.spin_time_offset.setValue(self.main_window.settings.get("prayer_time_offset", 0))
        self.main_window.spin_time_offset.setSuffix(" دقيقة")
        self.main_window.spin_time_offset.setToolTip("استخدم هذا الخيار لضبط التوقيت الصيفي (مثلاً +60) أو تصحيح الفروق الدقيقة.")
        self.main_window.spin_time_offset.valueChanged.connect(self.main_window.on_time_offset_changed)
        self.main_window.lbl_time_offset = QLabel(self.main_window.tr("time_offset_lbl"))
        prayer_settings_layout.addRow(self.main_window.lbl_time_offset, self.main_window.spin_time_offset)

        # --- NEW: Manual Coordinates Inputs ---
        coords_layout = QHBoxLayout()
        self.main_window.spin_lat = QDoubleSpinBox()
        self.main_window.spin_lat.setRange(-90.0, 90.0)
        self.main_window.spin_lat.setDecimals(5)
        self.main_window.spin_lat.setValue(float(self.main_window.settings.get("latitude", 30.0444)))
        self.main_window.spin_lat.valueChanged.connect(self.main_window.on_location_manual_changed)
        
        self.main_window.spin_lng = QDoubleSpinBox()
        self.main_window.spin_lng.setRange(-180.0, 180.0)
        self.main_window.spin_lng.setDecimals(5)
        self.main_window.spin_lng.setValue(float(self.main_window.settings.get("longitude", 31.2357)))
        self.main_window.spin_lng.valueChanged.connect(self.main_window.on_location_manual_changed)
        
        self.main_window.lbl_lat = QLabel(self.main_window.tr("lat_lbl"))
        coords_layout.addWidget(self.main_window.lbl_lat)
        coords_layout.addWidget(self.main_window.spin_lat)
        self.main_window.lbl_lng = QLabel(self.main_window.tr("lng_lbl"))
        coords_layout.addWidget(self.main_window.lbl_lng)
        coords_layout.addWidget(self.main_window.spin_lng)
        
        self.main_window.lbl_coords_manual = QLabel(self.main_window.tr("coords_manual_lbl"))
        prayer_settings_layout.addRow(self.main_window.lbl_coords_manual, coords_layout)

        # --- NEW: Manual Prayer Adjustments ---
        self.main_window.grp_manual_adj = QGroupBox("تعديل الدقائق يدوياً لكل صلاة (+/-)")
        adj_group = self.main_window.grp_manual_adj
        adj_layout = QGridLayout(adj_group)
        
        self.main_window.spin_adj_fajr = QSpinBox()
        self.main_window.spin_adj_sunrise = QSpinBox()
        self.main_window.spin_adj_dhuhr = QSpinBox()
        self.main_window.spin_adj_asr = QSpinBox()
        self.main_window.spin_adj_maghrib = QSpinBox()
        self.main_window.spin_adj_isha = QSpinBox()
        
        self.main_window.lbl_adj_fajr = QLabel(self.main_window.tr("prayer_fajr"))
        self.main_window.lbl_adj_sunrise = QLabel(self.main_window.tr("prayer_sunrise"))
        self.main_window.lbl_adj_dhuhr = QLabel(self.main_window.tr("prayer_dhuhr"))
        self.main_window.lbl_adj_asr = QLabel(self.main_window.tr("prayer_asr"))
        self.main_window.lbl_adj_maghrib = QLabel(self.main_window.tr("prayer_maghrib"))
        self.main_window.lbl_adj_isha = QLabel(self.main_window.tr("prayer_isha"))

        prayers_adj = [
            (self.main_window.lbl_adj_fajr, self.main_window.spin_adj_fajr, "adj_fajr"),
            (self.main_window.lbl_adj_sunrise, self.main_window.spin_adj_sunrise, "adj_sunrise"),
            (self.main_window.lbl_adj_dhuhr, self.main_window.spin_adj_dhuhr, "adj_dhuhr"),
            (self.main_window.lbl_adj_asr, self.main_window.spin_adj_asr, "adj_asr"),
            (self.main_window.lbl_adj_maghrib, self.main_window.spin_adj_maghrib, "adj_maghrib"),
            (self.main_window.lbl_adj_isha, self.main_window.spin_adj_isha, "adj_isha")
        ]
        
        for i, (label_widget, spin, key) in enumerate(prayers_adj):
            spin.setRange(-60, 60)
            spin.setValue(self.main_window.settings.get(key, 0))
            spin.valueChanged.connect(self.main_window.on_prayer_adj_changed)
            adj_layout.addWidget(label_widget, 0, i)
            adj_layout.addWidget(spin, 1, i)
            
        prayer_settings_layout.addRow(adj_group)

        # Azan Files Selection will be populated dynamically in quran_tasmee.py to keep logic clean
        # We create a layout container for it here
        self.main_window.azan_files_layout = QVBoxLayout()
        prayer_settings_layout.addRow(self.main_window.azan_files_layout)

        settings_layout.addWidget(prayer_settings_group)
        
        # --- NEW: Desktop Widget Settings Group ---
        self.main_window.grp_widget_settings = QGroupBox(self.main_window.tr("widget_settings_group"))
        widget_settings_group = self.main_window.grp_widget_settings
        widget_settings_layout = QFormLayout(widget_settings_group)

        # Show/Hide
        self.main_window.chk_show_widget = QCheckBox(self.main_window.tr("chk_show_widget"))
        self.main_window.chk_show_widget.setChecked(self.main_window.settings.get("show_prayer_widget_on_startup", True))
        self.main_window.chk_show_widget.toggled.connect(self.main_window.on_toggle_widget_visibility)
        widget_settings_layout.addRow(self.main_window.chk_show_widget)

        # Always on Top
        self.main_window.chk_widget_on_top = QCheckBox(self.main_window.tr("chk_widget_on_top"))
        self.main_window.chk_widget_on_top.setChecked(self.main_window.settings.get("widget_on_top", True))
        self.main_window.chk_widget_on_top.toggled.connect(self.main_window.on_toggle_widget_on_top)
        widget_settings_layout.addRow(self.main_window.chk_widget_on_top)

        # Colors Row
        colors_layout = QHBoxLayout()
        self.main_window.btn_widget_bg_color = QPushButton(self.main_window.tr("btn_widget_bg_color"))
        self.main_window.btn_widget_bg_color.clicked.connect(self.main_window.pick_widget_bg_color)
        self.main_window.btn_widget_text_color = QPushButton(self.main_window.tr("btn_widget_text_color"))
        self.main_window.btn_widget_text_color.clicked.connect(self.main_window.pick_widget_text_color)
        colors_layout.addWidget(self.main_window.btn_widget_bg_color)
        colors_layout.addWidget(self.main_window.btn_widget_text_color)
        self.main_window.lbl_widget_colors = QLabel(self.main_window.tr("lbl_widget_colors"))
        widget_settings_layout.addRow(self.main_window.lbl_widget_colors, colors_layout)

        # Font Scale
        self.main_window.spin_widget_scale = QDoubleSpinBox()
        self.main_window.spin_widget_scale.setRange(0.5, 3.0)
        self.main_window.spin_widget_scale.setSingleStep(0.1)
        self.main_window.spin_widget_scale.setValue(float(self.main_window.settings.get("widget_font_scale", 1.0)))
        self.main_window.spin_widget_scale.valueChanged.connect(self.main_window.on_widget_scale_changed)
        self.main_window.lbl_widget_font_size = QLabel(self.main_window.tr("lbl_widget_font_size"))
        widget_settings_layout.addRow(self.main_window.lbl_widget_font_size, self.main_window.spin_widget_scale)

        # Opacity Slider
        self.main_window.slider_widget_opacity = QSlider(Qt.Horizontal)
        self.main_window.slider_widget_opacity.setRange(0, 255)
        self.main_window.slider_widget_opacity.setValue(200)
        self.main_window.slider_widget_opacity.valueChanged.connect(self.main_window.on_widget_opacity_changed)
        self.main_window.lbl_widget_opacity = QLabel(self.main_window.tr("lbl_widget_opacity"))
        widget_settings_layout.addRow(self.main_window.lbl_widget_opacity, self.main_window.slider_widget_opacity)

        settings_layout.addWidget(widget_settings_group)
        # ----------------------------------------

        settings_layout.addStretch()
        
        settings_scroll.setWidget(settings_content)
        settings_tab_layout.addWidget(settings_scroll)
        self.main_window.right_panel.addTab(settings_tab, self.main_window.tr("settings_tab"))

        # -- Tab 3: Playlist --
        playlist_tab = QWidget()
        playlist_tab_layout = QVBoxLayout(playlist_tab)
        playlist_tab_layout.setContentsMargins(0, 0, 0, 0)
        
        playlist_scroll = QScrollArea()
        playlist_scroll.setWidgetResizable(True)
        playlist_scroll.setFrameShape(QFrame.NoFrame)
        
        playlist_content = QWidget()
        playlist_layout = QVBoxLayout(playlist_content)
        playlist_layout.setContentsMargins(10, 10, 10, 10)

        self.main_window.grp_select_reciter = QGroupBox(self.main_window.tr("select_reciter_group"))
        folder_group = self.main_window.grp_select_reciter
        folder_layout = QFormLayout(folder_group)
        self.main_window.btn_select_main_folder = QPushButton(self.main_window.tr("select_folder_btn"))
        self.main_window.btn_select_main_folder.clicked.connect(self.main_window.select_main_audio_folder)
        self.main_window.combo_reciters = QComboBox()
        self.main_window.combo_reciters.setEnabled(False)
        self.main_window.combo_reciters.currentIndexChanged.connect(self.main_window.on_reciter_changed)
        folder_layout.addRow(self.main_window.btn_select_main_folder)
        self.main_window.lbl_select_sheikh = QLabel(self.main_window.tr("select_sheikh_lbl"))
        folder_layout.addRow(self.main_window.lbl_select_sheikh, self.main_window.combo_reciters)
        
        self.main_window.grp_select_range = QGroupBox(self.main_window.tr("select_range_group"))
        self.main_window.range_group = self.main_window.grp_select_range # Alias for compatibility
        range_layout = QVBoxLayout(self.main_window.range_group)
        
        start_file_layout = QHBoxLayout()
        self.main_window.start_file_label = QLineEdit()
        self.main_window.start_file_label.setReadOnly(True)
        self.main_window.btn_select_start_file = QPushButton(self.main_window.tr("from_btn"))
        self.main_window.btn_select_start_file.setFixedWidth(50)
        self.main_window.btn_select_start_file.clicked.connect(self.main_window.select_start_file)
        start_file_layout.addWidget(self.main_window.start_file_label)
        start_file_layout.addWidget(self.main_window.btn_select_start_file)
        
        end_file_layout = QHBoxLayout()
        self.main_window.end_file_label = QLineEdit()
        self.main_window.end_file_label.setReadOnly(True)
        self.main_window.btn_select_end_file = QPushButton(self.main_window.tr("to_btn"))
        self.main_window.btn_select_end_file.setFixedWidth(50)
        self.main_window.btn_select_end_file.clicked.connect(self.main_window.select_end_file)
        end_file_layout.addWidget(self.main_window.end_file_label)
        end_file_layout.addWidget(self.main_window.btn_select_end_file)

        self.main_window.btn_update_files = QPushButton(self.main_window.tr("update_playlist_btn"))
        self.main_window.btn_update_files.clicked.connect(self.main_window.update_files_list)
        
        range_layout.addLayout(start_file_layout)
        range_layout.addLayout(end_file_layout)
        range_layout.addWidget(self.main_window.btn_update_files)
        self.main_window.range_group.setEnabled(False)

        self.main_window.options_group = QGroupBox(self.main_window.tr("playback_mode_group"))
        options_layout = QVBoxLayout(self.main_window.options_group)
        self.main_window.btn_play_single = QPushButton(self.main_window.tr("play_single_btn"))
        self.main_window.btn_play_single.clicked.connect(lambda: self.main_window.prepare_and_play("SINGLE"))
        self.main_window.btn_play_single.setStyleSheet("background-color: #27ae60; color: white;")
        self.main_window.btn_play_group = QPushButton(self.main_window.tr("play_group_btn"))
        self.main_window.btn_play_group.clicked.connect(lambda: self.main_window.prepare_and_play("GROUP"))
        self.main_window.btn_play_group.setStyleSheet("background-color: #d68910; color: white;")
        self.main_window.btn_play_complex = QPushButton(self.main_window.tr("play_complex_btn"))
        self.main_window.btn_play_complex.clicked.connect(lambda: self.main_window.prepare_and_play("COMPLEX"))
        self.main_window.btn_play_complex.setStyleSheet("background-color: #c0392b; color: white;")
        options_layout.addWidget(self.main_window.btn_play_single)
        options_layout.addWidget(self.main_window.btn_play_group)
        options_layout.addWidget(self.main_window.btn_play_complex)
        self.main_window.options_group.setEnabled(False)

        self.main_window.grp_repeat_options = QGroupBox(self.main_window.tr("repeat_options_group"))
        repeat_group = self.main_window.grp_repeat_options
        repeat_layout = QFormLayout(repeat_group)
        self.main_window.spin_single_repeat = QSpinBox()
        self.main_window.spin_single_repeat.setRange(1, 100)
        self.main_window.spin_single_repeat.setValue(3)
        self.main_window.spin_single_repeat.valueChanged.connect(lambda: self.main_window.update_session_estimate('SINGLE'))
        self.main_window.lbl_single_repeat = QLabel(self.main_window.tr("single_repeat_lbl"))
        repeat_layout.addRow(self.main_window.lbl_single_repeat, self.main_window.spin_single_repeat)

        self.main_window.spin_group_repeat = QSpinBox()
        self.main_window.spin_group_repeat.setRange(1, 100)
        self.main_window.spin_group_repeat.setValue(3)
        self.main_window.spin_group_repeat.valueChanged.connect(lambda: self.main_window.update_session_estimate('GROUP'))
        self.main_window.lbl_group_repeat = QLabel(self.main_window.tr("group_repeat_lbl"))
        repeat_layout.addRow(self.main_window.lbl_group_repeat, self.main_window.spin_group_repeat)

        self.main_window.spin_complex_individual = QSpinBox()
        self.main_window.spin_complex_individual.setRange(1, 100)
        self.main_window.spin_complex_individual.setValue(3)
        self.main_window.spin_complex_individual.valueChanged.connect(lambda: self.main_window.update_session_estimate('COMPLEX'))
        self.main_window.spin_complex_group = QSpinBox()
        self.main_window.spin_complex_group.setRange(1, 100)
        self.main_window.spin_complex_group.setValue(3)
        self.main_window.spin_complex_group.valueChanged.connect(lambda: self.main_window.update_session_estimate('COMPLEX'))
        self.main_window.spin_complex_group_size = QSpinBox()
        self.main_window.spin_complex_group_size.setRange(2, 100)
        self.main_window.spin_complex_group_size.setValue(3)
        self.main_window.spin_complex_group_size.valueChanged.connect(lambda: self.main_window.update_session_estimate('COMPLEX'))
        self.main_window.lbl_complex_single = QLabel(self.main_window.tr("complex_single_lbl"))
        repeat_layout.addRow(self.main_window.lbl_complex_single, self.main_window.spin_complex_individual)
        self.main_window.lbl_complex_group = QLabel(self.main_window.tr("complex_group_lbl"))
        repeat_layout.addRow(self.main_window.lbl_complex_group, self.main_window.spin_complex_group)
        self.main_window.lbl_complex_size = QLabel(self.main_window.tr("complex_size_lbl"))
        repeat_layout.addRow(self.main_window.lbl_complex_size, self.main_window.spin_complex_group_size)

        self.main_window.grp_audio_player = QGroupBox(self.main_window.tr("audio_player_group"))
        player_group = self.main_window.grp_audio_player
        player_layout = QVBoxLayout(player_group)
        progress_layout = QHBoxLayout()
        self.main_window.player_current_time_label = QLabel("00:00")
        self.main_window.player_progress_slider = QSlider(Qt.Horizontal)
        self.main_window.player_progress_slider.setRange(0, 1000) # لتسهيل حساب الموضع
        self.main_window.player_progress_slider.sliderMoved.connect(self.main_window.on_player_slider_moved)
        self.main_window.player_total_time_label = QLabel("00:00")
        progress_layout.addWidget(self.main_window.player_current_time_label)
        progress_layout.addWidget(self.main_window.player_progress_slider)
        progress_layout.addWidget(self.main_window.player_total_time_label)
        buttons_layout = QHBoxLayout()
        
        self.main_window.btn_player_prev = QPushButton()
        self.main_window.btn_player_prev.setIcon(QIcon(resource_path("assets/back-arrow.png")))
        self.main_window.btn_player_prev.setToolTip("السابق")
        self.main_window.btn_player_prev.clicked.connect(self.main_window.player_previous)
        
        self.main_window.btn_player_pause = QPushButton()
        # استخدام أيقونة التشغيل القياسية كبداية، وسيتم التبديل إلى pause.png عند التشغيل
        self.main_window.btn_player_pause.setIcon(self.main_window.style().standardIcon(QStyle.SP_MediaPlay))
        self.main_window.btn_player_pause.setToolTip("تشغيل")
        self.main_window.btn_player_pause.clicked.connect(self.main_window.player_toggle_pause)
        
        self.main_window.btn_player_next = QPushButton()
        self.main_window.btn_player_next.setIcon(QIcon(resource_path("assets/fast-forward-button.png")))
        self.main_window.btn_player_next.setToolTip("التالي")
        self.main_window.btn_player_next.clicked.connect(self.main_window.player_next)
        
        self.main_window.btn_player_stop = QPushButton()
        self.main_window.btn_player_stop.setIcon(QIcon(resource_path("assets/stop-button.png")))
        self.main_window.btn_player_stop.setToolTip("إيقاف")
        self.main_window.btn_player_stop.clicked.connect(self.main_window.player_stop)
        buttons_layout.addWidget(self.main_window.btn_player_prev)
        buttons_layout.addWidget(self.main_window.btn_player_pause)
        buttons_layout.addWidget(self.main_window.btn_player_next)
        buttons_layout.addWidget(self.main_window.btn_player_stop)
        speed_layout = QHBoxLayout()
        self.main_window.speed_slider = QSlider(Qt.Horizontal)
        self.main_window.speed_slider.setRange(50, 200)
        self.main_window.speed_slider.setValue(100)
        self.main_window.speed_slider.valueChanged.connect(self.main_window.on_speed_changed)
        self.main_window.speed_label = QLabel("x1.00")
        self.main_window.lbl_speed = QLabel(self.main_window.tr("speed_lbl"))
        speed_layout.addWidget(self.main_window.lbl_speed)
        speed_layout.addWidget(self.main_window.speed_slider)
        speed_layout.addWidget(self.main_window.speed_label)

        # --- NEW: Volume Control ---
        volume_layout = QHBoxLayout()
        self.main_window.volume_slider = QSlider(Qt.Horizontal)
        self.main_window.volume_slider.setRange(0, 100) # VLC volume is 0-100
        volume = self.main_window.settings.get("volume", 100)
        self.main_window.volume_slider.setValue(volume) # Apply setting
        self.main_window.volume_slider.valueChanged.connect(self.main_window.on_volume_changed)
        self.main_window.volume_label = QLabel("100%")
        self.main_window.lbl_volume = QLabel(self.main_window.tr("volume_lbl"))
        volume_layout.addWidget(self.main_window.lbl_volume)
        volume_layout.addWidget(self.main_window.volume_slider)
        volume_layout.addWidget(self.main_window.volume_label)

        player_layout.addLayout(progress_layout)
        player_layout.addLayout(buttons_layout)
        player_layout.addLayout(speed_layout)
        player_layout.addLayout(volume_layout)
        
        # --- NEW: Playback Review Mode Checkbox ---
        self.main_window.check_playback_review_mode = QCheckBox(self.main_window.tr("playback_review_mode_chk"))
        self.main_window.check_playback_review_mode.setToolTip(self.main_window.tr("playback_review_mode_tooltip"))
        self.main_window.check_playback_review_mode.stateChanged.connect(self.main_window.on_playback_review_toggled)
        player_layout.addWidget(self.main_window.check_playback_review_mode)

        playlist_layout.addWidget(player_group)
        playlist_layout.addWidget(folder_group)
        playlist_layout.addWidget(self.main_window.range_group)
        playlist_layout.addWidget(self.main_window.options_group)
        playlist_layout.addWidget(repeat_group)
        playlist_layout.addStretch() # Push everything up
        
        playlist_scroll.setWidget(playlist_content)
        playlist_tab_layout.addWidget(playlist_scroll)
        self.main_window.right_panel.addTab(playlist_tab, self.main_window.tr("playlist_tab"))
        
        # -- Tab 4: Review (New) --
        review_tab = QWidget()
        review_tab_layout = QVBoxLayout(review_tab)
        
        self.main_window.grp_visual_review = QGroupBox(self.main_window.tr("visual_review_group"))
        review_range_group = self.main_window.grp_visual_review
        review_range_layout = QFormLayout(review_range_group)
        
        self.main_window.combo_review_from_sura = QComboBox()
        self.main_window.spin_review_from_aya = QSpinBox()
        self.main_window.spin_review_from_aya.setRange(1, 286)
        
        self.main_window.combo_review_to_sura = QComboBox()
        self.main_window.spin_review_to_aya = QSpinBox()
        self.main_window.spin_review_to_aya.setRange(1, 286)

        # Populate combos
        sorted_suras = sorted(self.main_window.data_manager.sura_pages.items(), key=lambda item: item[0])
        for sura_no, _ in sorted_suras:
            sura_name = self.main_window.data_manager.get_sura_name(sura_no)
            text = f"{sura_no} - {sura_name}"
            self.main_window.combo_review_from_sura.addItem(text, sura_no)
            self.main_window.combo_review_to_sura.addItem(text, sura_no)

        # Connect signals for dynamic range update
        self.main_window.combo_review_from_sura.currentIndexChanged.connect(self.main_window.on_review_from_sura_changed)
        self.main_window.combo_review_to_sura.currentIndexChanged.connect(self.main_window.on_review_to_sura_changed)

        # Layouts
        row_from = QHBoxLayout()
        row_from.addWidget(self.main_window.combo_review_from_sura, 2)
        row_from.addWidget(self.main_window.spin_review_from_aya, 1)
        self.main_window.lbl_review_from = QLabel(self.main_window.tr("from_lbl"))
        review_range_layout.addRow(self.main_window.lbl_review_from, row_from)
        
        row_to = QHBoxLayout()
        row_to.addWidget(self.main_window.combo_review_to_sura, 2)
        row_to.addWidget(self.main_window.spin_review_to_aya, 1)
        self.main_window.lbl_review_to = QLabel(self.main_window.tr("to_lbl"))
        review_range_layout.addRow(self.main_window.lbl_review_to, row_to)
        
        review_tab_layout.addWidget(review_range_group)
        
        # Settings & Controls
        self.main_window.grp_control = QGroupBox(self.main_window.tr("control_group"))
        review_settings_group = self.main_window.grp_control
        review_settings_layout = QVBoxLayout(review_settings_group)
        
        self.main_window.spin_auto_reveal_time = QSpinBox()
        self.main_window.spin_auto_reveal_time.setRange(1, 600)
        self.main_window.spin_auto_reveal_time.setValue(self.main_window.settings.get("auto_reveal_time", 30))
        self.main_window.spin_auto_reveal_time.setSuffix(" ثانية/صفحة")
        self.main_window.spin_auto_reveal_time.valueChanged.connect(self.main_window.on_auto_reveal_time_changed)
        
        self.main_window.spin_review_repetitions = QSpinBox()
        self.main_window.spin_review_repetitions.setRange(1, 100)
        self.main_window.spin_review_repetitions.setValue(1)
        self.main_window.spin_review_repetitions.setPrefix(self.main_window.tr("repetition_prefix"))
        
        self.main_window.spin_auto_reveal_pause = QDoubleSpinBox()
        self.main_window.spin_auto_reveal_pause.setRange(0.0, 10.0)
        self.main_window.spin_auto_reveal_pause.setSingleStep(0.5)
        self.main_window.spin_auto_reveal_pause.setValue(self.main_window.settings.get("auto_reveal_pause", 1.5))
        self.main_window.spin_auto_reveal_pause.setSuffix(" ثانية")
        self.main_window.spin_auto_reveal_pause.setToolTip(self.main_window.tr("pause_tooltip"))
        
        self.main_window.lbl_reveal_speed = QLabel(self.main_window.tr("reveal_speed_lbl"))
        review_settings_layout.addWidget(self.main_window.lbl_reveal_speed)
        review_settings_layout.addWidget(self.main_window.spin_auto_reveal_time)
        review_settings_layout.addWidget(self.main_window.spin_review_repetitions)
        self.main_window.lbl_pause_at_ayah = QLabel(self.main_window.tr("pause_at_ayah_lbl"))
        review_settings_layout.addWidget(self.main_window.lbl_pause_at_ayah)
        review_settings_layout.addWidget(self.main_window.spin_auto_reveal_pause)
        
        btns_layout = QHBoxLayout()
        self.main_window.btn_auto_reveal_start = QPushButton(self.main_window.tr("start_reveal_btn"))
        self.main_window.btn_auto_reveal_start.setCursor(Qt.PointingHandCursor)
        self.main_window.btn_auto_reveal_start.clicked.connect(self.main_window.toggle_auto_reveal)
        self.main_window.btn_auto_reveal_start.setStyleSheet("background-color: #8E44AD; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        
        self.main_window.btn_auto_reveal_stop = QPushButton(self.main_window.tr("stop_btn"))
        self.main_window.btn_auto_reveal_stop.setCursor(Qt.PointingHandCursor)
        self.main_window.btn_auto_reveal_stop.clicked.connect(self.main_window.stop_auto_reveal)
        self.main_window.btn_auto_reveal_stop.setStyleSheet("background-color: #C0392B; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.main_window.btn_auto_reveal_stop.setEnabled(False)

        review_settings_layout.addSpacing(10)
        btns_layout.addWidget(self.main_window.btn_auto_reveal_start)
        btns_layout.addWidget(self.main_window.btn_auto_reveal_stop)
        review_settings_layout.addLayout(btns_layout)
        
        review_tab_layout.addWidget(review_settings_group)
        review_tab_layout.addStretch()
        
        self.main_window.right_panel.addTab(review_tab, self.main_window.tr("review_tab"))

        # --- Page Navigation Buttons (Side Buttons) ---
        self.main_window.btn_prev = QPushButton("◀")
        self.main_window.btn_prev.setFont(QFont("Arial", 20, QFont.Bold))
        self.main_window.btn_prev.setFixedSize(40, 100)
        self.main_window.btn_prev.clicked.connect(self.main_window.on_prev)

        self.main_window.btn_next = QPushButton("▶")
        self.main_window.btn_next.setFont(QFont("Arial", 20, QFont.Bold))
        self.main_window.btn_next.setFixedSize(40, 100)
        self.main_window.btn_next.clicked.connect(self.main_window.on_next)

        # --- NEW: Illuminated Style for Page Navigation Buttons ---
        button_style = """
            QPushButton {
                background-color: qradialgradient(
                    cx: 0.5, cy: 0.5, fx: 0.5, fy: 0.5, radius: 0.8,
                    stop: 0 rgba(218, 165, 32, 180), /* Goldenrod */
                    stop: 1 rgba(218, 165, 32, 80)
                );
                color: rgba(255, 255, 255, 220);
                border: 2px solid rgba(255, 215, 0, 150); /* Gold */
                border-radius: 20px;
            }
            QPushButton:hover {
                background-color: qradialgradient(
                    cx: 0.5, cy: 0.5, fx: 0.5, fy: 0.5, radius: 0.8,
                    stop: 0 rgba(238, 185, 52, 220),
                    stop: 1 rgba(238, 185, 52, 120)
                );
                border: 2px solid rgba(255, 215, 0, 200);
            }
            QPushButton:pressed {
                background-color: qradialgradient(
                    cx: 0.5, cy: 0.5, fx: 0.5, fy: 0.5, radius: 0.8,
                    stop: 0 rgba(198, 145, 12, 220),
                    stop: 1 rgba(198, 145, 12, 120)
                );
            }
        """
        self.main_window.btn_prev.setStyleSheet(button_style)
        self.main_window.btn_next.setStyleSheet(button_style)

        # --- Center Layout (View + Side Buttons) ---
        center_layout = QHBoxLayout()
        center_layout.addWidget(self.main_window.btn_next)
        center_layout.addWidget(self.main_window.view, 1)
        center_layout.addWidget(self.main_window.btn_prev)

        # --- Main Content Layout (Side Panels + Center) ---
        main_content_layout = QHBoxLayout()
        main_content_layout.addWidget(self.main_window.right_panel)
        main_content_layout.addLayout(center_layout, 1)

        # --- Assemble the final layout ---
        self.main_window.main_layout.addWidget(self.main_window.top_bar_widget)
        self.main_window.main_layout.addLayout(main_content_layout, 1)
