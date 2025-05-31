import requests
import json
from bs4 import BeautifulSoup
import re
from datetime import datetime, timezone, timedelta # Added timedelta
import time
import os

# --- Configuration (can be overridden by environment variables) ---
DEFAULT_CHANNEL_ID = os.environ.get('TV_CHANNEL_ID', '7')
OUTPUT_JSON_FILENAME = os.environ.get('OUTPUT_FILENAME', 'tv_schedule.json')
ERROR_JSON_FILENAME = f"ERROR_{OUTPUT_JSON_FILENAME}"

# Define KST timezone offset
KST_OFFSET_HOURS = 9
KST_TIMEZONE = timezone(timedelta(hours=KST_OFFSET_HOURS))

# --- (fetch_schedule_html_post and parse_schedule_to_json functions remain the same) ---
# ... (paste your existing fetch_schedule_html_post and parse_schedule_to_json here) ...
# Make sure parse_schedule_to_json returns the schedule_data dictionary

def is_todays_schedule_still_relevant(programs_today, current_kst_time):
    """
    Checks if today's schedule has relevant upcoming programs.
    - programs_today: List of program dictionaries for today.
    - current_kst_time: A datetime object representing the current time in KST.
    """
    if not programs_today:
        return False # No programs for today, so not relevant

    # Define a cut-off hour in KST (e.g., 2 AM - broadcasts for the "day" are likely over)
    # If current KST hour is >= LATE_NIGHT_CUTOFF_HOUR_KST, consider fetching next day.
    LATE_NIGHT_CUTOFF_HOUR_KST = 2 # 2 AM

    if current_kst_time.hour >= LATE_NIGHT_CUTOFF_HOUR_KST:
        # Check if there are any programs scheduled after this late-night cutoff
        # This handles cases where a "day's" schedule might run past midnight into the early morning.
        # We are primarily interested if there are programs *after* current_kst_time.
        pass # Continue to check upcoming programs

    for program in programs_today:
        try:
            program_time_parts = program.get('time', '00:00').split(':')
            program_hour = int(program_time_parts[0])
            program_minute = int(program_time_parts[1])
            
            # Compare with current KST time (only hour and minute for simplicity here)
            # A more robust comparison would involve creating full datetime objects for each program.
            if program_hour > current_kst_time.hour:
                return True # Found a program later today
            if program_hour == current_kst_time.hour and program_minute > current_kst_time.minute:
                return True # Found a program later in the current hour
        except (ValueError, IndexError):
            continue # Skip malformed program times

    # If loop finishes, no programs found starting after current_kst_time
    # Additionally, if it's past the late-night cutoff, we might also lean towards next day.
    if current_kst_time.hour >= LATE_NIGHT_CUTOFF_HOUR_KST:
         # If it's, for example, 3 AM, and the last program was at 1 AM, today is likely done.
         # If the last program was at 3:30 AM, this function would have returned True above.
         # This condition acts as a further incentive to check next day if it's very late.
         print(f"Current KST hour {current_kst_time.hour} is at or past late-night cutoff {LATE_NIGHT_CUTOFF_HOUR_KST} AM and no further programs found for today.")
         # return False # Can be more aggressive here if needed
    
    print("No more upcoming programs found for today's schedule or it's very late.")
    return False


