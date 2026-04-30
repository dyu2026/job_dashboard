import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta, timezone
from streamlit_cookies_manager import EncryptedCookieManager
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
import streamlit.components.v1 as components
import os
import base64
import altair as alt
import uuid
import re

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
df["last_seen_at"] = pd.to_datetime(df["last_seen_at"], errors="coerce", utc=True)

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
    if row.get("is_remote"):
        if remote_scope in ["global", "apac"]:
            return "remote_allowed"

        if any(x in location for x in ["apac", "asia"]):
            return "remote_allowed"

    return "unknown"
    
df["location_class"] = df.apply(classify_location, axis=1)

df_full = df.copy()

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

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
#    ["🔥 New", "📋 All Jobs", "🚀 Companies", "❄️ Roles", "📮 Posting Trends", "🚫 Removed", ]
    [":material/fiber_new: New", 
        ":material/cards_stack: All Jobs", 
        ":material/source_environment: Companies", 
        ":material/diversity_3: Roles", 
        ":material/sticker: Posting Trends", 
        ":material/shadow_minus: Removed", ]
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

# --- Data prep ---
    df_company = df_full.copy()   # ← full dataset
    df_company["company"] = df_company["company"].str.strip()
    df_company["first_seen_at"] = pd.to_datetime(df_company["first_seen_at"], errors="coerce", utc=True)
    df_company["last_seen_at"]  = pd.to_datetime(df_company["last_seen_at"],  errors="coerce", utc=True)
    
    role_cache = (
        df_company.groupby(["company", "role"])
        .size()
        .reset_index(name="count")
    )
    role_cache_dict = {
        company: group.drop(columns="company").reset_index(drop=True)
        for company, group in role_cache.groupby("company")
    }

    # --- Company summary ---
    company_stats = (
        df_company.groupby("company")
        .agg(active_roles=("title", "count"), last_updated=("first_seen_at", "max"),)
        .reset_index()
    )

    recent_new = df_company[
        df_company["first_seen_at"] >= (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7))
    ]
    recent_counts = recent_new.groupby("company")["title"].count().reset_index(name="new_roles_7d")

    company_stats = company_stats.merge(recent_counts, on="company", how="left").fillna(0)
    company_stats["growth_rate"] = (company_stats["new_roles_7d"] / company_stats["active_roles"]) * 100
    company_stats["last_updated"] = pd.to_datetime(
        company_stats["last_updated"], utc=True, errors="coerce"
    ).dt.tz_convert("Asia/Tokyo").dt.strftime("%b %d")
    company_stats = company_stats.sort_values("active_roles", ascending=False)

    if "selected_company_table" not in st.session_state:
        st.session_state.selected_company_table = company_stats.iloc[0]["company"]
    
    # Declare placeholder
    
    st.subheader("🚀 Company Breakdown")
    
    composition_placeholder = st.empty()

    # -----------------------------------
    # 🏢 Company Table — RENDER FIRST
    # so selection is captured before chart draws
    # -----------------------------------
    st.markdown("### Companies")

    # --- Add logo to company_stats ---
    company_stats["logo"] = company_stats["company"].apply(get_base64_logo)

    # --- Rename and reorder columns ---
    display_df = company_stats.rename(columns={
        "company": "Company",
        "active_roles": "Active Roles",
        "new_roles_7d": "7D New Roles",
        "growth_rate": "Growth %",
        "last_updated": "Last Updated",
    })

    display_df = display_df[[
        "logo", "Company", "Active Roles", "7D New Roles", "Growth %", "Last Updated"
    ]]

    # --- AgGrid config ---
    logo_renderer = JsCode("""
        class LogoRenderer {
            init(params) {
                this.eGui = document.createElement('div');
                this.eGui.style.display = 'flex';
                this.eGui.style.alignItems = 'center';
                this.eGui.style.height = '100%';
                if (params.value) {
                    const img = document.createElement('img');
                    img.src = params.value;
                    img.style.height = '32px';
                    img.style.width = '32px';
                    img.style.objectFit = 'contain';
                    img.style.borderRadius = '6px';
                    this.eGui.appendChild(img);
                }
            }
            getGui() { return this.eGui; }
        }
    """)

    gb = GridOptionsBuilder.from_dataframe(display_df)

    # Left-align all columns by default
    gb.configure_default_column(
        cellStyle={"textAlign": "left", "fontSize": "15px", "paddingTop": "10px", "paddingBottom": "10px"},
        headerClass="ag-left-aligned-header",
    )

    gb.configure_grid_options(rowHeight=42, headerHeight=42,) 

    gb.configure_column("logo", header_name="", cellRenderer=logo_renderer, width=50, pinned="left", sortable=False, filter=False)
    gb.configure_column("Company", pinned="left", width=160)
    gb.configure_column("Active Roles", width=120, cellStyle={"textAlign": "left"}, headerClass="ag-left-aligned-header",)
    gb.configure_column("7D New Roles", width=120, cellStyle={"textAlign": "left"}, headerClass="ag-left-aligned-header",)
    gb.configure_column("Growth %", width=120, valueFormatter="x.toFixed(1) + '%'", 
        cellStyle={"textAlign": "left"}, headerClass="ag-left-aligned-header",
    )
    gb.configure_column("Last Updated", width=120)
    gb.configure_selection("single", use_checkbox=False)
    gb.configure_pagination(paginationPageSize=10)

    grid = AgGrid(
        display_df,
        gridOptions=gb.build(),
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        height=600,
        fit_columns_on_grid_load=False,   # False so our explicit widths are respected
        allow_unsafe_jscode=True,         # required for JsCode renderer
        custom_css={
            ".ag-header-cell-text": {"font-size": "13px !important"},
            ".ag-cell": {"font-size": "13px !important"},
            ".ag-left-aligned-header .ag-header-cell-label": {"flex-direction": "row !important"},
        }
    )

    selected_rows = grid.get("selected_rows")
    if selected_rows is None:
        selected_rows = []
    elif isinstance(selected_rows, pd.DataFrame):
        selected_rows = selected_rows.to_dict("records")

    if len(selected_rows) > 0:
        new_selection = selected_rows[0]["Company"]
        if new_selection != st.session_state.selected_company_table:
            st.session_state.selected_company_table = new_selection

    # -----------------------------------
    # 📊 Role Composition
    # Fills the placeholder declared above — appears above the table visually
    # -----------------------------------
    selected_company = st.session_state.selected_company_table

    with composition_placeholder.container():
        if selected_company:
            role_df = role_cache_dict.get(selected_company, pd.DataFrame(columns=["role", "count"]))

            if role_df.empty:
                st.info(f"No role data for {selected_company}.")
            else:
                role_df = role_df.sort_values("count", ascending=False)

                top5 = role_df.head(5)
                rest = role_df.iloc[5:]
                if not rest.empty:
                    other_row = pd.DataFrame([{
                        "role": f"+ {len(rest)} more",
                        "count": rest["count"].sum(),
                    }])
                    role_stats = pd.concat([top5, other_row], ignore_index=True)
                else:
                    role_stats = top5.copy()

                role_stats["pct"] = role_stats["count"] / role_stats["count"].sum()
                role_stats["_y"] = "roles"
                role_stats["sort_order"] = range(len(role_stats))
                role_stats.loc[role_stats["role"].str.startswith("+"), "sort_order"] = 999
                role_order = role_stats["role"].tolist()

                chart = (
                    alt.Chart(role_stats)
                    .mark_bar(
                        cornerRadiusTopLeft=12,
                        cornerRadiusBottomLeft=12,
                        cornerRadiusTopRight=12,
                        cornerRadiusBottomRight=12,
                    )
                    .encode(
                        x=alt.X("pct:Q", stack="normalize", axis=None),
                        y=alt.Y("_y:N", axis=None),
                        color=alt.Color(
                            "role:N",
                            sort=role_order,
                            scale=alt.Scale(
                                domain=role_order,
                                range=["#ff4d6b", "#1b4e6b", "#f4ab33", "#c068a8", "#ec7176", "#5c63a2"],
                            ),
                            legend=alt.Legend(
                                orient="bottom",
                                direction="horizontal",
                                title=None,
                                columns=3,
                                symbolSize=100,
                                symbolType="circle",
                                labelFontSize=14,
                                columnPadding=20,
                                padding=0,
                            ),
                        ),
                        order=alt.Order("sort_order:Q", sort="ascending"),
                        tooltip=[
                            alt.Tooltip("role:N", title="Role"),
                            alt.Tooltip("count:Q", title="Roles"),
                            alt.Tooltip("pct:Q", title="Share", format=".0%"),
                        ],
                    )
                    .properties(height=240)
                )

                st.markdown(
                    f"""
                    <p style="font-size:18px; margin-top:10px;">
                        <b>{selected_company}</b> — Role Composition · hover a segment for details
                    </p>
                    """,
                    unsafe_allow_html=True
                )
                st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Select a company to see role composition.")

