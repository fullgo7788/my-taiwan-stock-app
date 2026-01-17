import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化與視覺風格 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

# 【請填入您的 FinMind Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 核心數據引擎 (高速且排除權證) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 全域修正名稱與代號清洗
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    """提速核心：排除權證 (排除代號長度>5或含英文) 並修正名稱"""
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        # 排除權證與雜訊標的
        df = df[df['stock_id'].str.match(r'^\d{4,5}$')]
        df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df
    return pd.DataFrame()

# 預載主資訊
master_info = get_clean_master_info()
if not master_info.empty:
    stock_options = master_info['display'].tolist()
    name_to_id = master_info.set_index('display')['stock_id'].to_dict()
else:
    stock_options, name_to_id = ["2330 台積電"], {"2330 台積電": "2330"}

# --- 3. VIP 高速鎖碼雷達邏輯 (資本額 30 億以內) ---
def fast_radar_scan(info_df):
    # A. 篩選資本額符合標的 (1億 - 30億)
    small_caps = info_df[(info_df['capital'] <= 3000000000) & (info_df['capital'] >= 100000000)]
    small_ids = small_caps['stock_id'].tolist()

    # B. 取得最新報價 (一次性)
    today = (datetime.now() - timedelta(days=0 if datetime.now().hour >= 16 else 1)).strftime('%Y-%m-%d')
    all_p = safe_get_data("TaiwanStockPrice", start_date=today)
    if all_p.empty: return pd.DataFrame()
    
    # C. 先過濾漲跌幅與成交量 (減少後續大戶 API 請求)
    all_p['chg'] = ((all_p['close'] / all_p['open']) - 1) * 100
    candidates = all_p[
        (all_p['stock_id'].isin(small_ids)) & 
        (all_p['chg'] >= -1.5) & (all_p['chg'] <= 2.5) &
        (all_p['trading_volume'] > 500000) # 成交量 > 500 張
    ].sort_values('trading_volume', ascending=False).head(20) # 僅精選前 20 檔進行籌碼分析
    
    potential_list = []
    h_start = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d')
    
    for _, row in candidates.iterrows():
        sid = row['stock_id']
        h_df = safe_get_data("TaiwanStockShareholding", sid, h_start)
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                if len(bh) >= 2 and bh['percent'].iloc[-1] > bh['percent'].iloc[-2]:
                    s_name = small_caps[small_caps['stock_id'] == sid]['stock_name'].values[0]
                    potential_list.append({