import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

def calculate_mas(df):
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    df['VolSMA50'] = df['Volume'].rolling(window=50).mean()
    return df

def check_trend_template(df):
    """
    Minervini-style Trend Template (Simplified for 4H/Daily usage)
    """
    if len(df) < 50: return False, "Not enough data"
    
    current = df.iloc[-1]
    
    # Simple check: Price > SMA50
    sma50 = current.get('SMA50', 0)
    sma200 = current.get('SMA200', 0)
    
    if pd.isna(sma50) or pd.isna(sma200):
        # Fallback if SMAs aren't ready
        return True, "Data incomplete (Trend OK)"

    if current['Close'] < sma200:
        return False, "Below SMA200"

    return True, "Trend OK"

def check_volume_breakout(df, lookback=3):
    """
    Breakout Volume > 1.35x 50-day Avg Vol
    Checks the last 'lookback' bars to catch recent breakouts.
    """
    avg_vol = df['VolSMA50'].iloc[-1]
    if pd.isna(avg_vol) or avg_vol == 0: return False
    
    # Check any of the last few bars
    for i in range(1, lookback + 1):
        if len(df) < i: break
        vol = df['Volume'].iloc[-i]
        if vol > (avg_vol * 1.35):
            return True
            
    return False

def find_cup_and_handle(df):
    """
    Advanced Cup & Handle Detection
    """
    if len(df) < 60: return False, f"Not enough data ({len(df)})"
    
    df = calculate_mas(df)
    closes = df['Close'].values
    highs = df['High'].values
    lows = df['Low'].values
    
    # 1. Find Right Rim (Recent High)
    lookback_right = min(60, len(closes))
    right_rim_rel_idx = np.argmax(highs[-lookback_right:])
    right_rim_idx = len(highs) - lookback_right + right_rim_rel_idx
    right_rim_price = highs[right_rim_idx]
    
    # 2. Check Handle Age
    bars_since_right = len(closes) - 1 - right_rim_idx
    if bars_since_right > 45: return False, "Old Pattern"
    
    # 3. Find Left Rim
    search_end = right_rim_idx - 8
    if search_end < 20: return False, "Pattern too short"
    
    search_start = max(0, search_end - 250)
    left_rim_idx = np.argmax(highs[search_start:search_end]) + search_start
    left_rim_price = highs[left_rim_idx]
    
    # 4. Rim Check
    ratio = left_rim_price / right_rim_price
    if not (0.70 <= ratio <= 1.40): return False, "Rim mismatch"
    
    # 5. Cup Bottom
    cup_slice = lows[left_rim_idx:right_rim_idx]
    if len(cup_slice) < 5: return False, "Cup too narrow"
    cup_bottom_price = np.min(cup_slice)
    cup_depth_pct = 1.0 - (cup_bottom_price / max(left_rim_price, right_rim_price))
    
    if not (0.08 <= cup_depth_pct <= 0.60): return False, "Invalid Depth"
    
    # 6. Handle Definition & Stop Loss
    handle_low = cup_bottom_price # Default to cup bottom if no handle
    handle_slice = []
    
    if bars_since_right > 3:
        handle_slice = lows[right_rim_idx:]
        handle_low = np.min(handle_slice)
        
        # Check handle doesn't drop too low (below 50% of cup depth usually invalid)
        midpoint = cup_bottom_price + (right_rim_price - cup_bottom_price) * 0.4
        if handle_low < midpoint:
            return False, "Handle too deep"

    # --- SCORING ---
    score = 50
    status = "Forming"
    
    # Depth
    if 0.12 <= cup_depth_pct <= 0.35: score += 15
    
    # Handle tightness
    handle_depth = 1.0 - (handle_low / right_rim_price)
    if handle_depth < 0.10: score += 15
    elif handle_depth < 0.15: score += 10
    
    # Breakout Logic
    current_price = closes[-1]
    dist_to_pivot = (right_rim_price - current_price) / right_rim_price
    
    vol_confirm = check_volume_breakout(df)
    
    if current_price > right_rim_price:
        status = "Breakout"
        score += 20
        if vol_confirm: score += 10
    elif dist_to_pivot < 0.03:
        status = "Near Pivot"
        score += 10
    
    # Improved Risk Management
    stop_loss = handle_low 
    # If handle is non-existent (V-shape), use midpoint of right side or cup bottom
    if bars_since_right < 3:
        stop_loss = cup_bottom_price + (right_rim_price - cup_bottom_price) * 0.3
        
    entry = right_rim_price
    risk = entry - stop_loss
    target = entry + (entry - cup_bottom_price) # Projected move
    
    return True, {
        "pattern": "Cup & Handle",
        "pivot": float(entry),
        "stop_loss": float(stop_loss),
        "target_price": float(target),
        "score": min(score, 100),
        "status": status,
        "ai_score": min(score, 100),
        "plot": None 
    }

