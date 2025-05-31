import requests
import json
from bs4 import BeautifulSoup
import re
from datetime import datetime, timezone, timedelta
import time
import os

# --- Configuration (can be overridden by environment variables) ---
DEFAULT_CHANNEL_ID = os.environ.get('TV_CHANNEL_ID', '7') # Default to '7' (KBS2) if env var not set
OUTPUT_JSON_FILENAME = os.environ.get('OUTPUT_FILENAME', 'tv_schedule.json') # Default output name
ERROR_JSON_FILENAME = f"ERROR_{OUTPUT_JSON_FILENAME}"

# Define KST timezone offset
KST_OFFSET_HOURS = 9
KST_TIMEZONE = timezone(timedelta(hours=KST_OFFSET_HOURS))

def fetch_schedule_html_post(channel_id, date_str_yyyymmdd=None, channel_type="4", view_type_val="1"):
    """
    Fetches HTML content from the KT TV schedule URL using POST.
    - channel_id: The service channel number (e.g., '7' for KBS2).
    - date_str_yyyymmdd: The date in 'YYYYMMDD' format (e.g., '20250601').
                         If None or empty, fetches for the current day (server default).
    - channel_type: The channel type (e.g., '4').
    - view_type_val: The view type (e.g., '1' for daily schedule).
    """
    url = "https://tv.kt.com/tv/channel/pSchedule.asp"

    payload = {
        'ch_type': channel_type,
        'service_ch_no': channel_id,
        'view_type': view_type_val
    }

    if date_str_yyyymmdd:
        payload['seldate'] = date_str_yyyymmdd
        print(f"Fetching schedule for Channel ID: {channel_id}, Specific Date: {date_str_yyyymmdd}")
    else:
        print(f"Fetching schedule for Channel ID: {channel_id}, Current Day (server default)")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': 'https://tv.kt.com/',
        'X-Requested-With': 'XMLHttpRequest',
        'Origin': 'https://tv.kt.com'
    }

    try:
        print(f"Attempting to fetch schedule with payload: {payload}")
        response = requests.post(url, data=payload, headers=headers, timeout=15)
        response.raise_for_status()

        try:
            response.encoding = 'euc-kr'
            html_text = response.text
        except UnicodeDecodeError:
            response.encoding = response.apparent_encoding or 'utf-8'
            html_text = response.text
            
        return html_text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            error_text = e.response.content
            try:
                decoded_error_text = error_text.decode('euc-kr')
            except UnicodeDecodeError:
                try:
                    decoded_error_text = error_text.decode(e.response.apparent_encoding or 'utf-8', errors='replace')
                except Exception:
                    decoded_error_text = str(error_text)
            print(f"Response text: {decoded_error_text[:500]}...")
        return None

