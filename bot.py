# bot.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, MessageHandler, filters, CommandHandler, ContextTypes, CallbackQueryHandler
from db import (
    init_db, get_or_create_user, get_rank,
    add_score, get_top_users, get_user_rank,
    list_tournaments
)
from config import BOT_TOKEN, ADMINS
from db import session, Tournament, User
from datetime import datetime
from langs import messages
import random
import string

init_db()

def generate_custom_id(length=6):
    while True:
        cid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        exists = session.query(User).filter_by(custom_id=cid).first()
        if not exists:
            return cid

def get_or_create_user(tg_id, username):
    user = session.query(User).filter_by(tg_id=tg_id).first()
    if not user:
        custom_id = generate_custom_id()
        user = User(tg_id=tg_id, username=username, custom_id=custom_id)
        session.add(user)
        session.commit()
    return user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    user = session.query(User).filter_by(tg_id=tg_id).first()

    if user:
        lang = user.language
        await update.message.reply_text(messages[lang]["registered"])
        return

    buttons = [
        [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang|uz")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="lang|ru")]
    ]
    await update.message.reply_text(
        "🌐 Tilni tanlang / Выберите язык:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("lang|"):
        lang = query.data.split("|")[1]
        context.user_data["register"] = True
        context.user_data["lang"] = lang
        await query.message.reply_text(messages[lang]["enter_name"])

async def handle_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("register"):
        return

    lang = context.user_data.get("lang", "uz")
    text = update.message.text.strip()

    if "fullname" not in context.user_data:
        context.user_data["fullname"] = text
        await update.message.reply_text(messages[lang]["enter_nick"])
        return

    nickname = text
    fullname = context.user_data["fullname"]
    tg_id = update.effective_user.id
    username = update.effective_user.username

    custom_id = generate_custom_id()

    new_user = User(
        tg_id=tg_id,
        username=username,
        fullname=fullname,
        nickname=nickname,
        custom_id=custom_id,
        language=lang
    )
    session.add(new_user)
    session.commit()
    context.user_data.clear()

    await update.message.reply_text(
        f"{messages[lang]['registered']}\n\n"
        f"{messages[lang]['your_id']}: `{custom_id}`\n"
        f"{messages[lang]['your_name']}: {fullname}\n"
        f"{messages[lang]['your_nick']}: {nickname}",
        parse_mode="Markdown"
    )

async def instruction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    lang = user.language if user and user.language in messages else "uz"
    await update.message.reply_text(messages[lang]["instruction_text"])

async def set_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return await update.message.reply_text("\u26d4\ufe0f Sizda ruxsat yo\u2018q.")

    if len(context.args) != 1 or context.args[0] not in ["uz", "ru"]:
        return await update.message.reply_text("\u26a0\ufe0f Format: /set_instruction uz yoki /set_instruction ru")

    context.user_data["set_inst_lang"] = context.args[0]
    await update.message.reply_text("📨 Endi matnni yuboring (forward ham mumkin, premium emoji qo\u043b\u043b\u0430\u0431-quvvatlanadi)")

async def instruction_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("set_inst_lang|"):
        lang = query.data.split("|")[1]
        context.user_data["set_inst_lang"] = lang
        await query.message.reply_text("📨 Endi ushbu til uchun instruktsiyani yuboring.\nPremium emojilarni saqlash uchun forward ham mumkin.")

async def handle_instruction_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "set_inst_lang" not in context.user_data:
        return  # boshqa handlerlarga o'tsin

    lang = context.user_data.pop("set_inst_lang")

    # Forward / text / caption ni olish
    msg = update.message
    text = msg.text or msg.caption

    if not text:
        return await update.message.reply_text("⚠️ Matn topilmadi. Forward qilingan yoki oddiy xabar yuboring.")

    messages[lang]["instruction_text"] = text
    await update.message.reply_text(f"✅ `{lang.upper()}` tilidagi instruktsiya saqlandi.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    lang = user.language or "uz"
    rank = get_rank(user.score)

    msg = (
        f"{messages[lang]['profile']}:\n"
        f"{messages[lang]['your_id']}: `{user.custom_id}`\n"
        f"{messages[lang]['your_name']}: {user.fullname or '❌'}\n"
        f"{messages[lang]['your_nick']}: {user.nickname or '❌'}\n"
        f"{messages[lang]['your_score']}: {user.score}\n"
        f"{messages[lang]['your_rank']}: {rank}\n"
        f"{messages[lang]['your_turnirs']}: {user.tournaments_played}"
    )

    buttons = [
        [InlineKeyboardButton(messages[lang]["change_name"], callback_data="edit_name")],
        [InlineKeyboardButton(messages[lang]["change_lang"], callback_data="change_lang")]
    ]

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def admin_add_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔️ Sizda ruxsat yo‘q.")
        return

    try:
        # Join args and split by '|'
        args = " ".join(context.args).split("|")
        if len(args) != 5:
            raise ValueError

        name = args[0].strip()
        final_teams = args[1].strip()
        score_summary = args[2].strip()
        date_str = args[3].strip()
        mvp_custom_id = args[4].strip()

        mvp_user = session.query(User).filter_by(custom_id=mvp_custom_id).first()
        if not mvp_user:
            await update.message.reply_text("❌ MVP foydalanuvchisi topilmadi.")
            return

        date_obj = datetime.strptime(date_str, "%Y-%m-%d")

        tournament = Tournament(
            name=name,
            final_teams=final_teams,
            score_summary=score_summary,
            date=date_obj,
            mvp_user_id=mvp_user.id
        )
        session.add(tournament)
        mvp_user.tournaments_played += 1
        session.commit()

        await update.message.reply_text(f"✅ Turnir '{name}' qo‘shildi.")
    except Exception as e:
        await update.message.reply_text(
            "⚠️ Format: /admin_add_tournament <nomi> | <final jamoalar> | <hisob> | <yyyy-mm-dd> | <mvp_custom_id>\n"
            "Example:\n"
            "/admin_add_tournament Super Cup | Red vs Blue | 4-2 | 2025-06-10 | user001"
        )

async def admin_edit_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return await update.message.reply_text("⛔️ Ruxsat yo‘q.")
    try:
        custom_id = context.args[0]
        user = session.query(User).filter_by(custom_id=custom_id).first()
        if not user:
            return await update.message.reply_text("❌ Foydalanuvchi topilmadi.")

        buttons = [
            [
                InlineKeyboardButton("➕ 10 ball", callback_data=f"addscore|{custom_id}|10"),
                InlineKeyboardButton("➕ 50 ball", callback_data=f"addscore|{custom_id}|50"),
                InlineKeyboardButton("➕ 100 ball", callback_data=f"addscore|{custom_id}|100"),
            ],
            [
                InlineKeyboardButton("✏️ Ismini o‘zgartirish", callback_data=f"admineditname|{custom_id}")
            ]
        ]

        await update.message.reply_text(
            f"👨‍💼 Foydalanuvchi: @{user.username or '-'}\n🆔 {custom_id}\nBall: {user.score}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except:
        await update.message.reply_text("❗ Format: /admin_edit_user <custom_id>")

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("addscore|"):
        _, custom_id, amount = query.data.split("|")
        user = add_score(custom_id, int(amount))
        if user:
            await query.message.reply_text(f"✅ {user.fullname or user.username} ga {amount} ball qo‘shildi. Yangi: {user.score}")
    
    elif query.data.startswith("admineditname|"):
        _, custom_id = query.data.split("|")
        context.user_data["admin_edit_name"] = custom_id
        await query.message.reply_text("✏️ Yangi ismni yuboring (admin mode):")

async def handle_admin_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    custom_id = context.user_data.get("admin_edit_name")
    if custom_id:
        user = session.query(User).filter_by(custom_id=custom_id).first()
        if user:
            user.fullname = update.message.text.strip()
            session.commit()
            context.user_data["admin_edit_name"] = None
            await update.message.reply_text(f"✅ Admin tomonidan ism o‘zgartirildi: {user.fullname}")


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    top_users = get_top_users()
    response = "🏅 Reyting Top 5:\n\n"
    for i, user in enumerate(top_users, start=1):
        rank = get_rank(user.score)
        response += f"{i}. @{user.username or 'no_name'} - {rank} ({user.score})\n"
    user_rank = get_user_rank(current_user)
    response += f"\n📌 Sizning o‘rningiz: #{user_rank} ({current_user.score} ball)"
    await update.message.reply_text(response)

async def tournaments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t_list = list_tournaments()
    if not t_list:
        await update.message.reply_text("⛔️ Hozircha turnirlar yo‘q.")
        return

    msg = "📜 Oldingi Turnirlar:\n\n"
    for t in t_list:
        msg += (
            f"🏷 {t.name} | 📅 {t.date.date()}\n"
            f"⚔️ {t.final_teams} | 🔢 {t.score_summary}\n"
            f"🥇 MVP: @{t.mvp.username if t.mvp else 'Noma’lum'}\n\n"
        )
    await update.message.reply_text(msg)


async def admin_add_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔️ Sizda ruxsat yo‘q.")
        return
    try:
        custom_id, score = context.args[0], int(context.args[1])
        user = add_score(custom_id, score)
        if user:
            await update.message.reply_text(f"✅ {user.username} foydalanuvchisiga {score} ball qo‘shildi!")
        else:
            await update.message.reply_text("❌ Foydalanuvchi topilmadi.")
    except Exception as e:
        await update.message.reply_text("⚠️ Format: /admin_add_score <custom_id> <ball>")

async def admin_take_bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔️ Sizda ruxsat yo‘q.")
        return
    try:
        custom_id, score = context.args[0], int(context.args[1])
        user = session.query(User).filter_by(custom_id=custom_id).first()
        if not user:
            return await update.message.reply_text("❌ Foydalanuvchi topilmadi.")

        user.score = max(0, user.score - score)
        session.commit()
        await update.message.reply_text(f"✅ {user.username} dan {score} ball olib tashlandi. Yangi ball: {user.score}")
    except:
        await update.message.reply_text("⚠️ Format: /admin_take_bal <custom_id> <ball>")

async def admin_reset_bal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        await update.message.reply_text("⛔️ Sizda ruxsat yo‘q.")
        return
    try:
        custom_id = context.args[0]
        user = session.query(User).filter_by(custom_id=custom_id).first()
        if not user:
            return await update.message.reply_text("❌ Foydalanuvchi topilmadi.")

        user.score = 0
        session.commit()
        await update.message.reply_text(f"♻️ {user.username} ballari tozalandi.")
    except:
        await update.message.reply_text("⚠️ Format: /admin_reset_bal <custom_id>")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = get_or_create_user(query.from_user.id, query.from_user.username)
    lang = user.language

    await query.answer()

    if query.data == "edit_name":
        context.user_data["edit_name"] = True
        await query.message.reply_text(messages[lang]["change_name"])
    elif query.data == "change_lang":
        btns = [
            [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="set_lang|uz")],
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="set_lang|ru")]
        ]
        await query.message.reply_text(messages[lang]["select_lang"], reply_markup=InlineKeyboardMarkup(btns))
    elif query.data.startswith("set_lang|"):
        new_lang = query.data.split("|")[1]
        user.language = new_lang
        session.commit()
        await query.message.reply_text("✅ Til o‘zgartirildi!")

async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("edit_name"):
        new_name = update.message.text.strip()
        user = get_or_create_user(update.effective_user.id, update.effective_user.username)
        user.fullname = new_name
        session.commit()
        context.user_data["edit_name"] = False
        await update.message.reply_text(f"✅ Ismingiz yangilandi: {new_name}")

async def instruction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    lang = user.language if user.language in messages else "uz"
    await update.message.reply_text(messages[lang]["instruction_text"])

async def handle_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id, update.effective_user.username)
    text = update.message.text or update.message.caption

    if context.user_data.get("set_inst_lang"):
        lang = context.user_data.pop("set_inst_lang")
        messages[lang]["instruction_text"] = text
        return await update.message.reply_text(f"\u2705 `{lang}` tilidagi instruktsiya saqlandi.", parse_mode="Markdown")

    if context.user_data.get("edit_name"):
        user.fullname = text
        session.commit()
        context.user_data["edit_name"] = False
        return await update.message.reply_text(f"\u2705 Ismingiz yangilandi: {text}")

    if context.user_data.get("admin_edit_name"):
        custom_id = context.user_data.pop("admin_edit_name")
        u = session.query(User).filter_by(custom_id=custom_id).first()
        if u:
            u.fullname = text
            session.commit()
            return await update.message.reply_text(f"\u2705 Admin tomonidan ism o\u2018zgartirildi: {text}")

    if context.user_data.get("register"):
        lang = context.user_data.get("lang", "uz")
        if "fullname" not in context.user_data:
            context.user_data["fullname"] = text
            return await update.message.reply_text(messages[lang]["enter_nick"])
        nickname = text
        fullname = context.user_data["fullname"]
        custom_id = generate_custom_id()
        new_user = User(
            tg_id=update.effective_user.id,
            username=update.effective_user.username,
            fullname=fullname,
            nickname=nickname,
            custom_id=custom_id,
            language=lang
        )
        session.add(new_user)
        session.commit()
        context.user_data.clear()
        return await update.message.reply_text(
            f"{messages[lang]['registered']}\n\n"
            f"{messages[lang]['your_id']}: `{custom_id}`\n"
            f"{messages[lang]['your_name']}: {fullname}\n"
            f"{messages[lang]['your_nick']}: {nickname}",
            parse_mode="Markdown"
        )
