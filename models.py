from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Asset types and their units as (singular, plural). One place defines them for the whole app.
ASSET_TYPES = {
    "Stocks": ("share", "shares"),
    "Mutual Funds": ("unit", "units"),
    "ETFs": ("unit", "units"),
    "Gold": ("gram", "grams"),
    "Silver": ("gram", "grams"),
    "Bonds": ("bond", "bonds"),
    "Fixed Deposit": ("deposit", "deposits"),
    "PPF/EPF": ("account", "accounts"),
    "NPS": ("unit", "units"),
    "Real Estate/Land": ("sq ft", "sq ft"),
    "Crypto": ("coin", "coins"),
    "Other": ("unit", "units"),
}

# Types available on the free plan. Premium users can use every type above.
FREE_ASSET_TYPES = ["Stocks", "Mutual Funds", "Gold", "Fixed Deposit"]

# Allowed payment modes for an expense (used by the forms in later parts)
PAYMENT_MODES = ["Cash", "UPI", "Card", "Net Banking"]


class User(UserMixin, db.Model):
    """A registered person. UserMixin gives Flask-Login the methods it needs."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)  # never store the plain password
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- NEW: balance, plan and admin fields ---
    opening_balance = db.Column(db.Float, nullable=False, default=0)       # money the user starts with
    plan = db.Column(db.String(10), nullable=False, default="free")        # "free" or "premium"
    premium_until = db.Column(db.DateTime)                                 # when premium ends (None if never premium)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)        # can approve payments

    # One user -> many expenses / holdings / children / payment requests
    expenses = db.relationship("Expense", backref="user", lazy="dynamic",
                               cascade="all, delete-orphan")
    holdings = db.relationship("Holding", backref="user", lazy="dynamic",
                               cascade="all, delete-orphan")
    children = db.relationship("Child", backref="user", lazy="dynamic",
                               cascade="all, delete-orphan")
    payment_requests = db.relationship("PaymentRequest", backref="user", lazy="dynamic",
                                       cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_premium(self):
        """True only while the plan is premium AND the end date has not passed.
        Because the date is checked every time, expired users are downgraded automatically."""
        return (self.plan == "premium" and self.premium_until is not None
                and self.premium_until > datetime.utcnow())


class Child(db.Model):
    """A child profile, stored by nickname only (no full name, no date of birth)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    nickname = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Expenses tagged to this child (if the child is deleted, expenses stay, tag becomes empty)
    expenses = db.relationship("Expense", backref="child", lazy="dynamic")


class Expense(db.Model):
    """One income or expense entry. Belongs to exactly one user."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False)       # "income" or "expense"
    category = db.Column(db.String(50), nullable=False)   # Food, Rent, Salary...
    date = db.Column(db.Date, nullable=False, default=date.today)

    # --- NEW ---
    payment_mode = db.Column(db.String(20), nullable=False, default="Cash")   # Cash / UPI / Card / Net Banking
    child_id = db.Column(db.Integer, db.ForeignKey("child.id"))               # optional: "spent on this child"


class Holding(db.Model):
    """One investment (stock / mutual fund). Belongs to exactly one user."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    asset_type = db.Column(db.String(30), nullable=False, default="Stocks")   # one of ASSET_TYPES
    symbol = db.Column(db.String(30))                     # optional, used for yfinance later
    buy_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    current_price = db.Column(db.Float, nullable=False)   # entered manually first


class PaymentRequest(db.Model):
    """One attempt to buy Premium (demo payment, verified manually by an admin)."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)           # unique amount, e.g. 1.37, so the admin can match it
    utr = db.Column(db.String(12), unique=True)            # 12-digit UTR typed by the user (unique: one payment, one request)
    status = db.Column(db.String(12), nullable=False, default="pending")   # pending / submitted / approved / rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)    # created_at + 30 minutes
    decided_at = db.Column(db.DateTime)                    # when the admin approved or rejected