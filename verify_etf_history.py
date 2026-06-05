import os
import datetime
import pandas as pd

def verify_history():
    print("=== Starting ETF CSV History Verification ===")
    today_str = datetime.date.today().strftime("%Y%m%d")
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    
    timeframes = ["daily", "weekly", "monthly"]
    price_types = ["actual", "adjusted"]
    expected_cols = ['날짜', '종목코드', '시가', '고가', '저가', '종가', '출처']
    
    all_success = True
    
    for tf in timeframes:
        for pt in price_types:
            filename = f"ETF_{pt}_{tf}_{today_str}.csv"
            filepath = os.path.join(output_dir, filename)
            
            print(f"\nChecking file: {filename}")
            
            # 1. Check file existence
            if not os.path.exists(filepath):
                print(f"Error: File does not exist: {filepath}")
                all_success = False
                continue
            print(" - Existence: OK")
            
            # 2. Load and check structure
            try:
                # Read csv forcing 종목코드 to be string to preserve leading zeros
                df = pd.read_csv(filepath, dtype={"종목코드": str})
                print(f" - Total rows: {len(df)}")
            except Exception as e:
                print(f" - Error reading CSV: {e}")
                all_success = False
                continue
                
            # Column structure
            if list(df.columns) != expected_cols:
                print(f" - Error: Column mismatch. Found {list(df.columns)}, expected {expected_cols}")
                all_success = False
                continue
            print(" - Columns: OK")
            
            # Empty check
            if df.empty:
                print(" - Error: Dataframe is empty.")
                all_success = False
                continue
            print(" - Data presence: OK")
            
            # Minimum row count sanity check — daily data should have at least 100 rows
            MIN_EXPECTED_ROWS = 100
            if len(df) < MIN_EXPECTED_ROWS:
                print(f" - Error: Expected at least {MIN_EXPECTED_ROWS} rows, but got {len(df)}.")
                all_success = False
                continue
            print(f" - Minimum row count check: OK ({len(df)} >= {MIN_EXPECTED_ROWS})")
            
            # 3. Numeric constraints validation
            # Check for NaN
            if df.isnull().any().any():
                print(" - Error: Found null/NaN values in the CSV.")
                all_success = False
                continue
            print(" - Null check: OK")
            
            # Duplicate row check — no duplicate (날짜, 종목코드) pairs should exist
            dup_count = df.duplicated(subset=['날짜', '종목코드']).sum()
            if dup_count > 0:
                print(f" - Error: Found {dup_count} duplicate (날짜, 종목코드) pairs.")
                all_success = False
                continue
            print(" - Duplicate check: OK (no duplicate date-ticker pairs)")
            
            # Date format validation — check that 날짜 matches YYYY-MM-DD pattern
            import re
            bad_dates = df[~df['날짜'].astype(str).str.match(r'^\d{4}-\d{2}-\d{2}$')]
            if not bad_dates.empty:
                print(f" - Error: Found {len(bad_dates)} rows with invalid date format (expected YYYY-MM-DD).")
                print(bad_dates.head(3))
                all_success = False
                continue
            print(" - Date format check: OK (YYYY-MM-DD)")
            
            # Date & Ticker sorting check (Strict order check)
            expected_sorted_df = df.sort_values(by=['날짜', '종목코드']).reset_index(drop=True)
            if df.equals(expected_sorted_df):
                print(" - Date & Ticker sorting: OK (strictly ordered by 날짜 & 종목코드)")
            else:
                print(" - Error: Date & Ticker sorting check failed. The file is NOT strictly sorted.")
                all_success = False
                
            # Numeric ranges and logical checks
            bad_price = df[(df['시가'] <= 0) | (df['고가'] <= 0) | (df['저가'] <= 0) | (df['종가'] <= 0)]
            if not bad_price.empty:
                print(f" - Error: Found {len(bad_price)} rows with non-positive prices.")
                print(bad_price.head(3))
                all_success = False
                continue
            print(" - Price ranges: OK (all > 0)")
            
            bad_high_low = df[df['고가'] < df['저가']]
            if not bad_high_low.empty:
                print(f" - Error: Found {len(bad_high_low)} rows where High < Low.")
                print(bad_high_low.head(3))
                all_success = False
                continue
            print(" - Price logical constraints: OK (High >= Low)")
            
            # Ticker format check (6 digits alphanumeric string)
            bad_tickers = df[~df['종목코드'].str.match(r'^[A-Z0-9]{6}$')]
            if not bad_tickers.empty:
                print(f" - Error: Found {len(bad_tickers)} rows with invalid stock codes.")
                print(bad_tickers.head(3))
                all_success = False
                continue
            print(" - Ticker codes format: OK (6-digit numeric)")
            
            # Fallback source labels
            sources = df['출처'].unique()
            invalid_sources = [s for s in sources if s not in ['Naver', 'KRX', 'Yahoo']]
            if invalid_sources:
                print(f" - Error: Found invalid source labels: {invalid_sources}")
                all_success = False
                continue
            print(f" - Sources: OK {list(sources)}")
            
    if all_success:
        print("\n=== All ETF CSV History Verifications Passed! ===")
        return True
    else:
        print("\n=== ETF CSV History Verification Failed! ===")
        return False

if __name__ == "__main__":
    import sys
    success = verify_history()
    if not success:
        sys.exit(1)
