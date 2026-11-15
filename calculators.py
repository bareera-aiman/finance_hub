import math
# All financial maths lives here, separate from Flask, so it is easy to test and explain.

# ---------- SIP calculator (Step 5) ----------

def sip_future_value(monthly, annual_rate, months):
    """FV = P x [((1+r)^n - 1) / r] x (1+r), with r = annual rate / 12 / 100."""
    r = annual_rate / 12 / 100          # monthly rate as a decimal
    if r == 0:                          # avoid dividing by zero when the return is 0%
        return monthly * months
    return monthly * (((1 + r) ** months - 1) / r) * (1 + r)


def sip_summary(monthly, annual_rate, years):
    """Totals plus year-by-year numbers for the growth chart."""
    months = years * 12
    invested = monthly * months
    future_value = round(sip_future_value(monthly, annual_rate, months))

    # One point per year (Year 0 = start) for the line chart
    labels, invested_series, value_series = [], [], []
    for y in range(years + 1):
        labels.append(f"Year {y}")
        invested_series.append(round(monthly * y * 12))
        value_series.append(round(sip_future_value(monthly, annual_rate, y * 12)))

    return {
        "invested": round(invested),
        "future_value": future_value,
        "returns": future_value - round(invested),
        "labels": labels,
        "invested_series": invested_series,
        "value_series": value_series,
    }


# ---------- Portfolio profit / loss (Step 6) ----------

def holding_stats(buy_price, quantity, current_price):
    """Numbers for ONE holding."""
    invested = buy_price * quantity
    current_value = current_price * quantity
    pl = current_value - invested                          # profit (+) or loss (-) in rupees
    pl_pct = (pl / invested * 100) if invested else 0      # guard against dividing by zero
    return {"invested": invested, "current_value": current_value,
            "pl": pl, "pl_pct": pl_pct}


def portfolio_summary(holdings):
    """Per-holding rows plus totals for the whole portfolio."""
    rows = []
    total_invested = total_value = 0
    for h in holdings:
        stats = holding_stats(h.buy_price, h.quantity, h.current_price)
        rows.append({"holding": h, **stats})               # **stats copies the numbers into the row
        total_invested += stats["invested"]
        total_value += stats["current_value"]

    total_pl = total_value - total_invested
    return {
        "rows": rows,
        "invested": total_invested,
        "value": total_value,
        "pl": total_pl,
        "pl_pct": (total_pl / total_invested * 100) if total_invested else 0,
    }


# ---------- Dashboard: SIP suggestion and projection (Step 7) ----------

def suggest_sip(avg_savings, share=0.5):
    """Suggest investing a share (default 50%) of monthly savings, rounded down to the nearest ₹100."""
    if avg_savings <= 0:
        return 0                                   # nothing saved, nothing to invest
    return int(avg_savings * share // 100 * 100)


def lump_sum_value(amount, annual_rate, months):
    """Growth of a one-time amount: A x (1 + r)^n, using the same monthly rate as the SIP."""
    r = annual_rate / 12 / 100
    return amount * (1 + r) ** months


def savings_projection(portfolio_value, monthly_sip, annual_rate, years):
    """Year-by-year growth of (a) the current portfolio alone and (b) portfolio + suggested SIP."""
    labels, portfolio_only, combined = [], [], []
    for y in range(years + 1):
        months = y * 12
        base = round(lump_sum_value(portfolio_value, annual_rate, months))
        extra = round(sip_future_value(monthly_sip, annual_rate, months))
        labels.append(f"Year {y}")
        portfolio_only.append(base)
        combined.append(base + extra)
    return {
        "labels": labels,
        "portfolio_only": portfolio_only,
        "combined": combined,
        "portfolio_final": portfolio_only[-1],
        "sip_final": combined[-1] - portfolio_only[-1],
        "combined_final": combined[-1],
    }

# ---------- Balance and net worth (part b) ----------

def balance_summary(opening_balance, total_income, total_expense, investment_value):
    """Total balance, and net worth = balance + current value of investments."""
    balance = opening_balance + total_income - total_expense
    return {"balance": balance, "net_worth": balance + investment_value}

# ---------- Allocation by asset type (part c) ----------

def allocation_by_type(rows):
    """Group portfolio rows by asset type: [{'type', 'value', 'pct'}], biggest first."""
    totals = {}
    for r in rows:
        kind = r["holding"].asset_type
        totals[kind] = totals.get(kind, 0) + r["current_value"]
    grand_total = sum(totals.values())
    return [{"type": kind, "value": value,
             "pct": (value / grand_total * 100) if grand_total else 0}
            for kind, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)]

# ---------- Education goal planner (part e) ----------

def sip_required(target, annual_rate, months):
    """Monthly SIP needed to reach 'target': the SIP formula solved for P."""
    r = annual_rate / 12 / 100
    if r == 0:
        return target / months
    factor = ((1 + r) ** months - 1) / r * (1 + r)     # value of Rs. 1 invested every month
    return target / factor


def education_goal(target_today, years, inflation_pct, annual_rate):
    """The cost grows with education inflation; find the monthly SIP that reaches it."""
    future_cost = target_today * (1 + inflation_pct / 100) ** years     # cost after N years
    months = years * 12
    monthly = math.ceil(sip_required(future_cost, annual_rate, months))  # round UP so the goal is met

    labels, cost_series, sip_series = [], [], []
    for y in range(years + 1):                         # one point per year for the chart
        labels.append(f"Year {y}")
        cost_series.append(round(target_today * (1 + inflation_pct / 100) ** y))
        sip_series.append(round(sip_future_value(monthly, annual_rate, y * 12)))

    invested = monthly * months
    return {"future_cost": round(future_cost), "monthly_sip": monthly, "invested": invested,
            "growth": sip_series[-1] - invested, "labels": labels,
            "cost_series": cost_series, "sip_series": sip_series}