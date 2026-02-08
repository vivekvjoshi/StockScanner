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

# --- Caching System ---
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
def get_screened_stocks(selected_cats=None):
    """
    Uses tradingview-screener to find liquid, uptrending stocks.
    Dynamically adjusts filters based on selected categories to reduce scan time.
    """
    # Default Strictness (Low)
    min_mkt_cap = 15_000_000_000
    min_volume = 500_000
    
    # If selected_cats provided, adjust filters upstream
    if selected_cats:
        # If user ONLY wants Platinum/Gold, we can be stricter upstream
        has_bronze = "Bronze" in selected_cats
        has_silver = "Silver" in selected_cats
        has_gold = "Gold" in selected_cats
        has_platinum = "Platinum" in selected_cats
        
        if not has_bronze and not has_silver:
            if has_platinum and not has_gold:
                # STRICTEST: Platinum Only
                min_mkt_cap = 50_000_000_000 # Only Giants
            elif has_platinum or has_gold:
                # STRICT: Platinum/Gold
                min_mkt_cap = 30_000_000_000

    q = Query().select('name', 'close', 'volume', 'market_cap_basic', 'relative_volume_10d_calc', 'change').where(
        Column('market_cap_basic') > min_mkt_cap, 
        Column('volume') > min_volume,
        Column('close') > Column('SMA200'), # Long-term uptrend
    ).limit(300)
    
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
            reason.append("Rev>25%")
        elif rev_growth > 0.15:
            score += 1
            
        if earn_growth > 0.25:
            score += 2
            reason.append("Earn>25%")
        elif earn_growth > 0.15:
            score += 1
            
        if margins > 0.20:
            score += 1
            reason.append("Margin>20%")
            
        # Categorization
        # Platinum: Needs 4+ points (e.g. High Rev + High Earn, or High Rev + Good Earn + High Margin)
        if score >= 4:
            return "Platinum", "High Growth Elite (" + ", ".join(reason) + ")"
        elif score >= 2:
            return "Gold", "Strong Performer"
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

# Page Config
# --- Main App ---
st.set_page_config(page_title="Eagle Eye Scanner", layout="wide", page_icon="🦅")

# --- CSS Styles ---
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        border-radius: 5px;
        font-weight: bold;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- Sidebar Controls ---
with st.sidebar:
    st.title("🦅 Eagle Eye")
    st.markdown("---")
    
    st.subheader("⚙️ Scanner Settings")
    
    min_score = st.slider("Min AI Score", 0, 100, 70, help="Filter results by proprietary 'Eagle Eye' score.")
    
    cat_help = """
    **Strict Filtering Logic:**
    - 💎 **Platinum:** Market Cap > $50B (Elite Leaders)
    - 🥇 **Gold:** Market Cap > $30B (Strong Large Caps)
    - 🥈 **Silver+:** Market Cap > $15B (Broad Search)
    """
    selected_cats = st.multiselect(
        "Fundamental Focus", 
        ["Platinum", "Gold", "Silver", "Bronze"], 
        default=["Platinum", "Gold", "Silver"], 
        help=cat_help
    )
    
    selected_statuses = st.multiselect(
        "Pattern Status",
        ["Breakout", "Near Pivot", "Forming", "Weak Setup"],
        default=["Breakout", "Near Pivot"],
        help="**Breakout**: Price breaking pivot.\n**Near Pivot**: Within 5% of pivot.\n**Forming**: Setup still developing."
    )
    
    # Dynamic Info on Scan Scope
    if not "Silver" in selected_cats and not "Bronze" in selected_cats:
        if "Platinum" in selected_cats and not "Gold" in selected_cats:
             st.info("🎯 **Elite Mode:** Scanning only $50B+ Giants.")
        else:
             st.info("🎯 **Strict Mode:** Scanning only $30B+ Leaders.")
    else:
        st.info("🌐 **Broad Mode:** Scanning top 300 stocks > $15B.")

    st.markdown("---")
    
    col_scan, col_reset = st.columns(2)
    with col_scan:
        start_scan = st.button("🚀 Run Scan", type="primary", use_container_width=True)
    with col_reset:
        clear_cache = st.button("🗑️ Reset Cache", use_container_width=True)
        
    debug_mode = st.checkbox("Show Debug Logs", value=True)
    
    st.markdown("---")
    st.caption("v2.1 | Powered by Claude 3.5 Sonnet")

# --- Main Content ---
st.title("High Probability Breakout Scanner")
st.markdown("**Identifying Cup & Handle / Inv. Head & Shoulders patterns on 4H Timeframe.**")

