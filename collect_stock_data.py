import os
import re
import json
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ==============================================================================
# Constants & Headers
# ==============================================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/"
}

# ==============================================================================
# Helper Functions
# ==============================================================================
def clean_int(val_str: str) -> int:
    """Cleans numeric string and converts it to integer."""
    if not val_str:
        return 0
    clean = val_str.replace(",", "").replace(" ", "").strip()
    if clean == "N/A" or not clean:
        return 0
    try:
        return int(clean)
    except ValueError:
        return 0

def clean_float_ratio(val_str: str) -> float:
    """Cleans percentage ratio string and converts it to a decimal float."""
    if not val_str:
        return 0.0
    clean = val_str.replace(",", "").replace("%", "").replace(" ", "").strip()
    if clean == "N/A" or not clean:
        return 0.0
    try:
        return float(clean) / 100.0
    except ValueError:
        return 0.0

# ==============================================================================
# Scraping Logic
# ==============================================================================
def fetch_market_cap_page(sosok: int, page: int) -> list:
    """Scrapes a single market capitalization page from Naver Finance."""
    url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
    results = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        html = r.content.decode("cp949", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="type_2")
        if not table:
            return []
            
        rows = table.find_all("tr")
        for row in rows:
            a_tag = row.find("a", class_="tltle")
            if not a_tag:
                continue
                
            href = a_tag.get("href", "")
            code_match = re.search(r"code=(\d{6})", href)
            if not code_match:
                continue
                
            code = code_match.group(1)
            name = a_tag.text.strip()
            
            tds = row.find_all("td")
            if len(tds) < 10:
                continue
                
            # Naver Market Cap Table Columns:
            # 0: N, 1: 종목명, 2: 현재가, 3: 전일비, 4: 등락률, 5: 액면가, 6: 시가총액, 7: 상장주식수, 8: 외국인비율
            price = clean_int(tds[2].text)
            market_cap = clean_int(tds[6].text)
            foreign_ratio = clean_float_ratio(tds[8].text)
            
            market_type = "코스피" if sosok == 0 else "코스닥"
            
            results.append({
                "종목코드": code,
                "종목명": name,
                "시장": market_type,
                "현재가": price,
                "시가총액(억)": market_cap,
                "외국인비율": foreign_ratio
            })
    except Exception as e:
        print(f"Error fetching market cap sosok={sosok}, page={page}: {e}")
        
    return results

def fetch_all_stocks() -> pd.DataFrame:
    """Fetches all KOSPI and KOSDAQ stocks using parallel execution."""
    print("Collecting all KOSPI and KOSDAQ stocks...")
    all_data = []
    
    # sosok=0 (KOSPI), sosok=1 (KOSDAQ)
    # We poll up to page 30 for KOSPI and 50 for KOSDAQ. Empty responses will break or be filtered out.
    tasks = []
    with ThreadPoolExecutor(max_workers=15) as executor:
        # KOSPI: Page 1 to 30
        for page in range(1, 31):
            tasks.append(executor.submit(fetch_market_cap_page, 0, page))
        # KOSDAQ: Page 1 to 50
        for page in range(1, 51):
            tasks.append(executor.submit(fetch_market_cap_page, 1, page))
            
        for future in as_completed(tasks):
            res = future.result()
            if res:
                all_data.extend(res)
                
    df = pd.DataFrame(all_data)
    # Drop duplicates just in case
    df = df.drop_duplicates(subset=["종목코드"])
    print(f"Total stocks fetched: {len(df)}")
    return df

def fetch_kospi200_codes() -> set:
    """Scrapes KOSPI 200 constituents codes from Naver Finance index pages (1 to 20)."""
    print("Collecting KOSPI 200 constituent codes...")
    kospi200_codes = set()
    
    def fetch_k200_page(page):
        url = f"https://finance.naver.com/sise/entryJongmok.naver?no=028&page={page}"
        codes = []
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            r.raise_for_status()
            html = r.content.decode("cp949", errors="ignore")
            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all("a", href=re.compile(r"/item/main\.naver\?code=\d{6}"))
            for link in links:
                code_match = re.search(r"code=(\d{6})", link.get("href", ""))
                if code_match:
                    codes.append(code_match.group(1))
        except Exception as e:
            print(f"Error fetching KOSPI 200 page {page}: {e}")
        return codes

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_k200_page, p) for p in range(1, 21)]
        for future in as_completed(futures):
            kospi200_codes.update(future.result())
            
    print(f"KOSPI 200 codes collected: {len(kospi200_codes)}")
    return kospi200_codes

def fetch_kosdaq150_names() -> set:
    """Scrapes KOSDAQ 150 constituent names from KODEX KOSDAQ 150 ETF PDF info on WiseFN."""
    print("Collecting KOSDAQ 150 constituent names...")
    kosdaq150_names = set()
    url = "http://companyinfo.stock.naver.com/v1/company/c1010001.aspx?cmp_cd=229200"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        html = r.text
        
        # Extract var CU_data = { ... };
        pattern = re.compile(r"var\s+CU_data\s*=\s*(\{.*?\});", re.DOTALL)
        match = pattern.search(html)
        if match:
            json_str = match.group(1)
            data = json.loads(json_str)
            grid_data = data.get("grid_data", [])
            for item in grid_data:
                stk_name = item.get("STK_NM_KOR")
                if stk_name and stk_name != "원화현금":
                    kosdaq150_names.add(stk_name.strip())
        else:
            print("Failed to find CU_data in WiseFN page.")
    except Exception as e:
        print(f"Error collecting KOSDAQ 150 names: {e}")
        
    print(f"KOSDAQ 150 names collected: {len(kosdaq150_names)}")
    return kosdaq150_names

