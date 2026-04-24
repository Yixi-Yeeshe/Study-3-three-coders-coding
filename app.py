import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

DB_FILE = "coding_responses_demo.db"
EXPORT_FILE = "coding_responses_demo_export.xlsx"

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
    "1. 全身比例型描述",
    "2. 全身与他人做比较描述",
    "3. 局部身体描述",
    "4. 面部/脸部描述",
    "5. 发福/变胖描述",
    "6. 体型大小描述",
    "7. 身材变化描述",
    "8. 否定式肥胖描述",
    "9. 委婉/中性描述",
    "10. 负面评价描述",
    "11. 夸张/戏剧化描述",
    "12. 隐喻/比喻描述",
    "13. 动物化/物化描述",
    "14. 年龄化描述",
    "15. 性别化描述",
    "16. 健康风险描述",
    "17. 医学/疾病描述",
    "18. 审美/外貌描述",
    "19. 不确定",
    "20. 其他"
]

st.set_page_config(page_title="Coding Demo", layout="wide")
st.title("Coding Demo")

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS responses (
    coder_id TEXT,
    item_id INTEGER,
    question TEXT,
    answer TEXT,
    comment TEXT,
    updated_at TEXT,
    PRIMARY KEY (coder_id, item_id)
)
""")
conn.commit()

coder_id = st.text_input("请输入你的 coder ID：", placeholder="例如 CoderA")

if not coder_id:
    st.info("请输入 coder ID 后开始。")
    st.stop()

coder_id = coder_id.strip()
st.write(f"Current coder: **{coder_id}**")

questions_df = pd.DataFrame(QUESTIONS)

existing = pd.read_sql_query(
    "SELECT * FROM responses WHERE coder_id = ?",
    conn,
    params=(coder_id,)
)

completed_ids = set(existing["item_id"].tolist())
total = len(questions_df)
done = len(completed_ids)

st.progress(done / total)
st.write(f"Progress: {done}/{total}")

remaining = questions_df[~questions_df["item_id"].isin(completed_ids)]

if len(remaining) == 0:
    st.success("你已经完成全部问题。")

else:
    current_row = remaining.iloc[0]
    item_id = int(current_row["item_id"])
    question_text = current_row["question"]

    st.subheader(f"Question {item_id}")
    st.write(question_text)

    st.write("请选择一个选项：")

    option_groups = [OPTIONS[i::3] for i in range(3)]
    cols = st.columns(3)

    answers = []

    for i, col in enumerate(cols):
        ans = col.radio(
            label=f"选项列 {i + 1}",
            options=option_groups[i],
            index=None,
            key=f"q{item_id}_group_{i}",
            label_visibility="collapsed"
        )
        answers.append(ans)

    selected = [a for a in answers if a is not None]
    answer = selected[0] if selected else None

    comment = st.text_area("备注（可选）：")

    if st.button("保存并进入下一题"):
        if answer is None:
            st.warning("请先选择一个选项。")
        elif len(selected) > 1:
            st.warning("你选择了多个选项，请只保留一个。")
        else:
            cur.execute("""
            INSERT OR REPLACE INTO responses
            (coder_id, item_id, question, answer, comment, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                coder_id,
                item_id,
                question_text,
                answer,
                comment,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            st.rerun()

st.divider()
st.subheader("导出结果")

if st.button("导出全部结果到 Excel"):
    all_data = pd.read_sql_query(
        "SELECT * FROM responses ORDER BY item_id, coder_id",
        conn
    )

    # 原始长表：每一行是一个 coder 对一个问题的回答
    long_output = all_data.copy()

    # 转成 kappa 需要的宽表：每一行一个问题，每一列一个 coder
    wide_output = all_data.pivot_table(
        index=["item_id", "question"],
        columns="coder_id",
        values="answer",
        aggfunc="first"
    ).reset_index()

    # 去掉 columns 的层级名
    wide_output.columns.name = None

    # 导出两个 sheet
    with pd.ExcelWriter(EXPORT_FILE, engine="openpyxl") as writer:
        wide_output.to_excel(writer, sheet_name="kappa_format", index=False)
        long_output.to_excel(writer, sheet_name="raw_data", index=False)

    st.success(f"已导出：{EXPORT_FILE}")
