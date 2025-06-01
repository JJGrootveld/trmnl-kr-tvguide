# Product Requirements Document: TV Guide Plugin

**Version:** 1.3
**Date:** June 1, 2025 (Updated for Current & Upcoming Layout)
**Author/Owner:** [Your Name/Plugin Developer]

## 1. Introduction

This document outlines the requirements for a TV Guide Plugin designed to fetch and display daily television schedules from the KT TV guide website (`https://tv.kt.com/`). The plugin consists of two main components: an **automated Python script** for data acquisition and JSON conversion, and Liquid templates for displaying the fetched data within a **TRMNL plugin environment**. This includes a primary layout showing a list of programs and an alternative layout focusing only on the current and upcoming program.

## 2. Goals

*   To provide TRMNL users with an easy way to view TV program schedules for specific KT channels.
*   To allow users to specify the channel for the desired schedule (date defaults to current KST day).
*   To present the schedule information in clear, concise, and user-friendly formats within the TRMNL plugin UI, including a detailed list and a focused current/next view.
*   To create a robust and **automated data fetching mechanism** that handles the specifics of the target website's API and ensures fresh data for the TRMNL plugin.
*   To ensure the plugin remains functional and stable within the TRMNL environment by adapting to observed platform behaviors.

## 3. Target Users

*   Users of the **TRMNL plugin environment** who wish to quickly check TV schedules.
*   The developer for integrating and maintaining this functionality.

## 4. User Stories

*   As a user, I want to configure a channel ID for the plugin to see its TV schedule.
*   As a user, I want the plugin to automatically show the TV schedule for the **current KST day**.
*   As a user, I want to see the program's start time, title, and genre.
*   As a user, I want to quickly identify if a program is currently "ON AIR".
*   As a user, I want to see the channel's name for easy identification.
*   As a user, when viewing the full schedule list, I want the currently "ON AIR" program (or the next upcoming program if none are on air) to be centrally displayed among a fixed number of listed programs, making it easy to focus on current/imminent broadcasts.
*   As a user, I want an alternative view that shows only the currently 'ON AIR' program and the immediately upcoming program, for a quick glance.
*   As a user, I want the "ON AIR" status to be dynamically calculated based on the current time (KST) when viewing today's schedule in either layout.
*   As a user, if broadcasting for the current KST day has ended or no programs are listed for today, I want to see a clear message indicating this, along with the channel logo/name.

## 5. Functional Requirements

### 5.1. Data Acquisition and Processing (Automated Python Script)

*   **FR1.1: Fetch HTML Data:** The script must fetch schedule data from `https://tv.kt.com/tv/channel/pSchedule.asp`.
*   **FR1.2: HTTP POST Request:** The request must be an HTTP POST.
*   **FR1.3: Request Payload:**
    *   The payload must include:
        *   `ch_type` (e.g., "4")
        *   `service_ch_no` (**configurable, typically via environment variable, e.g., `TV_CHANNEL_ID`**)
        *   `view_type` (e.g., "1" for daily schedule)
    *   The `seldate` parameter **should be omitted from the payload** to fetch the schedule for the KT server's current day.
*   **FR1.4: Request Headers:** The script must send appropriate headers, including `User-Agent`, `Content-Type: application/x-www-form-urlencoded; charset=UTF-8`, `Referer`, `X-Requested-With`, and `Origin`.
*   **FR1.5: HTML Parsing:** The script must parse the fetched HTML response (encoded in `euc-kr`) using BeautifulSoup.
*   **FR1.6: Data Extraction:** The script must extract the following information:
    *   Displayed Date
    *   Channel Name
    *   Channel Logo URL
    *   For each program:
        *   Time (HH:MM)
        *   Title
        *   Genre
        *   Icons (list of strings, including `alt` text or `src` fallback)
        *   On-air status (boolean: `true`/`false` - this is the server-provided status)
*   **FR1.7: JSON Output Structure:**
    *   The script must convert the extracted data into a structured JSON format.
    *   The top-level JSON object should include keys such as `channel_id_requested`, `date_requested` (contextual string), `date_displayed`, `channel_name`, `channel_logo_url`, a `programs` array, `script_run_epoch_utc`, `script_run_iso_utc`, and `schedule_context_message`.
    *   **Note on current JSON structure for TRMNL:** The Python script currently outputs a single JSON object. TRMNL appears to wrap this into an array, making the schedule data accessible via `data[0]` in Liquid.
