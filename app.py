import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import numpy as np

# --- 1. 核心初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

# 【填入您的 Token】
FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 安全數據引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.1) 
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'stock_id' in df.columns:
                df['stock_id'] = df['stock_id'].astype(str)
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except:
        pass
    return pd.DataFrame()

def calculate_rsi(df, period=14):
    if len(df) < period: return pd.Series([np.nan] * len(df))
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        # 排除權證與期貨標的
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df
    return pd.DataFrame()

master_info = get_clean_master_info()
stock_options = master_info['display'].tolist() if not master_info.empty else ["2330 台積電"]
name_to_id = master_info.set_index('display')['stock_id'].to_dict() if not master_info.empty else {"2330 台積電": "2330"}

# --- 3. UI 介面 ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    target_display = st.selectbox("🎯 標的診斷", stock_options)
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)
    if is_vip: st.success("✅ VIP 權限已開啟")

tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

# --- Tab 1 & 2 保持穩定 (略，請參考前版邏輯) ---
# ... (建議保留前一版 Tab 1 與 Tab 2 的完整代碼)

# --- Tab 3: VIP 鎖碼雷達 (修復 KeyError) ---
with tabs[2]:
    if not is_vip:
        st.warning("🔒 請在側邊欄輸入 VIP 授權碼以解鎖功能。")
    else:
        st.subheader("🚀 鎖碼雷達 (中小型股 + 大戶增持)")
        st.write("條件：全市場 4 碼個股、今日成交 > 800 張、大戶持股週增長。")
        
        if st.button("執行 VIP 深度掃描", key="vip_scan_btn"):
            with st.spinner("分析中..."):
                # 取得最新交易日
                today_p = pd.DataFrame()
                for i in range(5):
                    d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    today_p = safe_get_data("TaiwanStockPrice", start_date=d)
                    if not today_p.empty: break
                
                if not today_p.empty:
                    # 篩選成交量大且股價在 200 元以內的中小型潛力標的
                    cands = today_p[(today_p['stock_id'].isin(master_info['stock_id'])) & 
                                    (today_p['trading_volume'] >= 800000) & 
                                    (today_p['close'] <= 200)].head(15)
                    
                    final_res = []
                    for _, row in cands.iterrows():
                        sid = row['stock_id']
                        # 檢查大戶持股
                        h_check = safe_get_data("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=21)).strftime('%Y-%m-%d'))
                        if not h_check.empty:
                            c_col = next((c for c in h_check.columns if 'class' in c), None)
                            if c_col:
                                bh = h_check[h_check[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                                if len(bh) >= 2 and bh['percent'].iloc[-1] > bh['percent'].iloc[-2]:
                                    s_name = master_info[master_info['stock_id'] == sid]['stock_name'].values[0]
                                    final_res.append({
                                        "代號": sid, "名稱": s_name, "收盤": row['close'],
                                        "大戶前次": f"{bh['percent'].iloc[-2]}%",
                                        "大戶最新": f"{bh['percent'].iloc[-1]}%",
                                        "週增幅": round(bh['percent'].iloc[-1] - bh['percent'].iloc[-2], 2)
                                    })
                    if final_res:
                        st.table(pd.DataFrame(final_res).sort_values("週增幅", ascending=False))
                    else:
                        st.info("今日無符合鎖碼條件之標的。")
                else:
                    st.error("無法取得最新股價。")