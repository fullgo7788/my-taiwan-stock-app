import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化與狀態管理 ---
st.set_page_config(page_title="AlphaRadar 終極測試版", layout="wide")

# 確保狀態持久化，防止選單跳掉
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2317" # 預設鴻海 (符合 < 50億條件)

FINMIND_TOKEN = "fullgo" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 強化數據抓取引擎 (模擬偵錯過濾) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        # 模擬 API 延遲，防止請求過快被封鎖
        time.sleep(0.3)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 轉換所有數值，若遇非數字轉為 NaN
            numeric_cols = ['close', 'open', 'high', 'low', 'volume', 'percent', 'capital']
            for col in df.columns:
                if any(k in col for k in numeric_cols):
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 清理無效日期與價格，這是防止 ValueError 的關鍵
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                df = df.dropna(subset=['date', 'open', 'high', 'low', 'close'])
            
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except:
        pass
    return pd.DataFrame()

# --- 3. 核心過濾器：直接刪除資本額 > 50 億名單 ---
@st.cache_data(ttl=86400)
def get_final_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    if info_df.empty:
        return pd.DataFrame([{"stock_id": "2317", "stock_name": "鴻海", "display": "2317 鴻海"}])
    
    # 僅保留一般 4 位數股票
    df = info_df[info_df['stock_id'].str.match(r'^\d{4}$', na=False)].copy()
    
    # 強制執行 50 億資本額排除
    if 'capital' in df.columns:
        df = df[df['capital'] < 5000000000]
    
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_final_universe()
options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄：回呼驅動模式 (解決選單失效) ---
def on_stock_change():
    """當選單變更時強制同步 SID"""
    new_name = st.session_state.stock_selector
    st.session_state.active_sid = display_to_id[new_name]

with st.sidebar:
    st.header("⚡ 策略選單")
    st.write(f"當前標的: `{st.session_state.active_sid}`")
    
    # 查找當前索引，確保刷新後選單位置不變
    try:
        curr_name = master_df[master_df['stock_id'] == st.session_state.active_sid]['display'].values[0]
        curr_idx = options.index(curr_name)
    except:
        curr_idx = 0

    st.selectbox(
        "🔍 篩選個股 (已排除權值股)",
        options=options,
        index=curr_idx,
        key="stock_selector",
        on_change=on_stock_change
    )

# --- 5. 主分頁區 ---
tabs = st.tabs(["📊 技術分析", "🎯 籌碼比對名單"])

# --- TAB 1: 技術分析 (極簡風格 + 漲紅跌綠) ---
with tabs[0]:
    current_sid = st.session_state.active_sid
    # 抓取較長歷史資料以穩定計算 60MA
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=360)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty and len(df_raw) >= 5:
        df = df_raw.sort_values('date').copy()
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # 繪圖前最後清洗，移除均線計算產生的前期 NaN
        plot_df = df.dropna(subset=['ma20']).copy()
        
        if not plot_df.empty:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            
            # 漲紅跌綠 K 線
            fig.add_trace(go.Candlestick(
                x=plot_df['date'], open=plot_df['open'], high=plot_df['high'], low=plot_df['low'], close=plot_df['close'],
                increasing_line_color='#FF3232', increasing_fill_color='#FF3232',
                decreasing_line_color='#00AA00', decreasing_fill_color='#00AA00'
            ), row=1, col=1)
            
            # 均線配置 (高亮度)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma5'], line=dict(color='white', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma20'], line=dict(color='#FFD700', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma60'], line=dict(color='#00FFFF', width=1.5)), row=1, col=1)
            
            # 量能圖
            fig.add_trace(go.Bar(x=plot_df['date'], y=plot_df['volume'], marker_color='gray', opacity=0.4), row=2, col=1)
            
            fig.update_layout(
                height=650, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                margin=dict(t=30, b=10, l=10, r=10),
                annotations=[dict(x=0.01, y=1.05, xref="paper", yref="paper", 
                                 text="● 5MA(白)  ● 20MA(黃)  ● 60MA(青)", 
                                 showarrow=False, font=dict(color="white", size=13))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("數據清洗後不足以繪圖。")
    else:
        st.info("無法獲取該股足夠的歷史資料。")

# --- TAB 2: 籌碼比對名單 (僅表列，無圖形) ---
with tabs[1]:
    st.subheader("🎯 大戶籌碼與股價發動名單")
    st.caption("篩選條件：資本額 < 50 億、千張大戶連週增、股價 > 20MA")
    
    if st.button("🚀 執行策略模擬掃描"):
        with st.spinner("掃描中小標的中..."):
            hit_list = []
            # 模擬測試掃描前 40 檔 (平衡速度與準確率)
            sample_list = master_df['stock_id'].tolist()[:40]
            
            for s in sample_list:
                # 抓取籌碼與價格
                c_df = safe_fetch("TaiwanStockShareholding", s, (datetime.now()-timedelta(days=25)).strftime('%Y-%m-%d'))
                p_df = safe_fetch("TaiwanStockPrice", s, (datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d'))
                
                if not c_df.empty and not p_df.empty:
                    # 動態偵測籌碼欄位 (應對變動)
                    pct_col = next((c for c in c_df.columns if 'percent' in c or 'ratio' in c), None)
                    lvl_col = next((c for c in c_df.columns if 'level' in c or 'stage' in c), None)
                    
                    if pct_col and lvl_col:
                        # 篩選 1000 張大戶 (Level 15)
                        big = c_df[c_df[lvl_col].astype(str).str.contains('1000|15')].sort_values('date')
                        if len(big) >= 2:
                            diff = float(big.iloc[-1][pct_col]) - float(big.iloc[-2][pct_col])
                            
                            # 計算技術面：站上 20MA
                            p_df['ma20'] = p_df['close'].rolling(20).mean()
                            latest = p_df.iloc[-1]
                            
                            if diff > 0 and latest['close'] > latest['ma20']:
                                s_name = master_df[master_df['stock_id']==s]['stock_name'].values[0]
                                hit_list.append({
                                    "代號": s, "名稱": s_name, 
                                    "大戶增減": f"{diff:+.2f}%",
                                    "最新收盤": latest['close'],
                                    "發動點": "✅ 站上月線"
                                })
            
            if hit_list:
                st.table(pd.DataFrame(hit_list))
            else:
                st.info("當前樣本中暫無符合「大戶增持且站上均線」之標的。")