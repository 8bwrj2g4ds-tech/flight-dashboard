import os
import pytz
import pandas as pd
import streamlit as st
import plotly.express as px

CSV_FILE = "flight_results.csv"
AIRPORTS_FILE = "airports.dat"

RECENT_DAYS_FOR_AI = 14
MIN_VALID_BUSINESS_PRICE = 15000

PREMIUM_AIRLINES = [
    "Air France", "KLM", "Lufthansa", "British Airways",
    "Iberia", "ANA", "JAL", "Emirates", "Qatar",
    "Turkish Airlines", "Air Canada", "Delta"
]

SOLID_AIRLINES = [
    "Aeromexico", "United", "American", "Air Europa", "Avianca"
]

LOW_COST_AIRLINES = [
    "Volaris", "Viva Aerobus", "WestJet"
]

WEEKDAY_ORDER = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday"
]


def load_airport_database():
    columns = [
        "airport_id", "name", "city", "country", "iata", "icao",
        "lat", "lon", "altitude", "timezone", "dst", "tz_database",
        "type", "source"
    ]

    airports = pd.read_csv(
        AIRPORTS_FILE,
        header=None,
        names=columns,
        na_values="\\N"
    )

    airports = airports.dropna(subset=["iata", "lat", "lon"])
    airports["iata"] = airports["iata"].astype(str).str.strip().str.upper()
    airports = airports[airports["iata"].str.len() == 3]

    return airports[["iata", "name", "city", "country", "lat", "lon"]]


st.set_page_config(page_title="Flight Deal Dashboard", layout="wide")

st.title("✈️ Flight Deal Dashboard")
st.caption("Flexible date scanner, cabin comparison, airline filters, historical intelligence, and AI-style deal finder.")

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

df = df.dropna(subset=["timestamp", "lowest_price_mxn"])

df = df[
    ~(
        (df["cabin_class"] == "business")
        & (df["lowest_price_mxn"] < MIN_VALID_BUSINESS_PRICE)
    )
].copy()

latest_scan_time = df["timestamp"].max()

if latest_scan_time.tzinfo is None:
    utc_time = latest_scan_time.tz_localize("UTC")
else:
    utc_time = latest_scan_time

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


def historical_signal(row):
    delta = row["delta_vs_average_pct"]
    latest = row["lowest_price_mxn"]
    lowest = row["lowest_ever_mxn"]

    if row["observations"] < 3:
        return "Not enough history"

    if latest <= lowest * 1.03:
        return "🔥 Buy now - near lowest ever"

    if delta <= -15:
        return "✅ Good deal - below average"

    if delta >= 10:
        return "⏳ Wait - above average"

    return "Stable"


historical_data = filtered.copy()
historical_data = historical_data.sort_values("timestamp")

latest_prices = (
    historical_data
    .groupby(["origin", "destination", "cabin_class", "stops"])
    .tail(1)
)

historical_summary = (
    historical_data
    .groupby(["origin", "destination", "cabin_class", "stops"])
    .agg(
        lowest_ever_mxn=("lowest_price_mxn", "min"),
        average_price_mxn=("lowest_price_mxn", "mean"),
        highest_price_mxn=("lowest_price_mxn", "max"),
        observations=("lowest_price_mxn", "count")
    )
    .reset_index()
)

historical_table = latest_prices.merge(
    historical_summary,
    on=["origin", "destination", "cabin_class", "stops"],
    how="left"
)

historical_table["delta_vs_average_pct"] = (
    (historical_table["lowest_price_mxn"] - historical_table["average_price_mxn"])
    / historical_table["average_price_mxn"]
    * 100
)

historical_table["historical_signal"] = historical_table.apply(
    historical_signal,
    axis=1
)

history_features = historical_table[
    [
        "origin",
        "destination",
        "cabin_class",
        "stops",
        "lowest_ever_mxn",
        "average_price_mxn",
        "highest_price_mxn",
        "observations",
        "delta_vs_average_pct",
        "historical_signal"
    ]
].copy()

