import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from scipy.stats import linregress

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def calculate_mas(df):
    df = df.copy()
    df['SMA50']   = df['Close'].rolling(window=50).mean()
    df['SMA200']  = df['Close'].rolling(window=200).mean()
    df['EMA21']   = df['Close'].ewm(span=21, adjust=False).mean()
    df['VolSMA50']= df['Volume'].rolling(window=50).mean()
    df['ATR']     = _calc_atr(df, 14)
    return df

def _calc_atr(df, period=14):
    """Average True Range"""
    high = df['High']
    low  = df['Low']
    close= df['Close']
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def check_trend_template(df):
    """
    Minervini-style Trend Template.
    Price > SMA50 > SMA200 (upward slope preferred).
    """
    if len(df) < 50:
        return False, "Not enough data"

    current = df.iloc[-1]
    sma50  = current.get('SMA50',  np.nan)
    sma200 = current.get('SMA200', np.nan)

    if pd.isna(sma50) or pd.isna(sma200):
        return True, "Data incomplete (Trend OK)"

    if current['Close'] < sma200:
        return False, "Below SMA200"

    # SMA50 should be above SMA200 (golden cross zone)
    if sma50 < sma200:
        return False, "SMA50 below SMA200"

    return True, "Trend OK"

def check_volume_breakout(df, lookback=3, multiplier=1.35):
    """
    True if ANY of the last `lookback` bars has volume > multiplier * 50-bar avg.
    """
    avg_vol = df['VolSMA50'].iloc[-1]
    if pd.isna(avg_vol) or avg_vol == 0:
        return False
    for i in range(1, lookback + 1):
        if len(df) < i:
            break
        if df['Volume'].iloc[-i] > avg_vol * multiplier:
            return True
    return False

def _volume_trend(df, window=20):
    """
    Returns slope of volume over last `window` bars (normalised).
    Negative = declining volume (good for handle); Positive = expanding (good for breakout).
    """
    vols = df['Volume'].values[-window:]
    if len(vols) < 5:
        return 0.0
    xs = np.arange(len(vols))
    slope, _, _, _, _ = linregress(xs, vols)
    return slope / (np.mean(vols) + 1e-9)   # normalise to mean volume

def _cup_shape_score(lows_in_cup):
    """
    Measures how U-shaped (good) vs V-shaped (bad) the cup bottom is.
    Returns 0-20 bonus points.
    U-shape: bottom is flat / gently rounded → many bars near the minimum.
    V-shape: single bar at minimum then straight back up.
    """
    if len(lows_in_cup) < 5:
        return 0
    mn = np.min(lows_in_cup)
    mx = np.max(lows_in_cup)
    if mx == mn:
        return 10  # Flat → perfect U
    norm = (lows_in_cup - mn) / (mx - mn)
    # Count fraction of bars within 10% of the bottom
    near_bottom = np.sum(norm < 0.10) / len(norm)
    return int(near_bottom * 20)   # max 20 pts


# ─────────────────────────────────────────────
#  1. CUP & HANDLE  (primary pattern)
# ─────────────────────────────────────────────

