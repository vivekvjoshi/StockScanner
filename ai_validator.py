import streamlit.components.v1 as components
import base64
import os

def get_puter_ai_insight(ticker, analysis_type="chart", image_path=None):
    """
    Returns a Streamlit HTML component that uses Puter.js (browser-side) 
     to get AI insights WITHOUT any API keys.
    """
    prompt = ""
    image_data = ""
    
    if analysis_type == "chart" and image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()
        prompt = f"Look at this stock chart for {ticker}. Is this a high-quality Cup and Handle? Should I buy the breakout? Give me a 1-sentence bull/bear verdict."
    else:
        prompt = f"Explain the Wheel Strategy potential for {ticker}. Why is it a good or bad time to sell Puts? Give me a 1-sentence expert opinion."

    # The HTML/JS snippet that calls Puter.js
    # This runs in the user's browser, using THEIR Puter session.
    html_code = f"""
    <div id="puter-container-{ticker}" style="
        background: linear-gradient(135deg, rgba(46, 204, 113, 0.1) 0%, rgba(39, 174, 96, 0.05) 100%);
        padding: 16px; 
        border-radius: 12px; 
        border: 1px solid rgba(46, 204, 113, 0.3); 
        font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        font-size: 14px; 
        margin-top: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    ">
        <div id="puter-loading-{ticker}" style="display: flex; align-items: center; gap: 8px; color: #666;">
            <div class="spinner" style="
                width: 16px; 
                height: 16px; 
                border: 2px solid #2ecc71; 
                border-top-color: transparent; 
                border-radius: 50%; 
                animation: spin 1s linear infinite;
            "></div>
            <span>Institutional AI analyzing {ticker}...</span>
        </div>
        <div id="puter-result-{ticker}" style="color: #2c3e50; line-height: 1.5; display: none;">
            <div style="font-weight: 600; color: #27ae60; margin-bottom: 4px; display: flex; align-items: center; gap: 5px;">
                <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm3.5 4.5L7 10.5 4.5 8l-1 1 3.5 3.5 5.5-5.5-1-1z"/></svg>
                Puter AI Verdict:
            </div>
            <div id="text-content-{ticker}"></div>
        </div>
        <div id="puter-error-{ticker}" style="color: #e74c3c; display: none;">
             ⚠️ AI Unavailable. Please <a href="https://puter.com" target="_blank" style="color: #2ecc71; text-decoration: underline; font-weight: 600;">Login to Puter.com</a> to enable analysis.
        </div>
    </div>

    <style>
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        #puter-container-{ticker} a {{ color: #2ecc71; transition: color 0.2s; }}
        #puter-container-{ticker} a:hover {{ color: #27ae60; }}
    </style>

    <script src="https://js.puter.com/v2/"></script>
    <script>
        (function() {{
            const prompt = `{prompt}`;
            const imageData = "{image_data}";
            const ticker = "{ticker}";
            
            async function getInsight() {{
                try {{
                    let response;
                    if (imageData) {{
                        response = await puter.ai.chat(prompt, "data:image/png;base64," + imageData);
                    }} else {{
                        response = await puter.ai.chat(prompt);
                    }}
                    
                    document.getElementById('puter-loading-' + ticker).style.display = 'none';
                    const resDiv = document.getElementById('puter-result-' + ticker);
                    document.getElementById('text-content-' + ticker).innerText = response;
                    resDiv.style.display = 'block';
                }} catch (e) {{
                    console.error("Puter AI Error:", e);
                    document.getElementById('puter-loading-' + ticker).style.display = 'none';
                    document.getElementById('puter-error-' + ticker).style.display = 'block';
                }}
            }}
            
            if (window.puter) {{
                getInsight();
            }} else {{
                setTimeout(getInsight, 1000);
            }}
        }})();
    </script>
    """
    return html_code

def analyze_chart(image_path, ticker):
    """Legacy wrapper for the new JS component approach"""
    return get_puter_ai_insight(ticker, analysis_type="chart", image_path=image_path)
