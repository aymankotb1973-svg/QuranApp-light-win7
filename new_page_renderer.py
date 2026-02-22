# -*- coding: utf-8 -*-
"""
new_page_renderer.py - Renders Quran pages onto a QGraphicsScene.
A simplified renderer for displaying static, pre-formatted Quran pages.
"""

from PyQt5.QtGui import QFont, QColor, QBrush, QPen, QPixmap, QFontMetrics
from PyQt5.QtWidgets import QGraphicsTextItem, QGraphicsRectItem
from PyQt5.QtCore import Qt

from new_utils import resource_path
import re

class PageRenderer:
    """
    Manages the rendering of one or two Quran pages onto a QGraphicsScene.
    """
    def __init__(self, main_app, scene, view, data_manager):
        self.main_app = main_app
        self.scene = scene
        self.view = view
        self.data_manager = data_manager
        self.border_pixmap = None
        self._current_rendered_pages = set()

        try:
            # Use the new utils resource_path
            border_image_path = resource_path("assets/page_border.png")
            if border_image_path:
                self.border_pixmap = QPixmap(border_image_path)
            else:
                print("!!! Page border image not found.")
        except Exception as e:
            print(f"!!! Error loading page border image: {e}")

    def render_pages(self, page_num):
        """
        Renders the specified page, and the facing page if in two-page mode.
        """
        # For playlist-momorize-quran, it seems to be a two-page view by default
        # where the left page is page_num + 1 and the right is page_num
        is_two_page_view = True # Based on playlist-momorize-quran.py's render_page
        
        pages_to_render = {page_num}
        if is_two_page_view:
             pages_to_render.add(page_num + 1)
        
        # Prevent re-rendering the same pages
        if pages_to_render == self._current_rendered_pages:
            return

        self.scene.clear()
        self._current_rendered_pages = pages_to_render

        page_on_left = page_num + 1
        page_on_right = page_num
        
        if page_on_right > 604: page_on_right = 0
        if page_on_left > 604: page_on_left = 0

        left_page_width = self._render_single_page(page_on_left, 0) if page_on_left > 0 else 0
        right_page_offset = left_page_width + 20 if left_page_width > 0 else 0
        if page_on_right > 0:
            self._render_single_page(page_on_right, right_page_offset)

        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        self._apply_scale()


    def _render_single_page(self, page_num, x_offset):
        """
        Renders a single page using a static layout algorithm.
        """
        page_layout_data = self.data_manager.get_page_layout(page_num)
        page_metadata = self.data_manager.get_page_metadata(page_num)

        if not page_layout_data:
            print(f"No layout data for page {page_num}")
            return 0

        # --- Layout Constants ---
        PAGE_WIDTH = 660
        PAGE_HEIGHT = 800
        TOP_MARGIN = 60
        BOTTOM_MARGIN = 100
        SIDE_MARGIN = 70
        LINE_SPACING_FACTOR = 1.8
        MIN_WORD_SPACING = 5
        
        font_size = self.main_app.font_size
        quran_font_family = self.main_app.font_family
        
        quran_word_font = QFont(quran_font_family, font_size)
        quran_word_font.setBold(True)
        fm = QFontMetrics(quran_word_font)
        line_height = fm.height() * LINE_SPACING_FACTOR

        # --- Background and Border ---
        bg_rect_item = self.scene.addRect(x_offset, 0, PAGE_WIDTH, PAGE_HEIGHT, QPen(Qt.NoPen), QBrush(self.main_app.page_bg_color))
        bg_rect_item.setZValue(-1)

        if self.border_pixmap and not self.border_pixmap.isNull():
            border_item = self.scene.addPixmap(self.border_pixmap)
            border_item.setPixmap(self.border_pixmap.scaled(
                int(PAGE_WIDTH), int(PAGE_HEIGHT), 
                Qt.IgnoreAspectRatio, Qt.SmoothTransformation
            ))
            border_item.setPos(x_offset, 0)
            border_item.setZValue(0)

        current_y = TOP_MARGIN

        # --- Page Headers (Surah Name, Juz) ---
        if page_metadata:
            header_font = QFont("Arial", 16, QFont.Bold)
            sura_name = page_metadata.get("sura_name", "")
            juz_number = page_metadata.get("juz_number")

            header_text_left = f"الجزء {juz_number}" if juz_number else ""
            header_text_right = sura_name if sura_name else ""
            
            # Left-aligned header (Juz)
            left_header = QGraphicsTextItem(header_text_left)
            left_header.setFont(header_font)
            left_header.setDefaultTextColor(Qt.black)
            left_header.setPos(x_offset + SIDE_MARGIN, TOP_MARGIN / 2 - left_header.boundingRect().height() / 2)
            self.scene.addItem(left_header)
            
            # Right-aligned header (Surah)
            right_header = QGraphicsTextItem(header_text_right)
            right_header.setFont(header_font)
            right_header.setDefaultTextColor(Qt.black)
            header_width = right_header.boundingRect().width()
            right_header.setPos(x_offset + PAGE_WIDTH - SIDE_MARGIN - header_width, TOP_MARGIN / 2 - right_header.boundingRect().height() / 2)
            self.scene.addItem(right_header)

        # --- Text Rendering ---
        drawable_width = PAGE_WIDTH - (2 * SIDE_MARGIN)
        
        # Check if we need to render Basmalah
        first_word = page_layout_data[0][0]
        sura_no = first_word.get('surah')
        aya_no = first_word.get('ayah')
        
        # Render Basmalah if it's the first ayah of any surah except Al-Fatiha and At-Tawbah
        if aya_no == 1 and sura_no not in [1, 9]:
            basmalah_font = QFont(quran_font_family, font_size + 4, QFont.Bold)
            basmalah_text = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
            basmalah_item = QGraphicsTextItem(basmalah_text)
            basmalah_item.setFont(basmalah_font)
            basmalah_w = basmalah_item.boundingRect().width()
            basmalah_x = x_offset + (PAGE_WIDTH - basmalah_w) / 2
            basmalah_item.setPos(basmalah_x, current_y)
            self.scene.addItem(basmalah_item)
            current_y += fm.height() * 1.5

        for line_data in page_layout_data:
            words_in_line = [w for w in line_data if w.get('char_type') != 'end']
            if not words_in_line:
                continue

            total_content_width = sum(fm.width(w['text']) for w in words_in_line)
            
            num_gaps = len(words_in_line) - 1
            adjusted_word_spacing = MIN_WORD_SPACING
            # Simple justification, can be improved
            if num_gaps > 0:
                space_for_gaps = drawable_width - total_content_width
                if space_for_gaps > (num_gaps * MIN_WORD_SPACING):
                    adjusted_word_spacing = space_for_gaps / num_gaps

            current_x = x_offset + PAGE_WIDTH - SIDE_MARGIN
            for word_data in reversed(words_in_line):
                word_text = word_data['text']
                word_width = fm.width(word_text)
                
                word_x = current_x - word_width
                
                word_item = QGraphicsTextItem(word_text)
                word_item.setFont(quran_word_font)
                word_item.setDefaultTextColor(Qt.black)
                word_item.setPos(word_x, current_y)
                self.scene.addItem(word_item)
                
                current_x -= (word_width + adjusted_word_spacing)

            current_y += line_height

        # --- Page Number ---
        page_num_font = QFont("Arial", 14)
        page_num_item = QGraphicsTextItem(str(page_num))
        page_num_item.setFont(page_num_font)
        page_num_w = page_num_item.boundingRect().width()
        page_num_x = x_offset + (PAGE_WIDTH - page_num_w) / 2
        page_num_y = PAGE_HEIGHT - (BOTTOM_MARGIN / 2) - page_num_item.boundingRect().height() / 2
        page_num_item.setPos(page_num_x, page_num_y)
        self.scene.addItem(page_num_item)

        return PAGE_WIDTH

    def _apply_scale(self):
        """ Applies the current scaling factor to the view. """
        transform = self.view.transform()
        # Reset scaling to 1.0 before applying new scale
        transform.setMatrix(1, transform.m12(), transform.m13(),
                            transform.m21(), 1, transform.m23(),
                            transform.m31(), transform.m32(), transform.m33())
        self.view.setTransform(transform)
        self.view.scale(self.main_app.scale_factor, self.main_app.scale_factor)