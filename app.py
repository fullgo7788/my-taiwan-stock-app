import streamlit as st
import pandas as pd
import requests
import time
import urllib3

# --- 1. 系統環境設定與安全警告忽略 ---
st.set_page_config(page_title="AlphaRadar | 全市場個股同步", layout="wide")
# 忽略 SSL 警告 (針對 SSL 驗證失敗的環境)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 2. 核心：官方個股抓取 (跳過 SSL 驗證) ---
@st.cache_data(ttl=86400)
def get_official_stock_list():
    url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    try:
        # 關鍵修正：加入 verify=False 以跳過憑證驗證
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=20, verify=False)
        res.encoding = 'big5'
        
        # 讀取 HTML
        dfs = pd.read_html(res.text)
        df = dfs[0]
        df.columns = df.iloc[0]
        df = df.iloc[1:]
        
        # 解析代號與名稱 (處理全形空白 \u3000)
        def split_id_name(val):
            parts = str(val).split('\u3000')
            # 精準篩選 4 碼純個股，排除 ETF (6碼)
            if len(parts) >= 2 and len(parts[0]) == 4 and parts[0].isdigit():
                return parts[0], parts[1]
            return None, None

        df[['sid', 'sname']] = df['有價證券代號及名稱'].apply(lambda x: pd.Series(split_id_name(x)))
        
        # 清除資料並建立選單格式
        clean_df = df.dropna(subset=['sid'])[['sid', 'sname']].copy()
        clean_df['display'] = clean_df['sid'] + " " + clean_df['sname']
        
        return clean_df.sort_values('sid').reset_index(drop=True)
        
    except Exception as e:
        # 如果還是失敗，顯示詳細錯誤並使用最小備援
        st.error(f"連線證交所遇到技術障礙: {e}")
        backup = pd.DataFrame([
            {"sid": "2330", "sname": "台積電", "display": "2330 台積電"},
            {"sid": "2317", "sname": "鴻海", "display": "2317 鴻海"},
            {"sid": "2454", "sname": "聯發科", "display": "2454 聯發科"}
        ])
        return backup

# --- 3. 初始化數據與選單索引 ---
master_df = get_official_stock_list()
display_list = master_df['display'].tolist()
id_map = master_df.set_index('display')['sid'].to_dict()

if 'active_sid' not in st.session_state:
    st.session_state.active_sid = "2330"

# 選單變動回呼
def sync_selection():
    selected_label = st.session_state.stock_selector_key
    st.session_state.active_sid = id_map[selected_label]

# 計算 index 確保選單不會重置
try:
    current_display = master_df[master_df['sid'] == st.session_state.active_sid]['display'].values[0]
    default_index = display_list.index(current_display)
except:
    default_index = 0

# --- 4. 側邊欄 UI ---
with st.sidebar:
    st.header("⚡ 官方同步選單")
    st.selectbox(
        "🔍 搜尋全市場個股",
        options=display_list,
        index=default_index,
        key="stock_selector_key",
        on_change=sync_selection
    )
    st.divider()
    st.info(f"當前鎖定標的：{st.session_state.active_sid}")
    st.caption(f"已從證交所抓取：{len(display_list)} 檔個股")

# --- 5. 主內容顯示 ---
st.title(f"📊 {st.session_state.active_sid} 技術分析")
st.write(f"當前選中：**{st.session_state.active_sid}**")
st.success("SSL 憑證問題已強制繞過，現在選單已內建完整個股名單。")