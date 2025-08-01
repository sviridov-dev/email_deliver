from app import app, db, User

with app.app_context():
    if not User.query.filter_by(username="1").first():
        user = User(username="1")
        user.set_password("1")  # <-- now hashed
        db.session.add(user)
        db.session.commit()
        print("User added with hashed password: username=1, password=1")
    else:
        print("User already exists.")