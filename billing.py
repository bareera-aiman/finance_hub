import os
import random
import re
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import quote

import qrcode
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, abort, current_app)
from flask_login import login_required, current_user
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError

from models import db, PaymentRequest

billing = Blueprint("billing", __name__)

# ---------- Plan settings ----------
PREMIUM_PRICE = 99            # shown on the pricing page (rupees per month)
PREMIUM_DAYS = 30             # how long one approval lasts
REQUEST_MINUTES = 30          # time allowed to pay and submit the UTR
FREE_HOLDING_LIMIT = 5        # free plan: maximum number of holdings
UTR_RE = re.compile(r"[0-9]{12}")


# ---------- Decorators: checks done on the SERVER ----------
def premium_required(view):
    """Allow the page only for logged-in users with an active Premium plan."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_premium:
            flash("That feature is part of the Premium plan.", "warning")
            return redirect(url_for("billing.pricing"))
        return view(*args, **kwargs)
    return login_required(wrapped)          # login is checked first


def admin_required(view):
    """Allow the page only for logged-in admins (everyone else gets 403 Forbidden)."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return login_required(wrapped)


# ---------- Helpers ----------
def build_upi_link(upi_id, payee_name, amount, note="FinanceHub Demo"):
    """The text that goes inside the QR code. UPI apps read pa=payee, am=amount, tn=note."""
    return (f"upi://pay?pa={quote(upi_id, safe='@')}&pn={quote(payee_name)}"
            f"&am={amount:.2f}&cu=INR&tn={quote(note)}")


def qr_svg(text):
    """Draw a QR code as inline SVG: one black square for every 'on' cell of the QR matrix."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    matrix = qr.get_matrix()                 # list of rows of True/False
    size = len(matrix)
    squares = "".join(f'<rect x="{x}" y="{y}" width="1" height="1"/>'
                      for y, row in enumerate(matrix) for x, on in enumerate(row) if on)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
            f'shape-rendering="crispEdges"><rect width="{size}" height="{size}" fill="#fff"/>'
            f'<g fill="#000">{squares}</g></svg>')


def new_unique_amount():
    """Rs. 1 + random paise (1.01 to 1.99), different from every request still waiting."""
    now = datetime.utcnow()
    waiting = PaymentRequest.query.filter(
        or_(PaymentRequest.status == "submitted",
            and_(PaymentRequest.status == "pending", PaymentRequest.expires_at > now))).all()
    used = {r.amount for r in waiting}
    choices = [round(1 + paise / 100, 2) for paise in range(1, 100)
               if round(1 + paise / 100, 2) not in used]
    return random.choice(choices) if choices else None


def find_open_request(user_id):
    """The user's request that is still alive: submitted, or pending and not expired."""
    now = datetime.utcnow()
    return (PaymentRequest.query
            .filter(PaymentRequest.user_id == user_id,
                    or_(PaymentRequest.status == "submitted",
                        and_(PaymentRequest.status == "pending", PaymentRequest.expires_at > now)))
            .order_by(PaymentRequest.id.desc()).first())


# ---------- Pricing and payment pages ----------
@billing.route("/pricing")
@login_required
def pricing():
    return render_template("pricing.html", price=PREMIUM_PRICE, free_limit=FREE_HOLDING_LIMIT,
                           open_request=find_open_request(current_user.id))


@billing.route("/upgrade", methods=["POST"])
@login_required
def upgrade():
    if current_user.is_premium:
        flash("You are already on Premium.", "info")
        return redirect(url_for("billing.pricing"))
    if not current_app.config.get("UPI_ID"):
        flash("Payments are not set up on this server (the UPI_ID setting is missing).", "danger")
        return redirect(url_for("billing.pricing"))

    pr = find_open_request(current_user.id)          # reuse a live request instead of making many
    if pr is None:
        amount = new_unique_amount()
        if amount is None:
            flash("Too many payments are in progress. Please try again in a few minutes.", "warning")
            return redirect(url_for("billing.pricing"))
        pr = PaymentRequest(user_id=current_user.id, amount=amount,
                            expires_at=datetime.utcnow() + timedelta(minutes=REQUEST_MINUTES))
        db.session.add(pr)
        db.session.commit()
    return redirect(url_for("billing.payment", request_id=pr.id))


@billing.route("/payment/<int:request_id>")
@login_required
def payment(request_id):
    # Owner only: someone else's request gives a 404
    pr = PaymentRequest.query.filter_by(id=request_id, user_id=current_user.id).first_or_404()
    now = datetime.utcnow()
    expired = pr.status == "pending" and pr.expires_at <= now

    qr, upi_link = None, None
    upi_id = current_app.config.get("UPI_ID")
    if pr.status == "pending" and not expired and upi_id:
        upi_link = build_upi_link(upi_id, current_app.config["UPI_PAYEE_NAME"], pr.amount)
        qr = qr_svg(upi_link)

    return render_template("payment.html", pr=pr, expired=expired, qr=qr, upi_link=upi_link,
                           seconds_left=max(0, int((pr.expires_at - now).total_seconds())))


@billing.route("/payment/<int:request_id>/submit", methods=["POST"])
@login_required
def submit_utr(request_id):
    pr = PaymentRequest.query.filter_by(id=request_id, user_id=current_user.id).first_or_404()
    back = redirect(url_for("billing.payment", request_id=pr.id))
    utr = request.form.get("utr", "").strip()

    if pr.status != "pending":
        flash(f"This payment request is already {pr.status}.", "info")
        return back
    if pr.expires_at <= datetime.utcnow():
        flash("This request has expired. Please start a new one from the Pricing page.", "warning")
        return back
    if not UTR_RE.fullmatch(utr):
        flash("The UTR must be exactly 12 digits.", "danger")
        return back

    pr.utr = utr
    pr.status = "submitted"
    try:
        db.session.commit()
    except IntegrityError:                           # the UTR column is unique
        db.session.rollback()
        flash("That UTR has already been used for another request.", "danger")
        return back

    flash("UTR submitted. An admin will check it manually. Premium is NOT active until it is approved.",
          "success")
    return back


# ---------- Admin: manual verification ----------
@billing.route("/admin/payments")
@admin_required
def admin_payments():
    submitted = (PaymentRequest.query.filter_by(status="submitted")
                 .order_by(PaymentRequest.created_at).all())
    recent = (PaymentRequest.query.filter(PaymentRequest.status.in_(["approved", "rejected"]))
              .order_by(PaymentRequest.decided_at.desc()).limit(10).all())
    return render_template("admin_payments.html", submitted=submitted, recent=recent,
                           days=PREMIUM_DAYS)


@billing.route("/admin/payments/<int:request_id>/<action>", methods=["POST"])
@admin_required
def decide_payment(request_id, action):
    if action not in ("approve", "reject"):
        abort(404)
    pr = db.get_or_404(PaymentRequest, request_id)
    if pr.status != "submitted":                     # stops a double click approving twice
        flash("That request was already handled.", "info")
        return redirect(url_for("billing.admin_payments"))

    now = datetime.utcnow()
    pr.decided_at = now
    if action == "approve":
        user = pr.user
        # If the user is still premium, extend from their end date; otherwise start today
        start = user.premium_until if (user.premium_until and user.premium_until > now) else now
        user.plan = "premium"
        user.premium_until = start + timedelta(days=PREMIUM_DAYS)
        pr.status = "approved"
        flash(f"Approved. {user.username} is Premium until {user.premium_until:%d %b %Y}.", "success")
    else:
        pr.status = "rejected"
        flash("Request rejected.", "info")
    db.session.commit()
    return redirect(url_for("billing.admin_payments"))