filtered = filtered.merge(
    history_features,
    on=["origin", "destination", "cabin_class", "stops"],
    how="left"
)


def deal_score(row):
    price = row["lowest_price_mxn"]
    cabin = row["cabin_class"]
    stops_value = row["stops"]
    airline = row["airline"]
    duration = str(row["duration"])
    departure_date = pd.to_datetime(row["departure_date"], errors="coerce")

    score = 100

    avg_price = row.get("average_price_mxn")
    lowest_ever = row.get("lowest_ever_mxn")
    observations = row.get("observations", 0)

    if pd.notna(avg_price) and avg_price > 0 and observations >= 3:
        delta_vs_avg = (price - avg_price) / avg_price * 100

        if delta_vs_avg <= -20:
            score += 30
        elif delta_vs_avg <= -10:
            score += 20
        elif delta_vs_avg <= 0:
            score += 10
        elif delta_vs_avg >= 20:
            score -= 25
        elif delta_vs_avg >= 10:
            score -= 15

        if pd.notna(lowest_ever) and price <= lowest_ever * 1.03:
            score += 25
    else:
        if cabin == "economy":
            score -= price / 1000
        elif cabin == "business":
            score -= price / 3000

    if cabin == "business":
        score += 15
    elif cabin == "economy":
        score += 5

    if stops_value == "Nonstop":
        score += 20
    elif stops_value == "1 stop":
        score += 8
    elif stops_value == "2 stops":
        score -= 10
    else:
        score -= 5

    if airline in PREMIUM_AIRLINES:
        score += 12
    elif airline in SOLID_AIRLINES:
        score += 7
    elif airline in LOW_COST_AIRLINES:
        score -= 5

    duration_hours = 0

    if "hr" in duration:
        try:
            duration_hours = int(duration.split("hr")[0].strip())
        except Exception:
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

    if pd.notna(departure_date):
        month = departure_date.month

        if month in [6, 7, 8, 12]:
            score += 8
        elif month in [4, 5, 9, 10]:
            score += 5
        elif month in [1, 2, 3, 11]:
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

    avg_price = row.get("average_price_mxn")
    lowest_ever = row.get("lowest_ever_mxn")
    observations = row.get("observations", 0)

    if pd.notna(avg_price) and avg_price > 0 and observations >= 3:
        delta_vs_avg = (price - avg_price) / avg_price * 100

        if pd.notna(lowest_ever) and price <= lowest_ever * 1.03:
            reasons.append("🔥 Near lowest historical price")
        elif delta_vs_avg <= -15:
            reasons.append("✅ Below historical average")
        elif delta_vs_avg >= 10:
            reasons.append("⏳ Above historical average")

    if cabin == "business" and price <= 50000:
        reasons.append("✅ Excellent business fare")
    elif cabin == "economy" and price <= 18000:
        reasons.append("✅ Strong economy fare")

    if stops_value == "Nonstop":
        reasons.append("✅ Nonstop flight")
    elif stops_value == "1 stop":
        reasons.append("✅ Reasonable 1-stop itinerary")

    if airline in PREMIUM_AIRLINES:
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
        except Exception:
            pass

    if pd.notna(departure_date):
        month = departure_date.month

        if month in [6, 7, 8, 12]:
            reasons.append("✅ Peak-season value")
        elif month in [4, 5, 9, 10]:
            reasons.append("✅ Shoulder-season value")

    if not reasons:
        reasons.append("ℹ️ Ranked based on price, history, stops, airline, cabin, and duration")

    return " | ".join(reasons)


filtered["deal_score"] = filtered.apply(deal_score, axis=1)
filtered["deal_explanation"] = filtered.apply(explain_deal, axis=1)

latest_timestamp = filtered["timestamp"].max()
recent_cutoff = latest_timestamp - pd.Timedelta(days=RECENT_DAYS_FOR_AI)

recent_filtered = filtered[filtered["timestamp"] >= recent_cutoff].copy()

