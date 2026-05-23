import os
import pandas as pd
import streamlit as st

CSV_FILE = "flight_results.csv"

st.set_page_config(page_title="Flight Deal Dashboard", layout="wide")

st.title("✈️ Flight Deal Dashboard")
st.caption("Flexible date scanner, cabin comparison, airline filters, and AI-style deal finder.")

if not os.path.exists(CSV_FILE):
    st.error("flight_results.csv not found. Run flight_alert.py first.")
    st.stop()

df = pd.read_csv(CSV_FILE)

if df.empty:
    st.warning("flight_results.csv exists but has no data yet.")
    st.stop()

df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df["lowest_price_mxn"] = pd.to_numeric(df["lowest_price_mxn"], errors="coerce")
df["trip_length_days"] = pd.to_numeric(df["trip_length_days"], errors="coerce")

st.sidebar.header("Filters")

destinations = st.sidebar.multiselect(
    "Destination",
    sorted(df["destination"].dropna().unique()),
    default=sorted(df["destination"].dropna().unique())
)

cabins = st.sidebar.multiselect(
    "Cabin Class",
    sorted(df["cabin_class"].dropna().unique()),
    default=sorted(df["cabin_class"].dropna().unique())
)

stops = st.sidebar.multiselect(
    "Stops",
    sorted(df["stops"].dropna().unique()),
    default=sorted(df["stops"].dropna().unique())
)

airlines = st.sidebar.multiselect(
    "Airline",
    sorted(df["airline"].dropna().unique()),
    default=sorted(df["airline"].dropna().unique())
)

max_price = st.sidebar.slider(
    "Maximum Price MXN",
    min_value=0,
    max_value=int(df["lowest_price_mxn"].max()),
    value=int(df["lowest_price_mxn"].max()),
    step=1000
)

filtered = df[
    (df["destination"].isin(destinations)) &
    (df["cabin_class"].isin(cabins)) &
    (df["stops"].isin(stops)) &
    (df["airline"].isin(airlines)) &
    (df["lowest_price_mxn"] <= max_price)
].copy()

if filtered.empty:
    st.warning("No results match your filters.")
    st.stop()

# Deal score
def deal_score(row):
    price = row["lowest_price_mxn"]
    cabin = row["cabin_class"]
    stops_value = row["stops"]

    score = 100

    score -= price / 1000

    if cabin == "business":
        score += 20

    if stops_value == "Nonstop":
        score += 15
    elif stops_value == "1 stop":
        score += 5

    return round(score, 2)


filtered["deal_score"] = filtered.apply(deal_score, axis=1)

st.subheader("📌 Summary")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Cheapest Price", f"MX${filtered['lowest_price_mxn'].min():,.0f}")
col2.metric("Average Price", f"MX${filtered['lowest_price_mxn'].mean():,.0f}")
col3.metric("Search Results", len(filtered))
col4.metric("Destinations", filtered["destination"].nunique())

st.subheader("🤖 AI Destination Finder")

business_under_50k = filtered[
    (filtered["cabin_class"] == "business") &
    (filtered["lowest_price_mxn"] <= 50000)
].sort_values("lowest_price_mxn")

nonstop_deals = filtered[
    filtered["stops"] == "Nonstop"
].sort_values("lowest_price_mxn")

best_overall = filtered.sort_values("deal_score", ascending=False)

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("### 💼 Best Business Under MX$50k")
    if business_under_50k.empty:
        st.info("No business class deals under MX$50k found.")
    else:
        deal = business_under_50k.iloc[0]
        st.success(
            f"{deal['origin']} → {deal['destination']}\n\n"
            f"MX${deal['lowest_price_mxn']:,.0f}\n\n"
            f"{deal['departure_date']} to {deal['return_date']}\n\n"
            f"{deal['airline']} | {deal['stops']} | {deal['duration']}"
        )
        st.link_button("Open Google Flights", deal["url"])

with col_b:
    st.markdown("### 🛫 Best Nonstop Deal")
    if nonstop_deals.empty:
        st.info("No nonstop deals found.")
    else:
        deal = nonstop_deals.iloc[0]
        st.success(
            f"{deal['origin']} → {deal['destination']}\n\n"
            f"MX${deal['lowest_price_mxn']:,.0f}\n\n"
            f"{deal['departure_date']} to {deal['return_date']}\n\n"
            f"{deal['cabin_class'].title()} | {deal['airline']} | {deal['duration']}"
        )
        st.link_button("Open Google Flights", deal["url"])

with col_c:
    st.markdown("### 🏆 Best Overall Deal")
    deal = best_overall.iloc[0]
    st.success(
        f"{deal['origin']} → {deal['destination']}\n\n"
        f"Score: {deal['deal_score']}\n\n"
        f"MX${deal['lowest_price_mxn']:,.0f}\n\n"
        f"{deal['cabin_class'].title()} | {deal['airline']} | {deal['stops']}"
    )
    st.link_button("Open Google Flights", deal["url"])

st.subheader("🏆 Top 15 Deals Ranked by AI Score")

top_ranked = filtered.sort_values("deal_score", ascending=False).head(15)

st.dataframe(
    top_ranked[
        [
            "deal_score",
            "timestamp",
            "origin",
            "destination",
            "departure_date",
            "return_date",
            "trip_length_days",
            "cabin_class",
            "lowest_price_mxn",
            "airline",
            "stops",
            "duration",
            "url"
        ]
    ],
    use_container_width=True
)

st.subheader("💺 Economy vs Business Comparison")

comparison = (
    filtered
    .groupby(["destination", "cabin_class"])["lowest_price_mxn"]
    .min()
    .reset_index()
)

st.bar_chart(
    comparison,
    x="destination",
    y="lowest_price_mxn",
    color="cabin_class"
)

st.subheader("✈️ Cheapest Price by Airline")

airline_chart = (
    filtered
    .groupby("airline")["lowest_price_mxn"]
    .min()
    .sort_values()
)

st.bar_chart(airline_chart)

st.subheader("🛑 Cheapest Price by Stops")

stops_chart = (
    filtered
    .groupby("stops")["lowest_price_mxn"]
    .min()
    .sort_values()
)

st.bar_chart(stops_chart)

st.subheader("📈 Price History")

history = filtered.sort_values("timestamp")

st.line_chart(
    history,
    x="timestamp",
    y="lowest_price_mxn",
    color="cabin_class"
)

st.subheader("📄 Full Data")

st.dataframe(filtered, use_container_width=True)