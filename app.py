from dotenv import load_dotenv
import streamlit as st
import pandas as pd
import yfinance as yf
from tradingview_screener import Query, Column
import technical
import plotting
import os
import requests
import json
import base64

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

# --- Fundamental Check ---
def check_fundamentals(ticker):
    """
    checks detailed fundamentals using yfinance (Only when needed)
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        
        # 1. Cash > Debt - REMOVED per user request
        # total_cash = info.get('totalCash', 0)
        # total_debt = info.get('totalDebt', 0)
        # if total_debt > total_cash:
        #    return False, f"Debt ({total_debt/1e9:.1f}B) > Cash"
            
        # 2. Growth
        rev_growth = info.get('revenueGrowth', 0)
        earn_growth = info.get('earningsGrowth', 0)
        
        if rev_growth <= 0 or earn_growth <= 0:
             return False, "No Growth"
             
        return True, "Fundamentals Strong"
        
    except Exception:
        return False, "Data Unavailable"

# --- Main App ---
st.title("🦅 Eagle Eye: High Probability Breakout Scanner")
st.markdown("Scanning **S&P 500 / High Cap Leaders** for **Cup & Handle** / **Inv. H&S** patterns on the **4H Timeframe**.")

if st.button("🚀 Scan High Probability Setups"):
    debug_mode = st.checkbox("Show Debug Logs (Why stocks are failing)", value=True)
    status = st.empty()
    progress = st.progress(0)
    
    status.write("🔍 Querying TradingView for Strict Trend Template Stocks...")
    try:
        # 1. Get Universe from TV Screener (returns tuple: (count, dataframe))
        total_count, results_df = get_screened_stocks()
        
        st.write(f"✅ Found {total_count} momentum candidates. Analyzing top {len(results_df)} with 4H Technicals & Fundamentals...")
        
        # Ticker column usually 'name' or 'ticker'
        if 'name' in results_df.columns:
            tickers = results_df['name'].tolist()
        elif 'ticker' in results_df.columns:
            tickers = results_df['ticker'].tolist()
        elif 'symbol' in results_df.columns:
             tickers = results_df['symbol'].tolist()
        else:
            st.error(f"Cannot find ticker column. Available: {results_df.columns}")
            st.stop()
        
        matches = []
        debug_logs = []
        
        for i, ticker in enumerate(tickers):
            progress.progress((i+1)/len(tickers))
            
            # --- Quick Fundamental Check - DISABLED to focus on Price Action ---
            # passed_fund, fund_msg = check_fundamentals(ticker)
            # if not passed_fund:
            #      if debug_mode and len(debug_logs) < 20: 
            #          debug_logs.append(f"⚠️ {ticker}: Fundamental Weak - {fund_msg} (Proceeding)")
                 
            status.write(f"Analyzing {ticker} 4H Chart...")
            
            try:
                # 2. Get 4H Data
                # Use yfinance only for plotting and deep technicals as requested
                # Fetching 1 year of data to catch longer cup bases
                df = yf.download(ticker, period="730d", interval="1h", progress=False) 
                
                if df.empty: 
                    if debug_mode and len(debug_logs) < 10: debug_logs.append(f"❌ {ticker}: No Data Fetch")
                    continue
                
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
                    if debug_mode and len(debug_logs) < 10: debug_logs.append(f"❌ {ticker}: Not Enough Bars ({len(df_4h)})")
                    continue 
                
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
                    if debug_mode and len(debug_logs) < 10:
                        # details_ch is the error message if found_ch is False
                        validation_msg = details_ch if isinstance(details_ch, str) else "No Pattern"
                        debug_logs.append(f"❌ {ticker}: Tech Fail - {validation_msg}")

                if potential_match:
                    # 4. AI Verification (Automatic) - OPTIONAL
                    status.write(f"🤖 AI Verifying {ticker}...")
                    
                    try:
                        ai_result = get_ai_analysis(ticker, potential_match['pattern'], potential_match['plot'])
                        score = ai_result.get('score', 0)
                        
                        # Fallback: Use technical score if AI fails
                        if score == 0 or ai_result.get('verdict') == 'ERROR':
                            score = details.get('score', 60)  # Use technical score
                            ai_result = {
                                'score': score,
                                'reasoning': f"Technical Score: {score}/100 (AI unavailable)",
                                'summary': "Using technical pattern score only",
                                'verdict': "TECHNICAL"
                            }
                            if debug_mode:
                                debug_logs.append(f"⚠️ {ticker}: AI failed, using technical score {score}")
                        
                        potential_match['ai_score'] = score
                        potential_match['ai_reasoning'] = ai_result.get('reasoning', "N/A")
                        potential_match['ai_summary'] = ai_result.get('summary', ai_result.get('reasoning', "N/A"))
                        potential_match['ai_verdict'] = ai_result.get('verdict', "N/A")
                        
                        if score > 75:
                            matches.append(potential_match)
                            
                    except Exception as e:
                        # Fallback: Use technical score on exception
                        score = details.get('score', 60)
                        potential_match['ai_score'] = score
                        potential_match['ai_reasoning'] = f"Technical Score (AI Error: {str(e)[:50]})"
                        potential_match['ai_summary'] = "Using technical pattern score only"
                        potential_match['ai_verdict'] = "TECHNICAL"
                        
                        if score > 75:
                            matches.append(potential_match)
                        
                        if debug_mode:
                            debug_logs.append(f"❌ {ticker}: AI Exception - {str(e)[:80]}")
                    
            except Exception as e:
                if debug_mode and len(debug_logs) < 20:
                    debug_logs.append(f"❌ {ticker}: Processing Error - {str(e)[:80]}")

                
        status.empty()
        progress.empty()
        
        if matches:
            st.success(f"🎉 Found {len(matches)} High Probability Setups (Score > 75)!")
            
            # Sort by Score Descending
            matches.sort(key=lambda x: x['ai_score'], reverse=True)
            
            for m in matches:
                with st.expander(f"🏆 {m['ticker']} - {m['pattern']} (Score: {m['ai_score']}/100)", expanded=True):
                    c1, c2 = st.columns([2, 1])
                    
                    with c1:
                        st.image(m['plot'])
                        st.markdown(f"**🤖 AI Summary:** {m['ai_summary']}")
                        
                    with c2:
                        st.subheader("🎯 Trade Setup")
                        st.metric("AI Score", f"{m['ai_score']}/100", delta=m['ai_verdict'])
                        
                        entry_price = m.get('pivot', m.get('neckline_price')) 
                        if entry_price:
                            st.metric("Entry", f"${entry_price:.2f}")
                        
                        c_stop, c_tgt = st.columns(2)
                        c_stop.metric("Stop", f"${m.get('stop_loss', 0):.2f}")
                        c_tgt.metric("Target", f"${m.get('target_price', 0):.2f}")
                        
                        risk = entry_price - m.get('stop_loss', 0)
                        reward = m.get('target_price', 0) - entry_price
                        if risk > 0:
                            rr = reward / risk
                            st.write(f"**R:R:** 1:{rr:.1f}")

        else:
            st.warning("No setups > 75 Score found. Try lowering standards or checking manual matches.")
            
        if debug_mode and debug_logs:
            with st.expander("🛠️ Debug Logs (First 10 Failures)"):
                for log in debug_logs:
                    st.write(log)
            
    except Exception as master_e:
        st.error(f"Scanner Error: {master_e}")
