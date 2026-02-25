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

# --- OpenRouter Integration (Optional) ---
def get_ai_analysis(ticker, pattern_type, plot_path):
    """
    Sends the chart to OpenRouter (Claude-3.5-Sonnet) for backend automated scoring.
    Only runs if API Key is present.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None 

    # Encode image
    try:
        with open(plot_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    except:
        return {"score": 0, "reasoning": "Image Load Error", "verdict": "ERROR"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501", 
        "X-Title": "PatternScanner"
    }
    
    prompt = f"Analyze chart for {ticker}. Pattern: {pattern_type}. Return JSON: {{'verdict': 'BUY'/'WAIT', 'score': 0-100, 'reasoning': 'brief text'}}."

    data = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_string}"}}
                ]
            }
        ]
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        else:
            return None
    except Exception as e:
        return None

# --- TV Screener ---
@st.cache_data(ttl=300)
def get_screened_stocks(selected_cats=None, include_etfs=True):
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

    # 1. Get Normal Stocks
    q_stocks = Query().select('name', 'close', 'volume', 'market_cap_basic', 'relative_volume_10d_calc', 'change').where(
        Column('market_cap_basic') > min_mkt_cap, 
        Column('volume') > min_volume,
        Column('close') > Column('SMA200'), # Long-term uptrend
    ).limit(300)
    
    count_s, df_stocks = q_stocks.get_scanner_data()
    
    if include_etfs:
        # 2. Get Spyder ETFs (No Market Cap filter)
        spyder_etfs = ['XLU', 'XLE', 'XLF', 'XLK', 'XLV', 'XLP', 'XLY', 'XLB', 'XLI', 'XLRE', 'XLC', 'SPY', 'QQQ', 'DIA', 'IWM']
        q_etfs = Query().select('name', 'close', 'volume', 'market_cap_basic', 'relative_volume_10d_calc', 'change').where(
            Column('name').isin(spyder_etfs),
            Column('close') > Column('SMA200')
        )
        
        try:
            count_e, df_etfs = q_etfs.get_scanner_data()
            # Combine
            # Using pd.concat instead of append
            if count_s > 0 and count_e > 0:
                df_combined = pd.concat([df_stocks, df_etfs], ignore_index=True)
                return count_s + count_e, df_combined
            elif count_e > 0:
                return count_e, df_etfs
            elif count_s > 0:
                return count_s, df_stocks
            else:
                return 0, pd.DataFrame()
        except Exception as e:
            return count_s, df_stocks
    else:
        return count_s, df_stocks

# --- Fundamental Analysis ---
def categorize_fundamentals(ticker):
    """
    Categorizes stock into Platinum, Gold, Silver, Bronze based on growth/quality.
    """
    spyder_etfs = ['XLU', 'XLE', 'XLF', 'XLK', 'XLV', 'XLP', 'XLY', 'XLB', 'XLI', 'XLRE', 'XLC', 'SPY', 'QQQ', 'DIA', 'IWM']
    if ticker in spyder_etfs:
        return "ETF", "Major Market ETF"

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
    Process a single ticker: Download data, check patterns.
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
        matches = []
        
        # Run all scanners
        check_funcs = [
            technical.find_cup_and_handle,
            technical.find_inverse_head_and_shoulders,
            technical.find_bull_flag,
            technical.find_volatility_contraction
        ]
        
        for func in check_funcs:
            try:
                found, details = func(df_4h)
                if found:
                    matches.append(details)
            except Exception as e:
                logs.append(f"⚠️ {ticker}: {func.__name__} error: {e}")

        if not matches:
            return {'ticker': ticker, 'match': None, 'logs': [f"❌ {ticker}: No Patterns Found"], 'error': "No Patterns"}

        # Select best match based on score
        best_match = max(matches, key=lambda x: x['score'])
        
        # Generate Plot
        safe_pattern_name = best_match['pattern'].replace(' ', '_').replace('/', '')
        plot_path = plotting.plot_pattern(df_4h, ticker, best_match, f"{ticker}_{safe_pattern_name}.png")
        best_match['ticker'] = ticker
        best_match['plot'] = plot_path
        
        potential_match = best_match

        if potential_match:
            # 4. Get Fundamentals (Only for matches)
            cat, cat_reason = categorize_fundamentals(ticker)
            potential_match['category'] = cat
            potential_match['cat_reason'] = cat_reason
            
            # 5. Populate Default AI Fields (Technical Only)
            potential_match['ai_score'] = potential_match['score']
            potential_match['ai_reasoning'] = "Technical Analysis Only"
            potential_match['ai_summary'] = "AI not enabled (Add OpenRouter Key to enable)"
            potential_match['ai_verdict'] = "TECHNICAL"
            
            # Optional: Try Backend AI if Key Exists
            try:
                ai_result = get_ai_analysis(ticker, potential_match['pattern'], potential_match['plot'])
                if ai_result:
                    potential_match['ai_score'] = ai_result.get('score', potential_match['score'])
                    potential_match['ai_reasoning'] = ai_result.get('reasoning', "AI Verified")
                    potential_match['ai_summary'] = ai_result.get('reasoning', "AI Verified")
                    potential_match['ai_verdict'] = ai_result.get('verdict', "VERIFIED")
            except:
                pass

            return {'ticker': ticker, 'match': potential_match, 'logs': logs, 'error': None}
            
    except Exception as e:
        return {'ticker': ticker, 'match': None, 'logs': [f"❌ {ticker}: Processing Error - {str(e)[:80]}"], 'error': str(e)}

# Page Config
# --- Main App ---
st.set_page_config(page_title="Eagle Eye Scanner", layout="wide", page_icon="🦅")

# --- CSS Styles ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Manrope', sans-serif;
        background-color: #f8fafc;
        color: #1e293b;
    }

    /* Titles */
    h1, h2, h3 {
        font-family: 'Manrope', sans-serif;
        font-weight: 800;
        letter-spacing: -0.05em;
        color: #0f172a;
    }

    /* Buttons */
    .stButton>button {
        width: 100%;
        border-radius: 12px;
        font-weight: 700;
        border: none;
        padding: 0.75rem 1rem;
        transition: all 0.2s;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    /* Primary Button (Scan) */
    .stButton>button[kind="primary"] {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
    }
    .stButton>button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(16, 185, 129, 0.4);
    }

    /* Secondary Button (Reset) */
    .stButton>button[kind="secondary"] {
        background-color: white;
        color: #64748b;
        border: 1px solid #e2e8f0;
    }
    .stButton>button[kind="secondary"]:hover {
        border-color: #cbd5e1;
        background-color: #f1f5f9;
        color: #334155;
    }

    /* Metric Cards */
    div[data-testid="stMetric"] {
        background-color: white;
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid #f1f5f9;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
        transition: all 0.2s ease-in-out;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        border-color: #e2e8f0;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.875rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 800;
        color: #0f172a;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #f1f5f9;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background-color: white;
        border-radius: 8px;
        border: 1px solid #f1f5f9;
        font-weight: 600;
        color: #334155;
    }
    
    /* Tables */
    div[data-testid="stDataFrame"] {
        border: 1px solid #f1f5f9;
        border-radius: 12px;
        overflow: hidden;
    }

    /* Custom Header Style */
    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 1rem 0;
        margin-bottom: 2rem;
        border-bottom: 1px solid #e2e8f0;
    }
    .header-title {
        font-size: 1.875rem;
        font-weight: 800;
        color: #0f172a;
        letter-spacing: -0.025em;
    }
    .header-subtitle {
        font-size: 0.875rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #10b981;
    }
</style>
""", unsafe_allow_html=True)