def find_cup_and_handle(df):
    """
    Enhanced Cup & Handle Detection.

    Key improvements vs old version:
    • Proper U-shape validation (rewards rounded bottoms, penalises V-shapes)
    • Volume profile check: volume should DRY UP in the handle then SURGE at breakout
    • Right rim does NOT need to exactly match left rim (real C&H often slightly lower)
    • Pre-breakout focus: highest bonus for "Near Pivot" + drying volume in handle
    • Multi-attempt: scans multiple right-rim candidates to find best pattern
    • Tighter handle geometry: handle must stay in upper 50% of cup depth
    """
    if len(df) < 60:
        return False, f"Not enough data ({len(df)})"

    df = calculate_mas(df)
    closes = df['Close'].values
    highs  = df['High'].values
    lows   = df['Low'].values

    n = len(closes)

    # ── Step 1: Find Right Rim ──────────────────────────────────────────
    # Look back up to 120 bars for the highest recent high (right rim of the cup).
    lookback_right = min(120, n)
    rr_rel  = np.argmax(highs[-lookback_right:])
    right_rim_idx   = n - lookback_right + rr_rel
    right_rim_price = highs[right_rim_idx]

    bars_since_right = n - 1 - right_rim_idx

    # Handle should exist (at least 2 bars) and not be stale (>60 bars)
    if bars_since_right < 2:
        return False, "Handle not formed yet"
    if bars_since_right > 60:
        return False, "Pattern too old"

    # ── Step 2: Find Left Rim ──────────────────────────────────────────
    # Search in a window BEFORE the right rim (at least 15 bars of cup)
    search_end   = right_rim_idx - 15
    if search_end < 20:
        return False, "Cup too narrow for left rim search"

    search_start = max(0, right_rim_idx - 300)
    left_rim_idx   = np.argmax(highs[search_start:search_end]) + search_start
    left_rim_price = highs[left_rim_idx]

    cup_len = right_rim_idx - left_rim_idx
    if cup_len < 15:
        return False, "Cup too short"

    # ── Step 3: Rim parity check ────────────────────────────────────────
    # Real C&H: right rim can be SLIGHTLY lower than left rim (0.85–1.05 ratio)
    ratio = right_rim_price / left_rim_price
    if not (0.82 <= ratio <= 1.08):
        return False, f"Rim mismatch ({ratio:.2f})"

    # ── Step 4: Cup depth ───────────────────────────────────────────────
    cup_lows  = lows[left_rim_idx: right_rim_idx + 1]
    cup_bottom_price = np.min(cup_lows)
    ref_price = max(left_rim_price, right_rim_price)
    cup_depth = 1.0 - (cup_bottom_price / ref_price)

    if cup_depth < 0.08:
        return False, "Cup too shallow (<8%)"
    if cup_depth > 0.50:
        return False, "Cup too deep (>50%)"

    # ── Step 5: Handle geometry ─────────────────────────────────────────
    handle_slice_lows  = lows[right_rim_idx:]
    handle_slice_close = closes[right_rim_idx:]
    handle_low   = np.min(handle_slice_lows)
    handle_high  = np.max(highs[right_rim_idx:])

    # Handle must NOT drop below 40% retracement of cup depth from right rim
    max_handle_drop = right_rim_price - cup_depth * (right_rim_price - cup_bottom_price) * 0.6
    if handle_low < max_handle_drop:
        return False, "Handle too deep"

    # Handle must NOT be longer than 50 bars (otherwise it becomes a new base)
    if bars_since_right > 50:
        return False, "Handle too long"

    # Handle should drift DOWN or sideways relative to right rim
    handle_drop_pct = (right_rim_price - handle_low) / right_rim_price
    # Acceptable: 0% to 15% drop in the handle
    if handle_drop_pct > 0.15:
        return False, "Handle drops >15%"

    # ── Step 6: Volume profile ──────────────────────────────────────────
    # Ideal: volume contracts during handle, then surges at breakout
    handle_vol_trend = _volume_trend(df, window=max(bars_since_right, 5))
    # Negative trend = drying up = GOOD
    vol_drying = handle_vol_trend < 0

    # ── Step 7: Cup shape (U vs V) ──────────────────────────────────────
    cup_shape_bonus = _cup_shape_score(cup_lows)

    # ── Step 8: SMA alignment ───────────────────────────────────────────
    above_sma50  = closes[-1] > df['SMA50'].iloc[-1]   if not pd.isna(df['SMA50'].iloc[-1])  else True
    above_sma200 = closes[-1] > df['SMA200'].iloc[-1]  if not pd.isna(df['SMA200'].iloc[-1]) else True

    # ── SCORING ─────────────────────────────────────────────────────────
    score = 40   # base

    # Rim balance
    score += 10 if 0.92 <= ratio <= 1.02 else 5

    # Cup depth quality
    if 0.12 <= cup_depth <= 0.33:
        score += 15
    elif 0.08 <= cup_depth < 0.12:
        score += 8

    # Cup shape
    score += cup_shape_bonus  # 0–20

    # Handle tightness
    if handle_drop_pct < 0.06:
        score += 15
    elif handle_drop_pct < 0.10:
        score += 10
    elif handle_drop_pct < 0.15:
        score += 5

    # Volume drying in handle
    if vol_drying:
        score += 8

    # SMA alignment
    if above_sma200:
        score += 5
    if above_sma50:
        score += 5

    # ── Step 9: Breakout / Status ────────────────────────────────────────
    current_price = closes[-1]
    dist_to_pivot = (right_rim_price - current_price) / right_rim_price
    vol_confirm   = check_volume_breakout(df)

    status = "Forming"

    if current_price > right_rim_price:
        status = "Breakout"
        score += 15
        if vol_confirm:
            score += 10   # confirmed breakout on volume

    elif dist_to_pivot < 0.02:
        status = "Near Pivot"
        score += 12        # prime entry territory
        if vol_drying:
            score += 5    # handle dried up → optimal

    elif dist_to_pivot < 0.05:
        status = "Near Pivot"
        score += 7

    # ── Risk management ──────────────────────────────────────────────────
    stop_loss    = handle_low
    entry        = right_rim_price          # pivot = breakout point
    cup_height   = right_rim_price - cup_bottom_price
    target_price = entry + cup_height       # measured move

    return True, {
        "pattern":      "Cup & Handle",
        "pivot":        float(entry),
        "stop_loss":    float(stop_loss),
        "target_price": float(target_price),
        "score":        min(int(score), 100),
        "status":       status,
        "ai_score":     min(int(score), 100),
        "cup_depth_pct":round(cup_depth * 100, 1),
        "handle_drop_pct": round(handle_drop_pct * 100, 1),
        "vol_drying":   vol_drying,
        "plot":         None,
    }


