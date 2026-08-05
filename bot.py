#!/usr/bin/env python3
"""
🚀 CloudX Hosting Bot - v4.3 (بدون JobQueue، يعمل بأمان في Railway)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- استبدال JobQueue بـ asyncio.create_task لجدولة التنظيف.
- جميع الميزات السابقة محفوظة.
"""

import asyncio
import subprocess
import sys
import os
import uuid
import logging
import json
import signal
from pathlib import Path
from datetime import datetime, timedelta
from pymongo import MongoClient

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup,
    LabeledPrice
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, PreCheckoutQueryHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── إعدادات البيئة ───────────────────────────────────────────────────────────
TOKEN         = "8914863858:AAEsZujShfvrZ5VUQ6KT8A2QIClntbihH8Y"
ADMIN_IDS     = [8633059017]          # أضف آيديات الأدمن هنا
CHANNEL_ID    = os.getenv("CHANNEL_ID", "")
ADMIN_CHANNEL = os.getenv("ADMIN_CHANNEL", "")
MAX_SESSIONS  = int(os.getenv("MAX_SESSIONS", "100"))
HOST_HOURS    = int(os.getenv("HOST_HOURS", "24"))
MONGO_URI     = os.getenv("MONGO_URI", "")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_KB", "500")) * 1024

UPLOADS_DIR = Path("hosted_bots");  UPLOADS_DIR.mkdir(exist_ok=True)
PENDING_DIR = Path("pending_bots"); PENDING_DIR.mkdir(exist_ok=True)
DATA_FILE   = Path("cloudx_data.json")

mongo_client = None
mongo_db     = None

# ─── MongoDB ──────────────────────────────────────────────────────────────────
def init_mongo():
    global mongo_client, mongo_db
    if not MONGO_URI:
        log.warning("MONGO_URI غير موجود — سيتم استخدام الملف المحلي")
        return
    try:
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        mongo_db     = mongo_client["cloudx_hosting"]
        mongo_client.server_info()
        log.info("✅ MongoDB متصل")
    except Exception as e:
        log.error(f"MongoDB خطأ: {e}")
        mongo_client = mongo_db = None

# ─── الباقات ──────────────────────────────────────────────────────────────────
PACKAGES = {
    "basic": {"name": "⚪ Basic", "points_cost": 0,   "stars_cost": 0,   "max_bots": 1,   "desc": "بوت واحد مجاني"},
    "pro":   {"name": "🔵 Pro",   "points_cost": 50,  "stars_cost": 25,  "max_bots": 5,   "desc": "5 بوتات"},
    "vip":   {"name": "🟡 VIP",   "points_cost": 150, "stars_cost": 75,  "max_bots": 20,  "desc": "20 بوت"},
    "ultra": {"name": "💎 Ultra", "points_cost": 500, "stars_cost": 200, "max_bots": 999, "desc": "غير محدود"},
}

# ─── قاعدة البيانات المحلية ───────────────────────────────────────────────────
db = {
    "users":    {},
    "sessions": {},
    "pending":  {},
    "coupons":  {},
    "stats":    {"total_users": 0, "total_deploys": 0, "total_points_given": 0}
}

def save_db():
    try:
        data = {
            "users":   db["users"],
            "coupons": db["coupons"],
            "stats":   db["stats"],
            "pending": db.get("pending", {})
        }
        if mongo_db is not None:
            mongo_db["data"].replace_one({"_id": "main"}, {"_id": "main", **data}, upsert=True)
        else:
            DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.error(f"خطأ حفظ: {e}")

def load_db():
    src = None
    if mongo_db is not None:
        try:
            src = mongo_db["data"].find_one({"_id": "main"})
            if src:
                log.info("✅ تم تحميل البيانات من MongoDB")
        except Exception as e:
            log.error(f"خطأ تحميل MongoDB: {e}")
    if src is None and DATA_FILE.exists():
        try:
            src = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            log.info("✅ تم تحميل البيانات من الملف المحلي")
        except Exception as e:
            log.error(f"خطأ تحميل: {e}")
    if src:
        db["users"]   = src.get("users",   {})
        db["coupons"] = src.get("coupons", {})
        db["stats"]   = src.get("stats",   db["stats"])
        db["pending"] = src.get("pending", {})

# ─── مساعدات المستخدم ─────────────────────────────────────────────────────────
def get_user(uid):
    key = str(uid)
    if key not in db["users"]:
        db["users"][key] = {
            "points": 3, "stars": 0, "package": "basic",
            "daily_last": "", "referred_by": None,
            "join_date": datetime.now().strftime("%Y-%m-%d"),
            "banned": False, "ban_reason": "", "total_deploys": 0
        }
        db["stats"]["total_users"] += 1
        save_db()
    return db["users"][key]

def is_banned(uid):       return get_user(uid).get("banned", False)
def get_pts(uid):         return get_user(uid).get("points", 0)
def get_stars(uid):       return get_user(uid).get("stars", 0)
def get_package(uid):     return get_user(uid).get("package", "basic")
def max_bots(uid):        return PACKAGES.get(get_package(uid), PACKAGES["basic"])["max_bots"]
def user_bots_count(uid): return sum(1 for s in db["sessions"].values() if s["owner"] == uid)

