import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
from fpdf import FPDF
import tempfile
import os

# Set page configuration
st.set_page_config(page_title="Charitable Gift Annuity Calculator", layout="centered")
st.title("Charitable Gift Annuity (CGA) Calculator")

# Scrape ACGA single-life rates
def get_acga_single_life_rates():
    url = "https://www.acga-web.org/current-gift-annuity-rates"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CGAApp/1.0)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        st.sidebar.warning("ACGA data fetch failed. Using fallback.")
        return pd.DataFrame()
    soup = BeautifulSoup(response.text, 'html.parser')
    tables = soup.find_all('table')
    single_table = next((t for t in tables if "Single Life" in t.get_text()), None)
    if not single_table:
        return pd.DataFrame()
    data = []
    for row in single_table.find_all("tr")[1:]:
        cols = row.find_all(["td", "th"])
        if len(cols) >= 2:
            try:
                age = int(cols[0].text.strip())
                rate = float(cols[1].text.strip().replace('%', ''))
                data.append((age, rate))
            except:
                continue
    return pd.DataFrame(data, columns=["Age", "Rate"]).set_index("Age")

# Scrape ACGA joint-life rates
def get_acga_joint_life_rates():
    url = "https://www.acga-web.org/current-gift-annuity-rates"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CGAApp/1.0)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        st.sidebar.warning("Joint ACGA table fetch failed.")
        return pd.DataFrame()
    soup = BeautifulSoup(response.text, 'html.parser')
    tables = soup.find_all('table')
    joint_table = next((t for t in tables if "Two Lives" in t.get_text()), None)
    if not joint_table:
        return pd.DataFrame()
    headers = joint_table.find_all("tr")[0].find_all("th")[1:]
    age2_vals = [int(h.text.strip()) for h in headers]
    rows = joint_table.find_all("tr")[1:]
    data = []
    for r in rows:
        cols = r.find_all(["td", "th"])
        if not cols:
            continue
        try:
            age1 = int(cols[0].text.strip())
            for j, c in enumerate(cols[1:]):
                rate = float(c.text.strip().replace('%', ''))
                data.append((age1, age2_vals[j], rate))
        except:
            continue
    return pd.DataFrame(data, columns=["Age1", "Age2", "Rate"]).set_index(["Age1", "Age2"])

# Load factor tables
@st.cache_data
def load_annuity_factors():
    return pd.read_csv("annuity_factors.csv").set_index("Age")

@st.cache_data
def load_joint_annuity_factors():
    return pd.read_csv("joint_annuity_factors.csv").set_index(["Age1", "Age2"])

rate_table = get_acga_single_life_rates()
joint_rate_table = get_acga_joint_life_rates()
annuity_factors_df = load_annuity_factors()
joint_annuity_factors_df = load_joint_annuity_factors()

# Sidebar Inputs
st.sidebar.header("Donor Info")
donor_age = st.sidebar.number_input("Donor Age", min_value=20, max_value=100, value=75)
joint_annuitant_age = st.sidebar.number_input("Joint Annuitant Age (if any)", min_value=20, max_value=100, value=67)
is_joint = st.sidebar.selectbox("Is this a Joint Annuity?", ["No", "Yes"])

st.sidebar.header("Gift Info")
gift_amount = st.sidebar.number_input("Gift Amount ($)", min_value=1000, value=100000)
payout_frequency = st.sidebar.selectbox("Payout Frequency", ["Annual", "Semiannual", "Quarterly", "Monthly"])
irs_7520_rate = st.sidebar.slider("IRS 7520 Rate (%)", 3.0, 6.0, 4.2)

# Get annuity rate
if is_joint == "Yes" and not joint_rate_table.empty:
    rate_row = joint_rate_table.loc[(donor_age, joint_annuitant_age)] if (donor_age, joint_annuitant_age) in joint_rate_table.index else None
    annuity_rate = rate_row["Rate"] if rate_row is not None else 6.0
else:
    annuity_rate = rate_table.loc[donor_age, "Rate"] if donor_age in rate_table.index else 6.0