# -----------------------------------
# Role Insights Tab
# -----------------------------------

with tab4:
    
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

# -----------------------------------
# Posting Trends Tab
# -----------------------------------

with tab5:
    
    # -----------------------------------
    # 📅 Weekly Posting Trends
    # -----------------------------------

    st.subheader("📮 Weekly Posting Trends")
    st.markdown("""
    <p style="color: gray; margin-bottom: 30px; font-size: 14px;">
    New roles detected per week, grouped by calendar week start (JST).<br>
    Excludes first day of each company to remove initial data spikes.
    </p>
    """, unsafe_allow_html=True)

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
        import altair as alt
        from datetime import datetime, timedelta, timezone

        JST = timezone(timedelta(hours=9))

        df = trend_df.copy()

        # --- 🛡️ Resolve timestamp column safely ---
        if "first_seen_at" in df.columns:
            ts_col = "first_seen_at"
        elif "timestamp" in df.columns:
            ts_col = "timestamp"
        elif "created_at" in df.columns:
            ts_col = "created_at"
        else:
            st.error("No valid timestamp column found.")
            st.stop()

        # --- Convert to JST ---
        df["timestamp"] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
        df["timestamp"] = df["timestamp"].dt.tz_convert(JST)

        df = df.dropna(subset=["timestamp"])

        df["date"] = df["timestamp"].dt.date

        # --- Exclude first day per company ---
        first_seen = df.groupby("company")["date"].transform("min")
        df = df[df["date"] > first_seen]

        # --- Apply time window (JST aligned) ---
        today = datetime.now(JST).date()
        cutoff = today - timedelta(days=time_window)

        df = df[df["date"] >= cutoff]

        if df.empty:
            st.info("No data available after filtering.")
        else:
            # --- Weekly buckets (Sunda start) ---
            df["week_start"] = pd.to_datetime(df["date"]) - pd.to_timedelta(
                (pd.to_datetime(df["date"]).dt.weekday + 1) % 7, unit="d"
            )

            weekly_counts = (
                df.groupby("week_start")
                .size()
                .reset_index(name="count")
                .sort_values("week_start")
            )

            # --- Chart ---
            weekly_counts["label"] = weekly_counts["week_start"].dt.strftime("%b %d")

            # Pass explicit label order to Altair so it never re-sorts alphabetically
            label_order = weekly_counts["label"].tolist()

            bar_chart = alt.Chart(weekly_counts).mark_bar(color="#ff4d6b").encode(
                x=alt.X("label:N", sort=label_order, title=None),
                y=alt.Y("count:Q", title="New roles"),
                tooltip=[
                    alt.Tooltip("label:N", title="Week of"),
                    alt.Tooltip("count:Q", title="New roles"),
                ],
            )

            st.altair_chart(bar_chart, use_container_width=True)
                
    
    st.subheader("Most Active Posting Days")
    st.markdown("""
    <p style="color: gray; margin-bottom: 30px; font-size: 14px;">
    Which days of the week new roles are most frequently detected.<br>
    Excludes first day of each company to remove initial data spikes.
    </p>
    """, unsafe_allow_html=True)

    if trend_df.empty:
        st.info("Not enough data to show trends.")
    else:
        # -----------------------------------
        # Day-of-week bar chart
        # -----------------------------------
