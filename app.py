import streamlit as st
from serpapi.google_search import GoogleSearch
import pandas as pd
import tempfile
import os
import re
import dns.resolver

# -----------------------------
# PAGE CONFIG
# -----------------------------
st.set_page_config(page_title="Company Email Scraper", layout="centered")
st.title("📧 Company Email Scraper (Validated)")

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# -----------------------------
# INPUTS
# -----------------------------
company_name = st.text_input("Company Name", placeholder="LTIMindtree")

email_suffix = st.text_input(
    "Email Domain",
    placeholder="@ltimindtree.com"
)

separator = st.selectbox(
    "First–Last Name Separator",
    options=[".", "_"]
)

location = st.text_input(
    "Location (City)",
    placeholder="Mumbai"
)

pages = st.number_input(
    "Number of Google Pages",
    min_value=1,
    max_value=20,
    value=3
)

uploaded_excel = st.file_uploader(
    "Upload existing companies.xlsx",
    type=["xlsx"]
)

# -----------------------------
# EMAIL VALIDATION FUNCTIONS
# -----------------------------

def validate_syntax(email):
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def validate_mx(domain):
    try:
        records = dns.resolver.resolve(domain, "MX")
        return len(records) > 0
    except:
        return False


def validate_email(email):
    if not validate_syntax(email):
        return "Invalid Syntax", "Low"

    domain = email.split("@")[1]

    if validate_mx(domain):
        return "Valid Domain", "High"
    else:
        return "No MX Record", "Medium"


# -----------------------------
# SCRAPER
# -----------------------------
def scrape_profiles(company, location, pages):
    rows = []

    query = (
        f'site:linkedin.com/in ({company}) '
        '("HR" OR "Recruiter" OR "Talent" OR "Hiring" OR "Manager") '
        f'("{location}")'
    )

    progress = st.progress(0)

    for page in range(pages):
        params = {
            "engine": "google",
            "q": query,
            "start": page * 10,
            "num": 10,
            "api_key": SERPAPI_KEY
        }

        search = GoogleSearch(params)
        results = search.get_dict()

        for r in results.get("organic_results", []):
            title = r.get("title")
            link = r.get("link")

            if title and "-" in title:
                rows.append({"Title": title, "Link": link})

        progress.progress((page + 1) / pages)

    return pd.DataFrame(rows).drop_duplicates()


# -----------------------------
# MAIN ACTION
# -----------------------------
if st.button("Scrape & Validate Emails"):

    if not all([company_name, email_suffix, location, uploaded_excel]):
        st.error("All inputs are required")
        st.stop()

    if not SERPAPI_KEY:
        st.error("SERPAPI_KEY not set")
        st.stop()

    with st.spinner("Scraping LinkedIn profiles..."):
        df = scrape_profiles(company_name, location, pages)

    if df.empty:
        st.warning("No profiles found")
        st.stop()

    # -----------------------------
    # PROCESS DATA
    # -----------------------------
    df["full_name"] = df["Title"].str.split("-").str[0].str.strip()
    df["position"] = df["Title"].str.split("-").str[1].str.strip()

    df["first_name"] = df["full_name"].str.split(" ").str[0]
    df["last_name"] = df["full_name"].str.split(" ").str[-1]

    df["email"] = (
        df["first_name"].str.lower()
        + separator
        + df["last_name"].str.lower()
        + email_suffix.lower()
    )

    # -----------------------------
    # EMAIL VALIDATION
    # -----------------------------
    validation_results = df["email"].apply(validate_email)
    df["validation_status"] = validation_results.apply(lambda x: x[0])
    df["confidence"] = validation_results.apply(lambda x: x[1])

    # -----------------------------
    # SAVE UPDATED EXCEL
    # -----------------------------
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded_excel.getbuffer())
        temp_path = tmp.name

    with pd.ExcelWriter(
        temp_path,
        engine="openpyxl",
        mode="a",
        if_sheet_exists="replace"
    ) as writer:
        df.to_excel(writer, sheet_name=company_name, index=False)

    # -----------------------------
    # DOWNLOAD BUTTON
    # -----------------------------
    with open(temp_path, "rb") as f:
        st.download_button(
            label="⬇️ Download Updated companies.xlsx",
            data=f,
            file_name="companies.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.success(f"Saved validated emails to sheet: {company_name}")

    st.metric("Emails Generated", len(df))

    st.dataframe(
        df[
            [
                "first_name",
                "last_name",
                "email",
                "validation_status",
                "confidence",
                "position",
            ]
        ]
    )
