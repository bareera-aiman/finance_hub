from app import app
from models import User, Expense, Child, PaymentRequest

with app.app_context():
    u = User.query.filter_by(username="demo").first()
    print(u.username, "| plan:", u.plan, "| opening balance:", u.opening_balance, "| admin:", u.is_admin)
    print("expenses:", u.expenses.count(), "| payment modes:", {e.payment_mode for e in u.expenses})
    print("holdings:", u.holdings.count())
    print("children:", Child.query.count(), "| payment requests:", PaymentRequest.query.count())
    print("premium right now?", u.is_premium)