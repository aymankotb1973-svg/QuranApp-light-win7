import sqlite3
import os
from utils import resource_path

class QuranInfoManager:
    def __init__(self):
        # مسار مجلد قواعد البيانات
        self.base_path = resource_path(os.path.join("data", "sqlite"))
        self.connections = {}
        self.db_configs = {} # لتخزين هيكل الجداول المكتشف (Cache)
        
        # خريطة أسماء الملفات
        self.db_files = {
            "meaning": "word-meaning-word.sqlite",
            "eerab": "word-eerab-word.sqlite",
            "sarf": "word-word-tasreef.sqlite",
            "moyassar": "aya-w-moyassar.sqlite",
            "saadi": "aya-tafsir-saadi.sqlite",
            "mokhtasar": "aya-tafsir-mokhtasar.sqlite",
            "tabary": "aya-tafsir-tabary.sqlite",
            "baghawy": "aya-tafsir-baghawy.sqlite",
            "katheer": "aya-tafsir-katheer.sqlite",
            "nozool": "aya-ayat-nozool.sqlite",
            "tajweed": "aya-tajweed-aya.sqlite"
        }

    def _get_connection(self, db_key):
        """إنشاء أو استرجاع اتصال بقاعدة البيانات المطلوبة"""
        if db_key in self.connections:
            return self.connections[db_key]
        
        filename = self.db_files.get(db_key)
        if not filename: return None
        
        db_path = os.path.join(self.base_path, filename)
        if not os.path.exists(db_path):
            print(f"Database not found: {db_path}")
            return None
            
        try:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self.connections[db_key] = conn
            return conn
        except Exception as e:
            print(f"Error connecting to {db_key}: {e}")
            return None

    def _get_db_config(self, db_key, conn):
        """اكتشاف اسم الجدول وأسماء الأعمدة تلقائياً"""
        if db_key in self.db_configs:
            return self.db_configs[db_key]
        
        try:
            cur = conn.cursor()
            # 1. البحث عن اسم الجدول
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            
            # قائمة الأسماء المحتملة للجدول بالأولوية
            table = None
            for t in ['project_contents', 'content', 'verses', 'tafsir', 'data', 'ayahs']:
                if t in tables:
                    table = t
                    break
            if not table and tables:
                table = tables[0] # استخدام أول جدول إذا لم نجد اسماً معروفاً
            
            if not table:
                return None

            # 2. البحث عن أسماء الأعمدة
            cur.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in cur.fetchall()]
            
            # تخمين أسماء أعمدة السورة والآية والكلمة
            sura_col = 'sura_id' if 'sura_id' in cols else 'sura' if 'sura' in cols else 'surah'
            aya_col = 'aya_id' if 'aya_id' in cols else 'aya' if 'aya' in cols else 'ayah'
            word_col = 'word_id' if 'word_id' in cols else 'word'
            
            # تخمين اسم عمود المحتوى (النص)
            content_col = None
            for c in ['content', 'title', 'text', 'tafsir', 'desc', 'meaning']:
                if c in cols:
                    content_col = c
                    break
            
            # Check for project_id column
            has_project_id = 'project_id' in cols
            
            # Check for title column
            title_col = 'title' if 'title' in cols else None
            
            config = (table, sura_col, aya_col, word_col, content_col, has_project_id, title_col)
            self.db_configs[db_key] = config
            print(f"DB Config for {db_key}: {config}") # للتشخيص
            return config
        except Exception as e:
            print(f"Error inspecting DB {db_key}: {e}")
            return None

    def get_word_data(self, db_key, sura, aya, word):
        """جلب معلومات خاصة بكلمة محددة (معنى، إعراب، صرف)"""
        conn = self._get_connection(db_key)
        if not conn:
            print(f"DEBUG DB [{db_key}]: No connection.")
            return None
        
        config = self._get_db_config(db_key, conn)
        if not config:
            print(f"DEBUG DB [{db_key}]: No config found.")
            return None
        
        table, sura_col, aya_col, word_col, content_col, has_project_id, title_col = config
        if not content_col:
            print(f"DEBUG DB [{db_key}]: No content column found.")
            return None

        try:
            cur = conn.cursor()
            
            # Build query parts
            where_clause = f"{sura_col}=? AND {aya_col}=?"
            params = [sura, aya]
            
            # إذا كان العمود الخاص بالكلمة موجوداً نستخدمه، وإلا نبحث بالآية فقط
            if word_col:
                where_clause += f" AND {word_col}=?"
                params.append(word)

            sel_cols = content_col
            if title_col:
                sel_cols += f", {title_col}"

            query = f"SELECT {sel_cols} FROM {table} WHERE {where_clause}"
            
            # --- DEBUG PRINT ---
            print(f"DEBUG DB [{db_key}]: Query: {query} | Params: {params}")
            
            cur.execute(query, tuple(params))
            row = cur.fetchone()
            
            if row:
                val = row[0]
                title = row[1] if title_col else None
                
                # --- DEBUG PRINT ---
                print(f"DEBUG DB [{db_key}]: Row found. Value type: {type(val)}")
                val = val.decode('utf-8', errors='replace') if isinstance(val, bytes) else val
                title = title.decode('utf-8', errors='replace') if isinstance(title, bytes) else title
                return val, title
            else:
                # --- DEBUG PRINT ---
                print(f"DEBUG DB [{db_key}]: No row returned.")
                
        except Exception as e:
            print(f"Query error in {db_key}: {e}")
        return None, None

    def get_aya_data(self, db_key, sura, aya):
        """جلب معلومات خاصة بآية كاملة (تفاسير)"""
        conn = self._get_connection(db_key)
        if not conn: return None
        
        config = self._get_db_config(db_key, conn)
        if not config: return None
        
        table, sura_col, aya_col, word_col, content_col, has_project_id, title_col = config
        if not content_col: return None

        try:
            cur = conn.cursor()
            where_clause = f"{sura_col}=? AND {aya_col}=?"
            
            sel_cols = content_col
            if title_col:
                sel_cols += f", {title_col}"
                
            query = f"SELECT {sel_cols} FROM {table} WHERE {where_clause}"
            
            # --- DEBUG PRINT ---
            print(f"DEBUG DB [{db_key}]: Query: {query} | Params: {sura}, {aya}")

            cur.execute(query, (sura, aya))
            row = cur.fetchone()
            if row:
                val = row[0]
                title = row[1] if title_col else None
                print(f"DEBUG DB [{db_key}]: Row found.")
                val = val.decode('utf-8', errors='replace') if isinstance(val, bytes) else val
                title = title.decode('utf-8', errors='replace') if isinstance(title, bytes) else title
                return val, title
            else:
                print(f"DEBUG DB [{db_key}]: No row returned.")
        except Exception as e:
            print(f"Query error in {db_key}: {e}")
        return None, None

    def close_all(self):
        for conn in self.connections.values():
            conn.close()
        self.connections.clear()
