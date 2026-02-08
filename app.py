from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import yfinance as yf
from tradingview_screener import Query, Column
import technical
import matplotlib
matplotlib.use('Agg')
import plotting
import os
import requests
import json
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Load environment variables
load_dotenv()

# Page Config
st.set_page_config(page_title="High Prob Pattern Scanner", layout="wide", page_icon="🦅")

# --- OpenRouter Integration ---
def get_ai_analysis(ticker, pattern_type, plot_path):
    """
    Sends the chart to OpenRouter (Claude-3.5-Sonnet recommended) for analysis.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return "⚠️ OpenRouter API Key not found. Please set OPENROUTER_API_KEY in .env file."

    # Encode image
    with open(plot_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501", # Required by OpenRouter
        "X-Title": "PatternScanner"
    }
    
    prompt = f"""
    You are a professional technical analyst. I have identified a potential {pattern_type} on the 4H chart for {ticker}.
    Please analyze the attached chart image paying close attention to:
    1. The quality of the pattern structure (symmetry, depth).
    2. Volume characteristics (is there volume expansion on breakout/right side?).
    3. Key resistance/support levels.
    
    Return a valid JSON object with the following fields:
    - "verdict": "BUY", "WAIT", or "IGNORE"
    - "score": A number between 0 and 100 representing the probability of success.
    - "reasoning": A 2-sentence explanation of why you assigned this score.
    """

    data = {
        "model": "anthropic/claude-3.5-sonnet", # High vision capability
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded_string}"
                        }
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            # Clean up markdown code blocks if any
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        else:
            return {"score": 0, "reasoning": f"Error: {response.text}", "verdict": "ERROR"}
    except Exception as e:
        print(f"AI Req Error: {e}")
        return {"score": 0, "reasoning": f"Request Failed: {e}", "verdict": "ERROR"}

# --- TV Screener ---
@st.cache_data(ttl=300)
def get_screened_stocks():
    """
    Uses tradingview-screener to find liquid, uptrending stocks.
    # Query for High Probability Candidates (S&P 500 Proxy + Trend + Volume)
    # Re-introducing filters to increase "Win Probability" as requested.
    """
    q = Query().select('name', 'close', 'volume', 'market_cap_basic', 'relative_volume_10d_calc', 'change').where(
        Column('market_cap_basic') > 15_000_000_000, 
        Column('volume') > 500_000,
        
        # High Probability Filters:
        Column('close') > Column('SMA200'), # In a long-term uptrend
        # REMOVED: change > 0 (Handles can be red days)
        # REMOVED: rel_vol > 1.0 (Handles often have low volume / VCP)
    ).limit(300) # Scan top 300 candidates
    
    return q.get_scanner_data()



# --- Fundamental Analysis ---
def categorize_fundamentals(ticker):
    """
    Categorizes stock into Platinum, Gold, Silver, Bronze based on growth/quality.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        
        rev_growth = info.get('revenueGrowth', 0)
        earn_growth = info.get('earningsGrowth', 0)
        margins = info.get('profitMargins', 0)
        
        # Check for valid data
        if rev_growth is None: rev_growth = 0
        if earn_growth is None: earn_growth = 0
        if margins is None: margins = 0
        
        score = 0
        reason = []
        
        # Growth Scoring
        if rev_growth > 0.25: 
            score += 2
            reason.append("High Rev Growth")
        elif rev_growth > 0.15:
            score += 1
            
        if earn_growth > 0.25:
            score += 2
            reason.append("High Earnings Growth")
        elif earn_growth > 0.15:
            score += 1
            
        if margins > 0.20:
            score += 1
            reason.append("High Margins")
            
        # Categorization
        if score >= 4:
            return "Platinum", " ".join(reason)
        elif score >= 2:
            return "Gold", "Moderate Growth"
        elif score >= 1:
            return "Silver", "Positive Trend"
        else:
            return "Bronze", "Weak Fundamentals"
            
    except Exception:
        return "Bronze", "No Data"