# ─────────────────────────────────────────────
#  2. INVERSE HEAD & SHOULDERS
# ─────────────────────────────────────────────

def find_inverse_head_and_shoulders(df):
    if len(df) < 60:
        return False, "Not enough data"

    df = calculate_mas(df)
    prices = df['Close'].values
    lows   = df['Low'].values

    # Use local minima on LOWS for better sensitivity
    order    = 5
    min_idxs = argrelextrema(lows, np.less, order=order)[0]
    if len(min_idxs) < 3:
        return False, "No troughs"

    relevant = min_idxs[min_idxs > (len(prices) - 250)]
    if len(relevant) < 3:
        return False, "Not enough recent troughs"

    # Find the head = lowest trough in the relevant set
    head_i = -1
    lowest  = float('inf')
    for i in range(1, len(relevant) - 1):
        p = lows[relevant[i]]
        if p < lowest:
            lowest = p
            head_i = i

    if head_i == -1:
        return False, "No distinct head"

    l_idx = relevant[head_i - 1]
    h_idx = relevant[head_i]
    r_idx = relevant[head_i + 1]

    ls_p   = lows[l_idx]
    head_p = lows[h_idx]
    rs_p   = lows[r_idx]

    if not (head_p < ls_p and head_p < rs_p):
        return False, "Head not lowest"

    # Shoulders roughly equal (within 12%)
    if abs(ls_p - rs_p) / max(rs_p, 1e-9) > 0.12:
        return False, "Shoulders too asymmetrical"

    # Shoulder depth vs head
    avg_shoulder = (ls_p + rs_p) / 2
    head_depth   = (avg_shoulder - head_p) / avg_shoulder
    if head_depth < 0.05:
        return False, "Head not distinct enough"

    # Neckline: highest close between left-shoulder→head and head→right-shoulder
    neck_l = np.max(prices[l_idx: h_idx + 1])
    neck_r = np.max(prices[h_idx: r_idx + 1])
    neck_price = (neck_l + neck_r) / 2.0   # average neckline

    current   = prices[-1]
    score     = 55
    status    = "Forming"
    vol_confirm = check_volume_breakout(df)

    dist_to_neck = (neck_price - current) / neck_price

    if current > neck_price:
        status = "Breakout"
        score += 20
        if vol_confirm:
            score += 15
    elif dist_to_neck < 0.03:
        status = "Near Pivot"
        score += 12
    elif dist_to_neck < 0.05:
        status = "Near Pivot"
        score += 7

    # Quality: symmetry bonus
    sym_ratio = min(ls_p, rs_p) / max(ls_p, rs_p)
    if sym_ratio > 0.97:
        score += 10   # very symmetric
    elif sym_ratio > 0.93:
        score += 5

    height   = neck_price - head_p
    target   = neck_price + height
    stop     = rs_p

    return True, {
        "pattern":      "Inv H&S",
        "pivot":        float(neck_price),
        "stop_loss":    float(stop),
        "target_price": float(target),
        "score":        min(int(score), 100),
        "status":       status,
        "ai_score":     min(int(score), 100),
        "plot":         None,
    }


