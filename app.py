import streamlit as st
from FinMind.data import DataLoader
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. 系統環境初始化 ---
st.set_page_config(page_title="AlphaRadar 專業終端", layout="wide")

# 初始化全域變數，防止選單失效
if 'current_sid' not in st.session_state: st.session_state.current_sid = "2330"
if 'is_vip' not in st.session_state: st.session_state.is_vip = False

FINMIND_TOKEN = "fullgo" # 建議在此填入你的 Token
VIP_KEY = "ST888" 

@st.cache_resource
def get_loader():
    loader = DataLoader()
    if FINMIND_TOKEN: loader.token = FINMIND_TOKEN
    return loader

dl = get_loader()

# --- 2. 核心防錯數據引擎 ---
def safe_fetch(dataset, data_id=None, start_date=None):
    """
    模擬測試發現 API 容易因過快請求而拒絕，加入防護延遲與格式檢查
    """
    try:
        time.sleep(0.4) # 防護性延遲，避免 HTTP 429 錯誤
        df = dl.get_data(dataset=dataset, data_id=data_id, start_date=start_date)
        if df is not None and not df.empty:
            df.columns = [col.lower() for col in df.columns]
            if 'date' in df.columns: 
                df['date'] = pd.to_datetime(df['date'])
            # 統一欄位名稱，避免部分 API 回傳名稱不一
            df = df.rename(columns={'trading_volume': 'volume', 'max': 'high', 'min': 'low'})
            return df
    except Exception as e:
        st.error(f"數據讀取失敗: {dataset} - {e}")
    return pd.DataFrame()

# --- 3. 全市場索引 (快取 24 小時) ---
@st.cache_data(ttl=86400)
def get_universe():
    df = safe_fetch("TaiwanStockInfo")
    if df.empty:
        return pd.DataFrame([{"stock_id": "2330", "stock_name": "台積電", "display": "2330 台積電"}])
    # 過濾標準個股 (4位數代碼)
    df = df[df['stock_id'].str.match(r'^\d{4}$')]
    df['display'] = df['stock_id'].astype(str) + " " + df['stock_name'].astype(str)
    return df.sort_values('stock_id').reset_index(drop=True)

master_df = get_universe()

# --- 4. 側邊欄控制中心 (修復選單失效) ---
with st.sidebar:
    st.header("⚡ 策略控制台")
    
    options = master_df['display'].tolist()
    display_to_id = master_df.set_index('display')['stock_id'].to_dict()
    
    # 計算目前選中的 index，確保選單位置正確
    try:
        current_display = master_df[master_df['stock_id'] == st.session_state.current_sid]['display'].values[0]
        curr_idx = options.index(current_display)
    except:
        curr_idx = 0

    # 搜尋選單
    selected_tag = st.selectbox("🔍 全市場個股搜尋", options=options, index=curr_idx)
    
    # 邏輯觸發：一旦選擇不同，立即更新並強制刷新頁面
    target_sid = display_to_id[selected_tag]
    if target_sid != st.session_state.current_sid:
        st.session_state.current_sid = target_sid
        st.rerun() 
    
    st.divider()
    
    # VIP 驗證系統
    input_pw = st.text_input("💎 VIP 授權碼", type="password")
    if input_pw == VIP_KEY:
        if not st.session_state.is_vip:
            st.session_state.is_vip = True
            st.rerun()
    elif input_pw != "" and input_pw != VIP_KEY:
        st.sidebar.error("授權碼無效")

# --- 5. 主分頁顯示區 ---
tabs = st.tabs(["📊 技術診斷", "📡 強勢掃描", "🐳 籌碼動向", "💎 專業策略"])

# --- TAB 1: 技術診斷 (即時連動測試) ---
with tabs[0]:
    sid = st.session_state.current_sid
    st.subheader(f"📈 {sid} 技術走勢")
    
    df_price = safe_fetch("TaiwanStockPrice", sid, (datetime.now()-timedelta(days=150)).strftime('%Y-%m-%d'))
    
    if not df_price.empty:
        fig = go.Figure(data=[go.Candlestick(
            x=df_price['date'],
            open=df_price['open'], high=df_price['high'],
            low=df_price['low'], close=df_price['close']
        )])
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True, key=f"kline_{sid}")
    else:
        st.warning("無法取得技術面數據，請檢查 API 額度。")

# --- TAB 2: 全市場強勢掃描 (效能優化測試) ---
with tabs[1]:
    st.subheader("📡 全市場漲勢掃描 (近 3 交易日)")
    vol_filter = st.number_input("最低成交量門檻 (張)", 300, 10000, 1000)
    
    if st.button("🚀 執行全量掃描"):
        with st.spinner("正在分析 1,800 檔標的數據..."):
            # 縮小範圍至 5 天內，防止 API 超時
            scan_date = (datetime.now()-timedelta(days=5)).strftime('%Y-%m-%d')
            all_market = safe_fetch("TaiwanStockPrice", start_date=scan_date)
            
            if not all_market.empty:
                latest_dt = all_market['date'].max()
                # 篩選最新一日數據
                today_df = all_market[all_market['date'] == latest_dt].copy()
                today_df['漲幅%'] = ((today_df['close'] - today_df['open']) / today_df['open'] * 100).round(2)
                
                # 綜合條件篩選
                result = today_df[
                    (today_df['漲幅%'] > 2) & 
                    (today_df['volume'] >= vol_filter * 1000)
                ].merge(master_df[['stock_id', 'stock_name']], on='stock_id')
                
                st.success(f"掃描完成！基準日期：{latest_dt.date()}")
                st.dataframe(result[['stock_id', 'stock_name', 'close', '漲幅%', 'volume']].sort_values('漲幅%', ascending=False), use_container_width=True, hide_index=True)
            else:
                st.error("全市場抓取失敗，請稍後再試。")

# --- TAB 3: 籌碼動向 (修復日期文字報錯) ---
with tabs[2]:
    if st.session_state.is_vip:
        sid = st.session_state.current_sid
        st.subheader(f"🐳 {sid} 千張大戶持股比例 (%)")
        
        chip_df = safe_fetch("TaiwanStockShareholding", sid, (datetime.now()-timedelta(days=180)).strftime('%Y-%m-%d'))
        
        if not chip_df.empty:
            # 關鍵優化：模擬測試發現此處易混入 HTML 說明，強制僅選取數值欄位
            # 篩選大戶等級
            big_owner = chip_df[chip_df['stock_hold_level'] == '1000以上'].sort_values('date')
            if not big_owner.empty:
                # 只保留日期與比例，防止 line_chart 崩潰
                plot_df = big_owner.set_index('date')[['percent']]
                st.line_chart(plot_df)
            else:
                st.info("該標的近期無大戶異動數據。")
    else:
        st.info("💡 本功能僅開放給 VIP 用戶。請在側邊欄解鎖。")

# --- TAB 4: 專業策略 ---
with tabs[3]:
    if st.session_state.is_vip:
        st.subheader("💎 VIP 選股策略：量縮收紅")
        st.caption("條件：當日收紅 K 且成交量較前一日萎縮，暗示籌碼洗盤完成。")
        if st.button("🚀 執行量縮掃描"):
            # 執行選股邏輯...
            st.info("掃描引擎執行中...")
    else:
        st.write("### 📡 專業選股模式")
        st.caption("請輸入授權碼以開啟。")