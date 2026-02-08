"""
Full App Flow Diagnostic - Mimics app.py exactly
"""
import yfinance as yf
import pandas as pd
import numpy as np
from tradingview_screener import Query, Column
from technical import find_cup_and_handle, find_inverse_head_and_shoulders

print("=" * 80)
print("STEP 1: TradingView Screener Query")
print("=" * 80)

try:
    q = Query().select('name', 'close', 'volume', 'market_cap_basic', 'relative_volume_10d_calc', 'change').where(
        Column('market_cap_basic') > 15_000_000_000, 
        Column('volume') > 500_000,
        Column('close') > Column('SMA200'),
    ).limit(300)
    
    total_count, results_df = q.get_scanner_data()
    
    print(f"✓ Total Candidates Found: {total_count}")
    print(f"✓ Results DataFrame Shape: {results_df.shape}")
    print(f"\nFirst 10 tickers:")
    tickers = results_df['name'].tolist()[:10]
    print(tickers)
    
except Exception as e:
    print(f"✗ TradingView Error: {e}")
    import traceback
    traceback.print_exc()
    exit()

print("\n" + "=" * 80)
print("STEP 2: Data Fetching & Pattern Detection (First 5 stocks)")
print("=" * 80)

test_tickers = tickers[:5]

for ticker in test_tickers:
    print(f"\n{'─' * 60}")
    print(f"Testing: {ticker}")
    print(f"{'─' * 60}")
    
    try:
        # Fetch data EXACTLY as app.py does
        df = yf.download(ticker, period="730d", interval="1h", progress=False)
        
        if df.empty:
            print(f"  ✗ No data returned from yfinance")
            continue
            
        print(f"  ✓ Downloaded {len(df)} hourly bars")
        
        # Check column structure
        print(f"  Columns: {df.columns.tolist()}")
        print(f"  Is MultiIndex: {isinstance(df.columns, pd.MultiIndex)}")
        
        # Flatten MultiIndex if present (EXACTLY as app.py)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            print(f"  Flattened to: {df.columns.tolist()}")
            
        # Resample to 4H (EXACTLY as app.py)
        ohlc_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }
        
        df_4h = df.resample('4h').agg(ohlc_dict).dropna()
        print(f"  ✓ Resampled to {len(df_4h)} 4H bars")
        
        if len(df_4h) < 50:
            print(f"  ✗ Not enough 4H data ({len(df_4h)} bars)")
            continue
            
        # Run Cup & Handle Detection (EXACTLY as app.py)
        print(f"  Running Cup & Handle detection...")
        found, result = find_cup_and_handle(df_4h)
        
        if found:
            score = result.get('score', 0)
            print(f"  ✓✓ PATTERN FOUND! Score: {score}")
            print(f"     Pivot: ${result.get('pivot'):.2f}")
            print(f"     Status: {result.get('status')}")
            
            if score > 75:
                print(f"  ✓✓✓ PASSES AI SCORE THRESHOLD (>75)!")
            else:
                print(f"  ✗ Score {score} < 75 threshold")
        else:
            print(f"  ✗ No pattern: {result}")
            
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 80)
print("DIAGNOSIS COMPLETE")
print("=" * 80)
