import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta, timezone
from streamlit_cookies_manager import EncryptedCookieManager
import os, base64
import altair as alt
import uuid

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
    st.markdown("""
    <style>
    .sidebar-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 10px;
    }
    </style>

    <div class="sidebar-title">
        <span class="material-symbols-rounded">filter_alt</span>
        <span>Filters</span>
    </div>
    """, unsafe_allow_html=True)
   
    st.markdown("---") # Visual separator

# -----------------------------------
# Page Config
# -----------------------------------

#st.title("Job Intelligence Dashboard")
st.markdown("""
<h1 style="margin-bottom: 0;">Job Intelligence Dashboard</h1>
<p style="color: gray; margin-bottom: 40px;">
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

# Days since posted
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

df["days_since_posted"] = (
    (now_jst - df["first_seen_at"]).dt.days
).apply(format_days_ago)

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


# Recency Filter

st.sidebar.subheader("Posted")

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
    # 1. Get the max timestamp
    latest_utc = df["last_seen_at"].max()
    
    # 2. Define JST
    jst_timezone = timezone(timedelta(hours=9))
    
    # 3. Convert to python datetime and then to JST
    # We use .to_pydatetime() to avoid the pandas astimezone error
    last_updated_jst = latest_utc.to_pydatetime().astimezone(jst_timezone).strftime("%Y-%m-%d %H:%M:%S")

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Last scraper run: {last_updated_jst} JST")
    st.sidebar.caption("Made in :streamlit: by [Derek Yu](https://www.linkedin.com/in/derekhyyu/)")

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

if st.session_state.search:
    df = df[
        df["title"].str.contains(st.session_state.search, case=False, na=False)
        | df["company"].str.contains(st.session_state.search, case=False, na=False)
        | df["location"].str.contains(st.session_state.search, case=False, na=False)
    ]

# Exec Target Mode override
if target_mode:
    df = df[
        df["title"].str.contains(
            "Director|Head|VP|Principal", case=False, na=False
        )
    ]

# Apply Recency Filter

df_for_trends = df.copy()

if selected_recency != "All":
    days = TIME_FILTERS[selected_recency]
    cutoff = now_jst - timedelta(days=days)
    df = df[df["first_seen_at"] >= cutoff]

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
# Tabs Layout
# -----------------------------------

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["🔥 New", "📋 All Jobs", "🚀 Companies", "🚫 Removed", "📆 Posting Trends"]
)

display_cols = [
    "logo",
    "Priority",
    "company",
    "title",
    "location",
    "url",
    "days_since_posted",
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
                "days_since_posted": "Days Ago",
                "company": "Company",
                "title": "Title",
                "location": "Location",
                "function": "Function"
            },
            use_container_width=True,
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
            "days_since_posted": "Days Ago",
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

    df["company"] = df["company"].str.strip()

    company_stats = (
        df.groupby("company")
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
# 📆 Posting Trends Tab
# -----------------------------------

with tab5:
    st.subheader("📆 Job Posting Trends (JST)")
    st.caption("Excludes first day of each company to remove initial data spikes.")

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

        import altair as alt

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

            st.markdown("### 🔥 Peak Posting Times")

            medals = ["🥇", "🥈", "🥉"]

            for i, row in enumerate(top_slots.itertuples()):
                label = f"{row.day_of_week} at {int(row.hour)}:00 JST"
                count = int(row.count)

                st.markdown(f"{medals[i]} {label} ({count} jobs)")

