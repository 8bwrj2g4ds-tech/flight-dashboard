import re
import json
import os
import csv
import requests
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# =========================
# SETTINGS
# =========================

ORIGIN = "MEX"
DESTINATIONS = ["CDG"]

SCAN_START_DATE = "2026-09-01"
SCAN_END_DATE = "2026-09-10"

MIN_TRIP_DAYS = 7
MAX_TRIP_DAYS = 8

PASSENGERS = 1

# Automatically compare both
CABIN_CLASSES = ["economy", "business"]

# Options:
# ["Nonstop"]
# ["1 stop"]
# ["Nonstop", "1 stop"]
# ["Nonstop", "1 stop", "2 stops"]
ALLOWED_STOPS = ["Nonstop", "1 stop"]

MAX_PRICE_BY_CABIN = {
    "economy": 20000,
    "business": 70000
}

MIN_VALID_PRICE_MXN = 8000

HEADLESS_MODE = True

PRICE_HISTORY_FILE = "best_price_history.json"
CSV_FILE = "flight_results.csv"

TELEGRAM_BOT_TOKEN = "8911409301:AAEXOf50sAFo-E8mfdXajYTxnEYOxYEGl7w"
TELEGRAM_CHAT_ID = "5095590388"


# =========================
# HELPERS
# =========================

def generate_trips():
    trips = []
    start_date = datetime.strptime(SCAN_START_DATE, "%Y-%m-%d")
    end_date = datetime.strptime(SCAN_END_DATE, "%Y-%m-%d")

    departure_date = start_date

    while departure_date <= end_date:
        for trip_length in range(MIN_TRIP_DAYS, MAX_TRIP_DAYS + 1):
            return_date = departure_date + timedelta(days=trip_length)

            if return_date <= end_date:
                trips.append({
                    "departure": departure_date.strftime("%Y-%m-%d"),
                    "return": return_date.strftime("%Y-%m-%d"),
                    "trip_length": trip_length
                })

        departure_date += timedelta(days=1)

    return trips


def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    response = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    })

    print("Telegram status:", response.status_code)
    print("Telegram response:", response.text)


def load_price_history():
    if not os.path.exists(PRICE_HISTORY_FILE):
        return {}

    with open(PRICE_HISTORY_FILE, "r") as file:
        return json.load(file)


def save_price_history(history):
    with open(PRICE_HISTORY_FILE, "w") as file:
        json.dump(history, file, indent=4)


def build_google_flights_url(destination, departure_date, return_date, cabin_class):
    return (
        "https://www.google.com/travel/flights?"
        f"q=Flights%20from%20{ORIGIN}%20to%20{destination}%20"
        f"on%20{departure_date}%20returning%20{return_date}%20"
        f"{cabin_class}%20class%20{PASSENGERS}%20passenger"
    )


def extract_flight_blocks(all_text):
    lines = [line.strip() for line in all_text.splitlines() if line.strip()]
    blocks = []

    for i, line in enumerate(lines):
        if re.match(r"MX\$[\d,]+", line):
            price = int(line.replace("MX$", "").replace(",", ""))

            if price < MIN_VALID_PRICE_MXN:
                continue

            nearby = lines[max(0, i - 12): i + 6]
            block_text = "\n".join(nearby)

            stops = "Unknown"
            if "Nonstop" in block_text:
                stops = "Nonstop"
            elif "1 stop" in block_text:
                stops = "1 stop"
            elif "2 stops" in block_text:
                stops = "2 stops"

            duration = "Unknown"
            duration_match = re.search(r"(\d+ hr(?: \d+ min)?|\d+ min)", block_text)
            if duration_match:
                duration = duration_match.group(1)

            airline = "Unknown"
            possible_airlines = [
                "Aeromexico",
                "Air France",
                "KLM",
                "Lufthansa",
                "British Airways",
                "Iberia",
                "United",
                "American",
                "Delta",
                "ANA",
                "JAL",
                "Emirates",
                "Qatar",
                "Turkish Airlines",
                "Air Canada",
                "Air Europa",
                "Volaris",
                "Viva Aerobus"
            ]

            for name in possible_airlines:
                if name in block_text:
                    airline = name
                    break

            blocks.append({
                "price": price,
                "airline": airline,
                "stops": stops,
                "duration": duration,
                "raw_block": block_text
            })

    return blocks


def get_deal_score(price, cabin_class):
    if cabin_class == "economy":
        if price <= 15000:
            return "🔥 Excellent economy deal"
        elif price <= 18000:
            return "✅ Good economy deal"
        else:
            return "Average economy price"

    if cabin_class == "business":
        if price <= 55000:
            return "🔥 Excellent business deal"
        elif price <= 70000:
            return "✅ Good business deal"
        else:
            return "Average business price"

    return "Deal found"


