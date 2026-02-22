# -*- coding: utf-8 -*-
"""
user_profile.py - Manages user profiles, progress tracking, and dashboard UI.
"""
import json
import os
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QInputDialog,
                             QPushButton, QListWidget, QLineEdit, QMessageBox,
                             QDateEdit, QFrame, QGridLayout, QWidget, QToolButton, QGroupBox,
                             QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor

USERS_FILE = "users.json"
USER_DATA_DIR = "user_data"

class UserManager:
    def __init__(self):
        self.current_user = None
        self.users = self._load_users()
        if not os.path.exists(USER_DATA_DIR):
            os.makedirs(USER_DATA_DIR)

    def _load_users(self):
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Migration: If data is a list (old format), convert to dict with empty pins
                    # Migration 2: If data is dict but values are strings (pin only), convert to dict structure
                    if isinstance(data, list):
                        return {user: {"pin": "", "security": ""} for user in data}
                    
                    new_data = {}
                    for user, val in data.items():
                        if isinstance(val, str):
                            new_data[user] = {"pin": val, "security": ""}
                        else:
                            new_data[user] = val
                    return new_data
            except: return {}
        return {}

    def _save_users(self):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.users, f, ensure_ascii=False, indent=4)

    def add_user(self, username, pin="", security=""):
        if username and username not in self.users:
            self.users[username] = {"pin": pin, "security": security}
            self._save_users()
            # Initialize empty data for new user
            self.save_user_data(username, {"history": [], "khatma_count": 0})
            return True
        return False

    def delete_user(self, username):
        if username in self.users:
            del self.users[username]
            self._save_users()
            # Try to remove user data file
            try:
                path = self.get_user_data_path(username)
                if os.path.exists(path):
                    os.remove(path)
            except: pass
            return True
        return False

    def get_user_data_path(self, username):
        return os.path.join(USER_DATA_DIR, f"{username}.json")

    def load_user_data(self, username):
        path = self.get_user_data_path(username)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {"history": [], "khatma_count": 0}

    def save_user_data(self, username, data):
        path = self.get_user_data_path(username)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def record_session_progress(self, session_ayahs, duration_seconds=0):
        """
        session_ayahs: list of dicts {sura, ayah, accuracy, page}
        """
        if not self.current_user: return
        
        data = self.load_user_data(self.current_user)
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Record Session Metadata (New Feature)
        if "sessions" not in data:
            data["sessions"] = []
            
        data["sessions"].append({
            "date": today,
            "duration": duration_seconds,
            "ayahs_count": len(session_ayahs)
        })

        for item in session_ayahs:
            entry = {
                "date": today,
                "sura": item['sura'],
                "ayah": item['ayah'],
                "page": item.get('page', 0),
                "accuracy": item['accuracy'],
                "status": "memorized" if item['accuracy'] >= 70 else "pending"
            }
            data["history"].append(entry)
            
        self.save_user_data(self.current_user, data)

    def get_stats(self, username, start_date_str=None, end_date_str=None):
        data = self.load_user_data(username)
        history = data.get("history", [])
        
        filtered_history = []
        if start_date_str and end_date_str:
            for h in history:
                if start_date_str <= h.get("date", "") <= end_date_str:
                    filtered_history.append(h)
        else:
            filtered_history = history

        unique_ayahs = set()
        total_accuracy = 0
        count = 0
        
        for h in filtered_history:
            # Consider memorized if status is memorized
            if h.get("status") == "memorized":
                unique_ayahs.add((h["sura"], h["ayah"]))
                total_accuracy += h.get("accuracy", 0)
                count += 1
        
        avg_accuracy = (total_accuracy / count) if count > 0 else 0
        
        # Simple estimation for pages (approx 15 lines per page, avg 8-10 words per line... 
        # actually mapping is better but for now just count unique ayahs)
        # A rough estimate: 6236 ayahs / 604 pages ~= 10 ayahs per page.
        pages_estimate = len(unique_ayahs) / 10.0 
        
        return {
            "ayahs_memorized": len(unique_ayahs),
            "pages_estimate": int(pages_estimate),
            "avg_accuracy": avg_accuracy,
            "khatma_count": data.get("khatma_count", 0),
            "surahs_count": len(set(s for s, a in unique_ayahs))
        }

    def get_surah_breakdown(self, username):
        """
        Returns stats per surah:
        {
            sura_no: {
                'memorized_ayahs': set(aya_no),
                'attempts': int,
                'total_accuracy': float
            }
        }
        """
        data = self.load_user_data(username)
        history = data.get("history", [])
        
        breakdown = {}
        
        for h in history:
            sura = h.get("sura")
            aya = h.get("ayah")
            acc = h.get("accuracy", 0)
            status = h.get("status")
            
            if not sura: continue
            
            if sura not in breakdown:
                breakdown[sura] = {
                    'memorized_ayahs': set(),
                    'attempts': 0,
                    'total_accuracy': 0
                }
            
            breakdown[sura]['attempts'] += 1
            breakdown[sura]['total_accuracy'] += acc
            
            if status == "memorized":
                breakdown[sura]['memorized_ayahs'].add(aya)
                
        return breakdown

    def get_detailed_period_stats(self, username, start_date_str, end_date_str):
        """Returns detailed stats including duration and per-page breakdown."""
        data = self.load_user_data(username)
        history = data.get("history", [])
        sessions = data.get("sessions", [])
        
        # Filter History
        filtered_history = [h for h in history if start_date_str <= h.get("date", "") <= end_date_str]
        
        # Filter Sessions for Duration
        filtered_sessions = [s for s in sessions if start_date_str <= s.get("date", "") <= end_date_str]
        
        # Calculate Duration
        total_seconds = sum(s.get("duration", 0) for s in filtered_sessions)
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        
        # Calculate Counts
        surah_counts = {} # sura_no -> count
        page_counts = {} # page_no -> count
        
        for h in filtered_history:
            s = h.get("sura")
            p = h.get("page")
            if s: surah_counts[s] = surah_counts.get(s, 0) + 1
            if p: page_counts[p] = page_counts.get(p, 0) + 1
            
        return {
            "duration_str": f"{hours} ساعة و {minutes} دقيقة",
            "surah_counts": surah_counts,
            "page_counts": page_counts,
            "total_ayahs": len(filtered_history)
        }

    def get_last_position(self, username):
        data = self.load_user_data(username)
        history = data.get("history", [])
        if history:
            last = history[-1]
            return last.get("sura"), last.get("ayah")
        return None, None

    def reset_progress(self, username):
        data = self.load_user_data(username)
        if len(data["history"]) > 0:
             data["khatma_count"] = data.get("khatma_count", 0) + 1
        
        data["history"] = []
        self.save_user_data(username, data)

    def get_plans(self, username):
        data = self.load_user_data(username)
        return data.get("plans", [])

    def save_plans(self, username, plans):
        data = self.load_user_data(username)
        data["plans"] = plans
        self.save_user_data(username, data)

    def check_pin(self, username, pin):
        user_data = self.users.get(username, {})
        stored_pin = user_data.get("pin", "") if isinstance(user_data, dict) else user_data
        # If no pin is stored (legacy user), allow access
        if not stored_pin:
            return True
        return stored_pin == pin

    def check_security(self, username, answer):
        user_data = self.users.get(username, {})
        if isinstance(user_data, dict):
            return user_data.get("security", "") == answer
        return False

    def update_pin(self, username, new_pin):
        if username in self.users:
            if isinstance(self.users[username], dict):
                self.users[username]["pin"] = new_pin
            else:
                self.users[username] = {"pin": new_pin, "security": ""}
            self._save_users()
            return True
        return False

    def get_consistency_stats(self, username):
        data = self.load_user_data(username)
        sessions = data.get("sessions", [])
        history = data.get("history", [])
        
        # Collect all unique dates from sessions and history
        dates_set = set()
        for s in sessions:
            if s.get("date"): dates_set.add(s["date"])
        for h in history:
            if h.get("date"): dates_set.add(h["date"])
            
        if not dates_set:
            return {
                "total_days": 0, "current_streak": 0, "longest_streak": 0,
                "consistency_pct": 0.0, "last_active": "غير متوفر"
            }
            
        sorted_dates = sorted(list(dates_set))
        date_objs = []
        for d in sorted_dates:
            try:
                date_objs.append(datetime.strptime(d, "%Y-%m-%d").date())
            except: pass
            
        if not date_objs: return {"total_days": 0, "current_streak": 0, "longest_streak": 0, "consistency_pct": 0.0, "last_active": "غير متوفر"}

        total_days = len(date_objs)
        last_active = sorted_dates[-1]
        
        # Streaks
        current_streak = 0
        longest_streak = 0
        temp_streak = 0
        
        for i in range(len(date_objs)):
            if i == 0:
                temp_streak = 1
            else:
                diff = (date_objs[i] - date_objs[i-1]).days
                if diff == 1:
                    temp_streak += 1
                elif diff > 1:
                    longest_streak = max(longest_streak, temp_streak)
                    temp_streak = 1
        longest_streak = max(longest_streak, temp_streak)
        
        # Current Streak
        today = datetime.now().date()
        last_date_obj = date_objs[-1]
        diff_from_today = (today - last_date_obj).days
        
        if diff_from_today <= 1: # Active today or yesterday
            current_streak = 1
            # Count backwards
            for i in range(len(date_objs)-2, -1, -1):
                if (date_objs[i+1] - date_objs[i]).days == 1:
                    current_streak += 1
                else:
                    break
        else:
            current_streak = 0
            
        # Consistency Percentage
        first_date = date_objs[0]
        days_span = (today - first_date).days + 1
        consistency_pct = (total_days / days_span * 100) if days_span > 0 else 0.0
        
        return {
            "total_days": total_days,
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "consistency_pct": consistency_pct,
            "last_active": last_active
        }

    def save_reflection(self, username, sura, aya, text):
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

    def get_reflection(self, username, sura, aya):
        data = self.load_user_data(username)
        reflections = data.get("reflections", {})
        return reflections.get(f"{sura}:{aya}", "")

