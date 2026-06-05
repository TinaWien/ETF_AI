import os
import logging
import re
import ast
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
LIST_API_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"
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
        

        
        df['날짜'] = df['날짜'].apply(lambda x: f"{x[:4]}-{x[4:6]}-{x[6:]}")
        df['종목코드'] = code
        df['출처'] = 'Naver'
        
        for col in ['시가', '고가', '저가', '종가']:
            df[col] = pd.to_numeric(df[col], errors='coerce').round().fillna(0).astype(int)
            
        df = df[['날짜', '종목코드', '시가', '고가', '저가', '종가', '출처']]
        return df
    except Exception as e:
        logging.warning(f'[{code}] Naver fetch failed: {e}')
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
        except Exception as e:
            logging.warning(f'[{code}] KRX chunk fetch failed: {e}')
            
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
        df = df.resample('ME').agg({
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
    
    if timeframe == "month":
        interval = "1mo"
    elif timeframe == "week":
        interval = "1wk"
    else:
        interval = "1d"
    
    # Try KOSPI (.KS) first, then KOSDAQ (.KQ)
    for suffix in ('.KS', '.KQ'):
        ticker_symbol = f"{code}{suffix}"
        try:
            ticker = yf.Ticker(ticker_symbol)
            df = ticker.history(start=start_iso, end=end_iso, interval=interval, auto_adjust=False)
            if df is None or df.empty:
                continue
                
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
        except Exception as e:
            logging.warning(f'[{code}] Yahoo fetch failed ({ticker_symbol}): {e}')
            continue
    return None

# ==============================================================================
# Fallback Loop & Sanitization
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
    except Exception as e:
        logging.warning(f'[{code}] Naver fallback failed: {e}')
        df = None
        
    # 2. KRX
    if df is None or df.empty:
        try:
            df = fetch_from_krx(code, timeframe, start_date, end_date, price_type)
        except Exception as e:
            logging.warning(f'[{code}] KRX fallback failed: {e}')
            df = None
            
    # 3. Yahoo
    if df is None or df.empty:
        try:
            df = fetch_from_yahoo(code, timeframe, start_date, end_date, price_type)
        except Exception as e:
            logging.warning(f'[{code}] Yahoo fallback failed: {e}')
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
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_code = {
            executor.submit(get_single_ticker_price, code, price_type, timeframe, start_date, end_date): code
            for code in code_list
        }
        
        pbar = tqdm(concurrent.futures.as_completed(future_to_code), total=len(future_to_code), desc=f"Scraping ETF ({price_type}-{timeframe})")
        for future in pbar:
            code = future_to_code[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    combined_dfs.append(df)
            except Exception as e:
                print(f"\nError scraping ETF [{code}]: {e}")
                
    if not combined_dfs:
        return pd.DataFrame(columns=['날짜', '종목코드', '시가', '고가', '저가', '종가', '출처'])
        
    final_df = pd.concat(combined_dfs, ignore_index=True)
    final_df = final_df.sort_values(by=['날짜', '종목코드']).reset_index(drop=True)
    return final_df

# ==============================================================================
# Main Process
# ==============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="국내 ETF 과거 시세 CSV 수집 스크립트")
    parser.add_argument("--code", type=str, default=None, help="특정 ETF 종목코드 (쉼표 구분 가능, 예: 069500,360750)")
    parser.add_argument("--start", type=str, default=None, help="시작 날짜 (YYYYMMDD, 기본값: 1년 전)")
    parser.add_argument("--end", type=str, default=None, help="종료 날짜 (YYYYMMDD, 기본값: 오늘)")
    
    args = parser.parse_args()
    
    # 1. Start / End Dates
    today_dt = datetime.today()
    default_start = (today_dt - timedelta(days=365)).strftime("%Y%m%d")
    default_end = today_dt.strftime("%Y%m%d")
    
    start_date = parse_date_input(args.start, default_start)
    end_date = parse_date_input(args.end, default_end)
    
    # 2. Get ETF List
    if args.code:
        code_list = [c.strip() for c in args.code.split(",") if c.strip()]
        print(f"Targeting specified ETF codes: {code_list}")
    else:
        print("Fetching full ETF list from Naver...")
        try:
            res = requests.get(LIST_API_URL, headers=HEADERS, timeout=10)
            res.raise_for_status()
            data = res.json()
            etf_items = data['result']['etfItemList']
            code_list = [item['itemcode'] for item in etf_items]
            print(f"Identified {len(code_list)} ETF tickers.")
        except Exception as e:
            print(f"Failed to fetch ETF list: {e}")
            return
            
    if not code_list:
        print("No ETF codes identified. Exiting.")
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
    for tf in timeframes:
        label = timeframe_labels[tf]
        
        # A. Actual Prices (실제가격)
        df_act = get_multiple_prices(code_list, "actual", tf, start_date, end_date)
        act_filename = f"ETF_actual_{label}_{today_str}.csv"
        act_path = os.path.join(OUTPUT_DIR, act_filename)
        df_act.to_csv(act_path, index=False, encoding="utf-8-sig")
        print(f"Saved actual ETF prices to: {act_path} (rows: {len(df_act)})")
        
        # B. Adjusted Prices (수정가격)
        df_adj = get_multiple_prices(code_list, "adjusted", tf, start_date, end_date)
        adj_filename = f"ETF_adjusted_{label}_{today_str}.csv"
        adj_path = os.path.join(OUTPUT_DIR, adj_filename)
        df_adj.to_csv(adj_path, index=False, encoding="utf-8-sig")
        print(f"Saved adjusted ETF prices to: {adj_path} (rows: {len(df_adj)})")
        
    print("\nETF historical price CSV collection completed successfully!")

if __name__ == "__main__":
    main()
