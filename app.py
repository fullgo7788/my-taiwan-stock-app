import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統環境初始化 ---
st.set_page_config(page_title="AlphaRadar 策略端", layout="wide")

# 初始化 Session State，確保選單聯動
if 'current_sid' not in st.session_state: 
    st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據防錯引擎 (數值化修復) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.4)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns] 
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                df = df.dropna(subset=['date'])
            # 強制將關鍵欄位轉換為數值，防止 TypeError
            numeric_cols = ['close', 'open', 'high', 'low', 'volume', 'percent', 'ratio', 'capital']
            for col in df.columns:
                if any(k in col for k in numeric_cols):
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except:
        pass
    return pd.DataFrame()

# --- 3. 核心索引：排除資本額 50 億以上 ---
@st.cache_data(ttl=86400)
def get_screened_universe():
    # 獲取台股個股資訊
    info_df = safe_fetch("TaiwanStockInfo")
    if info_df.empty:
        # 保底數據，避免選單全空
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    
    # 1. 過濾標準個股 (4位代碼)
    df = info_df[info_df['stock_id'].str.match(r'^\d{4}$', na=False)].copy()
    
    # 2. 資本額過濾 (排除 50 億以上)
    # FinMind 的 capital 單位通常為元
    if 'capital' in df.columns:
        df['capital'] = pd.to_numeric(df['capital'], errors='coerce')
        # 篩選條件：資本額 < 5,000,000,000
        df = df[df['capital'] < 5000000000]
    
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

# 執行篩選後的名單載入
master_df = get_screened_universe()

# --- 4. 側邊欄 (連動篩選後的名單) ---
with st.sidebar:
    st.header("⚡ 中小標的控制台")
    st.caption("※ 選單已自動過濾資本額 50 億以上之個股")
    
    options = master_df['display'].tolist()
    display_to_id = master_df.set_index('display')['stock_id'].to_dict()
    
    # 確保當前選擇的 SID 還在篩選後的名單中
    if st.session_state.current_sid not in display_to_id.values():
        st.session_state.current_sid = master_df.iloc[0]['stock_id']

    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
        curr_idx = options.index(current_display)
    except:
        curr_idx = 0

    selected_tag = st.selectbox("🔍 選擇中小個股", options=options, index=curr_idx)
    
    target_sid = display_to_id[selected_tag]
    if target_sid != st.session_state.current_sid:
        st.session_state.current_sid = target_sid
        st.rerun()

# --- 5. 主分頁區 ---
tabs = st.tabs(["📊 技術診斷", "🎯 大戶發動比對名單"])

# TAB 1: 技術分析 (4條均線)
with tabs[0]:
    sid = st.session_state.current_sid
    st.subheader(f"📈 {selected_tag} 技術分析")
    
    df_p = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=260)).strftime('%Y-%m-%d'))
    if not df_p.empty:
        df = df_p.sort_values('date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
        # K線
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        # 均線
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], name="5MA", line=dict(color='white', width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], name="20MA (月)", line=dict(color='magenta', width=1.2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma60'], name="60MA (季)", line=dict(color='cyan', width=1.5)), row=1, col=1)
        # 量
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray', opacity=0.5), row=2, col=1)
        
        fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)


# TAB 2: 大戶發動名單 (僅表列，無圖表)
with tabs[1]:
    st.subheader("🎯 籌碼與股價發動比對名單")
    st.write("目前分析範圍：資本額 < 50億個股")
    
    if st.button("🚀 開始掃描正相關標的"):
        with st.spinner("正在對比全市場籌碼趨勢..."):
            hit_list = []
            # 為了避免 API Overload，掃描篩選後清單的前 40 檔 (可自行調整)
            sample_pool = master_df['stock_id'].tolist()[:40]
            
            for s in sample_pool:
                # 抓取籌碼與價格
                c_df = safe_fetch("TaiwanStockShareholding", s, (datetime.now()-timedelta(days=25)).strftime('%Y-%m-%d'))
                p_df = safe_fetch("TaiwanStockPrice", s, (datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d'))
                
                if not c_df.empty and not p_df.empty:
                    # 1. 解析大戶欄位
                    lvl_col = next((c for c in c_df.columns if 'level' in c or 'stage' in c), None)
                    pct_col = next((c for c in c_df.columns if 'percent' in c or 'ratio' in c), None)
                    
                    if lvl_col and pct_col:
                        # 篩選 1000 張以上等級
                        big = c_df[c_df[lvl_col].astype(str).str.contains('1000|15')].sort_values('date')
                        if len(big) >= 2:
                            # 計算籌碼增減
                            diff = float(big.iloc[-1][pct_col]) - float(big.iloc[-2][pct_col])
                            
                            # 2. 計算價格是否站上均線 (發動點)
                            p_df['ma20'] = p_df['close'].rolling(20).mean()
                            latest = p_df.iloc[-1]
                            
                            # 條件：大戶增持 且 股價站上 MA20
                            if diff > 0 and latest['close'] > latest['ma20']:
                                s_name = master_df[master_df['stock_id']==s]['stock_name'].values[0]
                                hit_list.append({
                                    "代號": s, "名稱": s_name, 
                                    "大戶持股增減(%)": f"{diff:+.2f}%",
                                    "收盤價": latest['close'],
                                    "MA20位置": round(latest['ma20'], 2),
                                    "趨勢": "🔥 籌碼進攻"
                                })
            
            if hit_list:
                st.table(pd.DataFrame(hit_list))
            else:
                st.info("當前樣本中無符合條件標的（大戶增持且站上均線）。")