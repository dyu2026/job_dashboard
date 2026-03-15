import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta, timezone
import os, base64

# Page setting
st.set_page_config(page_title="Job Intelligence Dashboard", layout="wide")
# -----------------------------------
# CSS
# -----------------------------------
with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    
JST = timezone(timedelta(hours=9))

# ... (Rest of your existing Supabase setup and Fetch Data code) ...

# -----------------------------------
# Sidebar Content
# -----------------------------------
# If you already have sidebar filters, place this at the very bottom
with st.sidebar:
    st.title("Filters")
    # ... your existing sidebar widgets ...
    
    st.markdown("---") # Visual separator

# -----------------------------------
# Page Config
# -----------------------------------

st.title("Job Intelligence Dashboard")

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

# Helper function to convert local images to Base64
def get_base64_logo(company_name):
    # Standardize name for file path: logos/apple.webp
    file_path = f"logos/{company_name.lower()}.webp"
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
            return f"data:image/webp;base64,{data}"
    return None

# Apply the logo mapping to the main dataframe
df["logo"] = df["company"].apply(get_base64_logo)

# -----------------------------------
# Cleanup & Time Logic
# -----------------------------------

df["first_seen_at"] = (
    pd.to_datetime(df["first_seen_at"], utc=True, errors="coerce")
    .dt.tz_convert("Asia/Tokyo")
)

df["last_seen_at"] = (
    pd.to_datetime(df["last_seen_at"], utc=True, errors="coerce")
    .dt.tz_convert("Asia/Tokyo")
)

now_jst = datetime.now(JST)

last_24 = now_jst - timedelta(hours=24)

today_start = now_jst.replace(
    hour=0,
    minute=0,
    second=0,
    microsecond=0
)

df["is_new_24h"] = df["first_seen_at"] >= last_24
df["is_new_today"] = df["first_seen_at"] >= today_start

# -----------------------------------
# Sidebar Filters
# -----------------------------------

# st.sidebar.header("Filters")

# Remote
remote_only = st.sidebar.checkbox("Remote Only")

# Japan Only
japan_only = st.sidebar.checkbox("Japan Only")

# Focus Roles
st.sidebar.subheader("Focus Roles")

product_roles = st.sidebar.checkbox("Product")
web_roles = st.sidebar.checkbox("Web")
ecommerce_roles = st.sidebar.checkbox("Ecommerce")

# Target Mode
target_mode = st.sidebar.checkbox("Exec Target Mode")


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
search = st.sidebar.text_input("🍭 Search")

# -----------------------------------
# Last Updated (JST)
# -----------------------------------

# Get the most recent timestamp from the records
if not df.empty and "last_seen_at" in df.columns:
    # 1. Get the max timestamp
    latest_utc = df["last_seen_at"].max()
    
    # 2. Define JST
    jst_timezone = timezone(timedelta(hours=9))
    
    # 3. Convert to python datetime and then to JST
    # We use .to_pydatetime() to avoid the pandas astimezone error
    last_updated_jst = latest_utc.to_pydatetime().astimezone(jst_timezone).strftime("%Y-%m-%d %H:%M:%S")

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Last scraper run: {last_updated_jst} JST")

# -----------------------------------
# Apply Filters
# -----------------------------------

if remote_only:
    df = df[df["is_remote"] == True]

if japan_only:
    df = df[df["location"].str.contains("Japan|Tokyo", case=False, na=False)]

role_patterns = []

if product_roles:
    role_patterns.append("product")

if web_roles:
    role_patterns.append("web")

if ecommerce_roles:
    role_patterns.append("ecommerce|e-commerce|commerce")

if role_patterns:
    pattern = "|".join(role_patterns)
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
        return "👑 Exec"
    elif "senior" in title:
        return "😎 Senior"
    else:
        return ""

df["Priority"] = df["title"].apply(tag_priority)

# -----------------------------------
# Metrics Row
# -----------------------------------

total_companies = df["company"].nunique()

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Jobs", len(df))
col2.metric("🔥 New (24h)", int(df["is_new_24h"].sum()))
col3.metric("✨ New Today (JST)", int(df["is_new_today"].sum()))
col4.metric("Companies Tracked", total_companies)

st.divider()

# -----------------------------------
# Tabs Layout
# -----------------------------------

tab1, tab2, tab3, tab4 = st.tabs(
    ["🔥 New", "📋 All Jobs", "🚀 Companies", "🗑 Removed"]
)

display_cols = [
    "logo",
    "Priority",
    "company",
    "title",
    "location",
    "url",
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
                "logo": st.column_config.ImageColumn("Logo", width="small"),
                "url": st.column_config.LinkColumn("Apply", display_text="Open"),
                "first_seen_at": "First Seen",
                "company": "Company",
                "title": "Title",
                "location": "Location",
                "function": "Function"
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
            "logo": st.column_config.ImageColumn("Logo", width="small"),
            "url": st.column_config.LinkColumn("Apply", display_text="Open"),
            "first_seen_at": "First Seen",
            "company": "Company",
            "title": "Title",
            "location": "Location",
            "function": "Function"
        },
        use_container_width=True,
    )

# -----------------------------------
# 📊 Company Tab
# -----------------------------------

with tab3:
    st.subheader("🚀 Company Breakdown")

    company_stats = (
        df.groupby("company")
        .agg(
            total_jobs=("title", "count"),
            new_24h=("is_new_24h", "sum"),
        )
        .sort_values("total_jobs", ascending=False)
    )

    st.bar_chart(company_stats["total_jobs"], color="#ff4d6b")

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
        # 1. Date Cleanup
        removed_df["first_seen_at"] = pd.to_datetime(
            removed_df["first_seen_at"], errors="coerce"
        ).dt.strftime("%Y-%m-%d %H:%M")

        # 2. Add Priority & Logo Columns (These aren't in the raw DB response)
        if "Priority" not in removed_df.columns:
            removed_df["Priority"] = removed_df["title"].apply(tag_priority)
            
        # This uses your existing get_base64_logo function
        removed_df["logo"] = removed_df["company"].apply(get_base64_logo)

        # 3. Filter for existing columns
        # We ensure 'logo' and 'Priority' are included in the filter check
        safe_cols = [c for c in display_cols if c in removed_df.columns]

        st.dataframe(
            removed_df.sort_values("first_seen_at", ascending=False)[safe_cols],
            column_config={
                "logo": st.column_config.ImageColumn("Logo", width="small"), # Renders the image
                "url": st.column_config.LinkColumn("Apply", display_text="Open"),
                "first_seen_at": "First Seen",
                "company": "Company",
                "title": "Title",
                "location": "Location",
                "function": "Function"
            },
            use_container_width=True,
            hide_index=True
        )

# -----------------------------------
# LinkedIn Hiring Signals
# -----------------------------------

st.divider()
st.header("LinkedIn Hiring Signals (Last 7 Days)")

cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

linkedin_posts = (
    supabase.table("linkedin_posts")
    .select("*")
    .gte("published_at", cutoff)
    .order("published_at", desc=True)
    .execute()
)

linkedin_df = pd.DataFrame(linkedin_posts.data)

if linkedin_df.empty:
    st.info("No LinkedIn hiring signals detected.")
else:

    linkedin_df["published_at"] = pd.to_datetime(
        linkedin_df["published_at"]
    ).dt.strftime("%Y-%m-%d %H:%M")

    st.dataframe(
        linkedin_df[["published_at","title","url"]],
        column_config={
            "url": st.column_config.LinkColumn("Open Post", display_text="View"),
            "title": "Title",
            "published_at": "Published"
        },
        use_container_width=True
    )
