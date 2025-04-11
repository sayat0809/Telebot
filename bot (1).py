from telegram.constants import ChatMemberStatus
from telegram import (
    Update,
    ChatPermissions,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    CallbackContext,
    ConversationHandler
)
from dotenv import load_dotenv
import os
import time
import hashlib
import random
import re
import asyncio
from datetime import datetime, timedelta
import telegram

# Словарь для хранения мутов и баланса пользователей
muted_users = {}  # {user_id: timestamp}
user_balances = {}  # {user_id: coins}

# Хранение времени последнего перевода
last_transfer_time = {}
# Хранение суммы переведенных монет за последние 12 часов
transferred_amount = {}
# Хранение времени последнего получения бонуса
last_bonus_time = {}

# Хранение рефералов (ключ — ID реферала, значение — ID пригласившего)
user_referrals = {}

# Хранение списка рефералов для каждого пользователя
user_invites = {}

load_dotenv

# Хранение реферальных связей
user_referrals = {}  # {ref_code: inviter_id}
user_invites = {}  # {inviter_id: [user_id1, user_id2, ...]}

ADMIN_ID = 8161445285

# Словарь для хранения запретов
block_list = {}

unlimited_users = set()     # Пользователи без лимитов
admin_id = 8161445285       # ID администратора

user_bets = {}
user_can_bet = set()
user_spinning = set()
user_bet_messages = {}
group_roulette_log = {}
private_roulette_log = {}
active_group_roulette = {}
rules_message_id = {}

TOP_UP_LINK = "https://t.me/Royalsbaatlle"
DELAY_BEFORE_SPIN = [3, 5]
GIF_DURATION = 5
RESULT_DELAY = 2
MIN_BET = 1000
ROULETTE_GIFS = [
    "https://i.gifer.com/77rN.gif",
    "https://i.gifer.com/8Emn.gif"]

# Настройки игры
SYMBOLS = {"💎": 2, "♥️": 10, "♠️": 10, "🀄️": 10}
WIN_MULTIPLIERS = {"💎": (5, 10), "♥️": (3, 4), "♠️": (3, 4), "🀄️": (4, 5)}

# Глобальные переменные
cooldowns = {}  # {chat_id: end_time}
active_games = set()  # Активные чаты

# Проверка подписки на канал
async def check_subscription(user_id: int,
                             context: ContextTypes.DEFAULT_TYPE) -> bool:
    CHANNEL_ID = "@CrystalDnewss"  # Замените на ваш канал
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"Ошибка при проверке подписки: {e}")
        return False


