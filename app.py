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

# --- Fetch Data ---
response = supabase.table("jobs").select("*").execute()
df = pd.DataFrame(response.data)

if df.empty:
    st.warning("No jobs found.")
    st.stop()

# Convert created_at
df["created_at"] = pd.to_datetime(df["created_at"])

# --- Filter: Last 24 Hours ---
st.subheader("🔥 New Jobs (Last 24 Hours)")
last_24 = datetime.utcnow() - timedelta(hours=24)
new_jobs = df[df["created_at"] >= last_24]

st.dataframe(new_jobs)

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
    st.dataframe(df)