import yfinance as yf
import pandas as pd
import numpy as np
import datetime

SPDR_SECTORS = {
    "XLK": "Technology",
    "XLV": "Health Care",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLC": "Communication Services",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "SPY": "S&P 500 Index"
}

def calculate_rsi(series, periods=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_wheel_data(ticker, name):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="1y")
        if df.empty:
            return None
            
        current_price = df['Close'].iloc[-1]
        
        # Indicators
        rsi = calculate_rsi(df['Close']).iloc[-1]
        ma200 = df['Close'].rolling(200).mean().iloc[-1]
        dist_ma200 = ((current_price - ma200) / ma200) * 100 if ma200 else 0
        
        # Info
        info = t.info
        div_yield = info.get('dividendYield', 0)
        
        # Simple status logic
        if rsi < 40:
            status = "📉 Oversold / High Put Premium Potential"
        elif rsi > 60:
            status = "🔥 Overextended / Wait for Pullback"
        else:
            status = "⚖️ Neutral Trend"
            
        # Get IV from options (first expiration ATM)
        iv = "N/A"
        try:
            options = t.options
            if options:
                chain = t.option_chain(options[0])
                puts = chain.puts
                # Find ATM put
                idx = (puts['strike'] - current_price).abs().idxmin()
                iv = f"{round(puts.loc[idx, 'impliedVolatility'] * 100, 1)}%"
        except:
            pass

        # Get next earnings date
        earnings_date = "N/A"
        try:
            cal = t.calendar
            if isinstance(cal, pd.DataFrame) and 'Earnings Date' in cal.index:
                next_date = cal.loc['Earnings Date'].iloc[0]
                if isinstance(next_date, (datetime.date, datetime.datetime)):
                    earnings_date = next_date.strftime('%Y-%m-%d')
        except:
            pass

        return {
            "Ticker": ticker,
            "Name": name,
            "Price": round(current_price, 2),
            "IV": iv,
            "RSI": round(rsi, 1),
            "vs 200MA %": round(dist_ma200, 1),
            "Yield": f"{round(div_yield * 100, 2)}%" if div_yield else "0.0%",
            "Earnings": earnings_date,
            "Status": status
        }
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None
