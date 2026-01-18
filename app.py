import streamlit as st
import pandas as pd
import requests
import time

# --- 1. 系統環境設定 ---
st.set_page_config(page_title="AlphaRadar | 證交所全名單版", layout="wide")

# --- 2. 核心：從證交所 ISIN 網頁抓取全個股 (內建化) ---
@st.cache_data(ttl=86400) # 快取 24 小時，避免重複爬蟲導致卡頓
def get_twse_official_list():
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    try:
        # 證交所網頁編碼為 big5
        res = requests.get(url, timeout=15)
        res.encoding = 'big5'
        
        # 解析 HTML 表格
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0] # 設定標題
        df = df.iloc[1:]        # 移除重複標題行
        
        # 解析函數：處理「2330　台積電」這種格式
        def parse_stock_info(val):
            # 證交所使用的是全形空白 \u3000
            parts = str(val).split('\u3000')
            # 僅抓取「代號為 4 碼」的個股，排除 ETF (0050 等) 與權證
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                return parts[0], parts[1]
            return None, None

        # 執行分割
        df[['sid', 'sname']] = df['有價證券代號及名稱'].apply(lambda x: pd.Series(parse_stock_info(x)))
        
        # 清除無效資料 (只留個股)
        clean_df = df.dropna(subset=['sid'])[['sid', 'sname']].copy()
        clean_df['display'] = clean_df['sid'] + " " + clean_df['sname']
        
        return clean_df.sort_values('sid').reset_index(drop=True)
    except Exception as e:
        # 萬一證交所網站斷線，提供基礎備援名單，確保程式不崩潰
        st.error(f"連線證交所失敗，使用備援名單: {e}")
        return pd.DataFrame({
            "sid": ["2330", "2317", "2454"],
            "sname": ["台積電", "鴻海", "聯發科"],
            "display": ["2330 台積電", "2317 鴻海", "2454 聯發科"]
        })

# --- 3. 預先加載名單與狀態管理 ---
master_df = get_twse_official_list()
all_labels = master_df['display'].tolist()
label_to_id = master_df.set_index('display')['sid'].to_dict()

# 初始化 Session State
if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

# 選單變動時的回呼函式 (修復選單無反應的關鍵)
def sync_selection():
    selected_label = st.session_state.stock_selector_key
    st.session_state.active_sid = label_to_id[selected_label]

# 找出當前 active_sid 應該在選單的第幾個位置
try:
    current_label = master_df[master_df['sid'] == st.session_state.active_sid]['display'].values[0]
    current_idx = all_labels.index(current_label)
except:
    current_idx = 0

# --- 4. 側邊欄 UI 配置 ---
with st.sidebar:
    st.header("⚡ 證交所個股選單")
    # 核心修復：使用 key 與 on_change 綁定
    st.selectbox(
        "請搜尋個股代號或名稱：",
        options=all_labels,
        index=current_idx,
        key="stock_selector_key",
        on_change=sync_selection
    )
    st.divider()
    st.info(f"當前鎖定標的：{st.session_state.active_sid}")
    st.caption(f"已載入官方上市個股：{len(all_labels)} 檔")

# --- 5. 主畫面 (測試用) ---
st.title(f"📊 {st.session_state.active_sid} 技術分析")
st.write("---")
st.write(f"您現在選擇的是: **{st.session_state.active_sid}**")
st.info("現在下拉選單已內建所有來自 TWSE 的 4 碼個股，請輸入代號測試。")