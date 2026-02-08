# 📧 Automated Email Scanner Setup

## Quick Setup (5 minutes)

### 1️⃣ Configure Email in `.env`

Edit `/Users/vivekjoshi/SAAS/CupAndHandle-main/.env`:

```bash
# For Gmail (Recommended)
SENDER_EMAIL=your-email@gmail.com
SENDER_PASSWORD=your-app-password  # See instructions below
RECIPIENT_EMAIL=your-email@gmail.com  # Where to receive alerts

# Scanner Settings
MIN_SCORE=80          # Only email setups with score >= 80
MAX_RESULTS=5         # Max stocks per email
```

### 2️⃣ Get Gmail App Password

**Important:** Don't use your regular Gmail password!

1. Go to [Google Account Settings](https://myaccount.google.com/)
2. Security → 2-Step Verification (enable if not already)
3. Security → App passwords
4. Select "Mail" and "Mac" 
5. Copy the 16-character password
6. Paste into `.env` as `SENDER_PASSWORD`

### 3️⃣ Test the Scanner

```bash
cd /Users/vivekjoshi/SAAS/CupAndHandle-main
source .venv/bin/activate
python scanner_job.py
```

You should receive an email if any high-quality setups are found!

---

## 🕐 Automated Scheduling Options

### Option A: Cron Job (Mac/Linux) - Run Daily

**Best for:** Running on your local Mac automatically

```bash
# Edit crontab
crontab -e

# Add this line to run every weekday at 6 PM (after market close)
# Minutes Hour Day Month Weekday Command
0 18 * * 1-5 /Users/vivekjoshi/SAAS/CupAndHandle-main/run_scanner.sh
```

**Other Useful Schedules:**
```bash
# Every day at 6 PM
0 18 * * * /Users/vivekjoshi/SAAS/CupAndHandle-main/run_scanner.sh

# Weekdays at 4:30 PM (right after market close)
30 16 * * 1-5 /Users/vivekjoshi/SAAS/CupAndHandle-main/run_scanner.sh

# Every Sunday at 8 AM (weekend screening)
0 8 * * 0 /Users/vivekjoshi/SAAS/CupAndHandle-main/run_scanner.sh
```

**View your cron jobs:**
```bash
crontab -l
```

---

### Option B: GitHub Actions (Cloud) - Free & Reliable

**Best for:** Running automatically without keeping your Mac on

Create `.github/workflows/scanner.yml`:

```yaml
name: Daily Stock Scanner

on:
  schedule:
    # Runs at 6 PM EST weekdays (11 PM UTC)
    - cron: '0 23 * * 1-5'
  workflow_dispatch:  # Allow manual trigger

jobs:
  scan:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run scanner
      env:
        SENDER_EMAIL: ${{ secrets.SENDER_EMAIL }}
        SENDER_PASSWORD: ${{ secrets.SENDER_PASSWORD }}
        RECIPIENT_EMAIL: ${{ secrets.RECIPIENT_EMAIL }}
        MIN_SCORE: 80
        MAX_RESULTS: 5
      run: python scanner_job.py
```

**Setup GitHub Secrets:**
1. Go to your GitHub repo → Settings → Secrets and variables → Actions
2. Add these secrets:
   - `SENDER_EMAIL`
   - `SENDER_PASSWORD`
   - `RECIPIENT_EMAIL`

---

### Option C: macOS Launchd (More Reliable than Cron)

Create `~/Library/LaunchAgents/com.eagleeye.scanner.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.eagleeye.scanner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/vivekjoshi/SAAS/CupAndHandle-main/run_scanner.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/vivekjoshi/SAAS/CupAndHandle-main/logs/scanner.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/vivekjoshi/SAAS/CupAndHandle-main/logs/scanner.error</string>
</dict>
</plist>
```

**Load the job:**
```bash
launchctl load ~/Library/LaunchAgents/com.eagleeye.scanner.plist
launchctl start com.eagleeye.scanner
```

---

## 📧 Email Example

You'll receive beautiful HTML emails with:

- 📊 Stock charts embedded
- 🎯 Entry, Stop Loss, and Target prices
- 📈 Pattern type and score
- ⏰ Timestamp

---

## 🎛️ Customization Options

Edit `.env` to customize:

```bash
MIN_SCORE=85          # Stricter (fewer results)
MIN_SCORE=75          # More lenient (more results)

MAX_RESULTS=10        # More stocks per email
MAX_RESULTS=3         # Fewer stocks per email
```

---

## 🐛 Troubleshooting

### No email received?
```bash
# Test manually
python scanner_job.py

# Check if email config is loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('SENDER_EMAIL'))"
```

### Gmail "Less secure app" error?
- Use an **App Password**, not your regular password
- Enable 2-Factor Authentication first

### Cron job not running?
```bash
# Check cron logs
tail -f /var/log/system.log | grep cron

# Verify permissions
ls -la run_scanner.sh  # Should show -rwxr-xr-x
```

---

## 🎯 Recommended Setup

**For most users:** Use **GitHub Actions** (Option B)
- ✅ Free
- ✅ Runs even when Mac is off
- ✅ Reliable
- ✅ Easy to manage

**For power users:** Use **Launchd** (Option C)
- ✅ More reliable than cron on Mac
- ✅ Runs on your local machine
- ⚠️ Mac must be on

---

Need help? Check the logs:
```bash
tail -f logs/scanner_*.log
```
