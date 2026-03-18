# Japan Tech Job Tracker

This job tracking dashboard is built with Streamlit and Supabasea and is a personal project that aggregates publicly available job listings from selected global tech companies and tracks roles relevant to Japan.
Designed for product-focused professionals in Japan/APAC, this tool aggregates job postings, highlights new opportunities, and surfaces hiring signals, all in one place.

It is not affiliated with any companies or job platforms.
The project only accesses publicly available endpoints and does not bypass authentication or paywalls.

---

## Smart Job Filtering

Search across title, company, and location

Filter by:
* Remote roles
* Japan-based roles
* Product / Web / Ecommerce functions
* Seniority levels (Manager → VP)
* Specific companies

---

## Insights
* “New in last 24 hours” detection
* “New today (JST)” tracking
* Company-level job breakdowns

---

## Priority Tagging
Automatically tags roles:
* Exec (Director, VP, Head)
* Senior

---

## LinkedIn Hiring Signals
* Surfaces hiring-related LinkedIn posts from the past 7 days

---


## Tech Stack

* Frontend: Streamlit
* Backend / DB: Supabase
* Data Processing: Pandas
* Styling: Custom CSS
* Hosting: Streamlit Cloud

---

## Project Structure

```
. 
├── app.py             # Main Streamlit app 
├── style.css          # Custom UI styling 
├── logos/             # Company logos (webp format) 
├── requirements.txt   # Python dependencies 
└── README.md

```

---

## Data Pipeline (High-Level)

1. Scrapers pull job postings from multiple company career pages
2. Data is normalized and stored in Supabase
3. Dashboard queries active + historical job data
4. UI applies filters and highlights insights in real-time

---

## Disclaimer

This project collects publicly available job listings from company career pages for personal tracking and research purposes.

All job data belongs to the respective companies.
This project is not affiliated with or endorsed by any of the companies referenced.

---

## License

MIT License
