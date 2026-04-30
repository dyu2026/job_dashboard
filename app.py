import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta, timezone
from streamlit_cookies_manager import EncryptedCookieManager
import streamlit.components.v1 as components
import os, base64
import altair as alt
import uuid
import re
import numpy as np
import matplotlib.colors as mcolors

# Page setting
st.set_page_config(page_title="Job Intelligence Dashboard", layout="wide")

st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded" rel="stylesheet">
""", unsafe_allow_html=True)

# -----------------------------------
# CSS
# -----------------------------------
with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# -----------------------------------
# cookie to exclude my traffic
# -----------------------------------
    
cookies = EncryptedCookieManager(
    prefix="job_dashboard",
    password=st.secrets["COOKIE_SECRET"]
)

if not cookies.ready():
    st.stop()
    
query_params = st.query_params

if query_params.get("internal") == st.secrets["INTERNAL_TOKEN"]:
    cookies["user_type"] = "internal"
    cookies.save()
    
    st.query_params.clear()

user_type = cookies.get("user_type", "external")

# debug cookie working for user type
# st.sidebar.write("User type:", user_type)

# -----------------------------------
# set timezone
# -----------------------------------

JST = timezone(timedelta(hours=9))

# -----------------------------------
# Sidebar Content
# -----------------------------------

with st.sidebar:
    import base64

    def get_base64_image(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    img_base64 = get_base64_image("logos/RainbowDino_200x173.png")

    st.markdown(f"""
    <style>
    .sidebar-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
    }}
    .sidebar-header .left {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 24px;
        font-weight: 700;
    }}
    </style>

    <div class="sidebar-header">
        <div class="left">
            <span class="material-symbols-rounded">filter_alt</span>
            <span>Filters</span>
        </div>
        <img src="data:image/png;base64,{img_base64}" 
             style="width:70px; height:auto;" />
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

# -----------------------------------
# Page Config
# -----------------------------------

#st.title("Job Intelligence Dashboard")
st.markdown("""
<h1 style="margin-bottom: 0;">Job Intelligence Dashboard</h1>
<p style="color: gray; margin-top: -5px; margin-bottom: 40px;">
Track Japan & remote tech jobs with real-time hiring insights
</p>
""", unsafe_allow_html=True)

# -----------------------------------
# Supabase Setup
# -----------------------------------

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------------
# Page View Tracking
# -----------------------------------

# Create session ID (persist across page interactions)
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())

