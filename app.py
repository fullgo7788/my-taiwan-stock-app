import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 系統初始化與視覺設定 ---
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

# --- 2. 數據抓取優化 (排除雜訊與提速) ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 全域修正 3629 名稱
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_data():
    """一次性清洗：排除權證、修正名稱、建立索引"""
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        # 排除權證 (僅保留 4-5 碼純數字代號)
        df = df[df['stock_id'].str.match(r'^\d{4,5}$')]
        df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df
    return pd.DataFrame()

# 初始化主數據
master_info = get_clean_master_data()
if not master_info.empty:
    stock_options = master_info['display'].tolist()
    name_to_id = master_info.set_index('display')['stock_id'].to_dict()
else:
    stock_options, name_to_id = ["2330 台積電"], {"2330 台積電": "2330"}

# --- 3. 核心雷達掃描邏輯 ---
def fast_radar_scan(info_df):
    """三層快速過濾：資本額 -> 價格橫盤 -> 籌碼集中"""
    # 第一層：資本額 1-30 億
    small_caps = info_df[(info_df['capital'] <= 3000000000) & (info_df['capital'] >= 100000000)]
    small_ids = small_caps['stock_id'].tolist()

    # 第二層：價格橫盤 (一次性抓取今日漲跌幅)
    today = (datetime.now() - timedelta(days=0 if datetime.now().hour >= 16 else 1)).strftime('%Y-%m-%d')
    all_p = safe_get_data("TaiwanStockPrice", start_date=today)
    if all_p.empty: return pd.DataFrame()
    
    all_p['chg'] = ((all_p['close'] / all_p['open']) - 1) * 100
    candidates = all_p[
        (all_p['stock_id'].isin(small_ids)) & 
        (all_p['chg'] >= -1.5) & (all_p['chg'] <= 2.5) &
        (all_p['trading_volume'] > 500000) # 過濾無量股 (500張以上)
    ].sort_values('trading_volume', ascending=False).head(20)
    
    # 第三層：針對前 20 檔深度查籌碼
    potential_list = []
    h_start = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d')
    
    for _, row in candidates.iterrows():
        sid = row['stock_id']
        h_df = safe_get_data("TaiwanStockShareholding", sid, h_start)
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                big_h = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                if len(big_h) >= 2 and big_h['percent'].iloc[-1] > big_h['percent'].iloc[-2]:
                    s_name = small_caps[small_caps['stock_id'] == sid]['stock_name'].values[0]
                    potential_list.append({
                        "代號": sid, "名稱": s_name, "收盤": row['close'], 
                        "今日漲幅%": round(row['chg'], 2), 
                        "大戶趨勢": f"{big_h['percent'].iloc[-2]}% ➔ {big_h['percent'].iloc[-1]}%", 
                        "增持比例": round(big_h['percent'].iloc[-1] - big_h['percent'].iloc[-2], 2)
                    })
    return pd.DataFrame(potential_list)

# --- 4. 介面呈現 ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    target_display = st.selectbox("🎯 標的診斷", stock_options)
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)

tabs = st.tabs(["📊 個股雷達", "📡 強勢掃描"] + (["💎 VIP 鎖碼股"] if is_vip else []))

# --- Tab 1: 個股雷達 (視覺優化) ---
with tabs[0]:
    start_date = (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_date)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, start_date)
    
    if not p_df.empty:
        df = p_df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        
        st.subheader(f"📈 {target_display}")
        fig = go.Figure()
        # K棒顏色：紅漲、調暗的深綠跌
        fig.add_trace(go.Candlestick(
            x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            increasing_line_color='#FF3333', decreasing_line_color='#228B22',
            increasing_fillcolor='#FF3333', decreasing_fillcolor='#228B22', name="K線"
        ))
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], line=dict(color='#00CED1', width=1.5), name="20MA"))
        fig.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)
        
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                st.write("💎 大戶持股比例趨勢 (%)")
                fig_h = go.Figure(data=[go.Scatter(x=bh['date'], y=bh['percent'], mode='lines+markers', line=dict(color='#FFD700', width=2))])
                fig_h.update_layout(height=250, template="plotly_dark", margin=dict(t=10))
                st.plotly_chart(fig_h, use_container_width=True)

# --- Tab 3: VIP 鎖碼雷達 ---
if is_vip:
    with tabs[2]:
        st.subheader("🚀 籌碼集中但股價尚未發動 (中小股)")
        if st.button("執行高速雷達掃描"):
            with st.spinner("雷達掃描中..."):
                res = fast_radar_scan(master_info)
                if not res.empty:
                    st.dataframe(res.sort_values("增持比例", ascending=False), use_container_width=True)
                else:
                    st.info("雷達範圍內尚未發現符合鎖碼條件的標的。")