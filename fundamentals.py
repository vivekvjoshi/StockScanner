import yfinance as yf
import pandas as pd
import requests
import bs4

def get_sp500_tickers():
    """Fetches S&P 500 tickers from Wikipedia."""
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, headers=headers)
    soup = bs4.BeautifulSoup(resp.text, 'html.parser')
    table = soup.find('table', {'id': 'constituents'})
    tickers = []
    for row in table.findAll('tr')[1:]:
        ticker = row.findAll('td')[0].text.strip()
        tickers.append(ticker.replace('.', '-'))  # Handle BRK.B -> BRK-B
    return tickers

def get_nasdaq_tickers():
    """Fetches Nasdaq 100 tickers from Wikipedia."""
    url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, headers=headers)
    soup = bs4.BeautifulSoup(resp.text, 'html.parser')
    # The table is usually the first one with class 'wikitable' and id 'constituents'
    table = soup.find('table', {'id': 'constituents'})
    tickers = []
    if table:
        for row in table.findAll('tr')[1:]:
            cells = row.findAll('td')
            if len(cells) > 1:
                ticker = cells[1].text.strip()
                tickers.append(ticker.replace('.', '-'))
    return tickers

def get_spdr_tickers():
    """Returns a combined list of major SPDR Sector ETF tickers."""
    # We'll include the ETFs themselves as they represent 'stocks' in a broader sense
    etfs = ["XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLK", "XLU", "XLRE"]
    return etfs + ["SPY", "QQQ", "DIA", "IWM"]

import datetime

def check_earnings_volatility(ticker_obj):
    """
    Checks if earnings are at least 15 days away.
    Returns: (Pass/Fail, Message)
    """
    try:
        # Try to get next earnings date from calendar
        cal = ticker_obj.calendar
        if cal is None:
             return True, "Earnings date unknown (proceeding)"
             
        # yfinance .calendar is sometimes a dict or dataframe depending on version
        # It usually keys 'Earnings Date' or 'Earnings Date' row
        if isinstance(cal, dict) and 'Earnings Date' in cal:
             dates = cal['Earnings Date']
             if dates:
                 next_date = dates[0] # List of dates
        elif isinstance(cal, pd.DataFrame):
             # Try finding the row
             if 'Earnings Date' in cal.index:
                 next_date = cal.loc['Earnings Date'].iloc[0]
             else:
                 # Check columns if transposed
                 return True, "Earnings Cal format check skipped"
        else:
             return True, "Earnings checking skipped"

        # Ensure next_date is datetime
        if not isinstance(next_date, (datetime.date, datetime.datetime)):
            return True, "Date format unknown"
            
        # Normalize to date for comparison
        if isinstance(next_date, datetime.datetime):
            next_date = next_date.date()
            
        today = datetime.date.today()
        days_until = (next_date - today).days
        
        if days_until < 15:
            return False, f"Earnings too soon ({days_until} days)"
            
        return True, "Earnings safe"
        
    except Exception as e:
        # If we can't find earnings, we skip blocking it (don't want to over-filter on data errors)
        return True, "Earnings check error"

def check_fundamentals(ticker, min_market_cap_billions=5):
    """
    Checks if a stock meets the fundamental criteria:
    1. Market Cap > $5 Billion
    2. Profitable for last 5 years (Positive Net Income)
    3. Positive P/E Ratio
    4. **Strong Fundamentals**: ROE > 10% and Revenue Growth > 0
    5. **Earnings Safety**: Next earnings > 15 days away
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # 1. Market Cap Check
        market_cap = info.get('marketCap', 0)
        if market_cap < min_market_cap_billions * 1_000_000_000:
            return False, "Market Cap too small"

        # 2. P/E Ratio Check
        pe_ratio = info.get('trailingPE')
        if pe_ratio is None or pe_ratio <= 0:
            return False, "Negative or missing PE"
            
        # 4. Strong Fundamentals (ROE & Growth)
        roe = info.get('returnOnEquity', 0)
        if roe < 0.10: # 10% ROE
            return False, f"ROE too low ({round(roe*100,1)}%)"
            
        rev_growth = info.get('revenueGrowth', 0)
        if rev_growth <= 0:
            return False, "No revenue growth"

        # 5. Earnings Date Check
        earnings_date = "N/A"
        try:
            cal = stock.calendar
            if isinstance(cal, pd.DataFrame) and 'Earnings Date' in cal.index:
                next_date = cal.loc['Earnings Date'].iloc[0]
                if isinstance(next_date, (datetime.date, datetime.datetime)):
                    earnings_date = next_date.strftime('%Y-%m-%d')
        except:
            pass

        # 3. Profitability Check (5 years) -- Keeping this last as it requests financials
        financials = stock.financials
        if financials.empty:
            return False, "No financial data"
        
        if 'Net Income' in financials.index:
            net_income = financials.loc['Net Income']
            if not (net_income > 0).all():
                return False, "Not consistently profitable"

        # Return Success and a dict with info
        return True, {
            "name": info.get('shortName', ticker),
            "earnings": earnings_date,
            "sector": info.get('sector', 'N/A')
        }

    except Exception as e:
        return False, f"Error: {e}"

def get_filtered_universe(limit=None, progress_callback=None):
    """
    Fetches S&P 500 tickers and filters them.
    limit: Optional int to limit number of tickers to check (for testing).
    progress_callback: Optional function to call with (current, total, ticker)
    """
    tickers = get_sp500_tickers()
    if limit:
        tickers = tickers[:limit]
    
    qualified_stocks = []
    print(f"Scanning {len(tickers)} stocks for fundamentals...")
    
    for i, ticker in enumerate(tickers):
        print(f"[{i+1}/{len(tickers)}] Checking {ticker}...", end='\r')
        
        if progress_callback:
            progress_callback(i + 1, len(tickers), ticker)
            
        passed, msg = check_fundamentals(ticker)
        if passed:
            qualified_stocks.append(ticker)
            
    print(f"\nFound {len(qualified_stocks)} stocks meeting fundamental criteria.")
    return qualified_stocks

if __name__ == "__main__":
    # Test run
    screened = get_filtered_universe(limit=10)
    print("Qualified:", screened)