def process_ticker(ticker, debug_mode=True):
    """
    Process a single ticker: Download data, check patterns, and verify with AI.
    Returns a dict with results to be handled by the main thread.
    """
    logs = []
    try:
        # 2. Get 4H Data
        # Fetching 1 year of data to catch longer cup bases
        df = yf.download(ticker, period="730d", interval="1h", progress=False) 
        
        if df.empty: 
            return {'ticker': ticker, 'match': None, 'logs': [f"❌ {ticker}: No Data Fetch"], 'error': "No Data"}
        
        # Resample to 4H
        ohlc_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }
        
        if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
        df_4h = df.resample('4h').agg(ohlc_dict).dropna()
        
        if len(df_4h) < 50: 
            return {'ticker': ticker, 'match': None, 'logs': [f"❌ {ticker}: Not Enough Bars ({len(df_4h)})"], 'error': "Not Enough Bars"}
        
        # 3. Check Patterns
        found_ch, details_ch = technical.find_cup_and_handle(df_4h)
        found_ihs, details_ihs = technical.find_inverse_head_and_shoulders(df_4h)
        
        potential_match = None
        
        if found_ch:
            plot_path = plotting.plot_pattern(df_4h, ticker, details_ch, f"{ticker}_ch.png")
            details_ch['ticker'] = ticker
            details_ch['plot'] = plot_path
            potential_match = details_ch
        elif found_ihs:
            plot_path = plotting.plot_pattern(df_4h, ticker, details_ihs, f"{ticker}_ihs.png")
            details_ihs['ticker'] = ticker
            details_ihs['plot'] = plot_path
            potential_match = details_ihs
        else:
            # details_ch is the error message if found_ch is False
            validation_msg = details_ch if isinstance(details_ch, str) else "No Pattern"
            return {'ticker': ticker, 'match': None, 'logs': [f"❌ {ticker}: Tech Fail - {validation_msg}"], 'error': validation_msg}

        if potential_match:
            # 4. Get Fundamentals (Only for matches)
            cat, cat_reason = categorize_fundamentals(ticker)
            potential_match['category'] = cat
            potential_match['cat_reason'] = cat_reason
            
            # 5. AI Verification (Automatic)
            try:
                ai_result = get_ai_analysis(ticker, potential_match['pattern'], potential_match['plot'])
                score = ai_result.get('score', 0)
                
                # Fallback: Use technical score if AI fails
                if score == 0 or ai_result.get('verdict') == 'ERROR':
                    score = potential_match.get('score', 60)  # Use technical score
                    ai_result = {
                        'score': score,
                        'reasoning': f"Technical Score: {score}/100 (AI unavailable)",
                        'summary': "Using technical pattern score only",
                        'verdict': "TECHNICAL"
                    }
                    logs.append(f"⚠️ {ticker}: AI failed, using technical score {score}")
                
                potential_match['ai_score'] = score
                potential_match['ai_reasoning'] = ai_result.get('reasoning', "N/A")
                potential_match['ai_summary'] = ai_result.get('summary', ai_result.get('reasoning', "N/A"))
                potential_match['ai_verdict'] = ai_result.get('verdict', "N/A")
                
                return {'ticker': ticker, 'match': potential_match, 'logs': logs, 'error': None}
                    
            except Exception as e:
                # Fallback: Use technical score on exception
                score = potential_match.get('score', 60)
                potential_match['ai_score'] = score
                potential_match['ai_reasoning'] = f"Technical Score (AI Error: {str(e)[:50]})"
                potential_match['ai_summary'] = "Using technical pattern score only"
                potential_match['ai_verdict'] = "TECHNICAL"
                
                msg = f"❌ {ticker}: AI Exception - {str(e)[:80]}"
                logs.append(msg)
                
                return {'ticker': ticker, 'match': potential_match, 'logs': logs, 'error': None}
            
    except Exception as e:
        return {'ticker': ticker, 'match': None, 'logs': [f"❌ {ticker}: Processing Error - {str(e)[:80]}"], 'error': str(e)}

# --- Main App ---
import json
import os

CACHE_FILE = "scan_cache.json"

