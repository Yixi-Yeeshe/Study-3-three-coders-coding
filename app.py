



import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

RAW_SHEET = "raw_data"
KAPPA_SHEET = "kappa_format"

QUESTIONS = [
    {
        "item_id": 1,
        "question": '''问题1 (Question 1)

"没错，自从来到澳洲，不管男女老少，不管身材如何，都逃不过澳洲的“变胖诅咒”……来澳洲前从不怎么注意自己的体重，因为基本没什么大变化。而来澳洲后，每日三省吾身，为什么我的脸在屏幕上越来越看不全了。"

P1：“脸在屏幕上越来越看不全” 属于（）'''
    },
    {
        "item_id": 2,
        "question": '''问题2 (Question 2)

"来到澳洲以后，很多人控制不住地“肿了”。澳洲仿佛有一种魔力，很多人来到这里，慢慢地就会控制不住胖了。"

P2：“肿了” 属于（）'''
    }
]

OPTIONS = [
    "1. 全身比例型描述 (whole-body proportion description)",
    "2. 全身与他人做比较描述 (whole-body comparison with others)",
    "3. 局部身体描述 (specific body part description)",
    "4. 面部/脸部描述 (facial description)",
    "5. 发福/变胖描述 (getting fat / weight gain description)",
    "6. 体型大小描述 (body size description)",
    "7. 身材变化描述 (body shape change description)",
    "8. 否定式肥胖描述 (negated obesity description)",
    "9. 委婉/中性描述 (euphemistic / neutral description)",
    "10. 负面评价描述 (negative evaluation)",
    "11. 夸张/戏剧化描述 (exaggerated / dramatic description)",
    "12. 隐喻/比喻描述 (metaphorical description)",
    "13. 动物化/物化描述 (animalistic / objectifying description)",
    "14. 年龄化描述 (age-related description)",
    "15. 性别化描述 (gendered description)",
    "16. 健康风险描述 (health risk description)",
    "17. 医学/疾病描述 (medical / disease-related description)",
    "18. 审美/外貌描述 (aesthetic / appearance-based description)",
    "19. 不确定 (uncertain)",
    "20. 其他 (other)"
]

st.set_page_config(page_title="Study 3 Coding", layout="wide")
st.title("Study 3 Coding Task")

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

    if not records:
        return pd.DataFrame(
            columns=[
                "coder_id",
                "item_id",
                "question",
                "answer",
                "comment",
                "updated_at"
            ]
        )

    df = pd.DataFrame(records)

    required_cols = [
        "coder_id",
        "item_id",
        "question",
        "answer",
        "comment",
        "updated_at"
    ]

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
        "item_id",
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
        kappa_ws.update([["item_id", "question"]])
        return

    df = df.fillna("")

    wide = df.pivot_table(
        index=["item_id", "question"],
        columns="coder_id",
        values="answer",
        aggfunc="first"
    ).reset_index()

    wide.columns.name = None
    wide = wide.fillna("")
    wide["item_id"] = wide["item_id"].astype(int)
    wide = wide.sort_values("item_id")

    kappa_ws.update(
        [wide.columns.tolist()] + wide.astype(str).values.tolist()
    )

