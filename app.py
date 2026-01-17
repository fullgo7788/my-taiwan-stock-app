import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化 ---
st.set_page_config(page_title="AlphaRadar 終極策略端", layout="wide")

if 'is_vip' not in st.session_state: st.session_state.is_vip = False
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888"

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 核心數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.4) # 穩定請求頻率
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            df = df.rename(columns={
                'trading_volume': 'volume', 'max': 'high', 'min': 'low',
                'stock_hold_class': 'level', 'stock_hold_level': 'level', 'stage': 'level'
            })
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            return df
    except: pass
    return pd.DataFrame()

# --- 3. 索引與側邊欄 ---
@st.cache_data(ttl=86400)
def get_universe():
    raw = safe_fetch("TaiwanStockInfo")
    if raw.empty: return pd.DataFrame([{"stock_id":"2330","stock_name":"台積電","display":"2330 台積電"}])
    raw = raw[raw['stock_id'].str.match(r'^\d{4}$')]
    raw['display'] = raw['stock_id'] + " " + raw['stock_name'].fillna("個股")
    return raw.sort_values('stock_id')

master_df = get_universe()
tag_map = master_df.set_index('display')['stock_id'].to_dict()

with st.sidebar:
    st.header("⚡ 策略控制台")
    try:
        curr_idx = int(master_df[master_df['stock_id'] == st.session_state.current_sid].index[0])
    except:
        curr_idx = 0
    sel_tag = st.selectbox("🔍 全市場搜尋", options=master_df['display'].tolist(), index=curr_idx)
    st.session_state.current_sid = tag_map[sel_tag]
    
    st.divider()
    pw = st.text_input("💎 VIP 授權碼", type="password")
    if pw == VIP_KEY: st.session_state.is_vip = True

# --- 4. 主功能區 ---
tabs = st.tabs(["📊 技術診斷", "📡 基礎掃描", "🐳 籌碼連動", "💎 VIP 策略選股"])

# (TAB 1-3 保持原有的穩定繪圖代碼...)
with tabs[0]:
    hist = safe_fetch("TaiwanStockPrice", st.session_state.current_sid, (datetime.now()-timedelta(days=200)).strftime('%Y-%m-%d'))
    if not hist.empty:
        df = hist.sort_values('date')
        df['ma5'] = df['close'].rolling(5).mean()
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="K線"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma5'], name="MA5", line=dict(color='white')), row=1, col=1)
        fig.add_trace(go.Bar(x=df['date'], y=df['volume'], name="量", marker_color='gray'), row=2, col=1)
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

with tabs[1]:
    st.write("請使用側邊欄解鎖 VIP 以開啟高級掃描。")

with tabs[2]:
    if st.session_state.is_vip:
        chip = safe_fetch("TaiwanStockShareholding", st.session_state.current_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
        if not chip.empty:
            st.line_chart(chip.iloc[:,-1]) # 顯示最後一欄比例
    else: st.warning("🔒 籌碼功能僅限 VIP")

# --- TAB 4: 前一交易日「量縮收紅」選股核心 ---
with tabs[3]:
    if st.session_state.is_vip:
        st.subheader("💎 VIP 策略：前一交易日量縮收紅")
        st.info("💡 此策略會自動尋找市場最近一個完整交易日，並篩選出：股價收紅 + 成交量較前日萎縮 + 站穩 5MA 的標的。")
        
        v_limit = st.number_input("最低成交量門檻 (張)", 300, 20000, 1000, key="v4_final")
        
        if st.button("🚀 啟動大數據掃描"):
            with st.spinner("正在運算 1,800 檔個股，請稍候..."):
                # 抓取近 20 天資料，確保有足夠樣本算 MA5 與 比對量能
                df_all = safe_fetch("TaiwanStockPrice", start_date=(datetime.now()-timedelta(days=20)).strftime('%Y-%m-%d'))
                
                if not df_all.empty:
                    # 關鍵：自動偵測「最後一個完整交易日」
                    latest_date = df_all['date'].max()
                    hits = []
                    
                    # 依照股票分組計算
                    grouped = df_all.groupby('stock_id')
                    for sid, g in grouped:
                        if len(g) < 6: continue
                        g = g.sort_values('date')
                        
                        # 計算 MA5
                        g['ma5'] = g['close'].rolling(5).mean()
                        
                        # 取得最後兩筆 (今日/最新交易日 vs 昨日)
                        t = g.iloc[-1]
                        y = g.iloc[-2]
                        
                        # 檢查基準日是否為市場最新交易日
                        if t['date'] != latest_date: continue
                        
                        # 策略條件：
                        cond_red = t['close'] > t['open']         # 收紅
                        cond_vol_down = t['volume'] < y['volume'] # 量縮
                        cond_ma5 = t['close'] > t['ma5']         # 站在5MA之上
                        cond_liquid = t['volume'] >= v_limit*1000 # 基本量過濾
                        
                        if cond_red and cond_vol_down and cond_ma5 and cond_liquid:
                            hits.append({
                                '股票代號': sid,
                                '收盤價': t['close'],
                                '今日量(張)': int(t['volume']/1000),
                                '昨日量(張)': int(y['volume']/1000),
                                '量縮比': f"{round((1 - t['volume']/y['volume'])*100, 1)}%",
                                '5MA': round(t['ma5'], 2)
                            })
                    
                    if hits:
                        res_df = pd.DataFrame(hits).merge(master_df[['stock_id', 'stock_name']], left_on='股票代號', right_on='stock_id')
                        st.success(f"✅ 掃描完成！基準日：{latest_date}")
                        st.dataframe(res_df[['股票代號', 'stock_name', '收盤價', '今日量(張)', '昨日量(張)', '量縮比', '5MA']], use_container_width=True, hide_index=True)
                    else:
                        st.warning(f"基準日 {latest_date} 暫無符合量縮收紅條件之標的。")
                else:
                    st.error("無法取得市場數據，請檢查連線。")
    else:
        st.error("🔒 此為 VIP 專屬分頁。請於側邊欄輸入 ST888。")