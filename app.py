import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

RAW_SHEET = "raw_data"
KAPPA_SHEET = "kappa_format"

DATA_PATH = "用于app数据.csv"

OPTIONS = [
    "A. 肥胖外观描述 obesity appearance",
    "B. 肥胖原因描述 obesity causes",
    "C. 肥胖发展描述 fatness development",
    "D. 肥胖影响描述（包含正面和负面） obesity consequences"
    "E. 对超重肥胖者的称谓 addressing overweight/obese people"
]

S_COLUMNS = [f"S{i}" for i in range(1, 9)]

RAW_HEADER = [
    "coder_id",
    "sentence_id",
    "s_col",
    "sentence",
    "question",
    "answer",
    "comment",
    "updated_at"
]

st.set_page_config(page_title="Study 3 Coding", layout="wide")
st.title("Study 3 Coding Task")


# -----------------------------
# 1. Load local question file
# -----------------------------
@st.cache_data
def load_questions_from_csv(file_path):
    df = pd.read_csv(file_path)

    required_cols = ["ID", "Sentence"] + S_COLUMNS

    for col in required_cols:
        if col not in df.columns:
            st.error(f"CSV 文件缺少必要列：{col}")
            st.stop()

    pages = []

    for _, row in df.iterrows():
        sentence_id = row["ID"]
        sentence_text = row["Sentence"]

        if pd.isna(sentence_id) or pd.isna(sentence_text):
            continue

        sub_questions = []

        for s_col in S_COLUMNS:
            value = row[s_col]

            if pd.notna(value) and str(value).strip() != "":
                sub_questions.append({
                    "s_col": s_col,
                    "text": str(value).strip()
                })

        if len(sub_questions) > 0:
            pages.append({
                "sentence_id": str(sentence_id).strip(),
                "sentence": str(sentence_text).strip(),
                "sub_questions": sub_questions
            })

    return pages


# -----------------------------
# 2. Cached Google Sheet connection
# -----------------------------
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
    sheet = client.open(st.secrets["spreadsheet_name"])
    return sheet


@st.cache_resource
def get_cached_ws(name, rows=1000, cols=50):
    """
    Cache worksheet objects so that Streamlit does not fetch sheet metadata
    every time the user clicks Next / Previous.
    """
    sheet = connect_sheet()
    try:
        return sheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=name, rows=rows, cols=cols)
        ws.update([RAW_HEADER] if name == RAW_SHEET else [["sentence_id", "s_col", "question"]])
        return ws


def ensure_raw_header(raw_ws):
    """
    Make sure raw_data has the correct header.
    """
    values = raw_ws.get_all_values()

    if not values:
        raw_ws.update([RAW_HEADER])
        return

    current_header = values[0]

    if current_header != RAW_HEADER:
        # Only overwrite header row, not the whole sheet.
        raw_ws.update("A1:H1", [RAW_HEADER])


# -----------------------------
# 3. Cached reading from raw_data
# -----------------------------
@st.cache_data(ttl=60)
def read_raw_data_cached():
    """
    Read raw_data from Google Sheets.

    ttl=60 means Streamlit will not repeatedly read Google Sheets within 60 seconds.
    After saving, we clear this cache so the app can see the latest answers.
    """
    raw_ws = get_cached_ws(RAW_SHEET)
    ensure_raw_header(raw_ws)

    values = raw_ws.get_all_values()

    if len(values) <= 1:
        df = pd.DataFrame(columns=RAW_HEADER)
        df["_row_num"] = []
        return df

    header = values[0]
    rows = values[1:]

    df = pd.DataFrame(rows, columns=header)

    for col in RAW_HEADER:
        if col not in df.columns:
            df[col] = ""

    df = df[RAW_HEADER]
    df = df.fillna("")

    # Google Sheets row numbers start from 1.
    # Data rows begin at row 2 because row 1 is the header.
    df["_row_num"] = range(2, len(df) + 2)

    return df


def clear_raw_cache():
    read_raw_data_cached.clear()