if recent_filtered.empty:
    recent_filtered = filtered.copy()


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


st.subheader("📌 Summary")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Cheapest Price", f"MX${recent_filtered['lowest_price_mxn'].min():,.0f}")
col2.metric("Average Price", f"MX${recent_filtered['lowest_price_mxn'].mean():,.0f}")
col3.metric("Recent Results", len(recent_filtered))
col4.metric("Destinations", recent_filtered["destination"].nunique())

st.caption(f"AI cards and summary use the latest {RECENT_DAYS_FOR_AI} days of scanner data.")

st.subheader("🤖 AI Destination Finder")

business_under_50k = recent_filtered[
    (recent_filtered["cabin_class"] == "business") &
    (recent_filtered["lowest_price_mxn"] <= 50000)
].sort_values(["timestamp", "lowest_price_mxn"], ascending=[False, True])

nonstop_deals = recent_filtered[
    recent_filtered["stops"] == "Nonstop"
].sort_values(["timestamp", "lowest_price_mxn"], ascending=[False, True])

best_overall = recent_filtered.sort_values(
    ["timestamp", "deal_score"],
    ascending=[False, False]
)

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("### 💼 Best Business Under MX$50k")
    if business_under_50k.empty:
        st.info("No recent business class deals under MX$50k found.")
    else:
        deal = business_under_50k.iloc[0]
        st.success(
            f"{deal['origin']} → {deal['destination']}\n\n"
            f"MX${deal['lowest_price_mxn']:,.0f}\n\n"
            f"{deal['departure_date']} to {deal['return_date']}\n\n"
            f"{deal['airline']} | {deal['stops']} | {deal['duration']}\n\n"
            f"Scanned: {deal['timestamp'].strftime('%Y-%m-%d %H:%M')}"
        )
        st.link_button("Open Google Flights", deal["url"])

with col_b:
    st.markdown("### 🛫 Best Nonstop Deal")
    if nonstop_deals.empty:
        st.info("No recent nonstop deals found.")
    else:
        deal = nonstop_deals.iloc[0]
        st.success(
            f"{deal['origin']} → {deal['destination']}\n\n"
            f"MX${deal['lowest_price_mxn']:,.0f}\n\n"
            f"{deal['departure_date']} to {deal['return_date']}\n\n"
            f"{deal['cabin_class'].title()} | {deal['airline']} | {deal['duration']}\n\n"
            f"Scanned: {deal['timestamp'].strftime('%Y-%m-%d %H:%M')}"
        )
        st.link_button("Open Google Flights", deal["url"])

with col_c:
    st.markdown("### 🏆 Best Overall Deal")
    if best_overall.empty:
        st.info("No recent deals found.")
    else:
        deal = best_overall.iloc[0]
        st.success(
            f"{deal['origin']} → {deal['destination']}\n\n"
            f"Score: {deal['deal_score']}\n\n"
            f"MX${deal['lowest_price_mxn']:,.0f}\n\n"
            f"{deal['cabin_class'].title()} | {deal['airline']} | {deal['stops']}\n\n"
            f"Scanned: {deal['timestamp'].strftime('%Y-%m-%d %H:%M')}"
        )
        st.link_button("Open Google Flights", deal["url"])

st.subheader("🗺️ Destination Price Map")

if os.path.exists(AIRPORTS_FILE):
    airports = load_airport_database()

    map_data = (
        recent_filtered
        .groupby(["destination", "cabin_class"])["lowest_price_mxn"]
        .min()
        .reset_index()
    )

    map_data["destination"] = map_data["destination"].astype(str).str.strip().str.upper()

    map_data = map_data.merge(
        airports,
        left_on="destination",
        right_on="iata",
        how="left"
    )

    map_data = map_data.dropna(subset=["lat", "lon"])

    if map_data.empty:
        st.info("No airport coordinates found for the current destinations.")
    else:
        map_fig = px.scatter_geo(
            map_data,
            lat="lat",
            lon="lon",
            color="lowest_price_mxn",
            size="lowest_price_mxn",
            hover_name="city",
            hover_data={
                "destination": True,
                "country": True,
                "cabin_class": True,
                "lowest_price_mxn": ":,.0f",
                "lat": False,
                "lon": False,
                "iata": False
            },
            projection="natural earth",
            title="Recent Cheapest Destination Prices by Cabin"
        )

        map_fig.update_geos(
            showcountries=True,
            showcoastlines=True,
            showland=True,
            fitbounds="locations"
        )

        st.plotly_chart(map_fig, use_container_width=True)
