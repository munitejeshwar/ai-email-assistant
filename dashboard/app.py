import streamlit as st
import sqlite3
import pandas as pd

st.set_page_config(page_title="AI Email Assistant", layout="wide")

st.title(" AI Email Assistant Dashboard")

# =====================================================
# DATABASE
# =====================================================

conn = sqlite3.connect("emails.db")

query = """
SELECT *
FROM processed_emails
ORDER BY processed_at DESC
"""

df = pd.read_sql_query(query, conn)

conn.close()

# =====================================================
# METRICS
# =====================================================

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Total Emails", len(df))

with col2:
    important_count = len(df[df["category"] == "IMPORTANT"])

    st.metric("Important Emails", important_count)

with col3:
    spam_count = len(df[df["category"] == "SPAM"])

    st.metric("Spam Emails", spam_count)

# =====================================================
# EMAIL TABLE
# =====================================================

st.subheader("Processed Emails")

st.dataframe(df, use_container_width=True)

# =====================================================
# EMAIL DETAILS
# =====================================================

st.subheader("Email Details")

if len(df) > 0:

    selected_subject = st.selectbox("Choose Email", df["subject"])

    selected_email = df[df["subject"] == selected_subject].iloc[0]

    st.markdown("###  Sender")
    st.write(selected_email["sender"])

    st.markdown("###  Category")
    st.write(selected_email["category"])

    st.markdown("###  Priority")
    st.write(selected_email["priority"])

    st.markdown("###  AI Summary")
    st.write(selected_email["summary"])