# -----------------------------
# 4. Fast save: update only necessary rows
# -----------------------------
def save_page_responses_fast(
    raw_ws,
    df,
    coder_id,
    sentence_id,
    sentence,
    responses,
    comment
):
    """
    Faster than clearing and rewriting the whole raw_data sheet.

    For each coder + sentence_id + s_col:
    - if the row already exists: update that row only
    - if the row does not exist: append a new row

    This means going back and changing an answer WILL overwrite the old answer
    for that coder + sentence + S item.
    """
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    df = df.copy()

    # Existing rows for the same coder and same sentence
    existing = df[
        (df["coder_id"].astype(str) == str(coder_id)) &
        (df["sentence_id"].astype(str) == str(sentence_id))
    ]

    updates = []
    append_rows = []

    for item in responses:
        s_col = item["s_col"]

        row_values = [
            coder_id,
            sentence_id,
            s_col,
            sentence,
            item["question"],
            item["answer"],
            comment,
            updated_at
        ]

        matched = existing[existing["s_col"].astype(str) == str(s_col)]

        if not matched.empty:
            row_num = int(matched.iloc[0]["_row_num"])
            updates.append({
                "range": f"A{row_num}:H{row_num}",
                "values": [row_values]
            })
        else:
            append_rows.append(row_values)

    # Batch update existing rows in one API call
    if updates:
        raw_ws.batch_update(updates)

    # Append all new rows in one API call
    if append_rows:
        raw_ws.append_rows(append_rows, value_input_option="USER_ENTERED")

    # Important: make Streamlit read the newest saved data after this save
    clear_raw_cache()


# -----------------------------
# 5. Kappa format: update manually, not every question
# -----------------------------
def update_kappa_format(kappa_ws, df):
    """
    Rebuild kappa_format from raw_data.

    This can be slow for large data, so the app now only runs it when the user
    clicks the 'Update kappa_format' button.
    """
    kappa_ws.clear()

    if df.empty:
        kappa_ws.update([["sentence_id", "s_col", "question"]])
        return

    df = df.copy()
    df = df.fillna("")

    # Remove helper column if present
    if "_row_num" in df.columns:
        df = df.drop(columns=["_row_num"])

    wide = df.pivot_table(
        index=["sentence_id", "s_col", "question"],
        columns="coder_id",
        values="answer",
        aggfunc="first"
    ).reset_index()

    wide.columns.name = None
    wide = wide.fillna("")
    wide = wide.sort_values(["sentence_id", "s_col"])

    kappa_ws.update(
        [wide.columns.tolist()] + wide.astype(str).values.tolist()
    )


# -----------------------------
# 6. App starts here
# -----------------------------
PAGES = load_questions_from_csv(DATA_PATH)

if len(PAGES) == 0:
    st.error("CSV 中没有可用题目。请检查 ID、Sentence、S1-S8 是否有内容。")
    st.stop()


raw_ws = get_cached_ws(RAW_SHEET)
kappa_ws = get_cached_ws(KAPPA_SHEET)

df = read_raw_data_cached()


coder = st.text_input(
    "请输入你的 coder ID：",
    placeholder="例如 CoderA / CoderB / CoderC"
)

if not coder:
    st.info("请输入 coder ID 后开始。")
    st.stop()

coder = coder.strip().lower()

if "finished" not in st.session_state:
    st.session_state.finished = False

st.write(f"Current coder: {coder}")
st.info(
    "点击“下一题”会自动保存本页所有答案。"
    "下次输入同一个 coder ID，会自动回到你上次停止的位置。"
)


coder_df = df[df["coder_id"].astype(str) == coder]

if not coder_df.empty:
    completed_sentence_ids = set(coder_df["sentence_id"].astype(str).tolist())
else:
    completed_sentence_ids = set()

total = len(PAGES)
done = len(completed_sentence_ids)

st.progress(done / total)
st.write(f"进度：{done}/{total}")


# Reset position when coder changes
if "current_coder" not in st.session_state or st.session_state.current_coder != coder:
    st.session_state.current_coder = coder
    st.session_state.finished = False

    first_incomplete_index = 0
    all_completed = True

    for i, page in enumerate(PAGES):
        if page["sentence_id"] not in completed_sentence_ids:
            first_incomplete_index = i
            all_completed = False
            break

    st.session_state.current_index = first_incomplete_index

    if all_completed:
        st.session_state.finished = True