def parse_schedule_to_json(html_content, channel_id_for_log="N/A", requested_date_str="N/A"):
    """Parses the HTML content of the TV schedule and returns a dictionary."""
    if not html_content:
        return {
            "error_summary": "No HTML content received to parse.",
            "channel_id_requested": channel_id_for_log,
            "date_requested": requested_date_str if requested_date_str else "Current Day (default)"
        }

    soup = BeautifulSoup(html_content, 'html.parser')
    schedule_data = {}

    schedule_data['channel_id_requested'] = channel_id_for_log
    schedule_data['date_requested'] = requested_date_str if requested_date_str else "Current Day (default)"

    date_tag = soup.find('strong', class_='day')
    if date_tag:
        date_str_raw = date_tag.get_text(strip=True)
        match = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", date_str_raw)
        if match:
            year, month, day = match.groups()
            schedule_data['date_displayed'] = f"{year}-{int(month):02d}-{int(day):02d}"
        else:
            schedule_data['date_displayed'] = date_str_raw
    else:
        if not soup.find('table', class_='board tb_schedule'):
            schedule_data['error_summary'] = "Core schedule structure (date or table) not found in HTML."
            schedule_data['date_displayed'] = "N/A (parsing error)"
        else:
             schedule_data['date_displayed'] = "N/A (date tag not found in HTML)"

    channel_logo_tag = soup.find('h5', class_='b_logo')
    if channel_logo_tag and channel_logo_tag.find('img'):
        img_tag = channel_logo_tag.find('img')
        schedule_data['channel_name'] = img_tag.get('alt', f'Channel ID: {channel_id_for_log}')
        logo_src = img_tag.get('src', '')
        if logo_src.startswith('http'):
            schedule_data['channel_logo_url'] = logo_src
        elif logo_src:
            schedule_data['channel_logo_url'] = "https://tv.kt.com" + logo_src
        else:
            schedule_data['channel_logo_url'] = ''
    else:
        schedule_data['channel_name'] = f'Channel ID: {channel_id_for_log}'
        schedule_data['channel_logo_url'] = ''
    
    schedule_data['programs'] = []
    schedule_table = soup.find('table', class_='board tb_schedule')

    if schedule_table and schedule_table.find('tbody'):
        rows = schedule_table.find('tbody').find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 4: continue
            
            hour_str = cells[0].get_text(strip=True)
            
            minute_p_tags = cells[1].find_all('p')
            program_p_tags = cells[2].find_all('p')
            category_p_tags = cells[3].find_all('p')
            
            num_programs_in_slot = len(program_p_tags)

            for i in range(num_programs_in_slot):
                program_entry = {}
                program_p_current = program_p_tags[i]
                
                minute_str = "00"
                if i < len(minute_p_tags): minute_str = minute_p_tags[i].get_text(strip=True)
                program_entry['time'] = f"{hour_str}:{minute_str}"
                
                temp_program_soup = BeautifulSoup(str(program_p_current), 'html.parser')
                current_p_for_text = temp_program_soup.p 
                
                is_on_air = False
                program_title = "N/A"

                if current_p_for_text:
                    online_strong_tag = current_p_for_text.find('strong', class_='online')
                    if online_strong_tag:
                        is_on_air = True
                        online_strong_tag.decompose()

                    for b_tag in current_p_for_text.find_all('b'):
                        b_tag.decompose()
                    
                    program_title = current_p_for_text.get_text(separator=' ', strip=True)

                program_entry['title'] = program_title
                program_entry['is_on_air'] = is_on_air
                
                icons = []
                for b_tag in program_p_current.find_all('b'):
                    img_icon_tag = b_tag.find('img')
                    alt_text = img_icon_tag.get('alt', '').strip() if img_icon_tag else ''
                    if alt_text:
                        icons.append(alt_text)
                    elif img_icon_tag:
                        icon_src = img_icon_tag.get('src','')
                        icons.append(f"Icon (src: {icon_src})") 
                program_entry['icons'] = icons
                
                genre_str = "N/A"
                if i < len(category_p_tags): genre_str = category_p_tags[i].get_text(strip=True)
                program_entry['genre'] = genre_str

                schedule_data['programs'].append(program_entry)
    elif 'error_summary' not in schedule_data:
         schedule_data.setdefault('error_summary', "Schedule table ('board tb_schedule') not found in the HTML.")

    if not schedule_data.get('programs') and 'error_summary' not in schedule_data:
        schedule_data.setdefault('error_summary', "No programs found.")

    return schedule_data # Return the dictionary

def is_todays_schedule_still_relevant(programs_today, current_kst_time_obj):
    """
    Checks if today's schedule has relevant upcoming programs.
    - programs_today: List of program dictionaries for today.
    - current_kst_time_obj: A datetime object representing the current time in KST.
    """
    if not programs_today:
        print("is_todays_schedule_still_relevant: No programs for today, so not relevant.")
        return False

    LATE_NIGHT_CUTOFF_HOUR_KST = 1

    # Get current KST date for creating program datetime objects
    current_kst_date = current_kst_time_obj.date()

    found_upcoming_program = False
    for program in programs_today:
        try:
            program_time_str = program.get('time', '00:00')
            program_hour = int(program_time_str.split(':')[0])
            program_minute = int(program_time_str.split(':')[1])

            # Create a datetime object for the program's start time in KST
            # This assumes programs are for the current_kst_date.
            # Handles programs that might start at 00:xx or 01:xx after midnight
            # but are still part of the "previous" broadcast day's listing.
            program_start_kst = datetime(current_kst_date.year, current_kst_date.month, current_kst_date.day,
                                         program_hour, program_minute, tzinfo=KST_TIMEZONE)
            
            # If a program time is like "00:30" and current KST is "23:00" of the *same calendar day*,
            # this program is effectively for the *next* day's very early morning if it's part of *today's* listing.
            # This can be tricky if schedules list "00:30" as part of the *current* day's programming.
            # For simplicity here, we assume 'time' in HH:MM refers to that specific calendar day.
            # The KT site seems to list e.g. 00:30 programs under the date they start.

            if program_start_kst > current_kst_time_obj:
                print(f"is_todays_schedule_still_relevant: Found upcoming program: {program.get('title')} at {program_time_str} KST.")
                found_upcoming_program = True
                break # Found at least one upcoming program
        except (ValueError, IndexError, AttributeError) as e:
            print(f"is_todays_schedule_still_relevant: Error parsing program time '{program.get('time')}': {e}")
            continue

    if not found_upcoming_program:
        print("is_todays_schedule_still_relevant: No more upcoming programs found for today's schedule based on start times.")
        # If it's already past the late-night cutoff, it's definitely not relevant.
        if current_kst_time_obj.hour >= LATE_NIGHT_CUTOFF_HOUR_KST:
            print(f"is_todays_schedule_still_relevant: Current KST hour ({current_kst_time_obj.hour}) is at or past late-night cutoff ({LATE_NIGHT_CUTOFF_HOUR_KST} AM).")
            return False
        return False # No upcoming programs found

    print("is_todays_schedule_still_relevant: Today's schedule is still considered relevant.")
    return True


