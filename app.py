import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import numpy as np

# --- 1. 系統初始化 ---
st.set_page_config(page_title="高速籌碼雷達", layout="wide")

FINMIND_TOKEN = "fullgo" 
VIP_KEY = "ST888" 

@st.cache_resource
def init_dl():
    loader = DataLoader()
    if FINMIND_TOKEN and "fullgo" not in FINMIND_TOKEN:
        loader.token = FINMIND_TOKEN
    return loader

dl = init_dl()

# --- 2. 數據引擎 ---
def safe_get_data(dataset, data_id=None, start_date=None):
    try:
        time.sleep(0.15) # 避開頻率限制
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'stock_id' in df.columns: df['stock_id'] = df['stock_id'].astype(str)
            if 'date' in df.columns: df['date'] = pd.to_datetime(df['date'])
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_clean_master_info():
    df = safe_get_data("TaiwanStockInfo")
    # 備援基礎名單 (保證下拉選單一定有東西)
    backup_df = pd.DataFrame({
        'stock_id': ['2330', '2317', '2454', '3629', '2303'],
        'stock_name': ['台積電', '鴻海', '聯發科', '地心引力', '聯電']
    })
    if df.empty:
        df = backup_df
    else:
        df = df[df['stock_id'].str.match(r'^\d{4}$')]
        if 'stock_name' not in df.columns: df['stock_name'] = df['stock_id']
    
    df['display'] = df['stock_id'] + " " + df['stock_name']
    return df

# --- 3. 處理狀態與選擇 ---
master_info = get_clean_master_info()
name_to_id = master_info.set_index('display')['stock_id'].to_dict()
id_to_name = master_info.set_index('stock_id')['stock_name'].to_dict()

with st.sidebar:
    st.header("⚡ 高速籌碼雷達")
    # 核心選單：target_display 是唯一驅動源
    target_display = st.selectbox(
        "🎯 選擇診斷個股", 
        options=list(name_to_id.keys()),
        index=0,
        key="global_selector"
    )
    
    # 強制獲取最新的 ID 與名稱
    sel_sid = name_to_id[target_display]
    sel_sname = id_to_name.get(sel_sid, "未知")
    
    st.divider()
    user_key = st.text_input("💎 VIP 授權碼", type="password")
    is_vip = (user_key == VIP_KEY)
    if is_vip: st.success("✅ VIP 權限已解鎖")

# --- 4. 功能分頁 (所有內容都引用 sel_sid 與 sel_sname) ---
tabs = st.tabs(["📊 趨勢診斷", "📡 強勢掃描", "💎 VIP 鎖碼雷達"])

