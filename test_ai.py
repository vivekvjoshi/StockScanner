"""
Test AI API Call
"""
import os
import json
import requests
import base64
from dotenv import load_dotenv
from plotting import plot_pattern

# Load environment
load_dotenv()
api_key = os.getenv('OPENROUTER_API_KEY')

print("=" * 80)
print("TESTING AI FUNCTIONALITY")
print("=" * 80)

# Step 1: Check API Key
print(f"\n1. API Key Check:")
if api_key:
    print(f"   ✓ API Key Found: {api_key[:15]}...{api_key[-10:]}")
else:
    print(f"   ✗ API Key NOT FOUND in .env")
    exit()

# Step 2: Test Chart Generation
print(f"\n2. Testing Chart Generation:")
try:
    import yfinance as yf
    import pandas as pd
    
    df = yf.download('NVDA', period="730d", interval="1h", progress=False)
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    ohlc_dict = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }
    
    df_4h = df.resample('4h').agg(ohlc_dict).dropna()
    
    pattern_info = {
        'pattern': 'Cup and Handle',
        'pivot': 193.48,
        'stop_loss': 169.55,
        'target_price': 217.41
    }
    
    chart_path = plot_pattern(df_4h.tail(200), 'NVDA', pattern_info, 'test_nvda.png')
    print(f"   ✓ Chart created: {chart_path}")
    
except Exception as e:
    print(f"   ✗ Chart generation failed: {e}")
    import traceback
    traceback.print_exc()
    exit()

# Step 3: Test AI API Call
print(f"\n3. Testing OpenRouter API:")
try:
    # Encode image
    with open(chart_path, 'rb') as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8501",
        "X-Title": "PatternScanner"
    }
    
    prompt = """
    You are a professional technical analyst. Analyze this Cup & Handle pattern on NVDA.
    
    Return a valid JSON object with:
    - "verdict": "BUY", "WAIT", or "IGNORE"
    - "score": A number between 0 and 100
    - "reasoning": A brief explanation
    """
    
    data = {
        "model": "anthropic/claude-3.5-sonnet",
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
    
    print(f"   → Sending request to OpenRouter...")
    response = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                            headers=headers, json=data, timeout=30)
    
    print(f"   → Status Code: {response.status_code}")
    
    if response.status_code == 200:
        content = response.json()['choices'][0]['message']['content']
        print(f"   ✓ AI Response received:")
        print(f"\n{content}\n")
        
        # Try to parse JSON
        content_clean = content.replace("```json", "").replace("```", "").strip()
        result = json.loads(content_clean)
        print(f"   ✓ Parsed JSON:")
        print(f"      Score: {result.get('score')}")
        print(f"      Verdict: {result.get('verdict')}")
        print(f"      Reasoning: {result.get('reasoning')}")
    else:
        print(f"   ✗ API Error:")
        print(f"      Status: {response.status_code}")
        print(f"      Response: {response.text}")
        
except Exception as e:
    print(f"   ✗ API Call failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
