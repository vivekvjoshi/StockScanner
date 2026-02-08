import mplfinance as mpf
import pandas as pd
import os

def plot_pattern(df, ticker, pattern_details, filename):
    """
    Plots the candlestick chart with pattern annotations.
    """
    if not os.path.exists("plots"):
        os.makedirs("plots")
        
    path = f"plots/{filename}"
    
    # Create pattern specific lines
    addplots = []
    
    if pattern_details['pattern'] == 'Cup and Handle':
        # Pivot Line
        pivot = pattern_details['pivot']
        pivot_line = [pivot] * len(df)
        addplots.append(mpf.make_addplot(pivot_line, color='blue', linestyle='--'))
        
    elif pattern_details['pattern'] == 'Inverse Head and Shoulders':
        # Neckline
        neckline = pattern_details['neckline_price']
        neck_line = [neckline] * len(df)
        addplots.append(mpf.make_addplot(neck_line, color='orange', linestyle='--'))
        
        # Stop Loss
        stop = pattern_details['stop_loss']
        stop_line = [stop] * len(df)
        addplots.append(mpf.make_addplot(stop_line, color='red', linestyle=':'))

    # Custom Style
    s = mpf.make_mpf_style(base_mpf_style='yahoo', rc={'font.size': 8})
    
    # Save fig
    mpf.plot(
        df, 
        type='candle', 
        style=s,
        title=f"{ticker} - {pattern_details['pattern']}",
        volume=True,
        addplot=addplots,
        savefig=dict(fname=path, dpi=100, bbox_inches='tight')
    )
    
    return path