#        st.bar_chart(day_counts, color="#ff4d6b")

        day_bar_df = day_counts.reset_index()
        day_bar_df.columns = ["day_of_week", "count"]

        day_bar = alt.Chart(day_bar_df).mark_bar(
            color="#ff4d6b"
        ).encode(
            x=alt.X(
                "day_of_week:N",
                sort=day_order,
                title=None,
                scale=alt.Scale(paddingInner=0.15),
                axis=alt.Axis(labelAngle=0, ticks=False, domain=False, grid=False),
            ),
            y=alt.Y(
                "count:Q",
                title="New roles",
                axis=alt.Axis(grid=True, gridColor="#f0f0f0", domain=False, ticks=False),
            ),
            tooltip=[
                alt.Tooltip("day_of_week:N", title="Day"),
                alt.Tooltip("count:Q", title="New roles"),
            ],
        )

        st.altair_chart(day_bar, use_container_width=True)

        # -----------------------------------
        # Heatmap (Day x Hour)
        # -----------------------------------

        # Format hour labels (1:00, 2:00, etc.)
        heatmap_data["hour_label"] = heatmap_data["hour"].apply(lambda x: f"{x}:00")

        # Ensure correct hour order
        hour_order = [f"{i}:00" for i in range(24)]
        
        st.subheader("New Job Detection Heatmap")
        st.markdown("""
        <p style="color: gray; margin-bottom: 30px; font-size: 14px;">
        When new roles are first detected by day and hour (JST)<br>
        Excludes first day of each company to remove initial data spikes.
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
# 🗑 Removed Jobs Tab
# -----------------------------------

with tab6:
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
