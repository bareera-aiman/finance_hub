from app import app, seed_demo
from models import db, User, Expense, Holding, Child, PaymentRequest

with app.app_context():
    for username in ("demo", "demo_free"):
        user = User.query.filter_by(username=username).first()
        if user:
            Expense.query.filter_by(user_id=user.id).delete()   # expenses first (they point to children)
            Child.query.filter_by(user_id=user.id).delete()
            Holding.query.filter_by(user_id=user.id).delete()
            PaymentRequest.query.filter_by(user_id=user.id).delete()
            db.session.delete(user)
    db.session.commit()
    seed_demo()
    print("Both demo accounts reset with fresh data.")