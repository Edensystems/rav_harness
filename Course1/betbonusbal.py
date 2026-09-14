import concurrent.futures
import threading
import time
import requests

# Operational Configurations
CONNECTIONS = 1
TIMEOUT = 10

# Define absolute file paths
INPUT_FILE = r"C:\Users\Root\PycharmProjects\GoogleDeepmindlabs\betlist.txt"
TOOMANY_FILE = r"C:\Users\Root\PycharmProjects\GoogleDeepmindlabs\toobets.txt"
ERROR_FILE = r"C:\Users\Root\PycharmProjects\GoogleDeepmindlabs\errorlist1.txt"

# State Tracking & Synchronization Locks
out = []
io_lock = threading.Lock()


def load_file(filename):
    """Safely loads and strips whitespace elements from the text line file."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Error: The source file {filename} could not be found.")
        return []


def write_log(filename, data_item):
    """Appends data entries to target logs safely across thread boundaries."""
    with io_lock:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{data_item}\n")


def bet_bonus(session, outcome, match_id, dt):
    lt = dt[-2:]
    kc = dt[-4]
    user_agent = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1{lt}.0.{kc}.90 Safari/537.36"

    """Authenticates and places an automated promotional voucher bet."""
    login_url = "https://identity.imarabet.co.ke:443/login?lang=en&country_code=ke"
    headers = {
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json",
        "Sec-Ch-Ua": '"Not-A.Brand";v="24", "Chromium";v="146"',
        "Content-Type": "application/json",
        "Sec-Ch-Ua-Mobile": "?0",
        "User-Agent": user_agent,
        "Origin": "https://imarabet.co.ke",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://imarabet.co.ke/",
    }

    payload = {
        "btag": "",
        "campaign": "",
        "click_id": "",
        "code": "",
        "country_code": "ke",
        "fbclid": "",
        "gclid": "",
        "medium": "",
        "msisdn": int(dt),
        "password": "qq1234",
        "referrer": "",
        "source": "",
        "utm_campaign": "",
        "utm_content": "",
        "utm_medium": "",
        "utm_source": "",
        "utm_term": "",
    }

    try:
        resp = session.post(
            login_url, headers=headers, json=payload, timeout=TIMEOUT
        )
        qq = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"\nLogin connection failure for user {dt}: {e}")
        return None

    auth_token = qq.get("auth")
    error_code = qq.get("error_code")

    if auth_token:
        bet_url = "https://betting.imarabet.co.ke:443/bet"
        bet_headers = headers.copy()
        bet_headers.update({"Api-Key": auth_token, "Accept": "*/*"})

        bet_payload = {
            "bet_type":1,"bets":[{"market_id":7079,"match_id":int(match_id),"outcome_id":str(outcome),"specifier":"","producer_id":3}],"booking_code":"","campaign":"null","ip_address":"","medium":"null","source":2,"stake":98,"stake_type":1,"utm_source":"null","referrer":"https://imarabet.co.ke/markets?game_id=13660723"
        }

        try:
            resp1 = session.post(
                bet_url, headers=bet_headers, json=bet_payload, timeout=TIMEOUT
            )
            mm = resp1.json()
            print(f"\nUser {dt} placement output: {mm}")

            if mm.get("error_code"):
                write_log(TOOMANY_FILE, dt)
                #time.sleep(30)
        except (requests.RequestException, ValueError) as e:
            print(f"\nBet placement transaction error for {dt}: {e}")

    if error_code:
        write_log(ERROR_FILE, dt)

    return auth_token


def test_range(data, outcome, match_id):
    """Manages thread orchestration utilizing a consolidated HTTP connection pool."""
    print(f"Initializing concurrent batch for {len(data)} items...")
    time1 = time.time()

    # Utilize requests.Session to bundle TCP handshakes securely across execution steps
    with requests.Session() as session:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=CONNECTIONS
        ) as executor:
            future_to_data = {
                executor.submit(
                    bet_bonus, session, outcome, match_id, dt
                ): dt
                for dt in data
            }

            for future in concurrent.futures.as_completed(future_to_data):
                try:
                    result = future.result()
                except Exception as exc:
                    result = str(type(exc))
                finally:
                    out.append(result)
                    print(f"Progress Tracker: {len(out)} entries", end="\r")

    time2 = time.time()
    print(f"\nBatch processing finalized. Total runtime: {time2 - time1:.2f} s")


def main():
    # Cold start file configurations load
    data = load_file(INPUT_FILE)
    if not data:
        print("Empty line dataset. Thread initialization canceled.")
        return

    # Fetching booking references configurations
    booking_url = "https://betting.imarabet.co.ke:443/bookings/BNBQV7?lang=en"
    booking_headers = {
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Not-A.Brand\";v=\"24\", \"Chromium\";v=\"146"',
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Origin": "https://imarabet.co.ke",
        "Referer": "https://imarabet.co.ke/",
    }

    try:
        response = requests.get(
            booking_url, headers=booking_headers, timeout=TIMEOUT
        )
        booking_data = response.json()
        match_id = booking_data[0]["match_id"]
        outcome_id = booking_data[0]["outcome_id"]
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        print(f"Failed to resolve setup credentials from tracking endpoint: {e}")
        return

    # Trigger worker execution pipeline
    #data1 =data[413:690]
    test_range(data, outcome_id, match_id)


if __name__ == "__main__":
    main()