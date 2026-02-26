[app]
title = Yusr Lite
package.name = yusrlite
package.domain = org.yusr.lite
source.dir = .
source.include_exts = py,png,jpg,ttf,json,db,sqlite,ico,mp3
# هنا شيلنا الـ Vosk عشان دي نسخة لايت
# استخدام رابط مباشر لـ KivyMD 2.0 (Master) لأن الكود يستخدم مكونات جديدة مثل MDButton
requirements = python3,kivy==2.3.1,https://github.com/kivymd/KivyMD/archive/master.zip,arabic-reshaper,python-bidi,requests,numpy
orientation = portrait
fullscreen = 1
android.archs = arm64-v8a, armeabi-v7a
# قبول التراخيص تلقائياً لحل مشكلة exit code 100
android.accept_sdk_license = True

# (android.permissions) Permissions
android.permissions = INTERNET,RECORD_AUDIO,WAKE_LOCK,ACCESS_NETWORK_STATE
