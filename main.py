import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config
import format_mail
import receive_mail
import tracker
import ai_processor

bot = Bot(token=config.TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher(storage=MemoryStorage())
pending_replies = {}


class ReplyStates(StatesGroup):
    waiting_subject = State()
    waiting_message = State()
    confirm_generated = State()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 <b>Gmail Telegram Bot</b>\n\n"
        "• 🏷 Auto-categorization\n"
        "• 🔐 Code extraction\n"
        "• 📋 AI summaries\n"
        "• ↩️ Reply from Telegram\n"
        "• 🤖 AI-generated responses"
    )


@dp.callback_query(F.data.startswith("reply_"))
async def handle_reply(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    msg_key = callback.data.replace("reply_", "")

    if msg_key not in pending_replies:
        await callback.message.answer("❌ Reply data expired.")
        return

    reply_data = pending_replies[msg_key]
    await state.update_data(reply_data=reply_data, msg_key=msg_key)
    await state.set_state(ReplyStates.waiting_subject)

    await callback.message.answer(
        f"↩️ <b>Replying to:</b> {reply_data['from_email']}\n\n"
        "📝 Enter subject (or <b>-</b> to keep original):"
    )


@dp.callback_query(F.data.startswith("generate_"))
async def handle_generate(callback: CallbackQuery, state: FSMContext):
    await callback.answer("🤖 Generating response...")
    msg_key = callback.data.replace("generate_", "")

    if msg_key not in pending_replies:
        await callback.message.answer("❌ Data expired.")
        return

    reply_data = pending_replies[msg_key]

    if not ai_processor.is_available():
        await callback.message.answer("❌ AI not available.")
        return

    generated = ai_processor.generate_reply(
        reply_data['subject'],
        reply_data['body'],
        reply_data['from_email'],
        reply_data['gmail_user']
    )

    await state.update_data(
        reply_data=reply_data,
        msg_key=msg_key,
        generated_text=generated,
        subject=f"Re: {reply_data['subject']}"
    )
    await state.set_state(ReplyStates.confirm_generated)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Send", callback_data="send_generated"),
            InlineKeyboardButton(text="✏️ Edit", callback_data="edit_generated"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_generated")
        ]
    ])

    await callback.message.answer(
        f"🤖 <b>Generated Reply:</b>\n\n{generated}",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "send_generated", ReplyStates.confirm_generated)
async def send_generated(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()

    success = await send_email(
        data['reply_data']['gmail_user'],
        data['reply_data']['from_email'],
        data['subject'],
        data['generated_text']
    )

    if success:
        await callback.message.answer("✅ Reply sent!")
    else:
        await callback.message.answer("❌ Failed to send.")

    cleanup_reply(data.get('msg_key'))
    await state.clear()


@dp.callback_query(F.data == "edit_generated", ReplyStates.confirm_generated)
async def edit_generated(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ReplyStates.waiting_message)
    await callback.message.answer("✏️ Enter your edited message:")


@dp.callback_query(F.data == "cancel_generated", ReplyStates.confirm_generated)
async def cancel_generated(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    cleanup_reply(data.get('msg_key'))
    await state.clear()
    await callback.message.answer("❌ Cancelled.")


@dp.message(ReplyStates.waiting_subject)
async def handle_subject(message: Message, state: FSMContext):
    data = await state.get_data()
    subject = message.text.strip()
    if subject == "-":
        subject = f"Re: {data['reply_data']['subject']}"

    await state.update_data(subject=subject)
    await state.set_state(ReplyStates.waiting_message)
    await message.answer("✍️ Enter your message:")


@dp.message(ReplyStates.waiting_message)
async def handle_message(message: Message, state: FSMContext):
    data = await state.get_data()
    body = message.text.strip()

    success = await send_email(
        data['reply_data']['gmail_user'],
        data['reply_data']['from_email'],
        data['subject'],
        body
    )

    if success:
        await message.answer(f"✅ Reply sent to {data['reply_data']['from_email']}")
    else:
        await message.answer("❌ Failed to send.")

    cleanup_reply(data.get('msg_key'))
    await state.clear()


async def send_email(from_addr: str, to_addr: str, subject: str, body: str) -> bool:
    password = None
    for item in config.MAIL_BOXES:
        if item[0] == from_addr:
            password = item[1]
            break

    if not password:
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = from_addr
        msg['To'] = to_addr
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_addr, password)
        server.send_message(msg)
        server.quit()
        return True
    except:
        return False


def cleanup_reply(msg_key):
    if msg_key and msg_key in pending_replies:
        del pending_replies[msg_key]


async def check_mail(username, password):
    conn = None
    try:
        conn = receive_mail.get_conn(username, password)
        saved_id = tracker.load_last_id(username)
        result = receive_mail.get_last_message_uid(conn)

        if result is None:
            return

        current_uid, email_msg = result

        if current_uid > saved_id:
            print(f"[{username}] New message UID: {current_uid}")

            subject = format_mail.get_subject(email_msg)
            body_text = format_mail.get_raw_text(email_msg)

            ai_result = None
            if ai_processor.is_available():
                try:
                    ai_result = ai_processor.process_email(subject, body_text)
                except:
                    pass

            formatted_text = format_mail.mail_to_text(email_msg, ai_result)

            msg_key = f"{username}_{current_uid}"
            from_header = email_msg.get('From', '')
            if '<' in from_header and '>' in from_header:
                from_email = from_header.split('<')[1].split('>')[0].strip()
            else:
                from_email = from_header.strip()

            pending_replies[msg_key] = {
                'from_email': from_email,
                'subject': subject,
                'body': body_text,
                'gmail_user': username
            }

            buttons = [[InlineKeyboardButton(text="↩️ Reply", callback_data=f"reply_{msg_key}")]]

            if ai_processor.is_available():
                buttons[0].append(InlineKeyboardButton(text="🤖 Generate", callback_data=f"generate_{msg_key}"))

            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await bot.send_message(config.TG_RECEIVER, formatted_text, reply_markup=keyboard)
            tracker.save_last_id(username, current_uid)

    except Exception as ex:
        print(f"[{username}] Error: {ex}")
    finally:
        if conn:
            try:
                conn.close()
                conn.logout()
            except:
                pass


async def check_daemon():
    print(f"Bot started. Checking every {config.UPDATE_INTERVAL}s")
    print(f"Mailboxes: {len(config.MAIL_BOXES)}")
    print(f"AI: {'Enabled' if ai_processor.is_available() else 'Disabled'}")

    while True:
        for item in config.MAIL_BOXES:
            username, password = item[0], item[1]
            await check_mail(username, password)
        await asyncio.sleep(config.UPDATE_INTERVAL)


async def main():
    asyncio.create_task(check_daemon())
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