# ─── لوحات المفاتيح ───────────────────────────────────────────────────────────
def main_kb(uid: int):
    """قائمة رئيسية مع زر لوحة الأدمن للأدمن فقط"""
    buttons = [
        [KeyboardButton("🚀 رفع ملف"),    KeyboardButton("📂 بوتاتي")],
        [KeyboardButton("💰 نقاطي"),       KeyboardButton("🎁 نقطة يومية")],
        [KeyboardButton("🛒 الباقات"),     KeyboardButton("🎫 كوبون")],
        [KeyboardButton("👥 الإحالات"),   KeyboardButton("📊 إحصائياتي")],
    ]
    if uid in ADMIN_IDS:
        buttons.append([KeyboardButton("🛠 لوحة الأدمن")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def packages_kb(uid):
    current = get_package(uid)
    rows = []
    for pkg_id, pkg in PACKAGES.items():
        mark = "✅ " if pkg_id == current else ""
        rows.append([InlineKeyboardButton(
            f"{mark}{pkg['name']} — {pkg['stars_cost']}⭐ او {pkg['points_cost']} نقطة",
            callback_data=f"buy|{pkg_id}"
        )])
    return InlineKeyboardMarkup(rows)

def bot_control_kb(sid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 إعادة تشغيل", callback_data=f"restart|{sid}"),
         InlineKeyboardButton("🛑 إيقاف",        callback_data=f"stop|{sid}")],
        [InlineKeyboardButton("📋 معلومات",      callback_data=f"info|{sid}")]
    ])

def approval_kb(pending_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول",  callback_data=f"approve|{pending_id}"),
        InlineKeyboardButton("❌ رفض",   callback_data=f"reject|{pending_id}")
    ]])

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 حظر",           callback_data="adm|ban"),
         InlineKeyboardButton("✅ رفع حظر",        callback_data="adm|unban")],
        [InlineKeyboardButton("🪙 شحن نقاط",      callback_data="adm|give_pts"),
         InlineKeyboardButton("⭐ شحن Stars",      callback_data="adm|give_stars")],
        [InlineKeyboardButton("🎫 كوبون جديد",    callback_data="adm|coupon"),
         InlineKeyboardButton("📊 إحصائيات",      callback_data="adm|stats")],
        [InlineKeyboardButton("📢 بث رسالة",      callback_data="adm|broadcast"),
         InlineKeyboardButton("🗂️ كل البوتات",   callback_data="adm|all_bots")],
        [InlineKeyboardButton("🔧 ترقية مستخدم",  callback_data="adm|upgrade"),
         InlineKeyboardButton("⏳ طلبات معلقة",   callback_data="adm|pending")],
    ])

# ─── التحقق من الاشتراك ───────────────────────────────────────────────────────
async def check_subscription(bot, uid):
    if not CHANNEL_ID:
        return True
    try:
        member = await bot.get_chat_member(CHANNEL_ID, uid)
        return member.status not in ["left", "kicked"]
    except:
        return True

# ─── إيقاف عملية ─────────────────────────────────────────────────────────────
def kill_process(pid: int):
    try:
        if sys.platform != "win32":
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        else:
            subprocess.call(["taskkill", "/F", "/PID", str(pid)], stderr=subprocess.DEVNULL)
    except Exception as e:
        log.warning(f"kill_process({pid}): {e}")