*   **FR1.8: Automated Execution:** The script is designed for automated execution (e.g., via GitHub Actions) and does not require direct user input at runtime. Channel ID and output filename are configurable via environment variables or script defaults.
*   **FR1.9: File Output:** The script should save the generated JSON to a local file with a **consistent filename** (e.g., `tv_schedule.json` or configurable via `OUTPUT_FILENAME` env var) to be committed to a repository. Error information should also be saved to a uniquely named file or be part of the main JSON structure if fetching/parsing fails.
*   **FR1.10: Error Handling:** The script should handle potential errors during HTTP requests and parsing, providing informative messages in logs and in the output JSON (e.g., via an `error_summary` field).
*   **FR1.11: Timestamp for Cache Busting:** The output JSON must include a timestamp (e.g., `script_run_epoch_utc`) that changes with each script execution to ensure TRMNL's diffing mechanism recognizes the data as new and triggers a re-render.

### 5.2. Data Display (Liquid Templates for TRMNL)

*   **FR2.1: Common Display Elements:** Both layouts must display:
    *   Channel Name (`channel_name`)
    *   Schedule Date (`date_displayed`)
*   **FR2.2: Program Listing Layout (Default View):**
    *   **FR2.2.1: Fixed Number of Programs:** Displays a fixed number of programs (e.g., 5) at a time.
    *   **FR2.2.2: Centered Target Program:** Attempts to center the "target" program in the 3rd position of the 5 displayed slots. The "target" program is determined by:
        1.  A program with `is_on_air == true` (from JSON).
        2.  If none, and schedule is for current KST day: the next program after current KST time.
        3.  Else, the first program in the schedule.
    *   **FR2.2.3: Slice Adjustment:** Logic adjusts to prevent out-of-bounds errors.
    *   **FR2.2.4: Program Details:** For each listed program: Time, Title, Genre.
