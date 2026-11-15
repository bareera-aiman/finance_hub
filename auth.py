import re
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User

# A Blueprint groups related routes (register/login/logout) in one file
auth = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")   # letters, digits, underscore
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # simple email shape check


@auth.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:          # already logged in -> go to dashboard
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        # --- Validation: collect every problem, then show them all ---
        errors = []
        if not USERNAME_RE.match(username):
            errors.append("Username must be 3-30 characters: letters, numbers, underscore only.")
        if not EMAIL_RE.match(email):
            errors.append("Please enter a valid email address.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        # --- Duplicate checks (case-insensitive) ---
        if User.query.filter(db.func.lower(User.username) == username.lower()).first():
            errors.append("That username is already taken.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
            # send back what they typed (never the password) so they don't retype
            return render_template("register.html", username=username, email=email)

        # --- All good: create the user with a HASHED password ---
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter(db.func.lower(User.username) == username.lower()).first()

        # Same message for "no such user" and "wrong password" so attackers
        # can't discover which usernames exist
        if user is None or not user.check_password(password):
            flash("Invalid username or password.", "danger")
            return render_template("login.html", username=username)

        login_user(user, remember=remember)    # Flask-Login stores the user id in the session
        flash(f"Welcome back, {user.username}!", "success")

        # If they were sent here from a protected page, return them there.
        # Only accept local paths (starting with a single "/") to avoid open redirects.
        next_page = request.args.get("next")
        if next_page and next_page.startswith("/") and not next_page.startswith("//"):
            return redirect(next_page)
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@auth.route("/logout")
@login_required
def logout():
    logout_user()                              # removes the user id from the session
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))