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

email_pattern = st.selectbox(
    "Email Format",
    options=[
        "firstname.lastname",
        "firstname.lastinitial",
        "firstinitial.lastname",
        "firstinitial.lastinitial",
        "firstname",
        "lastname.firstname",
    ]
)

separator = st.selectbox(
    "Separator",
    options=[".", "_", ""]
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
    "Upload existing companies.xlsx (optional)",
    type=["xlsx"]
)

# Live preview of email format
sample_first, sample_last = "john", "doe"
sample_fi, sample_li = sample_first[:1], sample_last[:1]
_preview_map = {
    "firstname.lastname": f"{sample_first}{separator}{sample_last}",
    "firstname.lastinitial": f"{sample_first}{separator}{sample_li}",
    "firstinitial.lastname": f"{sample_fi}{separator}{sample_last}",
    "firstinitial.lastinitial": f"{sample_fi}{separator}{sample_li}",
    "firstname": sample_first,
    "lastname.firstname": f"{sample_last}{separator}{sample_first}",
}
preview_domain = email_suffix.lower() if email_suffix else "@company.com"
st.caption(f"Preview: `{_preview_map.get(email_pattern, '')}{preview_domain}`")

# -----------------------------
# HR ROLE FILTER KEYWORDS
# -----------------------------
HR_KEYWORDS = [
    "hr", "human resource", "talent acquisition", "recruiter",
    "recruitment", "people operations", "hrbp", "hiring manager",
    "ta specialist", "people partner"
]

def is_hr_role(position):
    if not isinstance(position, str):
        return False
    pos = position.lower()
    return any(kw in pos for kw in HR_KEYWORDS)

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
# EMAIL BUILDER
# -----------------------------
def build_email(first, last, pattern, sep, domain):
    first = (first or "").lower()
    last = (last or "").lower()
    fi, li = first[:1], last[:1]
    mapping = {
        "firstname.lastname": f"{first}{sep}{last}",
        "firstname.lastinitial": f"{first}{sep}{li}",
        "firstinitial.lastname": f"{fi}{sep}{last}",
        "firstinitial.lastinitial": f"{fi}{sep}{li}",
        "firstname": first,
        "lastname.firstname": f"{last}{sep}{first}",
    }
    return f"{mapping.get(pattern, f'{first}{sep}{last}')}{domain}"

# -----------------------------
# SCRAPER
# -----------------------------
def scrape_profiles(company, location, pages):
    rows = []
    query = (
        f'site:linkedin.com/in ({company}) '
        '("HR" OR "Human Resources" OR "Talent Acquisition" OR "Recruiter" '
        'OR "Recruitment" OR "People Operations" OR "Hiring Manager" '
        'OR "HRBP" OR "TA Specialist") '
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

    if not all([company_name, email_suffix, location]):
        st.error("Company name, domain, and location are required")
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

    # Keep only HR-related roles
    df = df[df["position"].apply(is_hr_role)]

    if df.empty:
        st.warning("No HR/Recruiter profiles found after filtering")
        st.stop()

    df["email"] = df.apply(
        lambda r: build_email(r["first_name"], r["last_name"], email_pattern, separator, email_suffix.lower()),
        axis=1
    )

    # -----------------------------
    # EMAIL VALIDATION
    # -----------------------------
    validation_results = df["email"].apply(validate_email)
    df["validation_status"] = validation_results.apply(lambda x: x[0])
    df["confidence"] = validation_results.apply(lambda x: x[1])

    # -----------------------------
    # SAVE UPDATED EXCEL (upload optional)
    # -----------------------------
    if uploaded_excel:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(uploaded_excel.getbuffer())
            temp_path = tmp.name
        writer_kwargs = dict(mode="a", if_sheet_exists="replace")
    else:
        temp_path = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx").name
        writer_kwargs = dict(mode="w")

    with pd.ExcelWriter(
        temp_path,
        engine="openpyxl",
        **writer_kwargs
    ) as writer:
        df.to_excel(writer, sheet_name=company_name[:31], index=False)

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

    # -----------------------------
    # MOBILE-FRIENDLY COPY
    # -----------------------------
    st.markdown("### Copy emails")
    st.code("\n".join(df["email"]), language=None)

    with st.expander("Copy individually"):
        for email in df["email"]:
            st.code(email, language=None)
