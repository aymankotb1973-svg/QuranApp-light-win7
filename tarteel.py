import os
import shutil
from huggingface_hub import snapshot_download

# 1. تحديد مكان الحفظ
model_path = os.path.join(os.path.dirname(__file__), "quran_model_final")

print(f"🚀 جاري تحميل الموديل بطريقة الالتفاف لضمان التشغيل...")

try:
    # 2. تحميل الموديل مع تعطيل الـ Symlinks تماماً
    # ده هيجبره يحمل الملفات الحقيقية مش روابط
    snapshot_download(
        repo_id="tarteel-ai/whisper-base-ar-quran",
        local_dir=model_path,
        local_dir_use_symlinks=False, # الحل هنا!
        repo_type="model"
    )
    
    print("\n" + "="*40)
    print("✅ تم التحميل بنجاح في الفولدر النهائي!")
    print(f"المكان: {model_path}")
    print("دلوقتي المطور يقدر يستخدم الفولدر ده في البرنامج مباشرة.")
    print("="*40)

except Exception as e:
    print(f"❌ حدث خطأ: {e}")
    print("لو لسه فيه مشكلة، افتح الـ CMD كـ Administrator وشغل الملف.")