# Обработка команды /start с рефералами и кнопками


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args

    # Начальный баланс, если пользователь новый
    if user_id not in user_/balances:
        user_balances[user_id] = 5000

    # Проверяем реферальную ссылку
    if args and args[0].startswith("ref_"):
        ref_code = args[0][4:]  # Убираем "ref_"
        inviter_id = user_referrals.get(ref_code)

        if inviter_id and inviter_id != user_id:
            user_invites.setdefault(inviter_id, []).append(user_id)
            inviter_name = await get_username(inviter_id, context)

            await update.message.reply_text(
                f"Вы перешли по реферальной ссылке {inviter_name}.\n\n"
                f"Теперь {inviter_name} будет получать кэшбек 10% "
                f"с любой вашей покупки монет от 200K донат."
            )
        else:
            await update.message.reply_text("Реферальный код недействителен.")

    # Сообщение приветствия и клавиатура
    welcome_message = (
        "Добро пожаловать в @CrystalDnobot\n"
        "Рады видеть вас здесь. Наслаждайтесь игрой, весельем и новыми возможностями.\n\n")

    keyboard = [
        [KeyboardButton("📋Профиль"), KeyboardButton("🔗Рефералы")],
        [KeyboardButton("🌐Ссылки"), KeyboardButton("🛒Магазин")],
        [
            KeyboardButton("🎭Стикеры"),
            KeyboardButton("🎁Промокоды"),
            KeyboardButton("💳Донат"),
        ],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(welcome_message, reply_markup=reply_markup)


async def transfer_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id not in user_balances:
        user_balances[user_id] = 5000  # Начальный баланс, если пользователь новый

    if user_id not in last_transfer_time:
        last_transfer_time[user_id] = 0

    if user_id not in transferred_amount:
        transferred_amount[user_id] = 0

    if text.startswith("+"):
        try:
            amount = int(text[1:])
            if amount <= 0:
                await update.message.reply_text("Сумма должна быть больше 0.")
                return

            target_user = None
            if update.message.reply_to_message:
                target_user = update.message.reply_to_message.from_user.id
                if target_user == user_id or target_user == context.bot.id:
                    await update.message.reply_text("Гениально, но нет.")
                    return

            current_time = time.time()
            
            # Только для пользователей с лимитами
            if user_id not in unlimited_users:
                # Проверка задержки между переводами (старое сообщение)
                time_since_last_transfer = current_time - last_transfer_time[user_id]
                if time_since_last_transfer < 59:
                    remaining_time = int(59 - time_since_last_transfer)
                    minutes = remaining_time // 60
                    seconds = remaining_time % 60
                    await update.message.reply_text(f"Вы не можете переводить монеты ещё {minutes:02}:{seconds:02}")
                    return

                # Автоматический сброс лимита через 12 часов
                if time_since_last_transfer >= 12 * 3600:
                    transferred_amount[user_id] = 0

                # Проверка лимита (старое сообщение)
                if transferred_amount[user_id] + amount > 10000:
                    remaining_limit = 10000 - transferred_amount[user_id]
                    keyboard = [[InlineKeyboardButton("Снять лимит", url="https://t.me/CrystalDnewss")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(
                        f"Лимит на передачу 10000 монет за 12 часов. Вы можете передать ещё: {remaining_limit}🪙",
                        reply_markup=reply_markup,
                    )
                    return

            # Проверка баланса (без изменений)
            if user_balances[user_id] < amount:
                await update.message.reply_text("Недостаточно монет для перевода.")
                return

            # Инициализация баланса для получателя (без изменений)
            if target_user not in user_balances:
                user_balances[target_user] = 5000  # Начальный баланс

            # Перевод монет (без изменений)
            user_balances[user_id] -= amount
            user_balances[target_user] += amount

            # Обновление статистики только для пользователей с лимитами
            if user_id not in unlimited_users:
                last_transfer_time[user_id] = current_time
                transferred_amount[user_id] += amount

            # Сообщение о переводе (без изменений)
            user_name = update.message.from_user.first_name
            target_name = update.message.reply_to_message.from_user.first_name
            user_link = f"[{user_name}](tg://user?id={user_id})"
            target_link = f"[{target_name}](tg://user?id={target_user})"

            await update.message.reply_text(
                f"{user_link} перевёл {amount}🪙 пользователю {target_link}",
                parse_mode="Markdown",
            )

        except ValueError:
            await update.message.reply_text("Некорректная сумма.")

# Обработка рефералов

async def crystal_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды снятия лимитов"""
    if update.message.from_user.id != admin_id:
        return  # Игнорируем других пользователей
    
    if update.message.chat.type != "private":
        await update.message.reply_text("ℹ️ Эта команда работает только в личном чате с ботом.")
        return
    
    context.user_data['awaiting_user_id'] = True
    await update.message.reply_text("Введите ID пользователя, которому нужно снять лимиты:")

async def handle_user_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ввода ID пользователя"""
    if not context.user_data.get('awaiting_user_id'):
        return
    
    if update.message.from_user.id != admin_id:
        return
    
    try:
        target_id = int(update.message.text.strip())
        
        # Проверяем, не сняты ли уже лимиты у этого пользователя
        if target_id in unlimited_users:
            await update.message.reply_text(
                f"ℹ️ У пользователя {target_id} уже сняты лимиты.\n"
                "Повторное снятие не требуется."
            )
            context.user_data['awaiting_user_id'] = False
            return
            
        unlimited_users.add(target_id)
        context.user_data['awaiting_user_id'] = False
        
        # Уведомление администратора
        await update.message.reply_text(f"✅ Лимиты для пользователя {target_id} успешно сняты!")
        
        # Попытка уведомить пользователя
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="Вам сняли ограничения на переводы!\n\n"
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {target_id}: {e}")
            await update.message.reply_text(
                f"⚠️ Лимиты сняты, но не удалось уведомить пользователя {target_id}.\n"
                "Возможно, он не запускал бота или заблокировал его."
            )
            
    except ValueError:
        await update.message.reply_text("❌ Ошибка! Введите корректный ID пользователя (только цифры).")

async def referrals_handler(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    # Получаем список рефералов пользователя
    invited_users = user_invites.get(user_id, [])

    # Формируем сообщение
    message = "Ваши рефералы:\n\n/referal — команда для получения ссылки\n\n"

    if invited_users:
        # Добавляем список рефералов
        referral_list = "\n".join(
            [
                f"{i + 1}. {await get_username(uid, context)}"
                for i, uid in enumerate(invited_users)
            ]
        )
        message += referral_list
    else:
        # Если рефералов нет
        message += "У вас пока нет рефералов."

    # Отправляем сообщение
    await update.message.reply_text(
        message, parse_mode="Markdown", disable_web_page_preview=True
    )


def get_random_symbols():
    """Генерирует случайные символы для игры."""
    return random.choices(list(SYMBOLS.keys()), weights=SYMBOLS.values(), k=4)


async def play_bandit(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Проверка таймера (раздельно для каждого чата и пользователя)
    key = (chat_id, user_id)
    if key in cooldowns and datetime.now() < cooldowns[key]:
        remaining = (cooldowns[key] - datetime.now()).seconds
        await update.message.reply_text(f"")
        return

    # Устанавливаем таймер 12 секунд для этого чата и пользователя
    cooldowns[key] = datetime.now() + timedelta(seconds=12)

    # Парсинг ставки
    try:
        bet = int(context.matches[0].group(
            1)) if context.matches and context.matches[0].group(1) else 1000
    except BaseException:
        bet = 1000

    # Запускаем игру в отдельной задаче (чтобы не блокировать другие команды)
    asyncio.create_task(spin_slots(update, context, chat_id, user_id, bet))


    await msg.edit_text(result_text, parse_mode="Markdown")

async def spin_slots(update: Update, context: CallbackContext, chat_id, user_id, bet):
    """Логика игры с анимацией."""
    user = update.effective_user

    # Получаем баланс пользователя, если его нет — даем 5000 монет
    user_balance = user_balances.get(user_id, 5000)

    # Проверка баланса
    if bet > user_balance:
        await context.bot.send_message(chat_id, f"[{user.first_name}](tg://user?id={user_id}), недостаточно монет!", parse_mode="Markdown")
        return

    # Списание ставки
    user_balances[user_id] = user_balance - bet

    # Генерация символов
    symbols = get_random_symbols()

    # Создание кликабельного имени
    user_link = f"[{user.first_name}](tg://user?id={user_id})"

    # Отправка начального сообщения с анимацией
    msg = await context.bot.send_message(chat_id, f"{user_link}\n\n🌫|🌫|🌫|🌫", parse_mode="Markdown")

    for i in range(4):
        await asyncio.sleep(2.5)  # Пауза между вращениями
        display = "|".join(symbols[:i + 1] + ["🌫"] * (3 - i))
        await msg.edit_text(f"{user_link}\n\n{display}", parse_mode="Markdown")

    # Расчет выигрыша
    winnings = 0
    for symbol, (x3, x4) in WIN_MULTIPLIERS.items():
        count = symbols.count(symbol)
        if count == 4:
            winnings = bet * x4
        elif count == 3:
            winnings = bet * x3  # Теперь учитываем 3 одинаковых символа!

    # Обновление баланса
    user_balances[user_id] += winnings

    # Итоговое сообщение
    result_text = f"{user_link}\n\n"  # Имя пользователя с отступом
    result_text += f"{'|'.join(symbols)}\n\n"  # Символы с отступом
    result_text += f"Выигрыш {winnings} 🪙" if winnings else f"Проигрыш {bet} 🪙"

    await msg.edit_text(result_text, parse_mode="Markdown")

async def balance(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    balance = user_balances.get(user_id, 100000)
    user_name = update.message.from_user.first_name

    bet_info = user_bets.get((user_id, chat_id), {})
    total_bet = sum(bet_info.values())
    bet_text = f" +{total_bet}" if total_bet > 0 else ""

    message = f"{user_name}\nМонеты: {balance}{bet_text}"

    if balance == 0:
        keyboard = [[InlineKeyboardButton(" Бонус", callback_data="bonus_request")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message)
# Обработка нажатия на кнопку "Бонус"


async def handle_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_name = query.from_user.first_name

    # Проверка времени последнего бонуса
    if user_id in last_bonus_time:
        current_time = time.time()
        time_since_last_bonus = current_time - last_bonus_time[user_id]

        current_time = time.time()
        time_since_last_bonus = current_time - last_bonus_time[user_id]
        if time_since_last_bonus < 11 * 3600:  # 11 часов
            remaining_time = int(11 * 3600 - time_since_last_bonus)
            hours = remaining_time // 3600
            minutes = (remaining_time % 3600) // 60
            await query.edit_message_text(
                f"Вы сможете получить бонус через {hours}ч {minutes}м"
            )
            return

    # Проверка подписки на канал
    if not await check_subscription(user_id, context):
        keyboard = [[InlineKeyboardButton(
            "Получить бонус", callback_data="get_bonus")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Вы должны быть подписаны на новостной канал @CrystalDnewss",
            reply_markup=reply_markup,
        )
        return

    # Выдача бонуса
    user_balances[user_id] += 2500
    last_bonus_time[user_id] = time.time()
    await query.edit_message_text("Вы получили бонус 2500 монет")


# Обработка нажатия на кнопку "Получить бонус"


async def get_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    # Проверка подписки на канал
    if not await check_subscription(user_id, context):
        await query.edit_message_text("Вы не подписали на канал @CrystalDnewss")
        return

    # Выдача бонуса
    user_balances[user_id] += 2500
    last_bonus_time[user_id] = time.time()
    await query.edit_message_text("Вы получили бонус 2500 монет")


# Обработка нажатия на кнопку профиля


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[1])
    user_name = context.bot.get_chat(user_id).first_name
    balance = user_balances.get(user_id, 5000)

    await query.edit_message_text(
        f"Профиль пользователя {user_name}\n\nМонеты: {balance}🪙"
    )





# Функция для получения имени пользователя


async def get_username(user_id, context):
    user = await context.bot.get_chat(user_id)
    return user.full_name if user.username is None else f"@{user.username}"


# Команда /referal — выдаёт реферальную ссылку


async def get_referral_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    ref_code = hashlib.md5(str(user_id).encode()).hexdigest()[
        :16
    ]  # Генерация реферального кода
    referral_link = f"https://t.me/CrystalGnoBot?start=ref_{ref_code}"

    # Сохраняем код
    user_referrals[ref_code] = user_id

    await update.message.reply_text(f"Ваша реферальная ссылка:\n{referral_link}")


# Обновленный /Crystal_Money с реферальным кэшбеком


async def crystal_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return

    await update.message.reply_text("✏️ Введите ID пользователя:")
    context.user_data["waiting_for_id"] = True


async def handle_user_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_for_id"):
        try:
            target_id = int(update.message.text)
            context.user_data["target_id"] = target_id
            context.user_data["waiting_for_id"] = False
            context.user_data["waiting_for_amount"] = True
            await update.message.reply_text("💰 Введите сумму для начисления:")
        except ValueError:
            await update.message.reply_text("❌ Некорректный ID. Введите число.")

    elif context.user_data.get("waiting_for_amount"):
        try:
            amount = int(update.message.text)
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть больше 0.")
                return

            target_id = context.user_data["target_id"]
            if target_id not in user_balances:
                user_balances[target_id] = 5000  # Начальный баланс

            # Начисление монет
            user_balances[target_id] += amount
            context.user_data["waiting_for_amount"] = False
            await update.message.reply_text("✅ Готово!")

            # Отправка сообщения пользователю
            message_text = (
                f"На ваш баланс зачислено {amount}🪙\n\n"
                "Поставь рекорд дня в @CrystalDnobot и забери приз! "
                "Докажи своё мастерство и стань лучшим."
            )

            photo_url = (
                "https://i.postimg.cc/zGpBX53X/file-8-Ai-ZPmh-MAo6v3-Xz-M79-Wu-HT.webp"
            )

            try:
                await context.bot.send_photo(
                    target_id, photo=photo_url, caption=message_text
                )
            except Exception as e:
                print(f"Ошибка отправки фото: {e}")
                await context.bot.send_message(target_id, text=message_text)

            # Проверка реферала и начисление кэшбэка
            for inviter_id, referrals in user_invites.items():
                if target_id in referrals and amount >= 200000:
                    cashback = int(amount * 0.10)  # 10% от суммы
                    user_balances[inviter_id] = (
                        user_balances.get(inviter_id, 5000) + cashback
                    )

                    inviter_name = await get_username(inviter_id, context)

                    cashback_message = (
                        f"На ваш баланс зачислено {cashback}🪙 за покупку монет вашим рефералом {await get_username(target_id, context)}\n\n"
                        "Установите рекорд дня в @CrystalDnobot и выиграйте приз! "
                        "Покажите мастерство, станьте чемпионом."
                    )

                    try:
                        await context.bot.send_photo(
                            inviter_id, photo=photo_url, caption=cashback_message
                        )
                    except Exception as e:
                        print(f"Ошибка отправки фото: {e}")
                        await context.bot.send_message(
                            inviter_id, text=cashback_message
                        )

        except ValueError:
            await update.message.reply_text("❌ Некорректная сумма. Введите число.")


# Функция для проверки, является ли пользователь админом или владельцем
async def is_user_admin(
    chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ["administrator", "creator"]
    except Exception as e:
        print(f"Ошибка при проверке прав администратора: {e}")
        return False


# Мут пользователя


async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    text = update.message.text

    # Проверяем, является ли пользователь админом или владельцем
    is_admin = await is_user_admin(chat_id, user_id, context)

    # Получаем цель мута
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
    else:
        return

    # Проверяем, пытается ли пользователь замутить бота
    if target_id == context.bot.id:
        return  # Игнорируем команду, если цель — бот

    # Проверяем, пытается ли обычный пользователь замутить админа
    if not is_admin and await is_user_admin(chat_id, target_id, context):
        return

    # Проверяем, уже ли пользователь в муте
    if target_id in muted_users and datetime.now() < muted_users[target_id]:
        target_link = f"[{target_user.first_name}](tg://user?id={target_id})"
        await update.message.reply_text(
            f"{target_link} уже в муте", parse_mode="Markdown"
        )
        return

    # Обрабатываем команду для обычных пользователей
    if not is_admin:
        # Проверяем баланс
        if user_balances.get(user_id, 0) < 300:
            await update.message.reply_text(" У вас недостаточно монет для мута.")
            return

        # Снимаем 300 монет
        user_balances[user_id] -= 300

        # Устанавливаем мут на 1 минуту
        mute_duration = timedelta(minutes=1)
        mute_until = datetime.now() + mute_duration

        # Сохраняем время мута
        muted_users[target_id] = mute_until

        # Ограничиваем права пользователя
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until,
        )

        # Формируем сообщение
        target_link = f"[{target_user.first_name}](tg://user?id={target_id})"
        mute_message = f"{target_link} затихнет на 0ч 1м, можете выплеснуть свой гнев! 👉 [Тут](https://t.me/Demorgan_CRYSTAL)"
        await update.message.reply_text(mute_message, parse_mode="Markdown")
        return

    # Обрабатываем команду для админов
    if is_admin:
        # Если время не указано, устанавливаем мут на 1 минуту
        if len(text.split()) == 1:  # Команда без аргументов
            mute_duration = timedelta(minutes=1)
        else:
            try:
                mute_time = int(text.split()[1])  # Время в минутах
                if mute_time <= 0:
                    return
                mute_duration = timedelta(minutes=mute_time)
            except (IndexError, ValueError):
                return

        mute_until = datetime.now() + mute_duration

        # Сохраняем время мута
        muted_users[target_id] = mute_until

        # Ограничиваем права пользователя
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until,
        )

        # Формируем сообщение
        target_link = f"[{target_user.first_name}](tg://user?id={target_id})"
        mute_message = f"{target_link} затихнет до {
            mute_until.strftime('%d.%m.%Y %H:%M:%S')}"

        await update.message.reply_text(mute_message, parse_mode="Markdown")


# Снятие мута


async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user

    # Проверяем, является ли отправитель админом или владельцем
    chat_member = await context.bot.get_chat_member(chat.id, user.id)
    if chat_member.status not in ["administrator", "creator"]:
        return

    # Проверяем, есть ли ответ на сообщение
    if not update.message.reply_to_message:
        return

    muted_user = update.message.reply_to_message.from_user

    # Снимаем ограничения
    await context.bot.restrict_chat_member(
        chat.id, muted_user.id, permissions=ChatPermissions(
            can_send_messages=True)
    )

    # Удаляем пользователя из списка замьюченных
    if muted_user.id in muted_users:
        del muted_users[muted_user.id]

    # Формируем кликабельное имя пользователя
    user_link = f"[{muted_user.first_name}](tg://user?id={muted_user.id})"

    # Отправляем сообщение с кликабельным именем
    await update.message.reply_text(
        f" {user_link} теперь может отправлять сообщения.", parse_mode="Markdown"
    )


# Функция для проверки мута перед отправкой сообщения


async def check_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in muted_users:
        if datetime.now() < muted_users[user_id]:
            # Удаляем сообщение замьюченного пользователя
            try:
                await update.message.delete()
            except Exception as e:
                print(f"Ошибка при удалении сообщения: {e}")

            # Отправляем уведомление в чат
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=f"❌ Пользователь {
                    update.message.from_user.first_name} замьючен и не может писать.",
            )
        else:
            # Удаляем мут, если время истекло
            del muted_users[user_id]


async def bot_stop(update: Update, context: CallbackContext) -> None:
    """Функция для обработки команды !бот стоп."""
    if update.message.reply_to_message:
        user_id = update.message.from_user.id
        target_id = update.message.reply_to_message.from_user.id
        user_name = update.message.from_user.first_name
        target_name = update.message.reply_to_message.from_user.first_name

        user_link = f"[{user_name}](tg://user?id={user_id})"
        target_link = f"[{target_name}](tg://user?id={target_id})"

        if user_id not in block_list:
            block_list[user_id] = set()

        # Если уже есть блокировка, снимаем её
        if target_id in block_list[user_id]:
            block_list[user_id].remove(target_id)
            await update.message.reply_text(
                f"{user_link} разрешил {target_link} отвечать на свои сообщения",
                parse_mode="Markdown",
            )
        else:
            # Добавляем блокировку
            block_list[user_id].add(target_id)

            block_list[user_id].add(target_id)
            await update.message.reply_text(
                f"{user_link} запретил {target_link} отвечать на свои сообщения",
                parse_mode="Markdown",
            )
    else:
        await update.message.reply_text(
            "Этой командой необходимо ответить на сообщение человека, которому хотите запретить отвечать вам."
        )


# Проверка сообщений на блокировку


async def check_messages(update: Update, context: CallbackContext) -> None:
    """Функция для удаления сообщений, если пользователь отвечает на запрещённого."""
    user_id = update.message.from_user.id
    reply_to = (
        update.message.reply_to_message.from_user.id
        if update.message.reply_to_message
        else None
    )

    # Проверяем, отвечает ли пользователь тому, кто его заблокировал
    if reply_to and reply_to in block_list and user_id in block_list[reply_to]:
        try:
            await update.message.delete()
            return
        except TelegramError:
            pass  # Если бот не может удалить сообщение, просто игнорируем ошибку


# Бан пользователя


async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id

    # Проверяем, является ли отправитель админом
    is_admin = await is_user_admin(chat_id, user_id, context)
    if not is_admin:
        await update.message.reply_text("❌ У вас нет прав для бана.")
        return

    # Проверяем, есть ли ответ на сообщение
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Ответьте на сообщение пользователя, чтобы забанить."
        )
        return

    target_user = update.message.reply_to_message.from_user
    target_id = target_user.id

    # Проверяем, является ли цель админом (нельзя банить админов)
    if await is_user_admin(chat_id, target_id, context):
        await update.message.reply_text("❌ Вы не можете забанить администратора.")
        return

    # Баним пользователя навсегда
    await context.bot.ban_chat_member(chat_id, target_id)

    # Формируем сообщение с кликабельным именем
    target_link = f"[{target_user.first_name}](tg://user?id={target_id})"
    ban_message = f"🚫 {target_link} забанен навсегда."

    await update.message.reply_text(ban_message, parse_mode="Markdown")


# Кик пользователя


async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user = update.message.from_user

    # Проверяем, является ли отправитель админом
    chat_member = await context.bot.get_chat_member(chat_id, user.id)
    if chat_member.status not in [
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    ]:
        await update.message.reply_text("❌ У вас нет прав для удаления участников.")
        return

    # Ответ на сообщение пользователя, которого кикаем
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    else:
        await update.message.reply_text(
            "⚠ Укажите пользователя, ответив на его сообщение."
        )
        return

    # Проверяем, является ли цель админом
    target_chat_member = await context.bot.get_chat_member(chat_id, target_user.id)
    if target_chat_member.status in [
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    ]:
        await update.message.reply_text("❌ Нельзя удалить администратора.")
        return

    # Удаление пользователя
    try:
        await context.bot.ban_chat_member(chat_id, target_user.id)
        # Разбан (чтобы мог вернуться)
        await context.bot.unban_chat_member(chat_id, target_user.id)
        mention = f"[{target_user.first_name}](tg://user?id={target_user.id})"
        await update.message.reply_text(
            f"{mention} исчез... пропал... 💨", parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


# Запуск рулетки


async def roulette(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name

    if chat_id in active_group_roulette:
        await context.bot.send_message(
            chat_id=chat_id, text=f"Рулетка уже запущена, вы можете сделать ставку."
        )
        return

    active_group_roulette[chat_id] = True
    await show_roulette_rules(update, context)


# Показать правила рулетки


async def show_roulette_rules(update: Update, context: CallbackContext):
    keyboard = [
        [
            InlineKeyboardButton("1-3", callback_data="1-3"),
            InlineKeyboardButton("4-6", callback_data="4-6"),
            InlineKeyboardButton("7-9", callback_data="7-9"),
            InlineKeyboardButton("10-12", callback_data="10-12"),
        ],
        [
            InlineKeyboardButton("1к на 🔴", callback_data="red"),
            InlineKeyboardButton("1к на ⚫️", callback_data="black"),
            InlineKeyboardButton("1к на 🟢", callback_data="green"),
        ],
        [
            InlineKeyboardButton("Повторить", callback_data="repeat"),
            InlineKeyboardButton("Удвоить", callback_data="double"),
            InlineKeyboardButton("Крутить", callback_data="spin"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    rules_message = await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=(
            "Минирулетка Угадайте число из:\n"
            "0🟢\n"
            "1🔴 2⚫️ 3🔴 4⚫️ 5🔴 6⚫️\n"
            "7🔴 8⚫️ 9🔴10⚫️11🔴12⚫️\n"
            "Ставки можно текстом:\n"
            "10 на красное | 5 на 12\n"
        ),
        reply_markup=reply_markup,
    )
    rules_message_id[update.message.chat_id] = rules_message.message_id


# Обработка нажатия кнопок


async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    user_name = query.from_user.first_name
    data = query.data

    if chat_id not in active_group_roulette:
        await query.answer("Рулетка не активна. Напишите 'рулетка', чтобы начать.")
        return

    user_balances.setdefault(user_id, 100000)

    if data in ["1-3", "4-6", "7-9", "10-12"]:
        amount = 1000
        if user_balances[user_id] < amount:
            await query.answer("Недостаточно монет!")
            return

        bets = user_bets.setdefault((user_id, chat_id), {})
        bets[data] = bets.get(data, 0) + amount
        user_balances[user_id] -= amount

        bet_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ставка принята: [{user_name}](tg://user?id={user_id}) {amount} монет на {data}",
            parse_mode="Markdown",
        )
        user_bet_messages.setdefault((user_id, chat_id), []).append(
            bet_message.message_id
        )
        await query.answer()

    elif data in ["red", "black", "green"]:
        amount = 1000
        if user_balances[user_id] < amount:
            await query.answer("Недостаточно монет!")
            return

        bets = user_bets.setdefault((user_id, chat_id), {})
        color = "красное" if data == "red" else (
            "чёрное" if data == "black" else "0")
        bets[color] = bets.get(color, 0) + amount
        user_balances[user_id] -= amount

        bet_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ставка принята: [{user_name}](tg://user?id={user_id}) {amount} монет на {color}",
            parse_mode="Markdown",
        )
        user_bet_messages.setdefault((user_id, chat_id), []).append(
            bet_message.message_id
        )
        await query.answer()

    elif data == "repeat":
        await context.bot.send_message(
            chat_id=chat_id, text="Команда «Повторить» временно недоступна."
        )
        await query.answer()

    elif data == "double":
        bets = user_bets.get((user_id, chat_id), {})
        if not bets:
            await query.answer("Нет ставок для удвоения")
            return

        total_bet = sum(bets.values())
        if user_balances[user_id] < total_bet:
            await query.answer("Недостаточно монет для удвоения!")
            return

        for bet in bets:
            bets[bet] *= 2
        user_balances[user_id] -= total_bet

        bet_text = "\n".join(
            [f"{amount} на {bet}" for bet, amount in bets.items()])
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"[{user_name}](tg://user?id={user_id}) удвоил(а) ставки:\n{bet_text}",
            parse_mode="Markdown",
        )
        await query.answer()

    elif data == "spin":
        if (user_id, chat_id) not in user_bets or not user_bets[(
                user_id, chat_id)]:
            await query.answer()
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"[{user_name}](tg://user?id={user_id}), сделайте ставку.",
                parse_mode="Markdown",
            )
            return

        user_spinning.add((user_id, chat_id))
        await query.answer()

        if chat_id in rules_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=chat_id, message_id=rules_message_id[chat_id]
                )
            except Exception as e:
                print(f"Ошибка при удалении сообщения: {e}")
            del rules_message_id[chat_id]

        for bet_user_id, bet_chat_id in list(user_bet_messages.keys()):
            if bet_chat_id == chat_id:
                for message_id in user_bet_messages[(
                        bet_user_id, bet_chat_id)]:
                    try:
                        await context.bot.delete_message(
                            chat_id=chat_id, message_id=message_id
                        )
                    except Exception as e:
                        print(f"Ошибка при удалении сообщения о ставке: {e}")
                del user_bet_messages[(bet_user_id, bet_chat_id)]


async def spin_roulette_task(user_id, chat_id, user_name, context, update):
    result_text = ""

    if chat_id == user_id:
        delay = random.choice([3, 5, 10])
    else:
        delay = random.choice([5, 10, 15])

    spin_message = await context.bot.send_message(
        chat_id=chat_id,
        text=f"[{user_name}](tg://user?id={user_id}) крутит (через {delay} сек)",
        parse_mode='Markdown'
    )
    await asyncio.sleep(delay)

    await context.bot.delete_message(chat_id=chat_id, message_id=spin_message.message_id)

    gif_url = random.choice(ROULETTE_GIFS)
    gif_message = await context.bot.send_animation(chat_id=chat_id, animation=gif_url)
    await asyncio.sleep(GIF_DURATION)

    await context.bot.delete_message(chat_id=chat_id, message_id=gif_message.message_id)

    result_number = random.randint(0, 12)
    result_color = "🟢" if result_number == 0 else ("🔴" if result_number % 2 != 0 else "⚫️")

    result_text = f"Рулетка: {result_number}{result_color}\n"

    for (bet_user_id, bet_chat_id), bets in user_bets.items():
        if bet_chat_id == chat_id:
            try:
                user = await context.bot.get_chat(bet_user_id)
                user_name = user.first_name

                sorted_bets = sorted(bets.items(), key=lambda x: (
                    0 if isinstance(x[0], int) else (1 if "-" in str(x[0]) else 2),
                    x[0] if isinstance(x[0], int) else 0
                ))

                for bet, amount in sorted_bets:
                    if bet == 0 or bet == "0":
                        bet = "зеро"
                    elif bet == "🔴":
                        bet = "красное"
                    elif bet == "⚫️":
                        bet = "чёрное"
                    elif bet == "🟢":
                        bet = "зелёное"
                    result_text += f"{user_name} {amount} на {bet}\n"
            except Exception as e:
                print(f"Ошибка при получении информации о пользователе: {e}")

    for (bet_user_id, bet_chat_id), bets in user_bets.items():
        if bet_chat_id == chat_id:
            try:
                user = await context.bot.get_chat(bet_user_id)
                user_name = user.first_name
                total_win = 0

                sorted_bets = sorted(bets.items(), key=lambda x: (
                    0 if isinstance(x[0], int) else (1 if "-" in str(x[0]) else 2),
                    x[0] if isinstance(x[0], int) else 0
                ))

                for bet, amount in sorted_bets:
                    if isinstance(bet, int):
                        if bet == result_number:
                            win = amount * 12
                            total_win += int(win)
                            if result_number == 0:
                                result_text += f"[{user_name}](tg://user?id={bet_user_id}) выиграл {int(win)} на зеро\n"
                            else:
                                result_text += f"[{user_name}](tg://user?id={bet_user_id}) выиграл {int(win)} на {bet}\n"
                        elif result_number == 0:
                            return_amount = int(amount // 2)
                            user_balances[bet_user_id] += return_amount
                            result_text += f"[{user_name}](tg://user?id={bet_user_id}) возврат {return_amount} на {bet}\n"
                    elif bet in ["красное", "чёрное"]:
                        if (bet == "красное" and result_color == "🔴") or (bet == "чёрное" and result_color == "⚫️"):
                            win = amount * 2
                            total_win += int(win)
                            result_text += f"[{user_name}](tg://user?id={bet_user_id}) выиграл {int(win)} на {bet}\n"
                    elif bet == "0":
                        if result_number == 0:
                            win = amount * 12
                            total_win += int(win)
                            result_text += f"[{user_name}](tg://user?id={bet_user_id}) выиграл {int(win)} на зеро\n"
                    elif "-" in bet:
                        start, end = map(int, bet.split("-"))
                        if start <= result_number <= end:
                            multiplier = 12 / (end - start + 1)
                            win = amount * multiplier
                            total_win += int(win)
                            result_text += f"[{user_name}](tg://user?id={bet_user_id}) выиграл {int(win)} на {bet}\n"
                        elif result_number == 0:
                            return_amount = int(amount // 2)
                            user_balances[bet_user_id] += return_amount
                            result_text += f"[{user_name}](tg://user?id={bet_user_id}) возврат {return_amount} на {bet}\n"

                user_balances[bet_user_id] += total_win
            except Exception as e:
                print(f"Ошибка при обработке ставок: {e}")

    await context.bot.send_message(
        chat_id=chat_id,
        text=result_text,
        parse_mode='Markdown'
    )

    log_entry = f"Рулетка: {result_number}{result_color}"
    if chat_id == user_id:
        if user_id not in private_roulette_log:
            private_roulette_log[user_id] = []
        private_roulette_log[user_id].append(log_entry)
    else:
        if chat_id not in group_roulette_log:
            group_roulette_log[chat_id] = []
        group_roulette_log[chat_id].append(log_entry)

    for (bet_user_id, bet_chat_id) in list(user_bets.keys()):
        if bet_chat_id == chat_id:
            del user_bets[(bet_user_id, bet_chat_id)]

    user_spinning.remove((user_id, chat_id))

    if chat_id == user_id:
        if chat_id in active_group_roulette:
            del active_group_roulette[chat_id]

        await context.bot.send_message(
            chat_id=chat_id,
        )
    else:
        active_group_roulette[chat_id] = True
        await show_roulette_rules(update, context)

async def show_log(update: Update, context: CallbackContext):
    user_id=update.message.from_user.id
    chat_id=update.message.chat_id
    user_name=update.message.from_user.first_name

    command=update.message.text.strip().lower()

    if command in ["лог", "логи"]:
        log_limit=11
    elif command in ["!лог", "!логи"]:
        log_limit=21
    else:
        await context.bot.send_message(
            chat_id=chat_id, text="Неизвестная команда. Используйте 'лог' или '!лог'."
        )
        return

    if chat_id == user_id:
        log=private_roulette_log.get(user_id, [])
    else:
        log=group_roulette_log.get(chat_id, [])

    if not log:
        await context.bot.send_message(chat_id=chat_id, text="Лог пустой")
        return

    log_text="\n".join([entry.replace("Рулетка: ", "")
                         for entry in log[-log_limit:]])

    await context.bot.send_message(
        chat_id=chat_id, text=log_text, parse_mode="Markdown"
    )


# Показать ставки


async def show_bets(update: Update, context: CallbackContext):
    user_id=update.message.from_user.id
    chat_id=update.message.chat_id
    user_name=update.message.from_user.first_name

    if (user_id, chat_id) in user_bets and user_bets[(user_id, chat_id)]:
        bets=user_bets[(user_id, chat_id)]

        sorted_bets=sorted(
            bets.items(),
            key=lambda x: (
                0 if isinstance(x[0], int) else (1 if "-" in str(x[0]) else 2),
                x[0] if isinstance(x[0], int) else 0,
            ),
        )

        bet_text=""
        for bet, amount in sorted_bets:
            if bet == "красное":
                bet="🔴"
            elif bet == "чёрное":
                bet="⚫️"
            elif bet == "зелёное":
                bet="🟢"
            bet_text += f"{amount} на {bet}\n"

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ставки {user_name}:\n{bet_text}",
            parse_mode="Markdown",
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id, text=f"{user_name}, у вас нет ставок."
        )


async def place_bet(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name
    text = update.message.text.strip().lower()

    # Проверяем, активна ли рулетка в этом чате
    if chat_id not in active_group_roulette:
        if chat_id == user_id:  # Личный чат
            await context.bot.send_message(
                chat_id=chat_id,
            )
            return
        else:  # Группа
            await context.bot.send_message(
                chat_id=chat_id,
            )
            return

    # Проверяем, крутится ли рулетка
    if (user_id, chat_id) in user_spinning:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Рулетка уже крутится, дождитесь завершения."
        )
        return

    # Устанавливаем начальный баланс, если его нет
    user_balances.setdefault(user_id, 100000)

    # Обработка команды "го", "крутить", "spin"
    if text in ["го", "крутить", "spin"]:
        if (user_id, chat_id) not in user_bets or not user_bets[(user_id, chat_id)]:
            # Добавляем кликабельное имя пользователя
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"[{user_name}](tg://user?id={user_id}), сделайте ставку.",
                parse_mode='Markdown'
            )
            return

        # Если ставки есть, продолжаем с запуском рулетки
        user_spinning.add((user_id, chat_id))

        # Удаляем сообщение с правилами и кнопками
        if chat_id in rules_message_id:
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=rules_message_id[chat_id]
                )
            except Exception as e:
                print(f"Ошибка при удалении сообщения: {e}")
            del rules_message_id[chat_id]

        # Удаляем все сообщения о ставках
        for (bet_user_id, bet_chat_id) in list(user_bet_messages.keys()):
            if bet_chat_id == chat_id:
                for message_id in user_bet_messages[(bet_user_id, bet_chat_id)]:
                    try:
                        await context.bot.delete_message(
                            chat_id=chat_id,
                            message_id=message_id
                        )
                    except Exception as e:
                        print(f"Ошибка при удалении сообщения о ставке: {e}")
                del user_bet_messages[(bet_user_id, bet_chat_id)]

        # Запускаем рулетку
        asyncio.create_task(spin_roulette_task(user_id, chat_id, user_name, context, update))
        return

    # Обработка текстовых ставок
    bet_number_match = re.match(r"(\d+)\s+(0|[1-9]|1[0-2])$", text)
    bet_color_match = re.match(r"(\d+)\s+(к|ч)$", text)
    bet_range_match = re.match(r"(\d+)\s+(\d+)-(\d+)$", text)

    va_bank_number_match = re.match(r"(ва-банк|вабанк)\s+(0|[1-9]|1[0-2])$", text)
    va_bank_color_match = re.match(r"(ва-банк|вабанк)\s+(к|ч)$", text)
    va_bank_range_match = re.match(r"(ва-банк|вабанк)\s+(\d+)-(\d+)$", text)

    if bet_number_match:
        amount = int(bet_number_match.group(1))
        if amount < MIN_BET:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{user_name}, минимальная ставка {MIN_BET} монет."
            )
            return

        number = int(bet_number_match.group(2))

        # Проверяем баланс
        if user_balances[user_id] < amount:
            await send_insufficient_funds(update, context, user_balances[user_id])
            return

        bets = user_bets.setdefault((user_id, chat_id), {})
        bets[number] = bets.get(number, 0) + amount
        user_balances[user_id] -= amount  # Уменьшаем баланс на сумму ставки
        bet_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ставка принята: [{user_name}](tg://user?id={user_id}) {amount} монет на {number}",
            parse_mode='Markdown'
        )
        user_bet_messages.setdefault((user_id, chat_id), []).append(bet_message.message_id)

    elif bet_color_match:
        amount = int(bet_color_match.group(1))
        if amount < MIN_BET:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{user_name}, минимальная ставка {MIN_BET} монет."
            )
            return

        color = "красное" if "к" in bet_color_match.group(2) else "чёрное"

        # Проверяем баланс
        if user_balances[user_id] < amount:
            await send_insufficient_funds(update, context, user_balances[user_id])
            return

        bets = user_bets.setdefault((user_id, chat_id), {})
        bets[color] = bets.get(color, 0) + amount
        user_balances[user_id] -= amount
        bet_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ставка принята: [{user_name}](tg://user?id={user_id}) {amount} монет на {color}",
            parse_mode='Markdown'
        )
        user_bet_messages.setdefault((user_id, chat_id), []).append(bet_message.message_id)

    elif bet_range_match:
        amount = int(bet_range_match.group(1))
        if amount < MIN_BET:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{user_name}, минимальная ставка {MIN_BET} монет."
            )
            return

        start = int(bet_range_match.group(2))
        end = int(bet_range_match.group(3))

        if start > end or start < 0 or end > 12:
            return

        # Проверяем баланс
        if user_balances[user_id] < amount:
            await send_insufficient_funds(update, context, user_balances[user_id])
            return

        bets = user_bets.setdefault((user_id, chat_id), {})
        range_key = f"{start}-{end}"
        bets[range_key] = bets.get(range_key, 0) + amount
        user_balances[user_id] -= amount

        bet_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ставка принята: [{user_name}](tg://user?id={user_id}) {amount} монет на {range_key}",
            parse_mode='Markdown'
        )
        user_bet_messages.setdefault((user_id, chat_id), []).append(bet_message.message_id)

    elif va_bank_number_match:
        number = int(va_bank_number_match.group(2))
        amount = user_balances[user_id]

        if amount < MIN_BET:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{user_name}, у вас недостаточно монет (минимум {MIN_BET})."
            )
            return

        bets = user_bets.setdefault((user_id, chat_id), {})
        bets[number] = bets.get(number, 0) + amount
        user_balances[user_id] = 0
        bet_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ставка принята: [{user_name}](tg://user?id={user_id}) {amount} монет на {number}",
            parse_mode='Markdown'
        )
        user_bet_messages.setdefault((user_id, chat_id), []).append(bet_message.message_id)

    elif va_bank_range_match:
        start = int(va_bank_range_match.group(2))
        end = int(va_bank_range_match.group(3))
        amount = user_balances[user_id]

        if amount < MIN_BET:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{user_name}, у вас недостаточно монет (минимум {MIN_BET})."
            )
            return

        if start > end or start < 0 or end > 12:
            return

        bets = user_bets.setdefault((user_id, chat_id), {})
        range_key = f"{start}-{end}"
        bets[range_key] = bets.get(range_key, 0) + amount
        user_balances[user_id] = 0

        bet_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ставка принята: [{user_name}](tg://user?id={user_id}) {amount} монет на {range_key}",
            parse_mode='Markdown'
        )
        user_bet_messages.setdefault((user_id, chat_id), []).append(bet_message.message_id)

    elif va_bank_color_match:
        color = "красное" if "к" in va_bank_color_match.group(2) else "чёрное"
        amount = user_balances[user_id]

        if amount < MIN_BET:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{user_name}, у вас недостаточно монет (минимум {MIN_BET})."
            )
            return

        bets = user_bets.setdefault((user_id, chat_id), {})
        bets[color] = bets.get(color, 0) + amount
        user_balances[user_id] = 0
        bet_message = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ставка принята: [{user_name}](tg://user?id={user_id}) {amount} монет на {color}",
            parse_mode='Markdown'
        )
        user_bet_messages.setdefault((user_id, chat_id), []).append(bet_message.message_id)

    elif text in ["отмена", "Отмена"]:
        if (user_id, chat_id) in user_bets:
            bet_amount = sum(user_bets[(user_id, chat_id)].values())
            user_balances[user_id] += bet_amount
            del user_bets[(user_id, chat_id)]
            await context.bot.send_message(chat_id=chat_id, text=f"Ставки {user_name} отменены")
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"{user_name}, у вас нет активных ставок")

    elif text in ["удвоить", "Удвоить"]:
        bets = user_bets.get((user_id, chat_id), {})
        if not bets:
            await context.bot.send_message(chat_id=chat_id, text="Нет ставок для удвоения")
            return

        total_bet = sum(bets.values())
        if user_balances[user_id] < total_bet:
            await context.bot.send_message(chat_id=chat_id, text="Недостаточно монет для удвоения!")
            return

        for bet in bets:
            bets[bet] *= 2
        user_balances[user_id] -= total_bet

        bet_text = "\n".join([f"{amount} на {bet}" for bet, amount in bets.items()])
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"[{user_name}](tg://user?id={user_id}) удвоил(а) ставки:\n{bet_text}",
            parse_mode='Markdown'
        )

    elif text in ["повторить", "Повторить"]:
        await context.bot.send_message(chat_id=chat_id, text="Команда «Повторить» временно недоступна.")

