import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar 專業版", layout="wide")

FINMIND_TOKEN = "fullgo" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據引擎 (強化防錯) ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.4)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns] 
            numeric_cols = ['close', 'open', 'high', 'low', 'volume', 'percent', 'capital']
            for col in df.columns:
                if any(k in col for k in numeric_cols):
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                df = df.dropna(subset=['date', 'open', 'high', 'low', 'close'])
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 索引引擎：直接剔除 50 億以上個股 ---
@st.cache_data(ttl=86400)
def get_screened_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    if info_df.empty:
        return pd.DataFrame([{"stock_id": "2317", "stock_name": "鴻海", "display": "2317 鴻海"}])
    
    df = info_df[info_df['stock_id'].str.match(r'^\d{4}$', na=False)].copy()
    if 'capital' in df.columns:
        df = df[df['capital'] < 5000000000]
    
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_screened_universe()
options = master_df['display'].tolist()
display_to_id = master_df.set_index('display')['stock_id'].to_dict()

# --- 4. 側邊欄：修復選單無作用問題 ---
with st.sidebar:
    st.header("⚡ 中小標的選單")
    # 使用 st.session_state 綁定 key，這是最穩定的選單切換方式
    if 'selected_stock_display' not in st.session_state:
        st.session_state.selected_stock_display = options[0]

    st.selectbox(
        "🔍 選擇個股 (已排除50億以上)", 
        options=options, 
        key='selected_stock_display'
    )
    
    # 從選單顯示名稱反推股票代號
    current_sid = display_to_id[st.session_state.selected_stock_display]

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術診斷", "🎯 大戶發動名單"])

# --- TAB 1: 技術診斷 ---
with tabs[0]:
    st.subheader(f"📈 {st.session_state.selected_stock_display} 分析")
    df_raw = safe_fetch("TaiwanStockPrice", current_sid, (datetime.now()-timedelta(days=300)).strftime('%Y-%m-%d'))
    
    if not df_raw.empty and len(df_raw) >= 5:
        df = df_raw.sort_values('date').copy()
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        plot_df = df.dropna(subset=['open', 'high', 'low', 'close']).copy()
        
        if not plot_df.empty:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            fig.add_trace(go.Candlestick(
                x=plot_df['date'], open=plot_df['open'], high=plot_df['high'], low=plot_df['low'], close=plot_df['close'],
                increasing_line_color='#FF3333', increasing_fill_color='#FF3333',
                decreasing_line_color='#00AA00', decreasing_fill_color='#00AA00'
            ), row=1, col=1)
            
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma5'], line=dict(color='white', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma20'], line=dict(color='#FFD700', width=2)), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['ma60'], line=dict(color='#00FFFF', width=1.5)), row=1, col=1)
            fig.add_trace(go.Bar(x=plot_df['date'], y=plot_df['volume'], marker_color='gray', opacity=0.4), row=2, col=1)
            
            fig.update_layout(
                height=650, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                margin=dict(t=10, b=10, l=10, r=10),
                annotations=[dict(x=0.01, y=0.98, xref="paper", yref="paper", text="● 5MA (白) ● 20MA (黃) ● 60MA (青)", 
                                 showarrow=False, font=dict(color="white", size=13))]
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            st.warning("暫無可繪製數據。")
    else:
        st.info("歷史數據不足或無法獲取。")

# --- TAB 2: 名單比對 ---
with tabs[1]:
    st.subheader("🎯 籌碼與股價正相關名單")
    if st.button("🚀 執行策略掃描"):
        with st.spinner("分析中..."):
            hit_list = []
            sample_pool = master_df['stock_id'].tolist()[:50] 
            for s in sample_pool:
                c_df = safe_fetch("TaiwanStockShareholding", s, (datetime.now()-timedelta(days=21)).strftime('%Y-%m-%d'))
                p_df = safe_fetch("TaiwanStockPrice", s, (datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d'))
                
                if not c_df.empty and len(p_df) > 20:
                    pct_col = next((c for c in c_df.columns if 'percent' in c or 'ratio' in c), None)
                    lvl_col = next((c for c in c_df.columns if 'level' in c or 'stage' in c), None)
                    
                    if pct_col and lvl_col:
                        big = c_df[c_df[lvl_col].astype(str).str.contains('1000|15')].sort_values('date')
                        if len(big) >= 2:
                            diff = float(big.iloc[-1][pct_col]) - float(big.iloc[-2][pct_col])
                            p_df['ma20'] = p_df['close'].rolling(20).mean()
                            latest = p_df.iloc[-1]
                            if diff > 0 and latest['close'] > latest['ma20']:
                                s_name = master_df[master_df['stock_id']==s]['stock_name'].values[0]
                                hit_list.append({"代號": s, "名稱": s_name, "大戶持股增減": f"{diff:+.2f}%", "最新收盤": latest['close']})
            if hit_list:
                st.table(pd.DataFrame(hit_list))
            else:
                st.info("目前樣本中無符合標的。")