# --- Main execution block ---
if __name__ == "__main__":
    target_channel_id = DEFAULT_CHANNEL_ID
    default_channel_type = "4"
    default_view_type = "1"

    now_utc = datetime.now(timezone.utc)
    now_kst = now_utc.astimezone(KST_TIMEZONE)
    
    print(f"--- Script run at {now_kst.strftime('%Y-%m-%d %H:%M:%S KST')} ---")

    # --- Stage 1: Fetch Today's Schedule ---
    # For KT server, omitting 'seldate' fetches the current day according to its clock.
    # Using today's KST date string is also an option if server interpretation varies.
    date_to_fetch_today_param = None # Let server decide "today"
    # date_to_fetch_today_param = now_kst.strftime("%Y%m%d") # Alternative: be explicit
    
    print(f"\n--- Attempting to fetch schedule for TODAY (Server's current day, KST approx: {now_kst.strftime('%Y%m%d')}) ---")
    html_today = fetch_schedule_html_post(
        channel_id=target_channel_id,
        date_str_yyyymmdd=date_to_fetch_today_param,
        channel_type=default_channel_type,
        view_type_val=default_view_type
    )

    schedule_data_to_use = None
    # effective_date_for_output = now_kst.strftime("%Y-%m-%d") # Will be set by parsed data

    if html_today:
        print("HTML for today fetched successfully. Parsing schedule...")
        # When parsing, the 'requested_date_str' is for logging/context within the JSON
        parsed_data_today = parse_schedule_to_json(html_today, target_channel_id, f"{now_kst.strftime('%Y%m%d')}")
        
        if "error_summary" not in parsed_data_today and parsed_data_today.get("programs"):
            print(f"Today's schedule ({parsed_data_today.get('date_displayed')}) parsed successfully with {len(parsed_data_today.get('programs', []))} programs.")
            if is_todays_schedule_still_relevant(parsed_data_today.get("programs", []), now_kst):
                print("Today's schedule is still relevant. Using today's data.")
                schedule_data_to_use = parsed_data_today
            else:
                print("Today's schedule seems over or has no more upcoming programs. Will attempt to fetch tomorrow's schedule.")
        else:
            error_msg = parsed_data_today.get("error_summary", "Unknown parsing error or no programs found for today.")
            print(f"Error parsing today's schedule or no programs: {error_msg}")
            print("Will attempt to fetch tomorrow's schedule.")
    else:
        print("Failed to fetch HTML for today. Will attempt to fetch tomorrow's schedule.")

    # --- Stage 2: Fetch Tomorrow's Schedule (if today's wasn't used or failed) ---
    if schedule_data_to_use is None:
        tomorrow_kst_date_obj = now_kst.date() + timedelta(days=1)
        date_to_fetch_tomorrow_param = tomorrow_kst_date_obj.strftime("%Y%m%d")
        
        print(f"\n--- Attempting to fetch schedule for TOMORROW ({date_to_fetch_tomorrow_param}) ---")
        html_tomorrow = fetch_schedule_html_post(
            channel_id=target_channel_id,
            date_str_yyyymmdd=date_to_fetch_tomorrow_param,
            channel_type=default_channel_type,
            view_type_val=default_view_type
        )

        if html_tomorrow:
            print("HTML for tomorrow fetched successfully. Parsing schedule...")
            parsed_data_tomorrow = parse_schedule_to_json(html_tomorrow, target_channel_id, date_to_fetch_tomorrow_param)
            if "error_summary" not in parsed_data_tomorrow and parsed_data_tomorrow.get("programs"):
                print(f"Tomorrow's schedule ({parsed_data_tomorrow.get('date_displayed')}) parsed successfully with {len(parsed_data_tomorrow.get('programs', []))} programs. Using tomorrow's data.")
                schedule_data_to_use = parsed_data_tomorrow
            else:
                error_msg = parsed_data_tomorrow.get("error_summary", "Unknown parsing error or no programs found for tomorrow.")
                print(f"Error parsing tomorrow's schedule or no programs: {error_msg}")
                if schedule_data_to_use is None: # Still no valid data
                     schedule_data_to_use = {
                        "error_summary": f"Failed to get relevant schedule. Today: fetch/parse issue. Tomorrow: {error_msg}",
                        "channel_id_requested": target_channel_id,
                        "date_requested": f"Attempted Today & {date_to_fetch_tomorrow_param}"
                    }
        else:
            print("Failed to fetch HTML for tomorrow.")
            if schedule_data_to_use is None: 
                schedule_data_to_use = {
                    "error_summary": "Failed to fetch HTML for both today and tomorrow.",
                    "channel_id_requested": target_channel_id,
                    "date_requested": f"Attempted Today & Tomorrow ({date_to_fetch_tomorrow_param})"
                }
    
    # --- Prepare Final JSON Output ---
    final_data_to_write = {}
    output_filename_to_use = ERROR_JSON_FILENAME # Default to error filename

    if schedule_data_to_use and "error_summary" not in schedule_data_to_use:
        schedule_data_to_use['script_run_epoch_utc'] = int(time.time())
        schedule_data_to_use['script_run_iso_utc'] = datetime.now(timezone.utc).isoformat()
        
        # Add context message
        displayed_date_from_json = schedule_data_to_use.get('date_displayed', 'N/A')
        today_yyyymmdd_kst_str = now_kst.strftime('%Y-%m-%d') # For comparison with displayed_date

        if displayed_date_from_json == today_yyyymmdd_kst_str:
            schedule_data_to_use['schedule_context_message'] = f"Displaying schedule for today ({displayed_date_from_json})."
        elif displayed_date_from_json != 'N/A':
            schedule_data_to_use['schedule_context_message'] = f"Displaying schedule for {displayed_date_from_json} (likely tomorrow, as today's is complete/unavailable)."
        else: # date_displayed was N/A
            schedule_data_to_use['schedule_context_message'] = "Displaying available schedule data (date couldn't be confirmed)."


        final_data_to_write = schedule_data_to_use
        output_filename_to_use = OUTPUT_JSON_FILENAME
        print(f"\nFinal JSON data prepared for: {displayed_date_from_json}")
            
    else: 
        print("\nAn error occurred or no relevant schedule found. Error JSON will be generated.")
        if schedule_data_to_use is None: # Should have been set to an error dict by now
            schedule_data_to_use = {
                "error_summary": "Critical error: No schedule data object was formed.",
                "channel_id_requested": target_channel_id
            }
        
        # Ensure standard error fields are present
        error_data = schedule_data_to_use
        if 'channel_id_requested' not in error_data: error_data['channel_id_requested'] = target_channel_id
        if 'date_requested' not in error_data: error_data['date_requested'] = f"Attempted Today & Tomorrow"

        error_data['script_run_epoch_utc'] = int(time.time())
        error_data['script_run_iso_utc'] = datetime.now(timezone.utc).isoformat()
        
        final_data_to_write = error_data
        # output_filename_to_use is already ERROR_JSON_FILENAME
        print(f"\nError JSON data prepared: {final_data_to_write.get('error_summary')}")

    try:
        with open(output_filename_to_use, 'w', encoding='utf-8') as f:
            json.dump(final_data_to_write, f, indent=2, ensure_ascii=False)
        print(f"Data saved to {output_filename_to_use}")
    except IOError as e:
        print(f"Error saving data to file {output_filename_to_use}: {e}")
