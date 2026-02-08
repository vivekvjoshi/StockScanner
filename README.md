# 🦅 Eagle Eye: High Probability Breakout Scanner

A powerful stock scanner that identifies Cup & Handle and Inverse Head & Shoulders patterns on 4H charts for S&P 500 and high-cap leaders.

## Features

- 🔍 **Smart Screening**: Scans 300+ large-cap stocks using TradingView data
- 📊 **Technical Pattern Detection**: Finds Cup & Handle and Inverse H&S patterns
- 🤖 **Optional AI Analysis**: Uses Claude 3.5 Sonnet for pattern verification (requires OpenRouter credits)
- 📈 **4H Timeframe**: Reduces noise while catching reliable breakouts
- 🎯 **Trade Setups**: Provides pivot points, stop losses, and targets

## Deployment to Streamlit Cloud

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit - Eagle Eye Scanner"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### Step 2: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app"
4. Select your repository
5. Main file path: `app.py`
6. Click "Deploy"

### Step 3: Configure Secrets (Optional - for AI features)

In Streamlit Cloud dashboard:
1. Go to your app settings
2. Click "Secrets"
3. Add your OpenRouter API key:

```toml
OPENROUTER_API_KEY = "sk-or-v1-YOUR-KEY-HERE"
```

**Note**: The scanner works without AI (using technical scores). AI analysis requires OpenRouter credits.

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

## How It Works

1. **TradingView Screening**: Filters stocks above 200-day SMA with $15B+ market cap
2. **Data Fetching**: Downloads 2 years of hourly data and resamples to 4H
3. **Pattern Detection**: Uses fuzzy heuristic logic to find Cup & Handle structures
4. **Scoring**: Technical scoring (60-90) or optional AI scoring (0-100)
5. **Display**: Shows high-probability setups with charts and trade parameters

## Technical Criteria

### Cup & Handle
- Left/Right rim alignment (70-135% ratio)
- Cup depth: 8-60%
- Handle depth: max 22%
- Price near pivot (within 12%)

### Scoring
- Base: 60 points
- Symmetry bonus: +10
- Breakout status: +20
- Near pivot: +10

## Dependencies

- `streamlit` - Web framework
- `yfinance` - Historical price data
- `tradingview-screener` - Stock filtering
- `mplfinance` - Chart generation
- `scipy` - Pattern detection
- `requests` - AI API calls (optional)

## Credits

Built with ❤️ for traders seeking high-probability setups.

## License

MIT
