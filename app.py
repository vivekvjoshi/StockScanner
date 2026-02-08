import streamlit as st
import pandas as pd
import yfinance as yf
import fundamentals
import technical
import scanner_plotting
import os
import ai_validator
import streamlit.components.v1 as components

st.set_page_config(page_title="Cup & Handle Scanner", layout="wide")

st.title("📈 Trading Strategy Command Center")
st.markdown("""
This dashboard provides institutional-grade technical scans for **Cup & Handle** patterns and **Wheel Strategy** opportunities in SPDR ETFs.
""")

tabs = st.tabs(["🏆 Cup & Handle Scanner", "💰 Wheel Strategy (ETFs)"])

# Puter AI Status Banner
st.success("✅ Institutional Puter AI Enabled — No Keys Required")
st.info("💡 **Tip:** Ensure you are logged into [puter.com](https://puter.com) in this browser tab for seamless AI breakout analysis.")
with tabs[0]:
    st.header("🏆 Cup & Handle Pattern Scanner")
    st.info("Institutional-grade scan for high-quality rounding bottoms with handles.")
    
    # Scanner Settings inside the tab
    c1, c2 = st.columns([1, 1])
    with c1:
        universe = st.selectbox("Scanner Universe", ["S&P 500", "Nasdaq 100", "Major ETFs & SPY/QQQ"], key="ch_universe")
    with c2:
        limit_options = [10, 25, 50, 100, 250, 500]
        limit = st.select_slider("Number of Stocks to Scan", options=limit_options, value=25, key="ch_limit")
    
    run_ch_btn = st.button("🚀 Run Pattern Scan", type="primary", key="run_ch_button", use_container_width=True)

    if run_ch_btn:
        st.write(f"### Scanning {universe}...")
        
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        # Determine tickers based on selection
        import fundamentals as fund
        if universe == "S&P 500":
            all_tickers = fund.get_sp500_tickers()
        elif universe == "Nasdaq 100":
            all_tickers = fund.get_nasdaq_tickers()
        else:
            all_tickers = fund.get_spdr_tickers()
            
        tickers_to_scan = all_tickers[:limit]
        
        results = []
        
        # Placeholder for API key if needed for AI validation
        api_key = os.getenv("PUTER_AI_API_KEY") # Or however you manage your API key

        for i, ticker in enumerate(tickers_to_scan):
            progress_bar.progress((i + 1) / len(tickers_to_scan))
            status_text.text(f"Checking {ticker} ({i+1}/{len(tickers_to_scan)})...")
            
            passed_fund, fund_data = fund.check_fundamentals(ticker)
            
            if passed_fund:
                name = fund_data.get('name', ticker)
                earnings = fund_data.get('earnings', 'N/A')
                sector = fund_data.get('sector', 'N/A')
                
                try:
                    # Download data
                    df = yf.download(ticker, period="2y", interval="1d", progress=False, multi_level_index=False)
                    
                    if df.empty or len(df) < 200:
                        continue
                    
                    found, details = technical.find_cup_and_handle(df)
                    
                    if found:
                        details['ticker'] = ticker
                        
                        # Generate Plot
                        plot_path = scanner_plotting.plot_cup_and_handle(df, ticker, details)
                        details['plot_path'] = plot_path
                        
                        # Add fundamental data
                        details['name'] = name
                        details['sector'] = sector
                        details['earnings'] = earnings
                        details['market_cap_B'] = round(fund_data.get('marketCap', 0) / 1e9, 1)
                        details['pe_ratio'] = fund_data.get('trailingPE', 'N/A')
                        
                        # AI Verification
                        if api_key and plot_path:
                            status_text.text(f"🤖 Puter AI Analyzing chart for {ticker}...")
                            ai_resp = ai_validator.analyze_chart(plot_path, api_key)
                            details['ai_analysis'] = ai_resp
                            
                        results.append(details)
                        
                except Exception as e:
                    # st.error(f"Error processing {ticker}: {e}") # For debugging
                    pass
            
        progress_bar.empty()
        status_text.empty()
            
        if results:
            st.balloons()
            st.write(f"### 🎉 Found {len(results)} Matches!")
            
            df_res = pd.DataFrame(results)
            # Sort by RR Ratio (institutional benchmark)
            if 'rr_ratio' in df_res.columns:
                df_res = df_res.sort_values(by='rr_ratio', ascending=False)
            
            cols = ['ticker', 'name', 'earnings', 'sector', 'suggested_entry', 'stop_loss', 'target_price', 'rr_ratio']
            cols = [c for c in cols if c in df_res.columns]
            st.dataframe(df_res[cols], use_container_width=True)
            
            for res in df_res.to_dict('records'):
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.subheader(f"{res['ticker']}")
                    st.info(f"Setting up for breakout")
                    st.write(f"**Name:** {res.get('name', '')}")
                    st.write(f"📅 **Earnings:** {res.get('earnings', 'N/A')}")
                    st.markdown("#### 🎯 Trade Setup")
                    c_enter, c_stop, c_tgt = st.columns(3)
                    c_enter.metric("Entry", f"${res.get('suggested_entry', 0)}")
                    c_stop.metric("Stop Loss", f"${res.get('stop_loss', 0)}")
                    c_tgt.metric("Target", f"${res.get('target_price', 0)}")
                    
                    if 'plot_path' in res:
                        st.divider()
                        st.markdown("#### 🤖 Puter AI Institutional Verdict")
                        # Call the new JS-based AI component
                        ai_html = ai_validator.analyze_chart(res['plot_path'], res['ticker'])
                        components.html(ai_html, height=180)
                with c2:
                    if res.get('plot_path') and os.path.exists(res['plot_path']):
                        st.image(res['plot_path'], caption=f"{res['ticker']} Setup")
                st.divider()
        else:
            st.warning("No patterns found.")

