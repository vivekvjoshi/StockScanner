import pandas as pd
import yfinance as yf
import fundamentals
import technical
import scanner_plotting
import sys

def main():
    print("=== Starting Cup and Handle Scanner ===")
    
    # 1. Fundamental Screening
    # Fetch full list or limit? Let's use limit for testing if arg provided
    limit = None
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])
        print(f"DEBUG MODE: Limiting to top {limit} stocks.")
    
    print("Step 1: Fundamental Screening (Market Cap > 5B, Profitable being verified...)")
    candidates = fundamentals.get_filtered_universe(limit=limit)
    
    if not candidates:
        print("No stocks passed fundamental screening.")
        return

    print(f"\nStep 2: Technical Scanning {len(candidates)} candidates...")
    
    results = []
    
    for i, ticker in enumerate(candidates):
        print(f"[{i+1}/{len(candidates)}] Analyzing Chart for {ticker}...", end='\r')
        
        try:
            # Download 2 years of data to be safe
            df = yf.download(ticker, period="2y", interval="1d", progress=False, multi_level_index=False)
            
            if df.empty or len(df) < 200:
                continue
                
            found, details = technical.find_cup_and_handle(df)
            
            if found:
                print(f"\n[MATCH] found for {ticker}!")
                details['ticker'] = ticker
                
                # Generate Plot
                plot_file = scanner_plotting.plot_cup_and_handle(df, ticker, details)
                if plot_file:
                    print(f"  > Chart saved to {plot_file}")
                
                # Get some extra info for the report
                try:
                    info = yf.Ticker(ticker).info
                    details['name'] = info.get('shortName', 'N/A')
                    details['sector'] = info.get('sector', 'N/A')
                    details['market_cap_B'] = round(info.get('marketCap', 0) / 1e9, 1)
                    details['pe_ratio'] = info.get('trailingPE', 'N/A')
                except:
                    pass
                results.append(details)
                
        except Exception as e:
            # print(f"Error scanning {ticker}: {e}")
            pass

    print(f"\n\n=== Scan Complete ===")
    print(f"Found {len(results)} potential setups.")
    
    if results:
        res_df = pd.DataFrame(results)
        # Reorder columns
        cols = ['ticker', 'name', 'sector', 'market_cap_B', 'pe_ratio', 
                'left_rim', 'right_rim', 'cup_depth_pct', 'handle_duration_days', 'handle_retracement_pct']
        # Filter cols to only those that exist
        cols = [c for c in cols if c in res_df.columns]
        res_df = res_df[cols]
        
        print("\nResults:")
        print(res_df.to_string(index=False))
        
        res_df.to_csv('scanner_results.csv', index=False)
        print("\nResults saved to 'scanner_results.csv'")

if __name__ == "__main__":
    main()
