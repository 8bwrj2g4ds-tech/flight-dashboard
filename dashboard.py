import os
import pandas as pd
import streamlit as st
import plotly.express as px

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

latest_scan_time = df["timestamp"].max()

import pytz

utc_time = latest_scan_time.tz_localize("UTC")

mx_time = utc_time.tz_convert("America/Mexico_City")

st.info(
    f"🕒 Last scanner update: "
    f"{mx_time.strftime('%B %d, %Y %H:%M')} (Mexico City)"
)

st.sidebar.header("Filters")

origins = st.sidebar.multiselect(
    "Origin",
    sorted(df["origin"].dropna().unique()),
    default=sorted(df["origin"].dropna().unique())
)

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
    (df["origin"].isin(origins)) &
    (df["destination"].isin(destinations)) &
    (df["cabin_class"].isin(cabins)) &
    (df["stops"].isin(stops)) &
    (df["airline"].isin(airlines)) &
    (df["lowest_price_mxn"] <= max_price)
].copy()

if filtered.empty:
    st.warning("No results match your filters.")
    st.stop()

# Advanced AI Deal Ranking
def deal_score(row):
    price = row["lowest_price_mxn"]
    cabin = row["cabin_class"]
    stops_value = row["stops"]
    airline = row["airline"]
    duration = str(row["duration"])
    departure_date = pd.to_datetime(row["departure_date"], errors="coerce")

    score = 100

    # 1. Price score
    if cabin == "economy":
        score -= price / 1000
    elif cabin == "business":
        score -= price / 3000

    # 2. Cabin value
    if cabin == "business":
        score += 15
    elif cabin == "economy":
        score += 5

    # 3. Stops
    if stops_value == "Nonstop":
        score += 20
    elif stops_value == "1 stop":
        score += 8
    elif stops_value == "2 stops":
        score -= 10
    else:
        score -= 5

    # 4. Airline quality
    premium_airlines = [
        "Air France", "KLM", "Lufthansa", "British Airways",
        "Iberia", "ANA", "JAL", "Emirates", "Qatar",
        "Turkish Airlines", "Air Canada", "Delta"
    ]

    solid_airlines = [
        "Aeromexico", "United", "American", "Air Europa", "Avianca"
    ]

    low_cost_airlines = [
        "Volaris", "Viva Aerobus"
    ]

    if airline in premium_airlines:
        score += 12
    elif airline in solid_airlines:
        score += 7
    elif airline in low_cost_airlines:
        score -= 5

    # 5. Duration
    duration_hours = 0

    if "hr" in duration:
        try:
            duration_hours = int(duration.split("hr")[0].strip())
        except:
            duration_hours = 0

    if duration_hours > 0:
        if duration_hours <= 12:
            score += 12
        elif duration_hours <= 16:
            score += 6
        elif duration_hours <= 22:
            score -= 3
        else:
            score -= 10

    # 6. Seasonality
    if pd.notna(departure_date):
        month = departure_date.month

        peak_months = [6, 7, 8, 12]
        shoulder_months = [4, 5, 9, 10]
        low_season_months = [1, 2, 3, 11]

        if month in peak_months:
            score += 8
        elif month in shoulder_months:
            score += 5
        elif month in low_season_months:
            score += 2

    return round(score, 2)

def explain_deal(row):
    reasons = []

    price = row["lowest_price_mxn"]
    cabin = row["cabin_class"]
    stops_value = row["stops"]
    airline = row["airline"]
    duration = str(row["duration"])
    departure_date = pd.to_datetime(row["departure_date"], errors="coerce")

    if cabin == "business" and price <= 50000:
        reasons.append("✅ Excellent business fare")
    elif cabin == "economy" and price <= 18000:
        reasons.append("✅ Strong economy fare")

    if stops_value == "Nonstop":
        reasons.append("✅ Nonstop flight")
    elif stops_value == "1 stop":
        reasons.append("✅ Reasonable 1-stop itinerary")

    premium_airlines = [
        "Air France", "KLM", "Lufthansa", "British Airways",
        "Iberia", "ANA", "JAL", "Emirates", "Qatar",
        "Turkish Airlines", "Air Canada", "Delta"
    ]

    if airline in premium_airlines:
        reasons.append("✅ Premium airline")

    if "hr" in duration:
        try:
            duration_hours = int(duration.split("hr")[0].strip())

            if duration_hours <= 12:
                reasons.append("✅ Short travel duration")
            elif duration_hours <= 16:
                reasons.append("✅ Reasonable travel duration")
            elif duration_hours >= 22:
                reasons.append("⚠️ Long travel duration")
        except:
            pass

    if pd.notna(departure_date):
        month = departure_date.month

        if month in [6, 7, 8, 12]:
            reasons.append("✅ Peak-season value")
        elif month in [4, 5, 9, 10]:
            reasons.append("✅ Shoulder-season value")

    if not reasons:
        reasons.append("ℹ️ Ranked based on price, stops, airline, cabin, and duration")

    return " | ".join(reasons)