# IRS factor lookup
rate_column = f"Rate_{irs_7520_rate:.1f}"
if is_joint == "Yes" and (donor_age, joint_annuitant_age) in joint_annuity_factors_df.index:
    annuity_factor = joint_annuity_factors_df.loc[(donor_age, joint_annuitant_age), rate_column]
elif is_joint == "No" and donor_age in annuity_factors_df.index:
    annuity_factor = annuity_factors_df.loc[donor_age, rate_column]
else:
    annuity_factor = 9.0
    st.warning("Annuity factor fallback value used. Check IRS table coverage.")

frequency_adjustments = {
    "Annual": 1.0,
    "Semiannual": 0.975,
    "Quarterly": 0.96,
    "Monthly": 0.945
}
adjustment = frequency_adjustments.get(payout_frequency, 1.0)

# Final calculations
annual_payout = gift_amount * annuity_rate / 100
adjusted_annuity_factor = annuity_factor * adjustment
estimated_deduction = annual_payout * adjusted_annuity_factor

# Display results
st.subheader("Results")
st.write(f"**Annuity Rate (ACGA):** {annuity_rate:.2f}%")
st.write(f"**Annual Payout:** ${annual_payout:,.2f}")
st.write(f"**IRS Annuity Factor:** {annuity_factor:.2f}  ")
st.caption("Source: IRS Publication 1457, Table S (Single Life) or Joint Life")
st.write(f"**Frequency Adjustment Multiplier:** {adjustment:.3f}")
st.write(f"**Adjusted Annuity Factor:** {adjusted_annuity_factor:.2f}")
st.write(f"**Estimated Charitable Deduction (IRS-Based):** ${estimated_deduction:,.2f}")

# PDF Export Button
if st.button("Export Summary as PDF"):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.set_title("CGA Summary")

        pdf.cell(200, 10, txt="Charitable Gift Annuity Summary", ln=True, align="C")
        pdf.ln(5)
        pdf.cell(200, 10, txt=f"Donor Age: {donor_age}", ln=True)
        if is_joint == "Yes":
            pdf.cell(200, 10, txt=f"Joint Annuitant Age: {joint_annuitant_age}", ln=True)
        pdf.cell(200, 10, txt=f"Gift Amount: ${gift_amount:,.2f}", ln=True)
        pdf.cell(200, 10, txt=f"Annuity Rate: {annuity_rate:.2f}%", ln=True)
        pdf.cell(200, 10, txt=f"Annual Payout: ${annual_payout:,.2f}", ln=True)
        pdf.cell(200, 10, txt=f"IRS Annuity Factor: {annuity_factor:.2f}", ln=True)
        pdf.cell(200, 10, txt=f"Adjustment for {payout_frequency} Payments: x{adjustment:.3f}", ln=True)
        pdf.cell(200, 10, txt=f"Adjusted Factor: {adjusted_annuity_factor:.2f}", ln=True)
        pdf.cell(200, 10, txt=f"Estimated Deduction: ${estimated_deduction:,.2f}", ln=True)
        pdf.ln(5)
        pdf.set_font("Arial", style="I", size=10)
        pdf.multi_cell(0, 10, "Annuity factors based on IRS Publication 1457, Table S (Single Life) or Joint Life equivalents. This is an estimate and not legal or tax advice.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf.output(tmp_file.name)
            tmp_file_path = tmp_file.name

        with open(tmp_file_path, "rb") as file:
            st.download_button(
                label="Download PDF",
                data=file,
                file_name="CGA_Summary.pdf",
                mime="application/pdf"
            )
    except Exception as e:
        st.error(f"PDF generation failed: {str(e)}")
    finally:
        if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)

# Display full annuity factor table
if st.checkbox("Show Full IRS Annuity Factor Table"):
    st.subheader("Single-Life Annuity Factors")
    st.dataframe(annuity_factors_df.style.format("{:.2f}"))
    st.subheader("Joint-Life Annuity Factors")
    st.dataframe(joint_annuity_factors_df.style.format("{:.2f}"))
