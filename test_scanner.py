import yfinance as yf
import pandas as pd
import numpy as np
from technical import find_cup_and_handle, find_inverse_head_and_shoulders

tickers = ['NVDA', 'TSLA', 'AMD', 'MSFT', 'AAPL', 'META', 'AMZN']

print("--- Starting Diagnostic Scan ---")

for ticker in tickers:
    print(f"\nScanning {ticker}...")
    try:
        # 1. Fetch Data (Same parameters as app.py)
        df = yf.download(ticker, period="730d", interval="1h", progress=False)
        
        if df.empty:
            print(f"❌ {ticker}: No Data")
            continue
            
        # Resample
        ohlc_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }
        
        # Flattent MultiIndex if present
        if isinstance(df.columns, pd.MultiIndex):
             df.columns = df.columns.get_level_values(0)
             
        df_4h = df.resample('4h').agg(ohlc_dict).dropna()
        
        print(f"Data Shapes: 1H={len(df)}, 4H={len(df_4h)}")
        
        if len(df_4h) < 50:
            print(f"❌ {ticker}: Not enough 4H bars ({len(df_4h)})")
            continue
            
        # 2. Run Technical Check
        # We will manually debug the function logic here by replicating it with prints if needed
        # Or just call it and see result
        found, details = find_cup_and_handle(df_4h)
        
        if found:
            print(f"✅ {ticker}: FOUND C&H! Score: {details.get('score')}")
            print(details)
        else:
            print(f"❌ {ticker}: Failed C&H - {details}")
            
            # --- DEBUGGING INSIDE THE FAIL ---
            closes = df_4h['Close'].values
            highs = df_4h['High'].values
            
            lookback_right = min(60, len(closes))
            right_rim_rel = np.argmax(highs[-lookback_right:])
            right_rim_idx = len(highs) - lookback_right + right_rim_rel
            
            print(f"   Debug: Right Rim Index={right_rim_idx}, Price={highs[right_rim_idx]}")
            print(f"   Debug: Bars Since Right={len(closes)-1-right_rim_idx}")
            
    except Exception as e:
        print(f"❌ {ticker}: Error {e}")