filtered["deal_score"] = filtered.apply(deal_score, axis=1)
filtered["deal_explanation"] = filtered.apply(explain_deal, axis=1)

def price_trend_signal(group):
    group = group.sort_values("timestamp")

    if len(group) < 3:
        return "Not enough data"

    latest_price = group["lowest_price_mxn"].iloc[-1]
    average_price = group["lowest_price_mxn"].mean()
    min_price = group["lowest_price_mxn"].min()

    if latest_price <= min_price * 1.03:
        return "🔥 Buy now - near lowest price"
    elif latest_price <= average_price * 0.90:
        return "✅ Good - below average"
    elif latest_price >= average_price * 1.10:
        return "⏳ Wait - above average"
    else:
        return "Stable"


trend_table = (
    filtered
    .groupby(["origin", "destination", "cabin_class", "stops"])
    .apply(price_trend_signal)
    .reset_index(name="trend_signal")
)

st.subheader("🔮 Predictive Price Trends")

st.dataframe(
    trend_table,
    width="stretch"
)

st.subheader("🔥 Heat Map View")

heatmap_data = (
    filtered
    .groupby(["origin", "destination", "cabin_class"])["lowest_price_mxn"]
    .min()
    .reset_index()
)

heatmap_pivot = heatmap_data.pivot_table(
    index=["origin", "destination"],
    columns="cabin_class",
    values="lowest_price_mxn"
)

st.dataframe(
    heatmap_pivot,
    width="stretch"
)


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
            "deal_explanation",
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

st.subheader("📈 Interactive Price Trend Over Time")

price_trend_chart = px.line(
    filtered.sort_values("timestamp"),
    x="timestamp",
    y="lowest_price_mxn",
    color="cabin_class",
    line_dash="destination",
    hover_data=[
        "origin",
        "destination",
        "departure_date",
        "return_date",
        "airline",
        "stops",
        "duration"
    ],
    markers=True,
    title="Price Trend Over Time"
)

st.plotly_chart(price_trend_chart, width="stretch")


st.subheader("✈️ Interactive Airline Comparison")

airline_comparison = (
    filtered
    .groupby(["airline", "cabin_class"])["lowest_price_mxn"]
    .min()
    .reset_index()
)

airline_chart = px.bar(
    airline_comparison,
    x="airline",
    y="lowest_price_mxn",
    color="cabin_class",
    barmode="group",
    title="Cheapest Price by Airline",
    text_auto=True
)

st.plotly_chart(airline_chart, width="stretch")


st.subheader("🛑 Interactive Stop Comparison")

stop_comparison = (
    filtered
    .groupby(["stops", "cabin_class"])["lowest_price_mxn"]
    .min()
    .reset_index()
)

stop_chart = px.bar(
    stop_comparison,
    x="stops",
    y="lowest_price_mxn",
    color="cabin_class",
    barmode="group",
    title="Cheapest Price by Stops",
    text_auto=True
)

st.plotly_chart(stop_chart, width="stretch")


st.subheader("📅 Cheapest Weekday to Depart")

filtered["departure_weekday"] = pd.to_datetime(
    filtered["departure_date"],
    errors="coerce"
).dt.day_name()

weekday_order = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday"
]

weekday_prices = (
    filtered
    .groupby(["departure_weekday", "cabin_class"])["lowest_price_mxn"]
    .min()
    .reset_index()
)

weekday_prices["departure_weekday"] = pd.Categorical(
    weekday_prices["departure_weekday"],
    categories=weekday_order,
    ordered=True
)

weekday_prices = weekday_prices.sort_values("departure_weekday")

weekday_chart = px.bar(
    weekday_prices,
    x="departure_weekday",
    y="lowest_price_mxn",
    color="cabin_class",
    barmode="group",
    title="Cheapest Weekday to Depart",
    text_auto=True
)

st.plotly_chart(weekday_chart, width="stretch")

st.subheader("📄 Full Data")

st.dataframe(filtered, use_container_width=True)
