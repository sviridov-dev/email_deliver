from app import app, db, Email

with app.app_context():
    email_list = [
        {"email": "radugistang1@gmail.com", "password": "vhfwpclepkqhqdgq"},
        {"email": "sabrinamorgan19986@gmail.com", "password": "wmalblquclznqrdg"},
        {"email": "iamahotbanana@gmail.com", "password": "uxbjehqrpisehyng"},
        {"email": "fredricgallaghepy78@gmail.com", "password": "wlsvfugwmasvmkoc"},
        {"email": "maryzccarolur1204@gmail.com", "password": "xeijkhmfkbakjloa"},
        {"email": "patriciasysandraan1146@gmail.com", "password": "ksosieliwlewpbbj"},
        {"email": "vanessagoyette493@gmail.com", "password": "mauobygkoxmxopxw"},
        {"email": "bailchrissy62@gmail.com", "password": "czeljywcnqolqgnw"},
        {"email": "Jennifernymariaiy5181@gmail.com", "password": "wrepoyvfacrykdvo"},
        {"email": "adriusance@gmail.com", "password": "rbybwocsztkdiuxw"},
    ]

    for email_data in email_list:
        if not Email.query.filter_by(email=email_data["email"]).first():
            email = Email(email=email_data["email"])
            email.password = email_data["password"]
            db.session.add(email)
            db.session.commit()
            print(f"Email added with password: email={email_data['email']}, password={email_data['password']}")
        else:
            print(f"Email already exists: email={email_data['email']}")