# ─── تشغيل البوت بعد موافقة الأدمن ──────────────────────────────────────────
async def _deploy_bot(ctx: ContextTypes.DEFAULT_TYPE, uid: int, pending_id: str) -> bool:
    pending = db["pending"].get(pending_id)
    if not pending:
        return False

    cost = pending.get("cost", 3)
    if uid not in ADMIN_IDS:
        user = get_user(uid)
        if user.get("points", 0) >= cost:
            user["points"] -= cost
        elif user.get("stars", 0) >= 2:
            user["stars"] -= 2
        else:
            try:
                await ctx.bot.send_message(uid, "❌ رصيدك غير كافٍ للتشغيل!")
            except:
                pass
            return False

    file_path = Path(pending["path"])
    new_path  = UPLOADS_DIR / file_path.name
    try:
        if file_path.exists():
            import shutil
            shutil.copy2(file_path, new_path)
            file_path.unlink(missing_ok=True)
        else:
            try:
                await ctx.bot.send_message(uid, "❌ ملفك لم يعد موجوداً، أرسله مجدداً.")
            except:
                pass
            del db["pending"][pending_id]
            save_db()
            return False
    except Exception as e:
        log.error(f"نقل الملف: {e}")
        new_path = file_path

    try:
        proc = subprocess.Popen(
            [sys.executable, str(new_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if sys.platform != "win32" else None
        )
        expires = (datetime.now() + timedelta(hours=HOST_HOURS)).strftime("%Y-%m-%d %H:%M")
        db["sessions"][pending_id] = {
            "owner":      uid,
            "name":       pending["name"],
            "path":       str(new_path),
            "pid":        proc.pid,
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "expires":    expires
        }
        get_user(uid)["total_deploys"] = get_user(uid).get("total_deploys", 0) + 1
        db["stats"]["total_deploys"] += 1
        del db["pending"][pending_id]
        save_db()

        try:
            await ctx.bot.send_message(
                uid,
                f"<b>✅ تم تشغيل بوتك!</b>\n\n"
                f"📄 الملف: <code>{pending['name']}</code>\n"
                f"🔑 الرمز: <code>{pending_id}</code>\n"
                f"⏰ بدأ: {db['sessions'][pending_id]['start_time']}\n"
                f"🕐 ينتهي: {expires}",
                parse_mode=ParseMode.HTML,
                reply_markup=bot_control_kb(pending_id)
            )
        except:
            pass
        return True
    except Exception as e:
        log.error(f"خطأ تشغيل: {e}")
        return False

# ─── تنظيف الجلسات المنتهية (مهمة خلفية) ──────────────────────────────────
async def cleanup_loop(app: Application):
    """تعمل كل ساعة لتنظيف الجلسات المنتهية"""
    while True:
        await asyncio.sleep(3600)  # انتظر ساعة
        now = datetime.now()
        expired = []
        for sid, s in list(db["sessions"].items()):
            try:
                exp = datetime.strptime(s.get("expires", ""), "%Y-%m-%d %H:%M")
                if now > exp:
                    expired.append(sid)
            except:
                pass
        for sid in expired:
            s = db["sessions"].get(sid)
            if s:
                kill_process(s["pid"])
                Path(s["path"]).unlink(missing_ok=True)
                owner = s["owner"]
                del db["sessions"][sid]
                save_db()
                try:
                    await app.bot.send_message(
                        owner,
                        f"⏰ <b>انتهت مدة استضافة بوتك</b>\n"
                        f"📄 الملف: <code>{s['name']}</code>\n"
                        f"أرسل الملف مجدداً للاستمرار.",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
        if expired:
            log.info(f"🧹 تم تنظيف {len(expired)} جلسة منتهية")

# ─── /start ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        await update.message.reply_text(f"🚫 أنت محظور\nالسبب: {get_user(uid).get('ban_reason','')}")
        return
    user = get_user(uid)
    if ctx.args and ctx.args[0].startswith("ref_") and not user.get("referred_by"):
        try:
            inviter = int(ctx.args[0].split("_")[1])
            if inviter != uid:
                user["referred_by"] = inviter
                inv = get_user(inviter)
                inv["points"] = inv.get("points", 0) + 10
                db["stats"]["total_points_given"] += 10
                save_db()
                try:
                    await ctx.bot.send_message(inviter, "🎉 عضو جديد انضم عبر إحالتك!\n+10 نقاط لك 🪙")
                except:
                    pass
        except:
            pass
    if not await check_subscription(ctx.bot, uid):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton(
            "📢 اشترك في القناة",
            url=f"https://t.me/{CHANNEL_ID.lstrip('@')}"
        )]])
        await update.message.reply_text("⚠️ يجب الاشتراك في قناتنا أولاً!", reply_markup=btn)
        return
    name = update.effective_user.first_name or "مستخدم"
    pkg  = PACKAGES.get(get_package(uid), PACKAGES["basic"])
    await update.message.reply_text(
        f"<b>☁️ CloudX Hosting Bot</b>\n\n"
        f"👤 الاسم: <b>{name}</b>\n"
        f"📦 الباقة: <b>{pkg['name']}</b>\n"
        f"🪙 النقاط: <b>{get_pts(uid)}</b>\n"
        f"⭐ Stars: <b>{get_stars(uid)}</b>\n"
        f"🤖 البوتات: <b>{user_bots_count(uid)}/{max_bots(uid)}</b>\n"
        f"📅 الانضمام: <b>{user.get('join_date','؟')}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_kb(uid)
    )

# ─── /admin ───────────────────────────────────────────────────────────────────
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    ctx.user_data.clear()
    await update.message.reply_text(
        f"<b>🛠️ لوحة الأدمن</b>\n\n"
        f"👥 المستخدمون: <b>{db['stats'].get('total_users',0)}</b>\n"
        f"🚀 Deployments: <b>{db['stats'].get('total_deploys',0)}</b>\n"
        f"🤖 البوتات النشطة: <b>{len(db['sessions'])}</b>\n"
        f"⏳ طلبات معلقة: <b>{len(db.get('pending',{}))}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=admin_kb()
    )

