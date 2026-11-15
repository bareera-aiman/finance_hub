from datetime import date

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import current_user

from billing import premium_required
from calculators import education_goal
from models import db, Child, Expense

kids = Blueprint("kids", __name__, url_prefix="/kids")
MAX_CHILDREN = 10


def spending_on(child):
    """Expenses tagged to this child. Always filtered by the logged-in user as well."""
    return (Expense.query
            .filter_by(user_id=current_user.id, child_id=child.id, type="expense")
            .order_by(Expense.date.desc(), Expense.id.desc()).all())


def split_totals(expenses):
    """(all-time total, this-month total) for a list of expenses."""
    month_start = date.today().replace(day=1)
    return (sum(e.amount for e in expenses),
            sum(e.amount for e in expenses if e.date >= month_start))


@kids.route("/")
@premium_required
def index():
    children = Child.query.filter_by(user_id=current_user.id).order_by(Child.nickname).all()
    cards, grand_total = [], 0
    for child in children:
        expenses = spending_on(child)
        total, this_month = split_totals(expenses)
        cards.append({"child": child, "total": total, "this_month": this_month,
                      "count": len(expenses)})
        grand_total += total
    return render_template("kids.html", cards=cards, grand_total=grand_total)


@kids.route("/add", methods=["POST"])
@premium_required
def add_child():
    nickname = request.form.get("nickname", "").strip()
    mine = Child.query.filter_by(user_id=current_user.id)

    if not nickname or len(nickname) > 50:
        flash("Please enter a nickname (up to 50 characters).", "danger")
    elif mine.filter(db.func.lower(Child.nickname) == nickname.lower()).first():
        flash("You already have a child with that nickname.", "danger")
    elif mine.count() >= MAX_CHILDREN:
        flash(f"You can add up to {MAX_CHILDREN} children.", "warning")
    else:
        db.session.add(Child(user_id=current_user.id, nickname=nickname))
        db.session.commit()
        flash(f"{nickname} added.", "success")
    return redirect(url_for("kids.index"))


@kids.route("/<int:child_id>")
@premium_required
def detail(child_id):
    # Look up by id AND user_id: someone else's child gives a 404
    child = Child.query.filter_by(id=child_id, user_id=current_user.id).first_or_404()
    expenses = spending_on(child)
    total, this_month = split_totals(expenses)

    by_category = {}                                    # for the doughnut chart
    for e in expenses:
        by_category[e.category] = by_category.get(e.category, 0) + e.amount

    return render_template("kid_detail.html", child=child, expenses=expenses, total=total,
                           this_month=this_month, cat_labels=list(by_category.keys()),
                           cat_values=list(by_category.values()))


@kids.route("/<int:child_id>/delete", methods=["POST"])
@premium_required
def delete_child(child_id):
    child = Child.query.filter_by(id=child_id, user_id=current_user.id).first_or_404()
    # The expenses stay; they just stop being tagged to this child
    Expense.query.filter_by(user_id=current_user.id, child_id=child.id).update({"child_id": None})
    db.session.delete(child)
    db.session.commit()
    flash("Child profile deleted. The expenses were kept.", "info")
    return redirect(url_for("kids.index"))


@kids.route("/education")
@premium_required
def education():
    # First visit shows default values. Later visits read ?target=...&years=...&inflation=...&rate=...
    form = {"target": "1000000", "years": "10", "inflation": "8", "rate": "12"}
    if request.args:
        form = {key: request.args.get(key, "").strip() for key in form}

    errors = []
    target = years = inflation = rate = None
    try:
        target = float(form["target"])
        if not (1000 <= target <= 1_000_000_000):       # also rejects nan / inf
            raise ValueError
    except ValueError:
        errors.append("Today's cost must be between ₹1,000 and ₹100 crore.")
    try:
        years = int(form["years"])
        if not (1 <= years <= 30):
            raise ValueError
    except ValueError:
        errors.append("Years left must be a whole number between 1 and 30.")
    try:
        inflation = float(form["inflation"])
        if not (0 <= inflation <= 30):
            raise ValueError
    except ValueError:
        errors.append("Education inflation must be between 0% and 30%.")
    try:
        rate = float(form["rate"])
        if not (0 <= rate <= 50):
            raise ValueError
    except ValueError:
        errors.append("Expected return must be between 0% and 50%.")

    result = None
    if errors:
        for e in errors:
            flash(e, "danger")
    else:
        result = education_goal(target, years, inflation, rate)   # maths is in calculators.py

    return render_template("education.html", form=form, result=result)