if "current_index" not in st.session_state:
    st.session_state.current_index = 0


if st.session_state.finished:
    st.success("所有题目已经完成。谢谢你的参与！")
    st.balloons()

    st.divider()
    if st.button("更新 kappa_format 表"):
        latest_df = read_raw_data_cached()
        update_kappa_format(kappa_ws, latest_df)
        st.success("kappa_format 已更新。")

    st.stop()


idx = st.session_state.current_index
idx = max(0, min(idx, len(PAGES) - 1))
st.session_state.current_index = idx

page = PAGES[idx]

sentence_id = page["sentence_id"]
sentence = page["sentence"]
sub_questions = page["sub_questions"]

st.divider()
st.subheader(f"Sentence {idx + 1} of {total}")
st.write(f"**ID:** {sentence_id}")

st.markdown("### 原句")
st.write(sentence)

st.markdown("### 请判断下面每个片段属于哪个选项")


existing_page_answers = df[
    (df["coder_id"].astype(str) == coder) &
    (df["sentence_id"].astype(str) == str(sentence_id))
]

existing_answer_dict = {}
existing_comment = ""

for _, row in existing_page_answers.iterrows():
    existing_answer_dict[str(row["s_col"])] = str(row["answer"])
    if str(row.get("comment", "")).strip() != "":
        existing_comment = str(row.get("comment", "")).strip()

responses = []

for sub_q in sub_questions:
    s_col = sub_q["s_col"]
    q_text = sub_q["text"]

    st.divider()
    st.markdown(f"#### {s_col}")

    full_question = f"{q_text} 属于下面哪个选项？"
    st.write(full_question)

    default_answer = existing_answer_dict.get(s_col, None)

    if default_answer in OPTIONS:
        default_index = OPTIONS.index(default_answer)
    else:
        default_index = None

    answer = st.radio(
        label=f"{s_col}_answer",
        options=OPTIONS,
        index=default_index,
        key=f"{coder}_{sentence_id}_{s_col}",
        label_visibility="collapsed"
    )

    responses.append({
        "s_col": s_col,
        "question": full_question,
        "answer": answer
    })


comment = st.text_area(
    "本页备注（可选）：",
    value=existing_comment,
    key=f"{coder}_{sentence_id}_comment"
)


st.divider()

nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 1])

with nav_col1:
    if st.button("⬅️ 上一题"):
        st.session_state.finished = False
        if st.session_state.current_index > 0:
            st.session_state.current_index -= 1
            st.rerun()

with nav_col2:
    jump_to = st.number_input(
        "跳转到第几题：",
        min_value=1,
        max_value=total,
        value=idx + 1,
        step=1
    )

    if st.button("跳转"):
        st.session_state.current_index = int(jump_to) - 1
        st.session_state.finished = False
        st.rerun()

with nav_col3:
    button_label = "完成" if st.session_state.current_index == len(PAGES) - 1 else "保存并下一题 ➡️"

    if st.button(button_label):
        missing = [
            item["s_col"]
            for item in responses
            if item["answer"] is None
        ]

        if len(missing) > 0:
            st.warning(f"请先完成这些问题：{', '.join(missing)}")
        else:
            save_page_responses_fast(
                raw_ws=raw_ws,
                df=df,
                coder_id=coder,
                sentence_id=sentence_id,
                sentence=sentence,
                responses=responses,
                comment=comment
            )

            if st.session_state.current_index < len(PAGES) - 1:
                st.session_state.current_index += 1
            else:
                st.session_state.finished = True

            st.rerun()


st.divider()
st.subheader("Google Sheets 状态")

st.write("答案会自动保存到 Google Sheets。")
st.write("raw_data = 原始长表，每一行是一个 coder 对一个 S 片段的判断。")
st.write("kappa_format = 可用于计算 kappa 的宽表。")

if st.button("手动更新 kappa_format 表"):
    latest_df = read_raw_data_cached()
    update_kappa_format(kappa_ws, latest_df)
    st.success("kappa_format 已更新。")
