# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import sys
import re
import json
import math

# --- FIX FOR OPENGL 1.1 ERROR ---
# Force Kivy to use ANGLE (DirectX) backend on Windows
# This must be done BEFORE importing any other Kivy modules
if sys.platform == 'win32':
    os.environ['KIVY_GL_BACKEND'] = 'angle_sdl2'
# --- END FIX ---

import threading
import requests
from datetime import datetime, timedelta

# إعداد البيئة للأندرويد
os.environ["KIVY_NO_ARGS"] = "1"

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDButton, MDButtonText, MDButtonIcon, MDFabButton
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.textfield import MDTextField
from kivymd.uix.slider import MDSlider
from kivymd.uix.list import MDListItem, MDListItemHeadlineText

# --- KivyMD 2.0 Compatibility Wrappers ---
class MDRaisedButton(MDButton):
    def __init__(self, *args, **kwargs):
        text = kwargs.pop("text", "")
        text_color = kwargs.pop("text_color", None)
        font_size = kwargs.pop("font_size", None)
        font_name = kwargs.pop("font_name", None)

        if "style" not in kwargs:
            kwargs["style"] = "elevated"
        if "md_bg_color" in kwargs:
            kwargs["theme_bg_color"] = "Custom"
        super().__init__(*args, **kwargs)
        if text:
            t_kwargs = {"text": text}
            if text_color:
                t_kwargs["theme_text_color"] = "Custom"
                t_kwargs["text_color"] = text_color
            if font_size:
                t_kwargs["font_size"] = font_size
            if font_name:
                t_kwargs["font_name"] = font_name
            self.add_widget(MDButtonText(**t_kwargs))

class MDFlatButton(MDButton):
    def __init__(self, *args, **kwargs):
        text = kwargs.pop("text", "")
        text_color = kwargs.pop("text_color", None)
        font_size = kwargs.pop("font_size", None)
        font_name = kwargs.pop("font_name", None)

        if "style" not in kwargs:
            kwargs["style"] = "text"
        super().__init__(*args, **kwargs)
        if text:
            t_kwargs = {"text": text}
            if text_color:
                t_kwargs["theme_text_color"] = "Custom"
                t_kwargs["text_color"] = text_color
            if font_size:
                t_kwargs["font_size"] = font_size
            if font_name:
                t_kwargs["font_name"] = font_name
            self.add_widget(MDButtonText(**t_kwargs))

class CustomIconButton(MDButton):
    def __init__(self, *args, **kwargs):
        icon = kwargs.pop("icon", "")
        text_color = kwargs.pop("text_color", None)
        icon_color = kwargs.pop("icon_color", None)

        if "style" not in kwargs:
            kwargs["style"] = "text"
        super().__init__(*args, **kwargs)
        if icon:
            i_kwargs = {"icon": icon}
            final_color = icon_color if icon_color else text_color
            if final_color:
                i_kwargs["theme_icon_color"] = "Custom"
                i_kwargs["icon_color"] = final_color
            self.add_widget(MDButtonIcon(**i_kwargs))

class MDFloatingActionButton(MDFabButton):
    def __init__(self, *args, **kwargs):
        icon = kwargs.pop("icon", "")
        super().__init__(*args, **kwargs)
        if icon:
            self.add_widget(MDButtonIcon(icon=icon))

class OneLineListItem(MDListItem):
    def __init__(self, *args, **kwargs):
        text = kwargs.pop("text", "")
        super().__init__(*args, **kwargs)
        if text:
            self.add_widget(MDListItemHeadlineText(text=text))
# -----------------------------------------

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.textinput import TextInput
from kivy.uix.slider import Slider
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.clock import Clock
from kivy.uix.spinner import Spinner
from kivy.uix.filechooser import FileChooserIconView
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.modalview import ModalView
from kivy.graphics import Color, RoundedRectangle, BoxShadow, Rectangle, Line
from kivy.animation import Animation
from kivy.metrics import dp
from kivy.core.text import LabelBase # استيراد للتحكم في الخطوط
from kivy.uix.behaviors import ButtonBehavior

import arabic_reshaper
from bidi.algorithm import get_display

# --- إعداد Reshaper للحفاظ على التشكيل ---
configuration = {
    'delete_harakat': False,
    'support_ligatures': True,
}
reshaper = arabic_reshaper.ArabicReshaper(configuration=configuration)

# محاولة استيراد مكتبات الصوت (للمراجعة الصوتية)
try:
    import sounddevice as sd
    import numpy as np
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False

# محاولة استيراد مدير البيانات
try:
    from quran_data_manager import QuranDataManager
except ImportError:
    # طباعة الخطأ بالتفصيل لمعرفة المكتبة الناقصة
    import traceback
    traceback.print_exc()
    QuranDataManager = None
    print("Warning: Could not import QuranDataManager")

# محاولة استيراد مدير المعلومات (للمعاني والتفسير)
try:
    from quran_info_manager import QuranInfoManager
except ImportError:
    QuranInfoManager = None
    print("Warning: Could not import QuranInfoManager")

# محاولة استيراد مدير المستخدمين
try:
    from user_profile import UserManager
except ImportError:
    UserManager = None

# --- إعداد الخطوط (حل مشكلة المربعات واختفاء النص) ---
font_path = "Roboto" # الخط الافتراضي

# 1. خطوط ويندوز (الأولوية لضمان ظهور النص)
if sys.platform == "win32":
    win_dir = os.environ.get('WINDIR', 'C:\\Windows')
    fonts_dir = os.path.join(win_dir, 'Fonts')
    # استخدام Arial لأنه الأكثر توافقاً وموثوقية لظهور النص العربي
    font_path = os.path.join(fonts_dir, 'arial.ttf')
# 2. خط المشروع (احتياطي)
elif os.path.exists("fonts/uthmanic.ttf"):
    font_path = "fonts/uthmanic.ttf"

print(f"DEBUG: Using font: {font_path}")
# استبدال الخط الافتراضي (Roboto) بالخط الذي اخترناه
LabelBase.register(name='Roboto', fn_regular=font_path, fn_bold=font_path)

# --- Register Uthmanic font for Ayah numbers ---
uthmanic_font_path = "fonts/uthmanic.ttf"
if os.path.exists(uthmanic_font_path):
    LabelBase.register(name='UthmanicFont', fn_regular=uthmanic_font_path)
    print(f"DEBUG: Registered font: {uthmanic_font_path} as UthmanicFont")
else:
    # Fallback to main font if specific Uthmanic font not found
    LabelBase.register(name='UthmanicFont', fn_regular=font_path)

# --- إعداد خط الرموز (Emojis) لحل مشكلة المربعات ---
emoji_font = 'Roboto'  # افتراضي
if sys.platform == 'win32':
    win_fonts = os.path.join(os.environ['WINDIR'], 'Fonts')
    if os.path.exists(os.path.join(win_fonts, 'seguiemj.ttf')):
        emoji_font = os.path.join(win_fonts, 'seguiemj.ttf')

# دالة مساعدة للنص العربي
def ar_text(text):
    if not text: return ""
    try:
        reshaped_text = reshaper.reshape(text)
        return get_display(reshaped_text)
    except:
        return text

# --- ثوابت مساعدة ---
JUZ_START_PAGES = {
    1:1, 2:22, 3:42, 4:62, 5:82, 6:102, 7:122, 8:142, 9:162, 10:182,
    11:202, 12:222, 13:242, 14:262, 15:282, 16:302, 17:322, 18:342, 19:362, 20:382,
    21:402, 22:422, 23:442, 24:462, 25:482, 26:502, 27:522, 28:542, 29:562, 30:582
}

# --- Modern UI Constants ---
COLOR_PRIMARY = (0.0, 0.3, 0.25, 1)  # Deep Teal
COLOR_BG = (0.96, 0.96, 0.96, 1)     # Off-White
COLOR_SURFACE = (1, 1, 1, 1)         # White
COLOR_TEXT = (0.1, 0.1, 0.1, 1)
COLOR_ACCENT = (0.8, 0.6, 0.2, 1)    # Gold/Accent
STD_HEIGHT = dp(50) # Unified height for controls

HIGHLIGHT_COLORS = {
    'أحمر': 'ff0000',
    'أخضر': '008000',
    'أزرق': '0000ff',
    'ذهبي': 'daa520',
    'بفسجي': '800080'
}

class YusrProgressBar(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(8)
        self.value = 0.0  # 0.0 to 1.0
        self.radius = [dp(4)]
        
        with self.canvas.before:
            Color(0.85, 0.85, 0.85, 1)  # Background
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=self.radius)
            Color(*COLOR_PRIMARY)  # Foreground
            self.fg_rect = RoundedRectangle(pos=self.pos, size=(0, self.height), radius=self.radius)
            
        self.bind(pos=self.update_rect, size=self.update_rect)

    def on_value(self, instance, value):
        # Animate the change in width
        new_width = self.width * max(0, min(1, value))
        Animation(size=(new_width, self.height), duration=0.4, t='out_quad').start(self.fg_rect)

    def update_rect(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size
        self.fg_rect.pos = self.pos
        self.fg_rect.size = (self.width * self.value, self.height)

class VoiceSensor:
    def __init__(self):
        self.stream = None
        self.is_recording = False

    def start(self):
        if not SD_AVAILABLE:
            print("SoundDevice not available")
            return
        try:
            self.stream = sd.InputStream(channels=1, samplerate=44100)
            self.stream.start()
            self.is_recording = True
        except Exception as e:
            print(f"Error starting audio: {e}")

    def get_volume(self):
        if not self.is_recording or not self.stream:
            return 0
        try:
            # Read a small chunk
            data, overflow = self.stream.read(1024)
            if len(data) == 0: return 0
            # Calculate RMS amplitude
            rms = np.sqrt(np.mean(data**2))
            return rms * 10 # Scale up a bit
        except Exception as e:
            return 0

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.is_recording = False

class ArabicTextInput(MDTextField):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Use Arial on Windows for better Arabic support, otherwise Roboto
        self.font_name = 'arial' if sys.platform == 'win32' else 'Roboto'
        self.font_name_hint_text = 'Roboto'
        self.base_direction = 'rtl'
        self.halign = 'right'
        self.mode = "outlined"
        self._logical_text = self.text if self.text else ""
        if self._logical_text:
             self.text = ar_text(self._logical_text)
        # KivyMD handles the border and styling automatically

    def insert_text(self, substring, from_undo=False):
        # Simple filter check
        if self.input_filter == 'int' and not substring.isdigit():
            return
        self._logical_text += substring
        self.text = ar_text(self._logical_text)
        self.cursor = (0, 0) # Move cursor to visual start (left) for RTL

    def do_backspace(self, from_undo=False, mode='bkspc'):
        if self._logical_text:
            self._logical_text = self._logical_text[:-1]
            self.text = ar_text(self._logical_text)
            self.cursor = (0, 0)

    def get_text(self):
        return self._logical_text

    def set_text_value(self, text):
        self._logical_text = text
        self.text = ar_text(text)


# --- Modern UI Widgets ---

class ModernCard(MDCard):
    def __init__(self, text="", icon="", bg_color=COLOR_SURFACE, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = dp(10)
        self.spacing = dp(10)
        self.radius = [dp(15)]
        self.ripple_behavior = True
        self.elevation = 2
        
        if bg_color:
            self.md_bg_color = bg_color

        content_color = (1, 1, 1, 1) if bg_color != COLOR_SURFACE else COLOR_PRIMARY
        text_color = (1, 1, 1, 1) if bg_color != COLOR_SURFACE else COLOR_TEXT

        if icon:
            self.add_widget(Label(text=icon, font_size='36sp', color=content_color, font_name=emoji_font))

        self.text_label = MDLabel(text=ar_text(text), font_style='Title', theme_text_color="Custom", text_color=text_color, halign='center', font_name='Roboto')
        self.add_widget(self.text_label)



class BottomNavBar(BoxLayout):
    def __init__(self, current_tab='mushaf', show_arrows=False, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint = (1, None)
        self.height = dp(65)
        self.padding = [dp(10), dp(5)]
        self.spacing = dp(10)
        
        with self.canvas.before:
            Color(*COLOR_SURFACE)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(20), dp(20), 0, 0])
            Color(0, 0, 0, 0.05)
            self.shadow = BoxShadow(pos=self.pos, size=self.size, offset=(0, 5), spread_radius=[-2, -2], blur_radius=15)
        self.bind(pos=self.update_bg, size=self.update_bg)

        if show_arrows:
            # Special layout for ReaderScreen
            btn_prev = self.create_nav_item("chevron-left", "prev_page", False)
            btn_prev.unbind(on_press=self.change_screen)
            btn_prev.bind(on_press=self.go_prev_page)
            
            btn_home = self.create_nav_item("home", "home", False)
            
            btn_search = self.create_nav_item("magnify", "search", False)

            btn_next = self.create_nav_item("chevron-right", "next_page", False)
            btn_next.unbind(on_press=self.change_screen)
            btn_next.bind(on_press=self.go_next_page)

            self.add_widget(btn_prev)
            self.add_widget(btn_home)
            self.add_widget(btn_search)
            self.add_widget(btn_next)
        else:
            # Standard layout for other screens
            self.add_nav_item("home", 'home', current_tab == 'home')
            self.add_nav_item("book-open-page-variant", 'reader', current_tab == 'mushaf')
            self.add_nav_item("magnify", 'search', current_tab == 'search')
            self.add_nav_item("clipboard-list", 'plans_home', current_tab == 'review')
            self.add_nav_item("cog", 'settings', current_tab == 'settings')

    def create_nav_item(self, icon_name, screen_name, is_active, **kwargs):
        theme_color = "Primary" if is_active else "Hint"
        btn = CustomIconButton(icon=icon_name, theme_text_color=theme_color, **kwargs)
        btn.screen_name = screen_name
        btn.bind(on_press=self.change_screen)
        return btn

    def add_nav_item(self, icon_name, screen_name, is_active):
        btn = self.create_nav_item(icon_name, screen_name, is_active)
        self.add_widget(btn)

    def change_screen(self, instance):
        App.get_running_app().root.current = instance.screen_name

    def go_prev_page(self, instance):
        app = App.get_running_app()
        if app.root.current == 'reader':
            reader_screen = app.root.get_screen('reader')
            reader_screen.prev_page(None)

    def go_next_page(self, instance):
        app = App.get_running_app()
        if app.root.current == 'reader':
            reader_screen = app.root.get_screen('reader')
            reader_screen.next_page(None)

    def update_bg(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size
        self.shadow.pos = self.pos
        self.shadow.size = self.size

class FAB(Button):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (dp(56), dp(56))
        self.background_normal = ''
        self.background_color = (0,0,0,0)
        self.text = "+"
        self.font_size = '30sp'
        self.color = (1, 1, 1, 1)
        
        with self.canvas.before:
            Color(0, 0, 0, 0.2)
            self.shadow = BoxShadow(pos=self.pos, size=self.size, offset=(0, -4), spread_radius=[-2, -2], blur_radius=10)
            Color(*COLOR_ACCENT)
            self.circle = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(28)])
        self.bind(pos=self.update_shape, size=self.update_shape)

    def update_shape(self, *args):
        self.circle.pos = self.pos
        self.circle.size = self.size
        self.shadow.pos = self.pos
        self.shadow.size = self.size