else:
    st.info("airports.dat not found. Add it to enable the destination map.")

st.subheader("🏆 Top 15 Recent Deals Ranked by AI Score")

top_ranked = recent_filtered.sort_values("deal_score", ascending=False).head(15)

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
    column_config={"url": st.column_config.LinkColumn("Book")},
    use_container_width=True
)

st.subheader("🔮 Predictive Pricing Intelligence")

prediction_data = []

grouped_predictions = (
    filtered
    .sort_values("timestamp")
    .groupby(["origin", "destination", "cabin_class", "stops"])
)

for keys, group in grouped_predictions:

    if len(group) < 3:
        continue

    group = group.sort_values("timestamp")

    latest_price = group["lowest_price_mxn"].iloc[-1]
    average_price = group["lowest_price_mxn"].mean()
    lowest_price = group["lowest_price_mxn"].min()
    highest_price = group["lowest_price_mxn"].max()

    recent_group = group.tail(min(5, len(group)))
    recent_average = recent_group["lowest_price_mxn"].mean()

    volatility = group["lowest_price_mxn"].std()

    if pd.isna(volatility):
        volatility = 0

    first_recent = recent_group["lowest_price_mxn"].iloc[0]
    last_recent = recent_group["lowest_price_mxn"].iloc[-1]

    trend_pct = (
        (last_recent - first_recent)
        / first_recent
        * 100
    )

    if trend_pct <= -5:
        trend_direction = "📉 Falling"
    elif trend_pct >= 5:
        trend_direction = "📈 Rising"
    else:
        trend_direction = "➡️ Stable"

    if volatility <= 1500:
        volatility_label = "Low"
    elif volatility <= 5000:
        volatility_label = "Medium"
    else:
        volatility_label = "High"

    observations = len(group)

    if observations >= 10 and volatility_label == "Low":
        confidence = "High"
    elif observations >= 5:
        confidence = "Medium"
    else:
        confidence = "Low"

    if (
        latest_price <= lowest_price * 1.03
        and trend_direction == "📉 Falling"
    ):
        prediction_signal = "🔥 Strong Buy"

    elif latest_price < average_price * 0.90:
        prediction_signal = "✅ Buy"

    elif trend_direction == "📈 Rising":
        prediction_signal = "⏳ Wait"

    else:
        prediction_signal = "👀 Watch"

    prediction_data.append({
        "origin": keys[0],
        "destination": keys[1],
        "cabin_class": keys[2],
        "stops": keys[3],
        "latest_price_mxn": round(latest_price, 0),
        "historical_average_mxn": round(average_price, 0),
        "lowest_ever_mxn": round(lowest_price, 0),
        "highest_ever_mxn": round(highest_price, 0),
        "recent_average_mxn": round(recent_average, 0),
        "trend_direction": trend_direction,
        "trend_change_pct": round(trend_pct, 1),
        "volatility_mxn": round(volatility, 0),
        "volatility_level": volatility_label,
        "confidence": confidence,
        "prediction_signal": prediction_signal,
        "observations": observations
    })

prediction_df = pd.DataFrame(prediction_data)

if prediction_df.empty:
    st.info("Not enough historical data yet for predictive intelligence.")
else:
    prediction_df = prediction_df.sort_values(
        ["prediction_signal", "trend_change_pct"]
    )

    st.dataframe(
        prediction_df,
        use_container_width=True
    )