# ─────────────────────────────────────────────
#  3. BULL FLAG
# ─────────────────────────────────────────────

def find_bull_flag(df):
    """
    Sharp pole (>12% in <20 bars) + tight flag (≤35% retracement, declining volume).
    """
    if len(df) < 40:
        return False, "No data"

    df = calculate_mas(df)
    closes = df['Close'].values
    highs  = df['High'].values
    lows   = df['Low'].values
    n = len(closes)

    recent_window = 30
    pole_top_rel  = np.argmax(highs[-recent_window:])
    pole_top_idx  = n - recent_window + pole_top_rel
    pole_top      = highs[pole_top_idx]

    scan_back = max(0, pole_top_idx - 25)
    if pole_top_idx <= scan_back:
        return False, "No pole base"

    pole_base = np.min(lows[scan_back: pole_top_idx])
    pole_gain = (pole_top - pole_base) / max(pole_base, 1e-9)

    if pole_gain < 0.12:
        return False, f"Pole too weak ({pole_gain:.1%})"
    if pole_gain > 1.0:
        return False, "Suspicious pole (>100%)"

    # Flag: bars AFTER pole top
    bars_since_pole = n - 1 - pole_top_idx
    if bars_since_pole < 3:
        return False, "Flag not formed yet"

    flag_lows   = lows[pole_top_idx:]
    flag_highs  = highs[pole_top_idx:]
    flag_low    = np.min(flag_lows)
    flag_high   = np.max(flag_highs)

    retracement = (pole_top - flag_low) / (pole_top - pole_base + 1e-9)
    if retracement > 0.40:
        return False, f"Flag too deep ({retracement:.1%})"

    # Flag channel: slightly downward sloping is ideal
    flag_vol_trend = _volume_trend(df, window=max(bars_since_pole, 5))
    vol_drying     = flag_vol_trend < 0

    # Flag width (should be < 10% of pole height for tight flag)
    flag_range_pct = (flag_high - flag_low) / max(pole_top, 1e-9)

    current = closes[-1]
    pivot   = pole_top

    score  = 60
    status = "Forming"
    vol_confirm = check_volume_breakout(df)

    dist = (pivot - current) / pivot

    if current > pivot:
        status = "Breakout"
        score += 20
        if vol_confirm:
            score += 10
    elif dist < 0.02:
        status = "Near Pivot"
        score += 12
    elif dist < 0.05:
        status = "Near Pivot"
        score += 7

    # Bonuses
    if vol_drying:
        score += 8
    if retracement < 0.25:
        score += 8
    if flag_range_pct < 0.05:
        score += 5  # very tight flag

    stop   = flag_low
    target = pivot + (pole_top - pole_base)   # measured move = pole height

    return True, {
        "pattern":      "Bull Flag",
        "pivot":        float(pivot),
        "stop_loss":    float(stop),
        "target_price": float(target),
        "score":        min(int(score), 100),
        "status":       status,
        "ai_score":     min(int(score), 100),
        "plot":         None,
    }


# ─────────────────────────────────────────────
#  4. VCP – VOLATILITY CONTRACTION PATTERN
#     (Minervini-style multi-stage)
# ─────────────────────────────────────────────

