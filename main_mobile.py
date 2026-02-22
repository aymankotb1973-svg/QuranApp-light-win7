# -*- coding: utf-8 -*-
import os
import sys

# إعداد البيئة للأندرويد
os.environ["KIVY_NO_ARGS"] = "1"

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.core.window import Window
import arabic_reshaper
from bidi.algorithm import get_display

# استيراد مدير البيانات الخاص بك (تأكد من أنه لا يحتوي على أكواد PyQt5)
# إذا كان quran_data_manager يعتمد على PyQt5، يجب فصله.
# هنا سنستخدم واجهة بسيطة للتجربة.

class YusrMobileApp(App):
    def build(self):
        self.title = "Yusr Lite"
        Window.clearcolor = (0.96, 0.96, 0.86, 1)  # لون بيج فاتح

        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        
        # دالة مساعدة لعرض النص العربي بشكل صحيح
        def ar_text(text):
            reshaped_text = arabic_reshaper.reshape(text)
            return get_display(reshaped_text)

        # عنوان التطبيق
        lbl_title = Label(
            text=ar_text("تطبيق يُسْر - نسخة الموبايل"),
            font_name="fonts/uthmanic.ttf" if os.path.exists("fonts/uthmanic.ttf") else "Roboto",
            font_size='30sp',
            color=(0.2, 0.4, 0.2, 1)
        )
        
        # رسالة ترحيب
        lbl_info = Label(
            text=ar_text("جاري العمل على تحويل الواجهة..."),
            font_size='18sp',
            color=(0, 0, 0, 1)
        )

        btn_exit = Button(
            text=ar_text("خروج"),
            size_hint=(1, 0.2),
            background_color=(0.8, 0.2, 0.2, 1)
        )
        btn_exit.bind(on_press=self.stop)

        layout.add_widget(lbl_title)
        layout.add_widget(lbl_info)
        layout.add_widget(btn_exit)
        
        return layout

if __name__ == '__main__':
    YusrMobileApp().run()