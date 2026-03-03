import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import os

# Load secrets
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("🧭 Job Scraper Dashboard")

remote_only = st.sidebar.checkbox("🌍 Remote Only")
japan_only = st.sidebar.checkbox("🇯🇵 Japan Only")

# --- Fetch Data ---
response = supabase.table("jobs").select("*").execute()
df = pd.DataFrame(response.data)

# Remove technical columns
columns_to_hide = ["external_id", "posted_at", "platform"]
df = df.drop(columns=[col for col in columns_to_hide if col in df.columns])
df = df.rename(columns={"url": "Job Link"})

# --- Apply Filters ---
if remote_only:
    df = df[df["is_remote"] == True]

if japan_only:
    df = df[df["is_japan"] == True]

if df.empty:
    st.warning("No jobs found.")
    st.stop()

# Convert created_at
df["first_seen_at"] = pd.to_datetime(df["first_seen_at"])

# --- Filter: Last 24 Hours ---
st.subheader("🔥 New Jobs (Last 24 Hours)")
last_24 = datetime.utcnow() - timedelta(hours=24)
new_jobs = df[df["first_seen_at"] >= last_24]

st.dataframe(
    new_jobs,
    column_config={
        "Job Link": st.column_config.LinkColumn(
            "Apply",
            display_text="Open"
        )
    },
    use_container_width=True
)

# --- Search ---
st.subheader("🔎 Search Jobs")

search = st.text_input("Search by title, company, or location")

if search:
    filtered = df[
        df["title"].str.contains(search, case=False, na=False) |
        df["company"].str.contains(search, case=False, na=False) |
        df["location"].str.contains(search, case=False, na=False)
    ]
    st.dataframe(filtered)
else:
    st.dataframe(
        df,
        column_config={
            "Job Link": st.column_config.LinkColumn(
                "Apply",
                display_text="Open"
            )
        },
        use_container_width=True
    )

