import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar 專業版", layout="wide")

if 'current_sid' not in st.session_state: 
    st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 數據防錯引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.4)
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns] 
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'], errors='coerce')
                df = df.dropna(subset=['date'])
            # 數值轉換
            for col in df.columns:
                if any(k in col for k in ['close', 'open', 'high', 'low', 'volume', 'percent', 'capital']):
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 索引引擎：剔除資本額 > 50 億個股 ---
@st.cache_data(ttl=86400)
def get_small_cap_universe():
    info_df = safe_fetch("TaiwanStockInfo")
    if info_df.empty:
        return pd.DataFrame([{"stock_id": "2317", "stock_name": "鴻海", "display": "2317 鴻海"}])
    
    df = info_df[info_df['stock_id'].str.match(r'^\d{4}$', na=False)].copy()
    if 'capital' in df.columns:
        # 嚴格過濾資本額 < 50 億
        df = df[df['capital'] < 5000000000]
    
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_small_cap_universe()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚡ 中小標的選單")
    options = master_df['display'].tolist()
    display_to_id = master_df.set_index('display')['stock_id'].to_dict()
    
    if st.session_state.current_sid not in display_to_id.values():
        st.session_state.current_sid = master_df.iloc[0]['stock_id']

    current_val = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
    selected_tag = st.selectbox("🔍 選擇個股", options=options, index=options.index(current_val))
    
    if display_to_id[selected_tag] != st.session_state.current_sid:
        st.session_state.current_sid = display_to_id[selected_tag]
        st.rerun()

# --- 5. 主分頁 ---
tabs = st.tabs(["📊 技術診斷", "🎯 大戶發動名單"])

# --- TAB 1: 技術診斷 (漲紅跌綠、顏色強化、移除Legend) ---
with tabs[0]:
    sid = st.session_state.current_sid
    df_p = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=260)).strftime('%Y-%m-%d'))
    if not df_p.empty:
        df = df_p.sort_values('date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=[0.75, 0.25])
        
        # 1. K線圖 (漲紅跌綠)
        fig.add_trace(go.Candlestick(
            x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            increasing_line_color='#FF3333', increasing_fill_color='#FF3333', # 漲紅
            decreasing_line_color='#00AA00', decreasing_fill_color='#00AA00', # 跌綠
            name="K線"
        ), row=1, col=1)
        
        # 2. 均線 (高對比顏色)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], line=dict(color='white', width=1.2), name="5MA"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], line=dict(color='#FFD700', width=2), name="20MA"), row=1, col=1) # 鮮黃色
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma60'], line=dict(color='#00FFFF', width=1.5), name="60MA"), row=1, col=1) # 亮青色
        
        # 3. 成交量
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], marker_color='gray', opacity=0.4), row=2, col=1)
        
        # 4. 配置與純淨化設定
        fig.update_layout(
            height=650, 
            template="plotly_dark", 
            showlegend=False, # 移除上方標籤
            xaxis_rangeslider_visible=False,
            margin=dict(t=10, b=10, l=10, r=10),
            # 在圖形內加入均線顏色說明文字
            annotations=[
                dict(x=0.01, y=0.98, xref="paper", yref="paper", text="● 5MA (白)  ● 20MA (黃)  ● 60MA (青)", 
                     showarrow=False, font=dict(color="white", size=12))
            ]
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("數據載入中...")

# --- TAB 2: 名單比對 ---
with tabs[1]:
    st.subheader("🎯 籌碼與股價正相關名單")
    st.write("條件：大戶持股增加 + 股價站上20日線 (限資本額<50億)")
    if st.button("🚀 開始掃描分析"):
        with st.spinner("比對中..."):
            hit_list = []
            sample_pool = master_df['stock_id'].tolist()[:50] 
            for s in sample_pool:
                c_df = safe_fetch("TaiwanStockShareholding", s, (datetime.now()-timedelta(days=21)).strftime('%Y-%m-%d'))
                p_df = safe_fetch("TaiwanStockPrice", s, (datetime.now()-timedelta(days=40)).strftime('%Y-%m-%d'))
                
                if not c_df.empty and not p_df.empty:
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
                                hit_list.append({
                                    "代號": s, "名稱": s_name, 
                                    "大戶持股增減": f"{diff:+.2f}%",
                                    "最新收盤": latest['close'],
                                    "狀態": "📈 趨勢正向"
                                })
            if hit_list:
                st.table(pd.DataFrame(hit_list))
            else:
                st.info("暫無符合標的。")