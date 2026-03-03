import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import os

# -----------------------------------
# Supabase Setup
# -----------------------------------

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Job Dashboard", layout="wide")
st.title("🧭 Job Scraper Dashboard")

# -----------------------------------
# Sidebar Filters
# -----------------------------------

remote_only = st.sidebar.checkbox("🌍 Remote Only")
japan_only = st.sidebar.checkbox("🇯🇵 Japan Only")

# -----------------------------------
# Fetch Data
# -----------------------------------

response = supabase.table("jobs").select("*").execute()
data = response.data

if not data:
    st.warning("No jobs found in database.")
    st.stop()

df = pd.DataFrame(data)

# -----------------------------------
# Column Cleanup
# -----------------------------------

columns_to_hide = ["external_id", "platform"]
df = df.drop(columns=[col for col in columns_to_hide if col in df.columns], errors="ignore")

df = df.rename(columns={"url": "Job Link"})

# Convert timestamps safely
if "first_seen_at" in df.columns:
    df["first_seen_at"] = pd.to_datetime(df["first_seen_at"], errors="coerce")

if "last_seen_at" in df.columns:
    df["last_seen_at"] = pd.to_datetime(df["last_seen_at"], errors="coerce")

# -----------------------------------
# Apply Sidebar Filters
# -----------------------------------

if remote_only and "is_remote" in df.columns:
    df = df[df["is_remote"] == True]

if japan_only and "is_japan" in df.columns:
    df = df[df["is_japan"] == True]

if df.empty:
    st.warning("No jobs match the selected filters.")
    st.stop()

# -----------------------------------
# 🔥 New Jobs Section (Last 24 Hours)
# -----------------------------------

st.subheader("🔥 New Jobs (Last 24 Hours)")

if "first_seen_at" in df.columns:
    last_24 = datetime.utcnow() - timedelta(hours=24)
    new_jobs = df[df["first_seen_at"] >= last_24]
else:
    new_jobs = pd.DataFrame()

if new_jobs.empty:
    st.info("No new jobs in the last 24 hours.")
else:
    st.dataframe(
        new_jobs.sort_values("first_seen_at", ascending=False),
        column_config={
            "Job Link": st.column_config.LinkColumn(
                "Apply",
                display_text="Open"
            )
        },
        use_container_width=True
    )

# -----------------------------------
# 🔎 Search Section
# -----------------------------------

st.subheader("🔎 Search Jobs")

search = st.text_input("Search by title, company, or location")

if search:
    filtered = df[
        df["title"].str.contains(search, case=False, na=False) |
        df["company"].str.contains(search, case=False, na=False) |
        df["location"].str.contains(search, case=False, na=False)
    ]

    if filtered.empty:
        st.info("No matching jobs found.")
    else:
        st.dataframe(
            filtered.sort_values("first_seen_at", ascending=False),
            column_config={
                "Job Link": st.column_config.LinkColumn(
                    "Apply",
                    display_text="Open"
                )
            },
            use_container_width=True
        )
else:
    st.dataframe(
        df.sort_values("first_seen_at", ascending=False),
        column_config={
            "Job Link": st.column_config.LinkColumn(
                "Apply",
                display_text="Open"
            )
        },
        use_container_width=True
    )