*   **FR2.3: Dynamic On-Air Indicator (Common to relevant programs in both layouts):**
    *   **FR2.3.1: Dynamic Calculation:** For schedules of the current KST day, "ON AIR" status is dynamically calculated by comparing current KST time against program start/end times (end time derived from next program's start or assumed duration).
    *   **FR2.3.2: Visual Indicator:** A visual "ON AIR" label is displayed.
    *   **FR2.3.3: Non-Current Day Schedules:** Dynamic calculation does not apply.
*   **FR2.4: Current & Upcoming Layout Option (Focused View):**
    *   **FR2.4.1: Purpose:** Provides a concise view of only the currently broadcasting program and the one immediately following it.
    *   **FR2.4.2: Current Program Identification:**
        1.  Primary: Selects a program from the full schedule where `is_on_air == true` (server-provided flag).
        2.  Secondary (if no server flag and schedule is for current KST day): Dynamically determines the program currently on air by comparing current KST time with program start/end times.
    *   **FR2.4.3: Upcoming Program Identification:**
        1.  If a "current" program is identified and is not the last in the schedule: Selects the program immediately following it.
        2.  If no "current" program was found (or "current" is the last) and schedule is for current KST day: Selects the first program scheduled to start after the current KST time.
    *   **FR2.4.4: Display Elements:**
        *   Channel Name and Schedule Date (subtitle indicates "Current & Upcoming").
        *   "Currently On Air" section: Displays time, title, genre of the identified current program. Includes the dynamic "ON AIR" badge (per FR2.3) if applicable.
        *   "Upcoming Next" (if a current program is shown) or "Next Program" (if no current program shown but an upcoming one is found) section: Displays time, title, genre.
    *   **FR2.4.5: Fallback Messages:** Displays appropriate messages if no current or upcoming program can be determined (e.g., "Broadcasting may have ended..." or "No program information...").
    *   **FR2.4.6: Technical Implementation:** Realized as a separate Liquid markup file (e.g., `markup_current_upcoming.html`).
*   **FR2.5: No Programs Message / Broadcasting Ended Message (Common to both layouts, adapted as needed):**
    *   **FR2.5.1:** If the schedule is for the current KST day and all programs are in the past or no programs are listed, a message like "Broadcasting has ended for today." is displayed.
    *   **FR2.5.2:** If no programs are available for display for other reasons, a message "No program information available for this channel/date." is shown.
*   **FR2.6: Plugin Title Bar (Common to both layouts):** A title bar at the bottom displays the plugin's instance name and a generic TV icon.
*   **FR2.7: Data Source (Common to both layouts):** Templates consume JSON data, expected as `data[0]` in the Liquid context.
*   **FR2.8: Initial Data Availability (Common to both layouts):** Logic relies on `data[0]` and `data[0].programs` being non-nil.

## 6. Technical Requirements

*   **TR1: Python Script:**
    *   Language: Python 3.x
    *   Libraries: `requests`, `BeautifulSoup4`, `json`, `re`, `datetime`.
    *   Automation Environment: GitHub Actions (or similar scheduled task runner).
*   **TR2: Plugin Display:**
    *   Templating Engine: Liquid (as provided by TRMNL).
    *   Assumes TRMNL plugin environment can render Liquid templates and inject the JSON data as `data[0]`.
    *   Liquid logic uses `{{ "now" | date: "%s" }}` for current time due to observed instability with `trmnl.system.timestamp_utc` affecting data availability.
*   **TR3: Data Format:** JSON. Example structure (single object, which TRMNL wraps in `data` array for Liquid):
    ```json
    {
      "channel_id_requested": "7",
      "date_requested": "Current Day (KST approx: 20250601)",
      "date_displayed": "2025-06-01",
      "channel_name": "KBS2",
      "channel_logo_url": "https://tv.kt.com/...",
      "programs": [
        {
          "time": "HH:MM", 
          "title": "Program Title",
          "genre": "Program Genre",
          "is_on_air": true, 
          "icons": ["..."]
        }
      ],
      "script_run_epoch_utc": 1748721530,
      "script_run_iso_utc": "2025-05-31T19:58:50.571040+00:00",
      "schedule_context_message": "Displaying schedule for 2025-06-01."
    }
    ```

## 7. UI/UX Considerations (Liquid Templates)

*   The display should be clean and easy to read across both layouts.
*   The "ON AIR" status should be prominent when applicable.
*   The focused display of 5 programs (main layout) with the current/next program centered aims to improve scannability for browsing.
*   A 'Current & Upcoming' layout option (secondary layout) offers a highly focused view for users wanting quick information on what's on now and next.
*   Channel name will be prominently displayed at the top.
*   If broadcasting has ended for the day, a clear, user-friendly message is shown.
*   Styling will leverage classes potentially provided by the TRMNL plugin environment, supplemented by minimal inline styles for unique elements.

## 8. Release Criteria (MVP - Minimum Viable Product)

*   Automated Python script successfully fetches and parses data for the configured channel for the current day and saves it as valid JSON with a cache-busting timestamp.
*   **Main Layout (Program Listing):**
    *   Successfully displays the channel information and schedule if data is available and broadcasting has not ended.
    *   Displays a list of 5 programs (or fewer), correctly centered around the current/next program.
    *   Dynamically calculates and displays an "ON AIR" label for programs on the current day's schedule.
*   **Current & Upcoming Layout:**
    *   Successfully displays the channel information, identified current program (if any), and identified upcoming program (if any).
    *   Dynamically calculates and displays an "ON AIR" label for the current program if it's for today's schedule.
*   Both layouts display appropriate "Broadcasting has ended..." or "No program information..." messages.
*   Basic error handling is in place for data fetching and reflected in JSON.
*   Plugin functions reliably using `{{ "now" | date: "%s" }}` for time calculations.

## 9. Future Considerations / Out of Scope for MVP

*   **Re-evaluate "Today/Tomorrow" Python script logic:** The Python script logic to intelligently switch between today's and tomorrow's schedule was prototyped. It exposed an apparent instability in how the TRMNL platform handles significantly changing polled data for Liquid rendering (e.g., `data[0]` potentially becoming `nil` or conditional logic behaving unexpectedly). This feature is deferred until the TRMNL platform behavior is better understood or resolved.
*   Mapping icon `src` paths to meaningful descriptions.
*   More sophisticated UI for selecting channels (if plugin environment allows more than static config).
*   Displaying program icons visually.
*   More detailed error display within the plugin UI itself.
*   Using a unique ID for programs from the Python script to improve reliability of lookups in Liquid.
*   Investigate and potentially revert to `trmnl.system.timestamp_utc` if TRMNL platform issues are resolved.

## 10. Dependencies

*   The plugin's functionality relies on the Python script to provide the necessary JSON data.
*   The Python script relies on external libraries (`requests`, `BeautifulSoup4`).
*   A scheduled execution environment for the Python script (e.g., GitHub Actions).
*   The stability and structure of the `tv.kt.com` website and its `pSchedule.asp` endpoint.
*   The TRMNL Liquid templating environment, its `date` filter capabilities, and its specific behaviors regarding data injection and operator evaluation.
