# Personal Finance Hub

A full-stack web app for managing personal money in one place. Users register, log in, and use three modules that share one database: an **expense tracker**, an **investment portfolio** and a **SIP calculator**. A **dashboard** ties them together: it works out your average monthly savings, suggests a SIP amount, and projects how that SIP and your current portfolio could grow. A **Premium** plan adds a kids spending module, an education goal planner, more asset types and CSV export.

Built as a college mini project. Currency is INR (₹).

**Live demo:** _add the PythonAnywhere link here after deployment_

## Features

**Accounts and security**
- Register, login and logout, with duplicate username and email checks and flash messages
- Passwords hashed with Werkzeug (`generate_password_hash` / `check_password_hash`)
- Sessions handled by Flask-Login; every page except login and register uses `@login_required`
- Every user-owned table has a `user_id` foreign key, and every query filters by the logged-in user, so users only ever see their own data

**Expense tracker**
- Add, edit and delete income and expenses, with categories and a payment mode (Cash, UPI, Card, Net Banking)
- Monthly summary, a doughnut chart by category and a bar chart of the last six months
- Total balance = opening balance + income − expenses (future-dated entries are not counted yet)

**Investment portfolio**
- 12 asset types (Stocks, Mutual Funds, ETFs, Gold, Silver, Bonds, Fixed Deposit, PPF/EPF, NPS, Real Estate/Land, Crypto, Other), each with its own unit (shares, grams, sq ft and so on)
- Manual current prices; invested amount, current value and profit or loss in ₹ and %
- Allocation chart grouped by asset type
- Optional live prices for listed stocks through yfinance (fails gracefully when offline)

**SIP calculator**
- Monthly amount, expected return and years give the invested amount, estimated returns, future value and a growth chart
- `FV = P × [((1+r)^n − 1) / r] × (1+r)`, with `r = annual rate / 12 / 100` and `n = years × 12`

**Dashboard (the creative twist)**
- Average monthly savings over the last 3 months, a suggested SIP (50% of savings, rounded down to ₹100) and a projection chart: current portfolio alone vs portfolio + suggested SIP
- Total balance and net worth (balance + investments)

**Premium features**
- Kids spending: child profiles (nickname only), an optional child tag on expenses, per-child totals and a category chart
- Child education goal planner: today's cost, years left, education inflation and expected return give the monthly SIP needed
- All 12 asset types, unlimited holdings and CSV export

## Free vs Premium

| | Free | Premium (₹99/month, shown) |
|---|---|---|
| Expenses, SIP calculator, dashboard | Yes | Yes |
| Asset types | Stocks, Mutual Funds, Gold, Fixed Deposit | All 12 |
| Holdings | Up to 5 | Unlimited |
| Kids module and education planner | No | Yes |
| CSV export | No | Yes |

All limits are enforced **on the server** in the route code, not only by hiding buttons.

## About the payment flow (demo)

The upgrade flow is a **demo** and is **not confirmed automatically**:

1. "Upgrade" creates a payment request with a unique test amount (₹1 plus random paise) that expires in 30 minutes.
2. The page shows a UPI QR code built from a `upi://pay` link. The UPI ID comes from an environment variable.
3. The user pays, then enters the 12-digit UTR from their payment confirmation.
4. An admin compares the amount and UTR with the bank statement and presses Approve or Reject.
5. Approval sets the plan to premium for 30 days. When the date passes, the account is downgraded automatically. No data is deleted.

A production system would use a payment gateway with signed webhooks instead of manual approval.

## Tech stack

Python, Flask, Flask-SQLAlchemy (SQLite), Flask-Login, Jinja templates, Bootstrap 5, Chart.js, `qrcode`.

## Project structure

```
finance_hub/
├── app.py            routes: dashboard, expenses, SIP, portfolio, CSV export, demo seed
├── auth.py           register, login, logout
├── billing.py        pricing, UPI payment flow, admin approval, plan decorators
├── kids.py           kids module and education goal planner
├── calculators.py    all the maths (SIP, profit/loss, balance, projections)
├── models.py         User, Expense, Holding, Child, PaymentRequest
├── config.py         settings read from environment variables
├── prices.py         optional live prices (yfinance)
├── reset_demo.py     recreate the demo accounts with fresh dates
├── make_admin.py     give an existing user admin rights
├── migrate_a.py      database migrations used while extending the project
├── migrate_c.py
├── requirements.txt
├── templates/        Jinja templates (base layout, pages, forms)
└── static/           style.css (theme variables), charts.js (shared chart helpers)
```

## Run locally

```bash
python -m venv venv
venv\Scripts\activate            # Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

The database (`finance.db`) and two demo accounts are created automatically on first run.

| Account | Password | Plan |
|---|---|---|
| `demo` | `demo123` | Premium, with six months of data and two children |
| `demo_free` | `demo123` | Free |

New users register with an empty account and add everything manually.

Run `python reset_demo.py` to rebuild both demo accounts with fresh dates.

## Configuration (environment variables)

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs the session cookie. **Required in production.** Without it, a random key is generated on each start (fine for local testing only). |
| `UPI_ID` | Receiving UPI ID for the demo payment page. Never commit it. Without it, the Upgrade button shows a "payments are not set up" message. |
| `UPI_PAYEE_NAME` | Optional name shown in the UPI app (default "FinanceHub Demo"). |

Windows (Command Prompt): `set UPI_ID=yourid@bank`. Mac/Linux: `export UPI_ID=yourid@bank`.

Optional live prices: `pip install yfinance`.

## Admin

Admins are created from the terminal only, never through the website:

```bash
python make_admin.py <username>
```

The user must already be registered. Admins get a "Payments (admin)" page for approving or rejecting submitted payments.

## Security notes

- Passwords are hashed with a salt (Werkzeug), never stored in plain text
- Session cookie flags: `HttpOnly` and `SameSite=Lax`
- Edit and delete routes look records up by id **and** `user_id`, so another user's record returns 404
- Deletes are POST-only; redirect-after-POST avoids duplicate submissions
- All form input is validated on the server (ranges, allowed values, NaN and infinity rejected)
- CSV export neutralises spreadsheet formula injection
- The secret key and UPI ID are read from environment variables, never from the code

## Limitations and future improvements

- No CSRF tokens on forms yet (Flask-WTF would add them)
- Money is stored as floats and rounded for display; production code should use `Decimal` or integer paise
- No email verification or password reset
- Premium payments are verified manually; a payment gateway with webhooks would automate this
- Projections assume constant returns and inflation, and ignore taxes and charges. They are estimates, not financial advice
- Schema changes use small migration scripts; Flask-Migrate (Alembic) would be the standard tool
- Ideas: natural-language expense entry, automated tests for `calculators.py`, pagination for long transaction lists

## Screenshots

_Add screenshots of the dashboard, expenses, portfolio and kids pages here._