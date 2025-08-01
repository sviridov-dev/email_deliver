from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_mysqldb import MySQL
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from werkzeug.security import check_password_hash
from datetime import datetime
from imapclient import IMAPClient
from email import policy
from email.parser import BytesParser
from dotenv import load_dotenv
import imaplib 
import os, jwt, bcrypt

# Load .env
load_dotenv()


app = Flask(__name__, static_folder="../frontend/build", static_url_path="/")
CORS(app)

# from backend import config
import config

# SQLite configuration
app.config["SQLALCHEMY_DATABASE_URI"] = config.SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = config.SQLALCHEMY_TRACK_MODIFICATIONS

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.Text, nullable=False)  # TODO: hash later
    session_token = db.Column(db.Text, nullable=True)

     # Set hashed password
    def set_password(self, raw_password: str):
        self.password = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Check password
    def check_password(self, raw_password: str) -> bool:
        return bcrypt.checkpw(raw_password.encode("utf-8"), self.password.encode("utf-8"))

class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    password = db.Column(db.Text, nullable=False)

@app.route("/")
def serve():
    return send_from_directory(app.static_folder, "index.html")


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', None)
        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            data = jwt.decode(token,  os.getenv("SECRET_KEY"), algorithms=["HS256"])
            user_id = data['user_id']
        except:
            return jsonify({'error': 'Invalid token'}), 401

        user = User.query.filter_by(id=user_id).first()

        if not user or user.session_token != token:
            return jsonify({'error': 'Session expired (another login detected)'}), 403

        return f(*args, **kwargs)
    return decorated


@app.route('/api/emails', methods=['GET'])
@token_required
def get_emails():

    emails = Email.query.order_by(Email.id.asc()).limit(10).all()
    result = []
    for email in emails:
        result.append({"id": email.id, "email": email.email})
        
        
    return jsonify({"status": "OK", "results": result})


@app.route('/api/check', methods=['POST'])
@token_required
def check_email():


    data = request.json
    from_name_or_email = data.get("search")
    account_email = data.get("email")

    if not from_name_or_email or not account_email:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    email = Email.query.filter_by(email=account_email).first()
    if not email:
        return jsonify({"status": "error", "message": "Email not found"}), 404

    # for acc in address_info:
    # Check email status for each account
    status_list = check_email_status(account_email, email.password, from_name_or_email)

    return jsonify({"status": "OK", "results": status_list})



def token_compare(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', None)
        print(f"token:{token}")
        if token == None or token == '':
            # let assume that only one user is on the user table
            user = User.query.first()
            if not user:
                print(f"error: No user found")
                return jsonify({'error': 'No user found'}), 401
            elif user.session_token != None and user.session_token != '':
                print(f"error: Session expired (another login detected)")
                return jsonify({'error': 'Session expired (another login detected)'}), 403
            else:
                # If token is empty, we assume the user is not logged in
                return f(*args, **kwargs)
        
        else:
            try:
                data = jwt.decode(token,  os.getenv("SECRET_KEY"), algorithms=["HS256"])
                user_id = data['user_id']
            except:
                print(f"error: Invalid token")
                return jsonify({'error': 'Invalid token'}), 401

            user = User.query.filter_by(id=user_id).first()
            if not user or user.session_token != token:
                print(f"error: Session expired (another login detected)")
                return jsonify({'error': 'Session expired (another login detected)'}), 403

            return f(*args, **kwargs)
    return decorated

@app.route('/api/login', methods=['POST'])
@token_compare
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    print(f"username: {username}, password: {password}")
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"status": "error", "message": "Invalid credentials"}), 401

    user_id = user.id
    # Generate JWT token
    token = jwt.encode({"user_id": user_id}, os.getenv("SECRET_KEY"), algorithm="HS256")

    user.session_token = token
    db.session.commit()

    return jsonify({"token": token})

@app.route("/api/logout", methods=["POST"])
@token_required
def logout():
    token = request.headers.get("Authorization")

    if not token:
        return jsonify({"error": "Missing token"}), 401

    user = User.query.filter_by(session_token=token).first()
    if user:
        user.session_token = None
        db.session.commit()

    return jsonify({"status": "OK", "message": "Logout success"}), 200

