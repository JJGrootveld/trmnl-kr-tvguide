import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timezone, timedelta
import time
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom

DEFAULT_CHANNEL_ID = os.environ.get('TV_CHANNEL_ID', '7')
OUTPUT_XML_FILENAME = os.environ.get('OUTPUT_XML_FILENAME', 'tv_schedule.xml')
ERROR_XML_FILENAME = f"ERROR_{OUTPUT_XML_FILENAME}"

KST_OFFSET_HOURS = 9
KST_TIMEZONE = timezone(timedelta(hours=KST_OFFSET_HOURS))

def fetch_schedule_html_post(channel_id, date_str_yyyymmdd=None, channel_type="4", view_type_val="1"):
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

def parse_schedule_to_dict(html_content, channel_id_for_log="N/A", requested_date_str="N/A"):
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
    return schedule_data

def _convert_to_xml_recursive(parent_xml_element, data, key_as_tag_name):
    """
    Recursively converts Python dicts/lists/values to XML elements.
    - parent_xml_element: The ET.Element to append children to.
    - data: The Python data to convert (dict, list, str, int, etc.).
    - key_as_tag_name: The desired tag name for the current data element.
    """
    sane_tag = re.sub(r'[^a-zA-Z0-9_.-]', '_', str(key_as_tag_name))
    if not sane_tag or sane_tag[0].isdigit() or sane_tag.lower().startswith("xml"):
        sane_tag = f"item_{sane_tag}" if sane_tag else "item"
        if sane_tag and sane_tag[0].isdigit():
            sane_tag = "_" + sane_tag

    if isinstance(data, dict):
        current_element = ET.SubElement(parent_xml_element, sane_tag)
        for k, v in data.items():
            _convert_to_xml_recursive(current_element, v, k)
    elif isinstance(data, list):
        list_element = ET.SubElement(parent_xml_element, sane_tag)
        item_tag = "item"
        if sane_tag == "programs":
            item_tag = "program"
        elif sane_tag == "icons":
            item_tag = "icon"
        elif sane_tag == "data":
            item_tag = "entry"

        for item_in_list in data:
            if sane_tag == "data" and isinstance(item_in_list, dict):
                if "error_summary" in item_in_list:
                    _convert_to_xml_recursive(list_element, item_in_list, "error_entry")
                else:
                    _convert_to_xml_recursive(list_element, item_in_list, "schedule_entry")
            else:
                _convert_to_xml_recursive(list_element, item_in_list, item_tag)
    else:
        element = ET.SubElement(parent_xml_element, sane_tag)
        element.text = str(data) if data is not None else ""

def generate_schedule_xml_string(schedule_data_wrapper_dict):
    """
    Generates an XML string from the main schedule data structure.
    The input `schedule_data_wrapper_dict` is expected to be like:
    {"data": [schedule_object_or_error_dict]}
    """
    if not isinstance(schedule_data_wrapper_dict, dict) or "data" not in schedule_data_wrapper_dict:
        error_root = ET.Element("error_root")
        ET.SubElement(error_root, "message").text = "Invalid input: Expected dict with 'data' key for XML generation."
        rough_string = ET.tostring(error_root, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')

    root_key_name = list(schedule_data_wrapper_dict.keys())[0]
    root_xml_element = ET.Element(root_key_name)
    _convert_to_xml_recursive(root_xml_element, schedule_data_wrapper_dict[root_key_name], root_key_name)

    rough_string = ET.tostring(root_xml_element, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')

if __name__ == "__main__":
    target_channel_id = DEFAULT_CHANNEL_ID
    default_channel_type = "4"
    default_view_type = "1"

    date_to_fetch_param = None

    now_kst_for_log = datetime.now(timezone.utc).astimezone(KST_TIMEZONE)
    requested_date_context_str = f"Current Day (KST approx: {now_kst_for_log.strftime('%Y%m%d')})"

    print(f"--- Script run at {now_kst_for_log.strftime('%Y-%m-%d %H:%M:%S KST')} ---")
    print(f"\n--- Attempting to fetch schedule for {requested_date_context_str} ---")

    html = fetch_schedule_html_post(
        channel_id=target_channel_id,
        date_str_yyyymmdd=date_to_fetch_param,
        channel_type=default_channel_type,
        view_type_val=default_view_type
    )

    schedule_object_or_error = {}
    output_xml_filename_to_use = ERROR_XML_FILENAME

    if html:
        print("\nHTML fetched successfully. Parsing schedule...")
        parsed_data = parse_schedule_to_dict(html, target_channel_id, requested_date_context_str)

        if "error_summary" not in parsed_data:
            parsed_data['script_run_epoch_utc'] = int(time.time())
            parsed_data['script_run_iso_utc'] = datetime.now(timezone.utc).isoformat()
            parsed_data['schedule_context_message'] = f"Displaying schedule for {parsed_data.get('date_displayed', 'current day')}."

            schedule_object_or_error = parsed_data
            output_xml_filename_to_use = OUTPUT_XML_FILENAME
            print(f"\nSchedule data prepared for XML: {parsed_data.get('date_displayed')}")
        else:
            error_data = parsed_data
            error_data['script_run_epoch_utc'] = int(time.time())
            error_data['script_run_iso_utc'] = datetime.now(timezone.utc).isoformat()
            schedule_object_or_error = error_data
            print(f"\nError data prepared for XML (from parsing): {error_data.get('error_summary')}")

    else:
        print("\nFailed to fetch HTML. Error XML will be generated.")
        error_data = {
            "error_summary": "Failed to fetch HTML from server.",
            "channel_id_requested": target_channel_id,
            "date_requested": requested_date_context_str,
            "script_run_epoch_utc": int(time.time()),
            "script_run_iso_utc": datetime.now(timezone.utc).isoformat()
        }
        schedule_object_or_error = error_data

    final_output_structure_for_xml = {
        "data": [schedule_object_or_error]
    }

    print(f"\nGenerating XML data...")
    try:
        xml_string = generate_schedule_xml_string(final_output_structure_for_xml)
        with open(output_xml_filename_to_use, 'w', encoding='utf-8') as f:
            f.write(xml_string)
        print(f"XML Data saved to {output_xml_filename_to_use}")
    except Exception as e:
        print(f"\nError generating or saving XML data to file {output_xml_filename_to_use}: {e}")
        try:
            error_xml_root = ET.Element("fatal_xml_generation_error")
            ET.SubElement(error_xml_root, "message").text = f"Failed to generate full XML. Error: {str(e)}"
            ET.SubElement(error_xml_root, "original_error_summary").text = schedule_object_or_error.get("error_summary", "N/A")

            rough_string = ET.tostring(error_xml_root, 'utf-8')
            reparsed = minidom.parseString(rough_string)
            minimal_error_xml = reparsed.toprettyxml(indent="  ", encoding='utf-8').decode('utf-8')

            with open(ERROR_XML_FILENAME, 'w', encoding='utf-8') as f_err_xml:
                f_err_xml.write(minimal_error_xml)
            print(f"Minimal error XML saved to {ERROR_XML_FILENAME}")
        except Exception as e_xml_minimal:
            print(f"Could not even save minimal error XML: {e_xml_minimal}")
