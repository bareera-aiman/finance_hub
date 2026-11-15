import csv
import io
from datetime import date, datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_login import LoginManager, login_required, current_user

from config import Config
from models import (db, User, Expense, Holding, Child,
                    ASSET_TYPES, FREE_ASSET_TYPES, PAYMENT_MODES)
from auth import auth
from billing import billing, premium_required, FREE_HOLDING_LIMIT
from kids import kids
from calculators import (sip_summary, portfolio_summary, suggest_sip,
                         savings_projection, balance_summary, allocation_by_type)

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)  # connect SQLAlchemy to this app

# --- Flask-Login setup ---
login_manager = LoginManager(app)
login_manager.login_view = "auth.login"        # where to redirect if not logged in
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    # Called on every request: turns the id stored in the session back into a User object
    return db.session.get(User, int(user_id))


app.register_blueprint(auth)
app.register_blueprint(billing)
app.register_blueprint(kids)

# Allowed categories for each transaction type (also used for validation)
CATEGORIES = {
    "expense": ["Food", "Rent", "Transport", "Bills", "Shopping",
                "Entertainment", "Health", "Education", "Other"],
    "income": ["Salary", "Freelance", "Gift", "Interest", "Other"],
}


# ---------- Template filter: format numbers as ₹ with Indian grouping ----------
@app.template_filter("inr")
def inr(value, decimals=None):
    """1234567.5 -> ₹12,34,567.50 ; whole numbers show no decimals."""
    value = round(float(value or 0), 2)
    if decimals is None:
        decimals = 0 if value == int(value) else 2
    sign = "-" if value < 0 else ""
    whole, _, frac = f"{abs(value):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]   # last 3 digits, then groups of 2
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return f"{sign}₹{whole}" + (f".{frac}" if frac else "")


# ---------- Plan check: runs before every request ----------
@app.before_request
def auto_downgrade():
    """If a Premium plan has run out, switch the account back to Free. Data is never deleted."""
    if current_user.is_authenticated and current_user.plan == "premium" and not current_user.is_premium:
        user = db.session.get(User, current_user.id)
        user.plan = "free"
        db.session.commit()
        flash("Your Premium plan has ended. Your data is safe; upgrade any time to unlock everything again.",
              "info")


# ---------- Helper functions ----------
def monthly_totals(user_id, months=6):
    """Income and expense total for each of the user's latest N months (for the bar chart)."""
    totals = {}
    for e in Expense.query.filter_by(user_id=user_id).all():
        key = e.date.strftime("%Y-%m")                       # e.g. "2026-11"
        totals.setdefault(key, {"income": 0, "expense": 0})[e.type] += e.amount
    keys = sorted(totals)[-months:]
    labels = [datetime.strptime(k, "%Y-%m").strftime("%b %Y") for k in keys]
    return labels, [totals[k]["income"] for k in keys], [totals[k]["expense"] for k in keys]


