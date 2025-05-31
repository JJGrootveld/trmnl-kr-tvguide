import requests
import json
from bs4 import BeautifulSoup
import re
from datetime import datetime

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

    # If a specific date is provided, add 'seldate' to the payload.
    # Otherwise, no date parameter is sent (for current day).
    if date_str_yyyymmdd:
        payload['seldate'] = date_str_yyyymmdd
        print(f"Fetching schedule for a specific date: {date_str_yyyymmdd}")
    else:
        print("No specific date provided. Fetching for the current day (server default).")


    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Referer': 'https://tv.kt.com/', # Important for the server to accept the request
        'X-Requested-With': 'XMLHttpRequest', # Often indicates an AJAX request
        'Origin': 'https://tv.kt.com' # Important for cross-origin policies if checked by server
    }

    try:
        print(f"Attempting to fetch schedule with payload: {payload}")
        response = requests.post(url, data=payload, headers=headers, timeout=15) # 15-second timeout
        response.raise_for_status() # Raises an HTTPError for bad responses (4XX or 5XX)

        # The website uses 'euc-kr' encoding
        try:
            response.encoding = 'euc-kr'
            html_text = response.text
        except UnicodeDecodeError:
            # Fallback if euc-kr fails (e.g., error page in different encoding)
            response.encoding = response.apparent_encoding or 'utf-8'
            html_text = response.text
            
        return html_text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {url}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            error_text = e.response.content # Get raw bytes for decoding
            try:
                # Attempt to decode with the expected encoding first
                decoded_error_text = error_text.decode('euc-kr')
            except UnicodeDecodeError:
                try:
                    # Fallback to UTF-8 or apparent encoding
                    decoded_error_text = error_text.decode(e.response.apparent_encoding or 'utf-8', errors='replace')
                except Exception:
                    decoded_error_text = str(error_text) # Last resort, show raw bytes as string
            print(f"Response text: {decoded_error_text[:500]}...") # Print first 500 chars of error
        return None

