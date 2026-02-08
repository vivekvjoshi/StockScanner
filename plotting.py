import mplfinance as mpf
import pandas as pd
import os

def plot_pattern(df, ticker, pattern_details, filename):
    """
    Clean, minimal chart with just candlesticks and key levels
    """
    if not os.path.exists("plots"):
        os.makedirs("plots")
        
    path = f"plots/{filename}"
    
    # Only essential pattern lines
    apds = []
    
    pattern_type = pattern_details.get('pattern', '')
    
    # Add ONLY the breakout/pivot line (most important)
    pivot = pattern_details.get('pivot')
    if pivot:
        pivot_line = [pivot] * len(df)
        apds.append(mpf.make_addplot(pivot_line, color='#00ff00', 
                                     linestyle='--', width=2, alpha=0.8))
    
    # Add stop loss (secondary)
    stop = pattern_details.get('stop_loss')
    if stop:
        stop_line = [stop] * len(df)
        apds.append(mpf.make_addplot(stop_line, color='#ff5252', 
                                     linestyle=':', width=1.5, alpha=0.6))
    
    # Clean styling
    mc = mpf.make_marketcolors(
        up='#26a69a',
        down='#ef5350',
        edge='inherit',
        wick={'up':'#26a69a', 'down':'#ef5350'},
        volume={'up':'#26a69a', 'down':'#ef5350'}
    )
    
    s = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle=':',
        gridcolor='#333333',
        facecolor='#0e0e0e',
        figcolor='#0e0e0e',
        y_on_right=False
    )
    
    # Simple title
    score = pattern_details.get('score', 0)
    status = pattern_details.get('status', '')
    title = f"{ticker} - {pattern_type} | Score: {score}/100"
    if status:
        title += f" | {status}"
    
    # Create clean plot
    fig, axes = mpf.plot(
        df,
        type='candle',
        style=s,
        addplot=apds if apds else None,
        volume=True,
        panel_ratios=(4, 1),
        figsize=(12, 7),
        title=dict(title=title, fontsize=14, color='#ffffff', weight='bold'),
        ylabel='Price ($)',
        ylabel_lower='Volume',
        returnfig=True,
        warn_too_much_data=len(df)+1
    )
    
    # Minimal styling adjustments
    ax_main = axes[0]
    ax_vol = axes[1]
    
    # Clean up axes
    for ax in [ax_main, ax_vol]:
        ax.tick_params(colors='#cccccc', labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor('#333333')
    
    fig.tight_layout()
    fig.savefig(path, dpi=100, bbox_inches='tight', 
                facecolor='#0e0e0e', edgecolor='none')
    
    import matplotlib.pyplot as plt
    plt.close(fig)
    
    return path