with tabs[0]:
    # 標題強制連動
    st.subheader(f"🔍 診斷報告：{sel_sid} {sel_sname}")
    
    start_dt = (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d')
    p_df = safe_get_data("TaiwanStockPrice", sel_sid, start_dt)
    h_df = safe_get_data("TaiwanStockShareholding", sel_sid, (datetime.now()-timedelta(days=120)).strftime('%Y-%m-%d'))
    
    if not p_df.empty:
        df = p_df.sort_values('date').reset_index(drop=True)
        # 統一處理繪圖欄位
        df = df.rename(columns={'max':'high', 'min':'low'})
        df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')
        df['ma20'] = df['close'].rolling(20).mean()
        
        # 繪圖連動
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(
            x=df['date_str'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            name=f"{sel_sname} K線", increasing_line_color='#FF3333', decreasing_line_color='#228B22'
        ))
        fig.add_trace(go.Scatter(x=df['date_str'], y=df['ma20'], line=dict(color='#00CED1', width=1.5), name="20MA"))
        
        fig.update_xaxes(type='category', nticks=10)
        fig.update_layout(height=550, template="plotly_dark", xaxis_rangeslider_visible=False, title=f"{sel_sid} 最近半年走勢")
        st.plotly_chart(fig, use_container_width=True)
        
        # 大戶籌碼連動
        if not h_df.empty:
            st.divider()
            st.markdown(f"### 💎 {sel_sname} 千張大戶持股趨勢")
            c_col = next((c for c in h_df.columns if 'class' in c), None)
            if c_col:
                bh = h_df[h_df[c_col].astype(str).str.contains('1000以上')].sort_values('date').copy()
                if not bh.empty:
                    bh['date_str'] = bh['date'].dt.strftime('%Y-%m-%d')
                    fig_h = go.Figure(go.Scatter(x=bh['date_str'], y=bh['percent'], mode='lines+markers', line=dict(color='#FFD700')))
                    fig_h.update_xaxes(type='category', nticks=5)
                    fig_h.update_layout(height=250, template="plotly_dark")
                    st.plotly_chart(fig_h, use_container_width=True)
    else:
        st.error(f"目前無法抓取 {sel_sid} 的行情資料，請確認 API Token 有效性。")

# --- Tab 2: 強勢掃描 (保持獨立邏輯) ---
with tabs[1]:
    st.subheader("📡 強勢股爆量雷達")
    if st.button("啟動掃描", key="scan_btn_final"):
        with st.spinner("雷達掃描全市場中..."):
            for i in range(7):
                d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_p = safe_get_data("TaiwanStockPrice", start_date=d)
                if not all_p.empty:
                    res = all_p[(all_p['close'] > all_p['open']*1.04) & (all_p['trading_volume'] > 2000000)].copy()
                    if not res.empty:
                        res = res.merge(master_info[['stock_id', 'stock_name']], on='stock_id', how='left')
                        st.success(f"✅ 發現日期：{d}")
                        st.dataframe(res[['stock_id', 'stock_name', 'close', 'trading_volume']].sort_values('trading_volume', ascending=False))
                        break

# --- Tab 3: VIP 鎖碼雷達 (修復連動與無反應) ---
with tabs[2]:
    if not is_vip:
        st.warning("🔒 請輸入 VIP 授權碼以解鎖深度分析。")
    else:
        st.subheader("🚀 鎖碼雷達 (追蹤大戶集結個股)")
        if st.button("執行深度鎖碼分析", key="vip_scan_btn"):
            bar = st.progress(0)
            with st.spinner("分析中..."):
                # 取得最新收盤
                today_p = pd.DataFrame()
                for i in range(5):
                    d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                    today_p = safe_get_data("TaiwanStockPrice", start_date=d)
                    if not today_p.empty: break
                
                if not today_p.empty:
                    cands = today_p[
                        (today_p['stock_id'].isin(master_info['stock_id'])) & 
                        (today_p['trading_volume'] >= 1000000) & (today_p['close'] <= 400)
                    ].sort_values('trading_volume', ascending=False).head(12)
                    
                    final = []
                    for idx, row in enumerate(cands.iterrows()):
                        sid = row[1]['stock_id']
                        bar.progress((idx+1)/12)
                        h_data = safe_get_data("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=21)).strftime('%Y-%m-%d'))
                        if not h_data.empty:
                            c_col = next((c for c in h_data.columns if 'class' in c), None)
                            if c_col:
                                bh = h_data[h_data[c_col].astype(str).str.contains('1000以上')].sort_values('date')
                                if len(bh) >= 2 and bh['percent'].iloc[-1] > bh['percent'].iloc[-2]:
                                    s_name = id_to_name.get(sid, "未知")
                                    final.append({
                                        "代號": sid, "名稱": s_name, "收盤": row[1]['close'], 
                                        "大戶增幅": f"{round(bh['percent'].iloc[-1] - bh['percent'].iloc[-2], 2)}%",
                                        "最新持股": f"{bh['percent'].iloc[-1]}%"
                                    })
                    if final:
                        st.table(pd.DataFrame(final).sort_values("大戶增幅", ascending=False))
                    else:
                        st.info("今日無大戶明顯鎖碼標的。")