async def set_menu_commands(app):
    await app.bot.set_my_commands(
        commands=[
            BotCommand("start", "🔄 Botni ishga tushirish"), 
            BotCommand("profile", "👤 Profil"),
            BotCommand("instruction", "📘 Qo'llanma"), 
            BotCommand("top", "🏅 Reyting"),
            BotCommand("tournaments", "🏆 Turnirlar"),
            BotCommand("admin_add_score", "🛡 Ball qo'shish"),
            BotCommand("admin_edit_user", "🛡 Foydalanuvchi sozlamalari"),
            BotCommand("admin_add_tournament", "🛡 Turnir qo'shish"),
            BotCommand("admin_take_bal", "🛡 Ball olish"),
            BotCommand("admin_reset_bal", "🛡 Ballni 0 qilish"),
        ],
        language_code='uz'
    )
    
    await app.bot.set_my_commands(
        commands=[
            BotCommand("start", "🔄 Запустить бота"),
            BotCommand("profile", "👤 Профиль"),
            BotCommand("instruction", "📘 Руководство"),
            BotCommand("top", "🏅 Рейтинг"),
            BotCommand("tournaments", "🏆 Турниры"),
            BotCommand("admin_add_score", "🛡 Добавить баллы"),
            BotCommand("admin_edit_user", "🛡 Настройки пользователя"),
            BotCommand("admin_add_tournament", "🛡 Добавить турнир"),
            BotCommand("admin_take_bal", "🛡 Отнять баллы"),
            BotCommand("admin_reset_bal", "🛡 Сбросить баллы"),
        ],
        language_code='ru'
    )

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("instruction", instruction_command))
    app.add_handler(CommandHandler("set_instruction", set_instruction))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang\\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("instruction", instruction_command))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("admin_add_tournament", admin_add_tournament))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("tournaments", tournaments))
    app.add_handler(CommandHandler("admin_add_score", admin_add_score))
    app.add_handler(CommandHandler("admin_edit_user", admin_edit_user))
    app.add_handler(CommandHandler("admin_take_bal", admin_take_bal))
    app.add_handler(CommandHandler("admin_reset_bal", admin_reset_bal))
    app.add_handler(CallbackQueryHandler(lang_callback, pattern="^lang\|"))
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^edit_name$|^change_lang$|^set_lang\|"))
    app.add_handler(CallbackQueryHandler(admin_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_registration))
    app.add_handler(MessageHandler(filters.TEXT & filters.USER, handle_name_input))
    app.add_handler(MessageHandler(filters.TEXT & filters.USER, handle_admin_name_input))
    app.post_init = set_menu_commands
    app.run_polling()
