import mplfinance as mpf
import pandas as pd
import os

def plot_cup_and_handle(df, ticker, patterns_details, output_dir="plots"):
    """
    Plots the stock chart with the detected Cup and Handle pattern.
    
    Args:
        df (pd.DataFrame): OHLC data.
        ticker (str): Stock ticker.
        patterns_details (dict): details from technical.py containing keys like 'left_rim', 'right_rim'
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    # Prepare data for plotting (last year or so)
    # Ensure index is datetime
    df.index = pd.to_datetime(df.index)
    
    # We want to zoom in on the pattern. 
    # Let's say we plot from Left Rim date minus 30 days to today.
    try:
        left_rim_date = pd.to_datetime(patterns_details['left_rim'][0])
        right_rim_date = pd.to_datetime(patterns_details['right_rim'][0])
        
        start_date = left_rim_date - pd.Timedelta(days=60)
        plot_df = df.loc[start_date:]
        
        # Create lines for Rims
        # We can add horizontal lines or specific points.
        # Let's use `tlines` or `alines` feature of mplfinance if possible, or just `hlines`.
        
        # Simple approach: A horizontal line at Right Rim Price level
        right_rim_price = patterns_details['right_rim'][1]
        entry_price = patterns_details.get('suggested_entry', right_rim_price)
        stop_loss = patterns_details.get('stop_loss', 0)
        target_price = patterns_details.get('target_price', 0)
        
        filename = f"{output_dir}/{ticker}_cup_handle.png"
        
        # Title with trade setup
        title = (f"{ticker} - Cup & Handle Setup\n"
                 f"Entry: {entry_price} | Stop: {stop_loss} | Target: {target_price}")
        
        # Plot
        # hlines: Entry (Blue), Stop (Red), Target (Green)
        # We handle cases where they might be 0 (though logic shouldn't allow it)
        lines = []
        colors = []
        
        if entry_price > 0:
            lines.append(entry_price)
            colors.append('blue')
        if stop_loss > 0:
            lines.append(stop_loss)
            colors.append('red')
        if target_price > 0:
            lines.append(target_price)
            colors.append('green')

        hlines = dict(hlines=lines, colors=colors, linestyle='-.', linewidths=(1.5, 1.5, 1.5))
        
        mpf.plot(plot_df, 
                 type='candle', 
                 style='yahoo', 
                 volume=True, 
                 title=title,
                 hlines=hlines,
                 savefig=filename)
                 
        return filename
    except Exception as e:
        print(f"Failed to plot {ticker}: {e}")
        return None
