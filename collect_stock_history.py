import os
import re
import ast
import glob
import argparse
import concurrent.futures
from datetime import datetime, timedelta
from typing import List, Optional
import requests
import pandas as pd
from tqdm import tqdm

import yfinance as yf
from pykrx import stock

# ==============================================================================
# Constants & Headers
# ==============================================================================
OUTPUT_DIR = "./output"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/"
}

session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=30, pool_maxsize=30)
session.mount("https://", adapter)
session.mount("http://", adapter)
session.headers.update(HEADERS)

# ==============================================================================
# Date Helpers
# ==============================================================================
def parse_date_input(date_str: Optional[str], default_str: str) -> str:
    if not date_str:
        return default_str
    digits = re.sub(r'\D', '', str(date_str))
    if len(digits) == 8:
        return digits
    return default_str

def to_iso_format(yyyymmdd: str) -> str:
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"

# ==============================================================================
# Fetchers (Naver, KRX, Yahoo)
# ==============================================================================
def fetch_from_naver(code: str, timeframe: str, start_date: str, end_date: str, price_type: str) -> Optional[pd.DataFrame]:
    # timeframe: 'day', 'week', 'month'
    url = f"https://m.stock.naver.com/front-api/external/chart/domestic/info?symbol={code}&requestType=1&startTime={start_date}&endTime={end_date}&timeframe={timeframe}"
    try:
        r = session.get(url, timeout=10)
        if r.status_code != 200:
            return None
        raw_text = r.text.strip()
        if not raw_text or raw_text == "[[]]" or "날짜" not in raw_text:
            return None
        
        data = ast.literal_eval(raw_text)
        if len(data) <= 1:
            return None
            
        columns = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=columns)
        
        df = df.rename(columns={
            '날짜': '날짜',
            '시가': '시가',
            '고가': '고가',
            '저가': '저가',
            '종가': '종가'
        })
        
        df['날짜'] = df['날짜'].apply(lambda x: f"{x[:4]}-{x[4:6]}-{x[6:]}")
        df['종목코드'] = code
        df['출처'] = 'Naver'
        
        for col in ['시가', '고가', '저가', '종가']:
            df[col] = pd.to_numeric(df[col], errors='coerce').round().fillna(0).astype(int)
            
        df = df[['날짜', '종목코드', '시가', '고가', '저가', '종가', '출처']]
        return df
    except Exception:
        return None

def fetch_from_krx(code: str, timeframe: str, start_date: str, end_date: str, price_type: str) -> Optional[pd.DataFrame]:
    start_dt = datetime.strptime(start_date, "%Y%m%d")
    end_dt = datetime.strptime(end_date, "%Y%m%d")
    
    curr_start = start_dt
    dfs = []
    adjusted_flag = (price_type == 'adjusted')
    
    while curr_start <= end_dt:
        curr_end = curr_start + timedelta(days=5 * 365)
        if curr_end > end_dt:
            curr_end = end_dt
            
        s_str = curr_start.strftime("%Y%m%d")
        e_str = curr_end.strftime("%Y%m%d")
        
        try:
            df_chunk = stock.get_market_ohlcv_by_date(s_str, e_str, code, adjusted=adjusted_flag)
            if df_chunk is not None and not df_chunk.empty:
                df_chunk = df_chunk[(df_chunk['시가'] > 0) & (df_chunk['종가'] > 0)]
                if not df_chunk.empty:
                    dfs.append(df_chunk)
        except Exception:
            pass
            
        curr_start = curr_end + timedelta(days=1)
        
    if not dfs:
        return None
        
    df = pd.concat(dfs)
    df = df[~df.index.duplicated(keep='first')]
    
    if df.empty:
        return None
        
    # Resampling for week or month
    if timeframe == 'week':
        df = df.resample('W').agg({
            '시가': 'first',
            '고가': 'max',
            '저가': 'min',
            '종가': 'last'
        })
        df = df.dropna(subset=['시가', '고가', '저가', '종가'])
    elif timeframe == 'month':
        df = df.resample('M').agg({
            '시가': 'first',
            '고가': 'max',
            '저가': 'min',
            '종가': 'last'
        })
        df = df.dropna(subset=['시가', '고가', '저가', '종가'])
        
    df = df.reset_index()
    df.columns = ['날짜', '시가', '고가', '저가', '종가']
    df['날짜'] = df['날짜'].dt.strftime('%Y-%m-%d')
    df['종목코드'] = code
    df['출처'] = 'KRX'
    
    for col in ['시가', '고가', '저가', '종가']:
        df[col] = pd.to_numeric(df[col], errors='coerce').round().fillna(0).astype(int)
        
    df = df[['날짜', '종목코드', '시가', '고가', '저가', '종가', '출처']]
    return df

