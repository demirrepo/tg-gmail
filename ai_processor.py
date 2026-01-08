from openai import OpenAI
import config

client = None


def get_client():
    global client
    if client is None:
        if not config.OPENAI_API_KEY:
            return None
        client = OpenAI(api_key=config.OPENAI_API_KEY)
    return client


def is_available():
    try:
        c = get_client()
        if c is None:
            return False
        return True
    except:
        return False


def get_user_name(gmail_address: str) -> str:
    for item in config.MAIL_BOXES:
        if len(item) >= 3 and item[0] == gmail_address:
            return item[2]
    return ""


def categorize_email(subject: str, body: str) -> str:
    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You categorize emails. Respond with ONLY one hashtag."},
                {"role": "user", "content": f"""Choose ONE hashtag for this email:
#job_offer #urgent #spam #newsletter #social #finance #security #shipping #personal #work #other

Subject: {subject}
Body: {body[:500]}"""}
            ],
            max_tokens=20,
            temperature=0.3
        )
        result = response.choices[0].message.content.strip()
        return result if result.startswith('#') else "#other"
    except:
        return "#other"


def extract_code(body: str) -> str | None:
    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract verification/OTP codes from emails. Respond with ONLY the code or NONE."},
                {"role": "user", "content": f"""Extract any verification code, OTP, PIN from this email:

{body[:1000]}

Respond with ONLY the code or NONE if not found."""}
            ],
            max_tokens=30,
            temperature=0.1
        )
        result = response.choices[0].message.content.strip()
        return None if result.upper() == "NONE" or len(result) > 20 else result
    except:
        return None


def summarize_email(subject: str, body: str) -> str:
    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Summarize emails in 2-3 sentences. Be concise."},
                {"role": "user", "content": f"""Subject: {subject}
Body: {body[:2000]}"""}
            ],
            max_tokens=150,
            temperature=0.5
        )
        return response.choices[0].message.content.strip()
    except:
        return body[:500] + "..."


def generate_reply(subject: str, body: str, sender: str, gmail_user: str) -> str:
    user_name = get_user_name(gmail_user)
    
    try:
        response = get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"You are a professional email assistant writing replies on behalf of {user_name}. Generate polite, concise replies. Sign off with the name: {user_name}"},
                {"role": "user", "content": f"""Generate a reply to this email:

From: {sender}
Subject: {subject}
Body: {body[:1500]}

Write a professional reply (2-4 sentences). End with:
Best regards,
{user_name}"""}
            ],
            max_tokens=200,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error generating reply: {e}"


def process_email(subject: str, body: str) -> dict:
    result = {
        "category": None,
        "code": None,
        "summary": None,
        "is_long": len(body) > 500
    }
    
    if not is_available():
        return result
    
    try:
        result["category"] = categorize_email(subject, body)
        result["code"] = extract_code(body)
        if result["is_long"]:
            result["summary"] = summarize_email(subject, body)
    except:
        pass
    
    return result