def read_expense_form(form, existing_child_id=None):
    """Validate the add/edit form. Returns (list_of_errors, cleaned_values).
    existing_child_id is the expense's current child tag when editing (None when adding)."""
    errors = []
    title = form.get("title", "").strip()
    kind = form.get("type", "")
    category = form.get("category", "")
    payment_mode = form.get("payment_mode", "")

    if not title or len(title) > 100:
        errors.append("Title is required (max 100 characters).")

    try:
        amount = float(form.get("amount", ""))
        if not (0 < amount <= 1_000_000_000):    # also rejects nan / inf
            raise ValueError
    except ValueError:
        amount = None
        errors.append("Amount must be a number greater than 0.")

    if kind not in CATEGORIES:
        errors.append("Please choose income or expense.")
    elif category not in CATEGORIES[kind]:
        errors.append("Please choose a valid category.")

    if payment_mode not in PAYMENT_MODES:
        errors.append("Please choose a payment mode.")

    try:
        when = datetime.strptime(form.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        when = None
        errors.append("Please enter a valid date.")

    # --- Child tag: only Premium users can change it, and only to THEIR OWN children ---
    child_id = existing_child_id               # default: leave the tag as it was
    if current_user.is_premium:
        child_id = None
        raw = form.get("child_id", "")
        if kind == "expense" and raw:
            try:
                child = Child.query.filter_by(id=int(raw), user_id=current_user.id).first()
            except ValueError:
                child = None
            if child is None:
                errors.append("Please choose a valid child.")
            else:
                child_id = child.id
    if kind == "income":
        child_id = None                         # only expenses can be tagged to a child

    return errors, {"title": title, "amount": amount, "type": kind, "category": category,
                    "date": when, "payment_mode": payment_mode, "child_id": child_id}


def expense_form_extras():
    """Extra data for the expense form: payment modes, and the child list (Premium users only)."""
    children = []
    if current_user.is_premium:
        children = Child.query.filter_by(user_id=current_user.id).order_by(Child.nickname).all()
    return {"payment_modes": PAYMENT_MODES, "children": children}


def totals_until_today(user_id):
    """All-time income and expense totals. Future-dated entries are not counted yet."""
    def total(kind):
        return db.session.query(db.func.sum(Expense.amount)).filter(
            Expense.user_id == user_id, Expense.type == kind,
            Expense.date <= date.today()).scalar() or 0
    return total("income"), total("expense")


# ---------- Dashboard ----------
@app.route("/")
@login_required
def dashboard():
    # 1) Average monthly savings (income - expenses) over the user's last 3 months with data
    _, month_income, month_expense = monthly_totals(current_user.id, months=3)
    savings_list = [i - e for i, e in zip(month_income, month_expense)]
    avg_savings = sum(savings_list) / len(savings_list) if savings_list else 0
    suggested_sip = suggest_sip(avg_savings)       # rule: invest 50% of savings

    # 2) Current portfolio numbers (this user's holdings only)
    holdings = Holding.query.filter_by(user_id=current_user.id).all()
    pf = portfolio_summary(holdings)

    # 2b) Total balance and net worth
    total_income, total_expense = totals_until_today(current_user.id)
    money = balance_summary(current_user.opening_balance, total_income,
                            total_expense, pf["value"])

    # 3) Projection settings from the URL (?years=10&rate=12); fall back to defaults if invalid
    years, rate = 10, 12.0
    try:
        years = int(request.args.get("years", years))
        rate = float(request.args.get("rate", rate))
        if not (1 <= years <= 50 and 0 <= rate <= 50):
            raise ValueError
    except ValueError:
        years, rate = 10, 12.0
        flash("Projection settings were invalid, so defaults were used.", "warning")

    # 4) Grow the portfolio alone, and the portfolio together with the suggested SIP
    projection = savings_projection(pf["value"], suggested_sip, rate, years)

    return render_template("dashboard.html", avg_savings=avg_savings,
                           savings_months=len(savings_list), suggested_sip=suggested_sip,
                           pf=pf, money=money, years=years, rate=rate, projection=projection)


# ---------- Opening balance ----------
@app.route("/balance/opening", methods=["POST"])
@login_required
def set_opening_balance():
    try:
        value = float(request.form.get("opening_balance", ""))
        if not (0 <= value <= 1_000_000_000):      # also rejects nan / inf
            raise ValueError
    except ValueError:
        flash("Opening balance must be a number between 0 and 100 crore.", "danger")
        return redirect(url_for("dashboard"))

    user = db.session.get(User, current_user.id)    # update only the logged-in user's row
    user.opening_balance = round(value, 2)
    db.session.commit()
    flash("Opening balance updated.", "success")
    return redirect(url_for("dashboard"))


# ---------- Expense tracker ----------
@app.route("/expenses")
@login_required
def expenses():
    # Which month? URL looks like /expenses?month=2026-11 ; default = this month
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        start = datetime.strptime(month, "%Y-%m").date()      # first day of that month
    except ValueError:
        start = date.today().replace(day=1)
        month = start.strftime("%Y-%m")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)   # first day of next month

    # Only THIS user's transactions inside the chosen month
    transactions = (Expense.query
                    .filter(Expense.user_id == current_user.id,
                            Expense.date >= start, Expense.date < end)
                    .order_by(Expense.date.desc(), Expense.id.desc()).all())

    income = sum(t.amount for t in transactions if t.type == "income")
    spent = sum(t.amount for t in transactions if t.type == "expense")

    # Spending per category (for the doughnut chart)
    by_category = {}
    for t in transactions:
        if t.type == "expense":
            by_category[t.category] = by_category.get(t.category, 0) + t.amount

    month_labels, month_income, month_expense = monthly_totals(current_user.id)

    return render_template(
        "expenses.html", month=month, month_title=start.strftime("%B %Y"),
        transactions=transactions, income=income, spent=spent, savings=income - spent,
        cat_labels=list(by_category.keys()), cat_values=list(by_category.values()),
        month_labels=month_labels, month_income=month_income, month_expense=month_expense)


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    if request.method == "POST":
        errors, data = read_expense_form(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("expense_form.html", form=request.form, categories=CATEGORIES,
                                   mode="Add", **expense_form_extras())
        db.session.add(Expense(user_id=current_user.id, **data))   # owner = logged-in user
        db.session.commit()
        flash("Transaction added.", "success")
        # Redirect after POST so a page refresh doesn't submit the form twice
        return redirect(url_for("expenses", month=data["date"].strftime("%Y-%m")))

    form = {"date": date.today().isoformat(), "type": "expense", "payment_mode": "UPI"}
    return render_template("expense_form.html", form=form, categories=CATEGORIES,
                           mode="Add", **expense_form_extras())


@app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(expense_id):
    # Look up by id AND user_id: someone else's expense gives a 404
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()

    if request.method == "POST":
        errors, data = read_expense_form(request.form, existing_child_id=expense.child_id)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("expense_form.html", form=request.form, categories=CATEGORIES,
                                   mode="Edit", **expense_form_extras())
        for field, value in data.items():
            setattr(expense, field, value)
        db.session.commit()
        flash("Transaction updated.", "success")
        return redirect(url_for("expenses", month=expense.date.strftime("%Y-%m")))

    form = {"title": expense.title, "amount": expense.amount, "type": expense.type,
            "category": expense.category, "date": expense.date.isoformat(),
            "payment_mode": expense.payment_mode, "child_id": expense.child_id}
    return render_template("expense_form.html", form=form, categories=CATEGORIES,
                           mode="Edit", **expense_form_extras())


@app.route("/expenses/<int:expense_id>/delete", methods=["POST"])   # POST only, never GET
@login_required
def delete_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
    month = expense.date.strftime("%Y-%m")
    db.session.delete(expense)
    db.session.commit()
    flash("Transaction deleted.", "info")
    return redirect(url_for("expenses", month=month))


# ---------- SIP calculator ----------
@app.route("/sip")
@login_required
def sip():
    # First visit shows default values. Later visits read ?amount=...&rate=...&years=...
    form = {"amount": "5000", "rate": "12", "years": "10"}
    if request.args:
        form = {key: request.args.get(key, "").strip() for key in form}

    errors = []
    amount = rate = years = None
    try:
        amount = float(form["amount"])
        if not (1 <= amount <= 10_000_000):        # also rejects nan / inf
            raise ValueError
    except ValueError:
        errors.append("Monthly amount must be between ₹1 and ₹1,00,00,000.")
    try:
        rate = float(form["rate"])
        if not (0 <= rate <= 50):
            raise ValueError
    except ValueError:
        errors.append("Expected return must be between 0% and 50%.")
    try:
        years = int(form["years"])
        if not (1 <= years <= 50):
            raise ValueError
    except ValueError:
        errors.append("Years must be a whole number between 1 and 50.")

    result = None
    if errors:
        for e in errors:
            flash(e, "danger")
    else:
        result = sip_summary(amount, rate, years)   # all maths is in calculators.py

    return render_template("sip.html", form=form, result=result)


# ---------- Investment portfolio ----------
def parse_positive(form, field, label, errors):
    """Read a number > 0 from the form; add an error message if it is invalid."""
    try:
        value = float(form.get(field, ""))
        if not (0 < value <= 1_000_000_000):    # also rejects nan / inf
            raise ValueError
        return value
    except ValueError:
        errors.append(f"{label} must be a number greater than 0.")
        return None


def read_holding_form(form, current_type=None):
    """Validate the add/edit holding form. Returns (errors, cleaned_values).
    current_type is the holding's existing type when editing (None when adding)."""
    errors = []
    asset_type = form.get("asset_type", "")
    name = form.get("name", "").strip()
    symbol = form.get("symbol", "").strip().upper()

    # --- Plan check, done on the SERVER (hiding an option in the page is not security) ---
    if asset_type not in ASSET_TYPES:
        errors.append("Please choose a valid asset type.")
    elif (not current_user.is_premium and asset_type not in FREE_ASSET_TYPES
          and asset_type != current_type):
        errors.append(f"{asset_type} is a Premium asset type. The free plan includes: "
                      + ", ".join(FREE_ASSET_TYPES) + ".")

    if not name or len(name) > 100:
        errors.append("Name is required (max 100 characters).")
    if len(symbol) > 30:
        errors.append("Symbol is too long (max 30 characters).")

    buy_price = parse_positive(form, "buy_price", "Buy price", errors)
    quantity = parse_positive(form, "quantity", "Quantity", errors)
    current_price = parse_positive(form, "current_price", "Current price", errors)

    return errors, {"asset_type": asset_type, "name": name, "symbol": symbol or None,
                    "buy_price": buy_price, "quantity": quantity, "current_price": current_price}


@app.route("/portfolio")
@login_required
def portfolio():
    # Only THIS user's holdings
    holdings = Holding.query.filter_by(user_id=current_user.id).order_by(Holding.name).all()
    summary = portfolio_summary(holdings)                  # all maths is in calculators.py
    by_type = allocation_by_type(summary["rows"])          # totals grouped by asset type

    return render_template("portfolio.html", summary=summary, by_type=by_type,
                           asset_types=ASSET_TYPES,
                           alloc_labels=[t["type"] for t in by_type],
                           alloc_values=[round(t["value"]) for t in by_type])


@app.route("/portfolio/add", methods=["GET", "POST"])
@login_required
def add_holding():
    # Free plan: limited number of holdings. Checked on the server, for GET and POST.
    if not current_user.is_premium and current_user.holdings.count() >= FREE_HOLDING_LIMIT:
        flash(f"The free plan allows up to {FREE_HOLDING_LIMIT} holdings. "
              "Upgrade to Premium for unlimited holdings.", "warning")
        return redirect(url_for("billing.pricing"))

    if request.method == "POST":
        errors, data = read_holding_form(request.form)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("holding_form.html", form=request.form, mode="Add",
                                   asset_types=ASSET_TYPES, free_types=FREE_ASSET_TYPES,
                                   current_type=None)
        db.session.add(Holding(user_id=current_user.id, **data))   # owner = logged-in user
        db.session.commit()
        flash("Holding added.", "success")
        return redirect(url_for("portfolio"))
    return render_template("holding_form.html", form={}, mode="Add", asset_types=ASSET_TYPES,
                           free_types=FREE_ASSET_TYPES, current_type=None)


@app.route("/portfolio/<int:holding_id>/edit", methods=["GET", "POST"])
@login_required
def edit_holding(holding_id):
    # Look up by id AND user_id: someone else's holding gives a 404
    holding = Holding.query.filter_by(id=holding_id, user_id=current_user.id).first_or_404()

    if request.method == "POST":
        errors, data = read_holding_form(request.form, current_type=holding.asset_type)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("holding_form.html", form=request.form, mode="Edit",
                                   asset_types=ASSET_TYPES, free_types=FREE_ASSET_TYPES,
                                   current_type=holding.asset_type)
        for field, value in data.items():
            setattr(holding, field, value)
        db.session.commit()
        flash("Holding updated.", "success")
        return redirect(url_for("portfolio"))

    form = {"asset_type": holding.asset_type, "name": holding.name, "symbol": holding.symbol or "",
            "buy_price": holding.buy_price, "quantity": holding.quantity,
            "current_price": holding.current_price}
    return render_template("holding_form.html", form=form, mode="Edit", asset_types=ASSET_TYPES,
                           free_types=FREE_ASSET_TYPES, current_type=holding.asset_type)


@app.route("/portfolio/<int:holding_id>/delete", methods=["POST"])
@login_required
def delete_holding(holding_id):
    holding = Holding.query.filter_by(id=holding_id, user_id=current_user.id).first_or_404()
    db.session.delete(holding)
    db.session.commit()
    flash("Holding deleted.", "info")
    return redirect(url_for("portfolio"))


@app.route("/portfolio/refresh", methods=["POST"])
@login_required
def refresh_prices():
    from prices import fetch_price                      # optional live prices (Step 8)
    updated = failed = 0
    for h in Holding.query.filter_by(user_id=current_user.id).all():   # only this user's holdings
        if not h.symbol:
            continue
        price = fetch_price(h.symbol)
        if price:
            h.current_price = round(price, 2)
            updated += 1
        else:
            failed += 1
    db.session.commit()

    if updated:
        flash(f"Updated {updated} price(s) from Yahoo Finance.", "success")
    if failed:
        flash(f"Could not fetch {failed} price(s); the old prices were kept.", "warning")
    if not updated and not failed:
        flash("None of your holdings has a symbol to look up.", "info")
    return redirect(url_for("portfolio"))


# ---------- CSV export (Premium only) ----------
def safe_cell(value):
    """Stop spreadsheet formula injection: a text cell starting with = + - @ would run as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def csv_response(filename, header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(buffer.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/export/expenses.csv")
@premium_required                                       # checked on the server
def export_expenses():
    rows = (Expense.query.filter_by(user_id=current_user.id)
            .order_by(Expense.date.desc(), Expense.id.desc()).all())
    return csv_response("expenses.csv",
                        ["Date", "Type", "Category", "Title", "Amount", "Payment mode", "Child"],
                        [[e.date.isoformat(), e.type, e.category, safe_cell(e.title),
                          e.amount, e.payment_mode, safe_cell(e.child.nickname) if e.child else ""]
                         for e in rows])


@app.route("/export/holdings.csv")
@premium_required
def export_holdings():
    rows = Holding.query.filter_by(user_id=current_user.id).order_by(Holding.name).all()
    return csv_response("holdings.csv",
                        ["Asset type", "Name", "Symbol", "Quantity", "Buy price", "Current price"],
                        [[h.asset_type, safe_cell(h.name), h.symbol or "", h.quantity,
                          h.buy_price, h.current_price] for h in rows])


# ---------- Error pages (themed) ----------
@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(403)
def forbidden(error):
    return render_template("403.html"), 403


# ---------- Demo accounts ----------
def seed_account(username, email, premium, opening, salary, expenses, months, holdings, kids=None):
    """Create one demo account with sample data (skipped if the username already exists).
    kids = [(nickname, [(title, category, amount, payment_mode), ...]), ...]"""
    if User.query.filter_by(username=username).first():
        return
    kids = kids or []

    user = User(username=username, email=email, opening_balance=opening)
    user.set_password("demo123")
    if premium:
        user.plan = "premium"
        user.premium_until = datetime.utcnow() + timedelta(days=365)
    db.session.add(user)
    db.session.commit()  # commit first so user.id is available

    # Child profiles (nickname only) are created first so expenses can point to them
    child_ids = {}
    for nickname, _items in kids:
        child = Child(user_id=user.id, nickname=nickname)
        db.session.add(child)
        db.session.flush()                        # gives the child an id without committing yet
        child_ids[nickname] = child.id

    for i in range(months):                       # one block per month, 30 days apart
        d = date.today() - timedelta(days=30 * i)
        db.session.add(Expense(user_id=user.id, title="Monthly Salary", amount=salary,
                               type="income", category="Salary", date=d,
                               payment_mode="Net Banking"))
        for title, cat, amt, mode in expenses:
            amt = amt + (i % 3) * 300             # small variation so the bar chart isn't flat
            db.session.add(Expense(user_id=user.id, title=title, amount=amt, type="expense",
                                   category=cat, date=d, payment_mode=mode))
        for nickname, items in kids:              # spending tagged to each child
            for title, cat, amt, mode in items:
                db.session.add(Expense(user_id=user.id, title=title, amount=amt, type="expense",
                                       category=cat, date=d, payment_mode=mode,
                                       child_id=child_ids[nickname]))

    for asset_type, name, symbol, buy, qty, cur in holdings:
        db.session.add(Holding(user_id=user.id, asset_type=asset_type, name=name, symbol=symbol,
                               buy_price=buy, quantity=qty, current_price=cur))
    db.session.commit()


def seed_demo():
    """demo = Premium account with 6 months of data and 2 children; demo_free = Free account."""
    seed_account(
        "demo", "demo@example.com", premium=True, opening=25000, salary=55000, months=6,
        expenses=[("Rent", "Rent", 12000, "Net Banking"), ("Groceries", "Food", 5500, "UPI"),
                  ("Metro / Fuel", "Transport", 2000, "UPI"),
                  ("Electricity & Wi-Fi", "Bills", 2500, "Net Banking"),
                  ("Clothes", "Shopping", 3000, "Card"),
                  ("Movies & Dining", "Entertainment", 2000, "Card")],
        kids=[("Aarav", [("School fees", "Education", 4000, "Net Banking"),
                         ("Stationery & snacks", "Shopping", 800, "UPI")]),
              ("Diya", [("Tuition", "Education", 2500, "UPI"),
                        ("Toys & books", "Shopping", 1200, "Card")])],
        holdings=[("Stocks", "Reliance Industries", "RELIANCE.NS", 2400, 10, 2950),
                  ("Stocks", "TCS", "TCS.NS", 3300, 5, 3900),
                  ("Stocks", "Infosys", "INFY.NS", 1650, 15, 1500),   # a loss, shows red
                  ("Stocks", "HDFC Bank", "HDFCBANK.NS", 1600, 12, 1720),
                  ("Gold", "Gold (physical)", None, 6000, 10, 6500),
                  ("Mutual Funds", "Nifty 50 Index Fund", None, 150, 200, 165),
                  ("Fixed Deposit", "SBI Fixed Deposit", None, 50000, 1, 52000),
                  ("Crypto", "Bitcoin", None, 6000000, 0.01, 6500000)])
    seed_account(
        "demo_free", "demo_free@example.com", premium=False, opening=10000, salary=30000, months=3,
        expenses=[("Rent", "Rent", 8000, "Net Banking"), ("Groceries", "Food", 4500, "UPI"),
                  ("Metro / Fuel", "Transport", 1500, "UPI"),
                  ("Electricity & Wi-Fi", "Bills", 2000, "Net Banking"),
                  ("Clothes", "Shopping", 2000, "Card"),
                  ("Movies & Dining", "Entertainment", 1500, "Card")],
        holdings=[("Stocks", "Reliance Industries", "RELIANCE.NS", 2400, 10, 2950),
                  ("Stocks", "TCS", "TCS.NS", 3300, 5, 3900),
                  ("Gold", "Gold (physical)", None, 6000, 10, 6500),
                  ("Fixed Deposit", "SBI Fixed Deposit", None, 50000, 1, 52000)])


# Create tables and seed the demo accounts when the app loads
with app.app_context():
    db.create_all()
    seed_demo()


if __name__ == "__main__":
    app.run(debug=True)