# --- Main execution block ---
if __name__ == "__main__":
    target_channel_id = DEFAULT_CHANNEL_ID
    default_channel_type = "4"
    default_view_type = "1"

    # Get current time in KST
    now_utc = datetime.now(timezone.utc)
    now_kst = now_utc.astimezone(KST_TIMEZONE)
    
    # --- Stage 1: Fetch Today's Schedule ---
    print(f"--- Attempting to fetch schedule for TODAY ({now_kst.strftime('%Y%m%d')}) ---")
    # For KT server, omitting 'seldate' fetches the current day.
    # However, to be explicit and for potential future use, let's use today's KST date.
    # The KT server seems to determine "today" based on its own clock,
    # so sending `None` for date_to_fetch is often the most reliable for "current server day".
    # Let's stick to date_to_fetch = None for today initially.
    date_to_fetch_today = None # This tells the server to use its current date.
    # Or, if you want to be explicit with KST date:
    # date_to_fetch_today = now_kst.strftime("%Y%m%d")

    html_today = fetch_schedule_html_post(
        channel_id=target_channel_id,
        date_str_yyyymmdd=date_to_fetch_today, # Use None for server's current day
        channel_type=default_channel_type,
        view_type_val=default_view_type
    )

    schedule_data_to_use = None
    effective_date_for_output = now_kst.strftime("%Y-%m-%d") # Default to today

    if html_today:
        print("\nHTML for today fetched successfully. Parsing schedule...")
        parsed_data_today = parse_schedule_to_json(html_today, target_channel_id, "Today")
        
        if "error_summary" not in parsed_data_today and parsed_data_today.get("programs"):
            print("Today's schedule parsed successfully.")
            # Analyze if today's schedule is still relevant
            if is_todays_schedule_still_relevant(parsed_data_today.get("programs", []), now_kst):
                print("Today's schedule is still relevant. Using today's data.")
                schedule_data_to_use = parsed_data_today
                effective_date_for_output = parsed_data_today.get('date_displayed', effective_date_for_output)
            else:
                print("Today's schedule seems over or sparse. Will attempt to fetch tomorrow's schedule.")
        else:
            print("Error parsing today's schedule or no programs found. Will attempt to fetch tomorrow's schedule.")
            if "error_summary" in parsed_data_today:
                print(f"Error details for today: {parsed_data_today['error_summary']}")

    else: # html_today is None, fetch failed
        print("\nFailed to fetch HTML for today. Will attempt to fetch tomorrow's schedule.")

    # --- Stage 2: Fetch Tomorrow's Schedule (if today's wasn't used) ---
    if schedule_data_to_use is None:
        tomorrow_kst = now_kst + timedelta(days=1)
        date_to_fetch_tomorrow = tomorrow_kst.strftime("%Y%m%d")
        effective_date_for_output = tomorrow_kst.strftime("%Y-%m-%d") # Update for output context

        print(f"\n--- Attempting to fetch schedule for TOMORROW ({date_to_fetch_tomorrow}) ---")
        html_tomorrow = fetch_schedule_html_post(
            channel_id=target_channel_id,
            date_str_yyyymmdd=date_to_fetch_tomorrow,
            channel_type=default_channel_type,
            view_type_val=default_view_type
        )

        if html_tomorrow:
            print("\nHTML for tomorrow fetched successfully. Parsing schedule...")
            parsed_data_tomorrow = parse_schedule_to_json(html_tomorrow, target_channel_id, date_to_fetch_tomorrow)
            if "error_summary" not in parsed_data_tomorrow and parsed_data_tomorrow.get("programs"):
                print("Tomorrow's schedule parsed successfully. Using tomorrow's data.")
                schedule_data_to_use = parsed_data_tomorrow
                effective_date_for_output = parsed_data_tomorrow.get('date_displayed', effective_date_for_output)
            else:
                print("Error parsing tomorrow's schedule or no programs found for tomorrow.")
                if "error_summary" in parsed_data_tomorrow:
                     print(f"Error details for tomorrow: {parsed_data_tomorrow['error_summary']}")
                # Fallback: if today had an error and tomorrow also has an error/no programs, create minimal error JSON
                if schedule_data_to_use is None: # Still no valid data
                     schedule_data_to_use = {
                        "error_summary": "Failed to fetch relevant schedule for today and tomorrow.",
                        "channel_id_requested": target_channel_id,
                        "date_requested": f"Attempted Today & {date_to_fetch_tomorrow}"
                    }
        else:
            print("\nFailed to fetch HTML for tomorrow.")
            if schedule_data_to_use is None: # Still no valid data (today failed, tomorrow failed to fetch)
                schedule_data_to_use = {
                    "error_summary": "Failed to fetch HTML for both today and tomorrow.",
                    "channel_id_requested": target_channel_id,
                    "date_requested": f"Attempted Today & {date_to_fetch_tomorrow}"
                }
    
    # --- Prepare Final JSON Output ---
    final_data_to_write = {}
    output_filename_to_use = ERROR_JSON_FILENAME # Default to error filename

    if schedule_data_to_use and "error_summary" not in schedule_data_to_use:
        # Add script run timestamps to the chosen schedule data
        schedule_data_to_use['script_run_epoch_utc'] = int(time.time())
        schedule_data_to_use['script_run_iso_utc'] = datetime.now(timezone.utc).isoformat()
        
        # Ensure 'date_requested' reflects what was effectively fetched
        # The parse_schedule_to_json already sets 'date_requested' based on its input.
        # We might want to add a field like 'effective_schedule_target_date_type': 'today' or 'tomorrow'
        if schedule_data_to_use.get('date_displayed') == now_kst.strftime('%Y-%m-%d') or \
           schedule_data_to_use.get('date_requested') == "Today": # A bit heuristic
            schedule_data_to_use['schedule_context_message'] = f"Displaying schedule for today ({schedule_data_to_use.get('date_displayed')})."
        else:
            schedule_data_to_use['schedule_context_message'] = f"Displaying schedule for tomorrow ({schedule_data_to_use.get('date_displayed')}) as today's schedule is complete or unavailable."

        final_data_to_write = schedule_data_to_use
        output_filename_to_use = OUTPUT_JSON_FILENAME
        print(f"\nFinal JSON data prepared for: {schedule_data_to_use.get('date_displayed')}")
            
    else: # An error occurred, or no relevant schedule found
        print("\nAn error occurred or no relevant schedule found. Error JSON will be generated.")
        # Ensure schedule_data_to_use is at least an empty dict if it's None
        if schedule_data_to_use is None:
            schedule_data_to_use = {
                "error_summary": "Unknown error or no data could be determined for today or tomorrow.",
                "channel_id_requested": target_channel_id
            }

        error_data = schedule_data_to_use # It already contains error_summary if it's an error dict
        error_data['script_run_epoch_utc'] = int(time.time())
        error_data['script_run_iso_utc'] = datetime.now(timezone.utc).isoformat()
        if 'date_requested' not in error_data: # Ensure this key exists
             error_data['date_requested'] = f"Attempted Today ({now_kst.strftime('%Y%m%d')}) & Tomorrow ({ (now_kst + timedelta(days=1)).strftime('%Y%m%d') })"
        
        final_data_to_write = error_data
        output_filename_to_use = ERROR_JSON_FILENAME # Already set, but for clarity
        print("\nError JSON data prepared.")

    # Write the JSON data to the file
    try:
        with open(output_filename_to_use, 'w', encoding='utf-8') as f:
            json.dump(final_data_to_write, f, indent=2, ensure_ascii=False)
        print(f"\nData saved to {output_filename_to_use}")
    except IOError as e:
        print(f"\nError saving data to file {output_filename_to_use}: {e}")