class ProfileDialog(QDialog):
    def __init__(self, user_manager, parent=None):
        super().__init__(parent)
        self.user_manager = user_manager
        self.setWindowTitle("اختيار المستخدم")
        self.setFixedSize(450, 450)
        self.setLayoutDirection(Qt.RightToLeft)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("اختر المستخدم:"))
        self.user_list = QListWidget()
        self.user_list.addItems(list(self.user_manager.users.keys()))
        self.user_list.currentItemChanged.connect(self.on_user_selected)
        layout.addWidget(self.user_list)
        
        # Login Area
        login_group = QGroupBox("تسجيل الدخول")
        login_layout = QHBoxLayout(login_group)
        
        self.pin_input = QLineEdit()
        self.pin_input.setPlaceholderText("كود المرور (4 أرقام)")
        self.pin_input.setEchoMode(QLineEdit.Password)
        self.pin_input.setMaxLength(4)
        self.pin_input.setEnabled(False)
        self.pin_input.returnPressed.connect(self.login_user)
        
        self.btn_login = QPushButton("دخول")
        self.btn_login.clicked.connect(self.login_user)
        self.btn_login.setEnabled(False)
        self.btn_login.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")

        self.btn_forgot = QPushButton("تغيير الكود")
        self.btn_forgot.setToolTip("تغيير كلمة المرور باستخدام القديمة أو سنة الميلاد")
        self.btn_forgot.clicked.connect(self.change_pin_flow)
        self.btn_forgot.setEnabled(False)

        self.btn_delete = QPushButton("حذف")
        self.btn_delete.setToolTip("حذف المستخدم المحدد")
        self.btn_delete.setStyleSheet("background-color: #FFCDD2; color: #C62828; border: 1px solid #E57373;")
        self.btn_delete.clicked.connect(self.delete_user)
        self.btn_delete.setEnabled(False)
        
        login_layout.addWidget(self.pin_input)
        login_layout.addWidget(self.btn_login)
        login_layout.addWidget(self.btn_forgot)
        login_layout.addWidget(self.btn_delete)
        layout.addWidget(login_group)
        
        # Add User Area
        add_group = QGroupBox("إضافة مستخدم جديد")
        add_layout = QHBoxLayout(add_group)
        
        self.new_user_input = QLineEdit()
        self.new_user_input.setPlaceholderText("اسم المستخدم")
        
        self.new_user_pin = QLineEdit()
        self.new_user_pin.setPlaceholderText("كود (اختياري)")
        self.new_user_pin.setEchoMode(QLineEdit.Password)
        self.new_user_pin.setMaxLength(4)
        self.new_user_pin.setFixedWidth(100)

        self.new_user_security = QLineEdit()
        self.new_user_security.setPlaceholderText("سنة الميلاد (للاستعادة)")
        self.new_user_security.setMaxLength(4)
        self.new_user_security.setFixedWidth(120)
        
        self.btn_add = QPushButton("إضافة")
        self.btn_add.clicked.connect(self.add_user)
        
        add_layout.addWidget(self.new_user_input)
        add_layout.addWidget(self.new_user_pin)
        add_layout.addWidget(self.new_user_security)
        add_layout.addWidget(self.btn_add)
        layout.addWidget(add_group)

    def add_user(self):
        name = self.new_user_input.text().strip()
        pin = self.new_user_pin.text().strip()
        security = self.new_user_security.text().strip()
        if name:
            if self.user_manager.add_user(name, pin, security):
                self.user_list.addItem(name)
                self.new_user_input.clear()
                self.new_user_pin.clear()
                self.new_user_security.clear()
            else:
                QMessageBox.warning(self, "خطأ", "المستخدم موجود بالفعل")

    def login_user(self):
        current_item = self.user_list.currentItem()
        if current_item:
            username = current_item.text()
            pin = self.pin_input.text()
            if self.user_manager.check_pin(username, pin):
                self.user_manager.current_user = username
                self.accept()
            else:
                QMessageBox.warning(self, "خطأ", "كود المرور غير صحيح")
                self.pin_input.clear()
        else:
            QMessageBox.warning(self, "تنبيه", "الرجاء اختيار مستخدم")

    def change_pin_flow(self):
        current_item = self.user_list.currentItem()
        if not current_item: return
        username = current_item.text()
        
        # Ask for Old PIN or Security Answer
        auth_input, ok = QInputDialog.getText(self, "تحقق", f"أدخل الكود الحالي أو سنة الميلاد للمستخدم '{username}':", QLineEdit.Password)
        if ok and auth_input:
            is_pin_ok = self.user_manager.check_pin(username, auth_input)
            is_sec_ok = self.user_manager.check_security(username, auth_input)
            
            if is_pin_ok or is_sec_ok:
                new_pin, ok2 = QInputDialog.getText(self, "تغيير الكود", "أدخل الكود الجديد (4 أرقام):", QLineEdit.Password)
                if ok2:
                    self.user_manager.update_pin(username, new_pin)
                    QMessageBox.information(self, "نجاح", "تم تغيير كود المرور بنجاح.")
            else:
                QMessageBox.warning(self, "خطأ", "البيانات غير صحيحة.")

    def delete_user(self):
        current_item = self.user_list.currentItem()
        if current_item:
            username = current_item.text()
            reply = QMessageBox.question(self, 'تأكيد الحذف', 
                                         f"هل أنت متأكد من حذف المستخدم '{username}'؟\nسيتم حذف جميع بيانات الحفظ والخطط.",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.user_manager.delete_user(username):
                    self.user_list.takeItem(self.user_list.row(current_item))
                    self.on_user_selected(None, None)

    def on_user_selected(self, current, previous):
        has_selection = (current is not None)
        self.pin_input.setEnabled(has_selection)
        self.btn_login.setEnabled(has_selection)
        self.btn_forgot.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)
        if has_selection:
            self.pin_input.clear()
            self.pin_input.setFocus()