with tabs[1]:
    st.header("💰 Wheel Strategy Command Center")
    st.markdown("Find reliable stocks for selling Cash Secured Puts. Ideal for consistent income.")
    
    wheel_mode = st.radio("Scan Mode", ["Sector ETFs (SPDR)", "Broad Market Scan (<$30, Profitable)"], horizontal=True)
    
    import wheel
    
    if wheel_mode == "Sector ETFs (SPDR)":
        run_wheel_btn = st.button("🚀 Scan SPDR ETFs", type="primary", key="run_wheel_etfs")
        
        if run_wheel_btn:
            st.write("### Analyzing all SPDR Sector ETFs...")
            wheel_status = st.empty()
            wheel_progress = st.progress(0)
            
            tickers = wheel.SPDR_SECTORS
            wheel_results = []
            
            for i, (ticker, name) in enumerate(tickers.items()):
                wheel_status.text(f"Analyzing {ticker} ({name})...")
                wheel_progress.progress((i + 1) / len(tickers))
                
                data = wheel.get_wheel_data(ticker, name)
                if data:
                    wheel_results.append(data)
            
            wheel_status.empty()
            wheel_progress.empty()
            
            if wheel_results:
                df_wheel = pd.DataFrame(wheel_results)
                st.dataframe(df_wheel, use_container_width=True)
                
                st.write("### 🎯 Recommended Opportunities")
                # Sort by RSI (Low to High - better entries)
                df_wheel = df_wheel.sort_values(by="RSI", ascending=True)
                
                for _, row in df_wheel.iterrows():
                    with st.expander(f"{row['Ticker']} - {row['Name']} ({row['Status']})", expanded=(row['RSI'] < 45)):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Price", f"${row['Price']}")
                        c2.metric("RSI (14)", row['RSI'])
                        c3.metric("IV %", row['IV'])
                        c4.metric("Div Yield", row['Yield'])
                        
                        # Add Puter AI Opinion
                        ai_html = ai_validator.get_puter_ai_insight(row['Ticker'], analysis_type="text")
                        components.html(ai_html, height=150)
    
    else:
        # Broad Market Scan
        st.info("🔍 Searching for stocks < $30 that have been profitable for at least 3 years and are in an uptrend.")
        scan_limit = st.select_slider("Stocks to check (from S&P 500/Russell)", options=[50, 100, 250, 500], value=100)
        
        run_broad_btn = st.button("🚀 Start Institutional Wheel Scan", type="primary", key="run_broad_wheel")
        
        if run_broad_btn:
            # Re-use fundamental logic but with new filters
            status_text = st.empty()
            progress_bar = st.progress(0)
            
            # Determine tickers based on selection
            import fundamentals as fund
            # For Broad Market Scan, we use the same universe setting if preferred, 
            # but usually it's S&P 500 or Russell. Let's provide a local choice or use sidebar.
            # Using S&P 500 as default base for broad scan unless changed.
            all_tickers = fund.get_sp500_tickers()
            
            tickers = all_tickers[:scan_limit] 
            
            wheel_results = []
            
            for i, ticker in enumerate(tickers):
                progress = (i + 1) / len(tickers)
                progress_bar.progress(progress)
                status_text.text(f"Checking {ticker} ({i+1}/{len(tickers)})...")
                
                try:
                    t = yf.Ticker(ticker)
                    info = t.info
                    
                    price = info.get('regularMarketPrice') or info.get('currentPrice', 1000)
                    
                    # Criteria 1: < $30
                    if price >= 30:
                        continue
                        
                    # Criteria 2: Profitable (3+ years)
                    financials = t.financials
                    if financials.empty or 'Net Income' not in financials.index:
                        continue
                    
                    net_inc = financials.loc['Net Income']
                    # Using iloc[:3] assuming the data is sorted by year descending (common in yfinance)
                    if len(net_inc) < 3 or not (net_inc.iloc[:3] > 0).all():
                        continue
                        
                    # Criteria 3: Uptrend (Price > 200MA)
                    hist = t.history(period="1y")
                    if len(hist) < 200: continue
                    ma200 = hist['Close'].rolling(200).mean().iloc[-1]
                    if price <= ma200:
                        continue
                        
                    # If all passed, get full wheel data
                    data = wheel.get_wheel_data(ticker, info.get('shortName', ticker))
                    if data:
                        wheel_results.append(data)
                        
                except:
                    continue
            
            status_text.empty()
            progress_bar.empty()
            
            if wheel_results:
                st.success(f"🎉 Found {len(wheel_results)} powerful opportunities!")
                df_broad = pd.DataFrame(wheel_results)
                # Sort by RSI ascending (best entries first)
                df_broad = df_broad.sort_values(by="RSI", ascending=True)
                
                st.dataframe(df_broad, use_container_width=True)
                
                for _, row in df_broad.iterrows():
                    with st.expander(f"{row['Ticker']} - {row['Name']} ({row['Status']})", expanded=(row['RSI'] < 45)):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Price", f"${row['Price']}")
                        c2.metric("RSI (14)", row['RSI'])
                        c3.metric("IV %", row['IV'])
                        c4.metric("Div Yield", row['Yield'])
                        
                        # Add Puter AI Opinion for each Wheel candidate
                        ai_html = ai_validator.get_puter_ai_insight(row['Ticker'], analysis_type="text")
                        components.html(ai_html, height=150)
            else:
                st.warning("No stocks found matching the criteria in this batch.")
