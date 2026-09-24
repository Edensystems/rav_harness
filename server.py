from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
import concurrent.futures
import requests
import uuid
from datetime import datetime
from bs4 import BeautifulSoup
import threading
import os

from action_service import is_action_enabled
from auth_service import seed_admin_user
from config import get_task_connections
from billing_service import (
    KNOWN_ACTIONS,
    charge_successful_action,
    format_credits,
    get_action_rate,
    seed_action_rates,
)
from database import SessionLocal, get_db, init_db
from dependencies import get_current_user, require_admin
from models import User
from output_service import build_user_output_path, create_task_output, finalize_task_output
from routers import admin as admin_router
from routers import auth as auth_router
from routers import billing as billing_router
from routers import lists as lists_router
from routers import dashboard as dashboard_router
from routers import outputs as outputs_router
from schemas import TaskPayload
from sqlalchemy.orm import Session


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_admin_user(db)
        seed_action_rates(db)
        from action_service import seed_action_toggles

        seed_action_toggles(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Automation API Server", version="2.0", lifespan=lifespan)

app.include_router(auth_router.router)
app.include_router(lists_router.router)
app.include_router(admin_router.router)
app.include_router(outputs_router.router)
app.include_router(dashboard_router.router)
app.include_router(billing_router.router)

JOBS = {}
TIMEOUT = 20
OUTPUT_LOCK = threading.Lock()


def _validate_task_payload(payload: TaskPayload):
    if not payload.target_numbers:
        raise HTTPException(status_code=400, detail="No target numbers provided")
    if payload.task_type in {"bet", "app_bonus", "claim_bonus"} and not payload.share_code:
        raise HTTPException(status_code=400, detail=f"Share code required for '{payload.task_type}'")
    if payload.task_type == "withdrawal" and not payload.amount:
        raise HTTPException(status_code=400, detail="Amount required for 'withdrawal'")
    needs_amount = {"bet", "virtual_bet", "app_bonus", "rollover", "claim"}
    if payload.task_type in needs_amount and not payload.use_total_balance and not payload.amount:
        raise HTTPException(status_code=400, detail=f"Bet amount required for '{payload.task_type}'")

@app.post("/api/start_task")
def start_task(
    payload: TaskPayload,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_task_payload(payload)

    if payload.task_type not in KNOWN_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action '{payload.task_type}'")
    if not is_action_enabled(db, payload.task_type):
        raise HTTPException(
            status_code=423,
            detail=f"'{payload.task_type}' is currently disabled by the server.",
        )

    billing_rate = get_action_rate(db, payload.task_type)
    current_credits = float(user.credits)
    if billing_rate > 0 and current_credits < float(billing_rate):
        raise HTTPException(
            status_code=402,
            detail=(
                f"'{payload.task_type}' is billable at {format_credits(billing_rate)} credit(s) "
                f"per successful action. Your balance is {format_credits(current_credits)}."
            ),
        )

    job_id = str(uuid.uuid4())
    os.makedirs("server_outputs", exist_ok=True)
    if payload.output_filename:
        output_filename = payload.output_filename
        parent = os.path.dirname(output_filename)
        if parent:
            os.makedirs(parent, exist_ok=True)
    else:
        output_filename = build_user_output_path(user.id, job_id, payload.task_type)

    create_task_output(
        db=db,
        user_id=user.id,
        job_id=job_id,
        task_type=payload.task_type,
        file_path=output_filename,
        total=len(payload.target_numbers),
    )

    workers = get_task_connections()
    billing_note = (
        f"Billable action: {format_credits(billing_rate)} credit(s) per success. "
        f"Current balance: {format_credits(current_credits)}."
        if billing_rate > 0
        else "This action is not billed."
    )
    JOBS[job_id] = {
        "status": "running",
        "logs": [
            f"Task '{payload.task_type}' initialized by {user.email}. "
            f"Output will be saved to {output_filename}",
            f"Using {workers} server connection(s) from TASK_CONNECTIONS.",
            billing_note,
        ],
        "processed": 0,
        "total": len(payload.target_numbers),
        "stop_event": threading.Event(),
        "log_lock": threading.Lock(),
        "output_filename": output_filename,
        "owner_id": str(user.id),
        "job_id": job_id,
        "billing_rate": float(billing_rate),
        "credits_charged": 0.0,
        "credits_remaining": current_credits,
        "billable": billing_rate > 0,
        "connections": workers,
    }

    background_tasks.add_task(run_automation_engine, job_id, payload, output_filename)
    return {
        "job_id": job_id,
        "message": "Task started successfully",
        "output_filename": output_filename,
        "billable": billing_rate > 0,
        "billing_rate": float(billing_rate),
        "credits": current_credits,
        "connections": workers,
    }


@app.get("/api/task_status/{job_id}")
def get_task_status(job_id: str, user: User = Depends(get_current_user)):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    job = JOBS[job_id]
    if job.get("owner_id") != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized for this job")
    with job["log_lock"]:
        logs = list(job["logs"])
    return {
        "status": job["status"],
        "logs": logs,
        "processed": job["processed"],
        "total": job["total"],
        "output_filename": job.get("output_filename", ""),
        "billable": job.get("billable", False),
        "billing_rate": job.get("billing_rate", 0),
        "credits_charged": job.get("credits_charged", 0),
        "credits_remaining": job.get("credits_remaining"),
    }


@app.post("/api/stop_task/{job_id}")
def stop_task(job_id: str, user: User = Depends(get_current_user)):
    if job_id not in JOBS:
        raise HTTPException(status_code=400, detail="Job not found")
    if JOBS[job_id].get("owner_id") != str(user.id):
        raise HTTPException(status_code=403, detail="Not authorized for this job")
    if JOBS[job_id]["status"] == "running":
        JOBS[job_id]["stop_event"].set()
        with JOBS[job_id]["log_lock"]:
            JOBS[job_id]["logs"].append(f"{datetime.now().strftime('%H:%M:%S')} - Stop signal received. Halting task...")
        return {"message": "Stop signal sent"}
    raise HTTPException(status_code=400, detail="Job not running or not found")


def _apply_success_charge(job: dict, task_type: str, target_number: str, log_func) -> bool:
    rate = float(job.get("billing_rate") or 0)
    if rate <= 0:
        return True

    result = charge_successful_action(
        user_id=job["owner_id"],
        task_type=task_type,
        job_id=job.get("job_id", ""),
        rate=rate,
        note=f"Successful {task_type} for {target_number}",
    )
    if not result.charged:
        remaining = format_credits(result.balance)
        log_func(
            f"BILLING STOPPED: Not enough credits to charge {format_credits(rate)} "
            f"for {target_number}. Remaining: {remaining}."
        )
        job["credits_remaining"] = float(result.balance)
        job["stop_event"].set()
        return False

    job["credits_charged"] = float(job.get("credits_charged", 0)) + float(result.amount)
    job["credits_remaining"] = float(result.balance)
    log_func(
        f"BILLED: {format_credits(result.amount)} credit(s) for {target_number}. "
        f"Remaining: {format_credits(result.balance)}."
    )
    return True


def _looks_like_success(status_text: str) -> bool:
    lower = (status_text or "").lower()
    fail_hints = ("fail", "error", "insufficient", "denied", "reject", "unable", "invalid")
    return not any(hint in lower for hint in fail_hints)


def _job_log(job: dict, msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    with job["log_lock"]:
        job["logs"].append(f"{timestamp} - {msg}")


def _write_output(output_filename: str, line: str):
    with OUTPUT_LOCK:
        with open(output_filename, "a+", encoding="utf-8") as f:
            f.write(line)


def _resolve_stake(data: dict, payload: TaskPayload) -> float:
    if payload.use_total_balance:
        raw = data.get("bonus_balance", 0) if payload.use_bonus else data.get("balance", 0)
        return float(raw)
    if payload.amount == "1":
        return float(data.get("balance", 0))
    return float(payload.amount) if payload.amount else 0.0


def run_automation_engine(job_id: str, payload: TaskPayload, output_filename: str):
    job = JOBS[job_id]

    def log(msg):
        _job_log(job, msg)

    start_time = datetime.now()

    workers = get_task_connections()
    log(f"Worker pool size: {workers}")

    if payload.task_type == "rollover":
        _run_rollover_engine(job_id, job, payload, output_filename, log)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    process_single_user,
                    target_number,
                    payload,
                    log,
                    job["stop_event"],
                    output_filename,
                    job,
                ): target_number
                for target_number in payload.target_numbers
            }

            for future in concurrent.futures.as_completed(futures):
                if job["stop_event"].is_set():
                    log("Process stopped by user.")
                    break

                target_num = futures[future]
                try:
                    future.result()
                except Exception as e:
                    log(f"Unhandled exception for {target_num}: {str(e)}")

                job["processed"] += 1
                log(f"Progress: {job['processed']}/{job['total']}")

    elapsed = (datetime.now() - start_time).total_seconds()
    job["status"] = "stopped" if job["stop_event"].is_set() else "completed"
    log(f"Task finished in {elapsed:.2f} seconds.")
    finalize_task_output(job_id, job["status"], job["processed"], job["total"])


def _run_rollover_engine(job_id: str, job: dict, payload: TaskPayload, output_filename: str, log):
    log("Finding balanced virtual market for rollover...")
    balanced_slip = _get_rollover_slip(log)

    if not balanced_slip or len(balanced_slip) < 2:
        log("Could not find a suitable balanced market for rollover. Aborting.")
        job["status"] = "completed"
        finalize_task_output(job_id, job["status"], job["processed"], job["total"])
        return

    log(
        f"Found balanced market. O1: {balanced_slip[0]['outcome_name']} @ {balanced_slip[0]['odd_value']}. "
        f"O2: {balanced_slip[1]['outcome_name']} @ {balanced_slip[1]['odd_value']}"
    )

    user_list = payload.target_numbers
    half_point = len(user_list) // 2
    list1 = user_list[:half_point]
    list2 = user_list[half_point:]
    log(f"Splitting {len(user_list)} users into two groups: {len(list1)} and {len(list2)}.")

    workers = get_task_connections()
    log(f"Worker pool size: {workers}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for url in list1:
            futures.append(
                executor.submit(
                    _place_single_rollover_bet,
                    url,
                    payload,
                    balanced_slip[0],
                    log,
                    job["stop_event"],
                    output_filename,
                    job,
                )
            )
        for url in list2:
            futures.append(
                executor.submit(
                    _place_single_rollover_bet,
                    url,
                    payload,
                    balanced_slip[1],
                    log,
                    job["stop_event"],
                    output_filename,
                    job,
                )
            )

        for future in concurrent.futures.as_completed(futures):
            if job["stop_event"].is_set():
                log("Rollover stopped by user.")
                break
            try:
                future.result()
            except Exception as e:
                log(f"Rollover worker exception: {e}")
            job["processed"] += 1
            log(f"Progress: {job['processed']}/{job['total']}")


def _get_auth_details(url: str, password: str, log_func):
    try:
        lt = url[-2:] if len(url) >= 2 else "10"
        mz = (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/1{lt}.0.5993.90 Safari/537.36"
        )
        home_url = "https://odibets.com:443/"
        headers = {
            "User-Agent": mz,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        resp = requests.get(home_url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()

        cook = resp.headers.get("Set-Cookie", "")
        wer = cook.split(";")[0].split("=")[1] if "=" in cook else ""
        soup = BeautifulSoup(resp.content, "html.parser")
        element = soup.find(id="body")
        drr = element.get("ref")[2:].split(" ")[0] if element and element.get("ref") else ""

        login_url = "https://accounts-api.apps.odibets.com:443/accounts-api/api/v1/auth/login"
        headers_step3 = {
            "X-Link-Id": drr,
            "User-Agent": mz,
            "Content-Type": "application/json",
            "Origin": "https://odibets.com",
            "Referer": "https://odibets.com/",
        }
        cookies1 = {"odibetskenya": wer}
        json_payload = {"msisdn": url, "password": password}

        resp1 = requests.post(
            login_url, headers=headers_step3, cookies=cookies1, json=json_payload, timeout=TIMEOUT
        )
        resp1.raise_for_status()
        tt = resp1.json()

        if tt.get("status_code") == 200:
            return {
                "access_token": tt.get("data", {}).get("access_token"),
                "session_token": drr,
                "cookies": cookies1,
                "ua": mz,
                "data": tt.get("data"),
            }
        log_func(f"Login failed for {url}: {tt.get('message', 'Unknown failure')}")
        return None
    except Exception as e:
        log_func(f"Auth request exception for {url}: {e}")
        return None


def _get_android_auth_details(url: str, password: str, log_func):
    try:
        mz = (
            "Mozilla/5.0 (Linux; Android 13; SM-A7160 Build/TP1A.220624.014; wv) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/137.0.7151.115 Mobile Safari/537.36"
        )
        home_url = "https://odibets.com:443/?utm_source=ANDROID_APP&utm_medium=ANDROID_APP&utm_campaign=ANDROID_APP"
        headers = {
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": mz,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "X-Requested-With": "com.odibetsmini",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-GB,en;q=0.9",
        }
        resp = requests.get(home_url, headers=headers, timeout=TIMEOUT)
        resp.raise_for_status()

        cook = resp.headers.get("Set-Cookie", "")
        wer = cook.split(";")[0].split("=")[1] if "=" in cook else ""
        soup = BeautifulSoup(resp.content, "html.parser")
        element = soup.find(id="body")
        drr = element.get("ref")[2:].split(" ")[0] if element and element.get("ref") else ""

        if not wer or not drr:
            log_func(f"Failed to get initial Android tokens for {url}.")
            return None

        pxy_url = "https://odibets.com:443/pxy/punter"
        headers2 = {
            "Connection": "keep-alive",
            "X-Odi-Key": drr,
            "Authorization": "Bearer",
            "User-Agent": mz,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://odibets.com",
            "X-Requested-With": "com.odibetsmini",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": home_url,
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-GB,en;q=0.9",
        }
        json_payload = {"resource": "login", "ua": mz}
        resp2 = requests.post(pxy_url, headers=headers2, json=json_payload, timeout=TIMEOUT)
        resp2.raise_for_status()
        qq = resp2.json()

        if qq.get("status_code") != 200:
            log_func(f"Android pre-login failed for {url}: {qq.get('message', 'Unknown error')}")
            return None

        ks = qq.get("data", {}).get("id")
        cookies1 = {"odibetskenya": wer}
        headers1 = headers2.copy()
        headers1["X-Odi-Key"] = ks
        json_payload1 = {"code": "", "msisdn": url, "password": password, "resource": "login", "ua": mz}
        resp1 = requests.post(pxy_url, headers=headers1, cookies=cookies1, json=json_payload1, timeout=TIMEOUT)
        resp1.raise_for_status()
        tt = resp1.json()

        if tt.get("status_code") == 200:
            return {
                "access_token": tt.get("data", {}).get("access_token"),
                "session_token": ks,
                "cookies": cookies1,
                "ua": mz,
                "data": tt.get("data"),
            }
        log_func(f"Android login failed for {url}: {tt.get('message', 'Unknown error')}")
        return None
    except Exception as e:
        log_func(f"Android auth request failed for {url}: {e}")
        return None


def _create_betting_slip(selections):
    slip = []
    for selection in selections:
        slip.append(
            {
                "live": "false",
                "bet_type": selection.get("bet_type"),
                "odd_value": selection.get("odd_value"),
                "outcome_id": selection.get("outcome_id"),
                "outcome_name": selection.get("outcome_name"),
                "parent_match_id": selection.get("parent_match_id"),
                "specifiers": selection.get("specifiers"),
                "sport_id": selection.get("sport_id"),
                "sub_type_id": selection.get("sub_type_id"),
            }
        )
    return slip


def _generate_balanced_gg_slip(matches):
    min_diff = float("inf")
    selected_match = None
    selected_outcomes = []

    for match in matches:
        for market in match.get("markets", []):
            if market.get("sub_type_id") == "TG25":
                outcomes = {o["outcome_name"]: o for o in market.get("outcomes", [])}
                if "Over" in outcomes and "Under" in outcomes:
                    over_odd = float(outcomes["Over"]["odd_value"])
                    under_odd = float(outcomes["Under"]["odd_value"])
                    diff = abs(over_odd - under_odd)
                    if diff <= 0.05 and diff < min_diff:
                        min_diff = diff
                        selected_match = match
                        selected_outcomes = [outcomes["Over"], outcomes["Under"]]

    if selected_match and selected_outcomes:
        slip = []
        for outcome in selected_outcomes:
            slip.append(
                {
                    "away_team": selected_match.get("away_team"),
                    "booking_code": "",
                    "competition_id": selected_match.get("competition_id"),
                    "e_block_id": "",
                    "home_team": selected_match.get("home_team"),
                    "i": 0,
                    "id": "",
                    "jp_id": "",
                    "jp_expiry": "",
                    "jp_week_id": "",
                    "live": 2,
                    "odd_value": outcome.get("odd_value"),
                    "outcome_id": outcome.get("outcome_id"),
                    "outcome_name": outcome.get("outcome_name"),
                    "parent_match_id": selected_match.get("parent_match_id"),
                    "rebet": 0,
                    "round_id": selected_match.get("round_id"),
                    "specifiers": outcome.get("specifiers"),
                    "sport_id": "",
                    "sportsbook": "virtuals",
                    "start_time": selected_match.get("start_time"),
                    "status": outcome.get("status"),
                    "sub_type_id": outcome.get("sub_type_id"),
                }
            )
        return slip
    return None


def _get_rollover_slip(log_func):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        cookies = {"odibetskenya": "vsoq35q635oi82jvb5oftq6a75"}

        periods_url = (
            "https://odibets.com:443/pxy/virtuals?competition_id=1&tab=&period=&level=1"
            "&platform=desktop&view=odileague&resource=virtuals"
        )
        resp_periods = requests.get(periods_url, headers=headers, cookies=cookies, timeout=TIMEOUT)
        resp_periods.raise_for_status()
        periods_data = resp_periods.json()

        if periods_data.get("status_code") != 200:
            return None

        period_time_str = periods_data["data"]["periods"][5]["start_time"]
        formatted_time = datetime.strptime(period_time_str, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d+%H:%M:%S")

        matches_url = (
            f"https://odibets.com:443/pxy/virtuals?competition_id=1&period={formatted_time}"
            f"&sub_type_id=TG25&level=4&platform=desktop&view=odileague&resource=virtuals"
        )
        resp_matches = requests.get(matches_url, headers=headers, cookies=cookies, timeout=TIMEOUT)
        resp_matches.raise_for_status()
        matches_data = resp_matches.json()

        return _generate_balanced_gg_slip(matches_data["data"]["matches"])
    except Exception as e:
        log_func(f"Error getting rollover slip: {e}")
        return None


def _place_single_rollover_bet(
    url: str,
    payload: TaskPayload,
    slip_item: dict,
    log_func,
    stop_event: threading.Event,
    output_filename: str,
    job: dict | None = None,
):
    if stop_event.is_set():
        return

    auth_details = _get_auth_details(url, payload.target_password, log_func)
    if not auth_details:
        return

    try:
        data = auth_details.get("data", {})
        if payload.use_total_balance:
            stake = data.get("bonus_balance", 0) if payload.use_bonus else data.get("balance", 0)
        elif payload.amount == "1":
            stake = data.get("balance", 0)
        else:
            stake = payload.amount

        bet_headers = {
            "Authorization": f"Bearer {auth_details['access_token']}",
            "X-Odi-Key": auth_details["session_token"],
            "User-Agent": auth_details["ua"],
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Referer": "https://odibets.com/odileague",
            "Origin": "https://odibets.com",
        }
        bet_url = "https://odibets.com:443/pxy/bet"
        bet_payload = {
            "auto_oc": False,
            "bet_amount": float(stake),
            "id": "",
            "resource": "bet",
            "slip": [slip_item],
            "sportsbook": "virtuals",
            "src": "bet",
            "ua": auth_details["ua"],
            "view": "odileague",
        }

        resp_bet = requests.post(
            bet_url, headers=bet_headers, cookies=auth_details["cookies"], json=bet_payload, timeout=TIMEOUT
        )
        bet_result = resp_bet.json()
        status_desc = bet_result.get("status_description", "Unknown")

        result_line = f"{url} -> {slip_item['outcome_name']} -> {status_desc}\n"
        log_func(f"INFO (Rollover): {result_line.strip()}")
        _write_output(output_filename, result_line)
        if job is not None and _looks_like_success(status_desc):
            _apply_success_charge(job, payload.task_type, url, log_func)
    except Exception as e:
        log_func(f"Error during single rollover bet for {url}: {e}")


def _get_streak_details(auth_details: dict, log_func):
    try:
        streak_url = "https://odibets.com:443/pxy2/streaks"
        headers = {
            "Authorization": f"Bearer {auth_details['access_token']}",
            "User-Agent": auth_details["ua"],
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Referer": "https://odibets.com/account",
        }
        resp = requests.get(streak_url, headers=headers, cookies=auth_details["cookies"],           timeout=TIMEOUT)                                
        resp.raise_for_status()
        streak_data = resp.json()           
        return streak_data
    except Exception as e:
        log_func(f"Error occurred while fetching streak details for {auth_details.get('user_id', 'Unknown')}: {e}")
        return None

def process_single_user(
    target_number: str,
    payload: TaskPayload,
    log_func,
    stop_event: threading.Event,
    output_filename: str,
    job: dict | None = None,
):
    if stop_event.is_set():
        return

    task_type = payload.task_type

    if task_type == "app_bonus":
        auth_details = _get_android_auth_details(target_number, payload.target_password, log_func)
    elif task_type == "save_token":
        auth_details = _get_auth_details(target_number, payload.target_password, log_func)
        if auth_details and auth_details.get("access_token"):
            token = auth_details["access_token"]
            result_line = f"{target_number} {token}\n"
            log_func(f"SUCCESS (Save Token): Token found for {target_number}")
            _write_output(output_filename, result_line)
            if job is not None:
                _apply_success_charge(job, task_type, target_number, log_func)
        else:
            log_func(f"FAILED (Save Token): Could not retrieve token for {target_number}")
        return
    else:
        auth_details = _get_auth_details(target_number, payload.target_password, log_func)

    if not auth_details:
        return

    data = auth_details.get("data", {})

    try:
        if task_type == "balance":
            bl = data.get("balance", "0.00")
            bonus = data.get("bonus_balance", "0.00")
            result_line = f"{target_number} Actual: {bl} | Bonus: {bonus}\n"
            log_func(f"SUCCESS (Balance): {target_number} | Actual: {bl}, Bonus: {bonus}")
            _write_output(output_filename, result_line)
            if job is not None:
                _apply_success_charge(job, task_type, target_number, log_func)

        elif task_type == "bet":
            stake = _resolve_stake(data, payload)

            selections_url = (
                f"https://odibets.com:443/pxy2/bets?code={payload.share_code}"
                f"&ua={auth_details['ua']}&resource=bookingcode"
            )
            bet_headers = {
                "Authorization": f"Bearer {auth_details['access_token']}",
                "User-Agent": auth_details["ua"],
                "Content-Type": "application/json",
            }

            resp_selections = requests.get(
                selections_url, headers=bet_headers, cookies=auth_details["cookies"], timeout=TIMEOUT
            )
            resp_selections.raise_for_status()
            selections_data = resp_selections.json()

            if selections_data.get("status_code") != 200:
                msg = selections_data.get("message", "Booking code error")
                log_func(f"FAILED (Bet): {target_number} | {msg}")
                return
            selections=selections_data["data"]["selections"]    

            bet_url = "https://betting-api.apps.odibets.com:443/betting-api/api/v1/betting/sports/bets"
            bet_payload = {
                "stake_amount": float(stake),
                "slip": _create_betting_slip(selections),
                "use_bonus": payload.use_bonus,
                "attribution": "SPA",
                "auto_accept": True,
                "channel": "DESKTOPSPA",
            }

            resp_bet = requests.post(bet_url, headers=bet_headers, json=bet_payload, timeout=TIMEOUT)
            bet_result = resp_bet.json()

            if bet_result.get("response_status") == 200:
                desc = bet_result.get("response_message", "Bet Placed Successfully")
                result_line = f"{target_number} - Success (Stake: {stake}): {desc}\n"
                log_func(f"SUCCESS (Bet): {target_number} | {desc}")
                if job is not None:
                    _apply_success_charge(job, task_type, target_number, log_func)
            else:
                err = bet_result.get("status_message", "Bet placement error")
                result_line = f"{target_number} - Bet Failed: {err}\n"
                log_func(f"FAILED (Bet): {target_number} | {err}")

            _write_output(output_filename, result_line)
        elif task_type == "streak":
            str_result = _get_streak_details(auth_details, log_func)
            if str_result is None:
                log_func(f"FAILED (Streak): {target_number} | Could not retrieve streak details")
                return
            streak_data = str_result.get("data", {})
            streak_count = streak_data.get("current_streak", 0)
            
            result_line = f"{target_number} Streak Count: {streak_count}\n"
            log_func(f"INFO (Streak): {target_number} | Streak Count: {streak_count}")
            _write_output(output_filename, result_line)

        elif task_type == "claim_bonus":
            
            clmrslt = _get_streak_details(auth_details, log_func)
            if clmrslt is None:
                log_func(f"FAILED (Claim Bonus): {target_number} | Could not retrieve streak details")
                return
            existing_rewards = clmrslt.get("data", {}).get("unclaimed_rewards", [])
            if not existing_rewards:
                result_line = f"{target_number} Claim Bonus: No unclaimed rewards available\n"
                log_func(f"INFO (Claim Bonus): {target_number} | No unclaimed rewards available")
            else:       
                for reward in existing_rewards:
                    reward_id = reward.get("id")
                    claim_url = "https://odibets.com:443/pxy2/streaks"
                    claim_payload = {"id": reward_id}
                    resp_claim = requests.post(
                        claim_url, headers=bet_headers, cookies=auth_details["cookies"], json=claim_payload, timeout=TIMEOUT
                    )
                    claim_result = resp_claim.json()
                    status_desc = claim_result.get("status_description", "Unknown")
                    result_line = f"{target_number} Claim Bonus: {status_desc}\n"
                    log_func(f"INFO (Claim Bonus): {target_number} | {status_desc}") 
            _write_output(output_filename, result_line)

        elif task_type == "virtual_bet":
            stake = _resolve_stake(data, payload)
            virtual_headers = {
                "Authorization": f"Bearer {auth_details['access_token']}",
                "X-Odi-Key": auth_details["session_token"],
                "User-Agent": auth_details["ua"],
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Referer": "https://odibets.com/odileague",
                "Origin": "https://odibets.com",
            }

            periods_url = (
                "https://odibets.com:443/pxy/virtuals?competition_id=1&tab=&period=&level=1"
                "&platform=desktop&view=odileague&resource=virtuals"
            )
            resp_periods = requests.get(
                periods_url, headers=virtual_headers, cookies=auth_details["cookies"], timeout=TIMEOUT
            )
            resp_periods.raise_for_status()
            periods_data = resp_periods.json()

            if periods_data.get("status_code") != 200:
                log_func(f"FAILED (Virtual Bet): Could not get virtual periods for {target_number}")
                return

            period_time_str = periods_data["data"]["periods"][10]["start_time"]
            formatted_time = datetime.strptime(period_time_str, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d+%H:%M:%S")

            matches_url = (
                f"https://odibets.com:443/pxy/virtuals?competition_id=1&period={formatted_time}"
                f"&sub_type_id=TG25&level=4&platform=desktop&view=odileague&resource=virtuals"
            )
            resp_matches = requests.get(
                matches_url, headers=virtual_headers, cookies=auth_details["cookies"], timeout=TIMEOUT
            )
            resp_matches.raise_for_status()
            matches_data = resp_matches.json()

            balanced_slip = _generate_balanced_gg_slip(matches_data["data"]["matches"])

            if balanced_slip and len(balanced_slip) == 2:
                bet_url = "https://odibets.com:443/pxy/bet"

                bet_payload1 = {
                    "auto_oc": False,
                    "bet_amount": float(stake),
                    "id": "",
                    "resource": "bet",
                    "slip": [balanced_slip[0]],
                    "sportsbook": "virtuals",
                    "src": "bet",
                    "ua": auth_details["ua"],
                    "view": "odileague",
                }
                resp_bet1 = requests.post(
                    bet_url, headers=virtual_headers, cookies=auth_details["cookies"], json=bet_payload1, timeout=TIMEOUT
                )
                bet_result1 = resp_bet1.json()
                status_desc1 = bet_result1.get("status_description", "Unknown")
                log_func(f"INFO (Virtual Bet 1/2): {target_number} | {status_desc1}")

                if bet_result1.get("status_code") == 200:
                    bet_payload2 = {
                        "auto_oc": False,
                        "bet_amount": float(stake),
                        "id": "",
                        "resource": "bet",
                        "slip": [balanced_slip[1]],
                        "sportsbook": "virtuals",
                        "src": "bet",
                        "ua": auth_details["ua"],
                        "view": "odileague",
                    }
                    resp_bet2 = requests.post(
                        bet_url,
                        headers=virtual_headers,
                        cookies=auth_details["cookies"],
                        json=bet_payload2,
                        timeout=TIMEOUT,
                    )
                    bet_result2 = resp_bet2.json()
                    status_desc2 = bet_result2.get("status_description", "Unknown")
                    log_func(f"INFO (Virtual Bet 2/2): {target_number} | {status_desc2}")
                    result_line = f"{target_number} - Virtual Bet 1: {status_desc1} | Virtual Bet 2: {status_desc2}\n"
                else:
                    result_line = f"{target_number} - Virtual Bet 1: {status_desc1} | Virtual Bet 2: Not Attempted\n"

                _write_output(output_filename, result_line)
                if job is not None and _looks_like_success(status_desc1):
                    _apply_success_charge(job, task_type, target_number, log_func)
            else:
                log_func(f"INFO (Virtual Bet): No balanced market found for {target_number}")

        
        

        elif task_type == "withdrawal":
            stake = payload.amount
            result_line = f"{target_number} Withdrawal: {stake} | pending implementation\n"
            log_func(f"SKELETON (Withdrawal): {target_number} | amount={stake}")
            _write_output(output_filename, result_line)

        elif task_type == "cashout":
            bet_id = (payload.bet_id or "").strip() or "all"
            result_line = f"{target_number} Cashout: {bet_id} | pending implementation\n"
            log_func(f"SKELETON (Cashout): {target_number} | bet_id={bet_id}")
            _write_output(output_filename, result_line)

        else:
            log_func(f"Unknown task type: {task_type}")

    except Exception as e:
        log_func(f"Error processing {task_type} for {target_number}: {str(e)}")
