import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

def find_cup_and_handle(df, back_days=365):
    """
    Analyzes the last 'back_days' of data to find a forming Cup and Handle.
    
    Args:
        df (pd.DataFrame): DataFrame with 'Close' column and DateTime index.
        back_days (int): How far back to look for the pattern start.
        
    Returns:
        tuple: (bool, dict) -> (Found Pattern?, Details)
    """
    if len(df) < back_days // 2:
        return False, "Not enough data"
        
    # Focus on the relevant window
    recent = df.iloc[-back_days:].copy()
    prices = recent['Close'].values
    dates = recent.index
    
    # 1. Identify Local Maxima (Peaks)
    # Order=5 means looking for peaks that are max within 5 points on each side
    order = 5
    max_idx = argrelextrema(prices, np.greater, order=order)[0]
    
    if len(max_idx) < 2:
        return False, "Not enough peaks"
        
    # We need to find the Right Rim and Left Rim
    # The Right Rim should be relatively recent (within ~1-8 weeks perhaps?) 
    # but not *right now* otherwise where is the handle?
    # Actually, if the handle is forming, the Right Rim is a past peak.
    
    # Let's iterate backwards through potential Right Rims
    # The latest peak could be the Right Rim
    
    potential_patterns = []
    
    # Look at the last 3 peaks as candidates for Right Rim
    for r_idx in max_idx[::-1][:3]:
        right_rim_price = prices[r_idx]
        right_rim_date = dates[r_idx]
        
        # Days since Right Rim
        days_since_right_rim = (dates[-1] - right_rim_date).days
        
        # Handle Check Part 1: Time
        # Detect handle forming: Needs to be recent, e.g., 5 to 50 days (approx 1-10 weeks)
        if not (5 <= days_since_right_rim <= 60):
            continue
            
        # Handle Check Part 2: Price currently forming handle
        # Current price should be LOWER than Right Rim (retracing)
        current_price = prices[-1]
        if current_price >= right_rim_price:
             # It broke out or is above. We want "forming handle" which usually implies retrace.
             continue
             
        # Find a matching Left Rim
        # Iterate backwards from Right Rim
        for l_idx in max_idx:
            if l_idx >= r_idx:
                break
                
            left_rim_price = prices[l_idx]
            left_rim_date = dates[l_idx]
            
            # Duration Check: Cup needs to be meaningful (e.g., > 1 month, < 1 year)
            cup_duration = (right_rim_date - left_rim_date).days
            if not (30 <= cup_duration <= 365):
                continue
                
            # Height Check: Rims should be somewhat level-ish (e.g., within 20% of each other?)
            # Usually Cup and Handle rims are close, but strict equality isn't seen in wild.
            if not (0.8 <= left_rim_price / right_rim_price <= 1.2):
                continue
                
            # Verify "Cup" Shape: Low point between rims
            # Get slice between rims
            cup_slice_prices = prices[l_idx:r_idx]
            cup_bottom_price = np.min(cup_slice_prices)
            cup_bottom_idx = np.argmin(cup_slice_prices) + l_idx # global index
            
            # Depth Calculation
            cup_depth = right_rim_price - cup_bottom_price
            cup_depth_pct = cup_depth / right_rim_price
            
            # Reject if too shallow (< 5%?) or too deep (> 75%?)
            if not (0.05 <= cup_depth_pct <= 0.75):
                continue
            
            # Check mid-point of bottom. We don't want a "V" shape right at one end.
            # Bottom should be somewhat in the middle third timeframe ideally?
            # Or just ensure it's not the Rim index itself (guaranteed by slice)
            # A simple rule: verify the bottom is "deep enough" compared to the trend.
             
            # HANDLE CHECK: "Halfway forming"
            # We already know current_price < right_rim_price
            # Check how deep the handle has gone.
            handle_drop = right_rim_price - current_price
            
            # Handle shouldn't drop more than ~50% of the cup depth
            if handle_drop > (0.5 * cup_depth):
                # Dropped too much, pattern failed
                continue
                
            # Logic: "Halfway" ? 
            # If handle drop is very small (< 2%), it just started.
            # If handle drop is significant (e.g. > 20% of cup depth), it's forming well.
            # This is subjective, but "forming" implies it exists.
            
            # --- Calculate Trade Parameters ---
            # 1. Entry (Pivot): The Right Rim High
            entry_price = right_rim_price
            
            # 2. Stop Loss: The lowest point of the handle so far
            # We need the slice from right rim to end
            handle_slice = prices[r_idx:]
            handle_low = np.min(handle_slice)
            stop_loss = handle_low
            
            # 3. Profit Target: Measured Move (Depth of Cup) added to Entry
            # Classic target is 1x the depth
            target_price = entry_price + cup_depth
            
            # Risk/Reward Ratio (Approximate)
            risk = entry_price - stop_loss
            reward = target_price - entry_price
            rr_ratio = round(reward / risk, 1) if risk > 0 else 0
            
            return True, {
                "pattern": "Cup and Handle (Forming)",
                "left_rim": (str(left_rim_date.date()), round(left_rim_price, 2)),
                "right_rim": (str(right_rim_date.date()), round(right_rim_price, 2)),
                "cup_bottom": round(cup_bottom_price, 2),
                "cup_depth_pct": round(cup_depth_pct * 100, 1),
                "handle_duration_days": days_since_right_rim,
                "handle_retracement_pct": round(retracement_pct, 1),
                "suggested_entry": round(entry_price, 2),
                "stop_loss": round(stop_loss, 2),
                "target_price": round(target_price, 2),
                "rr_ratio": rr_ratio
            }

    return False, "No valid pattern found"
