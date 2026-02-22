# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QTextBrowser, QComboBox, QPushButton, QTabWidget, QWidget, QTextEdit, QMessageBox)
from PyQt5.QtCore import Qt, QSettings, pyqtSignal
from PyQt5.QtGui import QFont
import threading

try:
    import arabic_reshaper
    HAS_RESHAPER = True
except ImportError:
    HAS_RESHAPER = False

class WordInfoDialog(QDialog):
    reflection_saved_signal = pyqtSignal()

    def __init__(self, info_manager, data_manager, global_word_id, font_family="Traditional Arabic", parent=None, user_manager=None):
        super().__init__(parent)
        self.reflection_saved_signal.connect(self.on_reflection_saved)
        self.info_manager = info_manager
        self.data_manager = data_manager
        self.user_manager = user_manager  # تخزين مدير المستخدمين
        self.current_global_id = global_word_id
        self.font_family = font_family
        self.last_sura_aya = None 
        
        # Helper for translation
        self.tr_func = parent.tr if parent and hasattr(parent, 'tr') else lambda k, *args: k
        
        # تهيئة متغيرات السورة والآية لاستخدامها في التدبرات
        self.current_sura = 0
        self.current_aya = 0
        
        self.setWindowTitle(self.tr_func("window_title_info"))
        self.setMinimumSize(600, 550)
        self.setLayoutDirection(Qt.RightToLeft)
        
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        
        # --- NEW: Load Font Size ---
        self.settings = QSettings("QuranApp", "WordInfoDialog")
        self.current_font_size = int(self.settings.value("content_font_size", 14))

        layout = QVBoxLayout(self)
        
        # إنشاء التبويبات
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabBar::tab { height: 35px; width: 100px; font-size: 10pt; font-weight: bold; }
            QTabWidget::pane { border: 1px solid #ccc; }
        """)
        layout.addWidget(self.tabs)
        
        # 1. تبويب المعاني
        self.tab_meaning = QWidget()
        self.tabs.addTab(self.tab_meaning, self.tr_func("tab_meaning"))
        self._setup_meaning_tab()
        
        # 2. تبويب التفاسير
        self.tab_tafsir = QWidget()
        self.tabs.addTab(self.tab_tafsir, self.tr_func("tab_tafsir"))
        self._setup_tafsir_tab()
        
        # 3. تبويب الإعراب
        self.tab_eerab = QWidget()
        self.tabs.addTab(self.tab_eerab, self.tr_func("tab_eerab"))
        self._setup_eerab_tab()
        
        # 4. تبويب الصرف
        self.tab_sarf = QWidget()
        self.tabs.addTab(self.tab_sarf, self.tr_func("tab_sarf"))
        self._setup_sarf_tab()
        
        # 5. تبويب أسباب النزول
        self.tab_nozool = QWidget()
        self.tabs.addTab(self.tab_nozool, self.tr_func("tab_nozool"))
        self._setup_nozool_tab()

        # 6. تبويب التجويد
        self.tab_tajweed = QWidget()
        self.tabs.addTab(self.tab_tajweed, self.tr_func("tab_tajweed"))
        self._setup_tajweed_tab()

        # 7. تبويب تدبراتي (الجديد)
        self.tab_reflections = QWidget()
        self.tabs.addTab(self.tab_reflections, self.tr_func("tab_reflections"))
        self._setup_reflections_tab()
        
        # --- NEW: Bottom Bar (Nav + Zoom + Close) ---
        bottom_layout = QHBoxLayout()
        
        self.btn_prev = QPushButton(self.tr_func("btn_prev_word"))
        self.btn_next = QPushButton(self.tr_func("btn_next_word"))
        
        btn_style = """
            QPushButton { 
                font-size: 10pt; padding: 6px; font-weight: bold; 
                background-color: #f0f0f0; border: 1px solid #ccc; border-radius: 5px;
            }
            QPushButton:hover { background-color: #e0e0e0; }
        """
        self.btn_prev.setStyleSheet(btn_style)
        self.btn_next.setStyleSheet(btn_style)
        
        self.btn_prev.clicked.connect(self.go_prev_word)
        self.btn_next.clicked.connect(self.go_next_word)
        
        bottom_layout.addWidget(self.btn_prev)
        bottom_layout.addWidget(self.btn_next)
        
        bottom_layout.addStretch()
        
        # Zoom Controls
        lbl_zoom = QLabel(self.tr_func("font_size"))
        btn_zoom_in = QPushButton("+")
        btn_zoom_out = QPushButton("-")
        btn_zoom_in.setFixedSize(30, 30)
        btn_zoom_out.setFixedSize(30, 30)
        btn_zoom_in.clicked.connect(self.zoom_in)
        btn_zoom_out.clicked.connect(self.zoom_out)
        
        bottom_layout.addWidget(lbl_zoom)
        bottom_layout.addWidget(btn_zoom_in)
        bottom_layout.addWidget(btn_zoom_out)
        
        bottom_layout.addStretch()
        
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # زر الإغلاق
        btn_close = QPushButton(self.tr_func("btn_close"))
        btn_close.setStyleSheet("""
            QPushButton { 
                background-color: #ffebee; color: #c62828; 
                font-size: 10pt; padding: 6px; font-weight: bold; 
                border: 1px solid #ef9a9a; border-radius: 5px;
            }
            QPushButton:hover { background-color: #ffcdd2; }
        """)
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)
        
        layout.addLayout(bottom_layout)
        
        self.load_data()
        
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

    def _fix_text(self, text):
        if not text: return ""
        if HAS_RESHAPER:
            try:
                configuration = {
                    'delete_harakat': False,
                    'support_zwj': True,
                    'shift_harakat_position': True
                }
                reshaper = arabic_reshaper.ArabicReshaper(configuration=configuration)
                return reshaper.reshape(text)
            except Exception:
                return text
        return text

    def _create_browser(self):
        tb = QTextBrowser()
        font = QFont(self.font_family, self.current_font_size) # Use dynamic size
        tb.setFont(font)
        tb.setStyleSheet(f"QTextBrowser {{ font-family: '{self.font_family}', 'Segoe UI', 'Arial'; font-size: {self.current_font_size}pt; padding: 10px; line-height: 1.4; }}")
        return tb

    def _setup_meaning_tab(self):
        layout = QVBoxLayout(self.tab_meaning)
        self.txt_meaning = self._create_browser()
        layout.addWidget(self.txt_meaning)

    def _setup_tafsir_tab(self):
        layout = QVBoxLayout(self.tab_tafsir)
        self.combo_tafsir = QComboBox()
        self.combo_tafsir.setStyleSheet("QComboBox { font-size: 11pt; padding: 4px; }")
        self.combo_tafsir.addItem("التفسير الميسر", "moyassar")
        self.combo_tafsir.addItem("تفسير السعدي", "saadi")
        self.combo_tafsir.addItem("التفسير المختصر", "mokhtasar")
        self.combo_tafsir.addItem("تفسير الطبري", "tabary")
        self.combo_tafsir.addItem("تفسير البغوي", "baghawy")
        self.combo_tafsir.addItem("تفسير ابن كثير", "katheer")
        self.combo_tafsir.currentIndexChanged.connect(self.load_tafsir)
        layout.addWidget(self.combo_tafsir)
        self.txt_tafsir = self._create_browser()
        layout.addWidget(self.txt_tafsir)

    def _setup_eerab_tab(self):
        layout = QVBoxLayout(self.tab_eerab)
        self.txt_eerab = self._create_browser()
        layout.addWidget(self.txt_eerab)

    def _setup_sarf_tab(self):
        layout = QVBoxLayout(self.tab_sarf)
        self.txt_sarf = self._create_browser()
        layout.addWidget(self.txt_sarf)

    def _setup_nozool_tab(self):
        layout = QVBoxLayout(self.tab_nozool)
        self.txt_nozool = self._create_browser()
        layout.addWidget(self.txt_nozool)

    def _setup_tajweed_tab(self):
        layout = QVBoxLayout(self.tab_tajweed)
        self.txt_tajweed = self._create_browser()
        layout.addWidget(self.txt_tajweed)

    def _setup_reflections_tab(self):
        layout = QVBoxLayout(self.tab_reflections)
        
        lbl = QLabel(self.tr_func("lbl_reflections"))
        lbl.setStyleSheet("color: #8E44AD; font-weight: bold; font-size: 11pt;")
        layout.addWidget(lbl)
        
        self.txt_reflection = QTextEdit()
        self.txt_reflection.setPlaceholderText(self.tr_func("reflection_placeholder"))
        self.txt_reflection.setStyleSheet(f"font-size: {self.current_font_size}pt; padding: 5px;")
        layout.addWidget(self.txt_reflection)
        
        btn_layout = QHBoxLayout()
        self.btn_save_reflection = QPushButton(self.tr_func("btn_save_reflection"))
        self.btn_save_reflection.setStyleSheet("background-color: #2ECC71; color: white; font-weight: bold; padding: 6px;")
        self.btn_save_reflection.clicked.connect(self.save_reflection)
        
        btn_delete = QPushButton(self.tr_func("btn_delete"))
        btn_delete.setStyleSheet("background-color: #E74C3C; color: white; padding: 6px;")
        btn_delete.clicked.connect(self.delete_reflection)
        
        btn_layout.addWidget(self.btn_save_reflection)
        btn_layout.addWidget(btn_delete)
        layout.addLayout(btn_layout)

    def load_data(self):
        db_ids = self.data_manager.get_db_ids_from_global(self.current_global_id)
        local_info = self.data_manager.global_to_local_map.get(self.current_global_id)
        
        if not db_ids or not local_info:
            self.setWindowTitle("خطأ في البيانات")
            return
            
        sura_id_db, aya_id_db, word_id_db = db_ids
        sura_local, aya_local, word_local = local_info
        
        # تحديث المتغيرات الحالية للتدبرات
        self.current_sura = sura_local
        self.current_aya = aya_local
        
        sura_name = self.data_manager.get_sura_name(sura_local)
        self.setWindowTitle(self.tr_func("window_title_details", sura_name, aya_local, word_local))
        
        # 1. المعنى
        meaning, m_title = self.info_manager.get_word_data("meaning", sura_id_db, aya_id_db, word_id_db)
        html_meaning = ""
        if m_title:
            fixed_title = self._fix_text(m_title)
            # تصغير خط العنوان
            html_meaning += f"<div style='font-family: \"Traditional Arabic\"; color: #C0392B; font-size: 18px; font-weight: bold; margin-bottom: 5px;'>{fixed_title}</div>"
        html_meaning += f"<div dir='rtl' style='color:#2c3e50;'>{meaning if meaning else self.tr_func('no_meaning')}</div>"
        self.txt_meaning.setHtml(html_meaning)
        
        # 2. الإعراب
        eerab, e_title = self.info_manager.get_word_data("eerab", sura_id_db, aya_id_db, word_id_db)
        html_eerab = ""
        if e_title:
            fixed_title = self._fix_text(e_title)
            html_eerab += f"<div style='font-family: \"Traditional Arabic\"; color: #C0392B; font-size: 18px; font-weight: bold; margin-bottom: 5px;'>{fixed_title}</div>"
        html_eerab += f"<div dir='rtl' style='color:#16a085;'>{eerab if eerab else self.tr_func('no_eerab')}</div>"
        self.txt_eerab.setHtml(html_eerab)
        
        # 3. الصرف
        sarf, s_title = self.info_manager.get_word_data("sarf", sura_id_db, aya_id_db, word_id_db)
        html_sarf = ""
        if s_title:
            fixed_title = self._fix_text(s_title)
            html_sarf += f"<div style='font-family: \"Traditional Arabic\"; color: #C0392B; font-size: 18px; font-weight: bold; margin-bottom: 5px;'>{fixed_title}</div>"
        html_sarf += f"<div dir='rtl' style='color:#8e44ad;'>{sarf if sarf else self.tr_func('no_sarf')}</div>"
        self.txt_sarf.setHtml(html_sarf)
        
        # تحديث الحقول الخاصة بالآية
        current_sura_aya = (sura_id_db, aya_id_db)
        if current_sura_aya != self.last_sura_aya:
            self.load_tafsir()
            self.load_nozool()
            self.load_tajweed()
            self.load_reflection() # تحميل التدبر
            self.last_sura_aya = current_sura_aya

    def load_tafsir(self):
        db_ids = self.data_manager.get_db_ids_from_global(self.current_global_id)
        if not db_ids: return
        sura_id_db, aya_id_db, _ = db_ids
        
        source = self.combo_tafsir.currentData()
        tafsir, t_title = self.info_manager.get_aya_data(source, sura_id_db, aya_id_db)
        
        html_tafsir = ""
        if t_title:
            fixed_title = self._fix_text(t_title)
            html_tafsir += f"<div style='font-family: \"Traditional Arabic\"; color: #C0392B; font-size: 18px; font-weight: bold; margin-bottom: 5px;'>{fixed_title}</div>"
        html_tafsir += f"<div dir='rtl' style='color:#2980b9;'>{tafsir if tafsir else self.tr_func('no_tafsir')}</div>"
        self.txt_tafsir.setHtml(html_tafsir)

    def load_nozool(self):
        db_ids = self.data_manager.get_db_ids_from_global(self.current_global_id)
        if not db_ids: return
        sura_id_db, aya_id_db, _ = db_ids
        
        content, title = self.info_manager.get_aya_data("nozool", sura_id_db, aya_id_db)
        html = ""
        if title:
            fixed_title = self._fix_text(title)
            html += f"<div style='font-family: \"Traditional Arabic\"; color: #C0392B; font-size: 18px; font-weight: bold; margin-bottom: 5px;'>{fixed_title}</div>"
        html += f"<div dir='rtl' style='color:#2c3e50;'>{content if content else self.tr_func('no_nozool')}</div>"
        self.txt_nozool.setHtml(html)

    def load_tajweed(self):
        db_ids = self.data_manager.get_db_ids_from_global(self.current_global_id)
        if not db_ids: return
        sura_id_db, aya_id_db, _ = db_ids
        
        content, title = self.info_manager.get_aya_data("tajweed", sura_id_db, aya_id_db)
        html = ""
        if title:
            fixed_title = self._fix_text(title)
            html += f"<div style='font-family: \"Traditional Arabic\"; color: #C0392B; font-size: 18px; font-weight: bold; margin-bottom: 5px;'>{fixed_title}</div>"
        html += f"<div dir='rtl' style='color:#2c3e50;'>{content if content else self.tr_func('no_tajweed')}</div>"
        self.txt_tajweed.setHtml(html)

    def load_reflection(self):
        """تحميل التدبر المحفوظ للآية الحالية"""
        if self.user_manager and self.user_manager.current_user:
            text = self.user_manager.get_reflection(self.user_manager.current_user, self.current_sura, self.current_aya)
            self.txt_reflection.setText(text)
        else:
            self.txt_reflection.setPlaceholderText(self.tr_func("msg_login_reflection"))
            self.txt_reflection.setEnabled(False)

    def save_reflection(self):
        """حفظ التدبر"""
        if not self.user_manager or not self.user_manager.current_user:
            QMessageBox.warning(self, "تنبيه", self.tr_func("msg_login_reflection"))
            return
            
        text = self.txt_reflection.toPlainText().strip()
        
        # Disable button to indicate processing
        self.btn_save_reflection.setEnabled(False)
        self.btn_save_reflection.setText("جاري الحفظ...")
        
        # Run saving in background thread
        def save_task():
            self.user_manager.save_reflection(self.user_manager.current_user, self.current_sura, self.current_aya, text)
            self.reflection_saved_signal.emit()
            
        threading.Thread(target=save_task, daemon=True).start()

    def on_reflection_saved(self):
        self.btn_save_reflection.setEnabled(True)
        self.btn_save_reflection.setText(self.tr_func("btn_save_reflection"))
        QMessageBox.information(self, "تم", self.tr_func("msg_save_success"))

    def delete_reflection(self):
        """حذف التدبر"""
        if not self.user_manager or not self.user_manager.current_user:
            return
            
        if QMessageBox.question(self, "تأكيد", self.tr_func("msg_confirm_delete"), QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.user_manager.save_reflection(self.user_manager.current_user, self.current_sura, self.current_aya, "")
            self.txt_reflection.clear()

    def on_tab_changed(self, index):
        # التبويبات المعتمدة على الآية: التفسير (1)، أسباب النزول (4)، التجويد (5)، التدبرات (6)
        # لاحظ أن الفهرس يبدأ من 0
        if index in [1, 4, 5, 6]:
            self.btn_prev.setText(self.tr_func("btn_prev_ayah"))
            self.btn_next.setText(self.tr_func("btn_next_ayah"))
        else:
            self.btn_prev.setText(self.tr_func("btn_prev_word"))
            self.btn_next.setText(self.tr_func("btn_next_word"))

    def _go_prev_ayah(self):
        local_info = self.data_manager.global_to_local_map.get(self.current_global_id)
        if not local_info: return
        sura, aya, _ = local_info
        
        target_sura = sura
        target_aya = aya - 1
        
        if target_aya < 1:
            target_sura = sura - 1
            if target_sura < 1: return 
            target_aya = self.data_manager.sura_aya_counts.get(target_sura, 1)
            
        target_global_id = self.data_manager.get_global_word_id_from_local(target_sura, target_aya, 1)
        if target_global_id:
            self.current_global_id = target_global_id
            self.load_data()

    def _go_next_ayah(self):
        local_info = self.data_manager.global_to_local_map.get(self.current_global_id)
        if not local_info: return
        sura, aya, _ = local_info
        
        target_sura = sura
        target_aya = aya + 1
        
        max_aya = self.data_manager.sura_aya_counts.get(sura, 0)
        
        if target_aya > max_aya:
            target_sura = sura + 1
            if target_sura > 114: return
            target_aya = 1
            
        target_global_id = self.data_manager.get_global_word_id_from_local(target_sura, target_aya, 1)
        if target_global_id:
            self.current_global_id = target_global_id
            self.load_data()

    def go_prev_word(self):
        if self.tabs.currentIndex() in [1, 4, 5, 6]: 
            self._go_prev_ayah()
        else:
            if (self.current_global_id - 1) in self.data_manager.global_to_db_map:
                self.current_global_id -= 1
                self.load_data()

    def go_next_word(self):
        if self.tabs.currentIndex() in [1, 4, 5, 6]: 
            self._go_next_ayah()
        else:
            if (self.current_global_id + 1) in self.data_manager.global_to_db_map:
                self.current_global_id += 1
                self.load_data()

    def update_fonts(self):
        """Updates the font size for all text widgets."""
        style = f"QTextBrowser {{ font-family: '{self.font_family}', 'Segoe UI', 'Arial'; font-size: {self.current_font_size}pt; padding: 10px; line-height: 1.4; }}"
        browsers = [self.txt_meaning, self.txt_tafsir, self.txt_eerab, self.txt_sarf, self.txt_nozool, self.txt_tajweed]
        for tb in browsers:
            if tb: tb.setStyleSheet(style)
        
        if self.txt_reflection:
            self.txt_reflection.setStyleSheet(f"font-size: {self.current_font_size}pt; padding: 5px;")
            
        self.settings.setValue("content_font_size", self.current_font_size)

    def zoom_in(self):
        self.current_font_size += 2
        self.update_fonts()

    def zoom_out(self):
        if self.current_font_size > 8:
            self.current_font_size -= 2
            self.update_fonts()