# ─── استقبال الملف ────────────────────────────────────────────────────────────
async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        return
    if not await check_subscription(ctx.bot, uid):
        await update.message.reply_text("⚠️ اشترك في القناة أولاً!")
        return
    if len(db["sessions"]) >= MAX_SESSIONS:
        await update.message.reply_text("⚠️ السيرفر ممتلئ حالياً، حاول لاحقاً!")
        return

    doc = update.message.document
    if not doc.file_name.endswith(".py"):
        await update.message.reply_text("❌ فقط ملفات .py مقبولة!")
        return
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f"❌ حجم الملف كبير جداً!\n"
            f"الحد الأقصى: {MAX_FILE_SIZE // 1024} KB\n"
            f"حجم ملفك: {doc.file_size // 1024} KB"
        )
        return

    if user_bots_count(uid) >= max_bots(uid):
        pkg = PACKAGES.get(get_package(uid))
        await update.message.reply_text(
            f"⚠️ وصلت للحد الأقصى ({max_bots(uid)} بوت) في باقتك {pkg['name']}\n"
            f"ارقَّ باقتك من 🛒 الباقات"
        )
        return

    cost = 3
    if uid not in ADMIN_IDS:
        if get_pts(uid) < cost and get_stars(uid) < 2:
            await update.message.reply_text(
                f"❌ رصيدك غير كافٍ!\n"
                f"تحتاج <b>{cost} نقاط</b> أو <b>2 Stars</b>\n\n"
                f"رصيدك: 🪙 {get_pts(uid)} | ⭐ {get_stars(uid)}",
                parse_mode=ParseMode.HTML
            )
            return

    msg = await update.message.reply_text("⏳ جاري إرسال طلبك للمراجعة...")
    pending_id = str(uuid.uuid4())[:8]
    file_path  = PENDING_DIR / f"{uid}_{pending_id}_{doc.file_name}"

    try:
        t_file = await doc.get_file()
        await t_file.download_to_drive(custom_path=file_path)

        db["pending"][pending_id] = {
            "owner":        uid,
            "name":         doc.file_name,
            "path":         str(file_path),
            "cost":         cost,
            "request_time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        save_db()

        user_info = update.effective_user
        req_text  = (
            f"<b>📋 طلب استضافة جديد</b>\n\n"
            f"👤 المستخدم: <a href='tg://user?id={uid}'>{user_info.first_name}</a>\n"
            f"🆔 الآيدي: <code>{uid}</code>\n"
            f"📄 الملف: <code>{doc.file_name}</code>\n"
            f"📦 حجمه: {(doc.file_size or 0)//1024} KB\n"
            f"🪙 نقاطه: <b>{get_pts(uid)}</b> | ⭐ Stars: <b>{get_stars(uid)}</b>\n"
            f"📦 الباقة: <b>{PACKAGES[get_package(uid)]['name']}</b>\n"
            f"🕐 الوقت: {db['pending'][pending_id]['request_time']}\n"
            f"🔑 رمز الطلب: <code>{pending_id}</code>"
        )

        sent = False
        targets = list(ADMIN_IDS)
        if ADMIN_CHANNEL:
            targets.append(ADMIN_CHANNEL)
        for target in targets:
            try:
                await ctx.bot.send_document(
                    chat_id=target,
                    document=doc.file_id,
                    caption=req_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=approval_kb(pending_id)
                )
                sent = True
            except Exception as e:
                log.error(f"خطأ إرسال للأدمن {target}: {e}")

        if sent:
            await msg.edit_text(
                f"<b>⏳ تم إرسال طلبك بنجاح!</b>\n\n"
                f"📄 الملف: <code>{doc.file_name}</code>\n"
                f"🔑 رمز الطلب: <code>{pending_id}</code>\n\n"
                f"⏳ انتظر موافقة الأدمن، سيتم إشعارك.",
                parse_mode=ParseMode.HTML
            )
        else:
            await _deploy_bot(ctx, uid, pending_id)
            await msg.delete()

    except Exception as e:
        log.error(f"handle_document: {e}")
        await msg.edit_text(f"❌ خطأ غير متوقع: {e}")

# ─── الرسائل النصية ───────────────────────────────────────────────────────────
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()
    if is_banned(uid):
        return

    if uid in ADMIN_IDS and ctx.user_data.get("adm_action"):
        await handle_admin_input(update, ctx)
        return

    if ctx.user_data.get("waiting_coupon"):
        ctx.user_data.pop("waiting_coupon")
        code = text.upper()
        coup = db["coupons"].get(code)
        if not coup:
            await update.message.reply_text("❌ كوبون غير صالح!")
        elif coup["uses_left"] <= 0:
            await update.message.reply_text("❌ هذا الكوبون استُنفد!")
        else:
            used_by = coup.get("used_by", [])
            if str(uid) in used_by:
                await update.message.reply_text("❌ استخدمت هذا الكوبون من قبل!")
            else:
                user = get_user(uid)
                if coup["type"] == "points":
                    user["points"] = user.get("points", 0) + coup["discount"]
                    db["stats"]["total_points_given"] += coup["discount"]
                elif coup["type"] == "stars":
                    user["stars"] = user.get("stars", 0) + coup["discount"]
                coup["uses_left"] -= 1
                coup.setdefault("used_by", []).append(str(uid))
                save_db()
                kind = "نقاط" if coup["type"] == "points" else "Stars"
                await update.message.reply_text(f"✅ تم تفعيل الكوبون! +{coup['discount']} {kind} 🎉")
        return

    if text == "🚀 رفع ملف":
        pkg = PACKAGES.get(get_package(uid))
        await update.message.reply_text(
            f"<b>📤 أرسل ملف .py الآن</b>\n\n"
            f"📦 باقتك: <b>{pkg['name']}</b>\n"
            f"🤖 البوتات: <b>{user_bots_count(uid)}/{max_bots(uid)}</b>\n"
            f"💰 التكلفة: <b>3 نقاط</b> أو <b>2 Stars</b>\n"
            f"📏 الحد الأقصى للحجم: <b>{MAX_FILE_SIZE//1024} KB</b>\n"
            f"⏳ سيراجع الأدمن الملف قبل التشغيل",
            parse_mode=ParseMode.HTML
        )

    elif text == "📂 بوتاتي":
        my = {sid: s for sid, s in db["sessions"].items() if s["owner"] == uid}
        if not my:
            await update.message.reply_text("📭 لا يوجد بوتات نشطة حالياً.")
            return
        for sid, s in my.items():
            pid_alive = False
            try:
                os.kill(s["pid"], 0)
                pid_alive = True
            except:
                pass
            status = "🟢 يعمل" if pid_alive else "🔴 متوقف"
            await update.message.reply_text(
                f"<b>🤖 {s['name']}</b>\n"
                f"🔑 الرمز: <code>{sid}</code>\n"
                f"📊 الحالة: {status}\n"
                f"⏰ منذ: {s['start_time']}\n"
                f"🕐 ينتهي: {s.get('expires','؟')}",
                parse_mode=ParseMode.HTML,
                reply_markup=bot_control_kb(sid)
            )

    elif text == "💰 نقاطي":
        user = get_user(uid)
        pkg  = PACKAGES.get(get_package(uid))
        await update.message.reply_text(
            f"<b>💰 رصيدك</b>\n\n"
            f"🪙 النقاط: <b>{user.get('points', 0)}</b>\n"
            f"⭐ Stars: <b>{user.get('stars', 0)}</b>\n"
            f"📦 الباقة: <b>{pkg['name']}</b>\n"
            f"🚀 Deployments: <b>{user.get('total_deploys', 0)}</b>",
            parse_mode=ParseMode.HTML
        )

    elif text == "🎁 نقطة يومية":
        user  = get_user(uid)
        today = datetime.now().strftime("%Y-%m-%d")
        if user.get("daily_last") == today:
            await update.message.reply_text("⏰ خذت نقطتك اليومية! عد غداً.")
        else:
            bonus = 2 if get_package(uid) in ["vip", "ultra"] else 1
            user["points"]     = user.get("points", 0) + bonus
            user["daily_last"] = today
            db["stats"]["total_points_given"] += bonus
            save_db()
            extra = " (مضاعفة VIP! 🎖️)" if bonus == 2 else ""
            await update.message.reply_text(f"✅ تم إضافة +{bonus} نقطة{extra}")

    elif text == "🛒 الباقات":
        txt = "<b>📦 الباقات المتاحة:</b>\n\n"
        for pkg_id, pkg in PACKAGES.items():
            mark = "✅ " if get_package(uid) == pkg_id else ""
            txt += f"{mark}<b>{pkg['name']}</b>\n• {pkg['desc']}\n• 🪙 {pkg['points_cost']} | ⭐ {pkg['stars_cost']}\n\n"
        await update.message.reply_text(txt, parse_mode=ParseMode.HTML, reply_markup=packages_kb(uid))

    elif text == "🎫 كوبون":
        ctx.user_data["waiting_coupon"] = True
        await update.message.reply_text("🎫 أدخل كود الكوبون:")

    elif text == "👥 الإحالات":
        bot_user = await ctx.bot.get_me()
        link  = f"https://t.me/{bot_user.username}?start=ref_{uid}"
        count = sum(1 for u in db["users"].values() if u.get("referred_by") == uid)
        await update.message.reply_text(
            f"<b>👥 نظام الإحالات</b>\n\n"
            f"🔗 رابطك الخاص:\n<code>{link}</code>\n\n"
            f"👤 أحلت: <b>{count} شخص</b>\n"
            f"💎 مكافأة كل إحالة: <b>+10 نقاط</b>",
            parse_mode=ParseMode.HTML
        )

    elif text == "📊 إحصائياتي":
        user  = get_user(uid)
        count = sum(1 for u in db["users"].values() if u.get("referred_by") == uid)
        await update.message.reply_text(
            f"<b>📊 إحصائياتك</b>\n\n"
            f"📅 الانضمام: <b>{user.get('join_date','؟')}</b>\n"
            f"🚀 Deployments: <b>{user.get('total_deploys', 0)}</b>\n"
            f"👥 الإحالات: <b>{count}</b>\n"
            f"🪙 النقاط: <b>{get_pts(uid)}</b>\n"
            f"⭐ Stars: <b>{get_stars(uid)}</b>",
            parse_mode=ParseMode.HTML
        )

    elif text == "🛠 لوحة الأدمن":
        if uid not in ADMIN_IDS:
            await update.message.reply_text("⛔ غير مصرح!")
            return
        await update.message.reply_text(
            f"<b>🛠️ لوحة الأدمن</b>\n\n"
            f"👥 المستخدمون: <b>{db['stats'].get('total_users',0)}</b>\n"
            f"🚀 Deployments: <b>{db['stats'].get('total_deploys',0)}</b>\n"
            f"🤖 البوتات النشطة: <b>{len(db['sessions'])}</b>\n"
            f"⏳ طلبات معلقة: <b>{len(db.get('pending',{}))}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_kb()
        )

# ─── إدخال الأدمن ─────────────────────────────────────────────────────────────
async def handle_admin_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()
    act  = ctx.user_data.pop("adm_action", "")

    async def reply(msg): await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    if act == "ban":
        try:
            parts  = text.split(None, 1)
            target = int(parts[0])
            reason = parts[1] if len(parts) > 1 else "لا يوجد سبب"
            u = get_user(target)
            u["banned"] = True; u["ban_reason"] = reason
            save_db()
            await reply(f"✅ تم حظر <code>{target}</code>\nالسبب: {reason}")
        except:
            await reply("الصيغة: <code>الآيدي [السبب]</code>")

    elif act == "unban":
        try:
            target = int(text)
            get_user(target)["banned"] = False
            save_db()
            await reply(f"✅ رُفع الحظر عن <code>{target}</code>")
        except:
            await reply("أرسل الآيدي فقط")

    elif act in ("give_pts", "give_stars"):
        try:
            t_uid, amt = int(text.split()[0]), int(text.split()[1])
            u = get_user(t_uid)
            if act == "give_pts":
                u["points"] = u.get("points", 0) + amt
                db["stats"]["total_points_given"] += amt
                kind = "نقطة 🪙"
            else:
                u["stars"] = u.get("stars", 0) + amt
                kind = "Stars ⭐"
            save_db()
            await reply(f"✅ تم شحن +{amt} {kind} للمستخدم <code>{t_uid}</code>")
            try:
                await ctx.bot.send_message(t_uid, f"🎁 شُحن +{amt} {kind} في رصيدك من الإدارة!")
            except:
                pass
        except:
            await reply("الصيغة: <code>الآيدي الكمية</code>")

    elif act == "coupon":
        try:
            parts = text.split()
            code, typ, amt, uses = parts[0].upper(), parts[1], int(parts[2]), int(parts[3])
            if typ not in ["points", "stars"]:
                raise ValueError
            db["coupons"][code] = {"discount": amt, "uses_left": uses, "type": typ, "used_by": []}
            save_db()
            await reply(
                f"✅ تم إنشاء الكوبون:\n"
                f"الكود: <code>{code}</code>\n"
                f"النوع: {typ} | القيمة: {amt} | الاستخدامات: {uses}"
            )
        except:
            await reply("الصيغة: <code>الكود النوع(points/stars) الكمية الاستخدامات</code>")

    elif act == "broadcast":
        sent = failed = 0
        for key in list(db["users"]):
            try:
                await ctx.bot.send_message(int(key), f"📢 <b>رسالة من الإدارة:</b>\n\n{text}", parse_mode=ParseMode.HTML)
                sent += 1
                await asyncio.sleep(0.05)
            except:
                failed += 1
        await reply(f"📢 البث انتهى!\n✅ نجح: {sent}\n❌ فشل: {failed}")

    elif act == "upgrade":
        try:
            t_uid, pkg = int(text.split()[0]), text.split()[1]
            if pkg not in PACKAGES:
                raise ValueError
            get_user(t_uid)["package"] = pkg
            save_db()
            await reply(f"✅ تمت ترقية <code>{t_uid}</code> إلى {PACKAGES[pkg]['name']}")
            try:
                await ctx.bot.send_message(t_uid, f"🎉 تمت ترقية باقتك إلى {PACKAGES[pkg]['name']}!")
            except:
                pass
        except:
            await reply("الصيغة: <code>الآيدي اسم_الباقة</code>\n(basic/pro/vip/ultra)")

    elif act == "reject_reason":
        pending_id = ctx.user_data.pop("reject_pending_id", "")
        pending = db["pending"].get(pending_id)
        if pending:
            owner_uid = pending["owner"]
            Path(pending["path"]).unlink(missing_ok=True)
            del db["pending"][pending_id]
            save_db()
            try:
                await ctx.bot.send_message(
                    owner_uid,
                    f"❌ <b>تم رفض طلب الاستضافة</b>\n\n"
                    f"📄 الملف: <code>{pending['name']}</code>\n"
                    f"📝 السبب: {text}",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
            await reply(f"✅ تم رفض الطلب وإشعار المستخدم <code>{owner_uid}</code>")
        else:
            await reply("⚠️ الطلب غير موجود أو تمت معالجته مسبقاً")

# ─── Callbacks ────────────────────────────────────────────────────────────────
async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    parts  = q.data.split("|", 1)
    action = parts[0]
    value  = parts[1] if len(parts) > 1 else ""

    if action == "stop":
        s = db["sessions"].get(value)
        if not s or (s["owner"] != uid and uid not in ADMIN_IDS):
            await q.answer("⛔ غير مصرح!", show_alert=True); return
        kill_process(s["pid"])
        Path(s["path"]).unlink(missing_ok=True)
        del db["sessions"][value]
        save_db()
        await q.message.edit_text(f"🛑 تم إيقاف البوت <code>{value}</code>", parse_mode=ParseMode.HTML)

    elif action == "restart":
        s = db["sessions"].get(value)
        if not s or (s["owner"] != uid and uid not in ADMIN_IDS):
            await q.answer("⛔ غير مصرح!", show_alert=True); return
        kill_process(s["pid"])
        try:
            proc = subprocess.Popen(
                [sys.executable, s["path"]],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid if sys.platform != "win32" else None
            )
            s["pid"]        = proc.pid
            s["start_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            save_db()
            await q.answer("✅ تمت إعادة التشغيل!", show_alert=True)
        except Exception as e:
            await q.answer(f"❌ خطأ: {e}", show_alert=True)

    elif action == "info":
        s = db["sessions"].get(value)
        if not s:
            await q.answer("البوت غير موجود!", show_alert=True); return
        try:
            os.kill(s["pid"], 0)
            status = "🟢 يعمل"
        except:
            status = "🔴 متوقف"
        await q.answer(
            f"📄 {s['name']}\n{status}\n⏰ بدأ: {s['start_time']}\n🕐 ينتهي: {s.get('expires','؟')}",
            show_alert=True
        )

    elif action == "buy":
        pkg = PACKAGES.get(value)
        if not pkg:
            await q.answer("❌ باقة غير موجودة!", show_alert=True); return
        if get_package(uid) == value:
            await q.answer("✅ أنت على هذه الباقة بالفعل!", show_alert=True); return
        if pkg["points_cost"] == 0 and pkg["stars_cost"] == 0:
            get_user(uid)["package"] = value; save_db()
            await q.message.edit_text(f"✅ تم التحويل إلى {pkg['name']}!"); return
        user = get_user(uid)
        if pkg["points_cost"] > 0 and user.get("points", 0) >= pkg["points_cost"]:
            user["points"] -= pkg["points_cost"]; user["package"] = value; save_db()
            await q.message.edit_text(f"✅ تمت الترقية إلى {pkg['name']}!\nخُصم {pkg['points_cost']} نقطة 🪙")
        elif pkg["stars_cost"] > 0 and user.get("stars", 0) >= pkg["stars_cost"]:
            user["stars"] -= pkg["stars_cost"]; user["package"] = value; save_db()
            await q.message.edit_text(f"✅ تمت الترقية إلى {pkg['name']}!\nخُصم {pkg['stars_cost']} Stars ⭐")
        else:
            await q.answer(
                f"❌ رصيدك غير كافٍ!\nتحتاج {pkg['points_cost']} نقطة أو {pkg['stars_cost']} Stars",
                show_alert=True
            )

    elif action == "approve":
        if uid not in ADMIN_IDS:
            await q.answer("⛔ غير مصرح!", show_alert=True); return
        pending = db["pending"].get(value)
        if not pending:
            await q.answer("⚠️ الطلب غير موجود أو عولج مسبقاً!", show_alert=True); return
        ok = await _deploy_bot(ctx, pending["owner"], value)
        if ok:
            try:
                await q.message.edit_caption(
                    (q.message.caption or "") + f"\n\n✅ <b>وافق عليه الأدمن</b> {q.from_user.first_name}",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
            await q.answer("✅ تمت الموافقة والتشغيل!", show_alert=True)
        else:
            await q.answer("❌ فشل التشغيل! راجع السجلات.", show_alert=True)

    elif action == "reject":
        if uid not in ADMIN_IDS:
            await q.answer("⛔ غير مصرح!", show_alert=True); return
        pending = db["pending"].get(value)
        if not pending:
            await q.answer("⚠️ الطلب غير موجود أو عولج مسبقاً!", show_alert=True); return
        ctx.user_data["adm_action"]       = "reject_reason"
        ctx.user_data["reject_pending_id"] = value
        await q.message.reply_text(
            f"📝 اكتب سبب رفض طلب <code>{value}</code>:",
            parse_mode=ParseMode.HTML
        )

    elif action == "adm" and uid in ADMIN_IDS:
        prompts = {
            "ban":        "ارسل: <code>الآيدي [السبب]</code>",
            "unban":      "أرسل آيدي المستخدم:",
            "give_pts":   "أرسل: <code>الآيدي الكمية</code>",
            "give_stars": "أرسل: <code>الآيدي الكمية</code>",
            "coupon":     "أرسل:\n<code>الكود النوع(points/stars) الكمية الاستخدامات</code>\nمثال: <code>PROMO50 points 50 100</code>",
            "broadcast":  "أرسل نص الرسالة للبث:",
            "upgrade":    "أرسل: <code>الآيدي اسم_الباقة</code>\n(basic/pro/vip/ultra)",
        }
        if value in prompts:
            ctx.user_data["adm_action"] = value
            await q.message.reply_text(prompts[value], parse_mode=ParseMode.HTML)

        elif value == "stats":
            total_banned = sum(1 for u in db["users"].values() if u.get("banned"))
            pkgs_count   = {}
            for u in db["users"].values():
                p = u.get("package", "basic")
                pkgs_count[p] = pkgs_count.get(p, 0) + 1
            pkg_txt = "\n".join(
                f"  {PACKAGES[k]['name']}: {v}" for k, v in pkgs_count.items() if k in PACKAGES
            )
            await q.message.reply_text(
                f"<b>📊 إحصائيات النظام</b>\n\n"
                f"👥 المستخدمون: <b>{db['stats']['total_users']}</b>\n"
                f"🚀 Deployments: <b>{db['stats']['total_deploys']}</b>\n"
                f"🤖 البوتات النشطة: <b>{len(db['sessions'])}</b>\n"
                f"⏳ طلبات معلقة: <b>{len(db.get('pending',{}))}</b>\n"
                f"🚫 محظورون: <b>{total_banned}</b>\n"
                f"🪙 نقاط معطاة: <b>{db['stats']['total_points_given']}</b>\n\n"
                f"📦 الباقات:\n{pkg_txt}",
                parse_mode=ParseMode.HTML
            )

        elif value == "all_bots":
            if not db["sessions"]:
                await q.message.reply_text("📭 لا يوجد بوتات نشطة."); return
            txt = "<b>🤖 البوتات النشطة:</b>\n\n"
            for sid, s in list(db["sessions"].items())[:20]:
                txt += f"• <code>{sid}</code> | {s['owner']} | {s['name']}\n"
            if len(db["sessions"]) > 20:
                txt += f"\n... و{len(db['sessions'])-20} آخرون"
            await q.message.reply_text(txt, parse_mode=ParseMode.HTML)

        elif value == "pending":
            items = db.get("pending", {})
            if not items:
                await q.message.reply_text("⏳ لا يوجد طلبات معلقة."); return
            txt = f"<b>⏳ الطلبات المعلقة ({len(items)}):</b>\n\n"
            for pid, p in list(items.items())[:10]:
                txt += f"• <code>{pid}</code> | {p['owner']} | {p['name']} | {p['request_time']}\n"
            await q.message.reply_text(txt, parse_mode=ParseMode.HTML)

# ─── /buystars ────────────────────────────────────────────────────────────────
async def cmd_buy_stars(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_banned(uid):
        return
    try:
        await ctx.bot.send_invoice(
            chat_id=uid,
            title="شحن 50 Stars ⭐",
            description="شحن 50 Stars لاستخدامها في الاستضافة",
            payload="stars_50",
            currency="XTR",
            prices=[LabeledPrice("50 Stars", 50)],
            provider_token=""
        )
    except Exception as e:
        log.error(f"send_invoice: {e}")
        await update.message.reply_text(
            f"❌ خطأ في إنشاء الفاتورة.\n"
            f"تأكد أن البوت مفعّل للدفع عبر @BotFather\n\n<code>{e}</code>",
            parse_mode=ParseMode.HTML
        )

async def pre_checkout(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message.successful_payment.invoice_payload == "stars_50":
        user = get_user(uid)
        user["stars"] = user.get("stars", 0) + 50
        save_db()
        await update.message.reply_text(
            f"✅ تم شحن 50 Stars!\nرصيدك: <b>{user['stars']} Stars</b> ⭐",
            parse_mode=ParseMode.HTML
        )

async def error_handler(update, context):
    log.error(f"خطأ: {context.error}", exc_info=context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("⚠️ حدث خطأ، حاول مجدداً.")
    except:
        pass

# ─── التشغيل الرئيسي ──────────────────────────────────────────────────────────
async def main():
    init_mongo()
    load_db()
    if not TOKEN:
        log.error("BOT_TOKEN غير موجود!")
        return

    # بناء التطبيق بدون JobQueue (سيتم التعامل مع التنظيف يدوياً)
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()

    # إضافة جميع المعالجات
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("admin",    cmd_admin))
    app.add_handler(CommandHandler("apanel",   cmd_admin))
    app.add_handler(CommandHandler("buystars", cmd_buy_stars))
    app.add_handler(MessageHandler(filters.Document.ALL,                 handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,      handle_text))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT,           successful_payment))
    app.add_error_handler(error_handler)

    # تشغيل مهمة التنظيف الخلفية (بدلاً من JobQueue)
    asyncio.create_task(cleanup_loop(app))

    log.info("🚀 CloudX Bot v4.3 يعمل مع مهمة تنظيف خلفية!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    # الانتظار حتى يتم إيقاف البوت (استخدام Event Loop)
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
