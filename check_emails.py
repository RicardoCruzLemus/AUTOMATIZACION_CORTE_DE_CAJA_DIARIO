import imaplib
import email
from email.header import decode_header
from app.config import Config

mail = imaplib.IMAP4_SSL(Config.IMAP_SERVER, 993)
mail.login(Config.IMAP_USER, Config.IMAP_PASSWORD)
mail.select('inbox')
status, messages = mail.search(None, 'ALL')
email_ids = messages[0].split()

print(f'Total emails in inbox: {len(email_ids)}')
for eid in email_ids[-10:]:
    status, msg_data = mail.fetch(eid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
    for response_part in msg_data:
        if isinstance(response_part, tuple):
            msg = email.message_from_bytes(response_part[1])
            subj, enc = decode_header(msg['Subject'])[0]
            if isinstance(subj, bytes):
                subj = subj.decode(enc if enc else 'utf-8', errors='ignore')
            
            # Fetch flags
            status, flags_data = mail.fetch(eid, '(FLAGS)')
            flags = flags_data[0].decode() if flags_data else ""
            
            print(f'ID: {eid.decode()} - Date: {msg.get("Date")} - Subject: {subj} - Flags: {flags}')