# Handle Cache Reset
if clear_cache:
    if 'scan_results' in st.session_state:
        del st.session_state['scan_results']
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    st.rerun()

# Initialize State
if 'scan_results' not in st.session_state:
    cached_matches, cached_ts = load_cache()
    if cached_matches:
        st.session_state['scan_results'] = cached_matches
        st.session_state['scan_time'] = cached_ts

# --- Scanning Logic ---
if start_scan:
    # Clear previous
    if 'scan_results' in st.session_state:
        del st.session_state['scan_results']

    with st.status("🚀 Initiating Market Scan...", expanded=True) as status:
        try:
            # Phase 1
            status.write("🔍 Phase 1: Fetching Universe & filtering for Uptrends...")
            total_count, results_df = get_screened_stocks(selected_cats)
            
            if 'name' in results_df.columns:
                tickers = results_df['name'].tolist()
            elif 'ticker' in results_df.columns:
                tickers = results_df['ticker'].tolist()
            elif 'symbol' in results_df.columns:
                 tickers = results_df['symbol'].tolist()
            else:
                st.error("Column error in scanner results.")
                st.stop()
                
            status.write(f"✅ Universe: {total_count} Candidates. Checking Daily Trends...")
            
            passed_tickers = []
            chunk_size = 20
            
            bar = st.progress(0)
            
            for i in range(0, len(tickers), chunk_size):
                chunk = tickers[i:i+chunk_size]
                bar.progress(min((i / len(tickers)) * 0.3, 1.0))
                # Update status label with progress
                status.write(f"📉 Checking Trend: Batch {i}-{min(i+len(chunk), len(tickers))}")
                
                try:
                    data = yf.download(chunk, period="1y", interval="1d", group_by='ticker', progress=False, threads=False)
                    for ticker in chunk:
                        try:
                            # Handle data structure
                            if len(chunk) > 1:
                                if ticker in data.columns.levels[0]:
                                    df_daily = data[ticker]
                                else: continue
                            else:
                                df_daily = data
                                
                            df_daily = df_daily.dropna()
                            if df_daily.empty: continue
                            
                            df_daily = technical.calculate_mas(df_daily)
                            is_uptrend, _ = technical.check_trend_template(df_daily)
                            
                            if is_uptrend:
                                passed_tickers.append(ticker)
                        except: continue
                except Exception as e:
                    print(e)
            
            # Phase 2
            if not passed_tickers:
                status.update(label="❌ No stocks passed Trend Filter.", state="error")
                st.stop()
                
            status.write(f"✨ Trend Filter Passed: {len(passed_tickers)} Aggressive Uptrends detected.")
            status.update(label=f"🔍 Phase 2: Deep Pattern Analysis on {len(passed_tickers)} tickers...", state="running")
            
            matches = []
            debug_logs = []
            max_workers = 8
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_ticker = {executor.submit(process_ticker, ticker, debug_mode): ticker for ticker in passed_tickers}
                completed = 0
                
                for future in as_completed(future_to_ticker):
                    completed += 1
                    ticker = future_to_ticker[future]
                    
                    prog = 0.3 + ((completed / len(passed_tickers)) * 0.7)
                    bar.progress(min(prog, 1.0))
                    
                    try:
                        res = future.result()
                        if res['logs'] and debug_mode: 
                             debug_logs.extend(res['logs'])
                        
                        if res['match']:
                            matches.append(res['match'])
                            st.toast(f"Found {res['match']['category']} Setup: {ticker}", icon="🔥")
                    except Exception as exc:
                        if debug_mode: debug_logs.append(f"Error {ticker}: {exc}")
            
            bar.empty()
            status.update(label="✅ Scan Complete!", state="complete", expanded=False)
            
            st.session_state['scan_results'] = matches
            st.session_state['scan_time'] = time.time()
            st.session_state['total_scanned'] = total_count
            st.session_state['trend_passed'] = len(passed_tickers)
            
            save_cache(matches)
            st.rerun()

        except Exception as e:
            status.update(label="❌ Critical Error", state="error")
            st.error(f"Scanner failed: {e}")