class IndexBottomSheet(ModalView):
    def __init__(self, on_select_callback, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, 0.8)
        self.pos_hint = {'bottom': 1}
        self.background_color = (0, 0, 0, 0.5)
        self.on_select = on_select_callback
        self.data_manager = None
        
        # Content built in open() to ensure data is ready
        self.container = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Background
        with self.container.canvas.before:
            Color(*COLOR_SURFACE)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(20), dp(20), 0, 0])
        self.container.bind(pos=lambda inst, v: setattr(inst.canvas.before.children[-1], 'pos', v))
        self.container.bind(size=lambda inst, v: setattr(inst.canvas.before.children[-1], 'size', v))
        
        # Tabs Header
        tabs_box = BoxLayout(size_hint_y=None, height=dp(40), spacing=10)
        
        def create_tab(text, callback):
            btn = MDRaisedButton(text=ar_text(text), md_bg_color=COLOR_ACCENT, font_name='Roboto', size_hint_x=1)
            btn.bind(on_release=callback)
            return btn

        tabs_box.add_widget(create_tab("السور", lambda x: self.show_suras()))
        tabs_box.add_widget(create_tab("الأجزاء", lambda x: self.show_juzs()))
        tabs_box.add_widget(create_tab("الصفحات", lambda x: self.show_pages()))
        
        self.container.add_widget(tabs_box)
        
        # List
        self.scroll = ScrollView()
        self.grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(2))
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll.add_widget(self.grid)
        self.container.add_widget(self.scroll)
        
        self.add_widget(self.container)

    def populate(self, data_manager):
        self.data_manager = data_manager
        self.show_suras()

    def show_suras(self):
        self.grid.clear_widgets()
        self.grid.cols = 1
        self.grid.spacing = dp(2)
        for i in range(1, 115):
            sura_name = self.data_manager.get_sura_name(i)
            btn = Button(
                text=ar_text(f"{i}. {sura_name}"), 
                size_hint_y=None, 
                height=dp(50), 
                background_normal='',
                background_color=(0,0,0,0),
                color=COLOR_TEXT
            )
            # Calculate page here
            btn.target_page = self.data_manager.sura_pages.get(i, 1)
            btn.bind(on_press=self.item_selected)
            self.grid.add_widget(btn)

    def show_juzs(self):
        self.grid.clear_widgets()
        self.grid.cols = 1
        self.grid.spacing = dp(2)
        for i in range(1, 31):
            # Get start page for Juz
            page = JUZ_START_PAGES.get(i, 1)
            if self.data_manager and hasattr(self.data_manager, 'juz_pages') and self.data_manager.juz_pages:
                 page = self.data_manager.juz_pages.get(i, page)
            
            btn = Button(
                text=ar_text(f"الجزء {i}"), 
                size_hint_y=None, 
                height=dp(50), 
                background_normal='',
                background_color=(0,0,0,0),
                color=COLOR_TEXT
            )
            btn.target_page = page
            btn.bind(on_press=self.item_selected)
            self.grid.add_widget(btn)

    def show_pages(self):
        self.grid.clear_widgets()
        self.grid.cols = 4 # Grid for pages
        self.grid.spacing = dp(5)
        for i in range(1, 605):
            btn = Button(
                text=str(i), 
                size_hint_y=None, 
                height=dp(50), 
                background_normal='', 
                background_color=COLOR_ACCENT, 
                color=(1,1,1,1)
            )
            btn.target_page = i
            btn.bind(on_press=self.item_selected)
            self.grid.add_widget(btn)
            
    def item_selected(self, instance):
        self.dismiss()
        if self.on_select:
            self.on_select(instance.target_page)

class WordInfoPopup(ModalView):
    def __init__(self, info_manager, data_manager, sura, aya, word_id, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (0.95, 0.85)
        self.background_color = (0, 0, 0, 0.8)
        self.info_manager = info_manager
        self.data_manager = data_manager
        self.sura = sura
        self.aya = aya
        self.word_id = word_id
        self.font_size = 18 # Initial font size for content
        
        # Get Global ID
        self.global_id = self.data_manager.get_global_word_id_from_local(sura, aya, word_id) if self.data_manager else None
        
        self.layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        with self.layout.canvas.before:
            Color(*COLOR_SURFACE)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(15)])
        self.layout.bind(pos=lambda i,v: setattr(i.canvas.before.children[-1], 'pos', v), size=lambda i,v: setattr(i.canvas.before.children[-1], 'size', v))
        
        # Header
        sura_name = self.data_manager.get_sura_name(sura) if self.data_manager else str(sura)
        self.title_lbl = Label(text=ar_text(f"سورة {sura_name} - آية {aya}"), color=COLOR_PRIMARY, font_size='20sp', bold=True, size_hint_y=None, height=dp(40), font_name='Roboto')
        self.layout.add_widget(self.title_lbl)
        
        # Tabs Area (Horizontal Scroll for many buttons)
        tabs_scroll = ScrollView(size_hint_y=None, height=dp(60), do_scroll_x=True, do_scroll_y=False)
        self.tabs_box = GridLayout(rows=1, spacing=dp(5), size_hint_x=None, padding=dp(5))
        self.tabs_box.bind(minimum_width=self.tabs_box.setter('width'))
        
        # Define Tabs
        self.active_callback = self.show_meaning # Default
        tabs = [
            ("المعنى", self.show_meaning),
            ("التفسير", self.show_tafsir),
            ("الإعراب", self.show_eerab),
            ("أسباب النزول", self.show_nozool),
            ("التدبر", self.show_tadabbur)
        ]
        
        def create_tab_callback(cb):
            def on_press(instance):
                self.active_callback = cb
                cb()
            return on_press

        for title, callback in tabs:
            btn = MDRaisedButton(text=ar_text(title), md_bg_color=COLOR_ACCENT, font_name='Roboto', font_size='16sp')
            btn.bind(on_release=create_tab_callback(callback))
            self.tabs_box.add_widget(btn)
            
        tabs_scroll.add_widget(self.tabs_box)
        self.layout.add_widget(tabs_scroll)

        # Content Area
        self.content_scroll = ScrollView()
        self.content_lbl = Label(text=ar_text("جاري التحميل..."), color=COLOR_TEXT, size_hint_y=None, markup=True, halign='right', valign='top', font_name='Roboto', font_size='18sp', padding=(dp(10), dp(10)))
        self.content_lbl.bind(texture_size=self.content_lbl.setter('size'))
        self.content_lbl.bind(width=lambda instance, value: setattr(instance, 'text_size', (value, None)))
        self.content_scroll.add_widget(self.content_lbl)
        self.layout.add_widget(self.content_scroll)
        
        # --- NEW: Bottom Bar for Navigation and Controls ---
        bottom_bar = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(5), padding=(dp(5), 0))
        
        # Word Nav
        btn_prev_word = MDRaisedButton(text=ar_text("كلمة >>"), on_press=self.go_prev_word)
        btn_next_word = MDRaisedButton(text=ar_text("<< كلمة"), on_press=self.go_next_word)
        
        # Ayah Nav
        btn_prev_ayah = MDRaisedButton(text=ar_text("الآية السابقة"), on_press=self.go_prev_ayah, font_name='Roboto')
        btn_next_ayah = MDRaisedButton(text=ar_text("الآية التالية"), on_press=self.go_next_ayah, font_name='Roboto')
        
        # Font Size
        btn_zoom_out = MDRaisedButton(text="-", on_press=self.zoom_out, size_hint_x=0.15)
        btn_zoom_in = MDRaisedButton(text="+", on_press=self.zoom_in, size_hint_x=0.15)

        bottom_bar.add_widget(btn_prev_word)
        bottom_bar.add_widget(btn_next_word)
        bottom_bar.add_widget(Label(size_hint_x=0.05)) # Spacer
        bottom_bar.add_widget(btn_prev_ayah)
        bottom_bar.add_widget(btn_next_ayah)
        bottom_bar.add_widget(Label(size_hint_x=0.05)) # Spacer
        bottom_bar.add_widget(btn_zoom_out)
        bottom_bar.add_widget(btn_zoom_in)
        
        # Close
        btn_close = MDFlatButton(text=ar_text("إغلاق"), on_release=self.dismiss, size_hint_y=None, height=dp(40), font_name='Roboto')
        bottom_bar.add_widget(btn_close)

        self.layout.add_widget(bottom_bar)
        
        self.add_widget(self.layout)
        
        # Load initial data (Meaning)
        self.show_meaning()

    def load_data(self):
        db_ids = self.data_manager.get_db_ids_from_global(self.global_id)
        local_info = self.data_manager.global_to_local_map.get(self.global_id)
        
        if not db_ids or not local_info:
            self.title_lbl.text = ar_text("خطأ في البيانات")
            return
            
        sura_local, aya_local, word_local = local_info
        
        # Update current context
        self.sura = sura_local
        self.aya = aya_local
        self.word_id = word_local
        
        sura_name = self.data_manager.get_sura_name(sura_local)
        self.title_lbl.text = ar_text(f"سورة {sura_name} - آية {aya_local}")
        
        # Reload the currently visible tab's content
        if hasattr(self, 'active_callback'):
            self.active_callback()

    def clear_content(self):
        self.content_scroll.clear_widgets()
        self.content_lbl = Label(text="", color=COLOR_TEXT, size_hint_y=None, markup=True, halign='right', valign='top', font_name='Roboto', font_size='18sp', padding=(dp(10), dp(10)))
        self.content_lbl.bind(texture_size=self.content_lbl.setter('size'))
        self.content_lbl.bind(width=lambda instance, value: setattr(instance, 'text_size', (value, None)))
        self.content_scroll.add_widget(self.content_lbl)

    def show_meaning(self):
        self.clear_content()
        if not self.info_manager or not self.global_id:
            self.content_lbl.text = ar_text("بيانات غير متوفرة")
            return
        
        db_ids = self.data_manager.get_db_ids_from_global(self.global_id)
        if not db_ids:
             self.content_lbl.text = ar_text("لم يتم العثور على المعرف")
             return
        sura_db, aya_db, word_db = db_ids

        val, title = self.info_manager.get_word_data("meaning", sura_db, aya_db, word_db)
        if val:
            text = f"[b][color=#8B0000]{ar_text(title or '')}[/color][/b]\n\n{ar_text(val)}"
            self.content_lbl.text = text
            self._update_font_size()
        else:
            self.content_lbl.text = ar_text("لا يوجد معنى متاح")

    # --- NEW METHODS for navigation and zoom ---
    def _update_font_size(self):
        # This method will apply the current font size to all content labels
        font_size_str = f"{self.font_size}sp"
        if hasattr(self, 'content_lbl'):
            self.content_lbl.font_size = font_size_str
        # Also need to handle the tafsir label if it exists
        if self.content_scroll.children and isinstance(self.content_scroll.children[0], BoxLayout):
            container = self.content_scroll.children[0]
            for widget in container.children:
                if isinstance(widget, Label) and not hasattr(widget, 'is_title'):
                    widget.font_size = font_size_str

    def zoom_in(self, instance):
        self.font_size += 2
        self._update_font_size()

    def zoom_out(self, instance):
        if self.font_size > 12:
            self.font_size -= 2
            self._update_font_size()

    def go_prev_word(self, instance):
        if self.global_id and self.global_id > 1:
            self.global_id -= 1
            self.load_data()

    def go_next_word(self, instance):
        # Assuming max global_id is around 77430
        if self.global_id and self.global_id < 77430:
            self.global_id += 1
            self.load_data()

    def go_prev_ayah(self, instance):
        if not self.data_manager: return
        
        target_sura = self.sura
        target_aya = self.aya - 1
        
        if target_aya < 1:
            target_sura -= 1
            if target_sura < 1: return # Reached beginning of Quran
            target_aya = self.data_manager.sura_aya_counts.get(target_sura, 1)
        
        new_global_id = self.data_manager.get_global_word_id_from_local(target_sura, target_aya, 1)
        if new_global_id:
            self.global_id = new_global_id
            self.load_data()

    def go_next_ayah(self, instance):
        if not self.data_manager: return
        
        max_aya = self.data_manager.sura_aya_counts.get(self.sura, 0)
        
        target_sura = self.sura
        target_aya = self.aya + 1
        
        if target_aya > max_aya:
            target_sura += 1
            if target_sura > 114: return # Reached end of Quran
            target_aya = 1
            
        new_global_id = self.data_manager.get_global_word_id_from_local(target_sura, target_aya, 1)
        if new_global_id:
            self.global_id = new_global_id
            self.load_data()

    def show_tafsir(self):
        self.content_scroll.clear_widgets()
        if not self.info_manager: 
            self.content_scroll.add_widget(Label(text=ar_text("مدير المعلومات غير متوفر"), color=COLOR_TEXT, font_name='Roboto'))
            return

        container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(5))
        container.bind(minimum_height=container.setter('height'))
        
        tafsir_opts = {
            'الميسر': 'moyassar', 'السعدي': 'saadi', 'المختصر': 'mokhtasar',
            'الطبري': 'tabary', 'البغوي': 'baghawy', 'ابن كثير': 'katheer'
        }
        
        spinner = Spinner(
            text=ar_text('الميسر'),
            values=[ar_text(k) for k in tafsir_opts.keys()],
            size_hint_y=None, height=dp(40), font_name='Roboto',
            background_color=COLOR_ACCENT, color=(1,1,1,1)
        )
        
        lbl = Label(text="", color=COLOR_TEXT, size_hint_y=None, markup=True, halign='right', valign='top', font_name='Roboto', font_size='18sp', padding=(dp(10), dp(10)))
        lbl.bind(texture_size=lbl.setter('size'))
        lbl.bind(width=lambda instance, value: setattr(instance, 'text_size', (value, None)))
        
        def on_spinner_select(inst, text):
            # Reverse lookup for key
            key = next((k for k, v in tafsir_opts.items() if ar_text(k) == text), 'الميسر')
            db_key = tafsir_opts.get(key, 'moyassar')
            self.load_aya_data(db_key, lbl)
            
        spinner.bind(text=on_spinner_select)
        container.add_widget(spinner)
        container.add_widget(lbl)
        self.content_scroll.add_widget(container)
        
        # Initial load
        self.load_aya_data('moyassar', lbl)

    def load_aya_data(self, db_key, label_widget):
        db_ids = self.data_manager.get_db_ids_from_global(self.global_id)
        if not db_ids: return
        sura_db, aya_db, _ = db_ids
        val, title = self.info_manager.get_aya_data(db_key, sura_db, aya_db)
        label_widget.font_size = f"{self.font_size}sp"
        label_widget.text = ar_text(val if val else "لا يوجد بيانات متاحة")

    def show_eerab(self):
        self.show_word_generic("eerab", "لا يوجد إعراب متاح")

    def show_nozool(self):
        self.show_aya_generic("nozool", "لا توجد أسباب نزول مسجلة")

    def show_tajweed(self):
        self.show_aya_generic("tajweed", "لا توجد أحكام تجويد مسجلة")

    def show_tadabbur(self):
        self.content_scroll.clear_widgets()
        app = App.get_running_app()
        if not app.user_manager or not app.user_manager.current_user:
            self.content_scroll.add_widget(Label(text=ar_text("يرجى تسجيل الدخول لاستخدام التدبر"), color=COLOR_TEXT, font_name='Roboto'))
            return

        container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(10))
        container.bind(minimum_height=container.setter('height'))

        # Load existing reflection
        current_text = app.user_manager.get_reflection(app.user_manager.current_user, self.sura, self.aya)

        txt_input = ArabicTextInput(hint_text=ar_text("اكتب خواطرك هنا..."), size_hint_y=None, height=dp(200), multiline=True)
        txt_input.set_text_value(current_text)
        
        buttons_layout = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))
        btn_save = MDRaisedButton(text=ar_text("حفظ"))
        btn_save.md_bg_color = (0.2, 0.6, 0.2, 1)
        
        def save_callback(instance):
            app.user_manager.save_reflection(app.user_manager.current_user, self.sura, self.aya, txt_input.get_text())
            btn_save.children[0].text = ar_text("تم الحفظ!")
            Clock.schedule_once(lambda dt: setattr(btn_save.children[0], 'text', ar_text("حفظ")), 2)

        btn_save.bind(on_press=save_callback)
        
        btn_clear = MDRaisedButton(text=ar_text("مسح"), md_bg_color=(0.8, 0.3, 0.3, 1))
        def clear_text(instance):
            txt_input.set_text_value("")
        btn_clear.bind(on_press=clear_text)
        buttons_layout.add_widget(btn_save)
        buttons_layout.add_widget(btn_clear)
        
        container.add_widget(Label(text=ar_text("خواطرك حول الآية:"), color=COLOR_PRIMARY, size_hint_y=None, height=dp(30), halign='right', text_size=(self.width, None), font_name='Roboto'))
        container.add_widget(txt_input)
        container.add_widget(buttons_layout)
        
        self.content_scroll.add_widget(container)

    def show_word_generic(self, db_key, empty_msg):
        self.clear_content()
        if not self.info_manager or not self.global_id: return
        db_ids = self.data_manager.get_db_ids_from_global(self.global_id)
        if not db_ids: return
        sura_db, aya_db, word_db = db_ids
        val, title = self.info_manager.get_word_data(db_key, sura_db, aya_db, word_db)
        
        text = ""
        if title: text += f"[b][color=#8B0000]{ar_text(title)}[/color][/b]\n\n"
        text += ar_text(val if val else empty_msg)
        self.content_lbl.font_size = f"{self.font_size}sp"
        self.content_lbl.text = text

    def show_aya_generic(self, db_key, empty_msg):
        self.clear_content()
        if not self.info_manager or not self.global_id: return
        db_ids = self.data_manager.get_db_ids_from_global(self.global_id)
        if not db_ids: return
        sura_db, aya_db, _ = db_ids
        val, title = self.info_manager.get_aya_data(db_key, sura_db, aya_db)
        
        text = ""
        if title: text += f"[b][color=#8B0000]{ar_text(title)}[/color][/b]\n\n"
        text += ar_text(val if val else empty_msg)
        self.content_lbl.font_size = f"{self.font_size}sp"
        self.content_lbl.text = text