def save_response(raw_ws, kappa_ws, df, coder_id, item_id, question, answer, comment):
    new_row = {
        "coder_id": coder_id,
        "item_id": item_id,
        "question": question,
        "answer": answer,
        "comment": comment,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    if not df.empty:
        mask = (
            (df["coder_id"].astype(str) == str(coder_id)) &
            (df["item_id"].astype(str) == str(item_id))
        )
        df = df[~mask]

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = df.fillna("")
    df["item_id"] = df["item_id"].astype(int)
    df = df.sort_values(["item_id", "coder_id"])

    write_raw_data(raw_ws, df)
    update_kappa_format(kappa_ws, df)

# Connect to Google Sheets
sheet = connect_sheet()
raw_ws = get_or_create_ws(sheet, RAW_SHEET)
kappa_ws = get_or_create_ws(sheet, KAPPA_SHEET)

df = read_raw_data(raw_ws)

coder = st.text_input(
    "请输入你的 coder ID： (Enter your coder ID)",
    placeholder="例如 CoderA / CoderB / CoderC"
)

if not coder:
    st.info("请输入 coder ID 后开始。 (Please enter coder ID to start.)")
    st.stop()

coder = coder.strip().lower()

st.write(f"Current coder: **{coder}**")
st.info("每完成一题请点击保存。下次输入同一个 coder ID，会自动回到你上次停止的位置。(Progress will be saved automatically.)")

coder_df = df[df["coder_id"].astype(str) == coder]

completed_ids = set(coder_df["item_id"].astype(int).tolist()) if not coder_df.empty else set()

total = len(QUESTIONS)
done = len(completed_ids)

st.progress(done / total)
st.write(f"进度：{done}/{total} (Progress)")

if "current_coder" not in st.session_state or st.session_state.current_coder != coder:
    st.session_state.current_coder = coder
    st.session_state.current_index = next(
        (i for i, q_item in enumerate(QUESTIONS) if q_item["item_id"] not in completed_ids),
        0
    )

if "current_index" not in st.session_state:
    st.session_state.current_index = 0

idx = st.session_state.current_index
q = QUESTIONS[idx]

st.subheader(f"Question {idx + 1} of {total}")
st.write(q["question"])

existing_answer = df[
    (df["coder_id"].astype(str) == coder) &
    (df["item_id"].astype(str) == str(q["item_id"]))
]

default_answer = existing_answer.iloc[0]["answer"] if not existing_answer.empty else None
default_comment = existing_answer.iloc[0]["comment"] if not existing_answer.empty else ""

st.write("请选择一个选项： (Select one option)")

answers = []
cols = st.columns(3)
option_groups = [OPTIONS[i::3] for i in range(3)]

for i, col in enumerate(cols):
    group = option_groups[i]
    default_index = group.index(default_answer) if default_answer in group else None

    ans = col.radio(
        label=f"选项列 {i + 1}",
        options=group,
        index=default_index,
        key=f"{coder}_{q['item_id']}_group_{i}",
        label_visibility="collapsed"
    )

    if ans:
        answers.append(ans)

selected_unique = list(dict.fromkeys(answers))

comment = st.text_area(
    "备注（可选）： (Comment, optional)",
    value=default_comment
)

if st.button("保存当前题 (Save)"):
    if len(selected_unique) != 1:
        st.warning("请选择一个选项 (Please select exactly one option).")
    else:
        save_response(raw_ws, kappa_ws, df, coder, q["item_id"], q["question"], selected_unique[0], comment)
        st.success("已保存 (Saved)")
        st.session_state.current_index += 1
        st.rerun()
如果你下一步想更“学术一点”（比如统一术语、对接你的论文 coding frame），我可以帮你把这些英文再标准化成 publication-ready version。

其它都不变，你怎么去掉了上一题 下一题呢

import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

RAW_SHEET = "raw_data"
KAPPA_SHEET = "kappa_format"

QUESTIONS = [
{
"item_id": 1,
"question": '''问题1

"没错，自从来到澳洲，不管男女老少，不管身材如何，都逃不过澳洲的“变胖诅咒”……来澳洲前从不怎么注意自己的体重，因为基本没什么大变化。而来澳洲后，每日三省吾身，为什么我的脸在屏幕上越来越看不全了。"

P1：“脸在屏幕上越来越看不全” 属于（）'''
},
{
"item_id": 2,
"question": '''问题2

"来到澳洲以后，很多人控制不住地“肿了”。澳洲仿佛有一种魔力，很多人来到这里，慢慢地就会控制不住胖了。"

P2：“肿了” 属于（）'''
}
]

OPTIONS = [
 "1. 全身比例型描述 (whole-body proportion description)",
    "2. 全身与他人做比较描述 (whole-body comparison with others)",
    "3. 局部身体描述 (specific body part description)",
    "4. 面部/脸部描述 (facial description)",
    "5. 发福/变胖描述 (getting fat / weight gain description)",
    "6. 体型大小描述 (body size description)",
    "7. 身材变化描述 (body shape change description)",
    "8. 否定式肥胖描述 (negated obesity description)",
    "9. 委婉/中性描述 (euphemistic / neutral description)",
    "10. 负面评价描述 (negative evaluation)",
    "11. 夸张/戏剧化描述 (exaggerated / dramatic description)",
    "12. 隐喻/比喻描述 (metaphorical description)",
    "13. 动物化/物化描述 (animalistic / objectifying description)",
    "14. 年龄化描述 (age-related description)",
    "15. 性别化描述 (gendered description)",
    "16. 健康风险描述 (health risk description)",
    "17. 医学/疾病描述 (medical / disease-related description)",
    "18. 审美/外貌描述 (aesthetic / appearance-based description)",
    "19. 不确定 (uncertain)",
    "20. 其他 (other)"
]

st.set_page_config(page_title="Study 3 Coding", layout="wide")
st.title("Study 3 Coding Task")

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

if not records:
    return pd.DataFrame(
        columns=[
            "coder_id",
            "item_id",
            "question",
            "answer",
            "comment",
            "updated_at"
        ]
    )

df = pd.DataFrame(records)

required_cols = [
    "coder_id",
    "item_id",
    "question",
    "answer",
    "comment",
    "updated_at"
]

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
    "item_id",
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
    kappa_ws.update([["item_id", "question"]])
    return

df = df.fillna("")

wide = df.pivot_table(
    index=["item_id", "question"],
    columns="coder_id",
    values="answer",
    aggfunc="first"
).reset_index()

wide.columns.name = None
wide = wide.fillna("")
wide["item_id"] = wide["item_id"].astype(int)
wide = wide.sort_values("item_id")

kappa_ws.update(
    [wide.columns.tolist()] + wide.astype(str).values.tolist()
)
def save_response(raw_ws, kappa_ws, df, coder_id, item_id, question, answer, comment):
new_row = {
"coder_id": coder_id,
"item_id": item_id,
"question": question,
"answer": answer,
"comment": comment,
"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
}

if not df.empty:
    mask = (
        (df["coder_id"].astype(str) == str(coder_id)) &
        (df["item_id"].astype(str) == str(item_id))
    )
    df = df[~mask]

df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
df = df.fillna("")
df["item_id"] = df["item_id"].astype(int)
df = df.sort_values(["item_id", "coder_id"])

write_raw_data(raw_ws, df)
update_kappa_format(kappa_ws, df)
Connect to Google Sheets
sheet = connect_sheet()
raw_ws = get_or_create_ws(sheet, RAW_SHEET)
kappa_ws = get_or_create_ws(sheet, KAPPA_SHEET)

df = read_raw_data(raw_ws)

Coder ID
coder = st.text_input(
"请输入你的 coder ID：",
placeholder="例如 CoderA / CoderB / CoderC"
)

if not coder:
st.info("请输入 coder ID 后开始。")
st.stop()

coder = coder.strip().lower()

st.write(f"Current coder: {coder}")
st.info("每完成一题请点击保存。下次输入同一个 coder ID，会自动回到你上次停止的位置。")

Completed items for this coder
coder_df = df[df["coder_id"].astype(str) == coder]

if not coder_df.empty:
completed_ids = set(coder_df["item_id"].astype(int).tolist())
else:
completed_ids = set()

total = len(QUESTIONS)
done = len(completed_ids)

st.progress(done / total)
st.write(f"进度：{done}/{total}")

Set starting question: first incomplete question
if "current_coder" not in st.session_state or st.session_state.current_coder != coder:
st.session_state.current_coder = coder

first_incomplete_index = 0
for i, q_item in enumerate(QUESTIONS):
    if q_item["item_id"] not in completed_ids:
        first_incomplete_index = i
        break

st.session_state.current_index = first_incomplete_index
if "current_index" not in st.session_state:
st.session_state.current_index = 0

idx = st.session_state.current_index
idx = max(0, min(idx, len(QUESTIONS) - 1))
st.session_state.current_index = idx

q = QUESTIONS[idx]
item_id = int(q["item_id"])
question_text = q["question"]

st.divider()
st.subheader(f"Question {idx + 1} of {total}")
st.write(question_text)

Existing answer
existing_answer = df[
(df["coder_id"].astype(str) == coder) &
(df["item_id"].astype(str) == str(item_id))
]

default_answer = None
default_comment = ""

if not existing_answer.empty:
default_answer = existing_answer.iloc[0]["answer"]
default_comment = existing_answer.iloc[0]["comment"]

st.write("请选择一个选项：")

option_groups = [OPTIONS[i::3] for i in range(3)]
cols = st.columns(3)

answers = []

for i, col in enumerate(cols):
group = option_groups[i]

if default_answer in group:
    default_index = group.index(default_answer)
else:
    default_index = None

ans = col.radio(
    label=f"选项列 {i + 1}",
    options=group,
    index=default_index,
    key=f"{coder}_{item_id}_group_{i}",
    label_visibility="collapsed"
)

if ans is not None:
    answers.append(ans)
selected_unique = list(dict.fromkeys(answers))

comment = st.text_area(
"备注（可选）：",
value=default_comment,
key=f"{coder}_{item_id}_comment"
)

save_col, prev_col, next_col = st.columns([2, 1, 1])

with save_col:
if st.button("保存当前题"):
if len(selected_unique) == 0:
st.warning("请先选择一个选项。")
elif len(selected_unique) > 1:
st.warning("你选择了多个选项。请只保留一个。")
else:
save_response(
raw_ws=raw_ws,
kappa_ws=kappa_ws,
df=df,
coder_id=coder,
item_id=item_id,
question=question_text,
answer=selected_unique[0],
comment=comment
)

        st.success("已保存。")

        if st.session_state.current_index < len(QUESTIONS) - 1:
            st.session_state.current_index += 1

        st.rerun()
with prev_col:
if st.button("⬅️ 上一题"):
if st.session_state.current_index > 0:
st.session_state.current_index -= 1
st.rerun()

with next_col:
if st.button("下一题 ➡️"):
if st.session_state.current_index < len(QUESTIONS) - 1:
st.session_state.current_index += 1
st.rerun()

st.divider()
st.subheader("Google Sheets 状态")

st.write("答案会自动保存到 Google Sheets。")
st.write("raw_data = 原始长表")
st.write("kappa_format = 可用于计算 kappa 的宽表")


Close