def find_inverse_head_and_shoulders(df):
    if len(df) < 60: return False, "Not enough data"
    
    df = calculate_mas(df)
    prices = df['Close'].values
    
    # Use scipy to find local minima
    order = 5
    min_idxs = argrelextrema(prices, np.less, order=order)[0]
    if len(min_idxs) < 3: return False, "No troughs"
    
    # Look at recent minima
    relevant = min_idxs[min_idxs > (len(prices) - 200)]
    if len(relevant) < 3: return False, "Not enough recent troughs"
    
    # We need 3 consecutive troughs: Left, Head, Right
    # Heuristic: Find lowest trough (Head), then look left and right
    
    head_idx = -1
    lowest_price = float('inf')
    
    for i in range(1, len(relevant)-1):
        p = prices[relevant[i]]
        if p < lowest_price:
            lowest_price = p
            head_idx = i
            
    if head_idx == -1: return False, "No distinct head"
    
    l_idx = relevant[head_idx-1]
    h_idx = relevant[head_idx]
    r_idx = relevant[head_idx+1]
    
    ls_price = prices[l_idx]
    head_price = prices[h_idx]
    rs_price = prices[r_idx]
    
    # Logic: Head must be lower than shoulders
    if not (head_price < ls_price and head_price < rs_price):
        return False, "Head not lowest"
        
    # Logic: Shoulders roughly equal (+/- 15%)
    if abs(ls_price - rs_price) / rs_price > 0.15:
        return False, "Shoulders asymmetrical"
        
    # Neckline (High between shoulders)
    neck_left_idx = np.argmax(prices[l_idx:h_idx]) + l_idx
    neck_right_idx = np.argmax(prices[h_idx:r_idx]) + h_idx
    neck_price = max(prices[neck_left_idx], prices[neck_right_idx]) # Conservative: use higher peak
    
    current = prices[-1]
    
    score = 60
    status = "Forming"
    vol_confirm = check_volume_breakout(df)
    
    if current > neck_price:
        status = "Breakout"
        score += 20
        if vol_confirm: score += 15
    elif (neck_price - current)/neck_price < 0.05:
        status = "Near Pivot"
        score += 10
        
    # Targets
    height = neck_price - head_price
    target = neck_price + height
    stop = rs_price # Stop under right shoulder
    
    return True, {
        "pattern": "Inv H&S",
        "pivot": float(neck_price),
        "stop_loss": float(stop),
        "target_price": float(target),
        "score": score,
        "status": status,
        "ai_score": score,
        "plot": None
    }

def find_bull_flag(df):
    """
    Finds a sharp move up (Pole) followed by a consolidation (Flag).
    """
    if len(df) < 40: return False, "No data"
    
    df = calculate_mas(df)
    closes = df['Close'].values
    highs = df['High'].values
    lows = df['Low'].values
    
    # 1. Detect Pole (Last 15-40 bars)
    # Check for > 15% move in < 20 bars
    # Heuristic: Max high of recent window / Min low of slightly older window
    
    recent_window = 25
    flag_window = 10
    
    # The 'High' of the pole
    pole_top_idx = np.argmax(highs[-recent_window:])
    pole_top_idx = len(highs) - recent_window + pole_top_idx
    pole_top = highs[pole_top_idx]
    
    # The 'Low' before the pole
    # Scan backward from pole top
    scan_back = max(0, pole_top_idx - 20)
    if pole_top_idx <= scan_back: return False, "No pole base"
    
    pole_base = np.min(lows[scan_back:pole_top_idx])
    
    if (pole_top - pole_base) / pole_base < 0.12:
        return False, "Pole weak (<12%)"
        
    # 2. Detect Flag (Consolidation after Pole Top)
    # Price should drift down or sideways, not giving back > 50% of gains
    
    # Check bars AFTER pole top
    if pole_top_idx >= len(highs) - 3:
        # Pole top is very recent, flag just forming
        flag_low = np.min(lows[pole_top_idx:])
    else:
        flag_low = np.min(lows[pole_top_idx:])
        
    retracement = (pole_top - flag_low) / (pole_top - pole_base)
    
    if retracement > 0.50:
        return False, "Flag too deep (>50%)"
        
    # Check if flag is "tight" (volatility contraction) logic could apply here
    
    # 3. Status
    current = closes[-1]
    
    # Resistance line of the flag (simplified as Pole Top for horizontal flags, 
    # or a down-sloping trendline. Let's use Pole Top for high confidence breakout).
    pivot = pole_top
    
    score = 65
    status = "Forming"
    vol_confirm = check_volume_breakout(df)
    
    if current > pivot:
        status = "Breakout"
        score += 20
        if vol_confirm: score += 10
    elif (pivot - current)/pivot < 0.04:
        status = "Near Pivot"
        score += 10
        
    stop = flag_low
    target = pivot + (pole_top - pole_base) # Measured move
    
    return True, {
        "pattern": "Bull Flag",
        "pivot": float(pivot),
        "stop_loss": float(stop),
        "target_price": float(target),
        "score": score,
        "status": status,
        "ai_score": score,
        "plot": None
    }

def find_volatility_contraction(df):
    """
    Finds period of tight consolidation (Flat Base).
    """
    if len(df) < 30: return False, "Short data"
    
    # Look at last 15-20 bars
    window = 20
    segment = df.iloc[-window:]
    
    max_h = segment['High'].max()
    min_l = segment['Low'].min()
    
    width_pct = (max_h - min_l) / min_l
    
    if width_pct > 0.12: # 12% width max for "tight" base
        return False, f"Too wide ({width_pct:.1%})"
        
    current = df['Close'].iloc[-1]
    
    pivot = max_h
    score = 60
    status = "Forming"
    
    if current > pivot:
        status = "Breakout"
        score += 20
        if check_volume_breakout(df): score += 15
    elif (pivot - current)/pivot < 0.02:
        status = "Near Pivot"
        score += 10
        
    # Target: Width of base added to pivot (conservative) or 20%
    target = pivot * 1.20
    stop = min_l
    
    return True, {
        "pattern": "VCP / Flat Base",
        "pivot": float(pivot),
        "stop_loss": float(stop),
        "target_price": float(target),
        "score": score,
        "status": status,
        "ai_score": score,
        "plot": None
    }