def fetch_from_yahoo(code: str, timeframe: str, start_date: str, end_date: str, price_type: str) -> Optional[pd.DataFrame]:
    start_iso = to_iso_format(start_date)
    end_iso = to_iso_format(end_date)
    
    ticker_symbol = f"{code}.KS"
    # Mapping timeframe to Yahoo intervals
    if timeframe == "month":
        interval = "1mo"
    elif timeframe == "week":
        interval = "1wk"
    else:
        interval = "1d"
    
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(start=start_iso, end=end_iso, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            return None
            
        df = df.reset_index()
        
        if price_type == 'adjusted' and 'Adj Close' in df.columns:
            ratio = (df['Adj Close'] / df['Close']).fillna(1.0)
            df['Open'] = df['Open'] * ratio
            df['High'] = df['High'] * ratio
            df['Low'] = df['Low'] * ratio
            df['Close'] = df['Adj Close']
            
        df = df.rename(columns={
            'Date': '날짜',
            'Open': '시가',
            'High': '고가',
            'Low': '저가',
            'Close': '종가'
        })
        
        df['날짜'] = pd.to_datetime(df['날짜']).dt.strftime('%Y-%m-%d')
        df['종목코드'] = code
        df['출처'] = 'Yahoo'
        
        for col in ['시가', '고가', '저가', '종가']:
            df[col] = pd.to_numeric(df[col], errors='coerce').round().fillna(0).astype(int)
            
        df = df[['날짜', '종목코드', '시가', '고가', '저가', '종가', '출처']]
        return df
    except Exception:
        return None

# ==============================================================================
# Fallback Loop
# ==============================================================================
def sanitize_and_fix_prices(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return df
    
    # 1. Drop rows with invalid or zero close prices
    df = df.dropna(subset=['종가'])
    df = df[df['종가'] > 0].copy()
    if df.empty:
        return None
        
    # 2. If open, high, or low is zero/NaN, fill them with close price
    for col in ['시가', '고가', '저가']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df.loc[df[col] <= 0, col] = df.loc[df[col] <= 0, '종가']
        
    # 3. Ensure logical constraint: High >= Low
    bad_hl = df['고가'] < df['저가']
    if bad_hl.any():
        price_cols = ['시가', '고가', '저가', '종가']
        df.loc[bad_hl, '고가'] = df.loc[bad_hl, price_cols].max(axis=1)
        df.loc[bad_hl, '저가'] = df.loc[bad_hl, price_cols].min(axis=1)
        
    # 4. Cast all price columns to integer
    for col in ['시가', '고가', '저가', '종가']:
        df[col] = df[col].round().astype(int)
        
    return df

def get_single_ticker_price(code: str, price_type: str, timeframe: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    df = None
    
    # 1. Naver
    try:
        df = fetch_from_naver(code, timeframe, start_date, end_date, price_type)
    except Exception:
        df = None
        
    # 2. KRX
    if df is None or df.empty:
        try:
            df = fetch_from_krx(code, timeframe, start_date, end_date, price_type)
        except Exception:
            df = None
            
    # 3. Yahoo
    if df is None or df.empty:
        try:
            df = fetch_from_yahoo(code, timeframe, start_date, end_date, price_type)
        except Exception:
            df = None
            
    if df is not None and not df.empty:
        df = sanitize_and_fix_prices(df)
        
    if df is not None and not df.empty:
        start_iso = to_iso_format(start_date)
        end_iso = to_iso_format(end_date)
        df = df[(df['날짜'] >= start_iso) & (df['날짜'] <= end_iso)]
        df = df.sort_values(by='날짜').reset_index(drop=True)
        return df
        
    return None

def get_multiple_prices(code_list: List[str], price_type: str, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
    combined_dfs = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_code = {
            executor.submit(get_single_ticker_price, code, price_type, timeframe, start_date, end_date): code
            for code in code_list
        }
        
        pbar = tqdm(concurrent.futures.as_completed(future_to_code), total=len(future_to_code), desc=f"Scraping ({price_type}-{timeframe})")
        for future in pbar:
            code = future_to_code[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    combined_dfs.append(df)
            except Exception as e:
                print(f"\nError scraping [{code}]: {e}")
                
    if not combined_dfs:
        return pd.DataFrame(columns=['날짜', '종목코드', '시가', '고가', '저가', '종가', '출처'])
        
    final_df = pd.concat(combined_dfs, ignore_index=True)
    final_df = final_df.sort_values(by=['날짜', '종목코드']).reset_index(drop=True)
    return final_df

# ==============================================================================
# Helper to read target codes
# ==============================================================================
def load_top_stocks(top_n: int) -> List[str]:
    """Finds the latest Stock_YYYYMMDD.xlsx and returns top N ticker codes."""
    files = glob.glob(os.path.join(OUTPUT_DIR, "Stock_*.xlsx"))
    if not files:
        print("No stock spreadsheet found. Falling back to top 100 codes list.")
        # Fallback to a predefined list of major KOSPI stocks if no Excel
        return ["005930", "000660", "005935", "207940", "005380", "068270", "005490", "051910", "035420", "006400"]
        
    # Sort files to find the latest
    files.sort(reverse=True)
    latest_file = files[0]
    print(f"Loading stock codes from: {latest_file}")
    try:
        df = pd.read_excel(latest_file, dtype={"종목코드": str})
        # Assuming the file is already sorted by market cap
        top_codes = list(df["종목코드"].head(top_n))
        return top_codes
    except Exception as e:
        print(f"Failed to read stock Excel: {e}")
        return ["005930", "000660"]

# ==============================================================================
# Main Process
# ==============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="국내 주식 과거 시세 CSV 수집 스크립트")
    parser.add_argument("--code", type=str, default=None, help="특정 종목코드 (쉼표 구분 가능, 예: 005930,000660)")
    parser.add_argument("--top", type=str, default="100", help="시가총액 상위 N개 종목 수집 (all 또는 숫자, 기본값: 100)")
    parser.add_argument("--start", type=str, default=None, help="시작 날짜 (YYYYMMDD, 기본값: 1년 전)")
    parser.add_argument("--end", type=str, default=None, help="종료 날짜 (YYYYMMDD, 기본값: 오늘)")
    
    args = parser.parse_args()
    
    # 1. Start / End Dates
    today_dt = datetime.today()
    default_start = (today_dt - timedelta(days=365)).strftime("%Y%m%d")
    default_end = today_dt.strftime("%Y%m%d")
    
    start_date = parse_date_input(args.start, default_start)
    end_date = parse_date_input(args.end, default_end)
    
    # 2. Identify codes to collect
    if args.code:
        code_list_day = [c.strip() for c in args.code.split(",") if c.strip()]
        code_list_weekly_monthly = code_list_day
        print(f"Targeting specified stock codes for all timeframes: {code_list_day}")
    else:
        if args.top.lower() == "all":
            code_list_day = load_top_stocks(4500) # Load all stocks
        else:
            try:
                top_n = int(args.top)
            except ValueError:
                top_n = 100
            code_list_day = load_top_stocks(top_n)
        
        # Weekly/Monthly always targets all stocks (up to 4500)
        code_list_weekly_monthly = load_top_stocks(4500)
        print(f"Targeting top {len(code_list_day)} stocks for daily, and all {len(code_list_weekly_monthly)} stocks for weekly/monthly.")
        
    if not code_list_day:
        print("No stock codes identified. Exiting.")
        return
        
    timeframes = ["day", "week", "month"]
    timeframe_labels = {
        "day": "daily",
        "week": "weekly",
        "month": "monthly"
    }
    
    # Create output dir
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today_str = today_dt.strftime("%Y%m%d")
    
    # 3. Fetch daily, weekly, monthly for actual & adjusted
    # Loop over timeframes
    for tf in timeframes:
        label = timeframe_labels[tf]
        current_codes = code_list_day if tf == "day" else code_list_weekly_monthly
        
        # A. Actual Prices (실제가격)
        df_act = get_multiple_prices(current_codes, "actual", tf, start_date, end_date)
        act_filename = f"Stock_actual_{label}_{today_str}.csv"
        act_path = os.path.join(OUTPUT_DIR, act_filename)
        df_act.to_csv(act_path, index=False, encoding="utf-8-sig")
        print(f"Saved actual prices to: {act_path} (rows: {len(df_act)})")
        
        # B. Adjusted Prices (수정가격)
        df_adj = get_multiple_prices(current_codes, "adjusted", tf, start_date, end_date)
        adj_filename = f"Stock_adjusted_{label}_{today_str}.csv"
        adj_path = os.path.join(OUTPUT_DIR, adj_filename)
        df_adj.to_csv(adj_path, index=False, encoding="utf-8-sig")
        print(f"Saved adjusted prices to: {adj_path} (rows: {len(df_adj)})")
        
    print("\nStock historical price collection completed successfully!")

if __name__ == "__main__":
    main()
