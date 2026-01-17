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

# --- 2. 安全數據抓取引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            # 強制更正 3629 名稱錯誤
            if 'stock_name' in df.columns:
                df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
            return df
    except Exception as e:
        # 靜默錯誤處理，避免 UI 崩潰
        pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    """提速核心：排除權證 (排除長代號或含英文) 並建立緩存"""
    df = safe_get_data("TaiwanStockInfo")
    if not df.empty:
        # 正則表達式：僅保留 4 到 5 碼純數字 (過濾權證)
        df = df[df['stock_id'].str.match(r'^\d{4,5}$')]
        df.loc[df['stock_id'] == '3629', 'stock_name'] = '地心引力'
        df['display'] = df['stock_id'] + " " + df['stock_name']
        return df
    return pd.DataFrame()

# 載入主資料
master_info = get_clean_master_info()
if not master_info.empty:
    stock_options = master_info['display'].tolist()
    name_to_id = master_info.set_index('display')['stock_id'].to_dict()
else:
    stock_options, name_to_id = ["2330 台積電"], {"2330 台積電": "2330"}

# --- 3. VIP 高速鎖碼雷達 (偵錯完成：修正字典閉合) ---
def fast_radar_scan(info_df):
    # 第一層：資本額 1-30 億
    small_caps = info_df[(info_df['capital'] <= 3000000000) & (info_df['capital'] >= 100000000)]
    small_ids = small_caps['stock_id'].tolist()

    # 第二層：價格橫盤過濾
    today = (datetime.now() - timedelta(days=0 if datetime.now().hour >= 16 else 1)).strftime('%Y-%m-%d')
    all_p = safe_get_data("TaiwanStockPrice", start_date=today)
    if all_p.empty: return pd.DataFrame()
    
    all_p['chg'] = ((all_p['close'] / all_p['open']) - 1) * 100
    # 橫盤條件：-1.5% ~ 2.5%
    candidates = all_p[
        (all_p['stock_id'].isin(small_ids)) & 
        (all_p['chg'] >= -1.5) & (all_p['chg'] <= 2.5) &
        (all_p['trading_volume'] > 500000)
    ].sort_values('trading_volume', ascending=False).head(20)
    
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
                    # --- 語法修正區：確保 JSON 字典完整閉合 ---
                    potential_list.append({
                        "代號": sid, 
                        "名稱": s_name, 
                        "收盤": row['close'], 
                        "今日漲幅%": round(row['chg'], 2), 
                        "大戶趨勢": f"{bh['percent'].iloc[-2]}% ➔ {bh['percent'].iloc[-1]}%", 
                        "增持比例": round(bh['percent'].iloc[-1] - bh['percent'].iloc[-2], 2)
                    })
    return pd.DataFrame(potential_list)

# --- 4. 介面呈現 ---
with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    target_display = st.selectbox("🎯 標格診斷", stock_options)
    target_sid = name_to_id[target_display]
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)

tabs = st.tabs(["📊 個股診斷", "📡 強勢掃描"] + (["💎 VIP 鎖碼雷達"] if is_vip else []))

# --- Tab 1: 個股診斷 (視覺調優版) ---
with tabs[0]:
    start_dt = (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", target_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", target_sid, start_dt)
    
    if not p_df.empty:
        df = p_df.rename(columns={'max':'high', 'min':'low'})
        df['ma20'] = df['close'].rolling(20).mean()
        
        st.subheader(f"📈 {target_display} 趨勢診斷")
        
        # K線配置：紅漲(#FF3333)、深森林綠跌(#228B22)
        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            increasing_line_color='#FF3333', decreasing_line_color='#228B22',
            increasing_fillcolor='#FF3333', decreasing_fillcolor='#228B22', name="K線"
        ))
        # 青色 MA20 線
        fig.add_trace(go.Scatter(x=df['date'], y=df['ma20'], line=dict(color='#00CED1', width=1.5), name="20MA"))
        
        fig.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)
        
        if not h_df.empty:
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                st.write("💎 千張大戶持股比例趨勢 (%)")
                fig_h = go.Figure(data=[go.Scatter(x=bh['date'], y=bh['percent'], mode='lines+markers', line=dict(color='#FFD700', width=2), name="大戶%")])
                fig_h.update_layout(height=250, template="plotly_dark", margin=dict(t=10))
                st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.warning("⚠️ 數據抓取失敗。請確認今日是否開盤，或 Token 是否有效。")

# --- Tab 2: 強勢掃描 ---
with tabs[1]:
    st.subheader("📡 今日爆量強勢股")
    if st.button("啟動掃描"):
        today_dt = (datetime.now() - timedelta(days=0 if datetime.now().hour >= 16 else 1)).strftime('%Y-%m-%d')
        all_data = safe_get_data("TaiwanStockPrice", start_date=today_dt)
        if not all_data.empty:
            res = all_data[(all_data['close'] > all_data['open'] * 1.03) & (all_data['trading_volume'] > 2000000)].copy()
            res['漲幅%'] = round(((res['close'] / res['open']) - 1) * 100, 2)
            st.dataframe(res[['stock_id', 'close', '漲幅%', 'trading_volume']], use_container_width=True)

# --- Tab 3: VIP 鎖碼雷達 ---
if is_vip:
    with tabs[2]:
        st.subheader("🚀 資本額 30 億內：大戶鎖碼雷達")
        if st.button("執行 VIP 深度雷達掃描"):
            with st.spinner("正在執行多層數據過濾與籌碼比對..."):
                res = fast_radar_scan(master_info)
                if not res.empty:
                    st.success(f"雷達發現 {len(res)} 檔具備潛力標的！")
                    st.table(res.sort_values("增持比例", ascending=False))
                else:
                    st.info("目前雷達範圍內無符合鎖碼條件之標的。")