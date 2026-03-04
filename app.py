import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta, timezone

# -----------------------------------
# Page Config
# -----------------------------------

st.set_page_config(page_title="Job Intelligence Dashboard", layout="wide")
st.title("🧭 Job Intelligence Dashboard")

# -----------------------------------
# Supabase Setup
# -----------------------------------

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------------
# Fetch Data
# -----------------------------------

response = (
    supabase.table("jobs")
    .select("*")
    .eq("is_active", True)
    .execute()
)

data = response.data

if not data:
    st.warning("No jobs found in database.")
    st.stop()

df = pd.DataFrame(data)

# -----------------------------------
# Cleanup & Time Logic
# -----------------------------------

df["first_seen_at"] = pd.to_datetime(df["first_seen_at"], errors="coerce")
df["last_seen_at"] = pd.to_datetime(df["last_seen_at"], errors="coerce")

now_utc = datetime.now(timezone.utc)
last_24 = now_utc - timedelta(hours=24)
today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

df["is_new_24h"] = df["first_seen_at"] >= last_24
df["is_new_today"] = df["first_seen_at"] >= today_start

# -----------------------------------
# Sidebar Filters
# -----------------------------------

st.sidebar.header("Filters")

# Remote
remote_only = st.sidebar.checkbox("🌍 Remote Only")

# Japan Only
japan_only = st.sidebar.checkbox("🇯🇵 Japan Only")

# Focus Roles
focus_roles = st.sidebar.checkbox(
    "🎯 Focus Roles (Product / Web / eCommerce / Localization / Experience / Ops)"
)

# Seniority
st.sidebar.subheader("Seniority")

seniority_options = [
    "Director",
    "Head",
    "VP",
    "Principal",
    "Lead",
    "Manager",
]

selected_seniority = st.sidebar.multiselect(
    "Select Seniority Levels",
    seniority_options
)

# Company Filter
companies = sorted(df["company"].dropna().unique())
selected_companies = st.sidebar.multiselect("Company", companies)

# Search
search = st.sidebar.text_input("🔎 Search")

# Target Mode
target_mode = st.sidebar.checkbox("🎯 Exec Target Mode")

# -----------------------------------
# Apply Filters
# -----------------------------------

if remote_only:
    df = df[df["is_remote"] == True]

if japan_only:
    df = df[df["location"].str.contains("Japan|Tokyo", case=False, na=False)]

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

if selected_seniority:
    pattern = "|".join(selected_seniority)
    df = df[df["title"].str.contains(pattern, case=False, na=False)]

if selected_companies:
    df = df[df["company"].isin(selected_companies)]

if search:
    df = df[
        df["title"].str.contains(search, case=False, na=False)
        | df["company"].str.contains(search, case=False, na=False)
        | df["location"].str.contains(search, case=False, na=False)
    ]

# Exec Target Mode override
if target_mode:
    df = df[
        df["title"].str.contains(
            "Director|Head|VP|Principal", case=False, na=False
        )
    ]

if df.empty:
    st.warning("No jobs match filters.")
    st.stop()

# -----------------------------------
# Priority Tagging
# -----------------------------------

def tag_priority(title):
    title = str(title).lower()
    if any(x in title for x in ["director", "head", "vp"]):
        return "🔥 Exec"
    elif "senior" in title:
        return "⭐ Senior"
    else:
        return ""

df["Priority"] = df["title"].apply(tag_priority)

# -----------------------------------
# Metrics Row
# -----------------------------------

col1, col2, col3 = st.columns(3)

col1.metric("Total Jobs", len(df))
col2.metric("🔥 New (24h)", int(df["is_new_24h"].sum()))
col3.metric("🆕 New Today (UTC)", int(df["is_new_today"].sum()))

st.divider()

# -----------------------------------
# Tabs Layout
# -----------------------------------

tab1, tab2, tab3, tab4 = st.tabs(
    ["🔥 New", "📋 All Jobs", "📊 Companies", "🗑 Removed"]
)

display_cols = [
    "Priority",
    "company",
    "title",
    "location",
    "url",
    "seniority",
    "function",
    "first_seen_at",
]

# -----------------------------------
# 🔥 New Jobs Tab
# -----------------------------------

with tab1:
    st.subheader("🔥 New Jobs (Last 24 Hours)")

    new_jobs = df[df["is_new_24h"]].copy()
    new_jobs["first_seen_at"] = new_jobs["first_seen_at"].dt.strftime(
        "%Y-%m-%d %H:%M"
    )

    if new_jobs.empty:
        st.info("No new jobs in last 24 hours.")
    else:
        st.dataframe(
            new_jobs.sort_values("first_seen_at", ascending=False)[display_cols],
            column_config={
                "url": st.column_config.LinkColumn("Apply", display_text="Open")
            },
            use_container_width=True,
        )

# -----------------------------------
# 📋 All Jobs Tab
# -----------------------------------

with tab2:
    st.subheader("📋 All Active Jobs")

    df_display = df.copy()
    df_display["first_seen_at"] = df_display["first_seen_at"].dt.strftime(
        "%Y-%m-%d %H:%M"
    )

    st.dataframe(
        df_display.sort_values("first_seen_at", ascending=False)[display_cols],
        column_config={
            "url": st.column_config.LinkColumn("Apply", display_text="Open")
        },
        use_container_width=True,
    )

# -----------------------------------
# 📊 Company Tab
# -----------------------------------

with tab3:
    st.subheader("📊 Company Breakdown")

    company_stats = (
        df.groupby("company")
        .agg(
            total_jobs=("title", "count"),
            new_24h=("is_new_24h", "sum"),
        )
        .sort_values("total_jobs", ascending=False)
    )

    st.bar_chart(company_stats["total_jobs"])

# -----------------------------------
# 🗑 Removed Jobs Tab
# -----------------------------------

with tab4:
    st.subheader("🗑 Recently Removed (Last 24h)")

    removed = (
        supabase.table("jobs")
        .select("*")
        .eq("is_active", False)
        .gte("last_seen_at", last_24.isoformat())
        .execute()
    )

    removed_df = pd.DataFrame(removed.data)

    if removed_df.empty:
        st.info("No jobs removed in last 24 hours.")
    else:
        st.dataframe(removed_df, use_container_width=True)
