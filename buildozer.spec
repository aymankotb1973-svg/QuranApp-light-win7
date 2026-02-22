[app]
title = Yusr Lite
package.name = yusrlite
package.domain = org.yusr.lite
source.dir = .
source.include_exts = py,png,jpg,ttf,json,db
requirements = python3,kivy==2.3.0,arabic-reshaper,python-bidi
orientation = portrait
fullscreen = 1

# --- أهم سطور عشان الأندرويد ميزعلش ---
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
# ---------------------------------------

[buildozer]
log_level = 2
warn_on_root = 1