def find_volatility_contraction(df):
    """
    True Minervini VCP: at least 2 contractions where each successive price
    range is SMALLER than the previous one.

    Stages: we look for progressively tightening swings over the last 40–80 bars.
    """
    if len(df) < 40:
        return False, "Short data"

    df = calculate_mas(df)
    closes = df['Close'].values
    highs  = df['High'].values
    lows   = df['Low'].values
    n = len(closes)

    # ── Find swing pivots in last 80 bars ───────────────────────────────
    window    = min(80, n)
    seg_h     = highs[-window:]
    seg_l     = lows[-window:]
    seg_c     = closes[-window:]

    # Divide the window into 4 equal segments and compute range of each
    seg_size  = window // 4
    if seg_size < 5:
        return False, "Segments too small"

    ranges = []
    for i in range(4):
        s = i * seg_size
        e = s + seg_size
        seg_closes = closes[max(n - window + s, 0): max(n - window + e, 1)]
        mean_c = np.mean(seg_closes) if len(seg_closes) > 0 else 1.0
        r = (np.max(seg_h[s:e]) - np.min(seg_l[s:e])) / max(mean_c, 1e-9)
        ranges.append(r)

    # Check that ranges are generally contracting (each next < previous)
    contractions = sum(1 for i in range(1, len(ranges)) if ranges[i] < ranges[i - 1])
    if contractions < 2:
        return False, f"VCP: only {contractions}/3 contractions"

    # Final window = tightest so far (last seg_size bars)
    final_seg_h = seg_h[-seg_size:]
    final_seg_l = seg_l[-seg_size:]
    max_h  = np.max(final_seg_h)
    min_l  = np.min(final_seg_l)
    width  = (max_h - min_l) / max(min_l, 1e-9)

    if width > 0.12:
        return False, f"Final consolidation too wide ({width:.1%})"

    current = closes[-1]
    pivot   = max_h

    score  = 58
    status = "Forming"
    vol_confirm = check_volume_breakout(df)
    dist = (pivot - current) / pivot

    if current > pivot:
        status = "Breakout"
        score += 20
        if vol_confirm:
            score += 15
    elif dist < 0.02:
        status = "Near Pivot"
        score += 12
    elif dist < 0.04:
        status = "Near Pivot"
        score += 7

    # Contraction quality
    score += contractions * 5    # 2 → +10, 3 → +15
    if width < 0.05:
        score += 8               # very tight final stage

    # Volume profile: should decline in VCP
    vol_trend = _volume_trend(df, window=max(seg_size, 5))
    if vol_trend < 0:
        score += 5

    # Overall width bonus
    target    = pivot * 1.20    # conservative 20% target
    stop      = min_l

    return True, {
        "pattern":      "VCP / Flat Base",
        "pivot":        float(pivot),
        "stop_loss":    float(stop),
        "target_price": float(target),
        "score":        min(int(score), 100),
        "status":       status,
        "ai_score":     min(int(score), 100),
        "contractions": contractions,
        "plot":         None,
    }


# ─────────────────────────────────────────────
#  5. ASCENDING TRIANGLE  (new)
# ─────────────────────────────────────────────