# --- Sidebar Controls ---
with st.sidebar:
    st.markdown("<h2 style='text-align: center; color: #10b981;'>🦅 ScanPro</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 12px; font-weight: bold; color: #94a3b8; letter-spacing: 0.1em; text-transform: uppercase;'>Risk-Adjusted Engine</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    st.subheader("⚙️ Scanner Settings")
    if not os.getenv("OPENROUTER_API_KEY"):
         st.info("💡 **Tip:** Add `OPENROUTER_API_KEY` to .env to enable AI verification.")

    min_score = st.slider("Min Pattern Score", 0, 100, 60, help="Filter results by pattern quality.")
    
    cat_help = """
    **Strict Filtering Logic:**
    - 💎 **Platinum:** Market Cap > $50B (Elite Leaders)
    - 🥇 **Gold:** Market Cap > $30B (Strong Large Caps)
    - 🥈 **Silver+:** Market Cap > $15B (Broad Search)
    - 📈 **ETF:** Major Market ETFs (No Market Cap Filter)
    """
    selected_cats = st.multiselect(
        "Fundamental Focus", 
        ["Platinum", "Gold", "Silver", "Bronze", "ETF"], 
        default=["Platinum", "Gold", "Silver", "ETF"], 
        help=cat_help
    )
    
    selected_patterns = st.multiselect(
        "Pattern Type",
        ["Cup & Handle", "Inv H&S", "Bull Flag", "VCP / Flat Base"],
        default=["Cup & Handle", "Inv H&S", "Bull Flag", "VCP / Flat Base"]
    )

    selected_statuses = st.multiselect(
        "Pattern Status",
        ["Breakout", "Near Pivot", "Forming", "Weak Setup"],
        default=["Breakout", "Near Pivot"],
        help="**Breakout**: Price breaking pivot.\n**Near Pivot**: Within 5% of pivot.\n**Forming**: Setup still developing."
    )
    
    include_etfs = st.checkbox("Include Core Sector ETFs", value=True, help="Scan major sector ETFs like XLU, XLK, SPY regardless of market cap.")
    
    # Dynamic Info on Scan Scope
    if not "Silver" in selected_cats and not "Bronze" in selected_cats:
        if "Platinum" in selected_cats and not "Gold" in selected_cats:
             st.info("🎯 **Elite Mode:** Scanning only $50B+ Giants.")
        else:
             st.info("🎯 **Strict Mode:** Scanning only $30B+ Leaders.")
    else:
        st.info("🌐 **Broad Mode:** Scanning top 300 stocks > $15B.")

    st.markdown("---")
    
    col_scan, col_reset = st.columns([1, 1])
    with col_scan:
        start_scan = st.button("🚀 Run", type="primary", use_container_width=True, help="Run Market Scanner")
    with col_reset:
        clear_cache = st.button("🗑️ Clear", use_container_width=True, help="Clear cached data")
        
    debug_mode = st.checkbox("Show Debug Logs", value=True)
    
    st.markdown("---")
    st.caption("v2.1 | Powered by Claude 3.5 Sonnet")

# --- Main Content ---
st.markdown("""
    <div class="header-container">
        <div>
            <div class="header-title">Market Scanner</div>
            <div class="header-subtitle">High Probability Setups • 4H Timeframe</div>
        </div>
        <div>
            <span style="background: #ecfdf5; color: #10b981; padding: 0.5rem 1rem; border-radius: 9999px; font-weight: 700; font-size: 0.75rem;">LIVE MODE</span>
        </div>
    </div>
""", unsafe_allow_html=True)

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
            total_count, results_df = get_screened_stocks(selected_cats, include_etfs)
            
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
                            if isinstance(data.columns, pd.MultiIndex):
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
            completed = 0
            
            # Fetch sequentially to bypass yfinance thread-safety bug (identical prices cross-polluting)
            for ticker in passed_tickers:
                completed += 1
                
                prog = 0.3 + ((completed / len(passed_tickers)) * 0.7)
                bar.progress(min(prog, 1.0))
                
                try:
                    res = process_ticker(ticker, debug_mode)
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
    # Filter
    filtered = [
        m for m in matches 
        if m['category'] in selected_cats 
        and m['ai_score'] >= min_score 
        and m['status'] in selected_statuses
        and m['pattern'] in selected_patterns
    ]

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
    
    st.caption("ℹ️ Displaying candidates based on technical pattern matching.")

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
                    "Score": st.column_config.ProgressColumn("Tech Score", min_value=0, max_value=100, format="%d", help="Technical Pattern Quality (0-100)"),
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
                cat_colors = {"Platinum": "#e5e4e2", "Gold": "#ffd700", "Silver": "#c0c0c0", "Bronze": "#cd7f32", "ETF": "#8fbaff"}
                c_color = cat_colors.get(m['category'], "#eee")
                
                with st.expander(f"{m['ticker']} | {m['category']} | Score: {m['ai_score']}", expanded=True):
                    c1, c2 = st.columns([1.5, 1])
                    with c1:
                        st.image(m['plot'])
                    with c2:
                        st.markdown(f"### {m['ticker']}")
                        st.caption(f"{m['pattern']} • {m['status']}")
                        
                        st.metric("Entry Trigger", f"${m.get('pivot',0):.2f}")
                        st.metric("Stop Loss", f"${m.get('stop_loss',0):.2f}")
                        
                        if m.get('ai_verdict') == 'VERIFIED':
                             st.success(f"🤖 **AI Analysis:** {m.get('ai_reasoning')}")
                        else:
                             st.info(f"💡 **Pattern Note:** {m.get('ai_summary')}")

st.divider()
st.warning("⚠️ **DISCLAIMER:** Trading involves risk. Technical analysis is probabilistic. Always verify with your own due diligence.")