class CollapsibleSection(QWidget):
    def __init__(self, title="", parent=None, is_open=False):
        super().__init__(parent)
        self.toggle_button = QToolButton(text=title, checkable=True, checked=is_open)
        self.toggle_button.setStyleSheet("""
            QToolButton {
                border: none;
                background-color: #E3F2FD;
                text-align: left;
                padding: 10px;
                font-size: 14px;
                font-weight: bold;
                color: #1565C0;
                border-radius: 5px;
            }
            QToolButton:hover { background-color: #BBDEFB; }
            QToolButton:checked { background-color: #2196F3; color: white; }
        """)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setArrowType(Qt.DownArrow if is_open else Qt.LeftArrow)
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.clicked.connect(self.on_pressed)

        self.content_area = QWidget()
        self.content_area.setVisible(is_open)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(5, 5, 5, 5)
        self.content_layout.setSpacing(10)

        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle_button)
        lay.addWidget(self.content_area)

    def on_pressed(self, checked):
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.LeftArrow)
        self.content_area.setVisible(checked)

class DashboardDialog(QDialog):
    def __init__(self, user_manager, parent=None):
        super().__init__(parent)
        self.user_manager = user_manager
        self.data_manager = parent.data_manager if hasattr(parent, 'data_manager') else None
        self.setWindowTitle(f"لوحة الإنجاز - {self.user_manager.current_user}")
        self.resize(500, 700)
        self.setLayoutDirection(Qt.RightToLeft)
        
        main_layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        main_layout.addWidget(scroll)
        
        container = QWidget()
        self.layout = QVBoxLayout(container)
        self.layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)

        # 1. Summary Section (Open by default)
        self.sec_summary = CollapsibleSection("📊 ملخص الختمة الحالية", is_open=True)
        self._setup_summary_ui()
        self.layout.addWidget(self.sec_summary)

        # 2. Period Report Section
        self.sec_period = CollapsibleSection("📅 تقرير الفترة الزمنية")
        self._setup_period_ui()
        self.layout.addWidget(self.sec_period)

        # 3. Surah Details Section (New)
        self.sec_surah_details = CollapsibleSection("📖 تفاصيل السور ونسب الحفظ", is_open=False)
        self._setup_surah_details_ui()
        self.layout.addWidget(self.sec_surah_details)

        # 3. Performance Section
        self.sec_perf = CollapsibleSection("⭐ تقرير الالتزام والاستمرارية")
        self._setup_perf_ui()
        self.layout.addWidget(self.sec_perf)

        # 4. Management Section
        self.sec_mgmt = CollapsibleSection("👤 إدارة المستخدم والختمات")
        self._setup_mgmt_ui()
        self.layout.addWidget(self.sec_mgmt)

        self.update_all_data()

    def _setup_summary_ui(self):
        l = self.sec_summary.content_layout
        self.lbl_total_progress = QLabel()
        self.lbl_remaining = QLabel()
        self.lbl_last_pos = QLabel()
        
        for lbl in [self.lbl_total_progress, self.lbl_remaining, self.lbl_last_pos]:
            lbl.setStyleSheet("font-size: 14px; padding: 5px; border-bottom: 1px solid #eee;")
            l.addWidget(lbl)

    def _setup_period_ui(self):
        l = self.sec_period.content_layout
        
        date_layout = QHBoxLayout()
        self.date_from = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_from.setCalendarPopup(True)
        self.date_to = QDateEdit(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        
        btn_update = QPushButton("عرض النتيجة")
        btn_update.clicked.connect(self.update_period_stats)
        
        date_layout.addWidget(QLabel("من:"))
        date_layout.addWidget(self.date_from)
        date_layout.addWidget(QLabel("إلى:"))
        date_layout.addWidget(self.date_to)
        date_layout.addWidget(btn_update)
        l.addLayout(date_layout)
        
        self.lbl_period_result = QLabel("اضغط 'عرض النتيجة' لرؤية الإنجاز.")
        self.lbl_period_result.setStyleSheet("font-weight: bold; color: #2E7D32; margin-top: 10px;")
        self.lbl_period_result.setWordWrap(True)
        l.addWidget(self.lbl_period_result)

    def _setup_surah_details_ui(self):
        l = self.sec_surah_details.content_layout
        
        # Overall Progress
        self.lbl_overall_progress = QLabel("نسبة الحفظ الكلية من المصحف:")
        self.progress_overall = QProgressBar()
        self.progress_overall.setStyleSheet("QProgressBar { border: 1px solid grey; border-radius: 5px; text-align: center; height: 25px; } QProgressBar::chunk { background-color: #4CAF50; }")
        self.progress_overall.setRange(0, 100)
        self.progress_overall.setValue(0)
        
        l.addWidget(self.lbl_overall_progress)
        l.addWidget(self.progress_overall)
        
        # Table
        self.surah_table = QTableWidget()
        self.surah_table.setColumnCount(4)
        self.surah_table.setHorizontalHeaderLabels(["السورة", "نسبة الحفظ", "نشاط التسميع", "الدقة"])
        self.surah_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents) # Name
        self.surah_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Progress
        self.surah_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents) # Count
        self.surah_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents) # Accuracy
        self.surah_table.setMinimumHeight(300)
        l.addWidget(self.surah_table)

    def _setup_perf_ui(self):
        l = self.sec_perf.content_layout
        self.lbl_streak = QLabel()
        self.lbl_consistency = QLabel()
        self.lbl_last_active = QLabel()
        
        for lbl in [self.lbl_streak, self.lbl_consistency, self.lbl_last_active]:
            lbl.setStyleSheet("font-size: 13px; padding: 5px; border-bottom: 1px solid #f0f0f0;")
            l.addWidget(lbl)

    def _setup_mgmt_ui(self):
        l = self.sec_mgmt.content_layout
        
        user_layout = QHBoxLayout()
        self.lbl_current_user = QLabel()
        btn_switch = QPushButton("تبديل المستخدم")
        btn_switch.clicked.connect(self.switch_user)
        user_layout.addWidget(self.lbl_current_user)
        user_layout.addWidget(btn_switch)
        l.addLayout(user_layout)
        
        self.lbl_khatma_count = QLabel()
        l.addWidget(self.lbl_khatma_count)
        
        btn_reset = QPushButton("بدء ختمة جديدة (تصفير)")
        btn_reset.setStyleSheet("background-color: #ffcccc; color: red; border: 1px solid red;")
        btn_reset.clicked.connect(self.reset_progress)
        l.addWidget(btn_reset)

    def update_all_data(self):
        username = self.user_manager.current_user
        
        # 1. Summary
        stats = self.user_manager.get_stats(username) # All time
        total_ayahs = 6236
        memorized = stats['ayahs_memorized']
        remaining = total_ayahs - memorized
        
        self.lbl_total_progress.setText(f"✅ الإنجاز الكلي: {memorized} آية من أصل {total_ayahs}.")
        self.lbl_remaining.setText(f"⏳ باقي لك على الختمة: {remaining} آية.")
        
        last_sura, last_aya = self.user_manager.get_last_position(username)
        if last_sura and last_aya:
            sura_name = f"سورة {last_sura}"
            if self.data_manager:
                sura_name = self.data_manager.get_sura_name(last_sura)
            self.lbl_last_pos.setText(f"📍 آخر آية وقفت عندها: {sura_name} - آية {last_aya}.")
        else:
            self.lbl_last_pos.setText("📍 لم تبدأ بعد.")

        # 2. Surah Details & Overall
        breakdown = self.user_manager.get_surah_breakdown(username)
        
        # Calculate Overall Percentage
        overall_pct = (memorized / total_ayahs) * 100
        self.progress_overall.setValue(int(overall_pct))
        self.progress_overall.setFormat(f"{overall_pct:.2f}% ({memorized} من {total_ayahs})")

        # Populate Table
        self.surah_table.setRowCount(len(breakdown))
        sorted_suras = sorted(breakdown.keys())
        
        for row, sura_no in enumerate(sorted_suras):
            data = breakdown[sura_no]
            
            # Name
            sura_name = f"سورة {sura_no}"
            if self.data_manager:
                sura_name = self.data_manager.get_sura_name(sura_no)
            item_name = QTableWidgetItem(sura_name)
            item_name.setTextAlignment(Qt.AlignCenter)
            self.surah_table.setItem(row, 0, item_name)
            
            # Progress Bar
            total_ayahs_in_sura = 0
            if self.data_manager and sura_no in self.data_manager.sura_aya_counts:
                total_ayahs_in_sura = self.data_manager.sura_aya_counts[sura_no]
            
            memorized_count = len(data['memorized_ayahs'])
            sura_pct = (memorized_count / total_ayahs_in_sura * 100) if total_ayahs_in_sura > 0 else 0
            
            p_bar = QProgressBar()
            p_bar.setRange(0, 100)
            p_bar.setValue(int(sura_pct))
            color = "#4CAF50" if sura_pct == 100 else "#8BC34A" if sura_pct > 50 else "#FF9800"
            p_bar.setStyleSheet(f"QProgressBar {{ border: 0px; background-color: #eee; border-radius: 3px; text-align: center; }} QProgressBar::chunk {{ background-color: {color}; }}")
            p_bar.setFormat(f"{sura_pct:.1f}% ({memorized_count}/{total_ayahs_in_sura})")
            self.surah_table.setCellWidget(row, 1, p_bar)
            
            # Attempts
            item_attempts = QTableWidgetItem(str(data['attempts']))
            item_attempts.setTextAlignment(Qt.AlignCenter)
            self.surah_table.setItem(row, 2, item_attempts)
            
            # Accuracy
            avg_acc = (data['total_accuracy'] / data['attempts']) if data['attempts'] > 0 else 0
            item_acc = QTableWidgetItem(f"{avg_acc:.1f}%")
            item_acc.setTextAlignment(Qt.AlignCenter)
            if avg_acc >= 90: item_acc.setForeground(QColor("green"))
            elif avg_acc < 70: item_acc.setForeground(QColor("red"))
            self.surah_table.setItem(row, 3, item_acc)

        # 3. Consistency / Performance (Updated to Commitment Report)
        cons_stats = self.user_manager.get_consistency_stats(username)
        
        streak = cons_stats['current_streak']
        longest = cons_stats['longest_streak']
        total_days = cons_stats['total_days']
        pct = cons_stats['consistency_pct']
        
        self.lbl_streak.setText(f"🔥 التتابع الحالي: <b>{streak} يوم</b> (الأطول: {longest} يوم)")
        self.lbl_consistency.setText(f"📅 إجمالي أيام النشاط: <b>{total_days} يوم</b> (نسبة الالتزام: {pct:.1f}%)")
        self.lbl_last_active.setText(f"🕒 آخر نشاط: {cons_stats['last_active']}")

        # 4. Management
        self.lbl_current_user.setText(f"المستخدم الحالي: <b>{username}</b>")
        self.lbl_khatma_count.setText(f"عدد الختمات السابقة: {stats['khatma_count']}")

    def update_period_stats(self):
        d_from = self.date_from.date().toString("yyyy-MM-dd")
        d_to = self.date_to.date().toString("yyyy-MM-dd")
        
        stats = self.user_manager.get_detailed_period_stats(self.user_manager.current_user, d_from, d_to)
        
        # Format Report
        report = f"<b>الفترة: {d_from} إلى {d_to}</b><br>"
        report += f"⏱️ إجمالي وقت الاستماع: {stats['duration_str']}<br>"
        report += f"📖 إجمالي الآيات: {stats['total_ayahs']}<br><br>"
        
        report += "<b>📊 تفاصيل السور:</b><br>"
        if stats['surah_counts']:
            for sura, count in sorted(stats['surah_counts'].items()):
                sura_name = f"سورة {sura}"
                if self.data_manager:
                    sura_name = self.data_manager.get_sura_name(sura)
                report += f"- {sura_name}: {count} آية<br>"
        else:
            report += "لا يوجد بيانات.<br>"
            
        report += "<br><b>📄 تفاصيل الصفحات (الوجه):</b><br>"
        if stats['page_counts']:
            for page, count in sorted(stats['page_counts'].items()):
                report += f"- صفحة {page}: {count} آية<br>"
        else:
            report += "لا يوجد بيانات.<br>"
            
        self.lbl_period_result.setText(report)

    def switch_user(self):
        self.close()
        # Parent (QuranCanvasApp) has show_profile_dialog method
        if hasattr(self.parent(), 'show_profile_dialog'):
            self.parent().show_profile_dialog()

    def reset_progress(self):
        reply = QMessageBox.question(self, 'تأكيد', "هل تريد مسح السجلات والبدء بختمة جديدة؟",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.user_manager.reset_progress(self.user_manager.current_user)
            self.update_all_data()
            QMessageBox.information(self, "تم", "تم تصفير النتائج بنجاح.")
