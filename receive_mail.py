import email
import imaplib


def get_conn(user, password, host='imap.gmail.com', port=993):
    conn = imaplib.IMAP4_SSL(host, port)
    conn.login(user, password)
    return conn

def get_last_message_uid(conn):
    conn.select('INBOX', readonly=True)
    _, data = conn.search(None, 'ALL')
    all_ids = data[0].split()
    
    if not all_ids:
        return None
    
    last_num = all_ids[-1]
    _, uid_data = conn.fetch(last_num, '(UID)')
    
    if not uid_data or not uid_data[0]:
        return None
    
    uid_response = uid_data[0]
    if isinstance(uid_response, tuple):
        uid_str = uid_response[0].decode('utf-8')
    else:
        uid_str = uid_response.decode('utf-8')
    
    uid = None
    if 'UID' in uid_str:
        try:
            uid = int(uid_str.split('UID')[1].strip().rstrip(')'))
        except:
            pass
    
    if uid is None:
        return None
    
    _, msg_data = conn.fetch(last_num, '(RFC822)')
    if not msg_data or not msg_data[0]:
        return None
    
    return uid, email.message_from_bytes(msg_data[0][1])
