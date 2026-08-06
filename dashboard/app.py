# dashboard/app.py
# Streamlit Approval Center — Human-in-the-Loop Email Workflow Dashboard
#
# Pages:
#   1. Approval Center  — review, edit, approve, save draft, or reject
#   2. Analytics        — metrics and charts
#   3. Decision Timeline — placeholder (Phase 5)
#   4. Audit Log        — placeholder (Phase 5)
#
# Run:  streamlit run dashboard/app.py

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import sqlite3
from dotenv import load_dotenv

load_dotenv()

import workflow
from workflow import WorkflowStatus
from database.db_manager import (
    init_db, DB_PATH,
    get_emails, update_email_status,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Email Approval Center",
    page_icon="📬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Ensure schema exists before any DB call
init_db()

# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Status badge colours */
    .badge-PENDING           { background:#f59e0b; color:#fff; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
    .badge-DRAFT_SAVED       { background:#3b82f6; color:#fff; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
    .badge-GMAIL_DRAFT_SAVED { background:#8b5cf6; color:#fff; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
    .badge-APPROVED          { background:#10b981; color:#fff; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
    .badge-SENT              { background:#065f46; color:#fff; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
    .badge-REJECTED          { background:#ef4444; color:#fff; padding:2px 10px; border-radius:12px; font-size:0.8rem; font-weight:600; }
    /* Risk colours */
    .risk-LOW      { color:#10b981; font-weight:600; }
    .risk-MEDIUM   { color:#f59e0b; font-weight:600; }
    .risk-HIGH     { color:#ef4444; font-weight:600; }
    .risk-CRITICAL { color:#7f1d1d; font-weight:600; }
    /* Section divider */
    .section-divider { border-top: 1px solid #e5e7eb; margin: 1rem 0; }
    /* XAI card */
    .xai-card { background:#f9fafb; border-left:4px solid #6366f1; padding:0.75rem 1rem; border-radius:6px; margin-bottom:0.5rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar navigation
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("📬 AI Email Workflow")
st.sidebar.caption("Human-in-the-Loop Framework")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    ["📥 Approval Center", "📊 Analytics", "🕐 Decision Timeline", "📋 Audit Log"],
    label_visibility="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
STATUS_OPTIONS = ["All"] + [s.value for s in WorkflowStatus]
CATEGORY_OPTIONS = ["All", "IMPORTANT", "PROMOTION", "SOCIAL", "SPAM", "UPDATES", "UNKNOWN"]
RISK_OPTIONS = ["All", "LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"]

def status_badge(status: str) -> str:
    return f'<span class="badge-{status}">{status}</span>'

def risk_label(risk: str) -> str:
    return f'<span class="risk-{risk}">{risk}</span>'

def confidence_bar(value: float) -> str:
    pct = int((value or 0) * 100)
    color = "#10b981" if pct >= 70 else "#f59e0b" if pct >= 40 else "#ef4444"
    return (
        f'<div style="background:#e5e7eb;border-radius:6px;height:8px;width:100%">'
        f'<div style="background:{color};width:{pct}%;height:8px;border-radius:6px"></div></div>'
        f'<small style="color:#6b7280">{pct}% (Model Confidence Self-Assessment)</small>'
    )

def load_audit_log():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM audit_log ORDER BY timestamp DESC", conn)
    except Exception:
        df = pd.DataFrame(columns=["timestamp", "email_id", "actor", "action", "notes"])
    conn.close()
    return df

def load_decision_timeline():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM decision_timeline ORDER BY recorded_at DESC", conn)
    except Exception:
        df = pd.DataFrame(columns=["email_id", "event", "actor", "recorded_at"])
    conn.close()
    return df

# ─────────────────────────────────────────────────────────────────────────────
# Page 1 — Approval Center
# ─────────────────────────────────────────────────────────────────────────────
if page == "📥 Approval Center":
    st.title("📥 Approval Center")
    st.caption("Review AI-generated drafts. Edit, approve, save, or reject — the AI never sends automatically.")

    # ── Filters ───────────────────────────────────────────────────────────
    with st.expander("🔍 Search & Filter", expanded=True):
        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        search      = col1.text_input("Search (subject / sender / summary)", placeholder="Type to search…")
        status_f    = col2.selectbox("Status", STATUS_OPTIONS, index=0)
        category_f  = col3.selectbox("Category", CATEGORY_OPTIONS, index=0)
        risk_f      = col4.selectbox("Risk Level", RISK_OPTIONS, index=0)

        col5, col6 = st.columns([3, 3])
        sender_f    = col5.text_input("Sender contains", placeholder="@example.com")

    emails = get_emails(
        search=search,
        status_filter=status_f,
        category_filter=category_f,
        risk_filter=risk_f,
        sender_filter=sender_f,
    )

    if not emails:
        st.info("No emails match the current filters.")
        st.stop()

    # ── Email list ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader(f"Emails ({len(emails)} results)")

    # Build display table
    display_rows = []
    for e in emails:
        display_rows.append({
            "ID":        e.get("id", "")[:12] + "…",
            "From":      e.get("sender", "")[:40],
            "Subject":   e.get("subject", "")[:60],
            "Category":  e.get("category", ""),
            "Priority":  e.get("priority", "")[:20] if e.get("priority") else "",
            "Risk":      e.get("risk_level", ""),
            "Status":    e.get("status", ""),
            "Received":  (e.get("processed_at") or "")[:16],
        })

    df_display = pd.DataFrame(display_rows)
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ── Email detail ───────────────────────────────────────────────────────
    st.divider()
    subject_options = [f"{e.get('subject','(no subject)')} — {e.get('sender','')[:30]}"
                       for e in emails]
    selected_idx = st.selectbox("Select email to review", range(len(emails)),
                                format_func=lambda i: subject_options[i])
    email = emails[selected_idx]
    current_status = email.get("status", "PENDING") or "PENDING"

    # Header
    col_h1, col_h2 = st.columns([4, 1])
    col_h1.markdown(f"### {email.get('subject', '(no subject)')}")
    col_h2.markdown(status_badge(current_status), unsafe_allow_html=True)
    st.caption(f"**From:** {email.get('sender', '')}  •  **Received:** {(email.get('processed_at') or '')[:16]}")

    # ── XAI Panel ─────────────────────────────────────────────────────────
    with st.expander("🧠 AI Reasoning & Explainability", expanded=True):
        xc1, xc2, xc3 = st.columns(3)
        with xc1:
            st.markdown("**Category**")
            st.markdown(f"`{email.get('category','—')}`")
            st.markdown("**AI Confidence Estimate**")
            conf = email.get("ai_confidence_estimate") or 0.0
            st.markdown(confidence_bar(conf), unsafe_allow_html=True)
        with xc2:
            st.markdown("**Priority**")
            st.markdown(f"`{(email.get('priority') or '—').replace(chr(10), '  ')}`")
            st.markdown("**Risk Level**")
            st.markdown(risk_label(email.get("risk_level") or "UNKNOWN"), unsafe_allow_html=True)
        with xc3:
            st.markdown("**Suggested Tone**")
            st.markdown(f"`{email.get('suggested_tone') or '—'}`")
            st.markdown("**Reply Rationale**")
            st.markdown(f"*{email.get('reply_rationale') or '—'}*")

        st.markdown("**AI Reasoning**")
        st.markdown(
            f'<div class="xai-card">{email.get("reasoning") or "No reasoning available."}</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            "⚠️ AI Confidence Estimate is the model's self-assessed certainty. "
            "It is an explainability aid and must not be treated as a calibrated probability."
        )

    # ── Summary ────────────────────────────────────────────────────────────
    with st.expander("📋 AI Summary"):
        st.markdown(email.get("summary") or "*No summary available.*")

    # ── Draft reply editor ─────────────────────────────────────────────────
    st.markdown("### ✍️ Draft Reply")
    original_draft = email.get("draft_reply") or ""
    user_edited    = email.get("user_edited_reply") or original_draft

    edited_reply = st.text_area(
        "Edit the AI-generated draft before approving",
        value=user_edited,
        height=220,
        key=f"reply_editor_{email.get('id')}",
    )

    # Show diff if user has edited
    if edited_reply.strip() != original_draft.strip():
        with st.expander("🔄 Compare: AI Draft vs Your Edit"):
            dc1, dc2 = st.columns(2)
            dc1.markdown("**Original AI Draft**")
            dc1.markdown(f"```\n{original_draft}\n```")
            dc2.markdown("**Your Edited Version**")
            dc2.markdown(f"```\n{edited_reply}\n```")

    # ── Action buttons ─────────────────────────────────────────────────────
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("**Action — Human Decision Required**")

    can_approve = current_status in [WorkflowStatus.PENDING, WorkflowStatus.DRAFT_SAVED,
                                     WorkflowStatus.GMAIL_DRAFT_SAVED]
    can_draft   = current_status == WorkflowStatus.PENDING
    can_reject  = current_status in [WorkflowStatus.PENDING, WorkflowStatus.DRAFT_SAVED,
                                     WorkflowStatus.GMAIL_DRAFT_SAVED]

    btn_col1, btn_col2, btn_col3, btn_col4, _ = st.columns([2, 2, 2, 2, 1])

    # Compute to_email once for all buttons that need it
    sender_raw = email.get("sender", "")
    to_email   = sender_raw.split("<")[-1].replace(">", "").strip() if "<" in sender_raw else sender_raw
    subject    = email.get("subject", "")

    with btn_col1:
        if can_approve:
            if st.button("✅ Approve & Send", type="primary",
                         use_container_width=True, key=f"approve_{email['id']}"):
                try:
                    workflow.approve_and_send(email["id"], edited_reply, from_status=current_status)
                    st.success("✅ Approved and sent! Status → SENT.")
                    st.rerun()
                except RuntimeError as exc:
                    # Send failed — parked at APPROVED, user can retry
                    st.warning(str(exc))
                    st.rerun()
                except Exception as exc:
                    st.error(f"Unexpected error: {exc}")
        else:
            st.button("✅ Approve & Send", disabled=True, use_container_width=True)

    with btn_col2:
        if can_draft:
            if st.button("💾 Save Draft", use_container_width=True, key=f"draft_{email['id']}"):
                try:
                    update_email_status(email["id"], current_status, user_edited_reply=edited_reply)
                    workflow.save_as_draft(email["id"], from_status=current_status)
                    st.success("💾 Draft saved.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")
        else:
            st.button("💾 Save Draft", disabled=True, use_container_width=True)

    with btn_col3:
        can_gmail_draft = current_status in [WorkflowStatus.PENDING, WorkflowStatus.DRAFT_SAVED]
        if can_gmail_draft:
            if st.button("📤 Push to Gmail Drafts", use_container_width=True,
                         key=f"gmail_draft_{email['id']}"):
                try:
                    update_email_status(email["id"], current_status, user_edited_reply=edited_reply)
                    draft_id = workflow.push_to_gmail_drafts(
                        email["id"], to_email, subject, edited_reply,
                        from_status=current_status,
                    )
                    st.success(f"📤 Pushed to Gmail Drafts (ID: {draft_id}).")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Gmail Draft error: {exc}")
        else:
            st.button("📤 Push to Gmail Drafts", disabled=True, use_container_width=True)

    with btn_col4:
        if can_reject:
            reject_reason = st.text_input("Reason (optional)",
                                          key=f"reject_reason_{email['id']}",
                                          placeholder="Rejection reason…",
                                          label_visibility="collapsed")
            if st.button("❌ Reject", use_container_width=True, key=f"reject_{email['id']}"):
                try:
                    workflow.reject(email["id"], reason=reject_reason, from_status=current_status)
                    st.success("❌ Rejected.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")
        else:
            st.button("❌ Reject", disabled=True, use_container_width=True)

    if not (can_approve or can_draft or can_reject):
        st.info(f"This email is in a terminal state: **{current_status}**. No further actions available.")


# ─────────────────────────────────────────────────────────────────────────────
# Page 2 — Analytics
# ─────────────────────────────────────────────────────────────────────────────
elif page == "📊 Analytics":
    st.title("📊 Analytics")

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM processed_emails", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()

    if df.empty:
        st.info("No email data yet. Run the pipeline to process emails.")
        st.stop()

    # ── Top metrics ────────────────────────────────────────────────────────
    total     = len(df)
    pending   = len(df[df["status"] == "PENDING"])   if "status" in df.columns else 0
    approved  = len(df[df["status"] == "APPROVED"])  if "status" in df.columns else 0
    rejected  = len(df[df["status"] == "REJECTED"])  if "status" in df.columns else 0
    sent      = len(df[df["status"] == "SENT"])       if "status" in df.columns else 0
    important = len(df[df["category"] == "IMPORTANT"]) if "category" in df.columns else 0

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Emails",    total)
    m2.metric("⏳ Pending",       pending)
    m3.metric("✅ Approved",      approved)
    m4.metric("❌ Rejected",      rejected)
    m5.metric("📤 Sent",          sent)
    m6.metric("🔴 Important",     important)

    st.divider()

    # ── Charts ─────────────────────────────────────────────────────────────
    ch1, ch2 = st.columns(2)

    with ch1:
        st.subheader("Emails by Category")
        if "category" in df.columns and not df["category"].isnull().all():
            cat_counts = df["category"].value_counts().reset_index()
            cat_counts.columns = ["Category", "Count"]
            st.bar_chart(cat_counts.set_index("Category"))
        else:
            st.info("No category data.")

    with ch2:
        st.subheader("Workflow Status Distribution")
        if "status" in df.columns and not df["status"].isnull().all():
            st.bar_chart(df["status"].value_counts())
        else:
            st.info("No status data.")

    ch3, ch4 = st.columns(2)

    with ch3:
        st.subheader("Risk Level Distribution")
        if "risk_level" in df.columns and not df["risk_level"].isnull().all():
            st.bar_chart(df["risk_level"].value_counts())
        else:
            st.info("No risk data.")

    with ch4:
        st.subheader("AI Confidence Estimate Distribution")
        if "ai_confidence_estimate" in df.columns:
            conf_data = df["ai_confidence_estimate"].dropna()
            if not conf_data.empty:
                st.caption("Self-assessed model confidence — explainability aid only.")
                st.bar_chart(conf_data.apply(lambda x: round(x * 10) * 10).value_counts().sort_index())
            else:
                st.info("No confidence data.")
        else:
            st.info("No confidence data.")

    st.divider()
    st.subheader("All Emails")
    cols_to_show = [c for c in ["processed_at", "sender", "subject", "category",
                                 "status", "risk_level", "ai_confidence_estimate"]
                    if c in df.columns]
    st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Page 3 — Decision Timeline
# ─────────────────────────────────────────────────────────────────────────────
elif page == "🕐 Decision Timeline":
    st.title("🕐 Decision Timeline")
    df = load_decision_timeline()

    if df.empty:
        st.info(
            "No timeline events yet.\n\n"
            "Events populate automatically as emails move through the workflow "
            "(approve, reject, save draft, send)."
        )
    else:
        # Show most recent first; highlight per-email with expanders
        for email_id in df["email_id"].unique():
            sub = df[df["email_id"] == email_id].reset_index(drop=True)
            label = f"📧 {email_id[:16]}… — {len(sub)} events"
            with st.expander(label):
                st.dataframe(sub[["created_at", "event", "actor", "note"]],
                             use_container_width=True, hide_index=True)



# ─────────────────────────────────────────────────────────────────────────────
# Page 4 — Audit Log
# ─────────────────────────────────────────────────────────────────────────────
elif page == "📋 Audit Log":
    st.title("📋 Audit Log")
    df = load_audit_log()

    if df.empty:
        st.info(
            "No audit events yet.\n\n"
            "The Audit Log populates automatically as the workflow runs. "
            "Every AI and human action is recorded here."
        )
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption(
        "All AI and human actions are permanently logged here "
        "for transparency, reproducibility, and HITL audit compliance."
    )