def find_ascending_triangle(df):
    """
    Ascending Triangle: flat resistance top + rising lows.
    High-probability breakout pattern.
    """
    if len(df) < 40:
        return False, "Not enough data"

    df = calculate_mas(df)
    closes = df['Close'].values
    highs  = df['High'].values
    lows   = df['Low'].values
    n = len(closes)

    window = min(60, n)
    seg_h  = highs[-window:]
    seg_l  = lows[-window:]

    # ── Flat Resistance: top highs should cluster around a common level ──
    order    = 3
    peak_rel = argrelextrema(seg_h, np.greater, order=order)[0]
    if len(peak_rel) < 2:
        return False, "Not enough resistance peaks"

    peak_prices = seg_h[peak_rel]
    res_level   = np.median(peak_prices)
    # Peaks should all be within 3% of median
    res_spread  = np.std(peak_prices) / res_level
    if res_spread > 0.03:
        return False, f"Resistance not flat ({res_spread:.1%} spread)"

    # ── Rising Lows (ascending support) ─────────────────────────────────
    trough_rel = argrelextrema(seg_l, np.less, order=order)[0]
    if len(trough_rel) < 2:
        return False, "Not enough rising lows"

    # Fit a line through the troughs – must have positive slope
    trough_xs     = trough_rel
    trough_prices = seg_l[trough_rel]
    slope, intercept, r, _, _ = linregress(trough_xs, trough_prices)
    if slope <= 0:
        return False, "Lows not rising"
    if r**2 < 0.50:
        return False, "Rising lows not linear enough"

    # ── Squeeze: latest price vs resistance level ─────────────────────────
    current   = closes[-1]
    pivot     = res_level
    dist      = (pivot - current) / pivot

    score  = 60
    status = "Forming"
    vol_confirm = check_volume_breakout(df)

    if current > pivot:
        status = "Breakout"
        score += 20
        if vol_confirm:
            score += 10
    elif dist < 0.02:
        status = "Near Pivot"
        score += 15              # triangle near apex is IDEAL pre-breakout
    elif dist < 0.05:
        status = "Near Pivot"
        score += 8

    # Bonus: strong rising lows (high R²)
    score += int(r**2 * 10)

    # Target: height of widest part of triangle projected from breakout
    triangle_height = res_level - np.min(seg_l)
    target = pivot + triangle_height
    stop   = float(linregress(trough_xs, trough_prices)[0] * trough_xs[-1] + linregress(trough_xs, trough_prices)[1])
    # stop = interpolated support at current bar
    support_now = slope * (window - 1) + intercept
    stop = max(support_now - 0.01 * support_now, np.min(seg_l[-10:]))

    return True, {
        "pattern":      "Ascending Triangle",
        "pivot":        float(pivot),
        "stop_loss":    float(stop),
        "target_price": float(target),
        "score":        min(int(score), 100),
        "status":       status,
        "ai_score":     min(int(score), 100),
        "plot":         None,
    }


# ─────────────────────────────────────────────
#  6. DOUBLE BOTTOM  (new)
# ─────────────────────────────────────────────

def find_double_bottom(df):
    """
    Double Bottom (W pattern): two roughly equal lows separated by a peak.
    Second bottom ideally slightly higher than first (bullish divergence).
    """
    if len(df) < 40:
        return False, "Not enough data"

    df = calculate_mas(df)
    prices = df['Close'].values
    lows   = df['Low'].values
    n = len(prices)

    window   = min(120, n)
    seg_lows = lows[-window:]

    order    = 5
    trough_rel = argrelextrema(seg_lows, np.less, order=order)[0]
    if len(trough_rel) < 2:
        return False, "Need at least 2 troughs"

    # Take the two most recent troughs
    b1_rel = trough_rel[-2]
    b2_rel = trough_rel[-1]

    b1_price = seg_lows[b1_rel]
    b2_price = seg_lows[b2_rel]

    # Bottoms must be within 5% of each other
    diff = abs(b1_price - b2_price) / max(b1_price, 1e-9)
    if diff > 0.05:
        return False, f"Bottoms too different ({diff:.1%})"

    # Peak between the two bottoms (neckline)
    between_prices = prices[-window + b1_rel: -window + b2_rel + 1]
    if len(between_prices) < 3:
        return False, "No peak between bottoms"
    neckline = np.max(between_prices)

    # Separation: at least 10 bars between bottoms
    sep = b2_rel - b1_rel
    if sep < 10:
        return False, "Bottoms too close"

    # Second bottom slightly higher = bullish
    second_higher = b2_price > b1_price

    current  = prices[-1]
    pivot    = neckline
    dist     = (pivot - current) / pivot

    score  = 55
    status = "Forming"
    vol_confirm = check_volume_breakout(df)

    if current > pivot:
        status = "Breakout"
        score += 20
        if vol_confirm:
            score += 10
    elif dist < 0.03:
        status = "Near Pivot"
        score += 12
    elif dist < 0.05:
        status = "Near Pivot"
        score += 7

    if second_higher:
        score += 10   # bullish divergence
    if diff < 0.02:
        score += 8    # nearly identical bottoms

    height = neckline - min(b1_price, b2_price)
    target = neckline + height
    stop   = min(b1_price, b2_price) * 0.98

    return True, {
        "pattern":      "Double Bottom",
        "pivot":        float(pivot),
        "stop_loss":    float(stop),
        "target_price": float(target),
        "score":        min(int(score), 100),
        "status":       status,
        "ai_score":     min(int(score), 100),
        "plot":         None,
    }