class QuranPageWidget(RelativeLayout):
    def __init__(self, page_num=0, text_content="", **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, None)
        self.height = dp(600)  # Initial height
        self.page_num = page_num
        self.lines = [] # Store line widgets

        self.border = Image(
            allow_stretch=True, keep_ratio=False,
            pos_hint={'x': 0, 'y': 0}, size_hint=(1, 1)
        )
        self.add_widget(self.border)

        self.label = Label(
            markup=True,
            color=(0, 0, 0, 1),
            font_name='Roboto',
            halign='center',       # توسيط النص
            valign='middle',        # توسيط عمودي للسطر
            size_hint=(None, None),
            base_direction='rtl'    # اتجاه النص لضمان المحاذاة الصحيحة
        )
        self.add_widget(self.label)

        self.bind(size=self._update_layout)
        self.bind(pos=self._update_layout)
        
        # Initial setup
        self.update_content(page_num, text_content)

    def get_border_source(self):
        if not self.page_num:
            return ""  # No border for a blank page
        img_name = 'assets/page_border000.png' if self.page_num <= 2 else 'assets/page_border00.png'
        # A fallback for safety, in case the special border is missing
        if not os.path.exists(img_name):
            img_name = os.path.join('assets', 'page_border00.png')
        return img_name

    def update_content(self, page_num, text_content):
        self.page_num = page_num
        self.border.source = self.get_border_source()
        self.opacity = 1 if page_num > 0 else 0

        # Clear existing lines
        for lbl in self.lines:
            self.remove_widget(lbl)
        self.lines = []

        if isinstance(text_content, list):
            # List of lines -> Fixed Layout Mode
            self.label.opacity = 0
            for line_text in text_content:
                lbl = Label(
                    text=line_text, 
                    markup=True, 
                    color=(0,0,0,1), 
                    font_name='Roboto', # استرجاع الخط الأصلي (Roboto/Arial) لتصحيح التشكيل
                    halign='center',       # توسيط النص
                    valign='middle',
                    size_hint=(None, None),
                    base_direction='rtl'
                )
                # Bind ref press for word clicking
                lbl.bind(on_ref_press=self.on_word_click)
                self.add_widget(lbl)
                self.lines.append(lbl)
        else:
            # String -> Legacy/Review Mode
            self.label.opacity = 1
            self.label.text = text_content if text_content else ""

        self._update_layout()

    def on_word_click(self, instance, ref):
        # Delegate to ReaderScreen
        app = App.get_running_app()
        reader = app.root.get_screen('reader')
        if reader: reader.handle_word_click(ref)

    def _update_layout(self, *args):
        if self.width <= 0 or self.height <= 0:
            return

        # Define margins to position the text label within the border image
        # هوامش مدروسة لتناسب صورة الإطار
        if self.page_num in [1, 2]:
            # هوامش أكبر للصفحة الأولى والثانية (الفاتحة وأول البقرة)
            # لأن الإطار المزخرف يأخذ مساحة أكبر من الداخل
            margin_x = self.width * 0.25
            margin_y = self.height * 0.22
        else:
            margin_x = self.width * 0.13
            margin_y = self.height * 0.12
        
        available_width = self.width - (2 * margin_x)
        available_height = self.height - (2 * margin_y)

        # 1. Handle Fixed Lines (List)
        if self.lines:
            count = len(self.lines)
            if count > 0:
                # --- START UNIFIED FIX ---

                # 1. حساب حجم الخط بناءً على العرض لضمان عدم التفاف السطر (نسبة 0.05 آمنة لأغلب الأسطر)
                font_size_w = available_width * 0.05
                
                # 2. حساب حجم الخط بناءً على الارتفاع لضمان ظهور جميع الأسطر داخل الإطار
                spacing_factor = 1.8 # معامل التباعد بين الأسطر
                font_size_h = available_height / (count * spacing_factor)
                
                # 3. نختار الحجم الأصغر لضمان تحقق الشرطين (عدم الالتفاف + الاحتواء العمودي)
                font_size = min(font_size_w, font_size_h)

                line_height = font_size * spacing_factor

                # 4. توسيط الكتلة النصية بالكامل عمودياً
                total_text_height = count * line_height
                vertical_padding = max(0, (available_height - total_text_height) / 2)
                block_bottom_y = margin_y + vertical_padding
                
                # Position lines from top to bottom, starting from the top of the centered block.
                current_y = block_bottom_y + total_text_height - line_height
                
                for lbl in self.lines:
                    lbl.x = margin_x
                    lbl.y = current_y
                    lbl.size = (available_width, line_height)
                    # This is the key fix: Allow text to wrap by not constraining its height.
                    lbl.text_size = (available_width, None) 
                    lbl.font_size = font_size
                    current_y -= line_height
            return

        # 2. Handle Legacy Label (String)
        # Center the label in the allowed area
        self.label.x = margin_x
        self.label.y = margin_y
        self.label.size = (available_width, available_height)
        self.label.text_size = (available_width, available_height)
        
        # 1. حساب حجم الخط بناءً على العرض (لضمان عدم التفاف السطر)
        # النسبة 0.048 تضمن أن أطول سطر في المصحف يناسب العرض
        font_scale = 0.048
        if self.page_num in [1, 2]:
             font_scale = 0.045 # تصغير طفيف للصفحات المزخرفة

        self.label.font_size = available_width * font_scale
        
        # 2. حساب ارتفاع السطر لملء الارتفاع المتاح (Justify Vertical)
        # نفترض أن الصفحة القياسية 15 سطر، أو نعد الأسطر الفعلية
        line_count = self.label.text.count('\n') + 1 if self.label.text else 15
        if line_count < 13: line_count = 13 # حد أدنى لمنع تباعد الأسطر الفاحش في الصفحات الفارغة
        
        if self.label.font_size > 0:
            # line_height في Kivy هو معامل ضرب في حجم الخط
            # المعادلة: الارتفاع الكلي = عدد الأسطر * حجم الخط * ارتفاع السطر
            self.label.line_height = available_height / (line_count * self.label.font_size)

class ReviewModeSheet(ModalView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, None)
        self.background_color = (0,0,0,0.5)
        self.pos_hint = {'bottom': 0}
        
        container = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10), size_hint_y=None)
        container.bind(minimum_height=container.setter('height'))
        
        with container.canvas.before:
            Color(*COLOR_SURFACE)
            RoundedRectangle(pos=container.pos, size=container.size, radius=[dp(20), dp(20), 0, 0])
        container.bind(pos=lambda i,v: setattr(i.canvas.before.children[-1], 'pos', v), size=lambda i,v: setattr(i.canvas.before.children[-1], 'size', v))

        container.add_widget(Label(text=ar_text("اختر طريقة المراجعة"), font_size='20sp', color=COLOR_PRIMARY, bold=True, size_hint_y=None, height=dp(50)))
        
        btn_voice = Button(text=ar_text("🎙️ صوتك بنزين"), on_press=self.start_voice, background_normal='', background_color=(0,0,0,0), color=COLOR_TEXT, font_size='18sp', size_hint_y=None, height=dp(50))
        btn_auto = Button(text=ar_text("⏱️ تحدي الوقت"), on_press=self.start_auto, background_normal='', background_color=(0,0,0,0), color=COLOR_TEXT, font_size='18sp', size_hint_y=None, height=dp(50))
        btn_manual = Button(text=ar_text("👆 اللمس الذكي"), on_press=self.start_manual, background_normal='', background_color=(0,0,0,0), color=COLOR_TEXT, font_size='18sp', size_hint_y=None, height=dp(50))
        
        container.add_widget(btn_voice)
        container.add_widget(btn_auto)
        container.add_widget(btn_manual)
        container.add_widget(Label(size_hint_y=None, height=dp(20))) # Bottom padding
        
        self.add_widget(container)

    def _start_mode(self, mode_name):
        self.dismiss()
        app = App.get_running_app()
        app.review_mode = mode_name
        # Go to config screen first to select sura/aya
        app.root.current = 'review_config'

    def start_voice(self, instance):
        self._start_mode('voice')

    def start_auto(self, instance):
        self._start_mode('auto')

    def start_manual(self, instance):
        self._start_mode('manual')

class HomeScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        
        # Base layout using FloatLayout for layering
        layout = FloatLayout()

        # 1. Background Image
        self.bg_rect = None
        with layout.canvas.before:
            bg_source = 'assets/paper_bg.png'
            if os.path.exists(bg_source):
                Color(1, 1, 1, 1)
                self.bg_rect = Rectangle(source=bg_source, pos=self.pos, size=self.size)
            else:
                Color(*COLOR_BG)
                self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        layout.bind(size=self._update_canvas_rects)

        # 2. Center Logo
        logo_size = dp(140)
        self.logo = Image(source='assets/logo.png', allow_stretch=True, keep_ratio=True,
                          size_hint=(None, None), size=(logo_size, logo_size),
                          pos_hint={'center_x': 0.5, 'center_y': 0.55})
        layout.add_widget(self.logo)

        # 3. Circular Menu Items
        self.menu_buttons = []
        items = [
            ("المصحف", "📖", self.go_reader),
            ("التلاوة", "🔊", self.go_recitation),
            ("المراجعة", "🎙️", self.open_review_sheet),
            ("خططي", "📝", self.go_plans)
        ]
        
        # ألوان عصرية للأزرار
        button_colors = [
            (0.0, 0.6, 0.5, 1),  # أخضر تركواز
            (0.2, 0.5, 0.8, 1),  # أزرق
            (0.9, 0.6, 0.2, 1),  # برتقالي
            (0.6, 0.3, 0.6, 1)   # بنفسجي
        ]
        
        # Angles: Top-Right (45), Top-Left (135), Bottom-Left (225), Bottom-Right (315)
        angles = [45, 135, 225, 315]

        for i, (text, icon, callback) in enumerate(items):
            btn = ModernCard(text=text, icon=icon, bg_color=button_colors[i], size_hint=(None, None), size=(dp(110), dp(110)))
            btn.bind(on_release=callback)
            btn.angle = math.radians(angles[i])
            layout.add_widget(btn)
            self.menu_buttons.append(btn)

        layout.bind(size=self._update_button_positions)

        # 4. Border image
        self.border_rect = None
        border_source = 'assets/islamic_border.png'
        if os.path.exists(border_source):
            with layout.canvas.after:
                Color(1, 1, 1, 1)
                self.border_rect = Rectangle(source=border_source, pos=self.pos, size=self.size)
        
        # 5. Bottom Nav (Contains Settings)
        self.bottom_nav = BottomNavBar(current_tab='home')
        self.bottom_nav.pos_hint = {'x': 0, 'y': 0}
        layout.add_widget(self.bottom_nav)

        # The review mode sheet
        self.review_sheet = ReviewModeSheet()
        self.add_widget(layout)

    def _update_canvas_rects(self, instance, value):
        if self.bg_rect:
            self.bg_rect.pos = instance.pos
            self.bg_rect.size = instance.size
        if self.border_rect:
            self.border_rect.pos = instance.pos
            self.border_rect.size = instance.size

    def _update_button_positions(self, instance, value):
        center_x = instance.width * 0.5
        center_y = instance.height * 0.55
        radius = dp(140) # Distance from center
        
        for btn in self.menu_buttons:
            # x = cx + r * cos(a) - w/2
            # y = cy + r * sin(a) - h/2
            btn.x = center_x + radius * math.cos(btn.angle) - btn.width / 2
            btn.y = center_y + radius * math.sin(btn.angle) - btn.height / 2

    def go_recitation(self, instance):
        self.manager.current = 'recitation_config'

    def open_review_sheet(self, instance):
        self.review_sheet.open()

    def go_reader(self, instance):
        self.manager.current = 'reader'
        
    def go_plans(self, instance):
        self.manager.current = 'plans_home'

class ReaderScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        
        # Use FloatLayout for layering (Sliver Header, FAB, Bottom Sheet)
        self.layout = FloatLayout()
        
        # --- Top Bar ---
        # Sliver AppBar Logic: We will animate its Y position based on scroll
        self.header_height = dp(60)
        self.header = BoxLayout(size_hint=(1, None), height=self.header_height, pos_hint={'top': 1}, padding=[10, 0], spacing=dp(10))
        with self.header.canvas.before:
            Color(*COLOR_PRIMARY)
            RoundedRectangle(pos=self.header.pos, size=self.header.size, radius=[0, 0, dp(20), dp(20)])
        self.header.bind(pos=lambda inst, v: setattr(inst.canvas.before.children[-1], 'pos', v))
        self.header.bind(size=lambda inst, v: setattr(inst.canvas.before.children[-1], 'size', v))
        
        # Header Content
        # --- Animated Icon ---
        self.icon_paths = [
            'assets/icon.ico',
            'assets/icon1.ico',
            'assets/icon2.ico',
            'assets/icon3.ico'
        ]
        self.icon_index = 0
        self.header_icon = Image(
            source=self.icon_paths[0],
            size_hint=(None, None),
            size=(dp(40), dp(40)),
            pos_hint={'center_y': 0.5}
        )
        self.header.add_widget(self.header_icon)
        Clock.schedule_interval(self.animate_icon, 0.5)

        # --- زر الوقت المتبقي للصلاة القادمة ---
        self.btn_next_prayer = MDFlatButton(text=ar_text("..."), theme_text_color="Custom", text_color=(1,1,1,1), font_size='14sp')
        self.btn_next_prayer.bind(on_press=self.go_prayers)
        self.header.add_widget(self.btn_next_prayer)

        self.btn_sura_title = MDFlatButton(text=ar_text("سورة ..."), theme_text_color="Custom", text_color=(1,1,1,1), font_size='20sp')
        self.btn_sura_title.bind(on_press=self.open_index)
        self.header.add_widget(self.btn_sura_title)
        
        # Audio Toggle in Header
        self.btn_audio = CustomIconButton(icon="volume-high", theme_text_color="Custom", text_color=(1,1,1,1))
        self.btn_audio.bind(on_press=self.toggle_audio)
        self.header.add_widget(self.btn_audio)
        
        # --- Content Area ---
        # Padding top to avoid hiding behind header initially, padding bottom for nav bar
        self.scroll_view = ScrollView(size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        self.scroll_view.bind(on_scroll_move=self.on_scroll_move)
        
        # Container for pages (Horizontal for double view)
        self.pages_container = BoxLayout(orientation='horizontal', padding=[dp(5), dp(70), dp(5), dp(75)], spacing=dp(10), size_hint_y=None)
        self.pages_container.bind(minimum_height=self.pages_container.setter('height'))
        
        # Create Quran Page Widgets
        self.page_widget_left = QuranPageWidget()
        self.page_widget_right = QuranPageWidget()

        # Add left page first, then right page for correct RTL book visual in a LTR container
        self.pages_container.add_widget(self.page_widget_left)
        self.pages_container.add_widget(self.page_widget_right)
        
        self.scroll_view.add_widget(self.pages_container)
        self.layout.add_widget(self.scroll_view)
        
        # Add Header on top of ScrollView
        self.layout.add_widget(self.header)
        
        # --- Bottom Nav Bar ---
        self.bottom_nav = BottomNavBar(current_tab='mushaf', show_arrows=True, pos_hint={'bottom': 1})
        self.layout.add_widget(self.bottom_nav)
        
        # --- Bottom Sheet ---
        self.index_sheet = IndexBottomSheet(self.on_sura_selected_from_sheet)
        
        self.add_widget(self.layout)
        
        self.audio_player = None
        self.review_active = False
        self.review_words = [] # List of dicts: {text, revealed, is_marker}
        self.review_index = 0
        self.review_event = None
        self.voice_sensor = VoiceSensor()
        self.voice_fuel = 0.0
        
        self.active_sura = None
        self.active_aya = None
        self.last_scroll_y = 1.0
        
        # تحديث وقت الصلاة كل دقيقة
        Clock.schedule_interval(self.update_prayer_timer, 60)
        Clock.schedule_once(self.update_prayer_timer, 1)

    def animate_icon(self, dt):
        self.icon_index = (self.icon_index + 1) % len(self.icon_paths)
        self.header_icon.source = self.icon_paths[self.icon_index]

    def on_touch_down(self, touch):
        # Store starting position for swipe detection
        touch.ud['swipe_x'] = touch.x
        touch.ud['swipe_y'] = touch.y
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        # Check if it was a swipe
        if 'swipe_x' in touch.ud and self.collide_point(*touch.pos):
            dx = touch.x - touch.ud['swipe_x']
            dy = touch.y - touch.ud['swipe_y']

            # We only care about horizontal swipes that are significant
            if abs(dx) > dp(50) and abs(dx) > abs(dy) * 1.5: # More horizontal than vertical
                if dx < 0:  # Swipe left
                    self.next_page(None)
                    return True # Consume the touch event
                elif dx > 0: # Swipe right
                    self.prev_page(None)
                    return True # Consume the touch event
        
        return super().on_touch_up(touch)

    def update_prayer_timer(self, dt):
        if not self.app.prayer_times:
            self.btn_next_prayer.text = ar_text("...")
            return

        now = datetime.now()
        
        # خريطة الأسماء
        prayers_map = {
            "Fajr": "الفجر", "Sunrise": "الشروق", "Dhuhr": "الظهر",
            "Asr": "العصر", "Maghrib": "المغرب", "Isha": "العشاء"
        }
        
        # الترتيب الزمني
        prayer_order = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
        
        next_prayer_name = None
        next_prayer_dt = None
        
        # البحث عن الصلاة القادمة اليوم
        for p_name in prayer_order:
            p_time_str = self.app.prayer_times.get(p_name)
            if not p_time_str: continue
            
            try:
                # تحويل الوقت (نفترض الصيغة HH:MM)
                pt = datetime.strptime(p_time_str, "%H:%M").time()
                p_dt = datetime.combine(now.date(), pt)
                
                if p_dt > now:
                    next_prayer_name = p_name
                    next_prayer_dt = p_dt
                    break
            except: pass
            
        # إذا لم نجد صلاة اليوم، فالقادمة هي الفجر غداً
        if not next_prayer_name:
            p_time_str = self.app.prayer_times.get("Fajr")
            if p_time_str:
                try:
                    pt = datetime.strptime(p_time_str, "%H:%M").time()
                    next_prayer_dt = datetime.combine(now.date() + timedelta(days=1), pt)
                    next_prayer_name = "Fajr"
                except: pass
        
        if next_prayer_name and next_prayer_dt:
            diff = next_prayer_dt - now
            total_seconds = int(diff.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes = remainder // 60
            
            ar_name = prayers_map.get(next_prayer_name, next_prayer_name)
            # عرض: "العصر - 01:30"
            self.btn_next_prayer.text = ar_text(f"{ar_name} - {hours}:{minutes:02}")
        else:
            self.btn_next_prayer.text = ar_text("...")

    def on_scroll_move(self, instance, touch):
        # Simple Sliver Logic
        if instance.scroll_y < self.last_scroll_y:
            # Scrolling down -> Hide Header
            Animation(pos_hint={'top': 0.9}, duration=0.2).start(self.header)
        else:
            # Scrolling up -> Show Header
            Animation(pos_hint={'top': 1}, duration=0.2).start(self.header)
        self.last_scroll_y = instance.scroll_y

    def on_enter(self):
        # Initial load if empty
        if self.app.data_manager and not self.page_widget_right.label.text:
             self.load_page(self.app.current_page)
        
        # If returning from config with review mode set
        if getattr(self.app, 'start_review_flag', False):
            self.app.start_review_flag = False
            self.start_review_session()
            
        # Bind resize event for responsiveness
        Window.bind(on_resize=self._on_resize)
        # Trigger once to set initial layout
        Clock.schedule_once(lambda dt: self._on_resize(None, Window.width, Window.height), 0.1)

    def on_leave(self):
        Window.unbind(on_resize=self._on_resize)

    def _on_resize(self, instance, width, height):
        # 1. Determine View Mode (Responsive) - use a dp-based breakpoint
        new_mode = 'double' if width > dp(700) else 'single'
        
        # 2. Apply Mode if changed
        if new_mode != self.app.view_mode:
            self.app.view_mode = new_mode
            self.load_page(self.app.current_page)
            
        # --- تحديث ارتفاع الصفحات للحفاظ على التناسب ---
        # الارتفاع المتاح = ارتفاع النافذة - (الهيدر + الفوتر + هوامش)
        header_h = dp(60)
        footer_h = dp(65)
        margin_h = dp(20) # 10 top, 10 bottom
        available_h = height - (header_h + footer_h + margin_h)
        
        # عرض الصفحة الواحدة
        if self.app.view_mode == 'double':
            page_w = (width - dp(20)) / 2
        else:
            page_w = width - dp(10)
            
        # النسبة الذهبية لصفحة المصحف تقريباً 1:1.55
        target_h = page_w * 1.55
        
        # نختار الارتفاع الأقل لضمان ظهور الصفحة كاملة
        final_h = min(target_h, available_h)
        final_h = max(final_h, dp(300)) # حد أدنى
        
        self.page_widget_left.height = final_h
        self.page_widget_right.height = final_h
        
        # Center vertically
        extra_space = max(0, available_h - final_h)
        # Push content down to sit just above bottom nav
        top_pad = header_h + dp(10) + extra_space
        bottom_pad = footer_h + dp(10)
        
        self.pages_container.padding = [dp(5), top_pad, dp(5), bottom_pad]
        self.pages_container.height = final_h + top_pad + bottom_pad

    def load_page(self, page_num):
        self.app.current_page = page_num
        
        # Ensure container height is bound to its children
        self.pages_container.bind(minimum_height=self.pages_container.setter('height'))
        
        # Configure Layout based on View Mode
        if self.app.view_mode == 'double':
            self.page_widget_left.size_hint_x = 0.5
            self.page_widget_right.size_hint_x = 0.5

            # Logic for correct RTL book layout
            right_page_num = 0
            left_page_num = 0

            # Logic for correct RTL book layout as requested: (1,2), (3,4), etc.
            if page_num % 2 != 0: # Odd page (1, 3, 5...) -> It is the Right page
                right_page_num = page_num
                left_page_num = page_num + 1
            else: # Even page (2, 4, 6...) -> It is the Left page, so Right is page-1
                right_page_num = page_num - 1
                left_page_num = page_num
            
            # Boundary checks
            if right_page_num > 604: right_page_num = 0
            if left_page_num > 604: left_page_num = 0

            # Load content into the correct widgets
            content_right = self.get_page_content(right_page_num) if right_page_num > 0 else ""
            content_left = self.get_page_content(left_page_num) if left_page_num > 0 else ""

            self.page_widget_right.update_content(right_page_num, content_right)
            self.page_widget_left.update_content(left_page_num, content_left)
            
            
            if left_page_num > 0 and right_page_num > 0:
                self.btn_sura_title.text = ar_text(f"ص {right_page_num} - {left_page_num}")
            elif right_page_num > 0:
                 self.btn_sura_title.text = ar_text(f"ص {right_page_num}")
            elif left_page_num > 0:
                 self.btn_sura_title.text = ar_text(f"ص {left_page_num}")
            else:
                self.btn_sura_title.text = ar_text("المصحف")
            
        else: # Single Mode
            self.page_widget_left.update_content(0, "") # Hide left page
            self.page_widget_left.size_hint_x = 0
            self.page_widget_left.width = 0
            
            self.page_widget_right.size_hint_x = 1
            
            content = self.get_page_content(page_num)
            self.page_widget_right.update_content(page_num, content)
            

            self.btn_sura_title.text = ar_text(f"ص {page_num}")
            
        self.scroll_view.scroll_y = 1

    def handle_word_click(self, ref):
        if self.review_active: return # Don't show info during review/recitation
        
        try:
            sura, aya, word = map(int, ref.split(':'))
            popup = WordInfoPopup(self.app.info_manager, self.app.data_manager, sura, aya, word)
            popup.open()
        except Exception as e:
            print(f"Error handling click: {e}")

    def to_arabic_numerals(self, text):
        devanagari = "0123456789"
        arabic = "٠١٢٣٤٥٦٧٨٩"
        trans = str.maketrans(devanagari, arabic)
        return str(text).translate(trans)

    def get_page_content(self, page_num):
        if not self.app.data_manager or page_num == 0: return ""
        try:
            layout_lines = self.app.data_manager.get_page_layout(page_num)
            
            # --- Primary Rendering Path (from layout data) ---
            if layout_lines:
                display_lines = []
                self.review_words = [] 
                self.review_index = 0
                
                current_sura = None
                ayah_num_pattern = re.compile(r'^[\d\u0660-\u0669\u06F0-\u06F9]+$|[\ufc00-\uffff]')

                for line_words in layout_lines:
                    if not line_words: continue
                    
                    first_word = line_words[0]
                    try:
                        sura_no = int(first_word.get('surah'))
                        aya_no = int(first_word.get('ayah'))
                    except (ValueError, TypeError, IndexError):
                        continue

                    # --- Sura Header Logic ---
                    if (current_sura is not None and sura_no != current_sura) or (current_sura is None and aya_no == 1):
                         if aya_no == 1:
                            sura_name = self.app.data_manager.get_sura_name(sura_no)
                            display_lines.append(f"[color=#8B0000][b]{ar_text(f'--- سورة {sura_name} ---')}[/b][/color]")
                            if sura_no != 1 and sura_no != 9: # No basmala for Tawbah
                                basmala_txt = self.app.data_manager.get_basmala_text()
                                display_lines.append(f"[color=#B8860B]{ar_text(basmala_txt)}[/color]")
                    current_sura = sura_no
                    
                    line_text_parts = []
                    for w in line_words:
                        text = w.get('text', '')

                        # --- Ayah Number Styling ---
                        if text and ayah_num_pattern.match(text):
                            aya_val = w.get('ayah', text)
                            num_text = self.to_arabic_numerals(str(aya_val))
                            # FIX: عكس اتجاه الأقواس واستخدام الخط العثماني
                            marker_text = f"﴾{num_text}﴿"
                            styled_text = f"[font=Roboto][color=#B8860B][b]{ar_text(marker_text)}[/b][/color][/font]"
                            line_text_parts.append(styled_text)
                            continue

                        if self.review_active:
                            self.review_words.append({'text': text, 'revealed': False, 'is_marker': False})
                        
                        text_reshaped = ar_text(text)
                        
                        # Wrap in ref for click handling
                        word_id = w.get('word')
                        if word_id:
                             ref = f"{sura_no}:{aya_no}:{word_id}"
                             text_display = f"[ref={ref}]{text_reshaped}[/ref]"
                        else:
                             text_display = text_reshaped

                        # --- Highlight Logic ---
                        try:
                            w_sura = int(w.get('surah'))
                            w_aya = int(w.get('ayah')) 
                            if self.active_sura and self.active_aya and \
                               w_sura == self.active_sura and w_aya == self.active_aya:
                                color = self.app.highlight_color
                                text_display = f"[b][color=#{color}]{text_display}[/color][/b]"
                        except (ValueError, TypeError):
                            pass
                        
                        line_text_parts.append(text_display)
                    
                    full_line = " ".join(reversed(line_text_parts))
                    display_lines.append(full_line)

                if self.review_active and page_num == self.app.current_page:
                    return self.get_review_text_display()
                
                return display_lines

            # --- Fallback Rendering Path (manual wrap) ---
            ayas = self.app.data_manager.pages_by_number.get(page_num, [])
            if not ayas:
                ayas = self.app.data_manager.pages_by_number.get(str(page_num), [])
                
            full_page_tokens = []
            current_sura = None
            
            if self.review_active and not self.review_words:
                self.prepare_review_words(ayas)

            for aya in ayas:
                sura_no = aya.get('sura_no')
                aya_no = aya.get('aya_no')
                
                if sura_no != current_sura:
                    if aya_no == 1:
                        sura_name = self.app.data_manager.get_sura_name(sura_no)
                        if full_page_tokens: full_page_tokens.append({"type": "newline"})
                        full_page_tokens.append({"type": "header", "text": f"--- سورة {sura_name} ---"})
                        full_page_tokens.append({"type": "newline"})
                        if sura_no != 1 and sura_no != 9:
                            full_page_tokens.append({"type": "basmala", "text": "بسم الله الرحمن الرحيم"})
                            full_page_tokens.append({"type": "newline"})
                    current_sura = sura_no
                
                aya_text = aya.get('aya_text', aya.get('aya_text_emlaey', '[نص غير متوفر]'))
                # Clean text from potential old markers
                aya_text = re.sub(r'[\uFC00-\uFD3F]', '', aya_text).strip()

                words = aya_text.split()
                for w in words:
                    full_page_tokens.append({"type": "word", "text": w, "sura": sura_no, "aya": aya_no})
                
                # Add new styled marker
                arabic_aya_no = self.to_arabic_numerals(aya_no)
                # Use FD3F (Start) and FD3E (End) for logical order
                full_page_tokens.append({"type": "marker", "text": f"﴿{arabic_aya_no}﴾", "sura": sura_no, "aya": aya_no})

            # --- Manual Wrapping Logic (Simplified) ---
            # NOTE: This path is less ideal than the layout-based one.
            # The QuranPageWidget will handle the final wrapping. We just provide a long string.
            display_lines = []
            current_line_parts = []
            
            for token in full_page_tokens:
                t_type = token.get('type')
                t_text = ar_text(token.get('text', ''))

                if t_type == 'header':
                    display_lines.append(f"[color=#8B0000][b]{t_text}[/b][/color]")
                elif t_type == 'basmala':
                    display_lines.append(f"[color=#B8860B]{t_text}[/color]")
                elif t_type == 'marker':
                    # Ayah markers are styled and added with spaces to separate them
                    # Use Roboto to ensure brackets appear
                    styled_marker = f"[font=Roboto][color=#B8860B][b]{ar_text(t_text)}[/b][/color][/font]"
                    current_line_parts.append(styled_marker)
                elif t_type == 'word':
                    text = t_text
                    # Highlight Logic
                    if self.active_sura and self.active_aya and \
                       token.get('sura') == self.active_sura and token.get('aya') == self.active_aya:
                        color = self.app.highlight_color
                        text = f"[b][color=#{color}]{text}[/color][/b]"
                    current_line_parts.append(text)
                elif t_type == 'newline':
                    display_lines.append("\n")

            # Join all words and markers for the page
            full_page_text = " ".join(reversed(current_line_parts))
            display_lines.insert(0, full_page_text)

            if self.review_active and page_num == self.app.current_page:
                return self.get_review_text_display()
            
            return "\n".join(display_lines)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error loading page: {e}"

    def prepare_review_words(self, ayas):
        self.review_words = []
        self.review_index = 0
        for aya in ayas:
            text = aya.get('aya_text', aya.get('aya_text_emlaey', ''))
            words = text.split()
            for w in words:
                self.review_words.append({'text': w, 'revealed': False, 'is_marker': False})
            self.review_words.append({'text': f"({aya.get('aya_no')})", 'revealed': False, 'is_marker': True})

    def get_review_text_display(self):
        parts = []
        for w in self.review_words:
            text = ar_text(w['text'])
            if w['revealed']:
                color = "#000000" if not w['is_marker'] else "#228B22"
                parts.append(f"[color={color}]{text}[/color]")
            else:
                # Hidden (Transparent)
                parts.append(f"[color=#00000000]{text}[/color]")
        
        # Join reversed for RTL flow
        return " ".join(reversed(parts))

    def start_review_session(self):
        self.review_active = True
        self.review_words = [] # Will be populated in load_page
        self.load_page(self.app.current_page)
        
        if self.app.review_mode == 'auto':
            interval = getattr(self.app, 'review_speed', 0.5)
            self.review_event = Clock.schedule_interval(self.auto_reveal_step, interval)
        elif self.app.review_mode == 'voice':
            self.voice_sensor.start()
            self.voice_fuel = 0.0
            # Check audio 20 times a second
            self.review_event = Clock.schedule_interval(self.update_voice_loop, 0.05)

    def stop_review_session(self):
        self.review_active = False
        if self.review_event:
            self.review_event.cancel()
            self.review_event = None
        self.voice_sensor.stop()
        self.load_page(self.app.current_page)

    def update_voice_loop(self, dt):
        if not self.review_active: return
        
        vol = self.voice_sensor.get_volume()
        
        # Threshold to ignore silence
        if vol > 0.1:
            # Add fuel based on volume (louder/faster speech = more fuel)
            self.voice_fuel += vol * 0.8
            
        # Cap fuel to prevent runaway revealing
        self.voice_fuel = min(self.voice_fuel, 3.0)
        
        # Consume fuel to reveal words
        if self.voice_fuel >= 1.0:
            self.auto_reveal_step(0)
            self.voice_fuel -= 1.0
            
        # Natural decay (friction)
        self.voice_fuel = max(0, self.voice_fuel - 0.02)

    def auto_reveal_step(self, dt):
        if self.review_index < len(self.review_words):
            self.review_words[self.review_index]['revealed'] = True
            self.review_index += 1
            # Update the label within the appropriate page widget
            self.page_widget_right.label.text = self.get_review_text_display()
        else:
            # Page done
            if self.review_event:
                self.review_event.cancel()
                self.review_event = None

    def on_text_touch(self, instance, touch):
        if self.review_active and self.app.review_mode == 'manual':
            # Check for touch collision on the page widget itself
            if self.page_widget_right.collide_point(*touch.pos):
                self.auto_reveal_step(0)
                return True
        return False

    def highlight_aya(self, sura, aya):
        self.active_sura = sura
        self.active_aya = aya
        
        # Check if we need to change page
        if self.app.data_manager:
            found_page = None
            for entry in self.app.data_manager.all_ayas:
                if entry['sura_no'] == sura and entry['aya_no'] == aya:
                    found_page = entry['page']
                    break
            
            if found_page:
                # Load page (this will re-render with highlight)
                if self.app.current_page != found_page or True: # Force reload to apply color
                    self.load_page(found_page)

    def next_page(self, instance):
        step = 2 if self.app.view_mode == 'double' else 1
        if self.app.current_page + step <= 604:
            self.load_page(self.app.current_page + step)

    def prev_page(self, instance):
        step = 2 if self.app.view_mode == 'double' else 1
        if self.app.current_page - step >= 1:
            self.load_page(self.app.current_page - step)
            
    def open_index(self, instance):
        if self.app.data_manager:
            self.index_sheet.populate(self.app.data_manager)
            self.index_sheet.open()
            
    def on_sura_selected_from_sheet(self, page_num):
        self.load_page(page_num)
        
    def go_review(self, instance):
        self.manager.current = 'review_config'

    def go_recitation(self, instance):
        self.manager.current = 'recitation_config'

    def toggle_audio(self, instance):
        if self.audio_player and self.audio_player.state == 'play':
            self.audio_player.stop()
            self.btn_audio.icon = "volume-off"
        else:
            popup = Popup(title=ar_text("تنبيه"),
                          content=Label(text=ar_text("ميزة الصوت تتطلب اتصالاً بالإنترنت ومصدر صوتي صالح.")),
                          size_hint=(0.8, 0.4))
            popup.open()

    def go_prayers(self, instance):
        if not self.app.prayer_times:
            self.app.fetch_prayer_times()
            self.btn_next_prayer.text = ar_text("جاري التحديث...")
            return
        self.app.root.current = 'prayers'

class IndexScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        layout = BoxLayout(orientation='vertical')
        
        # Header
        header = BoxLayout(size_hint_y=0.1, padding=5)
        btn_back = MDFlatButton(text=ar_text("عودة"))
        btn_back.bind(on_press=self.go_back)
        header.add_widget(Label(text=ar_text("فهرس السور"), color=(0,0,0,1)))
        header.add_widget(btn_back)
        layout.add_widget(header)
        
        # List
        self.scroll = ScrollView()
        self.grid = GridLayout(cols=1, size_hint_y=None, spacing=2)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll.add_widget(self.grid)
        layout.add_widget(self.scroll)
        self.add_widget(layout)
        self.populated = False

    def on_enter(self):
        if not self.populated and self.app.data_manager:
            for i in range(1, 115):
                sura_name = self.app.data_manager.get_sura_name(i)
                btn = OneLineListItem(text=ar_text(f"{i}. {sura_name}"))
                btn.sura_no = i
                btn.bind(on_press=self.on_sura_select)
                self.grid.add_widget(btn)
            self.populated = True

    def on_sura_select(self, instance):
        sura_no = instance.sura_no
        page = self.app.data_manager.sura_pages.get(sura_no, 1)
        self.app.current_page = page
        self.manager.get_screen('reader').load_page(page)
        self.manager.current = 'reader'

    def go_back(self, instance):
        self.manager.current = 'reader'

class SearchScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10, size_hint=(1, 1))
        
        # Header
        header = BoxLayout(size_hint_y=0.1)
        btn_back = MDFlatButton(text=ar_text("عودة"))
        btn_back.bind(on_press=self.go_back)
        header.add_widget(Label(text=ar_text("البحث"), color=(0,0,0,1)))
        header.add_widget(btn_back)
        layout.add_widget(header)
        
        # Input
        search_box = BoxLayout(size_hint_y=0.1, spacing=5)
        self.txt_input = ArabicTextInput(hint_text=ar_text("اكتب كلمة للبحث..."))
        btn_do_search = MDRaisedButton(text=ar_text("بحث"), size_hint_x=0.3)
        btn_do_search.bind(on_press=self.do_search)
        search_box.add_widget(self.txt_input)
        search_box.add_widget(btn_do_search)
        layout.add_widget(search_box)
        
        # Results
        self.scroll = ScrollView()
        self.result_grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(10), padding=dp(10))
        self.result_grid.bind(minimum_height=self.result_grid.setter('height'))
        self.scroll.add_widget(self.result_grid)
        layout.add_widget(self.scroll)
        
        # Bottom Nav
        layout.add_widget(BottomNavBar(current_tab='search'))
        
        self.add_widget(layout)

    def do_search(self, instance):
        query = self.txt_input.get_text()
        if not query or not self.app.data_manager: return
        
        self.result_grid.clear_widgets()
        results = self.app.data_manager.find_verse_by_text(query)
        
        if not results:
            self.result_grid.add_widget(Label(text=ar_text("لا توجد نتائج"), color=(0,0,0,1), size_hint_y=None, height=50))
            return
            
        for res in results[:50]: # Limit to 50
            text = res['text']
            sura = res['sura_name']
            aya = res['aya_no']
            page = res['page_no']
            
            btn_text = f"{sura} ({aya}): {text[:40]}..."
            btn = ModernCard(text=btn_text, size_hint_y=None, height=dp(80))
            btn.target_page = page
            btn.bind(on_press=self.on_result_select)
            self.result_grid.add_widget(btn)

    def on_result_select(self, instance):
        self.app.current_page = instance.target_page
        self.manager.get_screen('reader').load_page(instance.target_page)
        self.manager.current = 'reader'

    def go_back(self, instance):
        self.manager.current = 'reader'

class PrayerScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Header
        header = BoxLayout(size_hint_y=0.1)
        btn_back = MDFlatButton(text=ar_text("عودة"))
        btn_back.bind(on_press=self.go_back)
        header.add_widget(Label(text=ar_text("مواقيت الصلاة (القاهرة)"), color=(0,0,0,1), font_size='20sp'))
        header.add_widget(btn_back)
        layout.add_widget(header)
        
        # Prayer List
        self.prayers_grid = GridLayout(cols=2, spacing=10, size_hint_y=0.8)
        layout.add_widget(self.prayers_grid)
        
        # Status
        self.lbl_status = Label(text=ar_text("جاري التحديث..."), color=(0.2, 0.2, 0.2, 1), size_hint_y=0.1)
        layout.add_widget(self.lbl_status)
        
        self.add_widget(layout)

    def on_enter(self):
        self.update_ui()

    def update_ui(self):
        self.prayers_grid.clear_widgets()
        if not self.app.prayer_times:
            self.lbl_status.text = ar_text("جاري جلب المواقيت من الإنترنت...")
            return
            
        self.lbl_status.text = ar_text("تم التحديث")
        
        names_map = {
            "Fajr": "الفجر", "Sunrise": "الشروق", "Dhuhr": "الظهر",
            "Asr": "العصر", "Maghrib": "المغرب", "Isha": "العشاء"
        }
        
        # ترتيب العرض
        order = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
        
        for key in order:
            time_str = self.app.prayer_times.get(key)
            if time_str:
                # تحويل الوقت لـ 12 ساعة
                try:
                    dt = datetime.strptime(time_str, "%H:%M")
                    display_time = dt.strftime("%I:%M %p")
                except:
                    display_time = time_str
                    
                self.prayers_grid.add_widget(Label(text=ar_text(names_map.get(key, key)), color=(0,0,0,1), font_size='18sp'))
                self.prayers_grid.add_widget(Label(text=display_time, color=(0,0.5,0,1), font_size='18sp'))

    def go_back(self, instance):
        self.manager.current = 'reader'

class RecitationConfigScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        layout = BoxLayout(orientation='vertical', padding=15, spacing=15)
        
        layout.add_widget(Label(text=ar_text("إعدادات خطة السماع"), font_size='22sp', color=(0,0,0,1), size_hint_y=0.1))
        
        # --- NEW: Audio Path Input ---
        path_grid = GridLayout(cols=3, spacing=10, size_hint_y=0.1)
        path_grid.add_widget(Label(text=ar_text("مسار مجلد الصوت:"), color=(0,0,0,1), size_hint_x=0.3))
        self.txt_audio_path = ArabicTextInput(text='audio', size_hint_x=0.5) # Initial text handled by init
        path_grid.add_widget(self.txt_audio_path)
        
        btn_browse = MDRaisedButton(text=ar_text("..."), size_hint_x=0.2)
        btn_browse.bind(on_press=self.open_file_browser)
        path_grid.add_widget(btn_browse)
        layout.add_widget(path_grid)
        
        # --- NEW: Recitation Type (Ayat / Pages) ---
        type_grid = GridLayout(cols=2, spacing=10, size_hint_y=0.1)
        type_grid.add_widget(Label(text=ar_text("نوع التلاوة:"), color=(0,0,0,1)))
        self.spin_type = Spinner(text='Ayat', values=('Ayat', 'Pages'), height=STD_HEIGHT, size_hint_y=None)
        type_grid.add_widget(self.spin_type)
        layout.add_widget(type_grid)
        
        # Range Selection
        range_grid = GridLayout(cols=2, spacing=10, size_hint_y=0.2)
        range_grid.add_widget(Label(text=ar_text("من سورة (للآيات):"), color=(0,0,0,1)))
        self.spin_sura_start = Spinner(text='1', values=[str(i) for i in range(1, 115)])
        range_grid.add_widget(self.spin_sura_start)
        
        range_grid.add_widget(Label(text=ar_text("البداية (آية/صفحة):"), color=(0,0,0,1)))
        self.txt_aya_start = ArabicTextInput(text='1', input_filter='int')
        range_grid.add_widget(self.txt_aya_start)
        
        range_grid.add_widget(Label(text=ar_text("النهاية (آية/صفحة):"), color=(0,0,0,1)))
        self.txt_aya_end = ArabicTextInput(text='7', input_filter='int')
        range_grid.add_widget(self.txt_aya_end)
        layout.add_widget(range_grid)
        
        # Mode Selection
        layout.add_widget(Label(text=ar_text("نظام التكرار"), color=(0,0,0,1), size_hint_y=0.05))
        self.spin_mode = Spinner(text='Single', values=('Single', 'Group', 'Complex'), size_hint_y=0.1)
        layout.add_widget(self.spin_mode)
        
        # Repetition Settings
        rep_grid = GridLayout(cols=2, spacing=10, size_hint_y=0.3)
        
        rep_grid.add_widget(Label(text=ar_text("تكرار الآية (فردي/مركب):"), color=(0,0,0,1)))
        self.txt_rep_ind = ArabicTextInput(text='3', input_filter='int')
        rep_grid.add_widget(self.txt_rep_ind)
        
        rep_grid.add_widget(Label(text=ar_text("تكرار المجموعة (جماعي/مركب):"), color=(0,0,0,1)))
        self.txt_rep_grp = ArabicTextInput(text='1', input_filter='int')
        rep_grid.add_widget(self.txt_rep_grp)
        
        rep_grid.add_widget(Label(text=ar_text("حجم الربط (للمركب):"), color=(0,0,0,1)))
        self.txt_grp_size = ArabicTextInput(text='2', input_filter='int')
        rep_grid.add_widget(self.txt_grp_size)
        
        layout.add_widget(rep_grid)
        
        # Buttons
        btn_start = MDRaisedButton(text=ar_text("بدء التلاوة"), size_hint_y=0.15, md_bg_color=(0.2, 0.7, 0.2, 1))
        btn_start.bind(on_press=self.start_recitation)
        layout.add_widget(btn_start)
        
        # Bottom Nav
        layout.add_widget(BottomNavBar(current_tab='settings'))

        self.add_widget(layout)

    def open_file_browser(self, instance):
        content = BoxLayout(orientation='vertical')
        
        # Start path
        path = self.txt_audio_path.text.strip()
        if not os.path.exists(path):
            path = "."
            
        # FileChooser
        self.file_chooser = FileChooserIconView(path=path, dirselect=True)
        content.add_widget(self.file_chooser)
        
        # Buttons
        btns = BoxLayout(size_hint_y=0.1, spacing=10)
        btn_ok = MDRaisedButton(text=ar_text("موافق"), md_bg_color=(0.2, 0.8, 0.2, 1))
        btn_cancel = MDFlatButton(text=ar_text("إلغاء"))
        
        btn_ok.bind(on_press=self.select_path)
        btn_cancel.bind(on_press=self.close_popup)
        
        btns.add_widget(btn_ok)
        btns.add_widget(btn_cancel)
        content.add_widget(btns)
        
        self.popup = Popup(title=ar_text("اختر المجلد"), content=content, size_hint=(0.9, 0.9))
        self.popup.open()

    def select_path(self, instance):
        selection = self.file_chooser.selection
        if selection:
            self.txt_audio_path.set_text_value(selection[0])
        else:
            self.txt_audio_path.set_text_value(self.file_chooser.path)
        self.popup.dismiss()

    def close_popup(self, instance):
        self.popup.dismiss()

    def start_recitation(self, instance):
        try:
            self.app.audio_path = self.txt_audio_path.get_text().strip()
            rec_type = self.spin_type.text
            rep_ind = int(self.txt_rep_ind.get_text())
            rep_grp = int(self.txt_rep_grp.get_text())
            grp_size = int(self.txt_grp_size.get_text())
            mode = self.spin_mode.text
            playlist = []
            
            if rec_type == 'Pages':
                # Page Mode
                start_page = int(self.txt_aya_start.get_text())
                end_page = int(self.txt_aya_end.get_text())
                
                if start_page > end_page:
                    start_page, end_page = end_page, start_page
                    
                # Generate page files list
                page_files = []
                for i in range(start_page, end_page + 1):
                    # We use 001.mp3 format, player will also check 1.mp3
                    page_files.append(f"{i:03d}.mp3")
                
                # Simple repetition for pages (treat as Single mode usually)
                for f in page_files:
                    for _ in range(rep_ind):
                        playlist.append(f)
            
            else:
                # Ayah Mode
                sura = int(self.spin_sura_start.text)
                aya_start = int(self.txt_aya_start.get_text())
                aya_end = int(self.txt_aya_end.get_text())
                
                # Generate list of files (Ayahs)
                # Assuming files are named like 001001.mp3 (SurahAyah)
                ayahs = []
                for i in range(aya_start, aya_end + 1):
                    filename = f"{sura:03d}{i:03d}.mp3"
                    ayahs.append(filename)
                
                if mode == 'Single':
                    for f in ayahs:
                        for _ in range(rep_ind):
                            playlist.append(f)
                            
                elif mode == 'Group':
                    for _ in range(rep_grp):
                        playlist.extend(ayahs)
                        
                elif mode == 'Complex':
                    # Complex Logic:
                    # 1. Repeat current ayah N times
                    # 2. Repeat last M ayahs K times
                    for i, f in enumerate(ayahs):
                        # Individual Repetition
                        for _ in range(rep_ind):
                            playlist.append(f)
                        
                        # Group/Link Repetition
                        if i > 0:
                            start_idx = max(0, i - grp_size + 1)
                            group_files = ayahs[start_idx : i + 1]
                            for _ in range(rep_grp):
                                playlist.extend(group_files)
            
            if playlist:
                self.app.start_playlist(playlist)
                self.manager.current = 'reader'
            else:
                print("Empty playlist")
                
        except ValueError:
            print("Invalid input")

    def go_back(self, instance):
        self.manager.current = 'home'

class PlanManager:
    def __init__(self):
        self.filename = 'yusr_plans.json'
        self.plans = self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.plans, f, ensure_ascii=False)
        except:
            pass

    def add_plan(self, name, days, items=None, **kwargs):
        self.plans[name] = {
            'days': days,
            'created_at': datetime.now().strftime('%Y-%m-%d'),
            **kwargs,
            'items': items if items else [],
            'history': []
        }
        self.save()

    def mark_done(self, name):
        if name in self.plans:
            today = datetime.now().strftime('%Y-%m-%d')
            if today not in self.plans[name]['history']:
                self.plans[name]['history'].append(today)
                self.save()

    def delete_plan(self, name):
        if name in self.plans:
            del self.plans[name]
            self.save()

    def get_plan(self, name):
        return self.plans.get(name)

class PlansHomeScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        # Header
        header = BoxLayout(size_hint_y=None, height=dp(60))
        header.add_widget(Label(text=ar_text("خطط الحفظ والمراجعة"), font_size='22sp', bold=True, color=COLOR_PRIMARY, halign='right', text_size=(Window.width*0.6, None)))
        layout.add_widget(header)
        
        # Plans List
        self.users_grid = GridLayout(cols=1, spacing=dp(15), size_hint_y=None)
        self.users_grid.bind(minimum_height=self.users_grid.setter('height'))
        
        self.scroll = ScrollView()
        self.scroll.add_widget(self.users_grid)
        layout.add_widget(self.scroll)
        
        # Add Button
        btn_new = MDRaisedButton(text=ar_text("+ إنشاء خطة جديدة"), md_bg_color=COLOR_PRIMARY, size_hint_y=None, height=STD_HEIGHT, font_name='Roboto')
        btn_new.bind(on_press=self.go_create)
        layout.add_widget(btn_new)
        
        # Bottom Nav
        layout.add_widget(BottomNavBar(current_tab='review'))
        self.add_widget(layout)

    def on_enter(self):
        self.users_grid.clear_widgets()
        plans = self.app.plan_manager.plans
        if not plans:
            self.users_grid.add_widget(Label(text=ar_text("لا توجد خطط حالياً. ابدأ بإنشاء خطة جديدة!"), color=(0.5,0.5,0.5,1), size_hint_y=None, height=dp(100)))
        else:
            for name in plans:
                plan_data = plans[name]
                self.add_plan_card(name, plan_data)

    def add_plan_card(self, name, data):
        card = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(90), padding=dp(10), spacing=dp(10))
        
        # Background
        with card.canvas.before:
            Color(1, 1, 1, 1)
            card.bg_rect = RoundedRectangle(pos=card.pos, size=card.size, radius=[dp(10)])
            Color(0, 0, 0, 0.1)
            card.shadow = BoxShadow(pos=card.pos, size=card.size, offset=(0, -2), blur_radius=5)
        def _update_card_canvas(instance, value):
            instance.bg_rect.pos = instance.pos
            instance.bg_rect.size = instance.size
            instance.shadow.pos = instance.pos
            instance.shadow.size = instance.size
        card.bind(pos=_update_card_canvas, size=_update_card_canvas)

        # Icon
        p_cat = data.get('plan_category', 'schedule')
        icon = "🎧" if p_cat == 'audio' else "📅"
        card.add_widget(Label(text=icon, font_size='30sp', size_hint_x=None, width=dp(50)))
        
        # Info
        info = BoxLayout(orientation='vertical')
        info.add_widget(Label(text=ar_text(name), color=COLOR_TEXT, font_size='18sp', bold=True, halign='right', text_size=(Window.width*0.4, None)))
        sub_text = "تكرار صوتي" if p_cat == 'audio' else "جدول متابعة"
        info.add_widget(Label(text=ar_text(sub_text), color=(0.5,0.5,0.5,1), font_size='14sp', halign='right', text_size=(Window.width*0.4, None)))
        card.add_widget(info)
        
        # Actions
        # Edit
        btn_edit = CustomIconButton(icon="pencil", theme_text_color="Custom", text_color=COLOR_ACCENT)
        btn_edit.plan_name = name
        btn_edit.bind(on_press=self.edit_plan)
        card.add_widget(btn_edit)
        
        # Delete
        btn_del = CustomIconButton(icon="delete", theme_text_color="Custom", text_color=(0.8, 0.3, 0.3, 1))
        btn_del.plan_name = name
        btn_del.bind(on_press=self.delete_plan_confirm)
        card.add_widget(btn_del)
        
        # Open
        btn_open = CustomIconButton(icon="arrow-right-bold", theme_text_color="Custom", text_color=COLOR_PRIMARY)
        btn_open.plan_name = name
        btn_open.bind(on_press=self.go_dashboard)
        card.add_widget(btn_open)
        
        self.users_grid.add_widget(card)

    def go_create(self, instance):
        self.app.editing_plan_name = None # New mode
        self.manager.current = 'plan_create'

    def edit_plan(self, instance):
        self.app.editing_plan_name = instance.plan_name
        self.manager.current = 'plan_create'

    def delete_plan_confirm(self, instance):
        name = instance.plan_name
        # Direct delete for simplicity, or add Popup confirmation
        self.app.plan_manager.delete_plan(name)
        self.on_enter()

    def go_dashboard(self, instance):
        self.app.current_plan_user = instance.plan_name
        self.manager.current = 'plan_dashboard'

    def go_back(self, instance):
        self.manager.current = 'home'

class PlanCreateScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.plan_items = []
        self.is_audio_plan = False
        
        # Main Container
        root = BoxLayout(orientation='vertical')
        
        # Header
        header = BoxLayout(size_hint_y=None, height=STD_HEIGHT, padding=dp(15))
        with header.canvas.before:
            Color(*COLOR_SURFACE)
            RoundedRectangle(pos=header.pos, size=header.size, radius=[0,0,dp(20),dp(20)])
        header.bind(pos=lambda inst, v: setattr(inst.canvas.before.children[-1], 'pos', v))
        header.bind(size=lambda inst, v: setattr(inst.canvas.before.children[-1], 'size', v))
        
        self.lbl_header = Label(text=ar_text("إعداد خطة جديدة"), font_size='20sp', bold=True, color=COLOR_PRIMARY)
        header.add_widget(self.lbl_header)
        root.add_widget(header)
        
        # Scrollable Content
        scroll = ScrollView()
        content = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))
        
        # 1. Name
        name_section = self._create_section_box()
        name_section.add_widget(self._create_label("اسم الخطة / المستخدم:"))
        self.txt_name_container, self.txt_name_input = self._create_styled_input(hint="مثال: ختمة رمضان")
        name_section.add_widget(self.txt_name_container)
        content.add_widget(name_section)
        
        # 2. Plan Category
        cat_section = self._create_section_box()
        cat_section.add_widget(self._create_label("نوع الخطة:"))
        self.spin_cat = Spinner(text=ar_text('جدول متابعة'), values=(ar_text('جدول متابعة'), ar_text('تكرار صوتي')), background_color=COLOR_PRIMARY, font_name='Roboto', size_hint_y=None, height=STD_HEIGHT)
        self.spin_cat.bind(text=self.on_category_change)
        cat_section.add_widget(self.spin_cat)
        content.add_widget(cat_section)
        
        # --- SCHEDULE SETTINGS CONTAINER ---
        self.container_schedule = BoxLayout(orientation='vertical', spacing=dp(15), size_hint_y=None)
        self.container_schedule.bind(minimum_height=self.container_schedule.setter('height'))
        
        self.container_schedule.add_widget(self._create_label("إعدادات الجدول:"))
        row_type = BoxLayout(spacing=dp(10), size_hint_y=None, height=STD_HEIGHT)
        self.spin_type = Spinner(text=ar_text('مراجعة'), values=(ar_text('حفظ'), ar_text('مراجعة')), background_color=COLOR_ACCENT, color=(1,1,1,1), font_name='Roboto')
        self.spin_dir = Spinner(text=ar_text('تصاعدي'), values=(ar_text('تصاعدي'), ar_text('تنازلي')), background_color=COLOR_ACCENT, color=(1,1,1,1), font_name='Roboto')
        row_type.add_widget(self.spin_type)
        row_type.add_widget(self.spin_dir)
        self.container_schedule.add_widget(row_type)
        
        self.container_schedule.add_widget(self._create_label("تحديد الأجزاء/السور:"))
        
        # Selection Type Spinner
        self.spin_sel_type = Spinner(
            text=ar_text('سورة'), 
            values=(ar_text('سورة'), ar_text('جزء'), ar_text('صفحة')),
            size_hint_y=None, height=STD_HEIGHT,
            background_color=COLOR_PRIMARY, font_name='Roboto'
        )
        self.spin_sel_type.bind(text=self.on_selection_type_change)
        self.container_schedule.add_widget(self.spin_sel_type)
        
        # Dynamic Input Container
        self.input_container = BoxLayout(spacing=dp(10), size_hint_y=None, height=STD_HEIGHT)
        self.container_schedule.add_widget(self.input_container)
        
        # Add Button
        btn_add = MDRaisedButton(text=ar_text("إضافة للقائمة +"), size_hint_y=None, height=STD_HEIGHT, md_bg_color=(0.3, 0.6, 0.8, 1), font_name='Roboto')
        btn_add.bind(on_press=self.add_range_item)
        self.container_schedule.add_widget(btn_add)
        
        # List of added items
        self.container_schedule.add_widget(self._create_label("محتوى الخطة:"))
        self.items_container = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.items_container.bind(minimum_height=self.items_container.setter('height'))
        
        # Scroll for items list (nested scroll)
        items_scroll = ScrollView(size_hint_y=None, height=dp(150))
        with items_scroll.canvas.before:
            Color(0.9, 0.9, 0.9, 1)
            RoundedRectangle(pos=items_scroll.pos, size=items_scroll.size, radius=[dp(10)])
        items_scroll.bind(pos=lambda inst, v: setattr(inst.canvas.before.children[-1], 'pos', v))
        items_scroll.bind(size=lambda inst, v: setattr(inst.canvas.before.children[-1], 'size', v))
        
        items_scroll.add_widget(self.items_container)
        self.container_schedule.add_widget(items_scroll)
        
        self.container_schedule.add_widget(self._create_label("طريقة التقسيم:"))
        row_calc = BoxLayout(spacing=dp(10), size_hint_y=None, height=STD_HEIGHT)
        self.spin_calc = Spinner(text=ar_text('عدد الأيام'), values=(ar_text('عدد الأيام'), ar_text('صفحات يومياً')), size_hint_x=0.6, font_name='Roboto', background_color=COLOR_ACCENT)
        self.txt_amount_container, self.txt_amount_input = self._create_styled_input(text='30', hint='القيمة')
        self.txt_amount_container.size_hint_x = 0.4
        row_calc.add_widget(self.spin_calc)
        row_calc.add_widget(self.txt_amount_container)
        self.container_schedule.add_widget(row_calc)
        
        content.add_widget(self.container_schedule)
        
        # --- AUDIO SETTINGS CONTAINER ---
        self.container_audio = BoxLayout(orientation='vertical', spacing=dp(15), size_hint_y=None)
        self.container_audio.bind(minimum_height=self.container_audio.setter('height'))
        self.container_audio.opacity = 0 # Hidden by default
        self.container_audio.height = 0
        
        self.container_audio.add_widget(self._create_label("نطاق التكرار:"))
        
        # Sura
        row_sura = BoxLayout(spacing=dp(10), size_hint_y=None, height=STD_HEIGHT)
        row_sura.add_widget(Label(text=ar_text("السورة:"), color=COLOR_TEXT, size_hint_x=0.3))
        self.spin_audio_sura = Spinner(text='1', values=[str(i) for i in range(1, 115)])
        row_sura.add_widget(self.spin_audio_sura)
        self.container_audio.add_widget(row_sura)
        
        # Ayahs
        row_ayahs = BoxLayout(spacing=dp(10), size_hint_y=None, height=STD_HEIGHT)
        self.txt_audio_start_container, self.txt_audio_start_input = self._create_styled_input(text='1', hint='من آية')
        self.txt_audio_end_container, self.txt_audio_end_input = self._create_styled_input(text='5', hint='إلى آية')
        row_ayahs.add_widget(self.txt_audio_start_container)
        row_ayahs.add_widget(self.txt_audio_end_container)
        self.container_audio.add_widget(row_ayahs)
        
        # Repeats
        self.container_audio.add_widget(self._create_label("إعدادات التكرار:"))
        self.txt_rep_ind_container, self.txt_rep_ind_input = self._create_styled_input(text='3', hint='تكرار الآية')
        self.container_audio.add_widget(self.txt_rep_ind_container)
        
        self.txt_rep_grp_container, self.txt_rep_grp_input = self._create_styled_input(text='1', hint='تكرار المجموعة')
        self.container_audio.add_widget(self.txt_rep_grp_container)
        
        content.add_widget(self.container_audio)
        
        scroll.add_widget(content)
        root.add_widget(scroll)
        
        # Footer Buttons
        footer = BoxLayout(size_hint_y=None, height=dp(80), padding=(dp(10), dp(10)), spacing=dp(10))
        btn_save = MDRaisedButton(text=ar_text("حفظ"), md_bg_color=(0.2, 0.7, 0.2, 1), font_size='18sp')
        btn_save.bind(on_press=self.save_plan)
        btn_cancel = MDFlatButton(text=ar_text("إلغاء"), font_size='18sp')
        btn_cancel.bind(on_press=self.go_back)
        
        footer.add_widget(btn_save)
        footer.add_widget(btn_cancel)
        root.add_widget(footer)
        
        self.add_widget(root)
        
        # Initialize inputs
        self.on_selection_type_change(None, ar_text('سورة'))

    def on_enter(self):
        # Check if editing
        name = getattr(self.app, 'editing_plan_name', None)
        if name:
            self.lbl_header.text = ar_text(f"تعديل الخطة: {name}")
            self.txt_name_input.set_text_value(name)
            self.txt_name_input.disabled = True # Cannot change name while editing key
            
            plan = self.app.plan_manager.get_plan(name)
            if plan:
                cat = plan.get('plan_category', 'schedule')
                if cat == 'audio':
                    self.spin_cat.text = ar_text('تكرار صوتي')
                    self.spin_audio_sura.text = str(plan.get('sura', 1))
                    self.txt_audio_start_input.set_text_value(str(plan.get('aya_start', 1)))
                    self.txt_audio_end_input.set_text_value(str(plan.get('aya_end', 1)))
                    self.txt_rep_ind_input.set_text_value(str(plan.get('rep_ind', 3)))
                    self.txt_rep_grp_input.set_text_value(str(plan.get('rep_grp', 1)))
                else:
                    self.spin_cat.text = ar_text('جدول متابعة')
                    self.plan_items = plan.get('items', [])
                    self.refresh_items_list()
                    self.txt_amount_input.set_text_value(str(plan.get('amount_val', 30)))
        else:
            self.lbl_header.text = ar_text("إعداد خطة جديدة")
            self.txt_name_input.set_text_value("")
            self.txt_name_input.disabled = False
            self.plan_items = []
            self.refresh_items_list()

    def on_category_change(self, instance, value):
        if value == ar_text('تكرار صوتي'):
            self.container_schedule.opacity = 0
            self.container_schedule.height = 0
            self.container_audio.opacity = 1
            self.container_audio.height = dp(300) # Approx height
            self.is_audio_plan = True
        else:
            self.container_schedule.opacity = 1
            self.container_schedule.height = self.container_schedule.minimum_height
            self.container_audio.opacity = 0
            self.container_audio.height = 0
            self.is_audio_plan = False

    def _create_label(self, text):
        return Label(text=ar_text(text), color=COLOR_TEXT, size_hint_y=None, height=dp(30), halign='right', text_size=(Window.width-dp(40), None))

    def _create_styled_input(self, text='', hint=''):
        container = BoxLayout(size_hint_y=None, height=STD_HEIGHT)
        ti = ArabicTextInput(text=text, hint_text=ar_text(hint) if hint else '')
        # Remove default border from ArabicTextInput for this specific usage if needed, 
        # but keeping it consistent is better.
        container.add_widget(ti)
        return container, ti

    def _create_section_box(self):
        section = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(12))
        section.bind(minimum_height=section.setter('height'))
        with section.canvas.before:
            Color(*COLOR_SURFACE)
            RoundedRectangle(pos=section.pos, size=section.size, radius=[dp(12)])
        section.bind(pos=lambda i,v: setattr(i.canvas.before.children[-1], 'pos', v), size=lambda i,v: setattr(i.canvas.before.children[-1], 'size', v))
        return section
        
    def on_selection_type_change(self, instance, value):
        self.input_container.clear_widgets()
        val_clean = value  # ar_text already applied
        
        if val_clean == ar_text('سورة'):
            self.sel_start = Spinner(text='1', values=[str(i) for i in range(1, 115)])
            self.sel_end = Spinner(text='114', values=[str(i) for i in range(1, 115)])
            self.input_container.add_widget(Label(text=ar_text("من:"), color=COLOR_TEXT, size_hint_x=0.15))
            self.input_container.add_widget(self.sel_start)
            self.input_container.add_widget(Label(text=ar_text("إلى:"), color=COLOR_TEXT, size_hint_x=0.15))
            self.input_container.add_widget(self.sel_end)
            
        elif val_clean == ar_text('جزء'):
            self.sel_start = Spinner(text='1', values=[str(i) for i in range(1, 31)])
            self.sel_end = Spinner(text='30', values=[str(i) for i in range(1, 31)])
            self.input_container.add_widget(Label(text=ar_text("من:"), color=COLOR_TEXT, size_hint_x=0.15))
            self.input_container.add_widget(self.sel_start)
            self.input_container.add_widget(Label(text=ar_text("إلى:"), color=COLOR_TEXT, size_hint_x=0.15))
            self.input_container.add_widget(self.sel_end)
            
        elif val_clean == ar_text('صفحة'):
            self.sel_start = ArabicTextInput(text='1', input_filter='int')
            self.sel_end = ArabicTextInput(text='604', input_filter='int')
            self.input_container.add_widget(Label(text=ar_text("من:"), color=COLOR_TEXT, size_hint_x=0.15))
            self.input_container.add_widget(self.sel_start)
            self.input_container.add_widget(Label(text=ar_text("إلى:"), color=COLOR_TEXT, size_hint_x=0.15))
            self.input_container.add_widget(self.sel_end)

    def add_range_item(self, instance):
        try:
            # Check if sel_start is Spinner or TextInput
            if isinstance(self.sel_start, ArabicTextInput):
                start = int(self.sel_start.get_text())
                end = int(self.sel_end.get_text())
            else:
                start = int(self.sel_start.text)
                end = int(self.sel_end.text)
                
            if start > end: start, end = end, start
            
            sel_type_txt = self.spin_sel_type.text
            type_code = 'sura'
            display_txt = ""
            
            if sel_type_txt == ar_text('سورة'):
                type_code = 'sura'
                display_txt = f"سورة {start} إلى {end}"
            elif sel_type_txt == ar_text('جزء'):
                type_code = 'juz'
                display_txt = f"جزء {start} إلى {end}"
            else:
                type_code = 'page'
                display_txt = f"صفحة {start} إلى {end}"
            
            item_data = {'type': type_code, 'start': start, 'end': end, 'display': display_txt}
            self.plan_items.append(item_data)
            self.refresh_items_list()
            
        except ValueError:
            pass

    def refresh_items_list(self):
        self.items_container.clear_widgets()
        for i, item in enumerate(self.plan_items):
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
            lbl = Label(text=ar_text(item['display']), color=COLOR_TEXT, size_hint_x=0.8, halign='right', text_size=(Window.width*0.6, None))
            btn_del = CustomIconButton(icon="close", theme_text_color="Custom", text_color=(0.8, 0.2, 0.2, 1), size_hint_x=0.2)
            btn_del.index = i
            btn_del.bind(on_press=self.delete_item)
            
            row.add_widget(lbl)
            row.add_widget(btn_del)
            self.items_container.add_widget(row)

    def delete_item(self, instance):
        idx = instance.index
        if 0 <= idx < len(self.plan_items):
            del self.plan_items[idx]
            self.refresh_items_list()

    def save_plan(self, instance):
        name = self.txt_name_input.get_text().strip()
        if not name: 
            print("Name is empty")
            return
        
        if not self.is_audio_plan and not self.plan_items:
            print("No items in plan")
            # Maybe show popup?
            return
        
        cat = 'audio' if self.is_audio_plan else 'schedule'
        
        try:
            if cat == 'schedule':
                amount_val = int(self.txt_amount_input.get_text())
                p_type = 'hifz' if self.spin_type.text == ar_text('حفظ') else 'review'
                p_dir = 'desc' if self.spin_dir.text == ar_text('تنازلي') else 'asc'
                a_type = 'pages' if self.spin_calc.text == ar_text('صفحات يومياً') else 'days'
                
                self.app.plan_manager.add_plan(
                    name, amount_val,
                    plan_category='schedule',
                    items=self.plan_items,
                    plan_type=p_type,
                    direction=p_dir,
                    amount_type=a_type,
                    amount_val=amount_val
                )
            else:
                # Audio Plan
                sura = int(self.spin_audio_sura.text) if self.spin_audio_sura.text else 1
                start = int(self.txt_audio_start_input.get_text()) if self.txt_audio_start_input.get_text() else 1
                end = int(self.txt_audio_end_input.get_text()) if self.txt_audio_end_input.get_text() else 1
                rep_ind = int(self.txt_rep_ind_input.get_text()) if self.txt_rep_ind_input.get_text() else 1
                rep_grp = int(self.txt_rep_grp_input.get_text()) if self.txt_rep_grp_input.get_text() else 1
                
                self.app.plan_manager.add_plan(
                    name, 0, # Days not relevant
                    plan_category='audio',
                    sura=sura,
                    aya_start=start,
                    aya_end=end,
                    rep_ind=rep_ind,
                    rep_grp=rep_grp
                )
            
            # Force refresh of Plans Home
            plans_screen = self.manager.get_screen('plans_home')
            if plans_screen:
                plans_screen.on_enter()
                
            self.manager.current = 'plans_home'
        except ValueError:
            print("Value Error in save")

    def go_back(self, instance):
        self.manager.current = 'plans_home'

class PlanDashboardScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(15))
        
        # Header
        self.lbl_title = Label(text="", font_size='24sp', color=COLOR_PRIMARY, bold=True, size_hint_y=None, height=dp(40), halign='right')
        layout.add_widget(self.lbl_title)
        
        # Main Info Card
        card = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15), size_hint_y=0.6)
        with card.canvas.before:
            Color(*COLOR_SURFACE)
            RoundedRectangle(pos=card.pos, size=card.size, radius=[dp(15)])
        card.bind(pos=lambda i,v: setattr(i.canvas.before.children[-1], 'pos', v), size=lambda i,v: setattr(i.canvas.before.children[-1], 'size', v))
        
        self.lbl_report = Label(text="", color=COLOR_TEXT, font_size='16sp', size_hint_y=None, height=dp(30))
        card.add_widget(self.lbl_report)
        
        self.progress_bar = YusrProgressBar(size_hint_y=None, height=dp(10))
        card.add_widget(self.progress_bar)
        
        card.add_widget(Label(size_hint_y=None, height=dp(20))) # Spacer
        
        self.lbl_task = Label(text="", font_size='22sp', color=COLOR_PRIMARY, bold=True, halign='center')
        card.add_widget(self.lbl_task)
        layout.add_widget(card)
        
        layout.add_widget(Label(size_hint_y=0.4)) # Spacer
        
        btn_start = MDRaisedButton(text=ar_text("ابدأ الورد / التلاوة"), md_bg_color=COLOR_ACCENT, size_hint_y=None, height=STD_HEIGHT)
        btn_start.bind(on_press=self.start_wird)
        layout.add_widget(btn_start)
        
        btn_done = MDRaisedButton(text=ar_text("تسجيل الإنجاز (تم)"), md_bg_color=(0.2, 0.8, 0.2, 1), size_hint_y=None, height=STD_HEIGHT)
        btn_done.bind(on_press=self.mark_done)
        layout.add_widget(btn_done)
        
        btn_back = MDFlatButton(text=ar_text("عودة"), size_hint_y=None, height=STD_HEIGHT)
        btn_back.bind(on_press=self.go_back)
        layout.add_widget(btn_back)
        
        self.add_widget(layout)
        self.today_page = 1

    def on_enter(self):
        name = self.app.current_plan_user
        plan = self.app.plan_manager.get_plan(name)
        if not plan: return
        
        self.lbl_title.text = ar_text(f"خطة: {name}")
        
        # Check Type
        if plan.get('plan_category') == 'audio':
            self.progress_bar.opacity = 0
            self.setup_audio_dashboard(plan)
        else:
            self.progress_bar.opacity = 1
            self.setup_schedule_dashboard(plan)

    def setup_audio_dashboard(self, plan):
        sura = plan.get('sura', 1)
        sura_name = self.app.data_manager.get_sura_name(sura) if self.app.data_manager else ''
        start = plan.get('aya_start', 1)
        end = plan.get('aya_end', 1)
        rep_ind = plan.get('rep_ind', 3)
        
        self.lbl_report.text = ar_text("خطة تكرار صوتي")
        self.lbl_task.text = ar_text(f"سورة {sura_name}\nمن آية {start} إلى {end}\nتكرار الآية: {rep_ind} مرات")

    def setup_schedule_dashboard(self, plan):
        
        # Calculate progress
        # Retrieve extended properties with defaults
        direction = plan.get('direction', 'asc')
        amount_type = plan.get('amount_type', 'days')
        amount_val = plan.get('amount_val', plan.get('days', 30))
        
        history = plan.get('history', [])
        days_done = len(history)
        
        # --- Calculate Total Pages from Items ---
        all_pages = []
        dm = self.app.data_manager
        
        items = plan.get('items', [])
        # Fallback for legacy
        if not items and 'start_sura' in plan:
            items = [{'type': 'sura', 'start': plan['start_sura'], 'end': plan['end_sura']}]
            
        for item in items:
            itype = item['type']
            start = int(item['start'])
            end = int(item['end'])
            
            if itype == 'page':
                all_pages.extend(range(start, end + 1))
            elif itype == 'juz':
                s_page = JUZ_START_PAGES.get(start, 1)
                e_page = JUZ_START_PAGES.get(end + 1, 605) - 1
                if end == 30: e_page = 604
                all_pages.extend(range(s_page, e_page + 1))
            elif itype == 'sura':
                if dm:
                    s_page = dm.sura_pages.get(start, 1)
                    next_sura = end + 1
                    e_page = dm.sura_pages.get(next_sura, 605) - 1
                    if end == 114: e_page = 604
                    all_pages.extend(range(s_page, e_page + 1))
        
        # Remove duplicates while preserving order? 
        # For simplicity, we trust the user's order.
        # If direction is desc, reverse the whole list
        if direction == 'desc':
            all_pages.reverse()
            
        total_pages = len(all_pages)
        if total_pages == 0:
            self.lbl_task.text = ar_text("الخطة فارغة")
            return

        # Calculate Rate & Total Days
        if amount_type == 'pages':
            rate = amount_val
            days_total = math.ceil(total_pages / rate)
        else:
            days_total = amount_val
            rate = math.ceil(total_pages / days_total)
        
        progress_val = (days_done / days_total) if days_total > 0 else 0
        self.progress_bar.value = progress_val
        
        self.lbl_report.text = ar_text(f"الأيام المنجزة: {days_done} / {days_total}")
        
        if days_done >= days_total:
            self.lbl_task.text = ar_text("تم ختم الخطة بحمد الله!")
            self.today_page = all_pages[0] if all_pages else 1
        else:
            start_idx = days_done * rate
            end_idx = min(total_pages, start_idx + rate)
            
            today_slice = all_pages[start_idx : end_idx]
            
            if today_slice:
                p_start = today_slice[0]
                p_end = today_slice[-1]
                self.today_page = p_start
                
                # Display logic
                if p_start == p_end:
                    self.lbl_task.text = ar_text(f"ورد اليوم: صفحة {p_start}")
                else:
                    # Show range. Note: if mixed ranges, this might look weird (e.g. 604 to 2)
                    # But usually it's sequential.
                    self.lbl_task.text = ar_text(f"ورد اليوم: صفحة {p_start} إلى {p_end}")
            else:
                self.lbl_task.text = ar_text("تم الانتهاء")

    def start_wird(self, instance):
        name = self.app.current_plan_user
        plan = self.app.plan_manager.get_plan(name)
        
        if plan.get('plan_category') == 'audio':
            # Generate Playlist
            sura = plan.get('sura', 1)
            start = plan.get('aya_start', 1)
            end = plan.get('aya_end', 1)
            rep_ind = plan.get('rep_ind', 1)
            rep_grp = plan.get('rep_grp', 1)
            
            playlist = []
            ayahs = []
            for i in range(start, end + 1):
                filename = f"{sura:03d}{i:03d}.mp3"
                ayahs.append(filename)
            
            # Simple logic: Repeat each ayah N times, then repeat whole group M times
            for _ in range(rep_grp):
                for f in ayahs:
                    for _ in range(rep_ind):
                        playlist.append(f)
            
            self.app.start_playlist(playlist)
            self.manager.current = 'reader'
            
        else:
            self.app.current_page = self.today_page
            self.manager.current = 'reader'
            self.manager.get_screen('reader').load_page(self.today_page)

    def mark_done(self, instance):
        self.app.plan_manager.mark_done(self.app.current_plan_user)
        self.on_enter() # Refresh UI

    def go_back(self, instance):
        self.manager.current = 'plans_home'

class ReviewConfigScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        layout.add_widget(Label(text=ar_text("إعدادات خطة المراجعة"), font_size='24sp', color=(0,0,0,1), size_hint_y=0.1))
        
        # --- Selection Mode ---
        mode_box = BoxLayout(size_hint_y=None, height=STD_HEIGHT, spacing=10)
        mode_box.add_widget(Label(text=ar_text("طريقة التحديد:"), color=(0,0,0,1), size_hint_x=0.4))
        self.spin_mode = Spinner(
            text=ar_text('سورة'),
            values=(ar_text('سورة'), ar_text('صفحة'), ar_text('جزء')),
            background_color=COLOR_ACCENT,
            font_name='Roboto'
        )
        self.spin_mode.bind(text=self.on_mode_change)
        mode_box.add_widget(self.spin_mode)
        layout.add_widget(mode_box)

        # --- Dynamic Input Container ---
        self.input_container = GridLayout(cols=2, spacing=10, size_hint_y=None, height=dp(100))
        layout.add_widget(self.input_container)
        
        # Initialize with Sura mode
        self.on_mode_change(None, ar_text('سورة'))
        
        layout.add_widget(Label(text=ar_text("سرعة العرض التلقائي"), color=(0,0,0,1), size_hint_y=0.1))
        # KivyMD 2.0 dev fix: Slider step must be integer. Using 1-20 to represent 0.1-2.0
        self.speed_slider = MDSlider(min=1, max=20, value=5, step=1, size_hint_y=0.1)
        layout.add_widget(self.speed_slider)
        
        btn_auto = MDRaisedButton(text=ar_text("بدء المراجعة التلقائية (وقت)"), md_bg_color=(0.3, 0.7, 0.3, 1), size_hint_y=0.15)
        btn_auto.bind(on_press=self.start_auto)
        layout.add_widget(btn_auto)
        
        btn_manual = MDRaisedButton(text=ar_text("بدء المراجعة اليدوية (نقر)"), md_bg_color=(0.3, 0.5, 0.8, 1), size_hint_y=0.15)
        btn_manual.bind(on_press=self.start_manual)
        layout.add_widget(btn_manual)
        
        btn_voice = MDRaisedButton(text=ar_text("بدء المراجعة الصوتية (تفاعلي)"), md_bg_color=(0.8, 0.5, 0.3, 1), size_hint_y=0.15)
        btn_voice.bind(on_press=self.start_voice)
        layout.add_widget(btn_voice)

        layout.add_widget(BottomNavBar(current_tab='review'))
        
        layout.add_widget(Label(size_hint_y=0.2)) # Spacer
        
        self.add_widget(layout)

    def on_mode_change(self, instance, value):
        self.input_container.clear_widgets()
        val = value
        
        if val == ar_text('سورة'):
            self.input_container.add_widget(Label(text=ar_text("السورة:"), color=(0,0,0,1)))
            
            sura_values = [str(i) for i in range(1, 115)]
            if self.app.data_manager:
                 # Use simple numbers if names cause issues, or format "1 - Name"
                 # ar_text handles reshaping, so "1 - Name" should be fine
                 sura_values = [ar_text(f"{i} - {self.app.data_manager.get_sura_name(i)}") for i in range(1, 115)]
            
            # Ensure text is valid
            current_text = sura_values[0]
            
            self.spin_sura = Spinner(text=current_text, values=sura_values, font_name='Roboto')
            self.input_container.add_widget(self.spin_sura)
            
            self.input_container.add_widget(Label(text=ar_text("رقم الآية:"), color=(0,0,0,1)))
            self.txt_aya = ArabicTextInput(text='1', input_filter='int')
            self.input_container.add_widget(self.txt_aya)
            
        elif val == ar_text('صفحة'):
            self.input_container.add_widget(Label(text=ar_text("رقم الصفحة:"), color=(0,0,0,1)))
            self.txt_page = ArabicTextInput(text='1', input_filter='int')
            self.input_container.add_widget(self.txt_page)
            # Fillers
            self.input_container.add_widget(Label())
            self.input_container.add_widget(Label())

        elif val == ar_text('جزء'):
            self.input_container.add_widget(Label(text=ar_text("رقم الجزء:"), color=(0,0,0,1)))
            self.spin_juz = Spinner(text='1', values=[str(i) for i in range(1, 31)])
            self.input_container.add_widget(self.spin_juz)
            # Fillers
            self.input_container.add_widget(Label())
            self.input_container.add_widget(Label())

    def _update_page_from_selection(self):
        """Updates the app's current page based on the selected criteria."""
        if not self.app.data_manager: return
        
        mode = self.spin_mode.text
        target_page = 1
        
        try:
            if mode == ar_text('سورة'):
                sura_txt = self.spin_sura.text
                if '-' in sura_txt:
                    sura = int(sura_txt.split('-')[0].strip())
                else:
                    sura = int(sura_txt)
                aya = int(self.txt_aya.get_text())
                
                # Find page
                found = False
                for entry in self.app.data_manager.all_ayas:
                    if entry.get('sura_no') == sura and entry.get('aya_no') == aya:
                        target_page = entry.get('page', 1)
                        found = True
                        break
                if not found:
                    target_page = self.app.data_manager.sura_pages.get(sura, 1)
            
            elif mode == ar_text('صفحة'):
                target_page = int(self.txt_page.get_text())
                
            elif mode == ar_text('جزء'):
                juz = int(self.spin_juz.text)
                if hasattr(self.app.data_manager, 'juz_pages'):
                    target_page = self.app.data_manager.juz_pages.get(juz, 1)
                else:
                    target_page = JUZ_START_PAGES.get(juz, 1)
            
            # Validate
            if target_page < 1: target_page = 1
            if target_page > 604: target_page = 604
            
            self.app.current_page = target_page
            
        except ValueError:
            pass # Keep current page if input is invalid

    def start_auto(self, instance):
        self._update_page_from_selection()
        self.app.review_mode = 'auto'
        self.app.review_speed = self.speed_slider.value / 10.0
        self.app.start_review_flag = True
        self.manager.current = 'reader'

    def start_manual(self, instance):
        self._update_page_from_selection()
        self.app.review_mode = 'manual'
        self.app.start_review_flag = True
        self.manager.current = 'reader'

    def start_voice(self, instance):
        self._update_page_from_selection()
        self.app.review_mode = 'voice'
        self.app.start_review_flag = True
        self.manager.current = 'reader'

    def go_back(self, instance):
        self.manager.current = 'home'

