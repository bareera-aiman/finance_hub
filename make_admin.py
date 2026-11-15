# Usage:  python make_admin.py yourusername     (the user must already be registered)
import sys
from flask import Flask
from config import Config
from models import db, User

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    user = User.query.filter_by(username=sys.argv[1]).first()
    if user is None:
        print("No such user. Register it on the website first.")
    else:
        user.is_admin = True
        db.session.commit()
        print(user.username, "is now an admin.")