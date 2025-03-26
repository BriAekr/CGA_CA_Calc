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

# Function to securely scrape ACGA single-life rate table
def get_acga_single_life_rates():
    url = "https://www.acga-web.org/current-gift-annuity-rates"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CGAApp/1.0)"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        st.sidebar.warning("ACGA data fetch failed. Using fallback.")
        raise e

    soup = BeautifulSoup(response.text, 'html.parser')
    tables = soup.find_all('table')
    single_life_table = None
    for table in tables:
        if "Single Life" in table.get_text():
            single_life_table = table
            break

    data = []
    if single_life_table:
        rows = single_life_table.find_all('tr')
        for row in rows[1:]:
            cols = row.find_all(['td', 'th'])
            if len(cols) >= 2:
                try:
                    age = int(cols[0].get_text(strip=True))
                    rate = float(cols[1].get_text(strip=True).replace('%', ''))
                    data.append((age, rate))
                except ValueError:
                    continue

    return pd.DataFrame(data, columns=["Age", "Rate"]).set_index("Age")

# Get the current ACGA rate table
st.sidebar.info("Fetching current ACGA rates...")
try:
    rate_table = get_acga_single_life_rates()
    st.sidebar.success("ACGA rates loaded successfully")
except Exception as e:
    st.sidebar.error("Failed to fetch ACGA rates. Using fallback data.")
    rate_table = pd.DataFrame({
        "Age": list(range(60, 91)),
        "Rate": [5.2, 5.4, 5.5, 5.7, 5.9, 6.1, 6.3, 6.5, 6.7, 6.9, 7.0, 7.2, 7.4, 7.6, 7.8, 8.0, 8.1, 8.3, 8.5, 8.7, 8.9, 9.1, 9.3, 9.5, 9.7, 9.9, 10.0, 10.1, 10.1, 10.1, 10.1]
    }).set_index("Age")

# Sidebar for inputs
st.sidebar.header("Donor Info")
donor_age = int(st.sidebar.number_input("Donor Age", min_value=20, max_value=100, value=75))
joint_annuitant_age = int(st.sidebar.number_input("Joint Annuitant Age (if any)", min_value=20, max_value=100, value=0))
is_joint = st.sidebar.selectbox("Is this a Joint Annuity?", ["No", "Yes"])

st.sidebar.header("Gift Info")
gift_amount = float(st.sidebar.number_input("Gift Amount ($)", min_value=1000, value=100000))
payout_frequency = st.sidebar.selectbox("Payout Frequency", ["Annual", "Semiannual", "Quarterly", "Monthly"])
irs_7520_rate = float(st.sidebar.slider("IRS 7520 Rate (%)", 3.0, 6.0, 4.2))

# Lookup annuity rate from ACGA table
age_to_use = max(donor_age, joint_annuitant_age) if is_joint == "Yes" else donor_age
if not rate_table.empty and age_to_use in rate_table.index:
    annuity_rate = rate_table.loc[age_to_use, "Rate"]
else:
    annuity_rate = 6.0

# Determine present value factor (simplified placeholder logic)
present_value_factor = max(4.0, 20 - (age_to_use - 60)*0.3 - (irs_7520_rate - 3.0)*1.5)

# Perform calculations
annual_payout = gift_amount * (annuity_rate / 100)
required_reserve = annual_payout * present_value_factor
charitable_remainder = gift_amount - required_reserve

# Display results
st.subheader("Results")
st.write(f"**Annuity Rate (ACGA):** {annuity_rate:.2f}%")
st.write(f"**Annual Payout:** ${annual_payout:,.2f}")
st.write(f"**Present Value Factor:** {present_value_factor:.2f}")
st.write(f"**Required Reserve:** ${required_reserve:,.2f}")
st.write(f"**Charitable Remainder (Estimated Deduction):** ${charitable_remainder:,.2f}")

# Show payout schedule
if st.checkbox("Show 20-Year Payout Schedule"):
    payout_schedule = pd.DataFrame({
        "Year": list(range(1, 21)),
        "Payout ($)": [annual_payout] * 20
    })
    st.dataframe(payout_schedule)

# Show ACGA rate chart
if st.checkbox("Show ACGA Rate Chart by Age"):
    st.subheader("ACGA Suggested Annuity Rates by Age")
    fig, ax = plt.subplots()
    rate_table.reset_index().plot(x="Age", y="Rate", ax=ax, legend=False)
    ax.set_ylabel("Annuity Rate (%)")
    ax.set_xlabel("Age")
    ax.set_title("ACGA Single-Life Rates")
    st.pyplot(fig)

# PDF Export
if st.button("Export Summary as PDF"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Charitable Gift Annuity Summary", ln=True, align="C")
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"Donor Age: {donor_age}", ln=True)
    if is_joint == "Yes":
        pdf.cell(200, 10, txt=f"Joint Annuitant Age: {joint_annuitant_age}", ln=True)
    pdf.cell(200, 10, txt=f"Gift Amount: ${gift_amount:,.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Annuity Rate: {annuity_rate:.2f}%", ln=True)
    pdf.cell(200, 10, txt=f"Annual Payout: ${annual_payout:,.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Present Value Factor: {present_value_factor:.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Required Reserve: ${required_reserve:,.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Charitable Remainder: ${charitable_remainder:,.2f}", ln=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        pdf.output(tmp_file.name)
        tmp_file_path = tmp_file.name

    try:
        with open(tmp_file_path, "rb") as file:
            st.download_button(
                label="Download PDF",
                data=file,
                file_name="CGA_Summary.pdf",
                mime="application/pdf"
            )
    finally:
        os.remove(tmp_file_path)

# Footer
st.markdown("---")
st.caption("Created for educational purposes. Not legal or tax advice. Data sourced from the American Council on Gift Annuities.")