st.subheader("📈 Historical Price Intelligence")

historical_display = historical_table[
    [
        "origin",
        "destination",
        "cabin_class",
        "stops",
        "lowest_price_mxn",
        "lowest_ever_mxn",
        "average_price_mxn",
        "highest_price_mxn",
        "delta_vs_average_pct",
        "observations",
        "historical_signal",
        "departure_date",
        "return_date",
        "airline",
        "duration",
        "url"
    ]
].copy()

for col in ["lowest_price_mxn", "lowest_ever_mxn", "average_price_mxn", "highest_price_mxn"]:
    historical_display[col] = historical_display[col].round(0)

historical_display["delta_vs_average_pct"] = historical_display["delta_vs_average_pct"].round(1)

st.dataframe(
    historical_display.sort_values("delta_vs_average_pct"),
    column_config={"url": st.column_config.LinkColumn("Book")},
    use_container_width=True
)

st.subheader("🔥 Price Heat Map by Route & Cabin")

heatmap_data = (
    recent_filtered
    .groupby(["origin", "destination", "cabin_class"])["lowest_price_mxn"]
    .min()
    .reset_index()
)

heatmap_data["route"] = (
    heatmap_data["origin"]
    + " → "
    + heatmap_data["destination"]
)

heatmap_pivot = heatmap_data.pivot_table(
    index="route",
    columns="cabin_class",
    values="lowest_price_mxn"
)

heatmap_fig = px.imshow(
    heatmap_pivot,
    text_auto=True,
    aspect="auto",
    color_continuous_scale="RdYlGn_r",
    title="Recent Lowest Price by Route & Cabin (MXN)"
)

st.plotly_chart(heatmap_fig, use_container_width=True)

st.subheader("💺 Economy vs Business Comparison")

comparison = (
    recent_filtered
    .groupby(["destination", "cabin_class"])["lowest_price_mxn"]
    .min()
    .reset_index()
)

comparison_chart = px.bar(
    comparison,
    x="destination",
    y="lowest_price_mxn",
    color="cabin_class",
    barmode="group",
    title="Recent Cheapest Price by Destination & Cabin",
    text_auto=True
)

st.plotly_chart(comparison_chart, use_container_width=True)

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
    title="Full Historical Price Trend Over Time"
)

st.plotly_chart(price_trend_chart, use_container_width=True)

st.subheader("✈️ Interactive Airline Comparison")

airline_comparison = (
    recent_filtered
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
    title="Recent Cheapest Price by Airline",
    text_auto=True
)

st.plotly_chart(airline_chart, use_container_width=True)

st.subheader("🛑 Interactive Stop Comparison")

stop_comparison = (
    recent_filtered
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
    title="Recent Cheapest Price by Stops",
    text_auto=True
)

st.plotly_chart(stop_chart, use_container_width=True)

st.subheader("📅 Cheapest Weekday to Depart")

recent_filtered["departure_weekday"] = pd.to_datetime(
    recent_filtered["departure_date"],
    errors="coerce"
).dt.day_name()

weekday_prices = (
    recent_filtered
    .groupby(["departure_weekday", "cabin_class"])["lowest_price_mxn"]
    .min()
    .reset_index()
)

weekday_prices["departure_weekday"] = pd.Categorical(
    weekday_prices["departure_weekday"],
    categories=WEEKDAY_ORDER,
    ordered=True
)

weekday_prices = weekday_prices.sort_values("departure_weekday")

weekday_chart = px.bar(
    weekday_prices,
    x="departure_weekday",
    y="lowest_price_mxn",
    color="cabin_class",
    barmode="group",
    title="Recent Cheapest Weekday to Depart",
    text_auto=True
)

st.plotly_chart(weekday_chart, use_container_width=True)

st.subheader("📄 Full Data")

st.dataframe(
    filtered,
    column_config={"url": st.column_config.LinkColumn("Book")},
    use_container_width=True
)
