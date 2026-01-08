import email
import email.header
import html
import re
from bs4 import BeautifulSoup

replaces = {
    re.compile(r'( *[\r\n] *){2,}'): '\n',
    re.compile(r' {2,}'): ' ',
    re.compile(r'\s{2,}'): '',
}.items()

trash_tags = ['title', 'style', 'script']

def mail_to_text(mail, ai_result: dict = None) -> str:
    payload = get_payload(mail)
    text = parse_text_from_payload(payload)
    
    from_ = get_sender(mail)
    to_ = mail.get('Delivered-To', mail.get('To', ''))
    subject = get_subject(mail)
    
    msg_parts = []
    
    if ai_result and ai_result.get("category"):
        msg_parts.append(ai_result["category"])
    
    msg_parts.append(f"\n📧 <b>From:</b> {html.escape(from_)}")
    if to_:
        msg_parts.append(f"📬 <b>To:</b> {html.escape(to_)}")
    msg_parts.append(f"📝 <b>Subject:</b> {html.escape(subject)}")
    
    if ai_result and ai_result.get("code"):
        msg_parts.append(f"\n🔐 <b>Code:</b> <code>{ai_result['code']}</code>")
    
    msg_parts.append("\n" + "─" * 20)
    
    if ai_result and ai_result.get("summary"):
        msg_parts.append(f"\n📋 <b>Summary:</b>\n{html.escape(ai_result['summary'])}")
        msg_parts.append(f"\n<i>(Full: {len(text)} chars)</i>")
    else:
        if len(text) > 3000:
            text = text[:3000] + "..."
        msg_parts.append(f"\n{html.escape(text)}")
    
    msg = "\n".join(msg_parts)
    
    if len(msg) > 4096:
        msg = msg[:4093] + "..."
    return msg

def get_sender(mail) -> str:
    from_header = mail.get('From', 'Unknown')
    try:
        decoded_parts = email.header.decode_header(from_header)
        result = ""
        for part, enc in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(enc or 'utf-8', errors='ignore')
            else:
                result += part
        return result.strip()
    except:
        return from_header


def get_subject(mail) -> str:
    subject_header = mail.get('Subject', 'No Subject')
    try:
        decoded_parts = email.header.decode_header(subject_header)
        result = ""
        for part, enc in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(enc or 'utf-8', errors='ignore')
            else:
                result += part
        return result.strip()
    except:
        return subject_header


def get_payload(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                return decode_payload(part)
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                return decode_payload(part)
        try:
            return get_payload(msg.get_payload(0))
        except:
            return ""
    return decode_payload(msg)


def decode_payload(part) -> str:
    try:
        charset = part.get_content_charset() or 'utf-8'
        payload = part.get_payload(decode=True)
        if not payload:
            return ""
        return payload.decode(charset, errors='ignore')
    except:
        try:
            payload = part.get_payload(decode=False)
            return payload if isinstance(payload, str) else ""
        except:
            return ""


def parse_text_from_payload(payload: str) -> str:
    if not payload:
        return ""
    
    try:
        soup = BeautifulSoup(payload, "html.parser")
        for tag in trash_tags:
            for t in soup.findAll(tag):
                t.decompose()
        text = soup.get_text()
    except:
        text = payload
    
    for pattern, replacement in replaces:
        text = pattern.sub(replacement, text)
    
    return text.strip()

def get_raw_text(mail) -> str:
    payload = get_payload(mail)
    return parse_text_from_payload(payload)