def save_cache(matches):
    try:
        data = {
            "timestamp": time.time(),
            "matches": matches
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Cache Save Error: {e}")

def load_cache():
    if not os.path.exists(CACHE_FILE):
        return None, None
    
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
            
        # Check Expiry (4 hours = 14400 seconds)
        if time.time() - data["timestamp"] > 14400:
            return None, None
            
        return data["matches"], data["timestamp"]
    except Exception:
        return None, None

# --- Main App ---
st.title("🦅 Eagle Eye: High Probability Breakout Scanner")
st.markdown("Scanning **S&P 500 / High Cap Leaders** for **Cup & Handle** / **Inv. H&S** patterns on the **4H Timeframe**.")

# Filters
c1, c2 = st.columns(2)
with c1:
    min_score = st.slider("Min AI Score", 0, 100, 70, help="Minimum proprietary 'Eagle Eye' score to display.")
with c2:
    selected_cats = st.multiselect("Fundamental Category", ["Platinum", "Gold", "Silver", "Bronze"], default=["Platinum", "Gold", "Silver"], help="Filter by fundamental strength (Platinum = High Growth/Margins).")

# Initialize Session State from Cache if needed
if 'scan_results' not in st.session_state:
    cached_matches, cached_ts = load_cache()
    if cached_matches:
        st.session_state['scan_results'] = cached_matches
        st.session_state['scan_time'] = cached_ts
        st.toast("Restored results from 4-hour cache", icon="💾")

# Action Buttons
col_scan, col_clear = st.columns([4, 1])
with col_scan:
    start_scan = st.button("🚀 Scan High Probability Setups", use_container_width=True)
with col_clear:
    clear_cache = st.button("🗑️ Force Clear", use_container_width=True)

if clear_cache:
    if 'scan_results' in st.session_state:
        del st.session_state['scan_results']
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    st.rerun()

if start_scan:
    # Clear previous results
    if 'scan_results' in st.session_state:
        del st.session_state['scan_results']
        
    debug_mode = st.checkbox("Show Debug Logs", value=True)
    status = st.empty()
    progress = st.progress(0)
    
    status.write("🔍 Phase 1: Rapid Trend Scan (Daily Data)...")
    try:
        # 1. Get Universe
        total_count, results_df = get_screened_stocks()
        
        # Extract Tickers
        if 'name' in results_df.columns:
            tickers = results_df['name'].tolist()
        elif 'ticker' in results_df.columns:
            tickers = results_df['ticker'].tolist()
        elif 'symbol' in results_df.columns:
             tickers = results_df['symbol'].tolist()
        else:
            st.error(f"Cannot find ticker column. Available: {results_df.columns}")
            st.stop()
            
        st.write(f"✅ Found {total_count} candidates. Filtering for strong trends (Above SMA50)...")
        
        # --- PHASE 1: Bulk Daily Scan (Fast) ---
        start_time = time.time()
        passed_tickers = []
        chunk_size = 50 
        
        for i in range(0, len(tickers), chunk_size):
            chunk = tickers[i:i+chunk_size]
            progress.progress((i / len(tickers)) * 0.3)
            status.write(f"Phase 1: Checking Trend... ({i}/{len(tickers)})")
            
            try:
                data = yf.download(chunk, period="1y", interval="1d", group_by='ticker', progress=False, threads=True)
                
                for ticker in chunk:
                    try:
                        if len(chunk) > 1:
                            df_daily = data[ticker]
                        else:
                            df_daily = data 
                        
                        df_daily = df_daily.dropna()
                        if df_daily.empty: continue
                        
                        df_daily = technical.calculate_mas(df_daily)
                        is_uptrend, _ = technical.check_trend_template(df_daily)
                        
                        if is_uptrend:
                            passed_tickers.append(ticker)
                            
                    except Exception:
                        continue
            except Exception as e:
                print(f"Bulk DL Error: {e}")
                
        # --- PHASE 2: Deep 4H Scan ---
        status.write(f"Phase 2: Deep Pattern Analysis on {len(passed_tickers)} Prime Candidates...")
        st.write(f"✨ Phase 1 Complete: Filtered {len(tickers)} -> {len(passed_tickers)} Prime Candidates")
        
        matches = []
        debug_logs = []
        
        if not passed_tickers:
           st.warning("No stocks passed the Trend Template filter. Try loosening requirements.")
           st.stop()

        max_workers = 8 
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {executor.submit(process_ticker, ticker, debug_mode): ticker for ticker in passed_tickers}
            
            completed_count = 0
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                completed_count += 1
                
                prog_val = 0.3 + ((completed_count / len(passed_tickers)) * 0.7)
                progress.progress(prog_val)
                status.write(f"Phase 2: Analyzing Patterns... ({completed_count}/{len(passed_tickers)}) - Last: {ticker}")
                
                try:
                    result = future.result()
                    if result['logs'] and debug_mode:
                         if len(debug_logs) < 20: debug_logs.extend(result['logs'])
                    
                    if result['match']:
                        matches.append(result['match'])
                        st.toast(f"Found {result['match']['category']} Setup: {ticker}", icon="🔥")
                        
                except Exception as exc:
                    if debug_mode: debug_logs.append(f"❌ {ticker}: Exception: {exc}")

        status.empty()
        progress.empty()
        
        st.session_state['scan_results'] = matches
        st.session_state['scan_time'] = time.time()
        save_cache(matches) # Save to disk
        st.rerun()
            
    except Exception as master_e:
        st.error(f"Scanner Error: {master_e}")

# --- Result Display (Persistent) ---
if 'scan_results' in st.session_state:
    matches = st.session_state['scan_results']
    scan_time = st.session_state.get('scan_time', time.time())
    
    # Cache Indicator
    mins_ago = int((time.time() - scan_time) / 60)
    st.info(f"⚡ Displaying cached results from {mins_ago} minutes ago.", icon="💾")
    
    # Filter Matches based on current inputs
    filtered_matches = [m for m in matches if m['category'] in selected_cats and m['ai_score'] >= min_score]
    
    if filtered_matches:
        st.success(f"🎉 Found {len(filtered_matches)} High Probability Setups!")
        
        # Display Mode Toggle
        view_mode = st.radio("Display Mode", ["Table View", "Detailed View"], horizontal=True, label_visibility="collapsed")
        
        # SORTING LOGIC: Breakout Status -> Category Rank -> Score
        cat_rank = {"Platinum": 0, "Gold": 1, "Silver": 2, "Bronze": 3}
        
        def sort_key(x):
            status_priority = 0 if x.get('status') == "Breakout!" else 1
            return (status_priority, cat_rank.get(x['category'], 99), -x['ai_score'])
            
        filtered_matches.sort(key=sort_key)
        
        # Prepare Data
        display_data = []
        for m in filtered_matches:
             entry_price = m.get('pivot', m.get('neckline_price'))
             stop_loss = m.get('stop_loss', 0)
             target_price = m.get('target_price', 0)
             risk = entry_price - stop_loss
             reward = target_price - entry_price
             rr_ratio = reward / risk if risk > 0 else 0
             
             display_data.append({
                "Ticker": m['ticker'],
                "Category": m['category'],
                "Pattern": m['pattern'],
                "Status": m.get('status', 'Forming'),
                "Score": m['ai_score'],
                "Entry ($)": round(entry_price, 2) if entry_price else 0,
                "Stop ($)": round(stop_loss, 2),
                "Target ($)": round(target_price, 2),
                "R:R": round(rr_ratio, 2),
                "Verdict": m['ai_verdict'],
                "Plot": m['plot'],
                "Reason": m['cat_reason'],
                "Summary": m['ai_summary']
            })
        
        df_results = pd.DataFrame(display_data)

        if view_mode == "Table View":
            st.dataframe(
                df_results.drop(columns=['Plot', 'Reason', 'Summary']),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Category": st.column_config.TextColumn("Category", help="Fundamental Rating (Platinum > Gold > Silver)"),
                    "Score": st.column_config.ProgressColumn("Score", format="%d", min_value=0, max_value=100, help="Pattern Quality Score (0-100)"),
                    "Status": st.column_config.TextColumn("Status", help="Current Pattern Stage (Forming vs Breakout)"),
                    "R:R": st.column_config.NumberColumn("R:R", format="1:%.1f", help="Risk/Reward Ratio"),
                    "Ticker": st.column_config.TextColumn("Ticker", help="Stock Symbol"),
                }
            )
        else: # Detailed View
            for m in filtered_matches:
                # Badge Style
                cat_colors = {
                    "Platinum": "#e5e4e2", "Gold": "#ffd700", 
                    "Silver": "#c0c0c0", "Bronze": "#cd7f32"
                }
                c_color = cat_colors.get(m['category'], "#eee")
                
                with st.expander(f"🏆 {m['ticker']} - {m['category']} | {m['status']} | Score: {m['ai_score']}", expanded=True):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown(f"<span style='background-color:{c_color}; color:black; padding:2px 6px; border-radius:4px;'><b>{m['category']}</b></span> {m['cat_reason']}", unsafe_allow_html=True)
                        st.image(m['plot'])
                        st.info(f"**AI Summary:** {m['ai_summary']}")
                    with c2:
                        st.subheader("Details")
                        st.metric("Score", f"{m['ai_score']}/100", delta=m['ai_verdict'])
                        st.metric("Status", m.get('status', 'Forming'))
                        
                        entry = m.get('pivot', 0)
                        if entry: st.metric("Entry", f"${entry:.2f}")
                        
                        c_stop, c_tgt = st.columns(2)
                        st.metric("Stop", f"${m.get('stop_loss', 0):.2f}")
                        st.metric("Target", f"${m.get('target_price', 0):.2f}")
                        
        # CSV Download
        csv = df_results.drop(columns=['Plot']).to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Filtered Results CSV", csv, "scan_results.csv", "text/csv")

    else:
        st.warning("No matches found with current filters.")
