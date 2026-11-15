# Optional live prices. If anything goes wrong we return None and the app keeps the old price.

def fetch_price(symbol):
    """Latest closing price for a symbol like RELIANCE.NS, or None on any failure."""
    try:
        import yfinance as yf          # imported here so the app still runs without yfinance
        history = yf.Ticker(symbol).history(period="5d")
        if history.empty:
            return None
        price = float(history["Close"].iloc[-1])
        return price if price > 0 else None    # also rejects nan
    except Exception:
        return None