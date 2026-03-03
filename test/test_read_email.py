from services.gmail_receiver import fetch_unread_emails

print("🔍 Checking Gmail inbox for unread emails...\n")

emails = fetch_unread_emails()
print(emails)

if not emails:
    print("📭 No unread emails found")
else:
    print(f"📬 Found {len(emails)} email(s)\n")

    for i, email in enumerate(emails, 1):
        print(f"{'='*50}")
        print(f"Email {i}:")
        print(f"  From:      {email['sender_email']}")
        print(f"  Subject:   {email['subject']}")
        print(f"  Thread ID: {email['thread_id'] or 'None (fresh email)'}")
        print(f"  Message ID: {email['message_id']}")
        print(f"  Body:\n{email['body'][:]}")
        print(f"  Attachments: {email['attachments'] or 'None'}")
        print(f"{'='*50}\n")