# --- Results Display ---
if 'scan_results' in st.session_state:
    matches = st.session_state['scan_results']
    scan_time = st.session_state.get('scan_time', time.time())
    
    # Filter
    filtered = [m for m in matches if m['category'] in selected_cats and m['ai_score'] >= min_score and m['status'] in selected_statuses]

    # --- Metrics Header ---
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Universe", st.session_state.get('total_scanned', 'N/A'))
    with m2:
        st.metric("Patterns Found", len(matches), help="Total technical patterns identified.")
    with m3:
        st.metric("Matches Shown", len(filtered), help=f"Results passing Score > {min_score} & selected Categories.")
    with m4:
        mins = int((time.time() - scan_time) / 60)
        st.metric("Data Age", f"{mins}m ago")
    
    def sort_key(x):
        status_priority = 0 if x.get('status') == "Breakout" else 1
        return (status_priority, -x['ai_score'])
    filtered.sort(key=sort_key)
    
    if not filtered:
        st.warning(f"No results match your current filters (Score > {min_score}, Categories: {selected_cats}).")
    else:
        tab_table, tab_cards = st.tabs(["📋 Table Results", "🔍 Detailed Analysis"])
        
        with tab_table:
            # Prepare DF
            data = []
            for m in filtered:
                 ep = m.get('pivot', m.get('neckline_price')) or 0
                 sl = m.get('stop_loss', 0)
                 tp = m.get('target_price', 0)
                 risk = ep - sl
                 rr = (tp - ep) / risk if risk > 0 else 0
                 
                 data.append({
                    "Ticker": m['ticker'],
                    "Category": m['category'],
                    "Status": m.get('status', 'Forming'),
                    "Pattern": m['pattern'],
                    "Score": m['ai_score'],
                    "Entry": ep,
                    "Stop": sl,
                    "Target": tp,
                    "R:R": rr,
                    "Plot": m['plot'],
                    "Summary": m['ai_summary'],
                    "Reason": m['cat_reason']
                })
            df = pd.DataFrame(data)
            
            st.dataframe(
                df.drop(columns=['Plot', 'Summary', 'Reason']),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Category": st.column_config.TextColumn("Category", width="medium"),
                    "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
                    "R:R": st.column_config.NumberColumn("R:R", format="1:%.1f"),
                    "Entry": st.column_config.NumberColumn("Entry", format="$%.2f"),
                    "Stop": st.column_config.NumberColumn("Stop", format="$%.2f"),
                    "Target": st.column_config.NumberColumn("Target", format="$%.2f"),
                }
            )
            
            csv = df.drop(columns=['Plot']).to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", csv, "results.csv", "text/csv")
            
        with tab_cards:
            for m in filtered:
                cat_colors = {"Platinum": "#e5e4e2", "Gold": "#ffd700", "Silver": "#c0c0c0", "Bronze": "#cd7f32"}
                c_color = cat_colors.get(m['category'], "#eee")
                
                with st.expander(f"{m['ticker']} | {m['category']} | Score: {m['ai_score']}", expanded=True):
                    c1, c2 = st.columns([1.5, 1])
                    with c1:
                        st.image(m['plot'])
                    with c2:
                        st.markdown(f"### {m['ticker']}")
                        st.caption(m['cat_reason'])
                        st.info(m['ai_summary'])
                        st.metric("Entry Trigger", f"${m.get('pivot',0):.2f}")
                        st.metric("Stop Loss", f"${m.get('stop_loss',0):.2f}")

st.divider()
st.warning("⚠️ **DISCLAIMER:** Trading involves risk. Technical analysis is probabilistic. Always verify with your own due diligence.")
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
def get_screened_stocks(selected_cats=None):
    """
    Uses tradingview-screener to find liquid, uptrending stocks.
    Dynamically adjusts filters based on selected categories to reduce scan time.
    """
    # Default Strictness (Low)
    min_mkt_cap = 15_000_000_000
    min_volume = 500_000
    
    # If selected_cats provided, adjust filters upstream
    if selected_cats:
        # If user ONLY wants Platinum/Gold, we can be stricter upstream
        has_bronze = "Bronze" in selected_cats
        has_silver = "Silver" in selected_cats
        has_gold = "Gold" in selected_cats
        has_platinum = "Platinum" in selected_cats
        
        if not has_bronze and not has_silver:
            if has_platinum and not has_gold:
                # STRICTEST: Platinum Only
                min_mkt_cap = 50_000_000_000 # Only Giants
            elif has_platinum or has_gold:
                # STRICT: Platinum/Gold
                min_mkt_cap = 30_000_000_000

    q = Query().select('name', 'close', 'volume', 'market_cap_basic', 'relative_volume_10d_calc', 'change').where(
        Column('market_cap_basic') > min_mkt_cap, 
        Column('volume') > min_volume,
        Column('close') > Column('SMA200'), # Long-term uptrend
    ).limit(300)
    
    return q.get_scanner_data()



# --- OpenRouter Integration ---

