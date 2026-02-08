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
    Advanced Cup & Handle Detection with Sophisticated Scoring
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
    if bars_since_right > 45:
        return False, f"Right rim too old ({bars_since_right} bars)"
    
    # 3. Find Left Rim
    search_end = right_rim_idx - 8
    if search_end < 20:
        return False, "Pattern too short"
    
    search_start = max(0, search_end - 250)
    left_rim_idx = np.argmax(highs[search_start:search_end]) + search_start
    left_rim_price = highs[left_rim_idx]
    
    # 4. Rim Alignment Check
    ratio = left_rim_price / right_rim_price
    if not (0.75 <= ratio <= 1.35):
        return False, f"Rim mismatch {left_rim_price:.2f}/{right_rim_price:.2f}"
    
    # 5. Cup Bottom
    cup_slice = lows[left_rim_idx:right_rim_idx]
    if len(cup_slice) < 5:
        return False, "Cup too narrow"
    
    cup_bottom_price = np.min(cup_slice)
    cup_depth_pct = 1.0 - (cup_bottom_price / max(left_rim_price, right_rim_price))
    
    if not (0.08 <= cup_depth_pct <= 0.60):
        return False, f"Depth invalid ({cup_depth_pct*100:.1f}%)"
    
    # ============================================================================
    # ADVANCED SCORING SYSTEM (0-100 points)
    # ============================================================================
    
    score = 50  # Base score
    status = "Forming"
    
    # FACTOR 1: Cup Depth Quality (0-20 points)
    # Ideal: 15-33% (Minervini's sweet spot)
    if 0.15 <= cup_depth_pct <= 0.33:
        score += 20  # Perfect depth
    elif 0.12 <= cup_depth_pct <= 0.40:
        score += 15  # Good depth
    elif 0.10 <= cup_depth_pct <= 0.50:
        score += 10  # Acceptable
    else:
        score += 5   # Marginal
    
    # FACTOR 2: Rim Symmetry (0-15 points)
    if 0.98 <= ratio <= 1.02:
        score += 15  # Nearly perfect
    elif 0.95 <= ratio <= 1.05:
        score += 12  # Excellent
    elif 0.90 <= ratio <= 1.10:
        score += 10  # Good
    elif 0.85 <= ratio <= 1.15:
        score += 7   # Acceptable
    else:
        score += 3   # Poor
    
    # FACTOR 3: Handle Quality & Breakout Proximity (0-25 points)
    if bars_since_right > 0:
        handle_slice = lows[right_rim_idx:]
        handle_low = np.min(handle_slice)
        handle_depth_pct = 1.0 - (handle_low / right_rim_price)
        
        # Reject if handle too deep
        if handle_depth_pct > 0.22:
            return False, f"Handle too deep ({handle_depth_pct*100:.1f}%)"
        
        # Tighter handle = better
        if handle_depth_pct <= 0.08:
            score += 15  # VCP-like tight consolidation
        elif handle_depth_pct <= 0.12:
            score += 12  # Good handle
        elif handle_depth_pct <= 0.18:
            score += 8   # Acceptable
        else:
            score += 4   # Deeper handle
        
        # Current price position
        current_price = closes[-1]
        
        # Reject if too far below rim
        if current_price < right_rim_price * 0.88:
            return False, "Price rejected (too far below rim)"
        
        # Breakout proximity bonus (0-10 points)
        distance_pct = (right_rim_price - current_price) / right_rim_price
        
        if distance_pct <= 0.02:  # Within 2%
            status = "Breakout!"
            score += 10
        elif distance_pct <= 0.05:  # Within 5%
            status = "Near Pivot"
            score += 8
        elif distance_pct <= 0.08:  # Within 8%
            status = "Approaching"
            score += 5
        else:
            score += 2
    
    # FACTOR 4: Volume Trend (0-10 points)
    # Volume should dry up in handle
    if bars_since_right >= 10:
        handle_vols = df['Volume'].iloc[right_rim_idx:]
        if len(handle_vols) >= 10:
            mid = len(handle_vols) // 2
            first_half_avg = handle_vols[:mid].mean()
            second_half_avg = handle_vols[mid:].mean()
            
            if second_half_avg < first_half_avg * 0.8:
                score += 10  # Volume drying up
            elif second_half_avg < first_half_avg:
                score += 6   # Volume declining
            else:
                score += 2
    
    # FACTOR 5: Trend Strength (0-10 points)
    current = df.iloc[-1]
    
    if not pd.isna(current.get('SMA50')) and current['Close'] > current['SMA50']:
        score += 5
    if not pd.isna(current.get('SMA200')) and current['Close'] > current['SMA200']:
        score += 5
    
    # FACTOR 6: Risk/Reward (0-10 points)
    risk = right_rim_price - cup_bottom_price
    reward = right_rim_price - cup_bottom_price  # Projected target
    rr_ratio = reward / risk if risk > 0 else 0
    
    if rr_ratio >= 2.5:
        score += 10
    elif rr_ratio >= 2.0:
        score += 8
    elif rr_ratio >= 1.5:
        score += 6
    else:
        score += 3
    
    # Cap at 100
    score = min(score, 100)
    
    return True, {
        "pattern": "Cup & Handle",
        "pivot": float(right_rim_price),
        "stop_loss": float(cup_bottom_price),
        "target_price": float(right_rim_price + (right_rim_price - cup_bottom_price)),
        "left_rim": float(left_rim_price),
        "right_rim": float(right_rim_price),
        "bottom": float(cup_bottom_price),
        "score": score,
        "status": status,
        "ai_score": score
    }

def find_inverse_head_and_shoulders(df):
    """
    Simplified IHS Detection
    """
    if len(df) < 60: return False, "Not enough data"
    
    df = calculate_mas(df)
    prices = df['Close'].values
    
    order = 5
    min_idxs = argrelextrema(prices, np.less, order=order)[0]
    
    if len(min_idxs) < 3: return False, "No troughs"
    
    relevant_min_idxs = min_idxs[min_idxs > (len(prices) - 250)]
    
    for i in range(len(relevant_min_idxs) - 2):
        l_idx = relevant_min_idxs[i]
        h_idx = relevant_min_idxs[i+1]
        r_idx = relevant_min_idxs[i+2]
        
        ls_price, head_price, rs_price = prices[l_idx], prices[h_idx], prices[r_idx]
        
        if not (head_price < ls_price and head_price < rs_price):
            continue
        
        if abs(ls_price - rs_price) / rs_price > 0.20:
            continue
        
        if head_price >= (ls_price + rs_price) / 2 * 0.98:
            continue
        
        neck_left_idx = np.argmax(prices[l_idx:h_idx]) + l_idx
        neck_right_idx = np.argmax(prices[h_idx:r_idx]) + h_idx
        neckline_price = (prices[neck_left_idx] + prices[neck_right_idx]) / 2
        
        current = prices[-1]
        
        if current >= neckline_price * 0.95:
            vol_breakout = check_volume_breakout(df)
            score = 60
            
            if vol_breakout:
                score += 20
            if current > neckline_price:
                score += 10
            
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
