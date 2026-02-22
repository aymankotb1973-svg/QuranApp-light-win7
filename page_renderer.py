# -*- coding: utf-8 -*-
# Recalculating...
"""
page_renderer.py - Renders Quran pages onto a QGraphicsScene.

This module is responsible for the visual representation of the Quran pages,
including laying out words, handling different display modes (normal vs. recitation),
and applying color-coding based on recitation accuracy.
"""

from PyQt5.QtGui import QFont, QFontDatabase, QColor, QBrush, QPen, QPixmap, QFontMetrics, QTextOption, QPainter, QCursor
from PyQt5.QtWidgets import QGraphicsTextItem, QMenu, QAction, QToolTip
from PyQt5.QtWidgets import QGraphicsRectItem, QGraphicsItem, QGraphicsEllipseItem
from PyQt5.QtCore import QObject, pyqtSignal, Qt, QRectF, QRect, QTimer
from utils import resource_path # Import resource_path
import re

# --- NEW: Import arabic_reshaper locally ---
try:
    import arabic_reshaper
    HAS_RESHAPER = True
except ImportError:
    HAS_RESHAPER = False

# --- NEW: Try importing python-bidi for better reshaping ---
try:
    from bidi.algorithm import get_display
    HAS_BIDI = True
except ImportError:
    HAS_BIDI = False

# --- NEW: Define colors for recitation status ---
CORRECT_COLOR = QColor(0, 128, 0, 255)       # Green
INCORRECT_COLOR = QColor(255, 0, 0, 255)     # Red
PROVISIONAL_CORRECT_COLOR = QColor(0, 128, 0, 100) # Transparent Green
PROVISIONAL_INCORRECT_COLOR = QColor(255, 165, 0, 180) # More opaque orange

# --- NEW: Default Text Color ---
# QColor(Red, Green, Blue, Alpha). Alpha 255 is fully opaque (darkest black).
DEFAULT_TEXT_COLOR = QColor(0, 0, 0, 255)
SURAH_NAME_COLOR = QColor("#8B0000") # Dark Red
BASMALA_COLOR = QColor("#B8860B")    # Dark Goldenrod
AYAH_MARKER_COLOR = QColor("#B8860B") # Gold for Ayah Markers

class WordSignals(QObject):
    """
    Defines signals that can be emitted when a word is interacted with.
    """
    word_clicked = pyqtSignal(str) # Changed to str to match global_idx type
    set_start_clicked = pyqtSignal(str) # New signal for setting start
    set_end_clicked = pyqtSignal(str)   # New signal for setting end
    select_page_clicked = pyqtSignal(str) # NEW: Select full page
    select_sura_clicked = pyqtSignal(str) # NEW: Select full sura
    select_juz_clicked = pyqtSignal(str) # NEW: Select full juz
    select_hizb_clicked = pyqtSignal(str) # NEW: Select full hizb
    select_rub_clicked = pyqtSignal(str) # NEW: Select full rub


