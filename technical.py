import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from scipy.stats import linregress

def calculate_mas(df):
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    df['VolSMA50'] = df['Volume'].rolling(window=50).mean()
    return df

def check_trend_template(df):
    """
    Minervini-style Trend Template (Simplified for 4H/Daily usage)
    """
    if len(df) < 200: return False, "Not enough data"
    
    current = df.iloc[-1]
    
    # 1. Moving Averages
    if not (current['Close'] > current['SMA50'] > current['SMA200']):
        return False, "Not in Uptrend (Close > 50 > 200)"
        
    return True, "Trend OK"

def check_volume_breakout(df):
    """
    Breakout Volume > 1.4x (40% above) 50-day Avg Vol
    """
    current_vol = df['Volume'].iloc[-1]
    avg_vol = df['VolSMA50'].iloc[-1]
    if pd.isna(avg_vol): return False
    return current_vol > (avg_vol * 1.40)

def find_cup_and_handle(df, spy_df=None):
    """
    Fuzzy Heuristic Cup & Handle Detection.
    Finds: High (Left) -> Low (Bottom) -> High (Right) -> Consolidation (Handle)
    """
    # Need at least ~60 bars
    if len(df) < 60: return False, f"Not enough data ({len(df)})"
    
    df = calculate_mas(df)
    
    closes = df['Close'].values
    highs = df['High'].values
    lows = df['Low'].values
    
    # 1. Identify Potential Right Rim (Recent High in last ~45 bars)
    # We look for a high point that acts as the pivot
    lookback_right = min(60, len(closes))
    
    # Find max in last 60 bars (approx 2-4 weeks 4H)
    right_rim_rel_idx = np.argmax(highs[-lookback_right:])
    right_rim_idx = len(highs) - lookback_right + right_rim_rel_idx
    right_rim_price = highs[right_rim_idx]
    
    # 2. Check Handle (Price since Right Rim)
    bars_since_right = len(closes) - 1 - right_rim_idx
    
    # If right rim is too old (> 45 bars), pattern fails
    if bars_since_right > 45:
        return False, f"Right rim too old ({bars_since_right} bars)"
        
    # 3. Identify Left Rim (High point BEFORE Right Rim)
    # Search window: from 250 bars ago up to Right Rim - 8 bars
    search_end = right_rim_idx - 8
    
    if search_end < 20: 
        return False, "Pattern too short"
    
    search_start = max(0, search_end - 250)
    
    # Find highest point in that window
    left_rim_idx = np.argmax(highs[search_start:search_end]) + search_start
    left_rim_price = highs[left_rim_idx]
    
    # 4. Check Rim Alignment
    # Left Rim should be somewhat close to Right Rim (0.75 to 1.35)
    ratio = left_rim_price / right_rim_price
    if not (0.75 <= ratio <= 1.35):
        return False, f"Rim mismatch {left_rim_price:.2f}/{right_rim_price:.2f}"
        
    # 5. Check for Cup Bottom (Lowest point between Rims)
    cup_slice = lows[left_rim_idx:right_rim_idx]
    if len(cup_slice) < 5: return False, "Cup too narrow"
    
    cup_bottom_price = np.min(cup_slice)
    cup_depth_pct = 1.0 - (cup_bottom_price / max(left_rim_price, right_rim_price))
    
    # Depth Check: 8% to 60% (Broad range)
    if not (0.08 <= cup_depth_pct <= 0.60):
        return False, f"Depth invalid ({cup_depth_pct*100:.1f}%)"
        
    # 6. Handle Validation
    score = 60
    status = "Forming"
    
    if bars_since_right > 0:
        handle_slice = lows[right_rim_idx:]
        handle_low = np.min(handle_slice)
        
        # Max handle depth relative to Right Rim
        handle_depth_pct = 1.0 - (handle_low / right_rim_price)
        
        # Handle shouldn't drop more than 22% usually
        if handle_depth_pct > 0.22: 
             return False, f"Handle too deep ({handle_depth_pct*100:.1f}%)"
             
        # Check if we are near breakout (current price vs Right Rim)
        current_price = closes[-1]
        
        # Must be in upper part of handle (within 12% of rim)
        # If it dropped too much, it's failed handle
        if current_price < right_rim_price * 0.88:
             return False, "Price rejected (too far below rim)"
             
        if current_price >= right_rim_price * 0.98:
            status = "Breakout!"
            score += 20
        elif current_price >= right_rim_price * 0.95:
             status = "Near Pivot"
             score += 10
             
    # Bonus points
    if 0.9 <= ratio <= 1.1: score += 10 # Symmetry

    pattern_details = {
        "pattern": "Cup & Handle (Fuzzy)",
        "pivot": float(right_rim_price), 
        "stop_loss": float(cup_bottom_price),
        "target_price": float(right_rim_price + (right_rim_price - cup_bottom_price)),
        "left_rim": float(left_rim_price),
        "right_rim": float(right_rim_price),
        "bottom": float(cup_bottom_price),
        "score": score,
        "status": status,
        "ai_score": score # Default
    }
    
    return True, pattern_details

def find_inverse_head_and_shoulders(df):
    """
    Simplified IHS Detection.
    """
    if len(df) < 60: return False, "Not enough data"
    
    prices = df['Close'].values
    # Using order=5 for local troughs
    order = 5
    min_idxs = argrelextrema(prices, np.less, order=order)[0]
    
    if len(min_idxs) < 3: return False, "No troughs"
    
    relevant_min_idxs = min_idxs[min_idxs > (len(prices) - 250)] # Look back 1 year
    
    for i in range(len(relevant_min_idxs) - 2):
        l_idx = relevant_min_idxs[i]
        h_idx = relevant_min_idxs[i+1]
        r_idx = relevant_min_idxs[i+2]
        
        ls_price, head_price, rs_price = prices[l_idx], prices[h_idx], prices[r_idx]
        
        # Structure: Head lowest
        if not (head_price < ls_price and head_price < rs_price): continue
        
        # Symmetry: Shoulders within 20%
        if abs(ls_price - rs_price) / rs_price > 0.20: continue
            
        # Depth: Head significantly lower
        if head_price >= (ls_price+rs_price)/2 * 0.98: continue
        
        # Neckline
        neck_left_idx = np.argmax(prices[l_idx:h_idx]) + l_idx
        neck_right_idx = np.argmax(prices[h_idx:r_idx]) + h_idx
        
        neckline_price = (prices[neck_left_idx] + prices[neck_right_idx]) / 2
        
        # Breakout
        current = prices[-1]
        
        if current >= neckline_price * 0.95:
             # Calculate score
             vol_breakout = check_volume_breakout(df)
             score = 60
             if vol_breakout: score += 20
             
             return True, {
                 "pattern": "Inv Head/Shoulders",
                 "status": "Breakout" if current > neckline_price else "Forming",
                 "pivot": neckline_price,
                 "stop_loss": rs_price,
                 "target_price": neckline_price + (neckline_price - head_price),
                 "score": score,
                 "volume_breakout": vol_breakout,
                 "ai_score": score
             }
             
    return False, "No IHS"