def search_single_trip(page, destination, trip, cabin_class):
    departure_date = trip["departure"]
    return_date = trip["return"]

    google_flights_url = build_google_flights_url(
        destination,
        departure_date,
        return_date,
        cabin_class
    )

    print("\nOpening Google Flights...")
    print(f"Route: {ORIGIN} → {destination}")
    print(f"Dates: {departure_date} to {return_date}")
    print(f"Cabin: {cabin_class}")

    page.goto(google_flights_url)
    page.wait_for_timeout(25000)

    all_text = page.locator("body").inner_text()
    flight_blocks = extract_flight_blocks(all_text)

    valid_blocks = [
        block for block in flight_blocks
        if block["stops"] in ALLOWED_STOPS
    ]

    if not valid_blocks:
        print("No flights found matching stop filter.")
        return None

    best = min(valid_blocks, key=lambda item: item["price"])

    print(
        f"Best found: MX${best['price']:,} | "
        f"{best['airline']} | {best['stops']} | {best['duration']}"
    )

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "origin": ORIGIN,
        "destination": destination,
        "departure": departure_date,
        "return": return_date,
        "trip_length": trip["trip_length"],
        "cabin": cabin_class,
        "passengers": PASSENGERS,
        "lowest_price": best["price"],
        "airline": best["airline"],
        "stops": best["stops"],
        "duration": best["duration"],
        "url": google_flights_url
    }


def save_results_to_csv(results):
    file_exists = os.path.exists(CSV_FILE)

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "timestamp",
                "origin",
                "destination",
                "departure_date",
                "return_date",
                "trip_length_days",
                "cabin_class",
                "passengers",
                "lowest_price_mxn",
                "airline",
                "stops",
                "duration",
                "url"
            ])

        for result in results:
            writer.writerow([
                result["timestamp"],
                result["origin"],
                result["destination"],
                result["departure"],
                result["return"],
                result["trip_length"],
                result["cabin"],
                result["passengers"],
                result["lowest_price"],
                result["airline"],
                result["stops"],
                result["duration"],
                result["url"]
            ])


def send_top_3_deals_alert(destination, cabin_class, top_3_deals, history):
    best_deal = top_3_deals[0]
    current_price = best_deal["lowest_price"]

    history_key = f"{ORIGIN}-{destination}-{cabin_class}-best-flexible-date-price"
    previous_best = history.get(history_key)

    should_alert = False
    reason = ""

    max_price = MAX_PRICE_BY_CABIN[cabin_class]

    if current_price <= max_price:
        if previous_best is None:
            should_alert = True
            reason = "First best flexible-date deal found"
        elif current_price < previous_best:
            should_alert = True
            reason = f"Best price dropped from MX${previous_best:,} to MX${current_price:,}"
        else:
            reason = "Best price is good, but not lower than previous best alert"
    else:
        reason = "Best price is above your limit"

    history[history_key] = current_price
    save_price_history(history)

    print(f"\nTop 3 deals for {destination} / {cabin_class}:")
    for index, deal in enumerate(top_3_deals, start=1):
        print(
            f"{index}. {deal['departure']} to {deal['return']} - "
            f"MX${deal['lowest_price']:,} - {deal['airline']} - {deal['stops']}"
        )

    print(reason)

    if should_alert:
        message = (
            f"🔥 TOP 3 FLEXIBLE DATE DEALS 🔥\n\n"
            f"Route: {ORIGIN} → {destination}\n"
            f"Cabin: {cabin_class.title()}\n"
            f"Allowed Stops: {', '.join(ALLOWED_STOPS)}\n\n"
        )

        for index, deal in enumerate(top_3_deals, start=1):
            message += (
                f"{index}. {deal['departure']} to {deal['return']}\n"
                f"   Trip Length: {deal['trip_length']} days\n"
                f"   Price: MX${deal['lowest_price']:,}\n"
                f"   Airline: {deal['airline']}\n"
                f"   Stops: {deal['stops']}\n"
                f"   Duration: {deal['duration']}\n\n"
            )

        message += (
            f"Deal Score: {get_deal_score(current_price, cabin_class)}\n"
            f"Reason: {reason}\n\n"
            f"Best Google Flights Link:\n"
            f"{best_deal['url']}"
        )

        send_telegram_alert(message)
        print("Top 3 deal alert sent.")


def run_searches():
    trips = generate_trips()
    history = load_price_history()

    print(f"Generated {len(trips)} trip combinations.")

    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS_MODE)
        page = browser.new_page()

        for destination in DESTINATIONS:
            for cabin_class in CABIN_CLASSES:
                cabin_results = []

                for trip in trips:
                    result = search_single_trip(
                        page,
                        destination,
                        trip,
                        cabin_class
                    )

                    if result:
                        cabin_results.append(result)
                        all_results.append(result)

                if cabin_results:
                    top_3_deals = sorted(
                        cabin_results,
                        key=lambda item: item["lowest_price"]
                    )[:3]

                    send_top_3_deals_alert(
                        destination,
                        cabin_class,
                        top_3_deals,
                        history
                    )
                else:
                    print(f"No valid prices found for {destination} / {cabin_class}.")

        browser.close()

    if all_results:
        save_results_to_csv(all_results)
        print(f"Saved {len(all_results)} results to {CSV_FILE}.")


run_searches()