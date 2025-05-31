# TV Guide Plugin - KT Schedules

This project fetches daily TV schedules from the KT TV guide website (`tv.kt.com`) and provides the data in JSON format, along with a Liquid template for displaying it as a plugin.

## Features

*   **Data Acquisition**: A Python script (`get_kt_schedule.py` or similar) handles:
    *   Fetching schedule data via HTTP POST requests to the KT TV guide endpoint.
    *   Parsing the HTML response.
    *   Extracting program details: time, title, genre, on-air status (server-provided), and icons.
    *   Converting data to a structured JSON output.
    *   User prompts for Channel ID and optional Date (YYYYMMDD format).
*   **Data Display**: A Liquid template (`tv_guide_template.liquid` or similar) for rendering the schedule:
    *   Displays channel name and schedule date.
    *   Lists a fixed number of programs (e.g., 5).
    *   Centers the "on-air" or next upcoming program within the displayed list.
    *   Dynamically calculates and shows an "ON AIR" status based on current KST time for today's schedule.
    *   Includes a simple title bar.

## Project Components

1.  **Python Scraper (`get_kt_schedule.py` - *rename if different*)**:
    *   Responsible for fetching and processing the TV schedule data.
    *   Outputs a JSON file (e.g., `kt_tv_schedule_[channel_id]_[date].json`).
2.  **Liquid Template (`tv_guide_template.liquid` - *rename if different*)**:
    *   Renders the JSON data into an HTML view for the plugin.
    *   Contains logic for program selection, centering, and dynamic "ON AIR" status.
3.  **Product Requirements Document (`TV_Guide_Plugin_PRD_v1.1.md`)**:
    *   Detailed description of the project's features and requirements.

## Setup and Usage

### 1. Python Scraper

**Prerequisites:**
*   Python 3.x
*   Required Python libraries: `requests`, `beautifulsoup4`

**Installation:**
```bash
pip install requests beautifulsoup4
```

**Running the script:**
`python get_kt_schedule.py`

**The script will prompt you for:**
Channel ID (e.g., 7 for KBS2)
Date (YYYYMMDD format, e.g., 20250601. Press Enter for today's schedule).

It will then generate a JSON file containing the schedule data for the specified channel and date.

### 2. Liquid Template
The generated JSON data needs to be made available to your plugin environment where the Liquid template is rendered.
The template expects variables like {{ channel_name }}, {{ date_displayed }}, {{ programs }}, etc., as defined by the JSON output from the Python script.

Ensure your Liquid environment correctly handles date filters (date: "%s", date: "%Y%m%d", etc.) and timezone offsets if you are not using a pre-configured trmnl environment.

## How it Works
The Python script sends a POST request to https://tv.kt.com/tv/channel/pSchedule.asp with a payload containing ch_type, service_ch_no, view_type, and optionally seldate.
The HTML response is parsed using BeautifulSoup.
Extracted data (channel info, program list) is structured into JSON.

The Liquid template takes this JSON and:
Identifies the current or next upcoming program.
Slices the program list to display 5 items, centered on the target program.
For today's schedule, it dynamically calculates if a displayed program is currently on air by comparing the current KST time with program start/end times.
