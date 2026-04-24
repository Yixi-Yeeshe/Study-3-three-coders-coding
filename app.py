import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# ===== 配置 =====
RAW_SHEET = "raw_data"
KAPPA_SHEET = "kappa_format"

QUESTIONS = [
    {"item_id": 1, "question": "P1：“脸在屏幕上越来越看不全” 属于（）"},
    {"item_id": 2, "question": "P2：“肿了” 属于（）"}
]

OPTIONS = [
    "1. 全身比例型描述","2. 全身与他人做比较描述","3. 局部身体描述",
    "4. 面部/脸部描述","5. 发福/变胖描述","6. 体型大小描述",
    "7. 身材变化描述","8. 否定式肥胖描述","9. 委婉/中性描述",
    "10. 负面评价描述","11. 夸张/戏剧化描述","12. 隐喻/比喻描述",
    "13. 动物化/物化描述","14. 年龄化描述","15. 性别化描述",
    "16. 健康风险描述","17. 医学/疾病描述","18. 审美/外貌描述",
    "19. 不确定","20. 其他"
]

# ===== 连接 Google Sheets =====
@st.cache_resource
def connect_sheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes
    )
    client = gspread.authorize(creds)
    return client.open(st.secrets["spreadsheet_name"])


def get_ws(sheet, name):
    try:
        return sheet.worksheet(name)
    except:
        return sheet.add_worksheet(title=name, rows=1000, cols=20)


def read_data(ws):
    data = ws.get_all_records()
    if not data:
        return pd.DataFrame(columns=["coder_id","item_id","question","answer","comment","time"])
    return pd.DataFrame(data)


def write_data(ws, df):
    ws.clear()
    ws.update([df.columns.tolist()] + df.astype(str).values.tolist())


def update_kappa(ws, df):
    if df.empty:
        ws.clear()
        return

    df = df.copy()

    df["item_id"] = pd.to_numeric(df["item_id"], errors="coerce")
    df = df.dropna(subset=["item_id"])
    df["item_id"] = df["item_id"].astype(int)

    # 清理空值，避免 Google Sheets API 报 InvalidJSONError
    df = df.fillna("")

    wide = df.pivot_table(
        index=["item_id", "question"],
        columns="coder_id",
        values="answer",
        aggfunc="first"
    ).reset_index()

    wide.columns.name = None
    wide = wide.sort_values("item_id")

    # pivot 后未完成的 coder 会产生 NaN，这里转成空白
    wide = wide.fillna("")

    ws.clear()
    ws.update([wide.columns.tolist()] + wide.astype(str).values.tolist())


# ===== UI =====
st.set_page_config(layout="wide")
st.title("Study 3 Coding")

sheet = connect_sheet()
raw_ws = get_ws(sheet, RAW_SHEET)
kappa_ws = get_ws(sheet, KAPPA_SHEET)

coder = st.text_input("请输入 coder ID")

if not coder:
    st.stop()

df = read_data(raw_ws)

done_ids = set(df[df["coder_id"] == coder]["item_id"])

remaining = [q for q in QUESTIONS if q["item_id"] not in done_ids]

if not remaining:
    st.success("完成！")
else:
    q = remaining[0]

    st.subheader(f"Q{q['item_id']}")
    st.write(q["question"])

    cols = st.columns(3)
    groups = [OPTIONS[i::3] for i in range(3)]

    selected = None
    for i, col in enumerate(cols):
        choice = col.radio("", groups[i], index=None, key=f"{q['item_id']}_{i}")
        if choice:
            selected = choice

    comment = st.text_area("备注")

    if st.button("保存"):
        if not selected:
            st.warning("请选择一个选项")
        else:
            new = {
                "coder_id": coder,
                "item_id": q["item_id"],
                "question": q["question"],
                "answer": selected,
                "comment": comment,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # 覆盖旧答案
            df = df[~((df["coder_id"]==coder)&(df["item_id"]==q["item_id"]))]

            df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)

            write_data(raw_ws, df)
            update_kappa(kappa_ws, df)

            st.success("已保存")
            st.rerun()
