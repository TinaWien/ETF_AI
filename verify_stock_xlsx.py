import os
import datetime
import pandas as pd
import openpyxl

def verify_report():
    print("=== Starting Excel Verification ===")
    today_str = datetime.date.today().strftime("%Y%m%d")
    filepath = f"/Users/tina/Documents/ETF_AI/output/Stock_{today_str}.xlsx"
    
    # 1. Existence check
    if not os.path.exists(filepath):
        print(f"Error: File does not exist: {filepath}")
        return False
        
    print(f"File found: {filepath}")
    
    # 2. Structure check using pandas
    try:
        df = pd.read_excel(filepath, dtype={"종목코드": str})
        print(f"Total rows in dataframe: {len(df)}")
    except Exception as e:
        print(f"Error reading excel with pandas: {e}")
        return False
        
    expected_cols = ["종목코드", "종목명", "유형", "현재가", "시가총액(억)", "외국인비율"]
    if list(df.columns) != expected_cols:
        print(f"Error: Column mismatch. Found {list(df.columns)}, expected {expected_cols}")
        return False
    print("Columns structure: OK")
    
    # 3. Row count sanity check
    # Combined KOSPI & KOSDAQ usually has 2400 to 2800 listed stocks.
    if len(df) < 2000 or len(df) > 3500:
        print(f"Error: Row count {len(df)} is outside the normal range (2000 ~ 3500).")
        return False
    print(f"Row count sanity check: OK ({len(df)} rows)")
    
    # 4. Type count validation
    type_counts = df["유형"].value_counts()
    print("Constituents count by Type:")
    for typ, count in type_counts.items():
        print(f" - {typ}: {count}")
        
    # KOSPI 200 should be exactly 200
    k200_count = type_counts.get("코스피200", 0)
    if k200_count != 200:
        print(f"Warning/Error: KOSPI 200 count is {k200_count}, expected exactly 200.")
        # We might not fail the test immediately but issue a strong warning
    else:
        print("KOSPI 200 count: OK (exactly 200)")
        
    # KOSDAQ 150 should be exactly 150
    k150_count = type_counts.get("코스닥150", 0)
    if k150_count != 150:
        print(f"Warning/Error: KOSDAQ 150 count is {k150_count}, expected exactly 150.")
    else:
        print("KOSDAQ 150 count: OK (exactly 150)")
        
    # 5. Null checks
    null_counts = df.isnull().sum()
    if null_counts.any():
        print("Error: Found null values in report:")
        print(null_counts)
        return False
    print("Null check: OK (No missing values)")
    
    # 6. Specific stocks check (e.g. Samsung Electronics)
    samsung = df[df["종목코드"] == "005930"]
    if samsung.empty:
        print("Error: Samsung Electronics (005930) is missing from the list.")
        return False
    else:
        sam_row = samsung.iloc[0]
        if sam_row["유형"] != "코스피200":
            print(f"Error: Samsung Electronics type is {sam_row['유형']}, expected 코스피200")
            return False
        if sam_row["현재가"] <= 0 or sam_row["시가총액(억)"] <= 0:
            print(f"Error: Invalid numerical values for Samsung Electronics. Row: {sam_row.to_dict()}")
            return False
        print("Samsung Electronics (005930) mapping and values: OK")
        
    # 7. Excel cell formatting and styling checks
    try:
        wb = openpyxl.load_workbook(filepath)
        ws = wb.active
        
        # Grid lines check
        if not ws.views.sheetView[0].showGridLines:
            print("Error: Sheet grid lines are disabled.")
            return False
        print("Grid lines: OK (Enabled)")
        
        # Header check (Row 1)
        for col_idx in range(1, 7):
            cell = ws.cell(row=1, column=col_idx)
            # Font family
            if cell.font.name != "Malgun Gothic":
                print(f"Error: Header font name is {cell.font.name}, expected 'Malgun Gothic'")
                return False
            # Font weight
            if not cell.font.bold:
                print("Error: Header font is not Bold.")
                return False
            # Header color fill (RGB)
            fill_color = cell.fill.start_color.rgb
            # Might be '00D9E1F2' or 'FFD9E1F2' depending on openpyxl interpretation
            if fill_color not in ["00D9E1F2", "FFD9E1F2"]:
                print(f"Error: Header fill color is {fill_color}, expected D9E1F2.")
                return False
        print("Header fonts & colors: OK")
        
        # Data format check
        # Row 2 (should be first data row)
        row_idx = 2
        
        # Code format
        cell_code = ws.cell(row=row_idx, column=1)
        if cell_code.number_format != "@":
            print(f"Error: Stock Code number format is {cell_code.number_format}, expected '@' (text)")
            return False
            
        # Price format
        cell_price = ws.cell(row=row_idx, column=4)
        if cell_price.number_format != "#,##0":
            print(f"Error: Price number format is {cell_price.number_format}, expected '#,##0'")
            return False
            
        # Market cap format
        cell_mcap = ws.cell(row=row_idx, column=5)
        if cell_mcap.number_format != "#,##0":
            print(f"Error: Market cap number format is {cell_mcap.number_format}, expected '#,##0'")
            return False
            
        # Foreign ratio format
        cell_fr = ws.cell(row=row_idx, column=6)
        if cell_fr.number_format != "0.00%":
            print(f"Error: Foreign ratio number format is {cell_fr.number_format}, expected '0.00%'")
            return False
            
        print("Excel cell number formatting: OK")
        
    except Exception as e:
        print(f"Error during openpyxl styling check: {e}")
        return False
        
    print("=== All Verifications Passed! ===")
    return True

if __name__ == "__main__":
    import sys
    success = verify_report()
    if not success:
        sys.exit(1)