class ClickableWord(QGraphicsTextItem):
    """
    A custom QGraphicsTextItem that represents a single word and emits a signal
    when clicked. It also holds metadata about the word.
    """
    def __init__(self, text, global_idx, page_num, data_manager, main_window=None, parent=None):
        super().__init__(text, parent)
        self.global_idx = global_idx
        self.page_num = page_num
        self.data_manager = data_manager
        self.main_window = main_window
        self.signals = WordSignals()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(False) # Disabled to show meaning on hover
        
        # Explicitly set text direction and shaping support for better Arabic rendering
        doc = self.document()
        option = doc.defaultTextOption()
        option.setTextDirection(Qt.RightToLeft)
        doc.setDefaultTextOption(option)

    def hoverEnterEvent(self, event):
        """Show tooltip on hover."""
        meaning = self.data_manager.get_word_meaning(self.global_idx)
        if meaning:
            # Improved styling: Dark background, white text, larger font
            styled_meaning = f"<div style='background-color:#2c3e50; color:white; padding:10px; border-radius:6px; font-size:16px; font-weight:bold; text-align:center; font-family: Arial;' dir='rtl'>{meaning}</div>"
            # Show tooltip for 10 seconds
            QToolTip.showText(QCursor.pos(), styled_meaning, None, QRect(), 10000)
        super().hoverEnterEvent(event)

    def mousePressEvent(self, event):
        """Handle mouse press, but without showing the tooltip."""
        # Tooltip logic is now in hover events.
        event.accept() # Essential: Accept the press so we get the release event

    def mouseReleaseEvent(self, event):
        """Emit word_clicked signal on mouse release."""
        # Emit the original click signal on release to trigger recitation logic
        if event.button() == Qt.LeftButton:
            self.signals.word_clicked.emit(self.global_idx)
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Shows a context menu to set recitation range."""
        menu = QMenu()
        
        # Helper for translation
        tr = self.main_window.tr if self.main_window else lambda k: k

        # Create actions
        start_action = menu.addAction(tr("ctx_set_start"))
        end_action = menu.addAction(tr("ctx_set_end"))
        menu.addSeparator()
        page_action = menu.addAction(tr("ctx_select_page"))
        sura_action = menu.addAction(tr("ctx_select_sura"))
        juz_action = menu.addAction(tr("ctx_select_juz"))
        hizb_action = menu.addAction(tr("ctx_select_hizb"))
        rub_action = menu.addAction(tr("ctx_select_rub"))
        
        # Execute menu at screen position
        action = menu.exec_(event.screenPos())
        
        if action == start_action:
            self.signals.set_start_clicked.emit(self.global_idx)
        elif action == end_action:
            self.signals.set_end_clicked.emit(self.global_idx)
        elif action == page_action:
            self.signals.select_page_clicked.emit(self.global_idx)
        elif action == sura_action:
            self.signals.select_sura_clicked.emit(self.global_idx)
        elif action == juz_action:
            self.signals.select_juz_clicked.emit(self.global_idx)
        elif action == hizb_action:
            self.signals.select_hizb_clicked.emit(self.global_idx)
        elif action == rub_action:
            self.signals.select_rub_clicked.emit(self.global_idx)

# --- NEW: Custom Rect Item for Multiply Blending ---
class BackgroundRectItem(QGraphicsRectItem):
    """A rectangle that blends with the background using Multiply mode."""
    def paint(self, painter, option, widget=None):
        # وضع الدمج "Multiply" يسمح بظهور تفاصيل الصورة تحت اللون
        painter.setCompositionMode(QPainter.CompositionMode_Multiply)
        super().paint(painter, option, widget)

class PageRenderer:
    """
    Manages the rendering of one or two Quran pages onto a QGraphicsScene.
    """
    def __init__(self, main_window):
        self.main_window = main_window
        self.scene = main_window.scene
        self.view = main_window.view
        self.data_manager = main_window.data_manager
        self.border_pixmap = None
        self._word_item_map = {} # Maps global_idx to ClickableWord objects
        self._word_highlight_map = {} # Maps global_idx to highlight rectangle objects
        self._page_overlay_map = {} # NEW: Maps page_num to page overlay rectangle objects
        self._page_bounds_map = {} # NEW: Maps page_num to bounding rectangle of the page
        self._current_rendered_pages = set() # To track which pages are currently rendered
        self.page_overlay_colors = {} # NEW: To store full-page overlay colors
        self._merged_highlight_items = [] # NEW: To store merged highlight rects
        self.splash_border_pixmap = None
        try:
            self.border_pixmap = QPixmap(resource_path("assets/page_border.png"))
            self.splash_border_pixmap = QPixmap(resource_path("assets/page_border0.png"))
        except Exception as e:
            print(f"!!! خطأ في تحميل صورة الإطار: {e}")

    def _is_muqattaat(self, sura, aya):
        """Checks if the word belongs to Muqatta'at (disjoined letters) verses."""
        try:
            s = int(sura)
            a = int(aya)
            # Surahs starting with Muqatta'at at Ayah 1
            if a == 1 and s in [2, 3, 7, 10, 11, 12, 13, 14, 15, 19, 20, 26, 27, 28, 29, 30, 31, 32, 36, 38, 40, 41, 42, 43, 44, 45, 46, 50, 68]:
                return True
            # Surah 42 (Ash-Shura) has Muqatta'at at Ayah 2 as well ('Ain Sin Qaf')
            if s == 42 and a == 2:
                return True
        except (ValueError, TypeError):
            pass
        return False

    def fix_arabic_display(self, text):
        """Applies reshaping for Arabic text (Muqatta'at)."""
        if not text or not HAS_RESHAPER:
            if not HAS_RESHAPER: print("WARNING: arabic_reshaper not found!")
            return text
        try:
            configuration = {
                'delete_harakat': False,
                'support_zwj': True,
                'shift_harakat_position': True
            }
            reshaper = arabic_reshaper.ArabicReshaper(configuration=configuration)
            reshaped_text = reshaper.reshape(text)
            
            # Apply Bidi if available (fixes direction issues)
            if HAS_BIDI:
                reshaped_text = get_display(reshaped_text)
                
            return reshaped_text
        except Exception as e:
            print(f"Error in fix_arabic_display: {e}")
            return text

    def start_recitation_render(self):
        """Forces a full re-render specifically for starting recitation."""
        print("DEBUG: Forcing recitation start re-render.")
        self._current_rendered_pages.clear()
        self.render_page(self.main_window.current_page)


    def update_word_text_color(self, global_idx: str, color: QColor):
        """
        Directly updates the text color of a specific word item on the scene.
        """
        try:
            word_item = self._word_item_map.get(global_idx)
            if word_item:
                word_item.setDefaultTextColor(color)
                word_item.setVisible(True) # Ensure item is visible
                word_item.update() # Force item repaint
                self.scene.update(word_item.sceneBoundingRect()) # Force scene update for this area
                self.view.viewport().update() # Force immediate view update
        except Exception as e:
            print(f"ERROR(PR) in update_word_text_color for {global_idx}: {e}")

    def update_word_highlight(self, global_idx: str, color: QColor):
        """
        Updates the background highlight color of a specific word.
        """
        try:
            highlight_item = self._word_highlight_map.get(global_idx)
            if highlight_item:
                highlight_item.setBrush(color)
                highlight_item.setVisible(color.alpha() > 0)
        except Exception as e:
            print(f"ERROR(PR) in update_word_highlight for {global_idx}: {e}")

    def apply_page_overlay(self, page_num: int, color: QColor):
        """
        Applies a full-page overlay highlight to the specified page.
        """
        if page_num not in self._page_bounds_map:
            print(f"WARNING: Cannot apply overlay, page {page_num} not rendered.")
            return

        page_rect = self._page_bounds_map[page_num]
        overlay_item = self._page_overlay_map.get(page_num)

        if overlay_item:
            overlay_item.setBrush(color)
            overlay_item.setVisible(color.alpha() > 0)
        else:
            overlay_item = self.scene.addRect(page_rect, QPen(Qt.NoPen), color)
            overlay_item.setZValue(-2) # Below text (-1 for word highlight, 0 for border, 1 for text)
            self._page_overlay_map[page_num] = overlay_item
            overlay_item.setVisible(color.alpha() > 0)

    def clear_page_overlays(self, page_num: int = None):
        """
        Clears page overlay highlights from the scene.
        If page_num is provided, clears only that page's overlay.
        If None, clears all page overlays.
        """
        if page_num is not None:
            overlay_item = self._page_overlay_map.pop(page_num, None)
            if overlay_item:
                self.scene.removeItem(overlay_item)
        else:
            for overlay_item in list(self._page_overlay_map.values()): # Use list() to iterate over a copy
                self.scene.removeItem(overlay_item)
            self._page_overlay_map.clear()

    def ensure_visible(self, global_idx):
        """Ensures the word with the given global_idx is visible in the view."""
        item = self._word_item_map.get(global_idx)
        if item:
            page_num = getattr(item, 'page_num', None)
            
            # If in two-page mode and we know the page number, do custom scrolling.
            if page_num is not None and self.main_window.view_mode == "two_pages":
                # Ensure vertical visibility first
                self.view.ensureVisible(item, 0, 50)
                
                h_scrollbar = self.view.horizontalScrollBar()
                # Odd pages are on the right, even on the left (except page 1, which is also odd/right)
                if page_num % 2 != 0: 
                    h_scrollbar.setValue(h_scrollbar.minimum())
                else:
                    h_scrollbar.setValue(h_scrollbar.maximum())
            else:
                # Fallback for single-page (dynamic) view or if page_num is missing: center the item.
                self.view.ensureVisible(item, 50, 50)

    def ensure_ayah_visible(self, sura, aya):
        """Ensures the first word of the specified ayah is visible."""
        # Try to find any word belonging to this ayah in the current map
        prefix = f"{sura}:{aya}:"
        for key in self._word_item_map:
            if key.startswith(prefix):
                self.ensure_visible(key)
                return

    def _to_arabic_numerals(self, number: int) -> str:
        """Converts a Latin digit integer to an Arabic numeral string."""
        arabic_map = "٠١٢٣٤٥٦٧٨٩"
        # The string is reversed to ensure correct display order for multi-digit numbers in a Right-to-Left rendering context.
        arabic_str = "".join(arabic_map[int(digit)] for digit in str(number))
        return arabic_str[::-1]

    def render_page(self, start_page_num):
        """
        Renders the specified page and the one next to it. It performs a full re-render
        if the pages have changed, and then always updates the word colors based on
        the current recitation state to ensure persistence.
        """
        # --- Check for None before processing pages (Moved to top) ---
        if start_page_num is None:
            print("Error: start_page_num is None. Skipping page rendering.")
            return # Stop further processing

        pages_to_render = {start_page_num}
        if start_page_num == 1: pages_to_render.add(2)
        elif start_page_num % 2 != 0:
            if start_page_num < 604: pages_to_render.add(start_page_num + 1)
        else: pages_to_render.add(start_page_num - 1)

        pages_to_render = {p for p in pages_to_render if 0 < p <= 604}
        full_rerender_needed = pages_to_render != self._current_rendered_pages

        if full_rerender_needed:
            self.scene.clear()
            self._word_item_map.clear()
            self._word_highlight_map.clear()
            self._page_overlay_map.clear() # Clear overlays on full re-render
            self._merged_highlight_items.clear() # Clear merged highlights list
            self._current_rendered_pages = pages_to_render
            self.main_window.rendered_sura_headers.clear()
            
            # --- NEW: Special handling for pages 1 & 2 ---
            # تم إزالة شرط الوضع الديناميكي ليظهر التصميم الجديد دائماً في الصفحة 1 و 2
            if start_page_num in [1, 2]:
                self._render_splash_spread()
            else:
                self._render_normal_spread(start_page_num)

            self.scene.setSceneRect(self.scene.itemsBoundingRect())
            self._apply_scale()
        
        # Always update word colors, whether it was a full re-render or just a state change.
        # This ensures recitation highlights (both live and final) are correctly applied.
        self._update_existing_word_colors()
        
        # --- FIX: Re-apply masks for Auto Reveal / Voice Trigger modes ---
        # This ensures that whenever the page is redrawn (e.g. resize, fullscreen), the mask is preserved.
        if getattr(self.main_window, 'is_auto_reveal_mode', False):
            if hasattr(self.main_window, '_apply_auto_reveal_mask'):
                self.main_window._apply_auto_reveal_mask()
        elif getattr(self.main_window, 'is_voice_trigger_active', False):
            if hasattr(self.main_window, '_apply_voice_trigger_mask'):
                self.main_window._apply_voice_trigger_mask()

    def _render_splash_spread(self):
        """Renders the special two-page spread for pages 1 and 2."""
        # Page 2 on left, Page 1 on right
        left_page_width = self._render_special_page(2, 0)
        right_page_offset = left_page_width + 20
        self._render_special_page(1, right_page_offset)

    def _render_special_page(self, page_num, x_offset):
        """
        Renders page 1 or 2 using standard data (ClickableWord) but with fixed layout/font 
        to fit the special border, preserving all interactive features.
        """
        PAGE_WIDTH = 1350
        PAGE_HEIGHT = 1500
        
        # إعدادات خاصة للصفحتين (ثابتة لا تتغير بإعدادات المستخدم)
        FIXED_FONT_SIZE = 42  # تم التصغير من 45 إلى 42
        SIDE_MARGIN = 280     # هوامش جانبية واسعة ليدخل النص في الإطار
        TOP_MARGIN = 340      # تم الرفع للصفحة 1 (كان 400) بمقدار سطر تقريباً
        LINE_SPACING = 25     # تباعد الأسطر

        # 1. Draw Special Border
        border_pixmap_to_use = self.splash_border_pixmap
        if border_pixmap_to_use and not border_pixmap_to_use.isNull():
            border_item = self.scene.addPixmap(border_pixmap_to_use)
            border_item.setPixmap(border_pixmap_to_use.scaled(int(PAGE_WIDTH), int(PAGE_HEIGHT), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))
            border_item.setPos(x_offset, 0)
            border_item.setZValue(0)

        # 2. Render Surah Header
        sura_no = 1 if page_num == 1 else 2
        sura_name = self.data_manager.get_sura_name(sura_no)
        sura_header_text = f"سورة {sura_name}"
        
        # Use app font family
        font_family = self.main_window.quran_text_display_font_family
        sura_header_font = QFont(font_family, 60, QFont.Bold)
        
        sura_header_item = QGraphicsTextItem(sura_header_text)
        sura_header_item.setFont(sura_header_font)
        sura_header_item.setDefaultTextColor(SURAH_NAME_COLOR)
        header_width = QFontMetrics(sura_header_font).width(sura_header_text)
        header_x = x_offset + (PAGE_WIDTH - header_width) / 2
        
        # تحديد مكان اسم السورة حسب الصفحة
        header_y = 220
        if page_num == 1: header_y += 70  # زيادة الإنزال للصفحة 1
        if page_num == 2: header_y += 70  # زيادة الإنزال للصفحة 2
            
        sura_header_item.setPos(header_x, header_y)
        self.scene.addItem(sura_header_item)

        # 3. Render Basmala (For Page 2 only manually, Page 1 has it in data)
        # تعديل بداية الآيات للصفحة 1 لتفادي التداخل مع العنوان الجديد
        current_y = TOP_MARGIN - 40 if page_num == 1 else TOP_MARGIN

        if page_num == 2:
            basmala_text = self.data_manager.get_basmala_text()
            basmala_font = QFont(font_family, 45, QFont.Bold) 
            basmala_item = QGraphicsTextItem(basmala_text)
            basmala_item.setFont(basmala_font)
            basmala_item.setDefaultTextColor(BASMALA_COLOR)
            b_width = QFontMetrics(basmala_font).width(basmala_text)
            b_x = x_offset + (PAGE_WIDTH - b_width) / 2
            # إنزال البسملة لتكون أسفل اسم السورة بمسافة مناسبة
            # header_y (290) + height (~100) -> 390
            basmala_item.setPos(b_x, 390) 
            self.scene.addItem(basmala_item)
            # تعديل بداية الآيات لتكون أسفل البسملة بمسافة كافية
            current_y = 300 

        # 4. Render Content using ClickableWord (Interactive)
        # We use the standard page data but force our layout and font
        page_data = self.data_manager.get_page_layout(page_num)
        if not page_data: return PAGE_WIDTH

        # جعل الخط عريضاً (Bold)
        quran_font = QFont(font_family, FIXED_FONT_SIZE, QFont.Bold)
        fm = QFontMetrics(quran_font)

        for line_data in page_data:
            # Calculate total width of the line to center it
            line_items = []
            total_width = 0
            
            for item in line_data:
                text = item.get('text', '').strip()
                if not text: continue
                
                # --- Apply reshaping for Muqatta'at ---
                if self._is_muqattaat(item.get('surah'), item.get('ayah')):
                     text = self.fix_arabic_display(text)

                # Check if marker
                is_numeral = re.match(r"^[٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹]+$", text)
                is_marker = (is_numeral or item.get('char_type') == 'end') and item.get('ayah') is not None
                
                if is_marker:
                    aya_val = item.get('ayah')
                    aya_str = self._to_arabic_numerals(int(aya_val))
                    m_font = QFont(self.main_window.ayah_number_font_family, int(FIXED_FONT_SIZE * 0.8))
                    w = QFontMetrics(m_font).width(aya_str)
                    line_items.append({'type': 'marker', 'text': aya_str, 'w': w, 'font': m_font})
                    total_width += w
                else:
                    w = fm.width(text)
                    line_items.append({'type': 'word', 'text': text, 'w': w, 'data': item, 'font': quran_font})
                    total_width += w
            
            # Add spacing
            spacing = 15
            if len(line_items) > 1:
                total_width += (len(line_items) - 1) * spacing
            
            # Calculate Start X (Centered)
            # Drawing Right-to-Left
            current_x = x_offset + (PAGE_WIDTH / 2) + (total_width / 2)
            
            for item in line_items:
                w = item['w']
                pos_x = current_x - w
                
                if item['type'] == 'word':
                    # Create ClickableWord for interactivity
                    word_data = item['data']
                    sura = word_data.get('surah')
                    aya = word_data.get('ayah')
                    word_id = word_data.get('word')
                    global_idx = f"{sura}:{aya}:{word_id}" if all([sura, aya, word_id is not None]) else ""
                    
                    word_item = ClickableWord(item['text'], global_idx, page_num, self.data_manager, self.main_window)
                    word_item.setFont(item['font'])
                    
                    # تلوين البسملة في الفاتحة باللون الذهبي
                    if page_num == 1 and sura == 1 and aya == 1:
                        word_item.setDefaultTextColor(BASMALA_COLOR)
                    else:
                        word_item.setDefaultTextColor(self.main_window.quran_text_color)

                    word_item.setPos(pos_x, current_y)
                    
                    # Connect signals (Crucial for interactivity)
                    word_item.signals.word_clicked.connect(self.main_window.handle_word_click)
                    word_item.signals.set_start_clicked.connect(self.main_window.set_recitation_start)
                    word_item.signals.set_end_clicked.connect(self.main_window.set_recitation_end)
                    word_item.signals.select_page_clicked.connect(self.main_window.set_range_page)
                    word_item.signals.select_sura_clicked.connect(self.main_window.set_range_sura)
                    word_item.signals.select_juz_clicked.connect(self.main_window.set_range_juz)
                    word_item.signals.select_hizb_clicked.connect(self.main_window.set_range_hizb)
                    word_item.signals.select_rub_clicked.connect(self.main_window.set_range_rub)
                    
                    # Highlight rect
                    highlight_rect = QGraphicsRectItem(word_item.boundingRect())
                    highlight_rect.setPos(pos_x, current_y)
                    highlight_rect.setPen(QPen(Qt.NoPen))
                    highlight_rect.setBrush(QColor(0,0,0,0))
                    highlight_rect.setZValue(0.5)
                    self._word_highlight_map[global_idx] = highlight_rect
                    self.scene.addItem(highlight_rect)
                    
                    word_item.setZValue(1)
                    self.scene.addItem(word_item)
                    self._word_item_map[global_idx] = word_item
                    
                else:
                    # Marker (Static text)
                    m_item = QGraphicsTextItem(item['text'])
                    m_item.setFont(item['font'])
                    m_item.setDefaultTextColor(AYAH_MARKER_COLOR)
                    m_item.setPos(pos_x, current_y)
                    self.scene.addItem(m_item)
                
                current_x -= (w + spacing)
            
            current_y += fm.height() + LINE_SPACING

        return PAGE_WIDTH

    def _render_normal_spread(self, start_page_num):
        """Renders a normal two-page spread for any page other than the special splash pages."""
        page_on_left = 0
        page_on_right = 0 

        if start_page_num % 2 != 0:
             page_on_left = start_page_num + 1
             page_on_right = start_page_num
        else: # Even page
             page_on_left = start_page_num
             page_on_right = start_page_num - 1

        if page_on_right > 604: page_on_right = 0
        if page_on_left > 604: page_on_left = 0

        render_func = self._render_single_page_dynamically if self.main_window.view_mode == "dynamic" else self._render_single_page

        left_page_width = render_func(page_on_left, 0) if page_on_left > 0 else 0
        right_page_offset = left_page_width + 20 if left_page_width > 0 else 0
        if page_on_right > 0:
            render_func(page_on_right, right_page_offset)

    def _get_merged_rects(self, word_items, tolerance=10):
        """
        Groups word rectangles into line strips based on Y-coordinate proximity.
        Returns a list of QRectF objects representing the merged areas.
        """


        lines = {}
        for i, item in enumerate(word_items):
            # Use sceneBoundingRect to get absolute coordinates in the scene
            rect = item.sceneBoundingRect()

            
            # Group by Y coordinate (row) with some tolerance.
            # Using center Y is robust against slight vertical misalignments.
            y_key = int(rect.center().y() // tolerance)
            
            if y_key not in lines:
                lines[y_key] = rect
            else:
                lines[y_key] = lines[y_key].united(rect)
        

        merged_rects = list(lines.values())
        return merged_rects

    def _update_existing_word_colors(self):
        print(f"DIAGNOSTIC: _update_existing_word_colors called. recording_mode = {self.main_window.recording_mode}")
        """
        Updates the visibility and color of existing ClickableWord items on the scene
        based on the current recitation state in main_window. This implements the
        "hide-then-show-as-you-go" feature.
        """
        # Ensure the main window is in a state where it has all the necessary attributes.
        if not all(hasattr(self.main_window, attr) for attr in
                   ['_word_statuses', 'recitation_idx_map', 'recording_mode']):
            return

        # --- NEW: Handle Merged Highlights (Playlist/Range) ---
        # 1. Clear previous merged highlights
        for item in self._merged_highlight_items:
            if item.scene() == self.scene:
                self.scene.removeItem(item)
        self._merged_highlight_items.clear()


        # 2. Collect words to highlight by color
        words_by_color = {} # ColorHex -> (QColor, [ClickableWord])
        merged_highlight_indices = set()

        if hasattr(self.main_window, '_pending_word_highlights'):
            for global_idx, color in self.main_window._pending_word_highlights.items():
                if global_idx in self._word_item_map:
                    c_key = color.name(QColor.HexArgb) # Use hex with alpha for key
                    if c_key not in words_by_color:
                        words_by_color[c_key] = (color, [])
                    words_by_color[c_key][1].append(self._word_item_map[global_idx])
                    merged_highlight_indices.add(global_idx)


        # 3. Draw merged highlights
        for _, (color, items) in words_by_color.items():
            if color.alpha() == 0: continue
            
            merged_rects = self._get_merged_rects(items)
            for rect in merged_rects:
                # Create QGraphicsRectItem for the merged area
                r_item = QGraphicsRectItem(rect)
                r_item.setPen(QPen(Qt.NoPen))
                r_item.setBrush(QBrush(color))
                r_item.setZValue(0.4) # Below text (1), above border/bg (-1, 0)
                self.scene.addItem(r_item)
                self._merged_highlight_items.append(r_item)
        # ------------------------------------------------------

        for global_idx, word_item in self._word_item_map.items():
            is_in_recitation_range = global_idx in self.main_window.recitation_idx_map

            # Default state: visible and black
            should_be_visible = True
            text_color = self.main_window.quran_text_color

            if self.main_window.recording_mode:
                # --- Recitation is ACTIVE ---
                if is_in_recitation_range:
                    recitation_idx = self.main_window.recitation_idx_map[global_idx]

                    # Rule 1: Word has a final status
                    if recitation_idx < len(self.main_window._word_statuses) and \
                         self.main_window._word_statuses[recitation_idx] is not None:
                        status = self.main_window._word_statuses[recitation_idx]
                        should_be_visible = True
                        text_color = CORRECT_COLOR if status else INCORRECT_COLOR
                    # Rule 2: Word is in range but not yet recited
                    else:
                        should_be_visible = False
                # else: word is not in recitation range, so it remains visible and black (default)

            else:
                # --- Recitation is STOPPED ---
                # Show final results for the completed recitation range.
                if is_in_recitation_range:
                    recitation_idx = self.main_window.recitation_idx_map[global_idx]
                    if recitation_idx < len(self.main_window._word_statuses) and \
                       self.main_window._word_statuses[recitation_idx] is not None:
                        status = self.main_window._word_statuses[recitation_idx]
                        text_color = CORRECT_COLOR if status else INCORRECT_COLOR
                # else: word is outside the range, remains black (default)

            # Apply the determined visibility and color
            word_item = self._word_item_map.get(global_idx)
            highlight_item = self._word_highlight_map.get(global_idx)
            if not word_item or not highlight_item:
                continue

            # --- Initialize background and text color/visibility with defaults ---
            final_bg_color = QColor(0,0,0,0) # Default transparent background
            
            # Determine base text color (Black usually, but Gold for Fatiha Basmala)
            base_text_color = self.main_window.quran_text_color
            if getattr(word_item, 'page_num', 0) == 1:
                try:
                    s, a, _ = map(int, global_idx.split(':'))
                    if s == 1 and a == 1:
                        base_text_color = BASMALA_COLOR
                except: pass

            final_text_color = base_text_color
            final_visibility = True

            # --- Determine background highlight color based on priority ---
            # Priority 1: Pending Range Highlight (lowest priority for background)
            # MODIFIED: Only apply individual highlight if NOT covered by merged highlight
            if global_idx not in merged_highlight_indices:
                if hasattr(self.main_window, '_pending_word_highlights') and global_idx in self.main_window._pending_word_highlights:
                    final_bg_color = self.main_window._pending_word_highlights[global_idx]

            # --- Text Color/Visibility Logic ---
            
            # Priority 1: Playback Review Mode (Works anytime, even if not recording)
            if self.main_window.playback_review_mode:
                parts = global_idx.split(':')
                is_revealed = False
                if len(parts) >= 3:
                    try:
                        sura = int(parts[0])
                        aya = int(parts[1])
                        # Check ayah
                        if (sura, aya) in self.main_window.revealed_ayahs_in_playback:
                            is_revealed = True
                        # Check page
                        if word_item.page_num in self.main_window.revealed_pages_in_playback:
                            is_revealed = True
                    except ValueError:
                        pass
                
                if is_revealed:
                    final_text_color = self.main_window.review_text_color # Use review color (Green)
                else:
                    final_text_color = QColor(0, 0, 0, 0) # Hidden
                
                final_visibility = True

            # Priority 2: Recording Mode (Microphone Recitation)
            elif self.main_window.recording_mode:
                is_in_recitation_range = global_idx in self.main_window.recitation_idx_map

                if is_in_recitation_range:
                    recitation_idx = self.main_window.recitation_idx_map[global_idx]
                    status = None
                    if recitation_idx < len(self.main_window._word_statuses):
                        status = self.main_window._word_statuses[recitation_idx]

                    if self.main_window.is_review_mode:
                        # In Review Mode: Show revealed words in review color, hide others
                        if status is True:
                            final_text_color = self.main_window.review_text_color
                        else:
                            final_text_color = QColor(0, 0, 0, 0) # Hidden
                        final_visibility = True
                    elif self.main_window.hide_text_during_recitation:
                        # In "Hide Text" mode
                        # Always keep text transparent
                        if status is True:
                            # If correct, show the text in green
                            final_text_color = CORRECT_COLOR
                        elif status is False:
                            # If incorrect, show the text in red
                            final_text_color = INCORRECT_COLOR
                        else: # Not yet recited (status is None)
                            # This is the main change: Hide only the default (black) text
                            final_text_color = QColor(0, 0, 0, 0) # Fully transparent
                        
                        final_visibility = True # Keep the item visible to allow its color (or transparency) to be set
                    else:
                        # Normal recitation mode (text is always visible and colored by status)
                        if status is True:
                            final_text_color = CORRECT_COLOR
                        elif status is False:
                            final_text_color = INCORRECT_COLOR
                        else:
                            final_text_color = base_text_color # Default for unrecited

                        final_visibility = True # Always visible in normal mode
                else:
                    final_visibility = True # Words outside recitation range are visible
                    final_text_color = base_text_color # Keep text black (or gold)

            # --- Apply determined colors and visibility ---
            highlight_item.setBrush(final_bg_color)
            highlight_item.setVisible(final_bg_color.alpha() > 0)

            word_item.setVisible(final_visibility)
            word_item.setDefaultTextColor(final_text_color)

    def _render_single_page_dynamically(self, page_num, x_offset):
        """
        Renders a single page with text wrapping to fit a fixed page width area.
        This implements the logic for "Dynamic View" mode for a single page.
        """
        print(f"DEBUG: Rendering page {page_num} DYNAMICALLY at offset {x_offset}")

        page_data = self.data_manager.get_page_layout(page_num)
        if not page_data:
            print(f"No layout data for page {page_num}")
            return 0

        # --- Layout Constants ---
        PAGE_WIDTH = 1350
        PAGE_HEIGHT = 1500
        TOP_MARGIN = 120
        BOTTOM_MARGIN = 170
        SIDE_MARGIN = 120
        # استخدام المسافة المحددة في الإعدادات (الافتراضي 5 لتقليل المسافة)
        word_spacing = getattr(self.main_window, 'dynamic_word_spacing', 10)
        line_spacing = -15 # Reduced from 10 to bring lines closer

        # --- Background and Border ---
        # 1. رسم الإطار أولاً (في الخلفية)
        if self.border_pixmap and not self.border_pixmap.isNull():
            border_item = self.scene.addPixmap(self.border_pixmap)
            border_item.setPixmap(self.border_pixmap.scaled(int(PAGE_WIDTH), int(PAGE_HEIGHT), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))
            border_item.setPos(x_offset, 0)
            border_item.setZValue(0)

        # Flatten all words and ayah markers from the page into a single list
        all_items = [item for line in page_data for item in line]

        # --- Font Metrics ---
        drawable_width = PAGE_WIDTH - (2 * SIDE_MARGIN)
        font_size = self.main_window.dynamic_font_size
        weight = getattr(self.main_window, 'font_weight', QFont.Normal)
        quran_word_font = QFont(self.main_window.quran_text_display_font_family, font_size, weight)
        quran_word_font.setStyleStrategy(QFont.PreferAntialias | QFont.ForceOutline) # Improve rendering quality and thickness
        fm = QFontMetrics(quran_word_font)
        line_height = fm.height() + line_spacing

        # Start position (Right-to-Left), adjusted for x_offset
        current_x = x_offset + PAGE_WIDTH - SIDE_MARGIN
        current_y = TOP_MARGIN

        # Regex for Arabic numerals to detect ayah markers robustly
        pattern = re.compile(r"^[٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹]+$")

        # --- Render Words with Wrapping (Right-to-Left) ---
        for item_data in all_items:
            text = item_data.get('text', '').strip()
            if not text: continue
            
            # ---  Apply reshaping for Muqatta'at ---
            if self._is_muqattaat(item_data.get('surah'), item_data.get('ayah')):
                text = self.fix_arabic_display(text)

            is_numeral = pattern.match(text)
            is_ayah_marker = (item_data.get('char_type') == 'end') or (is_numeral and item_data.get('ayah') is not None)
            is_word = not is_ayah_marker
            
            if is_word:
                # --- NEW: Check for Surah Header inside the loop ---
                current_surah = item_data.get('surah')
                if current_surah and page_num == self.data_manager.sura_pages.get(current_surah) and current_surah not in self.main_window.rendered_sura_headers:
                    # If not at the start of a line, move to next line
                    if current_x < (x_offset + PAGE_WIDTH - SIDE_MARGIN):
                        current_y += line_height
                        current_x = x_offset + PAGE_WIDTH - SIDE_MARGIN
                    
                    self.main_window.rendered_sura_headers.add(current_surah)
                    sura_name_arabic = self.main_window.data_manager.get_sura_name(current_surah)
                    sura_header_text = f"سورة {sura_name_arabic}"
                    
                    sura_header_font = QFont(self.main_window.quran_text_display_font_family, font_size + 4, QFont.Bold)
                    sura_header_item = QGraphicsTextItem(sura_header_text)
                    sura_header_item.setFont(sura_header_font)
                    sura_header_item.setDefaultTextColor(SURAH_NAME_COLOR)
                    header_width = QFontMetrics(sura_header_font).width(sura_header_text)
                    header_x = x_offset + (PAGE_WIDTH - header_width) / 2
                    sura_header_item.setPos(header_x, current_y)
                    sura_header_item.setZValue(1.5)
                    self.scene.addItem(sura_header_item)
                    current_y += sura_header_item.boundingRect().height() - 25

                    if current_surah != 1 and current_surah != 9:
                        basmala_text = self.data_manager.get_basmala_text()
                        basmala_font = QFont(self.main_window.quran_text_display_font_family, font_size + 2)
                        basmala_font.setBold(True)
                        basmala_item = QGraphicsTextItem(basmala_text)
                        basmala_item.setFont(basmala_font)
                        basmala_item.setDefaultTextColor(BASMALA_COLOR)
                        basmala_width = QFontMetrics(basmala_font).width(basmala_text)
                        basmala_x = x_offset + (PAGE_WIDTH - basmala_width) / 2
                        basmala_item.setPos(basmala_x, current_y)
                        basmala_item.setZValue(1.5)
                        self.scene.addItem(basmala_item)
                        current_y += basmala_item.boundingRect().height() - 10 # تعديل المسافة بعد البسملة في الوضع الديناميكي
                    else:
                        current_y += 5

                    # Reset X for the first word of the new surah
                    current_x = x_offset + PAGE_WIDTH - SIDE_MARGIN
                # ---------------------------------------------------

                word_text = text
                surah_no, aya_no, word_id = item_data.get('surah'), item_data.get('ayah'), item_data.get('word')
                global_idx = f"{surah_no}:{aya_no}:{word_id}" if all([surah_no, aya_no, word_id is not None]) else ""
                word_item = ClickableWord(word_text, global_idx, page_num, self.data_manager, self.main_window)
                word_item.setFont(quran_word_font)
                word_item.signals.word_clicked.connect(self.main_window.handle_word_click)
                word_item.signals.set_start_clicked.connect(self.main_window.set_recitation_start)
                word_item.signals.set_end_clicked.connect(self.main_window.set_recitation_end)
                word_item.signals.select_page_clicked.connect(self.main_window.set_range_page)
                word_item.signals.select_sura_clicked.connect(self.main_window.set_range_sura)
                word_item.signals.select_juz_clicked.connect(self.main_window.set_range_juz)
                word_item.signals.select_hizb_clicked.connect(self.main_window.set_range_hizb)
                word_item.signals.select_rub_clicked.connect(self.main_window.set_range_rub)
                word_item.setDefaultTextColor(self.main_window.quran_text_color)
            else: # Ayah marker
                if not self.main_window.show_aya_markers: continue
                
                # --- NEW: Draw Ayah Number (Large) ---
                aya_val = item_data.get('ayah', 0)
                aya_str = self._to_arabic_numerals(aya_val)
                
                # تكبير حجم الرقم (1.3 من حجم الخط الأصلي) ليكون واضحاً بدون دائرة
                number_font_size = int(font_size * 1.3)
                font = QFont(self.main_window.ayah_number_font_family, number_font_size)
                
                number_item = QGraphicsTextItem(aya_str)
                number_item.setFont(font)
                # لون ذهبي ليتناسب مع الزخارف القرآنية
                number_item.setDefaultTextColor(AYAH_MARKER_COLOR)
                number_item.setZValue(11) 
                
                word_item = number_item

            word_width = word_item.boundingRect().width()

            if current_x - word_width < (x_offset + SIDE_MARGIN):
                current_y += line_height
                current_x = x_offset + PAGE_WIDTH - SIDE_MARGIN

            item_x = current_x - word_width
            
            # Vertically center the item in the line
            item_height = word_item.boundingRect().height()
            y_pos = current_y + (line_height - item_height) / 2
            
            word_item.setPos(item_x, y_pos)
            self.scene.addItem(word_item)

            if is_word:
                highlight_rect = QGraphicsRectItem(word_item.boundingRect())
                highlight_rect.setPos(item_x, y_pos)
                highlight_rect.setPen(QPen(Qt.NoPen))
                highlight_rect.setBrush(QColor(0,0,0,0))
                highlight_rect.setZValue(0.5)
                self.scene.addItem(highlight_rect)
                self._word_highlight_map[global_idx] = highlight_rect
                self._word_item_map[global_idx] = word_item

            current_x -= (word_width + word_spacing)

        # --- Page Number ---
        page_num_font = QFont(self.main_window.font_family, 40)
        page_num_text_item = QGraphicsTextItem(str(page_num))
        page_num_text_item.setFont(page_num_font)
        page_num_text_item.setDefaultTextColor(QColor("#1565C0"))
        page_num_bounding_rect = page_num_text_item.boundingRect()
        page_num_x = x_offset + (PAGE_WIDTH - page_num_bounding_rect.width()) / 2
        page_num_y = PAGE_HEIGHT - (BOTTOM_MARGIN / 2) - (page_num_bounding_rect.height() / 2) - 50
        page_num_text_item.setPos(page_num_x, page_num_y)
        page_num_text_item.setZValue(2)
        self.scene.addItem(page_num_text_item)

        return PAGE_WIDTH

    def _render_single_page(self, page_num, x_offset):
        print(f"DEBUG: _render_single_page called for page {page_num}")
        """
        Renders a single page using a dynamic justification algorithm based on the shortest line.
        """
        page_data = self.data_manager.get_page_layout(page_num)
        if not page_data:
            print(f"No layout data for page {page_num}")
            return 0

        # Filter out lines that do not contain any words for rendering
        filtered_page_data = []
        for line_data in page_data:
            words_in_line = [w for w in line_data if w.get('char_type') != 'end']
            if words_in_line:
                filtered_page_data.append(line_data)
        page_data = filtered_page_data

        # --- Layout Constants ---
        PAGE_WIDTH = 1350
        PAGE_HEIGHT = 1500
        TOP_MARGIN = 120
        BOTTOM_MARGIN = 170
        SIDE_MARGIN = 120
        LINE_SPACING = -10
        MIN_WORD_SPACING = 5
        font_size = self.main_window.static_font_size
        
        # --- Background and Border ---
        if self.border_pixmap and not self.border_pixmap.isNull():
            border_item = self.scene.addPixmap(self.border_pixmap)
            border_item.setPixmap(self.border_pixmap.scaled(
                int(PAGE_WIDTH), int(PAGE_HEIGHT), 
                Qt.AspectRatioMode.IgnoreAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            ))
            border_item.setPos(x_offset, 0)
            border_item.setZValue(0)

        # --- Font Setup ---
        weight = getattr(self.main_window, 'font_weight', QFont.Normal)
        quran_word_font = QFont(self.main_window.quran_text_display_font_family, font_size, weight)
        quran_word_font.setStyleStrategy(QFont.PreferAntialias | QFont.ForceOutline)
        fm = QFontMetrics(quran_word_font)
        line_height = fm.height() + LINE_SPACING
        
        ayah_marker_font = QFont(self.main_window.ayah_number_font_family, int(font_size * self.main_window.ayah_font_size_ratio))
        # fm_aya = QFontMetrics(ayah_marker_font) # Not used directly for width

        # --- 1. Measure Phase: Calculate metrics for all lines ---
        line_measurements = []
        max_min_width = 0 # Width required for the widest line with minimum spacing

        for line_data in page_data:
            items = []
            content_width = 0
            
            # Process items in the line to calculate widths
            for item in line_data:
                text = item.get('text', '').strip()
                if not text: continue

                # ---  Apply reshaping for Muqatta'at ---
                if self._is_muqattaat(item.get('surah'), item.get('ayah')):
                     text = self.fix_arabic_display(text)

                # Check if it's an ayah marker
                is_numeral = re.match(r"^[٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹]+$", text)
                is_ayah_marker = (is_numeral or item.get('char_type') == 'end') and item.get('ayah') is not None

                # REMOVED: Title Replacement Logic to preserve Uthmanic Rasm
                # The JSON data contains the correct Uthmanic text.
                # Replacing it with 'titles_map' (Standard Arabic) breaks the drawing rules.

                item_width = 0
                item_type = 'word'
                
                if is_ayah_marker:
                    item_type = 'ayah_marker'
                    # Calculate marker width
                    aya_val = item.get('ayah')
                    # Fix for non-integer ayah values if any
                    if isinstance(aya_val, str) and not aya_val.isdigit():
                         # Try to extract number
                         nums = re.findall(r'\d+', aya_val)
                         aya_val = int(nums[0]) if nums else 0
                    
                    aya_str = self._to_arabic_numerals(int(aya_val))
                    # Use a temp text item to get accurate bounding rect for the marker font
                    temp_item = QGraphicsTextItem(aya_str)
                    temp_item.setFont(ayah_marker_font)
                    item_width = temp_item.boundingRect().width()
                else:
                    item_width = fm.width(text)

                items.append({
                    'type': item_type,
                    'width': item_width,
                    'text': text if item_type == 'word' else self._to_arabic_numerals(int(item.get('ayah', 0))),
                    'data': item
                })
                content_width += item_width

            # Calculate gaps
            num_items = len(items)
            adjustable_gaps = 0
            fixed_gaps_width = 0
            
            if num_items > 1:
                # If last item is marker, the gap before it is fixed
                if items[-1]['type'] == 'ayah_marker':
                    adjustable_gaps = max(0, num_items - 2)
                    fixed_gaps_width = MIN_WORD_SPACING # One fixed gap before marker
                else:
                    adjustable_gaps = num_items - 1
            
            min_required_width = content_width + fixed_gaps_width + (adjustable_gaps * MIN_WORD_SPACING)
            if min_required_width > max_min_width:
                max_min_width = min_required_width

            line_measurements.append({
                'items': items,
                'content_width': content_width,
                'adjustable_gaps': adjustable_gaps,
                'fixed_gaps_width': fixed_gaps_width,
                'min_required_width': min_required_width
            })

        # --- 2. Calculate Dynamic Page Width ---
        effective_page_width = PAGE_WIDTH - (2 * SIDE_MARGIN) # Default
        current_side_margin = SIDE_MARGIN

        if self.main_window.justify_text and line_measurements:
            # Filter for "full lines" to avoid using a very short last line as reference
            # We consider a line "full" if it's at least 65% of the widest line's content
            # This prevents justifying to a 2-word line which would make the page very narrow.
            max_content = max(l['content_width'] for l in line_measurements) if line_measurements else 0
            full_lines = [l for l in line_measurements if l['content_width'] > 0.65 * max_content]
            
            if not full_lines: 
                full_lines = line_measurements # Fallback if all lines are short

            # Find the shortest of the full lines
            shortest_line = min(full_lines, key=lambda x: x['content_width'])
            
            # Calculate Reference Width:
            # Content + Fixed Gaps + (Adjustable Gaps * VISUALLY_ACCEPTABLE_SPACING)
            # We use 2.5x MIN_SPACING (e.g. 12.5px) as the "acceptable" spacing for the shortest line.
            # This ensures the shortest line looks good (not too tight, not too spread).
            ACCEPTABLE_SPACING = 2.5 * MIN_WORD_SPACING
            reference_width = (shortest_line['content_width'] + 
                               shortest_line['fixed_gaps_width'] + 
                               (shortest_line['adjustable_gaps'] * ACCEPTABLE_SPACING))
            
            # The final width must be at least enough to hold the longest line with minimum spacing
            # otherwise the longest line will overlap.
            effective_page_width = max(reference_width, max_min_width)
            
            # Recenter the text block within the canvas
            current_side_margin = (PAGE_WIDTH - effective_page_width) / 2

        # --- 3. Render Phase ---
        current_y = TOP_MARGIN
        
        for i, line_data in enumerate(page_data): # Iterate original data to track Surahs
            # Check for Surah Header (Same logic as before)
            # We check the first word of the line
            if line_data:
                first_word = line_data[0]
                current_surah = first_word.get('surah')
                if current_surah and page_num == self.data_manager.sura_pages.get(current_surah) and current_surah not in self.main_window.rendered_sura_headers:
                    # Render Header
                    self.main_window.rendered_sura_headers.add(current_surah)
                    sura_name_arabic = self.main_window.data_manager.get_sura_name(current_surah)
                    sura_header_text = f"سورة {sura_name_arabic}"
                    
                    header_font = QFont(self.main_window.quran_text_display_font_family, font_size, QFont.Bold)
                    header_item = QGraphicsTextItem(sura_header_text)
                    header_item.setFont(header_font)
                    header_item.setDefaultTextColor(SURAH_NAME_COLOR)
                    
                    h_width = QFontMetrics(header_font).width(sura_header_text)
                    h_x = x_offset + (PAGE_WIDTH - h_width) / 2
                    header_item.setPos(h_x, current_y)
                    self.scene.addItem(header_item)
                    current_y += header_item.boundingRect().height() - 25

                    # Render Basmala/Isti'adha
                    if current_surah == 9:
                        b_text = "أَعُوذُ بِاللَّهِ مِنَ الشَّيْطَانِ الرَّجِيمِ"
                    elif current_surah != 1:
                        b_text = self.data_manager.get_basmala_text()
                    else:
                        b_text = "" # Fatiha has basmala as ayah 1

                    if b_text:
                        b_item = QGraphicsTextItem(b_text)
                        b_item.setFont(header_font) # Use same font for consistency
                        b_item.setDefaultTextColor(BASMALA_COLOR)
                        b_width = QFontMetrics(header_font).width(b_text)
                        b_x = x_offset + (PAGE_WIDTH - b_width) / 2
                        b_item.setPos(b_x, current_y)
                        self.scene.addItem(b_item)
                        current_y += b_item.boundingRect().height() - 10

            # --- Render Line Items ---
            metrics = line_measurements[i]
            items = metrics['items']
            
            if not items:
                current_y += line_height
                continue

            # Calculate Spacing for this line
            adjusted_spacing = MIN_WORD_SPACING
            
            # Special check for Fatiha Basmala (Surah 1, Ayah 1) - Center it, don't justify
            is_fatiha_basmala = (page_num == 1 and items[0]['data'].get('surah') == 1 and items[0]['data'].get('ayah') == 1)

            if self.main_window.justify_text and metrics['adjustable_gaps'] > 0 and not is_fatiha_basmala:
                # Available space for adjustable gaps
                # Total Width - Content - Fixed Gaps
                space_for_adjustable = effective_page_width - metrics['content_width'] - metrics['fixed_gaps_width']
                adjusted_spacing = space_for_adjustable / metrics['adjustable_gaps']
            
            # Start Position (Right aligned based on calculated margin)
            current_x = x_offset + PAGE_WIDTH - current_side_margin

            # If Fatiha Basmala, center it manually
            if is_fatiha_basmala:
                line_total_width = metrics['content_width'] + (len(items)-1) * MIN_WORD_SPACING
                center_offset = (PAGE_WIDTH - line_total_width) / 2
                current_x = x_offset + PAGE_WIDTH - center_offset

            for j, item in enumerate(items):
                item_type = item['type']
                item_data = item['data']
                item_width = item['width']
                text_to_draw = item['text']

                # Position: Right edge is at current_x
                item_x = current_x - item_width

                if item_type == 'word':
                    surah_no = item_data.get('surah')
                    aya_no = item_data.get('ayah')
                    word_id = item_data.get('word')
                    global_idx = f"{surah_no}:{aya_no}:{word_id}" if all([surah_no, aya_no, word_id is not None]) else ""

                    word_item = ClickableWord(text_to_draw, global_idx, page_num, self.data_manager, self.main_window)
                    word_item.setFont(quran_word_font)
                    word_item.setPos(item_x, current_y)
                    word_item.setDefaultTextColor(self.main_window.quran_text_color)
                    
                    # Highlight Rect
                    highlight_rect = QGraphicsRectItem(word_item.boundingRect())
                    highlight_rect.setPos(item_x, current_y)
                    highlight_rect.setPen(QPen(Qt.NoPen))
                    highlight_rect.setBrush(QColor(0,0,0,0))
                    highlight_rect.setZValue(0.5)
                    self._word_highlight_map[global_idx] = highlight_rect
                    
                    word_item.setZValue(1)
                    
                    # Connect signals
                    word_item.signals.word_clicked.connect(self.main_window.handle_word_click)
                    word_item.signals.set_start_clicked.connect(self.main_window.set_recitation_start)
                    word_item.signals.set_end_clicked.connect(self.main_window.set_recitation_end)
                    word_item.signals.select_page_clicked.connect(self.main_window.set_range_page)
                    word_item.signals.select_sura_clicked.connect(self.main_window.set_range_sura)
                    word_item.signals.select_juz_clicked.connect(self.main_window.set_range_juz)
                    word_item.signals.select_hizb_clicked.connect(self.main_window.set_range_hizb)
                    word_item.signals.select_rub_clicked.connect(self.main_window.set_range_rub)

                    # Visibility logic for recording mode
                    if hasattr(self.main_window, 'recording_mode') and self.main_window.recording_mode:
                        if hasattr(self.main_window, 'recitation_idx_map') and global_idx in self.main_window.recitation_idx_map:
                            word_item.setVisible(False)
                        else:
                            word_item.setVisible(True)
                    else:
                        word_item.setVisible(True)

                    self.scene.addItem(highlight_rect)
                    self.scene.addItem(word_item)
                    self._word_item_map[global_idx] = word_item

                elif item_type == 'ayah_marker' and self.main_window.show_aya_markers:
                    marker_item = QGraphicsTextItem(text_to_draw)
                    marker_item.setFont(ayah_marker_font)
                    marker_item.setDefaultTextColor(AYAH_MARKER_COLOR)
                    marker_item.setZValue(2)
                    
                    # Center vertically
                    marker_rect = marker_item.boundingRect()
                    marker_y = current_y + (line_height - marker_rect.height()) / 2
                    marker_item.setPos(item_x, marker_y)
                    self.scene.addItem(marker_item)

                # Determine spacing after this item
                gap = MIN_WORD_SPACING # Default
                
                if self.main_window.justify_text and not is_fatiha_basmala:
                    # If this is NOT the last item
                    if j < len(items) - 1:
                        # Check if next item is marker
                        next_is_marker = (items[j+1]['type'] == 'ayah_marker')
                        if next_is_marker:
                            gap = MIN_WORD_SPACING # Fixed gap before marker
                        else:
                            gap = adjusted_spacing # Adjusted gap between words

                current_x -= (item_width + gap)

            current_y += line_height

        # --- Page Number ---
        page_num_font = QFont(self.main_window.font_family, 40)
        page_num_text_item = QGraphicsTextItem(str(page_num))
        page_num_text_item.setFont(page_num_font)
        page_num_text_item.setDefaultTextColor(QColor("#1565C0"))
        page_num_bounding_rect = page_num_text_item.boundingRect()
        page_num_x = x_offset + (PAGE_WIDTH - page_num_bounding_rect.width()) / 2
        page_num_y = PAGE_HEIGHT - (BOTTOM_MARGIN / 2) - (page_num_bounding_rect.height() / 2) - 50
        page_num_text_item.setPos(page_num_x, page_num_y)
        page_num_text_item.setZValue(2)
        self.scene.addItem(page_num_text_item)

        return PAGE_WIDTH


    def _apply_scale(self):
        """
        Applies the current scaling factor to the view's transformation matrix.
        """
        transform = self.view.transform()
        # Reset scaling to 1.0 before applying the new scale factor
        transform.setMatrix(1, transform.m12(), transform.m13(),
                            transform.m21(), 1, transform.m23(),
                            transform.m31(), transform.m32(), transform.m33())
        self.view.setTransform(transform)
        
        # Apply the new scale
        self.view.scale(self.main_window.scale_factor, self.main_window.scale_factor)