def parse_schedule_to_json(html_content, channel_id_for_log="N/A", requested_date_str="N/A"):
    """Parses the HTML content of the TV schedule and returns a JSON string."""
    if not html_content:
        return json.dumps({
            "error_summary": "No HTML content received to parse.",
            "channel_id_requested": channel_id_for_log,
            "date_requested": requested_date_str if requested_date_str else "Current Day (default)"
        }, indent=2, ensure_ascii=False)

    soup = BeautifulSoup(html_content, 'html.parser')
    schedule_data = {}

    # Store requested parameters for context in the JSON output
    schedule_data['channel_id_requested'] = channel_id_for_log
    schedule_data['date_requested'] = requested_date_str if requested_date_str else "Current Day (default)"

    # Extract the date displayed on the page
    date_tag = soup.find('strong', class_='day')
    if date_tag:
        date_str_raw = date_tag.get_text(strip=True)
        # Regex to parse "YYYY년 MM월 DD일(요일)" format
        match = re.match(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", date_str_raw)
        if match:
            year, month, day = match.groups()
            schedule_data['date_displayed'] = f"{year}-{int(month):02d}-{int(day):02d}"
        else:
            schedule_data['date_displayed'] = date_str_raw # Fallback to raw text if regex fails
    else:
        # If the main schedule structure is missing, it indicates a likely error
        if not soup.find('table', class_='board tb_schedule'):
            schedule_data['error_summary'] = "Core schedule structure (date or table) not found in HTML. The page might be an error page, or the channel/date combination is invalid."
            schedule_data['date_displayed'] = "N/A (parsing error)"
        else:
             schedule_data['date_displayed'] = "N/A (date tag not found in HTML)"


    # Extract channel information
    channel_logo_tag = soup.find('h5', class_='b_logo')
    if channel_logo_tag and channel_logo_tag.find('img'):
        img_tag = channel_logo_tag.find('img')
        schedule_data['channel_name'] = img_tag.get('alt', f'Channel ID: {channel_id_for_log}') # Use alt text for name
        logo_src = img_tag.get('src', '')
        if logo_src.startswith('http'): # If absolute URL
            schedule_data['channel_logo_url'] = logo_src
        elif logo_src: # If relative URL, prepend base
            schedule_data['channel_logo_url'] = "https://tv.kt.com" + logo_src
        else:
            schedule_data['channel_logo_url'] = '' # No src attribute found
    else:
        schedule_data['channel_name'] = f'Channel ID: {channel_id_for_log}' # Fallback if logo/alt not found
        schedule_data['channel_logo_url'] = ''
    
    schedule_data['programs'] = []
    schedule_table = soup.find('table', class_='board tb_schedule')

    if schedule_table and schedule_table.find('tbody'):
        rows = schedule_table.find('tbody').find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 4: continue # Ensure it's a data row with enough cells
            
            hour_str = cells[0].get_text(strip=True)
            
            minute_p_tags = cells[1].find_all('p')
            program_p_tags = cells[2].find_all('p')
            category_p_tags = cells[3].find_all('p')
            
            num_programs_in_slot = len(program_p_tags)

            for i in range(num_programs_in_slot):
                program_entry = {}
                program_p_current = program_p_tags[i] # The <p> tag for the current program
                
                minute_str = "00" # Default minute
                if i < len(minute_p_tags): minute_str = minute_p_tags[i].get_text(strip=True)
                program_entry['time'] = f"{hour_str}:{minute_str}"
                
                # For cleaning title, create a temporary soup object from the program's <p> tag
                temp_program_soup = BeautifulSoup(str(program_p_current), 'html.parser')
                current_p_for_text = temp_program_soup.p 
                
                is_on_air = False
                program_title = "N/A"

                if current_p_for_text:
                    online_strong_tag = current_p_for_text.find('strong', class_='online')
                    if online_strong_tag:
                        is_on_air = True
                        online_strong_tag.decompose() # Remove "방송중" text for cleaner title

                    # Remove icon <b> tags for cleaner title
                    for b_tag in current_p_for_text.find_all('b'):
                        b_tag.decompose()
                    
                    program_title = current_p_for_text.get_text(separator=' ', strip=True)

                program_entry['title'] = program_title
                program_entry['is_on_air'] = is_on_air
                
                # Extract icons (from the original program_p_current tag)
                icons = []
                for b_tag in program_p_current.find_all('b'): # Iterate through <b> tags containing icons
                    img_icon_tag = b_tag.find('img')
                    alt_text = img_icon_tag.get('alt', '').strip() if img_icon_tag else ''
                    if alt_text: # Prioritize alt text if available and not empty
                        icons.append(alt_text)
                    elif img_icon_tag: # Fallback to src if alt is missing/empty
                        icon_src = img_icon_tag.get('src','')
                        # You could map known src paths to descriptions here if needed
                        # e.g., if 'icon_18x18_cap.png' in icon_src: icons.append("자막방송")
                        icons.append(f"Icon (src: {icon_src})") 
                program_entry['icons'] = icons
                
                genre_str = "N/A" # Default genre
                if i < len(category_p_tags): genre_str = category_p_tags[i].get_text(strip=True)
                program_entry['genre'] = genre_str

                schedule_data['programs'].append(program_entry)
    elif 'error_summary' not in schedule_data: # Add this error only if a major one isn't already set
         schedule_data['error_summary'] = "Schedule table ('board tb_schedule') not found in the HTML."

    # Final check: if no programs were parsed and no major error was set, note it.
    if not schedule_data.get('programs') and 'error_summary' not in schedule_data:
        schedule_data.setdefault('error_summary', "No programs found in the schedule table. The HTML structure might be different than expected, or the page is empty for this channel/date.")

    return json.dumps(schedule_data, indent=2, ensure_ascii=False)

# --- Main execution block ---
if __name__ == "__main__":
    # --- User Configuration ---
    target_channel_id = input("Enter Channel ID (service_ch_no, e.g., '7' for KBS2): ")
    if not target_channel_id: # Basic validation
        print("Channel ID is required. Exiting.")
        exit()
    
    # Ask for date, empty input means current day
    default_date_display = datetime.now().strftime("%Y-%m-%d (Today)")
    target_date_yyyymmdd_input = input(f"Enter Date in YYYYMMDD format (e.g., '20250601'), or press Enter for {default_date_display}: ")
    
    # This variable will be passed to fetch_schedule_html_post.
    # It remains None if user wants current day, otherwise it's the YYYYMMDD string.
    date_to_fetch = None 
    if target_date_yyyymmdd_input: # If user provided some input
        try:
            datetime.strptime(target_date_yyyymmdd_input, "%Y%m%d") # Validate format
            date_to_fetch = target_date_yyyymmdd_input
        except ValueError:
            print(f"Invalid date format '{target_date_yyyymmdd_input}'. Will attempt to fetch for current day.")
            # date_to_fetch remains None, so current day will be fetched
    else: # User pressed Enter
        print("No date entered. Will attempt to fetch for current day.")
        # date_to_fetch remains None

    # Default values from your findings, can be made configurable if needed
    default_channel_type = "4"
    default_view_type = "1" # For daily schedule

    # --- End User Configuration ---

    print(f"\nFetching schedule for Channel ID: {target_channel_id}, Date: {date_to_fetch if date_to_fetch else 'Current Day'}")
    html = fetch_schedule_html_post(
        channel_id=target_channel_id,
        date_str_yyyymmdd=date_to_fetch, # Pass None (for current day) or YYYYMMDD string
        channel_type=default_channel_type,
        view_type_val=default_view_type
    )
    
    if html:
        print("\nHTML fetched successfully. Parsing schedule...")
        json_data = parse_schedule_to_json(html, target_channel_id, date_to_fetch)
        print("\nJSON Output:")
        print(json_data)
        
        # Determine date part for filename (use today's date if 'date_to_fetch' is None)
        file_date_suffix = date_to_fetch if date_to_fetch else datetime.now().strftime("%Y%m%d") + "_today"
        output_filename = f'kt_tv_schedule_{target_channel_id}_{file_date_suffix}.json'
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(json_data)
            print(f"\nSchedule saved to {output_filename}")
        except IOError as e:
            print(f"\nError saving schedule to file {output_filename}: {e}")
            
    else: # html is None, fetch failed
        print("\nFailed to fetch HTML. No JSON will be generated.")
        
        # Prepare attempted payload for error log
        error_payload = {
            'ch_type': default_channel_type,
            'service_ch_no': target_channel_id,
            'view_type': default_view_type
        }
        if date_to_fetch: # Only add seldate if it was intended for the request
            error_payload['seldate'] = date_to_fetch

        error_json_output = json.dumps({
            "error_summary": "Failed to fetch HTML from server.",
            "channel_id_requested": target_channel_id,
            "date_requested": date_to_fetch if date_to_fetch else "Current Day (default)",
            "attempted_payload": error_payload # Show what payload was tried
        }, indent=2, ensure_ascii=False)
        
        file_date_suffix = date_to_fetch if date_to_fetch else datetime.now().strftime("%Y%m%d") + "_today"
        output_filename = f'kt_tv_schedule_ERROR_{target_channel_id}_{file_date_suffix}.json'
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(error_json_output)
            print(f"Error details saved to {output_filename}")
        except IOError as e:
            print(f"\nError saving error details to file {output_filename}: {e}")