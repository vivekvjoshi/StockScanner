"""
Automated Stock Scanner Job
Runs headless scans and emails high-probability setups
"""
import os
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
from dotenv import load_dotenv
import yfinance as yf
import pandas as pd
from tradingview_screener import Query, Column
from technical import find_cup_and_handle, find_inverse_head_and_shoulders
from plotting import plot_pattern

# Load environment variables
load_dotenv()

# Email Configuration
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')
RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL')

# Scanner Configuration
MIN_SCORE = int(os.getenv('MIN_SCORE', '80'))  # Only email scores >= 80
MAX_RESULTS = int(os.getenv('MAX_RESULTS', '5'))  # Max stocks per email

def get_screened_stocks():
    """Get stocks from TradingView screener"""
    q = Query().select('name', 'close', 'volume', 'market_cap_basic').where(
        Column('market_cap_basic') > 15_000_000_000, 
        Column('volume') > 500_000,
        Column('close') > Column('SMA200'),
    ).limit(300)
    
    total_count, results_df = q.get_scanner_data()
    return results_df['name'].tolist()

def scan_ticker(ticker):
    """Scan a single ticker for patterns"""
    try:
        # Download data
        df = yf.download(ticker, period="730d", interval="1h", progress=False)
        
        if df.empty:
            return None
            
        # Flatten MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Resample to 4H
        ohlc_dict = {
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }
        
        df_4h = df.resample('4h').agg(ohlc_dict).dropna()
        
        if len(df_4h) < 60:
            return None
            
        # Pattern Detection
        found_ch, details_ch = find_cup_and_handle(df_4h)
        
        if found_ch:
            score = details_ch.get('score', 0)
            
            if score >= MIN_SCORE:
                # Generate chart
                chart_path = plot_pattern(df_4h.tail(200), ticker, details_ch, f'{ticker}_cup.png')
                
                return {
                    'ticker': ticker,
                    'pattern': details_ch.get('pattern'),
                    'score': score,
                    'status': details_ch.get('status'),
                    'pivot': details_ch.get('pivot'),
                    'stop_loss': details_ch.get('stop_loss'),
                    'target': details_ch.get('target_price'),
                    'chart_path': chart_path
                }
        
        # Try Inverse H&S
        found_ihs, details_ihs = find_inverse_head_and_shoulders(df_4h)
        
        if found_ihs:
            score = details_ihs.get('score', 0)
            
            if score >= MIN_SCORE:
                chart_path = plot_pattern(df_4h.tail(200), ticker, details_ihs, f'{ticker}_ihs.png')
                
                return {
                    'ticker': ticker,
                    'pattern': details_ihs.get('pattern'),
                    'score': score,
                    'status': details_ihs.get('status'),
                    'pivot': details_ihs.get('pivot'),
                    'stop_loss': details_ihs.get('stop_loss'),
                    'target': details_ihs.get('target_price'),
                    'chart_path': chart_path
                }
                
    except Exception as e:
        print(f"Error scanning {ticker}: {e}")
        
    return None

def send_email(results):
    """Send email with scan results"""
    if not SENDER_EMAIL or not SENDER_PASSWORD or not RECIPIENT_EMAIL:
        print("❌ Email not configured. Set SENDER_EMAIL, SENDER_PASSWORD, RECIPIENT_EMAIL in .env")
        return False
        
    try:
        # Create message
        msg = MIMEMultipart('related')
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL
        msg['Subject'] = f'🦅 {len(results)} High-Probability Setup{"s" if len(results) > 1 else ""} Found - {datetime.now().strftime("%m/%d/%Y")}'
        
        # Create HTML body
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .header {{ background: #1a1a1a; color: white; padding: 20px; text-align: center; }}
                .stock {{ border: 2px solid #4CAF50; margin: 20px; padding: 15px; border-radius: 10px; }}
                .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
                .label {{ color: #666; font-size: 12px; }}
                .value {{ font-size: 18px; font-weight: bold; color: #4CAF50; }}
                .chart {{ margin: 15px 0; }}
                img {{ max-width: 100%; height: auto; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🦅 Eagle Eye Scanner Alert</h1>
                <p>{datetime.now().strftime("%B %d, %Y at %I:%M %p")}</p>
            </div>
        """
        
        for i, stock in enumerate(results):
            html += f"""
            <div class="stock">
                <h2>{stock['ticker']} - {stock['pattern']}</h2>
                <p><strong>Status:</strong> {stock['status']} | <strong>Score:</strong> {stock['score']}/100</p>
                
                <div class="metric">
                    <div class="label">Entry (Pivot)</div>
                    <div class="value">${stock['pivot']:.2f}</div>
                </div>
                
                <div class="metric">
                    <div class="label">Stop Loss</div>
                    <div class="value">${stock['stop_loss']:.2f}</div>
                </div>
                
                <div class="metric">
                    <div class="label">Target</div>
                    <div class="value">${stock['target']:.2f}</div>
                </div>
                
                <div class="chart">
                    <img src="cid:chart_{i}" alt="{stock['ticker']} Chart">
                </div>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        
        # Attach HTML
        msg.attach(MIMEText(html, 'html'))
        
        # Attach chart images
        for i, stock in enumerate(results):
            try:
                with open(stock['chart_path'], 'rb') as f:
                    img = MIMEImage(f.read())
                    img.add_header('Content-ID', f'<chart_{i}>')
                    msg.attach(img)
            except:
                pass
        
        # Send email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        print(f"✅ Email sent to {RECIPIENT_EMAIL}")
        return True
        
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False

def run_scan():
    """Main scan function"""
    print("=" * 80)
    print(f"🦅 Eagle Eye Scanner Job - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Get stocks to scan
    print("\n📊 Fetching stocks from TradingView...")
    tickers = get_screened_stocks()
    print(f"✓ Found {len(tickers)} candidates")
    
    # Scan for patterns
    print(f"\n🔍 Scanning for patterns (min score: {MIN_SCORE})...")
    results = []
    
    for i, ticker in enumerate(tickers):
        print(f"  [{i+1}/{len(tickers)}] {ticker}...", end=" ")
        
        result = scan_ticker(ticker)
        
        if result:
            print(f"✓ FOUND! Score: {result['score']}")
            results.append(result)
            
            if len(results) >= MAX_RESULTS:
                print(f"\n  → Reached max results ({MAX_RESULTS}), stopping scan")
                break
        else:
            print("✗")
    
    # Report results
    print("\n" + "=" * 80)
    print(f"📈 SCAN COMPLETE")
    print("=" * 80)
    print(f"Total Scanned: {i+1}")
    print(f"High-Quality Setups Found: {len(results)}")
    
    if results:
        print("\n🎯 Found Setups:")
        for r in results:
            print(f"  • {r['ticker']}: {r['pattern']} (Score: {r['score']}/100)")
        
        # Send email
        print("\n📧 Sending email alert...")
        send_email(results)
    else:
        print("\n⚠️ No high-quality setups found today.")
    
    print("\n✓ Job completed\n")

if __name__ == "__main__":
    run_scan()
