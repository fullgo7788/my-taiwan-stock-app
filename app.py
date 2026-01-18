import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests
import time

# --- 1. 系統初始化 (必須放在最前) ---
st.set_page_config(page_title="AlphaRadar | 全市場修復版", layout="wide")

# --- 2. 爬取證交所/櫃買官方個股名單 (上市+上櫃) ---
@st.cache_data(ttl=86400)
def fetch_full_stock_list():
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
    all_data = []
    for url in urls:
        try:
            res = requests.get(url, timeout=10)
            res.encoding = 'big5'
            df = pd.read_html(res.text)[0]
            df.columns = df.iloc[0]
            df = df.iloc[1:]
            
            def parse_row(val):
                parts = str(val).split('\u3000') # 分割代號與名稱
                if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                    return parts[0], parts[1]
                return None, None
            
            df[['sid', 'sname']] = df['有價證券代號及名稱'].apply(lambda x: pd.Series(parse_row(x)))
            all_data.append(df.dropna(subset=['sid'])[['sid', 'sname']])
        except: continue
    
    if not all_data:
        return pd.DataFrame({"sid": ["2330"], "sname": ["台積電"], "display": ["2330 台積電"]})
    
    final_df = pd.concat(all_data).drop_duplicates('sid')
    final_df['display'] = final_df['sid'] + " " + final_df['sname']
    return final_df.sort_values('sid').reset_index(drop=True)

# 預加載名單 (確保名單在選單出現前就準備好)
master_df = fetch_full_stock_list()
display_list = master_df['display'].tolist()
id_map = master_df.set_index('display')['sid'].to_dict()

# --- 3. 狀態同步邏輯 (徹底修復選單無反應) ---
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

def sync_stock():
    # 當下拉選單選擇後觸發
    new_label = st.session_state.stock_selector_key
    st.session_state.active_sid = id_map[new_label]
    # 不使用額外指令，Streamlit 會自動觸發 Rerun

# 找出當前 active_sid 對應的文字索引
try:
    current_text = master_df[master_df['sid'] == st.session_state.active_sid]['display'].values[0]
    current_idx = display_list.index(current_text)
except:
    current_idx = 0

# --- 4. 側邊欄配置 ---
with st.sidebar:
    st.header("⚡ 策略監控中心")
    st.selectbox(
        "🔍 選擇全市場個股 (上市/上櫃)",
        options=display_list,
        index=current_idx,
        key="stock_selector_key",
        on_change=sync_stock # 這是修復點：一旦改變立即執行回呼
    )
    st.divider()
    st.info(f"當前鎖定標的：{st.session_state.active_sid}")
    st.caption(f"名單總數：{len(display_list)} 檔")

# --- 5. 繪圖與技術分析 ---
FINMIND_TOKEN = "fullgo" 
@st.cache_resource
def get_dl():
    l = DataLoader()
    if FINMIND_TOKEN: l.token = FINMIND_TOKEN
    return l

dl = get_dl()

def get_data(sid):
    try:
        time.sleep(0.3)
        df = dl.get_data(dataset="TaiwanStockPrice", data_id=sid, 
                         start_date=(datetime.now()-timedelta(days=450)).strftime('%Y-%m-%d'))
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            df['date'] = pd.to_datetime(df['date'])
            return df.sort_values('date')
    except: pass
    return pd.DataFrame()

tabs = st.tabs(["📊 專業 K 線", "🎯 大戶掃描"])

with tabs[0]:
    sid = st.session_state.active_sid
    df = get_data(sid)
    
    if not df.empty:
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        pdf = df.dropna(subset=['ma5']).tail(180)
        d_str = pdf['date'].dt.strftime('%Y-%m-%d').tolist()
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=d_str, open=pdf['open'], high=pdf['high'], low=pdf['low'], close=pdf['close'],
                                    increasing_line_color='#FF3232', decreasing_line_color='#00AA00', name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=d_str, y=pdf['ma5'], line=dict(color='white', width=1), name="5MA"), row=1, col=1)
        fig.add_trace(go.Scatter(x=d_str, y=pdf['ma20'], line=dict(color='#FFD700', width=2), name="20MA"), row=1, col=1)
        fig.add_trace(go.Scatter(x=d_str, y=pdf['ma60'], line=dict(color='#00FFFF', width=1.5), name="60MA"), row=1, col=1)
        fig.add_trace(go.Bar(x=d_str, y=pdf['volume'], marker_color='gray', opacity=0.4), row=2, col=1)
        
        fig.update_layout(height=700, template="plotly_dark", showlegend=False, xaxis_rangeslider_visible=False,
                          margin=dict(t=30, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error(f"代號 {sid} 暫無歷史數據。")