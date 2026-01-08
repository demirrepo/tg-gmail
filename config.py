import os



TOKEN = os.getenv("TOKEN")
TG_RECEIVER = int(os.getenv("TG_RECEIVER", "0"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", "60"))


MAIL_BOXES = [
    ('lenovodroid151@gmail.com', os.getenv("MAIL_1_PASS"), 'Demir'),
    ('demirrazzaqov@gmail.com', os.getenv("MAIL_2_PASS"), 'Demir Razzaqov'),
    ('demirdev57@gmail.com', os.getenv("MAIL_2_PASS"), 'Demir'),
]