async def send_insufficient_funds(
    update: Update, context: CallbackContext, balance: int
):
    user_name=update.message.from_user.first_name
    keyboard=[[InlineKeyboardButton("Пополнить баланс", url=TOP_UP_LINK)]]
    reply_markup=InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=update.message.chat_id,
        text=f"{user_name}, ставка не может превышать ваши средства",
        reply_markup=reply_markup,
    )


# Основная функция


def main():
    app = (
        ApplicationBuilder()
        .token(os.getenv("TELEGRAM_TOKEN"))  # ← Добавлена закрывающая скобка
        .build()
    )

    # Обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("referal", get_referral_link))
    # Важно выше текстовых сообщений
    app.add_handler(CommandHandler("Crystal_Money", crystal_money))
    app.add_handler(CommandHandler("Crystal_Limit", crystal_limit))

    # Обработчики текстовых сообщений
    app.add_handler(
        MessageHandler(filters.Regex(r"^(б|Б|баланс|Баланс)$"), balance)
    )
    app.add_handler(MessageHandler(filters.Regex(r"^\+\d+$"), transfer_coins))
    app.add_handler(
        MessageHandler(
        filters.Text(
            ["🔗Рефералы"]),
        referrals_handler))
    app.add_handler(MessageHandler(filters.Text(["!бот стоп"]), bot_stop))
    app.add_handler(MessageHandler(filters.Regex(r"^(Бан|бан)$"), ban_user))
    app.add_handler(MessageHandler(filters.Regex(r"^(Кик|кик)$"), kick_user))
    app.add_handler(
        MessageHandler(
        filters.Regex(r"^(рулетка|Рулетка)$"),
        roulette))
    app.add_handler(
        MessageHandler(
        filters.Regex(r"^(лог|Лог|!лог|!Лог)$"),
        show_log))
    app.add_handler(
        MessageHandler(
        filters.Regex(r"^(ставки|Ставки)$"),
        show_bets))

    app.add_handler(
        MessageHandler(
            filters.Regex(r"(?i)^бандит(\s\d+)?$"),
            play_bandit))

    # Обработчики мута
    app.add_handler(
        MessageHandler(
        filters.Regex(r"^!![Мм]ут\s*\d*"),
        mute_user))
    app.add_handler(MessageHandler(filters.Regex(r"^!!снятьмут$"), unmute))

    # Обработчики кнопок
    app.add_handler(CallbackQueryHandler(show_profile, pattern="^profile_"))
    app.add_handler(
        CallbackQueryHandler(
        handle_bonus,
        pattern="^bonus_request$"))
    app.add_handler(CallbackQueryHandler(get_bonus, pattern="^get_bonus$"))

    # 1. Сначала ловим строго цифры (для handle_user_input)
    app.add_handler(
        MessageHandler(
            # только цифры, не команда
            filters.Regex(r"^\d+$") & ~filters.COMMAND,
            handle_user_input,
        )
    )

    app.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
    handle_user_id_input
    ), group=1)

    app.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    place_bet
    ), group=2)

    app.add_handler(
        MessageHandler(
        filters.ALL,
        check_mute))  # Проверка перед отправкой

    # Запуск бота
    app.run_polling()


if __name__ == "__main__":
    main()