# ==============================================================================
# Excel Generation & Styling
# ==============================================================================
def save_to_excel_with_style(df: pd.DataFrame, filepath: str):
    """Saves DataFrame as an Excel file with detailed corporate styling."""
    print(f"Saving styled Excel report to: {filepath}...")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # Create workbook and sheet
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "국내주식 종목현황"
    
    # Write Headers
    headers = list(df.columns)
    ws.append(headers)
    
    # Write Data
    for row in df.itertuples(index=False):
        ws.append(list(row))
        
    # Styles
    font_family = "Malgun Gothic"
    header_font = Font(name=font_family, size=10, bold=True, color="000000")
    data_font = Font(name=font_family, size=10, bold=False, color="000000")
    
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    
    thin_border_side = Side(border_style="thin", color="D3D3D3")
    border_all = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")
    
    # Format Headers (Row 1)
    ws.row_dimensions[1].height = 25
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = align_center
        cell.border = border_all
        
    # Format Data Rows
    # Columns: 1: 종목코드, 2: 종목명, 3: 유형, 4: 현재가, 5: 시가총액(억), 6: 외국인비율
    for r_idx in range(2, ws.max_row + 1):
        ws.row_dimensions[r_idx].height = 20
        
        # Col 1: 종목코드 (Center)
        c1 = ws.cell(row=r_idx, column=1)
        c1.font = data_font
        c1.alignment = align_center
        c1.border = border_all
        c1.number_format = "@" # Text format for stock codes
        
        # Col 2: 종목명 (Left)
        c2 = ws.cell(row=r_idx, column=2)
        c2.font = data_font
        c2.alignment = align_left
        c2.border = border_all
        
        # Col 3: 유형 (Center)
        c3 = ws.cell(row=r_idx, column=3)
        c3.font = data_font
        c3.alignment = align_center
        c3.border = border_all
        
        # Col 4: 현재가 (Right, Currency)
        c4 = ws.cell(row=r_idx, column=4)
        c4.font = data_font
        c4.alignment = align_right
        c4.border = border_all
        c4.number_format = "#,##0"
        
        # Col 5: 시가총액(억) (Right, Currency)
        c5 = ws.cell(row=r_idx, column=5)
        c5.font = data_font
        c5.alignment = align_right
        c5.border = border_all
        c5.number_format = "#,##0"
        
        # Col 6: 외국인비율 (Right, Percentage)
        c6 = ws.cell(row=r_idx, column=6)
        c6.font = data_font
        c6.alignment = align_right
        c6.border = border_all
        c6.number_format = "0.00%"
        
    # Enable grid lines
    ws.views.sheetView[0].showGridLines = True
    
    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or '')
            # Handle special display lengths for formatting (e.g. percentages, commas)
            if cell.row > 1:
                if cell.column == 4 or cell.column == 5:
                    try:
                        val_str = f"{int(cell.value):,}"
                    except (ValueError, TypeError):
                        pass
                elif cell.column == 6:
                    try:
                        val_str = f"{float(cell.value) * 100:.2f}%"
                    except (ValueError, TypeError):
                        pass
            
            # Check length, account for double-width characters (Korean)
            cell_len = 0
            for char in val_str:
                if ord(char) > 127:
                    cell_len += 2  # Korean character
                else:
                    cell_len += 1
            if cell_len > max_len:
                max_len = cell_len
                
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    wb.save(filepath)
    print("Excel file saved successfully!")

# ==============================================================================
# Main Execution
# ==============================================================================
def main():
    start_time = datetime.datetime.now()
    
    # 1. Fetch all stocks basic info
    df_stocks = fetch_all_stocks()
    if df_stocks.empty:
        print("Failed to fetch any stock data.")
        return
        
    # 2. Fetch Index constituents
    k200_codes = fetch_kospi200_codes()
    k150_names = fetch_kosdaq150_names()
    
    # 3. Classify 유형
    print("Classifying stocks based on index constituents...")
    types = []
    for row in df_stocks.itertuples():
        mkt = row.시장
        code = row.종목코드
        name = row.종목명
        
        if mkt == "코스피":
            if code in k200_codes:
                types.append("코스피200")
            else:
                types.append("코스피")
        elif mkt == "코스닥":
            if name in k150_names:
                types.append("코스닥150")
            else:
                types.append("코스닥")
        else:
            types.append(mkt)
            
    df_stocks["유형"] = types
    
    # 4. Final columns arrangement
    df_final = df_stocks[["종목코드", "종목명", "유형", "현재가", "시가총액(억)", "외국인비율"]].copy()
    
    # Sort by market capitalization descending
    df_final = df_final.sort_values(by="시가총액(억)", ascending=False)
    
    # 5. Save to Excel
    today_str = datetime.date.today().strftime("%Y%m%d")
    output_path = os.path.join("/Users/tina/Documents/ETF_AI/output", f"Stock_{today_str}.xlsx")
    save_to_excel_with_style(df_final, output_path)
    
    end_time = datetime.datetime.now()
    print(f"Elapsed Time: {end_time - start_time}")

if __name__ == "__main__":
    main()
