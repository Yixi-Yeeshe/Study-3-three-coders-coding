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
    "D. 肥胖结果描述 obesity consequences"
]

S_COLUMNS = [f"S{i}" for i in range(1, 9)]

st.set_page_config(page_title="Study 3 Coding", layout="wide")
st.title("Study 3 Coding Task")


@st.cache_data
def load_questions_from_csv(file_path):
    df = pd.read_csv(file_path)

    required_cols = ["ID", "Sentence"] + S_COLUMNS

    for col in required_cols:
        if col not in df.columns:
            st.error(f"Excel 文件缺少必要列：{col}")
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


def get_or_create_ws(sheet, name, rows=1000, cols=50):
    try:
        return sheet.worksheet(name)
    except gspread.WorksheetNotFound:
        return sheet.add_worksheet(title=name, rows=rows, cols=cols)


def read_raw_data(raw_ws):
    records = raw_ws.get_all_records()

    required_cols = [
        "coder_id",
        "sentence_id",
        "s_col",
        "sentence",
        "question",
        "answer",
        "comment",
        "updated_at"
    ]

    if not records:
        return pd.DataFrame(columns=required_cols)

    df = pd.DataFrame(records)

    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    df = df[required_cols]
    df = df.fillna("")

    return df


def write_raw_data(raw_ws, df):
    raw_ws.clear()

    header = [
        "coder_id",
        "sentence_id",
        "s_col",
        "sentence",
        "question",
        "answer",
        "comment",
        "updated_at"
    ]

    if df.empty:
        raw_ws.update([header])
    else:
        df = df.fillna("")
        raw_ws.update(
            [df.columns.tolist()] + df.astype(str).values.tolist()
        )


def update_kappa_format(kappa_ws, df):
    kappa_ws.clear()

    if df.empty:
        kappa_ws.update([["sentence_id", "s_col", "question"]])
        return

    df = df.fillna("")

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


def save_page_responses(
    raw_ws,
    kappa_ws,
    df,
    coder_id,
    sentence_id,
    sentence,
    responses,
    comment
):
    updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not df.empty:
        mask = (
            (df["coder_id"].astype(str) == str(coder_id)) &
            (df["sentence_id"].astype(str) == str(sentence_id))
        )
        df = df[~mask]

    new_rows = []

    for item in responses:
        new_rows.append({
            "coder_id": coder_id,
            "sentence_id": sentence_id,
            "s_col": item["s_col"],
            "sentence": sentence,
            "question": item["question"],
            "answer": item["answer"],
            "comment": comment,
            "updated_at": updated_at
        })

    df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    df = df.fillna("")
    df = df.sort_values(["sentence_id", "s_col", "coder_id"])

    write_raw_data(raw_ws, df)
    update_kappa_format(kappa_ws, df)


PAGES = load_questions_from_csv(DATA_PATH)

if len(PAGES) == 0:
    st.error("Excel 中没有可用题目。请检查 ID、sentence、S1-S8 是否有内容。")
    st.stop()


sheet = connect_sheet()
raw_ws = get_or_create_ws(sheet, RAW_SHEET)
kappa_ws = get_or_create_ws(sheet, KAPPA_SHEET)

df = read_raw_data(raw_ws)


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
st.info("点击“下一题”会自动保存本页所有答案。下次输入同一个 coder ID，会自动回到你上次停止的位置。")


coder_df = df[df["coder_id"].astype(str) == coder]

if not coder_df.empty:
    completed_sentence_ids = set(coder_df["sentence_id"].astype(str).tolist())
else:
    completed_sentence_ids = set()

total = len(PAGES)
done = len(completed_sentence_ids)

st.progress(done / total)
st.write(f"进度：{done}/{total}")


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

for _, row in existing_page_answers.iterrows():
    existing_answer_dict[str(row["s_col"])] = str(row["answer"])

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
    key=f"{coder}_{sentence_id}_comment"
)


prev_col, next_col = st.columns([1, 1])

with prev_col:
    if st.button("⬅️ 上一题"):
        st.session_state.finished = False
        if st.session_state.current_index > 0:
            st.session_state.current_index -= 1
            st.rerun()

with next_col:
    button_label = "完成" if st.session_state.current_index == len(PAGES) - 1 else "下一题 ➡️"

    if st.button(button_label):
        missing = [
            item["s_col"]
            for item in responses
            if item["answer"] is None
        ]

        if len(missing) > 0:
            st.warning(f"请先完成这些问题：{', '.join(missing)}")
        else:
            save_page_responses(
                raw_ws=raw_ws,
                kappa_ws=kappa_ws,
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