if "page_logged" not in st.session_state:
    try:
        supabase.table("page_views").insert({
            "session_id": st.session_state["session_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_type": user_type
        }).execute()

        st.session_state["page_logged"] = True

    except Exception as e:
        st.error(f"Tracking error: {e}")


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

# Safety fallback
for col, default in {
    "region": "unknown",
    "is_remote": False,
    "is_japan": False,
    "remote_scope": "unknown"
}.items():
    if col not in df.columns:
        df[col] = default

# Normalize
df["remote_scope"] = df["remote_scope"].astype(str).str.lower().fillna("unknown")
df["region"] = df["region"].astype(str).str.lower().fillna("unknown")

def classify_location(row):
    location = str(row.get("location", "")).lower()
    region = str(row.get("region", "")).lower()
    remote_scope = str(row.get("remote_scope", "")).lower()

    # --- Explicit exclusions ---
    if any(x in location for x in [
        "bogota", "colombia",
        "brazil", "argentina", "mexico",
        "africa", "nigeria", "kenya",
        "europe", "germany", "france", "spain", "uk",
        "canada", "united states", "usa"
    ]):
        return "exclude"

    # --- Strong Japan signals ---
    if any(x in location for x in ["japan", "tokyo", "osaka", "yokohama", "kanagawa"]):
        return "japan"

    if region == "japan":
        return "japan"

    # --- Remote allowed ---
    if row.get("is_remote") == True:
        if remote_scope in ["global", "apac"]:
            return "remote_allowed"

        if any(x in location for x in ["apac", "asia"]):
            return "remote_allowed"

    return "unknown"
    
df["location_class"] = df.apply(classify_location, axis=1)

df = df[
    df["location_class"].isin(["japan", "remote_allowed"])
]

def prepare_jobs_dataframe(df):
    now_utc = pd.Timestamp.now(tz="UTC")
    now_jst = pd.Timestamp.now(tz="Asia/Tokyo")

    # --- Ensure datetime ---
    if "first_seen_at" in df.columns:
        df["first_seen_at"] = pd.to_datetime(df["first_seen_at"], utc=True, errors="coerce")

    if "last_seen_at" in df.columns:
        df["last_seen_at"] = pd.to_datetime(df["last_seen_at"], utc=True, errors="coerce")

    # --- JST conversion ---
    if "first_seen_at" in df.columns:
        df["first_seen_at_jst"] = df["first_seen_at"].dt.tz_convert("Asia/Tokyo")

    if "last_seen_at" in df.columns:
        df["last_seen_at_jst"] = df["last_seen_at"].dt.tz_convert("Asia/Tokyo")

    # --- Time flags ---
    last_24_utc = now_utc - pd.Timedelta(hours=24)

    if "first_seen_at" in df.columns:
        df["is_new_24h"] = df["first_seen_at"] >= last_24_utc

    if "first_seen_at_jst" in df.columns:
        today_start = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
        df["is_new_today"] = df["first_seen_at_jst"] >= today_start

    # --- Relative time (NEW - better UX) ---
    if "first_seen_at" in df.columns:
        df["hours_since_posted"] = (
            (now_utc - df["first_seen_at"]).dt.total_seconds() / 3600
        ).fillna(0).astype(int)

    # --- Days since (keep your existing UX) ---
    if "first_seen_at_jst" in df.columns:
        df["days_since_posted"] = (
            now_jst.normalize() - df["first_seen_at_jst"].dt.normalize()
        ).dt.days

        def format_days_ago(days):
            if pd.isna(days):
                return ""
            days = int(days)
            if days == 0:
                return "Today"
            elif days == 1:
                return "1d ago"
            else:
                return f"{days}d ago"

        df["days_since_posted"] = df["days_since_posted"].apply(format_days_ago)

    return df

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
# Priority Tagging
# -----------------------------------

def tag_priority(title):
    title = str(title).lower()
    if any(x in title for x in ["director", "head", "vp", "cto", "chief", "ceo", "president", "general manager"]):
        return "👑 Exec"
    elif "senior" in title:
        return "😎 Senior"
    else:
        return ""

df["Priority"] = df["title"].apply(tag_priority)

ROLE_LABEL_MAP = {
    "product management": "Product",
    "engineering": "Engineering",
    "design": "Design",
    "data and analytics": "Data",
    "marketing": "Marketing",
    "sales": "Sales",
    "business development": "Biz Dev",
    "customer success and experience": "Customer Success",
    "hr and recruiting": "HR",
    "finance and accounting": "Finance",
    "operations and support": "Operations",
    "program and project management": "Program/Proj Mgmt",
    "information technology": "IT",
    "security": "Security",
    "legal": "Legal",
    "research and development": "R&D",
    "supply chain and procurement": "Supply Chain",
    "customer solution": "Customer Solutions",
    "communications and pr": "Comms",
    "solutions architect and engineer": "Solutions SA/SE",
    "other": "Other"
}

df["role_short"] = (
    df["role"]
    .str.lower()
    .map(ROLE_LABEL_MAP)
    .fillna("Other")
)

df_for_trends = df.copy()  # keep full dataset for trends if needed

def extract_seniority(title):
    title = str(title).lower()

    if re.search(r"\b(chief|ceo|cto|cfo|cpo)\b", title):
        return "C-Level"
    elif re.search(r"\b(vp|vice president)\b", title):
        return "VP"
    elif re.search(r"\bhead\b", title):
        return "Head"
    elif re.search(r"\bdirector\b", title):
        return "Director"
    elif re.search(r"\bprincipal\b", title):
        return "Principal"
    elif re.search(r"\blead\b", title):
        return "Lead"
    elif re.search(r"\bmanager\b", title):
        return "Manager"
    elif re.search(r"\bsenior\b", title):
        return "Senior"
    else:
        return "Other"

df["seniority"] = df["title"].apply(extract_seniority)

SENIORITY_ORDER = [
    "C-Level",
    "VP",
    "Head",
    "Director",
    "Principal",
    "Lead",
    "Manager",
    "Senior",
    "Other"
]

# -----------------------------------
# Cleanup & Time Logic (centralized)
# -----------------------------------

df = prepare_jobs_dataframe(df)

now_utc = pd.Timestamp.now(tz="UTC")
now_jst = pd.Timestamp.now(tz="Asia/Tokyo")
last_24_utc = now_utc - pd.Timedelta(hours=24)


# -----------------------------------
# Sidebar Filters
# -----------------------------------

# Roles and level filter
st.sidebar.markdown('<h3 style="color:#ff4d6b;">Role & Level</h3>', unsafe_allow_html=True)
# Get unique roles from dataset
role_options = sorted(df["role_short"].dropna().unique())

# Roles
selected_roles = st.sidebar.multiselect(
    "",
    role_options,
    placeholder="Search Roles"
)

# Seniority
available_levels = df["seniority"].dropna().unique()
seniority_options = [
    level for level in SENIORITY_ORDER if level in available_levels
]
selected_seniority = st.sidebar.multiselect(
    "",
    seniority_options,
    placeholder="Select Seniority"
)

# Company Filter
st.sidebar.markdown('<h3 style="color:#ff4d6b;">Company</h3>', unsafe_allow_html=True)
companies = sorted(df["company"].dropna().unique())
selected_companies = st.sidebar.multiselect(
    "", 
    companies,
    placeholder="Select Company"
)


# Recency Filter
st.sidebar.markdown('<h3 style="color:#ff4d6b;">Posted</h3>', unsafe_allow_html=True)

TIME_FILTERS = {
    "Last 3 days": 3,
    "Last 1 week": 7,
    "Last 2 weeks": 14,
    "Last 1 month": 30
}

selected_recency = st.sidebar.selectbox(
    "Show jobs from",
    ["All"] + list(TIME_FILTERS.keys())
)


# -----------------------------------
# Search + Reset
# -----------------------------------

def clear_search():
    st.session_state.search = ""

st.sidebar.markdown('<div class="search-row">', unsafe_allow_html=True)

col1, col2 = st.sidebar.columns([4, 1])

with col1:
    st.text_input("", key="search", placeholder="🍭 Search", label_visibility="collapsed")

with col2:
    st.button("✕", on_click=clear_search)

st.sidebar.markdown('</div>', unsafe_allow_html=True)

# -----------------------------------
# Last Updated (JST)
# -----------------------------------

# Get the most recent timestamp from the records
if not df.empty and "last_seen_at" in df.columns:
    # 1. Get latest timestamp (UTC)
    latest_utc = df["last_seen_at"].max().to_pydatetime()

    # 2. Current time (UTC)
    now_utc = datetime.now(timezone.utc)

    # 3. Time difference
    diff = now_utc - latest_utc
    seconds = int(diff.total_seconds())

    # 4. Format relative time
    if seconds < 60:
        val = seconds
        unit = "sec" if val == 1 else "secs"
    elif seconds < 3600:
        val = seconds // 60
        unit = "min" if val == 1 else "mins"
    elif seconds < 86400:
        val = seconds // 3600
        unit = "hr" if val == 1 else "hrs"
    else:
        val = seconds // 86400
        unit = "day" if val == 1 else "days"

    rel = f"{val} {unit} ago"

    # 5. Convert to JST
    jst_timezone = timezone(timedelta(hours=9))
    last_updated_jst = latest_utc.astimezone(jst_timezone)

    # 6. Format absolute time
    absolute = last_updated_jst.strftime("%b %d, %H:%M JST")

    # 7. Display
    st.sidebar.markdown("---")
    st.sidebar.caption(f"Updated: {rel} ({absolute})")
    st.sidebar.caption("Made in :streamlit: by [Derek Yu](https://www.linkedin.com/in/derekhyyu/)")

# -----------------------------------
# Apply Filters
# -----------------------------------

if selected_roles:
    df = df[df["role_short"].isin(selected_roles)]

if selected_seniority:
    df = df[df["seniority"].isin(selected_seniority)]

if selected_companies:
    df = df[df["company"].isin(selected_companies)]

if st.session_state.search:
    df = df[
        df["title"].str.contains(st.session_state.search, case=False, na=False)
        | df["company"].str.contains(st.session_state.search, case=False, na=False)
        | df["location"].str.contains(st.session_state.search, case=False, na=False)
    ]

# Apply Recency Filter (GLOBAL)

df_filtered = df.copy()

if selected_recency != "All":
    days = TIME_FILTERS[selected_recency]
    cutoff = now_jst - timedelta(days=days)

    df_filtered["first_seen_at"] = pd.to_datetime(
        df_filtered["first_seen_at"], errors="coerce"
    )

    df_filtered = df_filtered[df_filtered["first_seen_at"] >= cutoff]

if df_filtered.empty:
    st.warning("No jobs match filters.")
    st.stop()


# -----------------------------------
# Metrics Row
# -----------------------------------

total_companies = df["company"].nunique()

col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Jobs", len(df_filtered))
col2.metric("🔥 New (24h)", int(df_filtered["is_new_24h"].sum()))
col3.metric("✨ New Today (JST)", int(df_filtered["is_new_today"].sum()))
col4.metric("Companies Tracked", df_filtered["company"].nunique())

st.divider()

# -----------------------------------
# Posting Trend Dataset
# -----------------------------------

trend_df = df_for_trends.copy()

trend_df["first_seen_at"] = (
    pd.to_datetime(trend_df["first_seen_at"], utc=True, errors="coerce")
    .dt.tz_convert("Asia/Tokyo")
)

# 1. Company first seen
company_first_seen = (
    trend_df.groupby("company")["first_seen_at"]
    .min()
    .reset_index()
    .rename(columns={"first_seen_at": "company_first_seen"})
)

trend_df = trend_df.merge(company_first_seen, on="company", how="left")

# 2. Remove ingestion spike
INGESTION_WINDOW_DAYS = 1

trend_df["days_from_company_start"] = (
    trend_df["first_seen_at"] - trend_df["company_first_seen"]
).dt.days

trend_df = trend_df[
    trend_df["days_from_company_start"] > INGESTION_WINDOW_DAYS
]

# 3. Day of week
trend_df["day_of_week"] = trend_df["first_seen_at"].dt.day_name()

# 4. Order
day_order = [
    "Sunday", "Monday", "Tuesday", "Wednesday",
    "Thursday", "Friday", "Saturday"
]

trend_df["day_of_week"] = pd.Categorical(
    trend_df["first_seen_at"].dt.day_name(),
    categories=day_order,
    ordered=True
)

day_counts = (
    trend_df["day_of_week"]
    .value_counts()
    .sort_index()
    .fillna(0)
)

# Heatmap of postings

# Hour of day (JST)
trend_df["hour"] = trend_df["first_seen_at"].dt.hour

heatmap_data = (
    trend_df.groupby(["day_of_week", "hour"])
    .size()
    .reset_index(name="count")
)

# -----------------------------------
# Tabs prep
# -----------------------------------

company_first_seen = (
    df.groupby("company")["first_seen_at"]
    .min()
    .reset_index()
    .rename(columns={"first_seen_at": "company_first_seen_at"})
)

df_filtered = df_filtered.merge(company_first_seen, on="company", how="left")

df_filtered["company_first_seen_at"] = pd.to_datetime(
    df_filtered["company_first_seen_at"], utc=True, errors="coerce"
)

df_filtered["company_first_seen_at_jst"] = (
    df_filtered["company_first_seen_at"].dt.tz_convert("Asia/Tokyo")
)

df_filtered["is_new_company"] = (
    (now_utc - df_filtered["company_first_seen_at"])
    <= pd.Timedelta(hours=24)
)

df_filtered["company_display"] = df_filtered["company"]
df_filtered.loc[df_filtered["is_new_company"], "company_display"] += " 🌟"


# -----------------------------------
# Tabs Layout
# -----------------------------------

tab1, tab2, tab3, tab6, tab5, tab4 = st.tabs(
    ["🔥 New", "📋 All Jobs", "🚀 Companies", "❄️ Roles", "📮 Posting Trends", "🚫 Removed"]
)


display_cols = [
    "logo",
    "company",
    "Priority",
    "title",
    "location",
    "url",
    "hours_since_posted",
    "days_since_posted",
    "role",
    "first_seen_at",
]

# -----------------------------------
# New Jobs Tab
# -----------------------------------

with tab1:
    st.subheader("🔥 New Jobs (Last 24 Hours)")
    
    st.markdown("""
    <p style="color: gray; margin-bottom: 30px; font-size: 14px;">
    Includes newly tracked companies and recently discovered roles<br>
    🌟 New company added to tracking
    </p>
    """, unsafe_allow_html=True)

    new_jobs = df_filtered[df_filtered["is_new_24h"]].copy()

    if new_jobs.empty:
        st.info("No new jobs in last 24 hours.")
    else:
        # --- DATA CLEANUP FOR SORTING ---
        # Extract digits from "Hrs Ago" to allow numeric sorting
        if "hours_since_posted" in new_jobs.columns:
            new_jobs["hours_since_posted"] = (
                new_jobs["hours_since_posted"]
                .astype(str)
                .str.extract(r'(\d+)')
                .fillna(0)
                .astype(int)
            )

        # Format timestamp for display
        new_jobs["first_seen_at_jst"] = new_jobs["first_seen_at_jst"].dt.strftime("%Y-%m-%d %H:%M")

        # Column mapping
        safe_cols = [c for c in display_cols if c in new_jobs.columns]
        safe_cols = ["company_display" if c == "company" else c for c in safe_cols]
        safe_cols = ["first_seen_at_jst" if c == "first_seen_at" else c for c in safe_cols]
        
        st.dataframe(
            new_jobs.sort_values("first_seen_at", ascending=False)[safe_cols],
            column_config={
                "logo": st.column_config.ImageColumn("Logo", width="small"),
                "Priority": st.column_config.TextColumn("Priority", width="small"),
                "url": st.column_config.LinkColumn("Apply", display_text="Open"),
                "first_seen_at_jst": "First Seen (JST)",
                
                # --- THE SORTING FIX ---
                "hours_since_posted": st.column_config.NumberColumn(
                    "Hrs", 
                    format="%d h", 
                    width="small"
                ),
                
                "days_since_posted": st.column_config.TextColumn("Days", width="small"),
                "company_display": st.column_config.TextColumn("Company", width="small"),
                "title": "Title",
                "location": "Location",
                "role": "Role"
            },
            use_container_width=True,
            hide_index=True,
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

        linkedin_df["published_at"] = (
            pd.to_datetime(linkedin_df["published_at"], utc=True, errors="coerce")
            .dt.tz_convert("Asia/Tokyo")
            .dt.strftime("%Y-%m-%d %H:%M")
        )

        st.dataframe(
            linkedin_df[["published_at","title","url"]],
            column_config={
                "url": st.column_config.LinkColumn("Open Post", display_text="View"),
                "title": "Title",
                "published_at": "Published (JST)",
            },
            use_container_width=True,
            hide_index=True,
        )

# -----------------------------------
# All Jobs Tab
# -----------------------------------

with tab2:
    st.subheader("📋 All Active Jobs")
    
    st.markdown("""
    <p style="color: gray; margin-bottom: 30px; font-size: 14px;">
    All roles currently tracked across companies and regions<br>
    🌟 New company added to tracking
    </p>
    """, unsafe_allow_html=True)

    df_display = df_filtered.copy()

    # --- DATA CLEANUP FOR SORTING ---
    # Ensure these are numeric. If they contain "today" or strings, 
    # we convert them to 0 or extract the digits so sorting works.
    for col in ["hours_since_posted", "days_since_posted"]:
        if col in df_display.columns:
            # Convert to string first to handle mixed types, then extract digits
            df_display[col] = (
                df_display[col]
                .astype(str)
                .str.extract(r'(\d+)') # Extract only the numbers
                .fillna(0)             # Treat "today" or NaNs as 0
                .astype(int)           # Convert to actual integers
            )

    # Format the timestamp for display
    if "first_seen_at_jst" in df_display.columns:
        df_display["first_seen_at_jst"] = df_display["first_seen_at_jst"].dt.strftime("%Y-%m-%d %H:%M")

    # Column selection logic
    safe_cols = [c for c in display_cols if c in df_display.columns]
    safe_cols = ["company_display" if c == "company" else c for c in safe_cols]
    safe_cols = ["first_seen_at_jst" if c == "first_seen_at" else c for c in safe_cols]
    
    st.dataframe(
        df_display.sort_values("first_seen_at", ascending=False)[safe_cols],
        column_config={
            "logo": st.column_config.ImageColumn("Logo", width="small"),
            "Priority": st.column_config.TextColumn("Priority", width="small"),
            "url": st.column_config.LinkColumn("Apply", display_text="Open"),
            "first_seen_at_jst": "First Seen (JST)",
            
            # --- THE SORTING FIXES ---
            "hours_since_posted": st.column_config.NumberColumn(
                "Hrs", 
                help="Hours since the job was posted",
                format="%d h", # Adds 'h' suffix visually
                width="small"
            ),
            "days_since_posted": st.column_config.NumberColumn(
                "Days", 
                help="Days since the job was posted",
                format="%d d", # Adds 'd' suffix visually
                width="small"
            ),
            # -------------------------
            
            "company_display": st.column_config.TextColumn("Company", width="small"),
            "title": "Title",
            "location": "Location",
            "role": "Role"
        },
        use_container_width=True,
        hide_index=True,
    )

# -----------------------------------
# Company Tab
# -----------------------------------

with tab3:
    st.subheader("🚀 Company Breakdown")

    df_company = df_filtered.copy()
    df_company["company"] = df_company["company"].str.strip()

    selected_count = len(selected_companies)

    # -----------------------------------
    # CASE 1: Single company selected → show ROLE breakdown
    # -----------------------------------
    if selected_count == 1:
        selected_company = selected_companies[0]

        role_stats = (
            df_company[df_company["company"] == selected_company]
            .groupby("role_short")
            .size()
            .reset_index(name="count")
        )

        # sort by volume (most → least)
        role_stats = role_stats.sort_values("count", ascending=False).reset_index(drop=True)

        # % share
        role_stats["pct"] = (
            role_stats["count"] / role_stats["count"].sum() * 100
        ).round(1)

        # order = 0 is highest volume, order = max is lowest volume
        role_stats["order"] = range(len(role_stats))
        role_stats["group"] = selected_company

        st.markdown(f"**{selected_company} — Role Breakdown**")
        st.caption("Role distribution (stacked by volume)")

        # -----------------------------------
        # Red gradient (dark → light)
        # -----------------------------------
        base_gradient = [
            "#ff4d6b",  # strongest (largest roles)
            "#ff6b81",
            "#ff8fa3",
            "#ffb3c1",
            "#ffd6dd",
            "#ffe6ea",
            "#fff0f3"
        ]

        n_roles = len(role_stats)

        if n_roles > len(base_gradient):

            cmap = mcolors.LinearSegmentedColormap.from_list(
                "custom_red",
                ["#ff4d6b", "#fff0f3"]
            )

            base_gradient = [
                mcolors.to_hex(cmap(i / max(n_roles - 1, 1)))
                for i in range(n_roles)
            ]

        # -----------------------------------
        # Align Stack, Colors, and Legend
        # -----------------------------------
        # Reverse domains so the Legend displays Lowest (top) -> Highest (bottom)
        # while mapping Lowest -> Light and Highest -> Dark.
        legend_domain = role_stats["role_short"].tolist()[::-1]
        legend_range = base_gradient[:n_roles][::-1]

        chart = alt.Chart(role_stats).mark_bar().encode(
            x=alt.X(
                "group:N",
                title="",
                axis=alt.Axis(labels=False, ticks=False)
            ),

            y=alt.Y(
                "count:Q",
                title="Total Jobs"
            ),

            # Stack order: order:0 (highest volume) is drawn first (at the bottom)
            order=alt.Order("order:Q", sort="ascending"),

            color=alt.Color(
                "role_short:N",
                scale=alt.Scale(
                    domain=legend_domain,
                    range=legend_range
                ),
                legend=alt.Legend(title="Role")
            ),

            tooltip=[
                alt.Tooltip("role_short:N", title="Role"),
                alt.Tooltip("count:Q", title="Jobs"),
                alt.Tooltip("pct:Q", title="%")
            ]
        ).properties(
            height=400
        )

        st.altair_chart(chart, use_container_width=True)

    # -----------------------------------
    # CASE 2: Default → Company breakdown
    # -----------------------------------
    else:
        
        st.markdown("""
        <div style="
            background-color:#f5f7fb;
            padding:12px 16px;
            border-radius:8px;
            font-size:14px;
            margin-bottom: 40px;
        ">
        <b>Tip:</b> Select a single company in the sidebar filter to view its detailed role breakdown.
        </div>
        """, unsafe_allow_html=True)

        company_stats = (
            df_company.groupby("company")
            .agg(
                total_jobs=("title", "count"),
                new_24h=("is_new_24h", "sum"),
            )
            .reset_index()
        )

        sorted_companies = sorted(company_stats["company"], key=lambda x: x.lower())

        chart = alt.Chart(company_stats).mark_bar().encode(
            x=alt.X(
                "company:N",
                sort=sorted_companies,
                title="Company"
            ),
            y=alt.Y("total_jobs:Q", title="Total Jobs"),
            color=alt.value("#ff4d6b"),
            tooltip=["company", "total_jobs"]
        ).properties(
            height=400
        )

        st.altair_chart(chart, use_container_width=True)

# -----------------------------------
# 🗑 Removed Jobs Tab
# -----------------------------------

with tab4:
    st.subheader("🚫 Recently Removed (Last 24h)")

    removed = (
        supabase.table("jobs")
        .select("*")
        .eq("is_active", False)
        .gte("last_seen_at", last_24_utc.isoformat())
        .execute()
    )

    removed_df = pd.DataFrame(removed.data)

    if removed_df.empty:
        st.info("No jobs removed in last 24 hours.")
    else:
        # --- Datetime handling (correct way) ---
        removed_df["first_seen_at"] = pd.to_datetime(
            removed_df["first_seen_at"], utc=True, errors="coerce"
        )

        removed_df["first_seen_at_jst"] = (
            removed_df["first_seen_at"]
            .dt.tz_convert("Asia/Tokyo")
            .dt.strftime("%Y-%m-%d %H:%M")
        )

        # --- Add missing columns ---
        if "Priority" not in removed_df.columns:
            removed_df["Priority"] = removed_df["title"].apply(tag_priority)

        removed_df["logo"] = removed_df["company"].apply(get_base64_logo)

        if "days_since_posted" not in removed_df.columns:
            removed_df["days_since_posted"] = ""

        if "role" not in removed_df.columns:
            removed_df["role"] = ""

        # --- Safe columns ---
        removed_display_cols = [
            "logo",
            "company",
            "Priority",
            "title",
            "location",
            "role",
            "first_seen_at_jst",
        ]

        safe_cols = [c for c in removed_display_cols if c in removed_df.columns]
        safe_cols = ["first_seen_at_jst" if c == "first_seen_at" else c for c in safe_cols]

        # --- Render ---
        st.dataframe(
            removed_df.sort_values("first_seen_at", ascending=False)[safe_cols],
            column_config={
                "logo": st.column_config.ImageColumn("Logo", width="small"),
                "Priority": st.column_config.TextColumn("Priority", width="small"),
                "company": st.column_config.TextColumn("Company", width="small"),
                "title": "Title",
                "location": "Location",
                "role": "Role",
                "first_seen_at_jst": "First Seen (JST)",
            },
            use_container_width=True,
            hide_index=True
        )

# -----------------------------------
# Posting Trends Tab
# -----------------------------------

with tab5:
    st.subheader("📮 Job Posting Trends (JST)")
    
    
    # -----------------------------------
    # 📅 Weekly Posting Trends (NEW)
    # -----------------------------------

    st.markdown("### 📅 Weekly Posting Trends")

    time_window = st.selectbox(
        "Time Range",
        options=[7, 30, 90],
        format_func=lambda x: f"Last {x} days",
        index=1,
    )

    if trend_df.empty:
        st.info("Not enough data to show trends.")
    else:
        import pandas as pd
        from datetime import datetime, timedelta
        import altair as alt

        df = trend_df.copy()

        # --- Ensure datetime ---
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date

        # --- 🚫 Exclude first day per company ---
        first_seen = df.groupby("company")["date"].transform("min")
        df = df[df["date"] > first_seen]

        # --- ⏱ Apply time window ---
        cutoff = datetime.now().date() - timedelta(days=time_window)
        df = df[df["date"] >= cutoff]

        if df.empty:
            st.info("No data available after filtering.")
        else:
            # --- 📊 Create weekly buckets (7-day groups) ---
            df["week_start"] = pd.to_datetime(df["date"]) - pd.to_timedelta(
                pd.to_datetime(df["date"]).dt.weekday, unit="d"
            )

            weekly_counts = (
                df.groupby("week_start")
                .size()
                .reset_index(name="count")
                .sort_values("week_start")
            )

            # Optional: label formatting
            weekly_counts["label"] = weekly_counts["week_start"].dt.strftime("%b %d")

            # --- 📊 Chart ---
            weekly_chart = alt.Chart(weekly_counts).mark_bar().encode(
                x=alt.X(
                    "week_start:T",
                    title="Week (Start Date)",
                    axis=alt.Axis(format="%b %d")
                ),
                y=alt.Y("count:Q", title="New Jobs"),
                tooltip=[
                    alt.Tooltip("week_start:T", title="Week"),
                    alt.Tooltip("count:Q", title="Jobs"),
                ],
            )

            st.altair_chart(weekly_chart, use_container_width=True)

            # --- 🔥 Insight: Peak weeks ---
            top_weeks = weekly_counts.sort_values("count", ascending=False).head(3)

            if not top_weeks.empty:
                st.markdown("### 🔥 Peak Hiring Weeks")
                medals = ["🥇", "🥈", "🥉"]

                for i, row in enumerate(top_weeks.itertuples()):
                    label = row.week_start.strftime("%b %d")
                    count = int(row.count)
                    st.markdown(f"{medals[i]} Week of {label} ({count} jobs)")
        
        
        st.markdown("""
        <p style="color: gray; margin-bottom: 30px; font-size: 14px;">
        Excludes first day of each company to remove initial data spikes.
        </p>
        """, unsafe_allow_html=True)

        if trend_df.empty:
            st.info("Not enough data to show trends.")
        else:
            # -----------------------------------
            # Day-of-week bar chart
            # -----------------------------------
            st.bar_chart(day_counts, color="#ff4d6b")

            # -----------------------------------
            # Heatmap (Day x Hour)
            # -----------------------------------

            # Format hour labels (1:00, 2:00, etc.)
            heatmap_data["hour_label"] = heatmap_data["hour"].apply(lambda x: f"{x}:00")

            # Ensure correct hour order
            hour_order = [f"{i}:00" for i in range(24)]
            
            st.markdown("""
            <p style="color: gray; margin-bottom: 30px; font-size: 14px;">
            When new jobs are first detected (JST), excluding initial bulk import when company is first tracked.
            </p>
            """, unsafe_allow_html=True)

            heatmap = alt.Chart(heatmap_data).mark_rect().encode(
                x=alt.X(
                    "hour_label:O",
                    sort=hour_order,
                    title="Hour of Day (JST)"
                ),
                y=alt.Y(
                    "day_of_week:O",
                    sort=day_order,
                    title="Day of Week"
                ),
                color=alt.Color(
                    "count:Q",
                    scale=alt.Scale(scheme="reds"),
                    title="Jobs"
                ),
                tooltip=[
                    alt.Tooltip("day_of_week", title="Day"),
                    alt.Tooltip("hour_label", title="Hour"),
                    alt.Tooltip("count", title="Jobs")
                ]
            )

            st.altair_chart(heatmap, use_container_width=True)
            
            # -----------------------------------
            # 🔥 Auto Insight: Top Posting Times 
            # -----------------------------------

            if not heatmap_data.empty:
                top_slots = heatmap_data.sort_values("count", ascending=False).head(3)

                st.markdown("### 🔥 Peak Posting Activity (Observed)")

                medals = ["🥇", "🥈", "🥉"]

                for i, row in enumerate(top_slots.itertuples()):
                    label = f"{row.day_of_week} at {int(row.hour)}:00 JST"
                    count = int(row.count)

                    st.markdown(f"{medals[i]} {label} ({count} jobs)")

# -----------------------------------
# Role Insights Tab
# -----------------------------------

with tab6:
    
    st.subheader("❄️ Role Distribution")

    st.caption(f"Showing: {selected_recency}")

    # ✅ STEP 1: Create role_df
    
    role_df = (
        df_filtered.groupby("role_short")
        .size()
        .reset_index(name="count")
    )

    # ✅ STEP 2: Sort
    role_df = role_df.sort_values("count", ascending=False).reset_index(drop=True)
    
    total_jobs = role_df["count"].sum()
    max_count = role_df["count"].max()
    
    medals = ["🥇", "🥈", "🥉"]

    # Build HTML
    html = ""
    
    for i, row in role_df.iterrows():
        role = row["role_short"]
        count = int(row["count"])
        pct = (count / total_jobs) * 100
    
        rank = medals[i] if i < 3 else f"{i+1}"
    
        bar_width = int((count / max_count) * 100)
    
        html += f"""
        <div style="display: flex; align-items: center; margin-bottom: 8px;">
            
            <div style="width: 40px;">{rank}</div>
            
            <div style="width: 180px;">{role}</div>
            
            <div style="flex-grow: 1; background-color: rgba(0,0,0,0.05); height: 16px; border-radius: 5px; margin: 0 10px;">
                <div style="
                    width: {bar_width}%;
                    background-color: #ff4d6b;
                    height: 100%;
                    border-radius: 5px;
                "></div>
            </div>
            
            <div style="width: 60px;">{count}</div>
            <div style="width: 60px;">{pct:.1f}%</div>
            
        </div>
        """
    
    # ✅ STEP 3: Render HTML
    components.html(f"""
    <div style="font-family: sans-serif;">
    {html}
    </div>
    """, height=650, scrolling=True)
