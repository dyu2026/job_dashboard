import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta, timezone

# -----------------------------------
# Supabase Setup
# -----------------------------------

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Job Dashboard", layout="wide")
st.title("🧭 Job Intelligence Dashboard")

# -----------------------------------
# Sidebar Filters
# -----------------------------------

st.sidebar.header("Filters")

remote_only = st.sidebar.checkbox("🌍 Remote Only")
japan_only = st.sidebar.checkbox("🇯🇵 Japan Only")
focus_roles = st.sidebar.checkbox(
    "🎯 Focus Roles (Product / Web / eCommerce / Localization / Globalization / Experience / Operations)"
)

# -----------------------------------
# Fetch Data
# -----------------------------------

response = supabase.table("jobs") \
    .select("*") \
    .eq("is_active", True) \
    .execute()
data = response.data

if not data:
    st.warning("No jobs found in database.")
    st.stop()

df = pd.DataFrame(data)

# -----------------------------------
# Cleanup & Formatting
# -----------------------------------

df["first_seen_at"] = pd.to_datetime(df["first_seen_at"], errors="coerce")
df["last_seen_at"] = pd.to_datetime(df["last_seen_at"], errors="coerce")

now_utc = datetime.now(timezone.utc)
last_24 = now_utc - timedelta(hours=24)
today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

df["is_new_24h"] = df["first_seen_at"] >= last_24
df["is_new_today"] = df["first_seen_at"] >= today_start

# -----------------------------------
# Apply Filters
# -----------------------------------

if remote_only:
    df = df[df["is_remote"] == True]

if japan_only:
    df = df[df["is_japan"] == True]

if focus_roles:
    keywords = [
        "product",
        "web",
        "ecommerce",
        "localization",
        "globalization",
        "experience",
        "operations",
    ]
    pattern = "|".join(keywords)
    df = df[df["title"].str.contains(pattern, case=False, na=False)]

if df.empty:
    st.warning("No jobs match filters.")
    st.stop()

# -----------------------------------
# 🔥 Metrics Row
# -----------------------------------

col1, col2, col3 = st.columns(3)

col1.metric("Total Jobs", len(df))
col2.metric("🔥 New (24h)", df["is_new_24h"].sum())
col3.metric("🆕 New Today (UTC)", df["is_new_today"].sum())

st.divider()

# -----------------------------------
# 📊 Company Breakdown
# -----------------------------------

st.subheader("📊 Company Breakdown")

company_stats = (
    df.groupby("company")
    .agg(
        total_jobs=("title", "count"),
        new_24h=("is_new_24h", "sum"),
    )
    .sort_values("total_jobs", ascending=False)
    .reset_index()
)

st.dataframe(company_stats, use_container_width=True)

st.divider()

# -----------------------------------
# 🔥 New Jobs Section
# -----------------------------------

st.subheader("🔥 New Jobs (Last 24 Hours)")

# Badge column
df["New"] = df["is_new_24h"].apply(lambda x: "🔥 NEW" if x else "")
df["first_seen_at"] = df["first_seen_at"].dt.strftime("%Y-%m-%d %H:%M")

display_cols = [
    "New",
    "company",
    "title",
    "location",
    "url",
    "seniority",
    "function",
    "first_seen_at",
]

new_jobs = df[df["is_new_24h"]]

if new_jobs.empty:
    st.info("No new jobs in last 24 hours.")
else:
    st.dataframe(
        new_jobs[display_cols].sort_values(
            "first_seen_at", ascending=False
        ),
        column_config={
            "url": st.column_config.LinkColumn("Apply", display_text="Open")
        },
        use_container_width=True,
    )

st.divider()

# -----------------------------------
# Recently removed
# -----------------------------------

st.subheader("🗑 Recently Removed Jobs")

removed = supabase.table("jobs") \
    .select("*") \
    .eq("is_active", False) \
    .gte("last_seen_at", last_24.isoformat()) \
    .execute()

removed_df = pd.DataFrame(removed.data)

if not removed_df.empty:
    st.dataframe(removed_df)

st.divider()

# -----------------------------------
# 🔎 Search
# -----------------------------------

st.subheader("🔎 Search Jobs")

search = st.text_input("Search title, company, location")

if search:
    df = df[
        df["title"].str.contains(search, case=False, na=False)
        | df["company"].str.contains(search, case=False, na=False)
        | df["location"].str.contains(search, case=False, na=False)
    ]

# -----------------------------------
# 🧠 Main Job Table (With Highlight)
# -----------------------------------

st.subheader("📋 All Jobs")

st.dataframe(
    df[display_cols].sort_values(
        "first_seen_at", ascending=False
    ),
    column_config={
        "url": st.column_config.LinkColumn("Apply", display_text="Open")
    },
    use_container_width=True,
)



