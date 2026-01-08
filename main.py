import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command

import config
import format_mail
import receive_mail
import tracker
import ai_processor

# 1. Initialize Bot
bot = Bot(token=config.TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher(storage=MemoryStorage())
pending_replies = {}

class ReplyStates(StatesGroup):
    waiting_subject = State()
    waiting_message = State()
    confirm_generated = State()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("👋 <b>Gmail Bot Online</b>\nMonitoring your mailboxes...")

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
    await callback.message.answer(f"↩️ <b>Replying to:</b> {reply_data['from_email']}\n📝 Enter subject (or <b>-</b>):")

@dp.callback_query(F.data.startswith("generate_"))
async def handle_generate(callback: CallbackQuery, state: FSMContext):
    # Answer immediately so the button doesn't spin and timeout
    await callback.answer("🤖 AI is thinking...") 
    
    msg_key = callback.data.replace("generate_", "")
    if msg_key not in pending_replies:
        await callback.message.answer("❌ Data expired.")
        return

    reply_data = pending_replies[msg_key]
    
    # Run AI in background thread so it doesn't freeze the bot
    generated = await asyncio.to_thread(
        ai_processor.generate_reply,
        reply_data['subject'],
        reply_data['body'],
        reply_data['from_email'],
        reply_data['gmail_user']
    )

    await state.update_data(reply_data=reply_data, msg_key=msg_key, generated_text=generated, subject=f"Re: {reply_data['subject']}")
    await state.set_state(ReplyStates.confirm_generated)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Send", callback_data="send_generated"),
        InlineKeyboardButton(text="✏️ Edit", callback_data="edit_generated"),
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_generated")
    ]])
    await callback.message.answer(f"🤖 <b>AI Suggested Reply:</b>\n\n{generated}", reply_markup=keyboard)

@dp.callback_query(F.data == "send_generated", ReplyStates.confirm_generated)
async def send_generated(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Sending...")
    data = await state.get_data()
    success = await send_email(data['reply_data']['gmail_user'], data['reply_data']['from_email'], data['subject'], data['generated_text'])
    await callback.message.answer("✅ Sent!" if success else "❌ Failed to send.")
    await state.clear()

@dp.message(ReplyStates.waiting_subject)
async def handle_subject(message: Message, state: FSMContext):
    subject = message.text.strip()
    data = await state.get_data()
    if subject == "-": subject = f"Re: {data['reply_data']['subject']}"
    await state.update_data(subject=subject)
    await state.set_state(ReplyStates.waiting_message)
    await message.answer("✍️ Enter your message:")

@dp.message(ReplyStates.waiting_message)
async def handle_message(message: Message, state: FSMContext):
    data = await state.get_data()
    success = await send_email(data['reply_data']['gmail_user'], data['reply_data']['from_email'], data['subject'], message.text.strip())
    await message.answer("✅ Sent!" if success else "❌ Failed.")
    await state.clear()

# --- THE FIXES ARE HERE ---

def sync_send_email(from_addr, password, to_addr, subject, body):
    """Synchronous SMTP helper used in a thread."""
    try:
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = from_addr, to_addr, subject
        msg.attach(MIMEText(body, 'plain'))
        # Use Port 465 (SSL) which is safer for Railway/Cloud
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15) as server:
            server.login(from_addr, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"SMTP Error for {from_addr}: {e}")
        return False

async def send_email(from_addr, to_addr, subject, body):
    password = next((m[1] for m in config.MAIL_BOXES if m[0] == from_addr), None)
    if not password: return False
    # Run the blocking SMTP call in a separate thread
    return await asyncio.to_thread(sync_send_email, from_addr, password, to_addr, subject, body)

async def check_mail_task(username, password):
    """Check a single mailbox without blocking others."""
    try:
        # Run blocking IMAP calls in a thread
        conn = await asyncio.to_thread(receive_mail.get_conn, username, password)
        if not conn: return
        
        saved_id = tracker.load_last_id(username)
        result = await asyncio.to_thread(receive_mail.get_last_message_uid, conn)
        
        if result:
            current_uid, email_msg = result
            if current_uid > saved_id:
                subject = format_mail.get_subject(email_msg)
                body_text = format_mail.get_raw_text(email_msg)
                
                ai_result = None
                if ai_processor.is_available():
                    ai_result = await asyncio.to_thread(ai_processor.process_email, subject, body_text)

                formatted_text = format_mail.mail_to_text(email_msg, ai_result)
                msg_key = f"{username}_{current_uid}"
                from_header = email_msg.get('From', '')
                from_email = from_header.split('<')[1].split('>')[0].strip() if '<' in from_header else from_header.strip()

                pending_replies[msg_key] = {'from_email': from_email, 'subject': subject, 'body': body_text, 'gmail_user': username}
                
                buttons = [[InlineKeyboardButton(text="↩️ Reply", callback_data=f"reply_{msg_key}")]]
                if ai_processor.is_available():
                    buttons[0].append(InlineKeyboardButton(text="🤖 Generate", callback_data=f"generate_{msg_key}"))
                
                await bot.send_message(config.TG_RECEIVER, formatted_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                tracker.save_last_id(username, current_uid)
        
        await asyncio.to_thread(conn.logout)
    except Exception as e:
        print(f"Mail Error [{username}]: {e}")

async def check_daemon():
    while True:
        # Check all mailboxes at once (concurrently)
        tasks = [check_mail_task(m[0], m[1]) for m in config.MAIL_BOXES]
        await asyncio.gather(*tasks)
        await asyncio.sleep(config.UPDATE_INTERVAL)

async def main():
    asyncio.create_task(check_daemon())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())