def check_email_status(gmail_email, app_password, from_email_or_name):
    result = {"inbox": False, "spam": False, "not_found": True, "diff_time": ""}
    
    # List of folders to search
    folders = ["INBOX", "[Gmail]/Spam"]

    def short_date(date):
        
        try:
            if date is None:
                return ""
            now = datetime.now()
            diff = now - date
            if diff.total_seconds() < 60:
                return "Just now"
            elif diff.total_seconds() < 3600:
                return f"{int(diff.total_seconds() // 60)} minutes ago"
            elif diff.total_seconds() < 86400:
                return f"{int(diff.total_seconds() // 3600)} hours ago"
            else:
                return f"{diff.days} days ago"
        except Exception as e:
            return "Unknown"
        
    def find_email():
        try:
            
            def fetch_emails(client, folder, search_text, limit):
                client.select_folder(folder)
                criteria = ['ALL'] if not search_text else ['FROM', search_text]
                uids = client.search(criteria)
                uids = uids[-limit:]  # take last `limit` emails
                messages = client.fetch(uids, ['ENVELOPE', 'X-GM-LABELS'])
                results = []
                for uid, data in messages.items():
                    envelope = data[b'ENVELOPE']
                    subject = envelope.subject.decode() if envelope.subject else "(No subject)"
                    sender = f"{envelope.from_[0].mailbox.decode()}@{envelope.from_[0].host.decode()}"
                    sender_name = envelope.from_[0].name.decode() if envelope.from_[0].name else "(No name)"

                    labels = [l.decode() for l in data.get(b'X-GM-LABELS', [])]
        
                    # Fetch full raw email for body parsing
                    raw_data = client.fetch([uid], ['RFC822'])[uid][b'RFC822']
                    msg = BytesParser(policy=policy.default).parsebytes(raw_data)
                    
                    # Extract plain text and html bodies
                    text_body = None
                    html_body = None
                    if msg.is_multipart():
                        for part in msg.walk():
                            ct = part.get_content_type()
                            if ct == "text/plain" and text_body is None:
                                text_body = part.get_content()
                            elif ct == "text/html" and html_body is None:
                                html_body = part.get_content()
                    else:
                        if msg.get_content_type() == "text/plain":
                            text_body = msg.get_content()
                        elif msg.get_content_type() == "text/html":
                            html_body = msg.get_content()
                    results.append({
                        "folder": folder,
                        "date": envelope.date,
                        "sender": sender,
                        "sender_name": sender_name,
                        "subject": subject,
                        "labels": [l.decode() for l in data.get(b'X-GM-LABELS', [])],
                        "text_body": text_body,
                        "html_body": html_body
                    })
                return results
                        
            with IMAPClient('imap.gmail.com', port=993, ssl=True) as client:
                client.login(gmail_email, app_password)
                
                inbox_emails = fetch_emails(client, "INBOX", from_email_or_name, 10)
                spam_emails = fetch_emails(client, "[Gmail]/Spam", from_email_or_name, 10)
                
                all_emails = inbox_emails + spam_emails
                # Sort combined by date (newest first)
                all_emails.sort(key=lambda x: x['date'], reverse=True)

                return [{"folder": "INBOX", "emails": inbox_emails}, {"folder": "SPAM", "emails": spam_emails}]



            

        except imaplib.IMAP4.error as e:
            print(f"IMAP error occurred while accessing folder : {e}")
            return False
        except Exception as e:
            print(f"Unexpected error while accessing folder : {e}")
            return False

    # Loop through each folder
    results = []
    # Check each folder for the email
    # results = [{"inbox": 0, "spam": 0, "not_found": 0, "diff_time": "", "text": "", "sender": ""}]
    inbox_count = 0
    spam_count = 0  


        
    received_list = find_email()  # Pass the folder variable here


    if received_list == False:
        return {'results':[], 'inbox': 0, 'spam': 0, 'not_found': 1, 'type': 'invalid'}

    for received in received_list:
        email_count = 0
        for email in received['emails']:
            email_count += 1
            result = {}
            result["type"] = "inbox" if received['folder'] == "INBOX" else "spam"
            result["diff_time"] = short_date(email['date'])
            result["date"] = email['date']
            result["text"] = email['text_body']
            result["subject"] = email['subject']
            result["sender_email"] = email['sender']
            result["sender_name"] = email['sender_name']
            results.append(result)
        # Count emails in each folder
        inbox_count += email_count if received['folder'] == "INBOX" else 0
        spam_count += email_count if received['folder'] == "SPAM" else 0

    return {'results': results, 'email': gmail_email, 'inbox': inbox_count, 'spam': spam_count, 'not_found': 0 if inbox_count + spam_count > 0 else 1, 'type': 'valid'}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

    with app.app_context():
        db.create_all()
        print("Database initialized.")