class SimpleUserManager:
    def __init__(self):
        self.current_user = None
        self.users_file = "users.json"
        self.user_data_dir = "user_data"
        self.users = self._load_users()
        if not os.path.exists(self.user_data_dir):
            os.makedirs(self.user_data_dir)

    def _load_users(self):
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return {user: {"pin": "", "security": ""} for user in data}
                    return data
            except: return {}
        return {}

    def _save_users(self):
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, ensure_ascii=False, indent=4)
        except: pass

    def add_user(self, username):
        if username and username not in self.users:
            self.users[username] = {"pin": "", "security": ""}
            self._save_users()
            self.save_user_data(username, {})
            return True
        return False

    def delete_user(self, username):
        if username in self.users:
            del self.users[username]
            self._save_users()
            try:
                path = self.get_user_data_path(username)
                if os.path.exists(path):
                    os.remove(path)
            except: pass
            return True
        return False

    def get_user_data_path(self, username):
        return os.path.join(self.user_data_dir, f"{username}.json")

    def load_user_data(self, username):
        path = self.get_user_data_path(username)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {}

    def save_user_data(self, username, data):
        path = self.get_user_data_path(username)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except: pass

    def get_reflection(self, username, sura, aya):
        if not username: return ""
        data = self.load_user_data(username)
        reflections = data.get("reflections", {})
        return reflections.get(f"{sura}:{aya}", "")

    def save_reflection(self, username, sura, aya, text):
        if not username: return
        data = self.load_user_data(username)
        if "reflections" not in data:
            data["reflections"] = {}
        
        key = f"{sura}:{aya}"
        if text:
            data["reflections"][key] = text
        else:
            if key in data["reflections"]:
                del data["reflections"][key]
        
        self.save_user_data(username, data)

class UserManagementPopup(ModalView):
    def __init__(self, user_manager, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (0.9, 0.6)
        self.background_color = (0,0,0,0.8)
        self.user_manager = user_manager
        
        layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        with layout.canvas.before:
            Color(*COLOR_SURFACE)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(15)])
        layout.bind(pos=lambda i,v: setattr(i.canvas.before.children[-1], 'pos', v), size=lambda i,v: setattr(i.canvas.before.children[-1], 'size', v))
        
        layout.add_widget(Label(text=ar_text("إدارة المستخدمين"), font_size='20sp', color=COLOR_PRIMARY, size_hint_y=None, height=dp(40), font_name='Roboto'))
        
        # User List
        self.scroll = ScrollView()
        self.list_layout = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.list_layout.bind(minimum_height=self.list_layout.setter('height'))
        self.scroll.add_widget(self.list_layout)
        layout.add_widget(self.scroll)
        
        # Add New User Area
        add_box = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(5))
        self.txt_new_user = ArabicTextInput(hint_text=ar_text("اسم مستخدم جديد"))
        btn_add = MDRaisedButton(text=ar_text("إضافة"), md_bg_color=(0.2, 0.7, 0.2, 1), size_hint_x=0.3)
        btn_add.bind(on_press=self.add_user)
        add_box.add_widget(self.txt_new_user)
        add_box.add_widget(btn_add)
        layout.add_widget(add_box)
        
        btn_close = MDFlatButton(text=ar_text("إغلاق"), size_hint_y=None, height=dp(40))
        btn_close.bind(on_press=self.dismiss)
        layout.add_widget(btn_close)
        
        self.add_widget(layout)
        self.refresh_list()

    def refresh_list(self):
        self.list_layout.clear_widgets()
        users = self.user_manager.users
        for user in users:
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
            
            # Name Label - Bind text_size to ensure correct wrapping/display
            lbl = Label(text=ar_text(user), color=COLOR_TEXT, size_hint_x=0.6, halign='right', font_name='Roboto')
            lbl.bind(size=lambda s, w: setattr(s, 'text_size', (w[0], None)))
            
            # Select Button
            btn_select = MDRaisedButton(text=ar_text("دخول"), size_hint_x=0.2, md_bg_color=COLOR_PRIMARY)
            btn_select.user_name = user
            btn_select.bind(on_press=self.select_user)
            
            # Delete Button
            btn_delete = CustomIconButton(icon="delete", theme_text_color="Custom", text_color=(0.8, 0.2, 0.2, 1), size_hint_x=0.2)
            btn_delete.user_name = user
            btn_delete.bind(on_press=self.confirm_delete)
            
            row.add_widget(lbl)
            row.add_widget(btn_select)
            row.add_widget(btn_delete)
            self.list_layout.add_widget(row)

    def add_user(self, instance):
        name = self.txt_new_user.text.strip()
        if not name: return
        
        if self.user_manager.add_user(name):
            self.refresh_list()
            self.txt_new_user.set_text_value("")
        else:
            print(f"User {name} already exists or invalid")

    def confirm_delete(self, instance):
        user = instance.user_name
        self.user_manager.delete_user(user)
        self.refresh_list()

    def select_user(self, instance):
        name = instance.user_name
        self.user_manager.current_user = name
        # Update App
        app = App.get_running_app()
        # Refresh Settings Screen Label
        settings_screen = app.root.get_screen('settings')
        if settings_screen:
            settings_screen.lbl_user.text = ar_text(name)
        self.dismiss()

class SettingsScreen(MDScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(15))

        # Header
        header = BoxLayout(size_hint_y=None, height=dp(60))
        header.add_widget(Label(text=ar_text("الإعدادات"), font_size='22sp', bold=True, color=COLOR_PRIMARY, halign='right', text_size=(Window.width*0.8, None)))
        layout.add_widget(header)

        # ScrollView for settings content to ensure buttons are visible
        scroll = ScrollView()
        
        # --- Settings Content ---
        settings_content = BoxLayout(orientation='vertical', spacing=dp(20), padding=dp(10), size_hint_y=None)
        settings_content.bind(minimum_height=settings_content.setter('height'))

        # 0. User Management (NEW)
        user_box = BoxLayout(size_hint_y=None, height=STD_HEIGHT, spacing=dp(10))
        user_box.add_widget(Label(text=ar_text("المستخدم الحالي:"), color=COLOR_TEXT, size_hint_x=0.4, font_name='Roboto'))
        self.lbl_user = Label(text=ar_text("زائر"), color=COLOR_PRIMARY, bold=True, size_hint_x=0.3, font_name='Roboto')
        user_box.add_widget(self.lbl_user)
        
        btn_user = MDRaisedButton(text=ar_text("تغيير/إضافة"), size_hint_x=0.3, md_bg_color=COLOR_ACCENT, text_color=(1,1,1,1))
        btn_user.bind(on_press=self.show_user_popup)
        user_box.add_widget(btn_user)
        settings_content.add_widget(user_box)

        # 1. View Mode
        view_mode_box = BoxLayout(size_hint_y=None, height=STD_HEIGHT, spacing=dp(10))
        view_mode_box.add_widget(Label(text=ar_text("وضع عرض المصحف:"), color=COLOR_TEXT, size_hint_x=0.6))
        self.spin_view_mode = Spinner(
            values=(ar_text('صفحة واحدة'), ar_text('صفحتان')),
            font_name='Roboto',
            size_hint_x=0.4
        )
        self.spin_view_mode.bind(text=self.on_view_mode_change)
        view_mode_box.add_widget(self.spin_view_mode)
        settings_content.add_widget(view_mode_box)

        # 2. Font Size
        font_size_box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(80), spacing=dp(10))
        self.lbl_font_size = Label(color=COLOR_TEXT)
        font_size_box.add_widget(self.lbl_font_size)
        self.font_slider = MDSlider(min=16, max=40, step=1)
        self.font_slider.bind(value=self.on_font_size_change)
        font_size_box.add_widget(self.font_slider)
        settings_content.add_widget(font_size_box)
        
        # 3. Highlight Color
        hl_box = BoxLayout(size_hint_y=None, height=STD_HEIGHT, spacing=dp(10))
        hl_box.add_widget(Label(text=ar_text("لون تظليل التلاوة:"), color=COLOR_TEXT, size_hint_x=0.6))
        self.spin_hl_color = Spinner(
            values=[ar_text(k) for k in HIGHLIGHT_COLORS.keys()],
            font_name='Roboto',
            size_hint_x=0.4
        )
        self.spin_hl_color.bind(text=self.on_hl_color_change)
        hl_box.add_widget(self.spin_hl_color)
        settings_content.add_widget(hl_box)

        scroll.add_widget(settings_content)
        layout.add_widget(scroll)

        # Bottom Nav
        layout.add_widget(BottomNavBar(current_tab='settings'))
        self.add_widget(layout)

    def on_enter(self):
        self.spin_view_mode.text = ar_text('صفحة واحدة') if self.app.view_mode == 'single' else ar_text('صفحتان')
        self.font_slider.value = self.app.font_size
        self.lbl_font_size.text = ar_text(f"حجم الخط: {int(self.app.font_size)}")
        
        # Update user label
        if self.app.user_manager and self.app.user_manager.current_user:
             self.lbl_user.text = ar_text(self.app.user_manager.current_user)
        
        # Find current color name
        for name, code in HIGHLIGHT_COLORS.items():
            if code == self.app.highlight_color:
                self.spin_hl_color.text = ar_text(name)
                break

    def on_view_mode_change(self, spinner, text):
        self.app.view_mode = 'double' if text == ar_text('صفحتان') else 'single'
        reader_screen = self.manager.get_screen('reader')
        reader_screen.load_page(self.app.current_page)

    def show_user_popup(self, instance):
        if not self.app.user_manager:
             return
        popup = UserManagementPopup(self.app.user_manager)
        popup.open()

    def on_font_size_change(self, slider, value):
        self.app.font_size = int(value)
        self.lbl_font_size.text = ar_text(f"حجم الخط: {int(value)}")
        reader = self.manager.get_screen('reader')
        new_size = f"{int(value)}sp"
        # Update font size on the labels within the new page widgets
        if hasattr(reader, 'page_widget_right'):
            reader.page_widget_right.label.font_size = new_size
        if hasattr(reader, 'page_widget_left'):
            reader.page_widget_left.label.font_size = new_size

    def on_hl_color_change(self, spinner, text):
        # Reverse lookup
        for name, code in HIGHLIGHT_COLORS.items():
            if ar_text(name) == text:
                self.app.highlight_color = code
                break

class YusrMobileApp(MDApp):
    def build(self):
        self.title = "Yusr Lite"
        Window.clearcolor = COLOR_BG
        
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.accent_palette = "Amber"
        self.theme_cls.theme_style = "Light"

        # Data Manager
        self.data_manager = None
        if QuranDataManager:
            try:
                self.data_manager = QuranDataManager()
            except Exception as e:
                print(f"Error: {e}")
        
        # Info Manager
        self.info_manager = None
        if QuranInfoManager:
             try:
                 self.info_manager = QuranInfoManager()
             except Exception as e:
                 print(f"Error init info manager: {e}")
        
        self.current_page = 1
        self.plan_manager = PlanManager()
        # Use SimpleUserManager directly to avoid PyQt5 dependency issues
        self.user_manager = SimpleUserManager()
        
        # تهيئة المتغيرات الناقصة (هام جداً لمنع التوقف)
        self.prayer_times = {}
        self.review_mode = 'manual'
        self.start_review_flag = False
        self.review_speed = 0.5
        self.playlist = []
        self.playlist_index = 0
        self.current_plan_user = None
        self.audio_path = "audio"
        self.view_mode = 'single' # 'single' or 'double'
        self.font_size = 22
        self.highlight_color = 'ff0000' # Default Red
        
        sm = ScreenManager()
        sm.add_widget(HomeScreen(name='home'))
        sm.add_widget(ReaderScreen(name='reader'))
        sm.add_widget(IndexScreen(name='index'))
        sm.add_widget(SearchScreen(name='search'))
        sm.add_widget(PrayerScreen(name='prayers'))
        sm.add_widget(ReviewConfigScreen(name='review_config'))
        sm.add_widget(RecitationConfigScreen(name='recitation_config'))
        sm.add_widget(SettingsScreen(name='settings'))
        sm.add_widget(PlansHomeScreen(name='plans_home'))
        sm.add_widget(PlanCreateScreen(name='plan_create'))
        sm.add_widget(PlanDashboardScreen(name='plan_dashboard'))
        
        return sm

    def on_start(self):
        # جلب مواقيت الصلاة عند البدء
        self.fetch_prayer_times()

    def fetch_prayer_times(self):
        def _fetch():
            try:
                # استخدام القاهرة كافتراضي (يمكن تغييره لاحقاً ليأخذ الموقع)
                url = "http://api.aladhan.com/v1/timingsByCity?city=Cairo&country=Egypt&method=5"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    timings = data['data']['timings']
                    self.prayer_times = {
                        "Fajr": timings["Fajr"],
                        "Sunrise": timings["Sunrise"],
                        "Dhuhr": timings["Dhuhr"],
                        "Asr": timings["Asr"],
                        "Maghrib": timings["Maghrib"],
                        "Isha": timings["Isha"]
                    }
                    # تحديث الواجهة
                    Clock.schedule_once(lambda dt: self.update_prayer_ui_if_active(), 0)
            except Exception as e:
                print(f"Error fetching prayers: {e}")
        
        threading.Thread(target=_fetch).start()

    def update_prayer_ui_if_active(self):
        if self.root.current == 'prayers':
            self.root.get_screen('prayers').update_ui()
        if self.root.current == 'reader':
            self.root.get_screen('reader').update_prayer_timer(0)

    def start_playlist(self, playlist):
        self.playlist = playlist
        self.playlist_index = 0
        self.play_next_in_playlist()

    def play_next_in_playlist(self, *args):
        if self.playlist_index >= len(self.playlist):
            print("Playlist finished")
            return
            
        filename = self.playlist[self.playlist_index]
        
        # Check for file in audio folder
        # Support both padded (001.mp3) and unpadded (1.mp3)
        candidates = [filename]
        if filename.endswith('.mp3') and filename[:-4].isdigit():
            num = int(filename[:-4])
            candidates.append(f"{num}.mp3")
        
        file_path = None
        for cand in candidates:
            p = os.path.join(self.audio_path, cand)
            if os.path.exists(p):
                file_path = p
                break
        
        if file_path:
            sound = SoundLoader.load(file_path)
            if sound:
                sound.bind(on_stop=self.on_audio_stop)
                sound.play()
                
                # Highlight Logic
                if filename.endswith('.mp3') and filename[:-4].isdigit():
                    num_str = filename[:-4]
                    if len(num_str) == 6: # SSSAAA format (Ayah)
                        sura = int(num_str[:3])
                        aya = int(num_str[3:])
                        self.root.get_screen('reader').highlight_aya(sura, aya)
                    elif len(num_str) <= 3: # Page format
                        page = int(num_str)
                        self.root.get_screen('reader').load_page(page)
            else:
                self.on_audio_stop(None)
        else:
            self.on_audio_stop(None)

    def on_audio_stop(self, sound):
        self.playlist_index += 1
        Clock.schedule_once(self.play_next_in_playlist, 0.1)

if __name__ == '__main__':
    YusrMobileApp().run()
