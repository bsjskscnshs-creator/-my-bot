import telebot
from telebot import types
import re
import random
import time
import sqlite3
import json
from datetime import datetime, timedelta
import threading
import traceback
import string
import html

# =====================================================================
# 1. إعدادات البوت
# =====================================================================
API_TOKEN = "8660276552:AAErPEqGzudkuKNIcollzgORbzEPCPdQAhc"
ADMIN_ID = 8633059017
DEVELOPER_USERNAME = "@XENYXr"
BOT_NAME = "بيت الخدمات"
BOT_USERNAME = "rabeh52Bot"

bot = telebot.TeleBot(API_TOKEN)

# =====================================================================
# 2. قاعدة البيانات
# =====================================================================
class DB:
    def __init__(self):
        self.conn = sqlite3.connect("bot.db", check_same_thread=False)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.init_tables()
    
    def init_tables(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                (id TEXT PRIMARY KEY, name TEXT, join_date TEXT, referred_by TEXT)''')
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'name' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN name TEXT")
                print("✅ تم إضافة عمود name إلى جدول users")
            
            cursor.execute('''CREATE TABLE IF NOT EXISTS user_stats 
                (user_id TEXT PRIMARY KEY, 
                 points INTEGER DEFAULT 0, 
                 invites INTEGER DEFAULT 0, 
                 last_daily TEXT, 
                 total_servers INTEGER DEFAULT 0)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS server_stats 
                (server_name TEXT PRIMARY KEY, uses INTEGER DEFAULT 0, last_use TEXT, 
                 avg_ping INTEGER DEFAULT 0, total_ping INTEGER DEFAULT 0, ping_count INTEGER DEFAULT 0)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS cooldown 
                (user_id TEXT, server TEXT, time REAL, PRIMARY KEY (user_id, server))''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS announcements 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, message TEXT, date TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS force_channels 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 channel TEXT UNIQUE, 
                 type TEXT, 
                 added_date TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS store_items 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 seller_id TEXT, 
                 seller_username TEXT,
                 image_message_id TEXT,
                 description TEXT,
                 date_added TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS bot_settings 
                (key TEXT PRIMARY KEY, value TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS user_state 
                (user_id TEXT PRIMARY KEY, 
                 state TEXT, 
                 image_message_id TEXT, 
                 description TEXT,
                 temp_data TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS request_counter 
                (id INTEGER PRIMARY KEY, counter INTEGER)''')
            cursor.execute("INSERT OR IGNORE INTO request_counter (id, counter) VALUES (1, 0)")
            cursor.execute('''CREATE TABLE IF NOT EXISTS redeem_codes 
                (code TEXT PRIMARY KEY, 
                 points INTEGER, 
                 max_uses INTEGER, 
                 used INTEGER DEFAULT 0, 
                 created_by TEXT, 
                 created_date TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS redeem_usage 
                (code TEXT, user_id TEXT, used_date TEXT, PRIMARY KEY (code, user_id))''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS sell_requests 
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id TEXT,
                 username TEXT,
                 phone TEXT,
                 points INTEGER,
                 status TEXT DEFAULT 'pending',
                 request_date TEXT,
                 completed_date TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS campaigns 
                (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 owner_id TEXT,
                 channel_link TEXT,
                 channel_username TEXT,
                 target_members INTEGER,
                 current_members INTEGER DEFAULT 0,
                 price_per_member INTEGER DEFAULT 5,
                 points_per_join INTEGER DEFAULT 2,
                 status TEXT DEFAULT 'active',
                 code TEXT UNIQUE,
                 created_at TEXT,
                 updated_at TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS campaign_joins 
                (campaign_id INTEGER,
                 user_id TEXT,
                 joined_at TEXT,
                 PRIMARY KEY (campaign_id, user_id))''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS daily_rewards 
                (user_id TEXT PRIMARY KEY, last_claim TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS user_verification 
                (user_id TEXT PRIMARY KEY, 
                 verified INTEGER DEFAULT 0, 
                 attempts INTEGER DEFAULT 0, 
                 last_attempt_time REAL, 
                 verified_until REAL)''')
            self.conn.commit()
            print("✅ تم إنشاء الجداول بنجاح")
            
            cursor.execute("PRAGMA table_info(user_state)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'temp_data' not in columns:
                cursor.execute("ALTER TABLE user_state ADD COLUMN temp_data TEXT")
                self.conn.commit()
                print("✅ تم إضافة عمود temp_data")
                
            # حذف عمود campaign_id من force_channels إذا كان موجوداً (للتوافق)
            try:
                cursor.execute("ALTER TABLE force_channels DROP COLUMN campaign_id")
                self.conn.commit()
                print("✅ تم حذف عمود campaign_id من force_channels")
            except:
                pass
        except Exception as e:
            print(f"❌ خطأ في إنشاء الجداول: {e}")
        finally:
            cursor.close()
    
    # ===== دوال المستخدمين والنقاط =====
    def add_user(self, user_id, name=None, referred_by=None):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO users (id, name, join_date, referred_by) VALUES (?, ?, ?, ?)",
                (str(user_id), name, datetime.now().strftime('%Y-%m-%d'), referred_by)
            )
            cursor.execute(
                "INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)",
                (str(user_id),)
            )
            self.conn.commit()
            if referred_by:
                self.add_points(user_id, 1)
                self.add_points(referred_by, 2)
                self.add_invite(referred_by)
                try:
                    bot.send_message(
                        referred_by,
                        f"🎉 تم دعوة مستخدم جديد بواسطتك!\n\n"
                        f"👤 {name or 'مستخدم'}\n"
                        f"⭐ تم إضافة 2 نقطة لك!"
                    )
                except:
                    pass
            return True
        except Exception as e:
            print(f"❌ خطأ في add_user: {e}")
            self.conn.rollback()
            return False
        finally:
            cursor.close()
    
    def get_user_count(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]
        except:
            return 0
        finally:
            cursor.close()
    
    def get_active_users(self, days=7):
        cursor = self.conn.cursor()
        try:
            date_limit = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            cursor.execute("SELECT COUNT(*) FROM users WHERE join_date >= ?", (date_limit,))
            return cursor.fetchone()[0]
        except:
            return 0
        finally:
            cursor.close()
    
    def add_points(self, user_id, points):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT user_id FROM user_stats WHERE user_id = ?", (str(user_id),))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO user_stats (user_id) VALUES (?)", (str(user_id),))
            cursor.execute(
                "UPDATE user_stats SET points = points + ? WHERE user_id = ?",
                (points, str(user_id))
            )
            self.conn.commit()
            cursor.execute("SELECT points FROM user_stats WHERE user_id = ?", (str(user_id),))
            new_points = cursor.fetchone()[0]
            return new_points
        except Exception as e:
            print(f"❌ خطأ في add_points: {e}")
            self.conn.rollback()
            return 0
        finally:
            cursor.close()
    
    def get_points(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT user_id FROM user_stats WHERE user_id = ?", (str(user_id),))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO user_stats (user_id) VALUES (?)", (str(user_id),))
                self.conn.commit()
                return 0
            cursor.execute("SELECT points FROM user_stats WHERE user_id = ?", (str(user_id),))
            row = cursor.fetchone()
            return row[0] if row else 0
        except:
            return 0
        finally:
            cursor.close()
    
    def get_invites(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT invites FROM user_stats WHERE user_id = ?", (str(user_id),))
            row = cursor.fetchone()
            return row[0] if row else 0
        except:
            return 0
        finally:
            cursor.close()
    
    def add_invite(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "UPDATE user_stats SET invites = invites + 1 WHERE user_id = ?",
                (str(user_id),)
            )
            self.conn.commit()
        except:
            pass
        finally:
            cursor.close()
    
    # ===== دوال الهدية اليومية (تُستخدم الآن لعجلة الحظ) =====
    def can_claim_daily(self, user_id):
        """التحقق مما إذا كان يمكن المطالبة بعجلة الحظ (مرة كل 24 ساعة)"""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT last_claim FROM daily_rewards WHERE user_id = ?",
                (str(user_id),)
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return True, 0
            last_claim = float(row[0])
            now = time.time()
            diff = now - last_claim
            if diff >= 86400:
                return True, 0
            else:
                seconds_left = int(86400 - diff)
                return False, seconds_left
        except Exception as e:
            print(f"⚠️ خطأ في can_claim_daily: {e}")
            return True, 0
        finally:
            cursor.close()
    
    def claim_daily(self, user_id):
        """تسجيل وقت المطالبة (يُستخدم لعجلة الحظ)"""
        cursor = self.conn.cursor()
        try:
            now = str(time.time())
            cursor.execute(
                "INSERT OR REPLACE INTO daily_rewards (user_id, last_claim) VALUES (?, ?)",
                (str(user_id), now)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ خطأ في claim_daily: {e}")
            self.conn.rollback()
            return False
        finally:
            cursor.close()
    
    # ===== دوال التحقق (Captcha) =====
    def is_user_verified(self, user_id):
        if str(user_id) == str(ADMIN_ID):
            return True
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT verified, verified_until FROM user_verification WHERE user_id = ?",
                (str(user_id),)
            )
            row = cursor.fetchone()
            if row:
                verified, verified_until = row
                if verified and verified_until and time.time() < verified_until:
                    return True
                else:
                    return False
            return False
        except:
            return False
        finally:
            cursor.close()
    
    def verify_user(self, user_id, duration_hours=24):
        cursor = self.conn.cursor()
        try:
            verified_until = time.time() + duration_hours * 3600
            cursor.execute(
                "INSERT OR REPLACE INTO user_verification (user_id, verified, attempts, last_attempt_time, verified_until) VALUES (?, ?, ?, ?, ?)",
                (str(user_id), 1, 0, time.time(), verified_until)
            )
            self.conn.commit()
            return True
        except:
            return False
        finally:
            cursor.close()
    
    def reset_verification(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM user_verification WHERE user_id = ?",
                (str(user_id),)
            )
            self.conn.commit()
            return True
        except:
            return False
        finally:
            cursor.close()
    
    def increment_attempts(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO user_verification (user_id, verified, attempts, last_attempt_time) VALUES (?, ?, ?, ?)",
                (str(user_id), 0, 0, time.time())
            )
            cursor.execute(
                "UPDATE user_verification SET attempts = attempts + 1, last_attempt_time = ? WHERE user_id = ?",
                (time.time(), str(user_id))
            )
            self.conn.commit()
            cursor.execute(
                "SELECT attempts FROM user_verification WHERE user_id = ?",
                (str(user_id),)
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        except:
            return 0
        finally:
            cursor.close()
    
    def get_attempts(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT attempts, last_attempt_time FROM user_verification WHERE user_id = ?",
                (str(user_id),)
            )
            row = cursor.fetchone()
            if row:
                return row[0], row[1]
            return 0, 0
        except:
            return 0, 0
        finally:
            cursor.close()
    
    def is_user_blocked(self, user_id):
        if str(user_id) == str(ADMIN_ID):
            return False
        attempts, last_time = self.get_attempts(user_id)
        if attempts >= 3:
            if time.time() - last_time < 600:
                return True
            else:
                self.reset_verification(user_id)
                return False
        return False
    
    # ===== أكواد النقاط =====
    def create_redeem_code(self, points, max_uses, created_by):
        cursor = self.conn.cursor()
        try:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            while True:
                cursor.execute("SELECT code FROM redeem_codes WHERE code = ?", (code,))
                if not cursor.fetchone():
                    break
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            cursor.execute(
                "INSERT INTO redeem_codes (code, points, max_uses, created_by, created_date) VALUES (?, ?, ?, ?, ?)",
                (code, points, max_uses, str(created_by), datetime.now().strftime('%Y-%m-%d %H:%M'))
            )
            self.conn.commit()
            return code
        except:
            return None
        finally:
            cursor.close()
    
    def use_redeem_code(self, code, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT points, max_uses, used FROM redeem_codes WHERE code = ?", (code,))
            row = cursor.fetchone()
            if not row:
                return None, "الكود غير صحيح", 0
            points, max_uses, used = row
            if used >= max_uses:
                return None, "هذا الكود انتهت صلاحيته (تم استخدامه من قبل كل المستخدمين المسموح لهم)", 0
            cursor.execute("SELECT 1 FROM redeem_usage WHERE code = ? AND user_id = ?", (code, str(user_id)))
            if cursor.fetchone():
                return None, "لقد استخدمت هذا الكود مسبقاً، لا يمكن استخدامه مرة أخرى", 0
            new_balance = self.add_points(user_id, points)
            cursor.execute(
                "INSERT INTO redeem_usage (code, user_id, used_date) VALUES (?, ?, ?)",
                (code, str(user_id), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            cursor.execute(
                "UPDATE redeem_codes SET used = used + 1 WHERE code = ?",
                (code,)
            )
            self.conn.commit()
            return points, "تم إضافة النقاط بنجاح", new_balance
        except Exception as e:
            print(f"❌ خطأ في use_redeem_code: {e}")
            self.conn.rollback()
            return None, "حدث خطأ", 0
        finally:
            cursor.close()
    
    def get_redeem_codes(self, created_by=None):
        cursor = self.conn.cursor()
        try:
            if created_by:
                cursor.execute("SELECT code, points, max_uses, used, created_date FROM redeem_codes WHERE created_by = ? ORDER BY created_date DESC", (str(created_by),))
            else:
                cursor.execute("SELECT code, points, max_uses, used, created_date FROM redeem_codes ORDER BY created_date DESC")
            return cursor.fetchall()
        except:
            return []
        finally:
            cursor.close()
    
    # ===== حالات المستخدم =====
    def set_user_state(self, user_id, state, image_message_id=None, description=None, temp_data=None):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO user_state (user_id, state, image_message_id, description, temp_data) VALUES (?, ?, ?, ?, ?)",
                (str(user_id), state, image_message_id, description, temp_data)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ خطأ في set_user_state: {e}")
            return False
        finally:
            cursor.close()
    
    def get_user_state(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT state, image_message_id, description, temp_data FROM user_state WHERE user_id = ?", (str(user_id),))
            row = cursor.fetchone()
            return row
        except Exception as e:
            print(f"❌ خطأ في get_user_state: {e}")
            return None
        finally:
            cursor.close()
    
    def clear_user_state(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM user_state WHERE user_id = ?", (str(user_id),))
            self.conn.commit()
            return True
        except:
            return False
        finally:
            cursor.close()
    
    # ===== إعدادات البوت =====
    def set_setting(self, key, value):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)",
                (key, value)
            )
            self.conn.commit()
            return True
        except:
            return False
        finally:
            cursor.close()
    
    def get_setting(self, key):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None
        except:
            return None
        finally:
            cursor.close()
    
    def delete_setting(self, key):
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM bot_settings WHERE key = ?", (key,))
            self.conn.commit()
            return cursor.rowcount > 0
        except:
            return False
        finally:
            cursor.close()
    
    # ===== القنوات الإجبارية (للإدمن فقط) =====
    def add_force_channel(self, channel, channel_type='channel'):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO force_channels (channel, type, added_date) VALUES (?, ?, ?)",
                (channel, channel_type, datetime.now().strftime('%Y-%m-%d'))
            )
            self.conn.commit()
            return True
        except:
            return False
        finally:
            cursor.close()
    
    def remove_force_channel(self, channel):
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM force_channels WHERE channel = ?", (channel,))
            self.conn.commit()
            return cursor.rowcount > 0
        except:
            return False
        finally:
            cursor.close()
    
    def get_force_channels(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT channel, type FROM force_channels")
            return cursor.fetchall()
        except:
            return []
        finally:
            cursor.close()
    
    def get_force_channels_count(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM force_channels")
            return cursor.fetchone()[0]
        except:
            return 0
        finally:
            cursor.close()
    
    def is_channel_forced(self, channel):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM force_channels WHERE channel = ?", (channel,))
            return cursor.fetchone() is not None
        except:
            return False
        finally:
            cursor.close()
    
    # ===== الملف الدارك =====
    def set_dark_file(self, file_id, description, expiry_timestamp):
        self.set_setting('dark_file_id', file_id)
        self.set_setting('dark_description', description)
        self.set_setting('dark_expiry', str(expiry_timestamp))
        return True

    def get_dark_file(self):
        file_id = self.get_setting('dark_file_id')
        description = self.get_setting('dark_description')
        expiry = self.get_setting('dark_expiry')
        if file_id and description and expiry:
            return file_id, description, int(expiry)
        return None, None, None

    def delete_dark_file(self):
        self.delete_setting('dark_file_id')
        self.delete_setting('dark_description')
        self.delete_setting('dark_expiry')
        return True

    def is_dark_file_expired(self):
        _, _, expiry = self.get_dark_file()
        if expiry:
            return int(time.time()) > expiry
        return True

    # ===== الملف الانجكتور (جديد) =====
    def set_injector_file(self, file_id, description, expiry_timestamp):
        self.set_setting('injector_file_id', file_id)
        self.set_setting('injector_description', description)
        self.set_setting('injector_expiry', str(expiry_timestamp))
        return True

    def get_injector_file(self):
        file_id = self.get_setting('injector_file_id')
        description = self.get_setting('injector_description')
        expiry = self.get_setting('injector_expiry')
        if file_id and description and expiry:
            return file_id, description, int(expiry)
        return None, None, None

    def delete_injector_file(self):
        self.delete_setting('injector_file_id')
        self.delete_setting('injector_description')
        self.delete_setting('injector_expiry')
        return True

    def is_injector_file_expired(self):
        _, _, expiry = self.get_injector_file()
        if expiry:
            return int(time.time()) > expiry
        return True

    # ===== طلبات بيع النقاط =====
    def add_sell_request(self, user_id, username, phone, points):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO sell_requests (user_id, username, phone, points, request_date, status) VALUES (?, ?, ?, ?, ?, ?)",
                (str(user_id), username, phone, points, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'pending')
            )
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            print(f"❌ خطأ في add_sell_request: {e}")
            return None
        finally:
            cursor.close()
    
    def get_sell_requests(self, status='pending'):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT id, user_id, username, phone, points, request_date, status FROM sell_requests WHERE status = ? ORDER BY id DESC",
                (status,)
            )
            return cursor.fetchall()
        except:
            return []
        finally:
            cursor.close()
    
    def update_sell_request_status(self, request_id, status):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "UPDATE sell_requests SET status = ?, completed_date = ? WHERE id = ?",
                (status, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), request_id)
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except:
            return False
        finally:
            cursor.close()
    
    def get_sell_request(self, request_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT id, user_id, username, phone, points, request_date, status FROM sell_requests WHERE id = ?",
                (request_id,)
            )
            return cursor.fetchone()
        except:
            return None
        finally:
            cursor.close()

    # ===== دوال ميزة تمويل القناة (مستقلة تماماً) =====
    def create_campaign(self, owner_id, channel_link, target_members, price_per_member=5, points_per_join=2):
        cursor = self.conn.cursor()
        try:
            # استخلاص اسم المستخدم من الرابط
            channel_username = None
            match = re.search(r'(?:https?://)?t\.me/([a-zA-Z0-9_]+)', channel_link)
            if match:
                channel_username = match.group(1)
            else:
                if channel_link.startswith('@'):
                    channel_username = channel_link[1:]
                else:
                    channel_username = channel_link.strip()
            
            # إنشاء كود الحملة
            code = 'fund_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            while True:
                cursor.execute("SELECT code FROM campaigns WHERE code = ?", (code,))
                if not cursor.fetchone():
                    break
                code = 'fund_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                """INSERT INTO campaigns 
                   (owner_id, channel_link, channel_username, target_members, price_per_member, points_per_join, code, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(owner_id), channel_link, channel_username, target_members, price_per_member, points_per_join, code, now, now)
            )
            self.conn.commit()
            campaign_id = cursor.lastrowid
            
            return campaign_id, code, channel_username
        except Exception as e:
            print(f"❌ خطأ في create_campaign: {e}")
            self.conn.rollback()
            return None, str(e), None
        finally:
            cursor.close()

    def get_campaign_by_code(self, code):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT id, owner_id, channel_link, channel_username, target_members, current_members, price_per_member, points_per_join, status, code, created_at FROM campaigns WHERE code = ?",
                (code,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'owner_id': row[1],
                    'channel_link': row[2],
                    'channel_username': row[3],
                    'target_members': row[4],
                    'current_members': row[5],
                    'price_per_member': row[6],
                    'points_per_join': row[7],
                    'status': row[8],
                    'code': row[9],
                    'created_at': row[10]
                }
            return None
        except:
            return None
        finally:
            cursor.close()

    def get_campaign(self, campaign_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT id, owner_id, channel_link, channel_username, target_members, current_members, price_per_member, points_per_join, status, code, created_at FROM campaigns WHERE id = ?",
                (campaign_id,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'owner_id': row[1],
                    'channel_link': row[2],
                    'channel_username': row[3],
                    'target_members': row[4],
                    'current_members': row[5],
                    'price_per_member': row[6],
                    'points_per_join': row[7],
                    'status': row[8],
                    'code': row[9],
                    'created_at': row[10]
                }
            return None
        except:
            return None
        finally:
            cursor.close()

    def increment_campaign_members(self, campaign_id):
        cursor = self.conn.cursor()
        try:
            # تحديث العدد
            cursor.execute(
                "UPDATE campaigns SET current_members = current_members + 1, updated_at = ? WHERE id = ?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), campaign_id)
            )
            # جلب معلومات الحملة للتحقق من الاكتمال
            cursor.execute(
                "SELECT target_members, current_members, owner_id, channel_link FROM campaigns WHERE id = ?",
                (campaign_id,)
            )
            row = cursor.fetchone()
            if row:
                target, current, owner_id, channel_link = row
                if current >= target:
                    # إرسال رسالة للمالك
                    try:
                        bot.send_message(
                            owner_id,
                            f"✅ **تم اكتمال تمويل قناتك بنجاح!** 🎉\n\n"
                            f"🔗 **القناة:** {channel_link}\n"
                            f"👥 **العدد المستهدف:** {target} عضو\n"
                            f"📊 **عدد المنضمين:** {current} عضو\n\n"
                            f"📌 تم إزالة الحملة تلقائياً من النظام.\n"
                            f"شكراً لاستخدامك البوت! 💎"
                        )
                    except:
                        pass
                    # حذف الحملة
                    cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
                    self.conn.commit()
                    return True
                self.conn.commit()
                return True
            return False
        except Exception as e:
            print(f"❌ خطأ في increment_campaign_members: {e}")
            self.conn.rollback()
            return False
        finally:
            cursor.close()

    def add_campaign_join(self, campaign_id, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO campaign_joins (campaign_id, user_id, joined_at) VALUES (?, ?, ?)",
                (campaign_id, str(user_id), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        except:
            return False
        finally:
            cursor.close()

    def has_user_joined_campaign(self, campaign_id, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT 1 FROM campaign_joins WHERE campaign_id = ? AND user_id = ?",
                (campaign_id, str(user_id))
            )
            return cursor.fetchone() is not None
        except:
            return False
        finally:
            cursor.close()

    def get_user_campaigns(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT id, channel_link, target_members, current_members, status, code, created_at FROM campaigns WHERE owner_id = ? AND status = 'active' ORDER BY id DESC",
                (str(user_id),)
            )
            return cursor.fetchall()
        except:
            return []
        finally:
            cursor.close()

    def get_active_campaigns_except_owner(self, user_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT id, owner_id, channel_link, channel_username, target_members, current_members, points_per_join, code FROM campaigns WHERE status = 'active' AND owner_id != ? ORDER BY id DESC",
                (str(user_id),)
            )
            return cursor.fetchall()
        except:
            return []
        finally:
            cursor.close()

    def get_all_campaigns(self):
        """تعيد جميع الحملات النشطة فقط (status = 'active')"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT id, owner_id, channel_link, channel_username, target_members, current_members, status, code FROM campaigns WHERE status = 'active' ORDER BY id DESC")
            return cursor.fetchall()
        except:
            return []
        finally:
            cursor.close()

    def delete_campaign(self, campaign_id):
        """حذف الحملة مع إرجاع النقاط (لإلغاء الإدمن)"""
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT owner_id, target_members, price_per_member FROM campaigns WHERE id = ?", (campaign_id,))
            row = cursor.fetchone()
            if not row:
                return None, 0
            owner_id, target, price = row
            cost = target * price
            cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
            self.conn.commit()
            return owner_id, cost
        except:
            self.conn.rollback()
            return None, 0
        finally:
            cursor.close()

db = DB()

# =====================================================================
# 3. نظام الاشتراك الإجباري (للقنوات الأساسية فقط)
# =====================================================================
def check_force_subscribe(user_id):
    channels = db.get_force_channels()
    if not channels:
        return True, None
    not_subscribed = []
    for channel, channel_type in channels:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['member', 'administrator', 'creator']:
                continue
            else:
                not_subscribed.append(channel)
        except:
            not_subscribed.append(channel)
    if not_subscribed:
        return False, not_subscribed
    return True, None

def get_force_subscribe_keyboard(not_subscribed):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for channel in not_subscribed:
        clean_channel = channel.replace('@', '').strip()
        markup.add(
            types.InlineKeyboardButton(
                f"📢 اشترك في {channel}",
                url=f"https://t.me/{clean_channel}"
            )
        )
    markup.add(
        types.InlineKeyboardButton(
            "✅ تحقق من الاشتراك",
            callback_data="check_subscribe"
        )
    )
    return markup

# =====================================================================
# 4. دوال حماية البيانات (إخفاء الأرقام) - لم تعد مستخدمة لكن نتركها
# =====================================================================
def mask_phone(text):
    pattern = r'\b(05|06|07)\d{8}\b'
    def replacer(match):
        phone = match.group(0)
        return phone[:2] + 'xxxxxx' + phone[-2:]
    return re.sub(pattern, replacer, text)

# =====================================================================
# 5. دالة اختبار صلاحية البوت (للحملات)
# =====================================================================
def check_bot_permission(channel_username):
    try:
        chat = bot.get_chat(f"@{channel_username}")
        member_count = bot.get_chat_members_count(f"@{channel_username}")
        return True, chat.title
    except Exception as e:
        return False, str(e)

# =====================================================================
# 6. دوال التحقق من الحالة المعلقة
# =====================================================================
def has_pending_state(user_id):
    state = db.get_user_state(user_id)
    return state is not None and state[0] is not None

def cancel_pending_state(user_id, chat_id):
    db.clear_user_state(user_id)
    send_safe(chat_id, "❌ **تم إلغاء العملية الحالية.**", reply_markup=get_main_keyboard(user_id))

# =====================================================================
# 7. دوال التحقق (Captcha) - تُطلب مرة واحدة عند البدء
# =====================================================================
FRUITS = ["تفاح", "موز", "برتقال", "عنب", "فراولة"]
CORRECT_FRUIT = "تفاح"

def get_captcha_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = []
    for fruit in FRUITS:
        buttons.append(types.InlineKeyboardButton(fruit, callback_data=f"captcha_{fruit}"))
    markup.add(*buttons)
    return markup

def request_verification(chat_id):
    msg = (
        "🔐 **تحقق أمان**\n\n"
        "للتأكد من أنك إنسان وليس بوت، يرجى اختيار الفاكهة الصحيحة من الأزرار أدناه.\n\n"
        f"🍎 اختر الفاكهة: **{CORRECT_FRUIT}**"
    )
    bot.send_message(chat_id, msg, reply_markup=get_captcha_keyboard())

def handle_captcha_callback(call):
    user_id = call.from_user.id
    data = call.data
    if data.startswith("captcha_"):
        chosen = data.split("_", 1)[1]
        if chosen == CORRECT_FRUIT:
            db.verify_user(user_id, duration_hours=24*30)  # لمدة 30 يوم
            bot.answer_callback_query(call.id, "✅ تم التحقق بنجاح! يمكنك الاستمرار.")
            bot.delete_message(call.message.chat.id, call.message.message_id)
            send_safe(call.message.chat.id, "✅ **تم التحقق بنجاح!**\nيمكنك الآن استخدام جميع الخدمات.")
            send_safe(call.message.chat.id, "🔙 اختر الخدمة:", reply_markup=get_main_keyboard(user_id))
        else:
            attempts = db.increment_attempts(user_id)
            if attempts >= 3:
                bot.answer_callback_query(call.id, "🚫 تجاوزت عدد المحاولات المسموح بها! تم حظرك 10 دقائق.", show_alert=True)
                bot.delete_message(call.message.chat.id, call.message.message_id)
                send_safe(call.message.chat.id, "🚫 **تم حظرك مؤقتاً بسبب كثرة المحاولات الفاشلة.**\nيرجى الانتظار 10 دقائق ثم حاول مرة أخرى.")
            else:
                remaining = 3 - attempts
                bot.answer_callback_query(call.id, f"❌ اختيار خاطئ. متبقي {remaining} محاولات.", show_alert=True)
                msg = (
                    "🔐 **تحقق أمان**\n\n"
                    f"❌ اختيار خاطئ. حاول مرة أخرى، متبقي {remaining} محاولات.\n"
                    f"🍎 اختر الفاكهة: **{CORRECT_FRUIT}**"
                )
                bot.edit_message_text(msg, call.message.chat.id, call.message.message_id, reply_markup=get_captcha_keyboard())

# =====================================================================
# 8. واجهات البوت
# =====================================================================
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = []

    buttons.append(types.KeyboardButton("📁 ملف دارك"))
    buttons.append(types.KeyboardButton("📁 ملف انجكتور"))

    if str(user_id) == str(ADMIN_ID):
        buttons.append(types.KeyboardButton("🔄 تحديث دارك"))
        buttons.append(types.KeyboardButton("🔄 تحديث انجكتور"))
        buttons.append(types.KeyboardButton("📊 الإحصائيات"))
        buttons.append(types.KeyboardButton("⚙️ لوحة التحكم"))
    else:
        buttons.append(types.KeyboardButton("👨‍💻 المطور"))
        buttons.append(types.KeyboardButton("💰 شراء نقاط"))
        buttons.append(types.KeyboardButton("📤 مشاركة البوت"))
        buttons.append(types.KeyboardButton("💰 بيع نقاط"))
        buttons.append(types.KeyboardButton("📢 تمويل قناة"))

    buttons.append(types.KeyboardButton("🎡 عجلة الحظ"))
    buttons.append(types.KeyboardButton("💰 رصيدي"))
    buttons.append(types.KeyboardButton("📤 تحويل نقاط"))  # زر جديد
    buttons.append(types.KeyboardButton("🎫 إدخال كود نقاط"))

    if has_pending_state(user_id):
        buttons.append(types.KeyboardButton("❌ إلغاء العملية"))

    markup.add(*buttons)
    return markup

def get_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ إضافة قناة إجبارية", callback_data="add_channel"),
        types.InlineKeyboardButton("📋 عرض القنوات الإجبارية", callback_data="list_channels"),
        types.InlineKeyboardButton("❌ حذف قناة إجبارية", callback_data="remove_channel"),
        types.InlineKeyboardButton("📊 إحصائيات البوت", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 إرسال إعلان", callback_data="admin_announce"),
        types.InlineKeyboardButton("💰 إعدادات الدفع", callback_data="payment_settings"),
        types.InlineKeyboardButton("🎫 إنشاء كود نقاط", callback_data="create_code"),
        types.InlineKeyboardButton("📋 طلبات بيع النقاط", callback_data="view_sell_requests"),
        types.InlineKeyboardButton("📋 إدارة حملات التمويل", callback_data="manage_campaigns"),
        types.InlineKeyboardButton("🔄 إعادة تعيين تحقق مستخدم", callback_data="reset_user_verification")
    )
    return markup

def get_buy_points_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 شراء عبر فليكسي", callback_data="flexi_pay"),
        types.InlineKeyboardButton("⭐ شراء عبر نجوم تلغرام", callback_data="stars_pay"),
        types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
    )
    return markup

# =====================================================================
# 9. دوال مساعدة عامة
# =====================================================================
def parse_expiry(text):
    text = text.strip()
    try:
        dt = datetime.strptime(text, '%Y-%m-%d %H:%M')
        return int(dt.timestamp())
    except:
        pass
    if text.startswith('+'):
        try:
            num = int(text[1:-1])
            unit = text[-1]
            if unit == 'd':
                delta = timedelta(days=num)
            elif unit == 'h':
                delta = timedelta(hours=num)
            elif unit == 'm':
                delta = timedelta(minutes=num)
            else:
                return None
            return int((datetime.now() + delta).timestamp())
        except:
            pass
    return None

def send_safe(chat_id, text, parse_mode='HTML', reply_markup=None):
    try:
        bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    except:
        try:
            bot.send_message(chat_id, text, reply_markup=reply_markup)
        except:
            bot.send_message(chat_id, "حدث خطأ. حاول مرة أخرى.")

# =====================================================================
# 10. معالج الأوامر الرئيسي
# =====================================================================
@bot.message_handler(commands=['start'])
def start(message):
    try:
        user_id = message.from_user.id
        name = message.from_user.first_name
        referred_by = None
        param = None
        if len(message.text.split()) > 1:
            param = message.text.split()[1]
            if param.startswith('ref_'):
                ref_id = param.replace('ref_', '')
                if ref_id.isdigit() and int(ref_id) != user_id:
                    referred_by = int(ref_id)
        
        if param and param.startswith('fund_'):
            campaign_code = param
            campaign = db.get_campaign_by_code(campaign_code)
            if not campaign:
                send_safe(message.chat.id, "❌ هذه الحملة غير موجودة أو منتهية.")
                return
            if campaign['status'] != 'active':
                send_safe(message.chat.id, "❌ هذه الحملة قد انتهت.")
                return
            db.add_user(user_id, name, referred_by)
            if db.has_user_joined_campaign(campaign['id'], user_id):
                send_safe(
                    message.chat.id,
                    "✅ لقد حصلت بالفعل على نقاط هذه الحملة.\nلا يمكنك الحصول عليها مرة أخرى."
                )
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            channel_username = campaign['channel_username']
            if channel_username:
                markup.add(
                    types.InlineKeyboardButton(
                        "📢 انضم إلى القناة",
                        url=f"https://t.me/{channel_username}"
                    )
                )
            else:
                markup.add(
                    types.InlineKeyboardButton(
                        "📢 انضم إلى القناة",
                        url=campaign['channel_link']
                    )
                )
            markup.add(
                types.InlineKeyboardButton(
                    "✅ تحقق من الانضمام واحصل على النقاط",
                    callback_data=f"fund_verify_{campaign['id']}"
                )
            )
            send_safe(
                message.chat.id,
                f"🎁 **احصل على نقاط مجانية!**\n\n"
                f"قم بالانضمام إلى القناة التالية لتحصل على {campaign['points_per_join']} نقطة:\n"
                f"{campaign['channel_link']}\n\n"
                f"بعد الانضمام، اضغط على زر التحقق.",
                reply_markup=markup
            )
            return
        
        db.add_user(user_id, name, referred_by)
        # التحقق من الاشتراك الإجباري (القنوات الأساسية فقط)
        is_subscribed, not_subscribed = check_force_subscribe(user_id)
        if not is_subscribed:
            channels_text = "\n".join([f"• {ch}" for ch in not_subscribed])
            msg = (
                f"🔒 **اشتراك إجباري**\n\n"
                f"عذراً {name}، يجب الاشتراك في:\n\n"
                f"{channels_text}\n\n"
                f"📌 بعد الاشتراك، اضغط على زر التحقق."
            )
            send_safe(
                message.chat.id,
                msg,
                reply_markup=get_force_subscribe_keyboard(not_subscribed)
            )
            return
        
        # التحقق من حالة المستخدم: إذا لم يكن محققاً، نطلب التحقق
        if not db.is_user_verified(user_id):
            request_verification(message.chat.id)
            return
        
        # إذا كان محققاً، نعرض القائمة الرئيسية
        welcome_msg = (
            f"👋 أهلاً بك {name} في {BOT_NAME}!\n\n"
            "🌟 **المميزات:**\n"
            "• 📁 ملف دارك (1 نقطة)\n"
            "• 📁 ملف انجكتور (1 نقطة)\n"
            "• 🎡 عجلة الحظ (مرة كل 24 ساعة)\n"
            "• 💰 شراء نقاط عبر فليكسي (1000 نقطة = 100 دينار جزائري)\n"
            "• ⭐ شراء نقاط عبر نجوم تلغرام (تواصل مع المالك)\n"
            "• 💰 بيع نقاط (1200 نقطة = 100 دينار جزائري، حد أدنى 150 نقطة)\n"
            "• 📤 تحويل نقاط للمستخدمين\n"
            "• 🎫 أكواد نقاط للهدايا (كل مستخدم يستخدم الكود مرة واحدة)\n"
            "• 📢 تمويل قناة (5 نقاط لكل عضو، 2 نقطة للمنضم)\n\n"
            "اختر الخدمة 👇"
        )
        send_safe(message.chat.id, welcome_msg, reply_markup=get_main_keyboard(user_id))
    except Exception as e:
        print(f"خطأ في start: {e}")

# =====================================================================
# 11. معالج النصوص (المعدل والمكتمل)
# =====================================================================
@bot.message_handler(func=lambda m: True)
def handle_text(message):
    try:
        user_id = message.from_user.id
        text = message.text
        
        # التحقق من الاشتراك الإجباري الأساسي
        is_subscribed, not_subscribed = check_force_subscribe(user_id)
        if not is_subscribed:
            channels_text = "\n".join([f"• {ch}" for ch in not_subscribed])
            msg = (
                f"🔒 **اشتراك إجباري**\n\n"
                f"يجب الاشتراك في:\n\n"
                f"{channels_text}\n\n"
                f"📌 بعد الاشتراك، اضغط على زر التحقق."
            )
            send_safe(
                message.chat.id,
                msg,
                reply_markup=get_force_subscribe_keyboard(not_subscribed)
            )
            return

        # =============================================================
        # مسح الحالة عند أي زر من القائمة الرئيسية
        # =============================================================
        main_buttons = [
            "📁 ملف دارك",
            "📁 ملف انجكتور",
            "🔄 تحديث دارك",
            "🔄 تحديث انجكتور",
            "📊 الإحصائيات",
            "🎡 عجلة الحظ",
            "💰 رصيدي",
            "📤 مشاركة البوت",
            "📤 تحويل نقاط",
            "👨‍💻 المطور",
            "💰 بيع نقاط",
            "🎫 إدخال كود نقاط",
            "📢 تمويل قناة",
            "💰 شراء نقاط",
            "⚙️ لوحة التحكم"
        ]
        if text in main_buttons:
            db.clear_user_state(user_id)

        # ===== معالجة زر الإلغاء =====
        if text == "❌ إلغاء العملية":
            cancel_pending_state(user_id, message.chat.id)
            return

        # ===== معالجة الحالة المعلقة =====
        state = db.get_user_state(user_id)
        if state:
            current_state = state[0]
            temp_data = state[3] if state[3] else '{}'
            try:
                temp = json.loads(temp_data)
            except:
                temp = {}
                print("⚠️ خطأ في تحميل temp_data, تم استبداله بـ {}")

            # ===== حالات إنشاء كود النقاط (للإدمن) =====
            if current_state == 'admin_create_code_points':
                try:
                    points = int(text)
                    if points < 1:
                        bot.reply_to(message, "❌ عدد النقاط يجب أن يكون أكبر من 0.")
                        return
                    db.set_user_state(user_id, 'admin_create_code_uses', temp_data=json.dumps({'points': points}))
                    bot.reply_to(
                        message,
                        f"✅ تم حفظ عدد النقاط: {points}\n\n"
                        "📝 **الخطوة 2:** أرسل عدد المستخدمين الذين يمكنهم استخدام هذا الكود (كل مستخدم مرة واحدة)."
                    )
                except ValueError:
                    bot.reply_to(message, "❌ يرجى إدخال رقم صحيح.")
                return

            elif current_state == 'admin_create_code_uses':
                try:
                    uses = int(text)
                    if uses < 1:
                        bot.reply_to(message, "❌ عدد المستخدمين يجب أن يكون أكبر من 0.")
                        return
                    points = temp.get('points')
                    if not points:
                        bot.reply_to(message, "❌ حدث خطأ في البيانات المؤقتة.")
                        db.clear_user_state(user_id)
                        return
                    code = db.create_redeem_code(points, uses, user_id)
                    if code:
                        bot.reply_to(
                            message,
                            f"✅ **تم إنشاء كود النقاط بنجاح!**\n\n"
                            f"🎫 **الكود:** `{code}`\n"
                            f"⭐ عدد النقاط: {points}\n"
                            f"👥 عدد المستخدمين المسموح لهم: {uses}\n\n"
                            f"📌 يمكن لـ {uses} مستخدم مختلف استخدام هذا الكود، كل منهم مرة واحدة."
                        )
                    else:
                        bot.reply_to(message, "❌ حدث خطأ أثناء إنشاء الكود.")
                    db.clear_user_state(user_id)
                except ValueError:
                    bot.reply_to(message, "❌ يرجى إدخال رقم صحيح.")
                except json.JSONDecodeError:
                    bot.reply_to(message, "❌ حدث خطأ.")
                    db.clear_user_state(user_id)
                return

            # ===== حالات رفع الملف الدارك =====
            if current_state == 'admin_dark_file_waiting_description':
                description = text
                if not description.strip():
                    bot.reply_to(message, "❌ الوصف لا يمكن أن يكون فارغاً.")
                    return
                temp['description'] = description
                db.set_user_state(user_id, 'admin_dark_file_waiting_expiry', temp_data=json.dumps(temp))
                bot.reply_to(
                    message,
                    "✅ تم حفظ الوصف.\n\n⏳ الآن أرسل وقت انتهاء الصلاحية (مثال: `2026-07-20 15:30` أو `+1d`)."
                )
                return

            elif current_state == 'admin_dark_file_waiting_expiry':
                expiry_input = text.strip()
                expiry_timestamp = parse_expiry(expiry_input)
                if expiry_timestamp is None:
                    bot.reply_to(
                        message,
                        "❌ صيغة الوقت غير صحيحة.\nاستخدم:\n• `YYYY-MM-DD HH:MM`\n• `+1d` (يوم)\n• `+2h` (ساعة)"
                    )
                    return
                file_id = temp.get('file_id')
                description = temp.get('description')
                if not file_id or not description:
                    bot.reply_to(message, "❌ حدث خطأ في البيانات المؤقتة.")
                    db.clear_user_state(user_id)
                    return
                db.set_dark_file(file_id, description, expiry_timestamp)
                db.clear_user_state(user_id)
                expiry_str = datetime.fromtimestamp(expiry_timestamp).strftime('%Y-%m-%d %H:%M')
                escaped_desc = html.escape(description)
                formatted_desc = f"<pre>{escaped_desc}</pre>"
                bot.reply_to(
                    message,
                    f"✅ **تم تحديث ملف دارك بنجاح!**\n\n"
                    f"📝 **الوصف:**\n{formatted_desc}\n"
                    f"⏳ **ينتهي في:** `{expiry_str}`",
                    parse_mode='HTML'
                )
                return

            # ===== حالات رفع ملف الانجكتور (جديد) =====
            if current_state == 'admin_injector_file_waiting_description':
                description = text
                if not description.strip():
                    bot.reply_to(message, "❌ الوصف لا يمكن أن يكون فارغاً.")
                    return
                temp['description'] = description
                db.set_user_state(user_id, 'admin_injector_file_waiting_expiry', temp_data=json.dumps(temp))
                bot.reply_to(
                    message,
                    "✅ تم حفظ الوصف.\n\n⏳ الآن أرسل وقت انتهاء الصلاحية (مثال: `2026-07-20 15:30` أو `+1d`)."
                )
                return

            elif current_state == 'admin_injector_file_waiting_expiry':
                expiry_input = text.strip()
                expiry_timestamp = parse_expiry(expiry_input)
                if expiry_timestamp is None:
                    bot.reply_to(
                        message,
                        "❌ صيغة الوقت غير صحيحة.\nاستخدم:\n• `YYYY-MM-DD HH:MM`\n• `+1d` (يوم)\n• `+2h` (ساعة)"
                    )
                    return
                file_id = temp.get('file_id')
                description = temp.get('description')
                if not file_id or not description:
                    bot.reply_to(message, "❌ حدث خطأ في البيانات المؤقتة.")
                    db.clear_user_state(user_id)
                    return
                db.set_injector_file(file_id, description, expiry_timestamp)
                db.clear_user_state(user_id)
                expiry_str = datetime.fromtimestamp(expiry_timestamp).strftime('%Y-%m-%d %H:%M')
                escaped_desc = html.escape(description)
                formatted_desc = f"<pre>{escaped_desc}</pre>"
                bot.reply_to(
                    message,
                    f"✅ **تم تحديث ملف انجكتور بنجاح!**\n\n"
                    f"📝 **الوصف:**\n{formatted_desc}\n"
                    f"⏳ **ينتهي في:** `{expiry_str}`",
                    parse_mode='HTML'
                )
                return

            # ===== حالة بيع النقاط: إدخال عدد النقاط =====
            if current_state == 'sell_points_amount':
                try:
                    points = int(text)
                    if points < 150:
                        bot.reply_to(message, "❌ الحد الأدنى لبيع النقاط هو 150 نقطة.")
                        return
                    max_points = temp.get('max_points', 0)
                    if points > max_points:
                        bot.reply_to(
                            message,
                            f"❌ **رصيدك غير كافٍ!**\n⭐ رصيدك: {max_points} نقطة\n💡 لا يمكنك بيع أكثر من رصيدك."
                        )
                        return
                    db.set_user_state(user_id, 'sell_points_phone', temp_data=json.dumps({'points': points}))
                    amount_dzd = int(points * (100 / 1200))
                    bot.reply_to(
                        message,
                        f"✅ تم تحديد عدد النقاط: {points}\n"
                        f"📌 المبلغ المستحق: {amount_dzd} دينار جزائري (1200 نقطة = 100 دينار).\n\n"
                        f"📱 **الخطوة الأخيرة:** أرسل رقم هاتف فليكسي الذي تريد شحن الرصيد عليه.\n"
                        f"مثال: `0779429835`"
                    )
                except ValueError:
                    bot.reply_to(message, "❌ يرجى إدخال رقم صحيح.")
                return

            # ===== حالة بيع النقاط: إدخال رقم الهاتف =====
            if current_state == 'sell_points_phone':
                phone = text.strip()
                if not phone:
                    bot.reply_to(message, "❌ الرقم لا يمكن أن يكون فارغاً. أرسل رقم الهاتف.")
                    return
                points = temp.get('points')
                if not points:
                    bot.reply_to(message, "❌ حدث خطأ، حاول مرة أخرى.")
                    db.clear_user_state(user_id)
                    return
                current_points = db.get_points(user_id)
                if current_points < points:
                    bot.reply_to(
                        message,
                        f"❌ **رصيدك غير كافٍ!**\n"
                        f"⭐ رصيدك: {current_points} نقطة\n"
                        f"💡 تحتاج {points} نقطة."
                    )
                    db.clear_user_state(user_id)
                    return
                new_balance = db.add_points(user_id, -points)
                username = message.from_user.username or "لا يوجد يوزر"
                request_id = db.add_sell_request(user_id, username, phone, points)
                if request_id:
                    amount_dzd = int(points * (100 / 1200))
                    admin_text = (
                        f"💰 **طلب بيع نقاط جديد**\n\n"
                        f"🆔 رقم الطلب: `{request_id}`\n"
                        f"👤 المستخدم: @{username}\n"
                        f"🆔 المعرف: `{user_id}`\n"
                        f"📱 رقم الهاتف: `{phone}`\n"
                        f"⭐ عدد النقاط المبيعة: `{points}`\n"
                        f"💵 المبلغ المستحق: {amount_dzd} دينار جزائري\n"
                        f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                        f"⚠️ تم خصم النقاط من المستخدم.\n"
                        f"📌 قم بشحن الرصيد للمستخدم ثم اضغط على زر 'تم الشحن'."
                    )
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    markup.add(
                        types.InlineKeyboardButton("✅ تم شحن الرصيد", callback_data=f"complete_sell_{request_id}")
                    )
                    bot.send_message(ADMIN_ID, admin_text, reply_markup=markup)
                    bot.reply_to(
                        message,
                        f"✅ **تم استلام طلب بيع النقاط!**\n\n"
                        f"⭐ تم خصم {points} نقطة من رصيدك.\n"
                        f"📊 رصيدك الجديد: {new_balance} نقطة\n"
                        f"📱 رقم الهاتف: `{phone}`\n"
                        f"💵 المبلغ المستحق: {amount_dzd} دينار جزائري\n\n"
                        f"📌 سيتم شحن رصيدك قريباً.\n"
                        f"سوف تتلقى رسالة تأكيد عند اكتمال العملية."
                    )
                else:
                    db.add_points(user_id, points)
                    bot.reply_to(message, "❌ حدث خطأ أثناء تسجيل الطلب. تم إعادة النقاط.")
                db.clear_user_state(user_id)
                return

            # ===== حالة تحويل النقاط: إدخال عدد النقاط =====
            if current_state == 'transfer_points_amount':
                try:
                    amount = int(text)
                    if amount < 1:
                        bot.reply_to(message, "❌ يجب أن يكون المبلغ أكبر من 0.")
                        return
                    sender_points = db.get_points(user_id)
                    if amount > sender_points:
                        bot.reply_to(
                            message,
                            f"❌ **رصيدك غير كافٍ!**\n⭐ رصيدك: {sender_points} نقطة\n💡 لا يمكنك تحويل أكثر من رصيدك."
                        )
                        return
                    db.set_user_state(user_id, 'transfer_points_recipient', temp_data=json.dumps({'amount': amount}))
                    bot.reply_to(
                        message,
                        f"✅ تم تحديد المبلغ: {amount} نقطة.\n\n"
                        f"📝 **الخطوة التالية:** أرسل معرف (ID) المستخدم الذي تريد تحويل النقاط إليه.\n"
                        f"يمكنك الحصول على المعرف من خلال أمر `/id` أو من معلومات المستخدم.\n"
                        f"مثال: `123456789`"
                    )
                except ValueError:
                    bot.reply_to(message, "❌ يرجى إدخال رقم صحيح.")
                return

            # ===== حالة تحويل النقاط: إدخال معرف المستلم =====
            if current_state == 'transfer_points_recipient':
                recipient_id = text.strip()
                if not recipient_id.isdigit():
                    bot.reply_to(message, "❌ يجب إدخال معرف رقمي صحيح (مثال: `123456789`).")
                    return
                recipient_id = int(recipient_id)
                if recipient_id == user_id:
                    bot.reply_to(message, "❌ لا يمكنك تحويل النقاط لنفسك!")
                    return
                # التحقق من وجود المستخدم في قاعدة البيانات
                cursor = db.conn.cursor()
                cursor.execute("SELECT name FROM users WHERE id = ?", (str(recipient_id),))
                row = cursor.fetchone()
                cursor.close()
                if not row:
                    bot.reply_to(
                        message,
                        f"❌ **المستخدم غير موجود!**\n"
                        f"تأكد من أن المعرف صحيح وأن المستخدم قد بدأ البوت مسبقاً.\n"
                        f"يمكنك الحصول على المعرف من خلال أمر `/id`."
                    )
                    return
                recipient_name = row[0]
                amount = temp.get('amount')
                if not amount:
                    bot.reply_to(message, "❌ حدث خطأ في البيانات، حاول مرة أخرى.")
                    db.clear_user_state(user_id)
                    return
                # خصم النقاط من المرسل
                new_sender_balance = db.add_points(user_id, -amount)
                # إضافة النقاط للمستلم
                new_recipient_balance = db.add_points(recipient_id, amount)
                # إرسال رسالة للمرسل
                bot.reply_to(
                    message,
                    f"✅ **تم تحويل النقاط بنجاح!**\n\n"
                    f"📤 أرسلت `{amount}` نقطة إلى المستخدم `{recipient_name}` (ID: `{recipient_id}`).\n"
                    f"📊 رصيدك الجديد: `{new_sender_balance}` نقطة."
                )
                # إرسال رسالة للمستلم
                try:
                    bot.send_message(
                        recipient_id,
                        f"🎉 **لقد تلقيت نقاطاً جديدة!**\n\n"
                        f"📥 استلمت `{amount}` نقطة من المستخدم `{message.from_user.first_name}` (ID: `{user_id}`).\n"
                        f"📊 رصيدك الجديد: `{new_recipient_balance}` نقطة.\n\n"
                        f"شكراً لاستخدامك البوت! 💎"
                    )
                except:
                    pass
                db.clear_user_state(user_id)
                return

            # ===== حالة تمويل القناة: إدخال عدد الأعضاء =====
            if current_state == 'fund_amount':
                try:
                    target = int(text)
                    if target < 1:
                        bot.reply_to(message, "❌ يجب أن يكون العدد أكبر من 0.")
                        return
                    cost = target * 5
                    points = db.get_points(user_id)
                    if points < cost:
                        bot.reply_to(
                            message,
                            f"❌ **رصيدك غير كافٍ!**\n"
                            f"⭐ رصيدك: {points} نقطة\n"
                            f"💡 تحتاج {cost} نقطة (5 نقاط لكل عضو)."
                        )
                        db.clear_user_state(user_id)
                        return
                    db.set_user_state(user_id, 'fund_channel', temp_data=json.dumps({'target': target, 'cost': cost}))
                    bot.reply_to(
                        message,
                        f"✅ تم تحديد العدد: {target} عضو.\n"
                        f"💰 التكلفة: {cost} نقطة (5 نقاط لكل عضو).\n\n"
                        f"📢 **الخطوة التالية:** أرسل رابط القناة أو المجموعة التي تريد تمويلها.\n"
                        f"مثال: `https://t.me/your_channel` أو `@your_channel`\n\n"
                        f"⚠️ سيتم إنشاء حملة تمويل مستقلة، ولن تؤثر على قنوات الاشتراك الإجباري الأساسية."
                    )
                except ValueError:
                    bot.reply_to(message, "❌ يرجى إدخال رقم صحيح.")
                return

            # ===== حالة تمويل القناة: إدخال رابط القناة (مع التحقق من صلاحية البوت) =====
            if current_state == 'fund_channel':
                channel_link = text.strip()
                if not channel_link:
                    bot.reply_to(message, "❌ الرابط لا يمكن أن يكون فارغاً.")
                    return
                if not re.search(r'(?:https?://)?t\.me/|@', channel_link):
                    bot.reply_to(
                        message,
                        "❌ الرابط غير صحيح. تأكد من أنه رابط قناة تيليجرام (مثل `https://t.me/example` أو `@example`)."
                    )
                    return
                target = temp.get('target')
                cost = temp.get('cost')
                if not target or not cost:
                    bot.reply_to(message, "❌ حدث خطأ في البيانات، حاول مرة أخرى.")
                    db.clear_user_state(user_id)
                    return
                
                # استخلاص اسم المستخدم من الرابط
                channel_username = None
                match = re.search(r'(?:https?://)?t\.me/([a-zA-Z0-9_]+)', channel_link)
                if match:
                    channel_username = match.group(1)
                else:
                    if channel_link.startswith('@'):
                        channel_username = channel_link[1:]
                    else:
                        channel_username = channel_link.strip()
                
                # التحقق من أن البوت مشرف في القناة
                try:
                    bot_member = bot.get_chat_member(f"@{channel_username}", bot.get_me().id)
                    if bot_member.status not in ['administrator', 'creator']:
                        bot.reply_to(
                            message,
                            f"❌ **البوت ليس مشرفاً في القناة!**\n\n"
                            f"يرجى إضافة البوت كمشرف في قناتك مع صلاحية **\"عرض الأعضاء\"** ثم حاول مرة أخرى.\n"
                            f"🤖 معرف البوت: `{BOT_USERNAME}`"
                        )
                        db.clear_user_state(user_id)
                        return
                except Exception as e:
                    bot.reply_to(
                        message,
                        f"❌ **تعذر التحقق من صلاحية البوت في القناة!**\n\n"
                        f"تأكد من أن البوت عضو في القناة، ثم حاول مرة أخرى.\n"
                        f"إذا كان البوت مشرفاً بالفعل، تأكد من صحة الرابط.\n"
                        f"🤖 معرف البوت: `{BOT_USERNAME}`"
                    )
                    db.clear_user_state(user_id)
                    return
                
                # خصم النقاط
                new_balance = db.add_points(user_id, -cost)
                # إنشاء الحملة (بدون إضافة إلى force_channels)
                campaign_id, msg, channel_username_from_db = db.create_campaign(user_id, channel_link, target, price_per_member=5, points_per_join=2)
                if not campaign_id:
                    # إعادة النقاط في حالة الفشل
                    db.add_points(user_id, cost)
                    bot.reply_to(message, f"❌ حدث خطأ أثناء إنشاء الحملة: {msg}\nتم إرجاع النقاط.")
                    db.clear_user_state(user_id)
                    return
                campaign = db.get_campaign(campaign_id)
                invite_link = f"https://t.me/{BOT_USERNAME}?start={campaign['code']}"
                can_check, chat_title = check_bot_permission(channel_username)
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton(
                        "📤 مشاركة رابط الدعوة",
                        url=f"https://t.me/share/url?url=احصل على نقاط مجانية بالانضمام لهذه القناة! {invite_link}"
                    ),
                    types.InlineKeyboardButton(
                        "🔍 اختبار صلاحية البوت",
                        callback_data=f"test_permission_{campaign_id}"
                    )
                )
                bot.reply_to(
                    message,
                    f"✅ **تم وضع طلبك في الخدمة بنجاح!** 🚀\n\n"
                    f"🔗 **القناة:** {channel_link}\n"
                    f"👥 **الهدف:** {target} عضو\n"
                    f"💰 **التكلفة:** {cost} نقطة (5 نقاط لكل عضو)\n"
                    f"🎁 **نقاط المنضم:** 2 نقطة لكل عضو ينضم عبر رابطك.\n\n"
                    f"💎 *شكراً لثقتك بنا!* ✨",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                db.clear_user_state(user_id)
                return

        # ===== الأزرار العادية =====
        if text == "📁 ملف دارك":
            points = db.get_points(user_id)
            if points < 1:
                bot.reply_to(message, f"❌ **رصيدك غير كافٍ!**\n⭐ رصيدك: {points} نقطة\n💡 تحتاج نقطة واحدة للحصول على ملف دارك.")
                return
            db.add_points(user_id, -1)
            file_id, description, expiry = db.get_dark_file()
            if file_id and not db.is_dark_file_expired():
                expiry_str = datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M')
                escaped_desc = html.escape(description)
                caption = f"📁 **ملف دارك**\n\n📝 **الوصف:**\n<pre>{escaped_desc}</pre>\n⏳ **ينتهي في:** `{expiry_str}`\n⭐ تم خصم 1 نقطة."
                bot.send_document(
                    message.chat.id,
                    file_id,
                    caption=caption,
                    parse_mode='HTML'
                )
            else:
                bot.reply_to(message, "❌ **لا يوجد ملف دارك صالح حالياً.**")
                db.add_points(user_id, 1)
            return

        elif text == "📁 ملف انجكتور":
            points = db.get_points(user_id)
            if points < 1:
                bot.reply_to(message, f"❌ **رصيدك غير كافٍ!**\n⭐ رصيدك: {points} نقطة\n💡 تحتاج نقطة واحدة للحصول على ملف انجكتور.")
                return
            db.add_points(user_id, -1)
            file_id, description, expiry = db.get_injector_file()
            if file_id and not db.is_injector_file_expired():
                expiry_str = datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M')
                escaped_desc = html.escape(description)
                caption = f"📁 **ملف انجكتور**\n\n📝 **الوصف:**\n<pre>{escaped_desc}</pre>\n⏳ **ينتهي في:** `{expiry_str}`\n⭐ تم خصم 1 نقطة."
                bot.send_document(
                    message.chat.id,
                    file_id,
                    caption=caption,
                    parse_mode='HTML'
                )
            else:
                bot.reply_to(message, "❌ **لا يوجد ملف انجكتور صالح حالياً.**")
                db.add_points(user_id, 1)
            return

        elif text == "🔄 تحديث دارك":
            if str(user_id) != str(ADMIN_ID):
                bot.reply_to(message, "⛔ مخصص للإدمن فقط!")
                return
            db.set_user_state(user_id, 'admin_dark_file_waiting_file')
            bot.reply_to(message, "📤 **رفع ملف دارك جديد**\n\nأرسل الملف (صورة، فيديو، مستند، أو أي نوع).")
            return

        elif text == "🔄 تحديث انجكتور":
            if str(user_id) != str(ADMIN_ID):
                bot.reply_to(message, "⛔ مخصص للإدمن فقط!")
                return
            db.set_user_state(user_id, 'admin_injector_file_waiting_file')
            bot.reply_to(message, "📤 **رفع ملف انجكتور جديد**\n\nأرسل الملف (صورة، فيديو، مستند، أو أي نوع).")
            return

        elif text == "💰 رصيدي":
            points = db.get_points(user_id)
            bot.send_message(
                message.chat.id,
                f"💰 **رصيد نقاطك**\n\n⭐ عدد النقاط: `{points}`"
            )
            return

        elif text == "💰 بيع نقاط":
            if str(user_id) == str(ADMIN_ID):
                bot.reply_to(message, "⛔ هذا الزر غير متاح للمالك.")
                return
            points = db.get_points(user_id)
            if points < 150:
                bot.reply_to(
                    message,
                    f"❌ **رصيدك غير كافٍ لبيع النقاط!**\n"
                    f"⭐ رصيدك الحالي: {points} نقطة\n"
                    f"💡 الحد الأدنى لبيع النقاط هو 150 نقطة.\n"
                    f"💰 السعر: 1200 نقطة = 100 دينار جزائري."
                )
                return
            bot.send_message(
                message.chat.id,
                f"💰 **بيع نقاط**\n\n"
                f"⭐ رصيدك الحالي: {points} نقطة\n"
                f"💰 السعر: 1200 نقطة = 100 دينار جزائري.\n"
                f"📝 أدخل عدد النقاط التي تريد بيعها (الحد الأدنى 150 نقطة):"
            )
            db.set_user_state(user_id, 'sell_points_amount', temp_data=json.dumps({'max_points': points}))
            return

        elif text == "💰 شراء نقاط":
            flexi = db.get_setting('flexi_number')
            if flexi:
                msg = f"💳 **شراء نقاط**\n\n💰 السعر: 1000 نقطة = 100 دينار جزائري.\n📌 رقم فليكسي: `{flexi}`\n\nاختر طريقة الشراء:"
            else:
                msg = f"💳 **شراء نقاط**\n\n💰 السعر: 1000 نقطة = 100 دينار جزائري.\n❌ رقم فليكسي غير محدد حالياً.\nيرجى التواصل مع الإدمن.\n\nاختر طريقة الشراء:"
            send_safe(
                message.chat.id,
                msg,
                reply_markup=get_buy_points_keyboard()
            )
            return

        elif text == "🎫 إدخال كود نقاط":
            bot.send_message(
                message.chat.id,
                "🎫 **إدخال كود نقاط**\n\nأرسل الكود (يمكن لكل مستخدم استخدام الكود مرة واحدة فقط):"
            )
            db.set_user_state(user_id, 'waiting_code')
            bot.register_next_step_handler(message, process_redeem_code)
            return

        elif text == "📤 تحويل نقاط":
            if str(user_id) == str(ADMIN_ID):
                bot.reply_to(message, "⛔ هذا الزر غير متاح للمالك.")
                return
            points = db.get_points(user_id)
            if points < 1:
                bot.reply_to(
                    message,
                    f"❌ **ليس لديك نقاط كافية للتحويل!**\n⭐ رصيدك: {points} نقطة\n💡 يجب أن يكون لديك نقطة واحدة على الأقل."
                )
                return
            bot.send_message(
                message.chat.id,
                f"📤 **تحويل نقاط**\n\n"
                f"⭐ رصيدك الحالي: {points} نقطة\n"
                f"📝 أدخل عدد النقاط التي تريد تحويلها (يجب أن يكون أكبر من 0):"
            )
            db.set_user_state(user_id, 'transfer_points_amount', temp_data=json.dumps({}))
            return

        elif text == "📢 تمويل قناة":
            if str(user_id) == str(ADMIN_ID):
                bot.reply_to(message, "⛔ هذا الزر غير متاح للمالك.")
                return
            bot.send_message(
                message.chat.id,
                "📢 **تمويل قناة (حملة مستقلة)**\n\n"
                "💡 سعر العضو الواحد = 5 نقاط.\n"
                "🎁 نقطة المنضم = 2 نقطة.\n"
                "📌 سيتم إنشاء حملة برابط دعوة خاص، ولن تؤثر على قنوات الاشتراك الإجباري الأساسية.\n"
                "عند اكتمال العدد، تُغلق الحملة تلقائياً.\n\n"
                "⚠️ **ملاحظة مهمة:** يجب أن يكون البوت مشرفاً في قناتك مع صلاحية **\"عرض الأعضاء\"** حتى تعمل الحملة.\n\n"
                "📝 أدخل عدد الأعضاء الذين تريد جلبهم (مثال: 50):"
            )
            db.set_user_state(user_id, 'fund_amount', temp_data=json.dumps({}))
            return

        elif text == "📤 مشاركة البوت":
            if str(user_id) == str(ADMIN_ID):
                bot.reply_to(message, "⛔ هذا الزر غير متاح للمالك.")
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            invite_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
            share_url = f"https://t.me/share/url?url=اشترك في {BOT_NAME} واحصل على نقاط! {invite_link}"
            markup.add(
                types.InlineKeyboardButton(
                    "📤 مشاركة البوت (دعوة أصدقاء)",
                    url=share_url
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "🎁 الحصول على نقاط عبر الانضمام لقنوات",
                    callback_data="show_fund_campaigns"
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "🔙 رجوع",
                    callback_data="back_main"
                )
            )
            send_safe(
                message.chat.id,
                f"📤 **مشاركة البوت والحصول على نقاط**\n\n"
                f"🔹 **الخيار الأول:** شارك البوت مع أصدقائك واحصل على نقاط (أنت +2 نقطة، الصديق +1 نقطة).\n"
                f"🔹 **الخيار الثاني:** انضم إلى قنوات مستخدمين آخرين (حملات تمويل) واحصل على 2 نقطة لكل قناة.\n\n"
                f"اختر ما يناسبك 👇",
                reply_markup=markup
            )
            return

        elif text == "📊 الإحصائيات":
            if str(user_id) != str(ADMIN_ID):
                bot.reply_to(message, "⛔ مخصص للإدمن فقط!")
                return
            stats_text = (
                f"📊 **إحصائيات البوت**\n\n"
                f"👥 المستخدمين: `{db.get_user_count()}`\n"
                f"📅 نشطاء الأسبوع: `{db.get_active_users()}`\n"
                f"🔒 القنوات الإجبارية: `{db.get_force_channels_count()}`"
            )
            send_safe(message.chat.id, stats_text)
            return

        # ===== عجلة الحظ (بدون عرض النسب) =====
        elif text == "🎡 عجلة الحظ":
            can_claim, seconds_left = db.can_claim_daily(user_id)
            if not can_claim:
                hours = seconds_left // 3600
                minutes = (seconds_left % 3600) // 60
                seconds = seconds_left % 60
                send_safe(
                    message.chat.id,
                    f"⏳ **عجلة الحظ متاحة مرة كل 24 ساعة**\n"
                    f"المتبقي: `{hours:02d} ساعة {minutes:02d} دقيقة {seconds:02d} ثانية`"
                )
                return
            
            rand = random.random()
            if rand < 0.70:
                points = 1
                emoji = "👍"
                result_text = "ربحت نقطة واحدة!"
            elif rand < 0.90:
                points = 0
                emoji = "😅"
                result_text = "حظ سيئ! لم تربح أي نقطة."
            else:
                points = 5
                emoji = "🎉"
                result_text = "ربحت 5 نقاط! حظ سعيد!"
            
            db.claim_daily(user_id)
            
            if points > 0:
                db.add_points(user_id, points)
            
            new_balance = db.get_points(user_id)
            
            send_safe(
                message.chat.id,
                f"🎡 **عجلة الحظ**\n\n"
                f"{emoji} {result_text}\n"
                f"⭐ +{points} نقطة\n"
                f"📊 رصيدك الحالي: `{new_balance}` نقطة\n\n"
                f"⏳ يمكنك الدوران مرة أخرى بعد 24 ساعة."
            )
            return

        elif text == "👨‍💻 المطور":
            developer_text = (
                f"👨‍💻 **المطور**\n\n"
                f"• الاسم: XENYX\n"
                f"• المعرف: {DEVELOPER_USERNAME}\n"
                f"• الإصدار: 2.0\n\n"
                f"📞 للتواصل: {DEVELOPER_USERNAME}"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "📩 تواصل مع المطور",
                    url=f"https://t.me/XENYXr"
                )
            )
            send_safe(message.chat.id, developer_text, reply_markup=markup)
            return

        elif text == "⚙️ لوحة التحكم":
            if str(user_id) != str(ADMIN_ID):
                send_safe(message.chat.id, "⛔ مخصص للإدمن فقط!")
                return
            dark_status = '✅ موجود' if db.get_dark_file()[0] else '❌ لا يوجد'
            injector_status = '✅ موجود' if db.get_injector_file()[0] else '❌ لا يوجد'
            admin_text = (
                f"⚙️ **لوحة التحكم**\n\n"
                f"🔒 القنوات الإجبارية: {db.get_force_channels_count()}\n"
                f"👥 المستخدمين: {db.get_user_count()}\n"
                f"💳 رقم فليكسي: {db.get_setting('flexi_number') or '❌ غير محدد'}\n"
                f"📁 ملف دارك: {dark_status}\n"
                f"📁 ملف انجكتور: {injector_status}\n"
                f"💰 طلبات بيع نقاط معلقة: {len(db.get_sell_requests('pending'))}"
            )
            send_safe(message.chat.id, admin_text, reply_markup=get_admin_panel())
            return

        elif text.startswith('تم فليكسي'):
            admin_text = (
                f"💳 **طلب شراء عبر فليكسي**\n\n"
                f"👤 المستخدم: @{message.from_user.username or message.from_user.first_name}\n"
                f"🆔 المعرف: `{user_id}`\n"
                f"📝 الرسالة: `{text}`\n"
                f"💰 السعر: 1000 نقطة = 100 دينار جزائري.\n\n"
                f"📌 بعد التحقق، استخدم زر '🎫 إنشاء كود نقاط'."
            )
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("🎫 إنشاء كود نقاط", callback_data="create_code")
            )
            bot.send_message(ADMIN_ID, admin_text, reply_markup=markup)
            bot.reply_to(
                message,
                "✅ **تم استلام طلبك!**\n\n"
                "📌 سيقوم الإدمن بالتحقق وإرسال كود نقاط لك قريباً."
            )
            return

        else:
            pass

    except Exception as e:
        print(f"❌ خطأ في handle_text: {e}")
        traceback.print_exc()
        send_safe(message.chat.id, "❌ حدث خطأ، حاول مرة أخرى.")

# =====================================================================
# 12. معالج الملفات
# =====================================================================
@bot.message_handler(content_types=['document', 'photo', 'video', 'audio'])
def handle_files(message):
    try:
        user_id = message.from_user.id
        is_subscribed, not_subscribed = check_force_subscribe(user_id)
        if not is_subscribed:
            channels_text = "\n".join([f"• {ch}" for ch in not_subscribed])
            msg = (
                f"🔒 **اشتراك إجباري**\n\n"
                f"يجب الاشتراك في:\n\n"
                f"{channels_text}\n\n"
                f"📌 بعد الاشتراك، اضغط على زر التحقق."
            )
            send_safe(
                message.chat.id,
                msg,
                reply_markup=get_force_subscribe_keyboard(not_subscribed)
            )
            return
        state = db.get_user_state(user_id)
        if state:
            current_state = state[0]
            # معالجة رفع ملف دارك
            if current_state == 'admin_dark_file_waiting_file':
                if message.document:
                    file_id = message.document.file_id
                elif message.photo:
                    file_id = message.photo[-1].file_id
                elif message.video:
                    file_id = message.video.file_id
                elif message.audio:
                    file_id = message.audio.file_id
                else:
                    bot.reply_to(message, "❌ نوع الملف غير مدعوم.")
                    return
                temp_data = state[3] if state[3] else '{}'
                try:
                    temp = json.loads(temp_data)
                except:
                    temp = {}
                temp['file_id'] = file_id
                db.set_user_state(user_id, 'admin_dark_file_waiting_description', temp_data=json.dumps(temp))
                bot.reply_to(message, "✅ تم استلام الملف الدارك.\n\n📝 الآن أرسل وصفاً لهذا الملف:")
                return
            # معالجة رفع ملف انجكتور
            elif current_state == 'admin_injector_file_waiting_file':
                if message.document:
                    file_id = message.document.file_id
                elif message.photo:
                    file_id = message.photo[-1].file_id
                elif message.video:
                    file_id = message.video.file_id
                elif message.audio:
                    file_id = message.audio.file_id
                else:
                    bot.reply_to(message, "❌ نوع الملف غير مدعوم.")
                    return
                temp_data = state[3] if state[3] else '{}'
                try:
                    temp = json.loads(temp_data)
                except:
                    temp = {}
                temp['file_id'] = file_id
                db.set_user_state(user_id, 'admin_injector_file_waiting_description', temp_data=json.dumps(temp))
                bot.reply_to(message, "✅ تم استلام ملف الانجكتور.\n\n📝 الآن أرسل وصفاً لهذا الملف:")
                return
            else:
                bot.reply_to(message, "❌ لا توجد عملية نشطة لاستقبال الملفات.")
        else:
            bot.reply_to(message, "❌ لا توجد عملية نشطة لاستقبال الملفات.")
    except Exception as e:
        print(f"خطأ في handle_files: {e}")
        bot.reply_to(message, "❌ حدث خطأ.")

# =====================================================================
# 13. معالج إدخال الكود
# =====================================================================
def process_redeem_code(message):
    try:
        user_id = message.from_user.id
        code = message.text.strip().upper()
        if not code:
            bot.reply_to(message, "❌ الكود لا يمكن أن يكون فارغاً.")
            db.clear_user_state(user_id)
            return
        points, msg, new_balance = db.use_redeem_code(code, user_id)
        if points:
            bot.reply_to(
                message,
                f"✅ **تم إضافة النقاط بنجاح!**\n\n⭐ +{points} نقطة\n📊 نقاطك الحالية: `{new_balance}`\n\n⚠️ لا يمكنك استخدام هذا الكود مرة أخرى."
            )
        else:
            bot.reply_to(message, f"❌ {msg}")
        db.clear_user_state(user_id)
    except Exception as e:
        print(f"خطأ في process_redeem_code: {e}")
        bot.reply_to(message, "❌ حدث خطأ")

# =====================================================================
# 14. معالج الأزرار (المكتمل)
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        user_id = call.from_user.id
        data = call.data

        # معالج التحقق (Captcha)
        if data.startswith("captcha_"):
            handle_captcha_callback(call)
            return

        # أزرار لا تحتاج إلى حالة → نمسح الحالة
        clear_state_buttons = [
            "show_fund_campaigns", "back_to_share", "back_main", 
            "flexi_pay", "stars_pay", "view_sell_requests", "payment_settings",
            "list_channels", "remove_channel", "admin_stats", "admin_announce",
            "add_channel", "cancel_delete", "set_flexi", "delete_flexi",
            "manage_campaigns", "reset_user_verification"
        ]
        if data in clear_state_buttons:
            db.clear_user_state(user_id)
        
        # التحقق من الاشتراك الإجباري الأساسي
        is_subscribed, not_subscribed = check_force_subscribe(user_id)
        if not is_subscribed and data != "check_subscribe":
            bot.answer_callback_query(
                call.id,
                "🔒 يجب الاشتراك في القنوات الإجبارية!",
                show_alert=True
            )
            return
        
        if data == "check_subscribe":
            is_subscribed, not_subscribed = check_force_subscribe(user_id)
            if is_subscribed:
                bot.answer_callback_query(call.id, "✅ تم التحقق!")
                send_safe(
                    call.message.chat.id,
                    "✅ **تم التحقق بنجاح!**",
                    reply_markup=get_main_keyboard(user_id)
                )
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
            else:
                channels_text = "\n".join([f"• {ch}" for ch in not_subscribed])
                bot.answer_callback_query(call.id, "❌ لم تشترك بعد!", show_alert=True)
            return
        
        # ===== زر شراء عبر نجوم تلغرام =====
        if data == "stars_pay":
            text = (
                f"⭐ **شراء النقاط عبر نجوم تلغرام**\n\n"
                f"لشراء النقاط عبر نجوم تلغرام، تواصل مع المالك في الخاص:\n"
                f"👤 **المالك:** {DEVELOPER_USERNAME}\n\n"
                f"📌 أرسل له النجوم، وسوف يعطيك كود نقاط ☺️✅."
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "📩 تواصل مع المالك",
                    url=f"https://t.me/XENYXr"
                )
            )
            markup.add(
                types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
            )
            send_safe(call.message.chat.id, text, reply_markup=markup)
            bot.answer_callback_query(call.id, "✅")
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            return
        
        # ===== عرض حملات التمويل للمستخدمين العاديين =====
        if data == "show_fund_campaigns":
            campaigns = db.get_active_campaigns_except_owner(user_id)
            if not campaigns:
                send_safe(
                    call.message.chat.id,
                    "📢 **لا توجد حملات نشطة حالياً من مستخدمين آخرين.**\n"
                    "يمكنك إنشاء حملتك الخاصة عبر زر '📢 تمويل قناة'."
                )
                bot.answer_callback_query(call.id, "✅")
                return
            
            seen_channels = set()
            unique_campaigns = []
            for camp in campaigns:
                channel_key = camp[3]
                if channel_key and channel_key not in seen_channels:
                    seen_channels.add(channel_key)
                    unique_campaigns.append(camp)
                elif not channel_key:
                    link_key = camp[2][:30]
                    if link_key not in seen_channels:
                        seen_channels.add(link_key)
                        unique_campaigns.append(camp)
            
            if not unique_campaigns:
                send_safe(call.message.chat.id, "📢 **لا توجد حملات فريدة لعرضها.**")
                bot.answer_callback_query(call.id, "✅")
                return
            
            text = "🎁 **قائمة القنوات التي يمكنك الانضمام إليها للحصول على نقاط:**\n\n"
            markup = types.InlineKeyboardMarkup(row_width=1)
            for camp in unique_campaigns:
                camp_id, owner_id, channel_link, channel_username, target, current, points_per_join, code = camp
                remaining = target - current
                invite_url = f"https://t.me/{BOT_USERNAME}?start={code}"
                display_name = channel_username if channel_username else channel_link[:30]
                markup.add(
                    types.InlineKeyboardButton(
                        f"📢 انضم إلى {display_name}  ({points_per_join} نقطة)",
                        url=invite_url
                    )
                )
            markup.add(
                types.InlineKeyboardButton("🔙 رجوع", callback_data="back_to_share")
            )
            send_safe(
                call.message.chat.id,
                text,
                reply_markup=markup
            )
            bot.answer_callback_query(call.id, "✅")
            return
        
        if data == "back_to_share":
            markup = types.InlineKeyboardMarkup(row_width=1)
            invite_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
            share_url = f"https://t.me/share/url?url=اشترك في {BOT_NAME} واحصل على نقاط! {invite_link}"
            markup.add(
                types.InlineKeyboardButton(
                    "📤 مشاركة البوت (دعوة أصدقاء)",
                    url=share_url
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "🎁 الحصول على نقاط عبر الانضمام لقنوات",
                    callback_data="show_fund_campaigns"
                )
            )
            markup.add(
                types.InlineKeyboardButton(
                    "🔙 رجوع",
                    callback_data="back_main"
                )
            )
            send_safe(
                call.message.chat.id,
                "📤 **مشاركة البوت والحصول على نقاط**\n\n"
                "🔹 **الخيار الأول:** شارك البوت مع أصدقائك واحصل على نقاط (أنت +2 نقطة، الصديق +1 نقطة).\n"
                "🔹 **الخيار الثاني:** انضم إلى قنوات مستخدمين آخرين واحصل على 2 نقطة لكل قناة.\n\n"
                "اختر ما يناسبك 👇",
                reply_markup=markup
            )
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            bot.answer_callback_query(call.id, "✅")
            return
        
        if data.startswith('test_permission_'):
            campaign_id = int(data.split('_')[2])
            campaign = db.get_campaign(campaign_id)
            if not campaign:
                bot.answer_callback_query(call.id, "❌ الحملة غير موجودة!", show_alert=True)
                return
            channel_username = campaign['channel_username']
            if not channel_username:
                bot.answer_callback_query(call.id, "❌ لا يوجد اسم مستخدم للقناة.", show_alert=True)
                return
            can_check, info = check_bot_permission(channel_username)
            if can_check:
                bot.answer_callback_query(call.id, "✅ البوت لديه صلاحية الوصول إلى القناة!", show_alert=True)
                bot.send_message(
                    call.message.chat.id,
                    f"✅ **النتيجة:** البوت قادر على الوصول إلى القناة `@{channel_username}`.\n"
                    f"📌 يمكنه التحقق من الأعضاء ومنح النقاط."
                )
            else:
                bot.answer_callback_query(call.id, "❌ البوت لا يستطيع الوصول!", show_alert=True)
                bot.send_message(
                    call.message.chat.id,
                    f"❌ **النتيجة:** البوت لا يستطيع الوصول إلى القناة `@{channel_username}`.\n"
                    f"🔴 السبب: {info}\n\n"
                    f"⚠️ **الحل:** أضف البوت كمشرف في القناة مع صلاحية **\"عرض الأعضاء\"**، ثم اختبر مرة أخرى."
                )
            return
        
        # ===== نقطة التحقق من حملة التمويل =====
        if data.startswith('fund_verify_'):
            campaign_id = int(data.split('_')[2])
            campaign = db.get_campaign(campaign_id)
            
            if not campaign:
                bot.answer_callback_query(call.id, "❌ الحملة غير موجودة!", show_alert=True)
                return
                
            if db.has_user_joined_campaign(campaign_id, user_id):
                bot.answer_callback_query(call.id, "❌ لقد حصلت بالفعل على نقاط هذه الحملة من قبل!", show_alert=True)
                return

            channel_username = campaign['channel_username']
            try:
                member = bot.get_chat_member(f"@{channel_username}", user_id)
                if member.status not in ['member', 'administrator', 'creator']:
                    bot.answer_callback_query(call.id, "❌ لم تنضم إلى القناة بعد!", show_alert=True)
                    return
            except Exception as e:
                bot.answer_callback_query(call.id, "❌ تعذر التحقق من انضمامك، يرجى المحاولة لاحقاً.", show_alert=True)
                return

            points = campaign['points_per_join']
            db.add_points(user_id, points)
            db.add_campaign_join(campaign_id, user_id)
            db.increment_campaign_members(campaign_id)  # ستتولى هذه الدالة حذف الحملة عند الاكتمال
            
            bot.answer_callback_query(call.id, f"✅ تم إضافة {points} نقطة بنجاح!", show_alert=True)
            
            try:
                bot.edit_message_text(
                    f"✅ **تم التحقق بنجاح!** 🎉\n\n⭐ حصلت على {points} نقطة.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )
            except:
                pass
            return
        
        # ===== أزرار الإدمن =====
        if str(user_id) != str(ADMIN_ID):
            if data in ['add_channel', 'list_channels', 'remove_channel', 
                        'admin_stats', 'admin_announce', 'payment_settings', 
                        'create_code', 'del_channel_', 'cancel_delete', 
                        'set_flexi', 'delete_flexi', 'view_sell_requests',
                        'manage_campaigns', 'delete_campaign_', 'reset_user_verification']:
                bot.answer_callback_query(call.id, "⛔ مخصص للإدمن!", show_alert=True)
                return
        
        # ===== إدارة حملات التمويل (للمالك) =====
        if data == "manage_campaigns":
            campaigns = db.get_all_campaigns()  # تعيد النشطة فقط
            if not campaigns:
                send_safe(call.message.chat.id, "📋 **لا توجد حملات تمويل نشطة حالياً.**")
                bot.answer_callback_query(call.id, "✅")
                return
            text = "📋 **قائمة حملات التمويل النشطة:**\n\n"
            markup = types.InlineKeyboardMarkup(row_width=1)
            for camp in campaigns:
                camp_id, owner_id, channel_link, channel_username, target, current, status, code = camp
                status_emoji = "🟢" if status == "active" else "🔴"
                display = channel_username if channel_username else channel_link[:30]
                text += f"{status_emoji} {display}  (👤 `{owner_id}`)  {current}/{target}\n"
                markup.add(
                    types.InlineKeyboardButton(
                        f"🗑️ حذف حملة {display}",
                        callback_data=f"delete_campaign_{camp_id}"
                    )
                )
            markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
            send_safe(call.message.chat.id, text, reply_markup=markup)
            bot.answer_callback_query(call.id, "✅")
            return
        
        if data.startswith("delete_campaign_"):
            campaign_id = int(data.split("_")[2])
            camp = db.get_campaign(campaign_id)
            if not camp:
                send_safe(call.message.chat.id, "❌ الحملة غير موجودة.")
                bot.answer_callback_query(call.id, "❌")
                return
            owner_id = camp['owner_id']
            channel_username = camp['channel_username']
            owner_id, cost = db.delete_campaign(campaign_id)
            if owner_id:
                db.add_points(owner_id, cost)
                try:
                    bot.send_message(
                        owner_id,
                        f"⚠️ **تم إلغاء حملة تمويل القناة الخاصة بك بواسطة الإدمن.**\n\n"
                        f"🔗 القناة: {camp['channel_link']}\n"
                        f"💰 تم إرجاع {cost} نقطة إلى رصيدك.\n"
                        f"📌 رصيدك الحالي: {db.get_points(owner_id)} نقطة."
                    )
                except:
                    pass
                send_safe(
                    call.message.chat.id,
                    f"✅ **تم حذف الحملة وإرجاع {cost} نقطة للمستخدم `{owner_id}`.**"
                )
                try:
                    bot.delete_message(call.message.chat.id, call.message.message_id)
                except:
                    pass
                # تحديث القائمة
                campaigns = db.get_all_campaigns()
                if campaigns:
                    text = "📋 **قائمة حملات التمويل النشطة:**\n\n"
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    for camp in campaigns:
                        camp_id, owner_id, channel_link, channel_username, target, current, status, code = camp
                        status_emoji = "🟢" if status == "active" else "🔴"
                        display = channel_username if channel_username else channel_link[:30]
                        text += f"{status_emoji} {display}  (👤 `{owner_id}`)  {current}/{target}\n"
                        markup.add(
                            types.InlineKeyboardButton(
                                f"🗑️ حذف حملة {display}",
                                callback_data=f"delete_campaign_{camp_id}"
                            )
                        )
                    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="back_main"))
                    send_safe(call.message.chat.id, text, reply_markup=markup)
                else:
                    send_safe(call.message.chat.id, "📋 **لا توجد حملات تمويل نشطة حالياً.**")
            else:
                send_safe(call.message.chat.id, "❌ فشل حذف الحملة.")
            bot.answer_callback_query(call.id, "✅")
            return
        
        # ===== باقي الأزرار =====
        if data == "back_main":
            db.clear_user_state(user_id)
            send_safe(
                call.message.chat.id,
                "🔙 رجوع إلى القائمة الرئيسية",
                reply_markup=get_main_keyboard(user_id)
            )
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            bot.answer_callback_query(call.id, "✅")
            return
        
        if data.startswith('complete_sell_'):
            if str(user_id) != str(ADMIN_ID):
                bot.answer_callback_query(call.id, "⛔ مخصص للإدمن فقط!", show_alert=True)
                return
            request_id = int(data.split('_')[2])
            request = db.get_sell_request(request_id)
            if not request:
                bot.answer_callback_query(call.id, "❌ الطلب غير موجود!", show_alert=True)
                return
            if request[6] != 'pending':
                bot.answer_callback_query(call.id, "❌ هذا الطلب تم معالجته مسبقاً!", show_alert=True)
                return
            if db.update_sell_request_status(request_id, 'completed'):
                user_id_req = request[1]
                username = request[2]
                phone = request[3]
                points = request[4]
                amount_dzd = int(points * (100 / 1200))
                try:
                    bot.send_message(
                        user_id_req,
                        f"✅ **تم شحن رصيد فليكسي بنجاح!**\n\n"
                        f"💰 عدد النقاط المباعة: `{points}`\n"
                        f"📱 رقم الهاتف: `{phone}`\n"
                        f"💵 المبلغ: {amount_dzd} دينار جزائري\n\n"
                        f"🎉 تم إيداع الرصيد في حسابك."
                    )
                except:
                    pass
                bot.answer_callback_query(call.id, "✅ تم شحن الرصيد وإعلام المستخدم.")
                bot.edit_message_text(
                    f"✅ **تم شحن الرصيد**\n\nطلب #{request_id}\nالمستخدم: @{username}\nالهاتف: {phone}\nالنقاط: {points}\nالمبلغ: {amount_dzd} دينار",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=None
                )
            else:
                bot.answer_callback_query(call.id, "❌ فشل التحديث!", show_alert=True)
            return
        
        if data == "view_sell_requests":
            if str(user_id) != str(ADMIN_ID):
                bot.answer_callback_query(call.id, "⛔ مخصص للإدمن!", show_alert=True)
                return
            requests = db.get_sell_requests('pending')
            if not requests:
                send_safe(call.message.chat.id, "📋 **لا توجد طلبات بيع نقاط معلقة.**")
                bot.answer_callback_query(call.id, "✅")
                return
            text = "📋 **طلبات بيع النقاط المعلقة:**\n\n"
            for req in requests:
                points = req[4]
                amount_dzd = int(points * (100 / 1200))
                text += f"🆔 #{req[0]}\n"
                text += f"👤 المستخدم: @{req[2] or 'لا يوجد يوزر'}\n"
                text += f"📱 الهاتف: `{req[3]}`\n"
                text += f"⭐ النقاط: `{points}`\n"
                text += f"💵 المبلغ: {amount_dzd} دينار\n"
                text += f"📅 التاريخ: {req[5]}\n"
                text += "─" * 20 + "\n"
            send_safe(call.message.chat.id, text)
            bot.answer_callback_query(call.id, "✅")
            return
        
        if data == "create_code":
            db.clear_user_state(user_id)
            db.set_user_state(user_id, 'admin_create_code_points')
            bot.send_message(
                call.message.chat.id,
                "🎫 **إنشاء كود نقاط**\n\n📝 أرسل عدد النقاط:"
            )
            bot.answer_callback_query(call.id, "✅")
            return
        
        if data == "payment_settings":
            flexi = db.get_setting('flexi_number')
            text = f"💳 **إعدادات الدفع**\n\n📌 رقم فليكسي: `{flexi or '❌ غير محدد'}`\n💰 شراء: 1000 نقطة = 100 دينار جزائري\n💰 بيع: 1200 نقطة = 100 دينار جزائري\n⭐ شراء عبر نجوم تلغرام: تواصل مع المالك"
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("➕ تعيين رقم فليكسي", callback_data="set_flexi"),
                types.InlineKeyboardButton("❌ حذف رقم فليكسي", callback_data="delete_flexi")
            )
            send_safe(call.message.chat.id, text, reply_markup=markup)
            bot.answer_callback_query(call.id, "✅")
            return
        
        if data == "set_flexi":
            bot.send_message(
                call.message.chat.id,
                "📝 **تعيين رقم فليكسي**\n\nأرسل الرقم:"
            )
            bot.register_next_step_handler(call.message, set_flexi_handler)
            bot.answer_callback_query(call.id, "✅")
            return
        
        if data == "delete_flexi":
            db.delete_setting('flexi_number')
            send_safe(call.message.chat.id, "✅ **تم حذف رقم فليكسي**")
            bot.answer_callback_query(call.id, "✅")
            return
        
        if data == "add_channel":
            bot.send_message(
                call.message.chat.id,
                "📝 **إضافة قناة إجبارية**\n\nأرسل معرف القناة:\n`@hsjBwbxkw`"
            )
            bot.register_next_step_handler(call.message, add_channel_handler)
            bot.answer_callback_query(call.id, "✅")
        
        elif data == "list_channels":
            channels = db.get_force_channels()
            if channels:
                text = "📋 **القنوات الإجبارية:**\n\n"
                for i, (channel, ctype) in enumerate(channels, 1):
                    text += f"{i}. {channel} ({ctype})\n"
            else:
                text = "📋 لا توجد قنوات إجبارية."
            send_safe(call.message.chat.id, text)
            bot.answer_callback_query(call.id, "✅")
        
        elif data == "remove_channel":
            channels = db.get_force_channels()
            if not channels:
                send_safe(call.message.chat.id, "📋 لا توجد قنوات.")
                bot.answer_callback_query(call.id, "❌")
                return
            markup = types.InlineKeyboardMarkup(row_width=1)
            for channel, ctype in channels:
                markup.add(
                    types.InlineKeyboardButton(
                        f"🗑️ حذف {channel}",
                        callback_data=f"del_channel_{channel}"
                    )
                )
            markup.add(types.InlineKeyboardButton("🔙 إلغاء", callback_data="cancel_delete"))
            send_safe(call.message.chat.id, "🗑️ **اختر القناة:**", reply_markup=markup)
            bot.answer_callback_query(call.id, "✅")
        
        elif data.startswith("del_channel_"):
            channel = data.replace("del_channel_", "")
            if db.remove_force_channel(channel):
                send_safe(call.message.chat.id, f"✅ **تم حذف {channel}**")
            bot.answer_callback_query(call.id, "✅")
        
        elif data == "cancel_delete":
            send_safe(call.message.chat.id, "🔙 تم الإلغاء.")
            bot.answer_callback_query(call.id, "✅")
        
        elif data == "admin_stats":
            dark_status = '✅ موجود' if db.get_dark_file()[0] else '❌ لا يوجد'
            injector_status = '✅ موجود' if db.get_injector_file()[0] else '❌ لا يوجد'
            stats_text = (
                f"📊 **إحصائيات البوت**\n\n"
                f"👥 المستخدمين: `{db.get_user_count()}`\n"
                f"🔒 القنوات الإجبارية: `{db.get_force_channels_count()}`\n"
                f"💳 رقم فليكسي: `{db.get_setting('flexi_number') or 'غير محدد'}`\n"
                f"📁 ملف دارك: {dark_status}\n"
                f"📁 ملف انجكتور: {injector_status}\n"
                f"💰 طلبات بيع نقاط معلقة: `{len(db.get_sell_requests('pending'))}`"
            )
            send_safe(call.message.chat.id, stats_text)
            bot.answer_callback_query(call.id, "✅")
        
        elif data == "admin_announce":
            bot.send_message(
                call.message.chat.id,
                "📢 **إرسال إعلان**\n\nأرسل النص:"
            )
            bot.register_next_step_handler(call.message, admin_announce_handler)
            bot.answer_callback_query(call.id, "✅")
        
        elif data == "flexi_pay":
            flexi = db.get_setting('flexi_number')
            if not flexi:
                send_safe(
                    call.message.chat.id,
                    "❌ **رقم فليكسي غير محدد حالياً.**\nيرجى التواصل مع الإدمن."
                )
                bot.answer_callback_query(call.id, "❌", show_alert=True)
                return
            text = (
                f"💳 **الشراء عبر فليكسي**\n\n"
                f"📌 رقم فليكسي: `{flexi}`\n"
                f"💰 السعر: 1000 نقطة = 100 دينار جزائري.\n\n"
                f"📝 **الخطوات:**\n"
                f"1. أرسل المبلغ إلى الرقم أعلاه.\n"
                f"2. أرسل رسالة `تم فليكسي` مع ذكر عدد النقاط.\n"
                f"3. سيقوم الإدمن بالتحقق وإرسال كود نقاط لك."
            )
            send_safe(call.message.chat.id, text)
            bot.answer_callback_query(call.id, "✅")
        
        elif data == "reset_user_verification":
            if str(user_id) != str(ADMIN_ID):
                bot.answer_callback_query(call.id, "⛔ مخصص للإدمن!", show_alert=True)
                return
            bot.send_message(
                call.message.chat.id,
                "🔁 **إعادة تعيين تحقق المستخدم**\n\nأرسل معرف المستخدم (user_id) الذي تريد إعادة تعيين تحققه:"
            )
            bot.register_next_step_handler(call.message, reset_verification_handler)
            bot.answer_callback_query(call.id, "✅")
    
    except Exception as e:
        print(f"خطأ في handle_callback: {e}")
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ", show_alert=True)
        except:
            pass

# =====================================================================
# 15. معالج إعادة تعيين التحقق (للمشرف)
# =====================================================================
def reset_verification_handler(message):
    try:
        user_id = message.from_user.id
        if str(user_id) != str(ADMIN_ID):
            return
        target_id = message.text.strip()
        if not target_id.isdigit():
            send_safe(message.chat.id, "❌ يجب إدخال معرف رقمي صحيح.")
            return
        if db.reset_verification(target_id):
            send_safe(message.chat.id, f"✅ **تم إعادة تعيين تحقق المستخدم `{target_id}`.**")
        else:
            send_safe(message.chat.id, "❌ فشل إعادة التعيين، قد لا يكون المستخدم موجوداً.")
    except Exception as e:
        print(f"خطأ في reset_verification_handler: {e}")
        send_safe(message.chat.id, "❌ حدث خطأ.")

# =====================================================================
# 16. معالج تعيين رقم فليكسي
# =====================================================================
def set_flexi_handler(message):
    try:
        user_id = message.from_user.id
        if str(user_id) != str(ADMIN_ID):
            return
        flexi_number = message.text.strip()
        if not flexi_number:
            send_safe(message.chat.id, "❌ الرقم لا يمكن أن يكون فارغاً.")
            return
        if db.set_setting('flexi_number', flexi_number):
            send_safe(message.chat.id, f"✅ **تم تعيين رقم فليكسي:** `{flexi_number}`")
        else:
            send_safe(message.chat.id, "❌ فشل في تعيين الرقم.")
    except Exception as e:
        print(f"خطأ في set_flexi_handler: {e}")

# =====================================================================
# 17. معالج إضافة القناة والإعلان
# =====================================================================
def add_channel_handler(message):
    try:
        user_id = message.from_user.id
        if str(user_id) != str(ADMIN_ID):
            return
        channel = message.text.strip()
        if not channel.startswith('@'):
            channel = '@' + channel
        try:
            chat = bot.get_chat(channel)
            chat_type = chat.type
        except:
            send_safe(
                message.chat.id,
                f"❌ **خطأ:** لا يمكن العثور على {channel}"
            )
            return
        if db.add_force_channel(channel, chat_type):
            send_safe(
                message.chat.id,
                f"✅ **تم إضافة {channel} بنجاح!**\n📌 النوع: {chat_type}"
            )
        else:
            send_safe(
                message.chat.id,
                f"❌ فشل الإضافة! قد تكون {channel} مضافة بالفعل."
            )
    except Exception as e:
        print(f"خطأ في add_channel_handler: {e}")

def admin_announce_handler(message):
    try:
        user_id = message.from_user.id
        if str(user_id) != str(ADMIN_ID):
            return
        announce_text = message.text
        cursor = db.conn.cursor()
        cursor.execute(
            "INSERT INTO announcements (message, date) VALUES (?, ?)",
            (announce_text, datetime.now().strftime('%Y-%m-%d'))
        )
        db.conn.commit()
        cursor.close()
        cursor = db.conn.cursor()
        users = cursor.execute("SELECT id FROM users").fetchall()
        cursor.close()
        sent = 0
        failed = 0
        bot.reply_to(message, "🔄 جاري إرسال الإعلان...")
        for uid in users:
            try:
                bot.send_message(uid[0], f"📢 **إعلان جديد**\n\n{announce_text}")
                sent += 1
                time.sleep(0.05)
            except:
                failed += 1
        bot.send_message(
            ADMIN_ID,
            f"✅ **تم إرسال الإعلان**\n\n• تم الإرسال: {sent}\n• فشل: {failed}\n• المجموع: {len(users)}"
        )
    except Exception as e:
        print(f"خطأ في admin_announce_handler: {e}")

# =====================================================================
# 18. خيوط خلفية لفحص انتهاء صلاحية الملفات
# =====================================================================
def dark_file_expiry_checker():
    while True:
        try:
            if db.is_dark_file_expired():
                file_id, _, _ = db.get_dark_file()
                if file_id:
                    db.delete_dark_file()
                    bot.send_message(ADMIN_ID, "⏰ **انتهت صلاحية ملف دارك**\nتم حذفه تلقائياً.")
        except Exception as e:
            print(f"خطأ في dark_file_expiry_checker: {e}")
        time.sleep(60)

def injector_file_expiry_checker():
    while True:
        try:
            if db.is_injector_file_expired():
                file_id, _, _ = db.get_injector_file()
                if file_id:
                    db.delete_injector_file()
                    bot.send_message(ADMIN_ID, "⏰ **انتهت صلاحية ملف انجكتور**\nتم حذفه تلقائياً.")
        except Exception as e:
            print(f"خطأ في injector_file_expiry_checker: {e}")
        time.sleep(60)

# =====================================================================
# 19. تشغيل البوت
# =====================================================================
if __name__ == "__main__":
    threading.Thread(target=dark_file_expiry_checker, daemon=True).start()
    threading.Thread(target=injector_file_expiry_checker, daemon=True).start()
    
    print("=" * 50)
    print(f"⚡ {BOT_NAME} جاهز للعمل (مع تحويل النقاط)")
    print("=" * 50)
    print(f"👤 المطور: {DEVELOPER_USERNAME}")
    print(f"🆔 الآدمن: {ADMIN_ID}")
    print(f"📁 نظام الملف الدارك: نشط (تكلفة 1 نقطة)")
    print(f"📁 نظام ملف انجكتور: نشط (تكلفة 1 نقطة)")
    print(f"💳 رقم فليكسي: {db.get_setting('flexi_number') or '❌ غير محدد'}")
    print(f"📁 ملف دارك: {'✅ موجود' if db.get_dark_file()[0] else '❌ لا يوجد'}")
    print(f"📁 ملف انجكتور: {'✅ موجود' if db.get_injector_file()[0] else '❌ لا يوجد'}")
    print(f"💰 أسعار النقاط: شراء 1000 نقطة = 100 دينار، بيع 1200 نقطة = 100 دينار")
    print(f"📢 تمويل القنوات: سعر العضو 5 نقاط، نقطة المنضم 2 نقطة (مستقل عن الإجباري)")
    print(f"⭐ شراء عبر نجوم تلغرام: متاح (تواصل مع المالك)")
    print(f"🎡 عجلة الحظ: متاحة مرة كل 24 ساعة (بدون عرض النسب)")
    print(f"📤 تحويل النقاط: أرسل نقاطاً لأي مستخدم مسجل")
    print(f"🔐 نظام التحقق: يُطلب مرة واحدة عند أول بدء (اختيار فاكهة صحيحة، 3 محاولات، حظر 10 دقائق)")
    print("✅ تم إضافة ميزة تحويل النقاط بين المستخدمين.")
    print("=" * 50)
    print("🔄 تشغيل البوت...")
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"❌ خطأ: {e}")
            traceback.print_exc()
            print("🔄 إعادة المحاولة بعد 5 ثواني...")
            time.sleep(5)