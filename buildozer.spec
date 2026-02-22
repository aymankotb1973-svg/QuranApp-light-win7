[app]
title = Yusr Lite
package.name = yusrlite
package.domain = org.yusr.lite
source.dir = .
source.include_exts = py,png,jpg,ttf,json,db
# هنا شيلنا الـ Vosk عشان دي نسخة لايت
requirements = python3,kivy==2.3.1,arabic-reshaper,python-bidi
orientation = portrait
fullscreen = 1
android.archs = arm64-v8a, armeabi-v7a