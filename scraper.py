import requests
from bs4 import BeautifulSoup
import re
import subprocess
import warnings
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

# Hide the harmless urllib3 LibreSSL warning
warnings.filterwarnings("ignore", message=".*LibreSSL.*")


# ============================================================
# PEOPLE
# These are the usernames exactly as they appear on the site.
# ============================================================

PEOPLE = [
    "Reece Rose",
    "Shaun Seidenberger",
    "Blearn",
    "Bovsta",
    "bradenwink",
    "CharlieClark",
    "caskweres",
    "Keybort",
    "Ric",
    "Fro",
    "GigEm3",
    "gskweres2",
    "Astro",
    "Wilson361",
    "Michael W",
    "Niclanas",
    "rrose1988",
    "Cumster69",
    "KSculley",
    "TJ",
]


# ============================================================
# DISPLAY NAME MAPPING
#
# LEFT SIDE = username used by the website
# RIGHT SIDE = name shown in Google Sheets
# ============================================================

DISPLAY_NAMES = {
    "Blearn": "Ben",
    "Bovsta": "Bova",
    "bradenwink": "Braden",
    "CharlieClark": "Charlie",
    "caskweres": "Chase",
    "Keybort": "Chris",
    "Ric": "Erik",
    "Fro": "Fro",
    "GigEm3": "Geoff",
    "gskweres2": "Grayson",
    "Astro": "Jason",
    "Wilson361": "Matthew",
    "Michael W": "Michael",
    "Niclanas": "Nic",
    "Reece Rose": "Reece",
    "rrose1988": "Ronnie",
    "Cumster69": "Ryan",
    "KSculley": "Sculley",
    "Shaun Seidenberger": "Shaun",
    "TJ": "TJ",
}


STANDINGS_URL = "http://www.chiphoward.com/ContestStandings.aspx"


# ============================================================
# GET A WEB PAGE
# ============================================================

def get_page(url):

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    return response.text


# ============================================================
# FIND MOST RECENT WEEK / ENTRY
#
# IMPORTANT:
#
# We ONLY use the newest week shown on the standings page.
#
# If the person has an entry link for that newest week,
# we use it.
#
# If the newest week has no entry link (for example "-"),
# we consider that person MISSING for the current week.
#
# We DO NOT fall back to an older week's picks.
# ============================================================

def find_latest_entry(soup, person):

    for table in soup.find_all("table"):

        rows = table.find_all("tr")

        if not rows:
            continue

        # Build a visual table grid so colspan/rowspan cells do not
        # shift the week-column positions.
        grid = {}
        row_cells = {}

        for row_index, row in enumerate(rows):

            cells = row.find_all(
                ["th", "td"],
                recursive=False
            )

            if not cells:
                cells = row.find_all(
                    ["th", "td"]
                )

            current_column = 0

            for cell in cells:

                while (
                    row_index,
                    current_column
                ) in grid:
                    current_column += 1

                try:
                    colspan = int(
                        cell.get("colspan", "1")
                    )
                except (TypeError, ValueError):
                    colspan = 1

                try:
                    rowspan = int(
                        cell.get("rowspan", "1")
                    )
                except (TypeError, ValueError):
                    rowspan = 1

                colspan = max(1, colspan)
                rowspan = max(1, rowspan)

                for r in range(
                    row_index,
                    row_index + rowspan
                ):
                    for c in range(
                        current_column,
                        current_column + colspan
                    ):
                        grid[(r, c)] = cell

                row_cells.setdefault(
                    row_index, []
                ).append(
                    (current_column, cell)
                )

                current_column += colspan

        # Find W1, W2, W3, etc. headers and their actual visual
        # positions.
        weekly_headers = {}

        for (row_index, column_index), cell in grid.items():

            text = cell.get_text(
                " ",
                strip=True
            )

            match = re.fullmatch(
                r"W(\d+)",
                text
            )

            if match:
                weekly_headers[int(match.group(1))] = (
                    row_index,
                    column_index,
                    cell
                )

        if not weekly_headers:
            continue

        latest_week = max(weekly_headers.keys())

        header_row, _, header_cell = weekly_headers[latest_week]

        header_columns = [
            column_index
            for (row_index, column_index), cell in grid.items()
            if row_index == header_row and cell is header_cell
        ]

        # Find the person's row without assuming their name is
        # necessarily the first physical cell.
        person_row_index = None

        for row_index, cells in row_cells.items():

            for _, cell in cells:

                cell_text = cell.get_text(
                    " ",
                    strip=True
                )

                if cell_text == person:
                    person_row_index = row_index
                    break

            if person_row_index is not None:
                break

        if person_row_index is None:
            continue

        # Look only underneath the newest-week header.
        possible_cells = []

        for (row_index, column_index), cell in grid.items():

            if row_index != person_row_index:
                continue

            if column_index in header_columns and cell not in possible_cells:
                possible_cells.append(cell)

        for latest_cell in possible_cells:

            cell_html = str(latest_cell)

            match = re.search(
                r"ContestEntryView\.aspx\?id=(\d+)",
                cell_html,
                re.IGNORECASE
            )

            if match:
                return {
                    "week": latest_week,
                    "entry_id": match.group(1)
                }

        # No entry in the newest week means blank. Never fall back
        # to an older week.
        return {
            "week": latest_week,
            "entry_id": ""
        }

    return None


# ============================================================
# CLEAN UP PICK
# ============================================================

def clean_pick(pick):

    pick = re.sub(
        r"\([^)]*\)",
        "",
        pick
    )

    pick = " ".join(
        pick.split()
    )

    pick = pick.lower().title()

    exceptions = {
        "Smu": "SMU",
        "Lsu": "LSU",
        "Ucla": "UCLA",
        "Tcu": "TCU",
        "Usc": "USC",
        "Ucf": "UCF",
        "Utsa": "UTSA",
        "Fsu": "FSU",
        "Byu": "BYU",
        "Nyu": "NYU",
        "Nc State": "NC State",
        "Lc Thomas": "LC Thomas",
        "Uab": "UAB",
        "Ecu": "ECU",
        "Etsu": "ETSU",
        "Fau": "FAU",
        "Fiu": "FIU",
        "Ulm": "ULM",
        "Mtsu": "MTSU",
        "Wku": "WKU",
        "Utep": "UTEP",
        "Sdsu": "SDSU",
        "Sjsu": "SJSU",
        "Unt": "UNT",
        "Usf": "USF",
        "Usa": "USA",
        "Unlv": "UNLV",
        "Gt": "GT",
        "Jmu": "JMU",
        "Odu": "ODU",
        "Cmu": "CMU",
        "Emu": "EMU",
        "Wmu": "WMU",
        "Niu": "NIU",
        "Uconn": "UConn",
    }

    if pick in exceptions:
        pick = exceptions[pick]

    return pick


# ============================================================
# EXTRACT A SCORE LIKE "(21)" FROM A CHUNK OF HTML/TEXT
# ============================================================

def extract_score(team_soup):

    text = team_soup.get_text(
        " ",
        strip=True
    )

    match = re.search(
        r"\((\d+)\)",
        text
    )

    if match:
        return match.group(1)

    return ""


# ============================================================
# PARSE ENTRY PAGE
# ============================================================

def parse_entry(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    entry_label = soup.find(
        "span",
        id="lblEntry"
    )

    if not entry_label:
        raise Exception(
            "Could not find entry information."
        )

    entry_html = str(
        entry_label
    )

    game_matches = re.findall(
        r"Game\s+(\d+):\s*(.*?)(?:<br\s*/?>|$)",
        entry_html,
        re.IGNORECASE | re.DOTALL
    )

    picks = {}

    tiebreaker_1 = ""
    tiebreaker_2 = ""

    warnings = []

    for game_number, game_html in game_matches:

        game_number = int(
            game_number
        )

        game_soup = BeautifulSoup(
            game_html,
            "html.parser"
        )

        strong_tags = game_soup.find_all(
            "strong"
        )

        # ====================================================
        # GAME 1
        # ====================================================

        if game_number == 1:

            parts = re.split(
                r"vs\.",
                game_html,
                flags=re.IGNORECASE
            )

            if len(parts) != 2:

                parts = re.split(
                    r"@",
                    game_html,
                    flags=re.IGNORECASE
                )

            if len(parts) == 2:

                team1_soup = BeautifulSoup(
                    parts[0],
                    "html.parser"
                )

                team2_soup = BeautifulSoup(
                    parts[1],
                    "html.parser"
                )

                tiebreaker_1 = extract_score(
                    team1_soup
                )

                tiebreaker_2 = extract_score(
                    team2_soup
                )

                if team1_soup.find("strong"):

                    selected_text = (
                        team1_soup.get_text(
                            " ",
                            strip=True
                        )
                    )

                else:

                    selected_text = (
                        team2_soup.get_text(
                            " ",
                            strip=True
                        )
                    )

                selected_team = re.sub(
                    r"\s*\(\d+\)",
                    "",
                    selected_text
                )

                picks[game_number] = clean_pick(
                    selected_team
                )

            else:

                warnings.append(
                    "Game 1 didn't match 'vs.' or '@' format - "
                    "tiebreaker and Game 1 pick left blank."
                )

        # ====================================================
        # ALL OTHER GAMES
        # ====================================================

        else:

            selected_team = None

            for strong in strong_tags:

                text = strong.get_text(
                    " ",
                    strip=True
                )

                if text.upper() not in [
                    "W",
                    "L"
                ]:

                    selected_team = text

                    break

            if selected_team:

                picks[game_number] = clean_pick(
                    selected_team
                )

    return {
        "picks": picks,
        "tiebreaker_1": tiebreaker_1,
        "tiebreaker_2": tiebreaker_2,
        "warnings": warnings
    }


# ============================================================
# MAIN
# ============================================================

print()
print("Chip Howard Pick Scraper")
print()


# ============================================================
# GET LIVE STANDINGS
# ============================================================

print(
    "Getting live standings page..."
)

standings_html = get_page(
    STANDINGS_URL
)

print(
    "Live standings loaded."
)

print()


standings_soup = BeautifulSoup(
    standings_html,
    "html.parser"
)


# ============================================================
# GET EACH PERSON
# ============================================================

results = []


def prepare_person(person):
    """Find the newest entry and download/parse that entry if present."""

    week = ""
    entry_id = ""
    tiebreaker_1 = ""
    tiebreaker_2 = ""
    picks = {}

    try:

        entry_info = find_latest_entry(
            standings_soup,
            person
        )

        if (
            not entry_info
            or not entry_info["entry_id"]
        ):

            if entry_info:

                week = entry_info["week"]

                message = (
                    f"Latest week: W{week} - "
                    "no picks submitted; blank placeholder."
                )

            else:
                message = (
                    "No available entry found - "
                    "using blank placeholder."
                )

            return {
                "username": person,
                "display_name": DISPLAY_NAMES[person],
                "week": week,
                "entry_id": entry_id,
                "tiebreaker_1": tiebreaker_1,
                "tiebreaker_2": tiebreaker_2,
                "picks": picks,
                "message": message,
                "warnings": []
            }

        week = entry_info["week"]
        entry_id = entry_info["entry_id"]

        entry_url = (
            "http://www.chiphoward.com/"
            f"ContestEntryView.aspx?id={entry_id}"
        )

        entry_html = get_page(entry_url)
        parsed = parse_entry(entry_html)

        tiebreaker_1 = parsed["tiebreaker_1"]
        tiebreaker_2 = parsed["tiebreaker_2"]
        picks = parsed["picks"]

        return {
            "username": person,
            "display_name": DISPLAY_NAMES[person],
            "week": week,
            "entry_id": entry_id,
            "tiebreaker_1": tiebreaker_1,
            "tiebreaker_2": tiebreaker_2,
            "picks": picks,
            "message": (
                f"Latest week: W{week}, Entry ID: {entry_id}, "
                f"Successfully read: {DISPLAY_NAMES[person]}"
            ),
            "warnings": parsed["warnings"]
        }

    except Exception as error:

        return {
            "username": person,
            "display_name": DISPLAY_NAMES[person],
            "week": "",
            "entry_id": "",
            "tiebreaker_1": "",
            "tiebreaker_2": "",
            "picks": {},
            "message": (
                f"Error reading {person}: {error} - "
                "using blank placeholder."
            ),
            "warnings": []
        }


# Download entry pages concurrently. The standings page is still
# downloaded exactly once, and each person is still restricted to
# the newest week only. Five workers keeps the speed improvement
# reasonable without sending all requests at once.
MAX_WORKERS = 5

print(
    f"Downloading and parsing entries with up to "
    f"{MAX_WORKERS} simultaneous requests..."
)
print()

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

    future_to_person = {
        executor.submit(prepare_person, person): person
        for person in PEOPLE
    }

    completed = 0

    for future in as_completed(future_to_person):

        person = future_to_person[future]
        completed += 1

        result = future.result()

        print(
            f"[{completed}/{len(PEOPLE)}] "
            f"{person}: {result['message']}"
        )

        for warning in result["warnings"]:
            print(
                f"  Warning: {warning}"
            )

        results.append(result)

print()


# ============================================================
# SORT EVERYTHING BY DISPLAY NAME
# ============================================================

results = sorted(
    results,
    key=lambda result: result[
        "display_name"
    ].lower()
)


# ============================================================
# SHOW THE FINAL ORDER
# ============================================================

print()
print(
    "FINAL ALPHABETICAL ORDER:"
)

print()

for number, result in enumerate(
    results,
    start=1
):

    print(
        f"{number}. "
        f"{result['display_name']} "
        f"({result['username']})"
    )

print()


# ============================================================
# BUILD GOOGLE SHEETS TABLE
# ============================================================

output_rows = []


# ============================================================
# TIEBREAKER ROW
# ============================================================

tiebreaker_row = []

for result in results:

    tiebreaker_row.append(
        result["tiebreaker_1"]
    )

    tiebreaker_row.append(
        result["tiebreaker_2"]
    )

output_rows.append(
    tiebreaker_row
)


# ============================================================
# GAME ROWS
# ============================================================

highest_game_number = 0

for result in results:

    if result["picks"]:

        highest_in_entry = max(
            result["picks"].keys()
        )

        if (
            highest_in_entry
            > highest_game_number
        ):

            highest_game_number = (
                highest_in_entry
            )


if highest_game_number == 0:

    highest_game_number = 10


print(
    f"Building "
    f"{highest_game_number} game row(s)."
)

print()


for game_number in range(
    1,
    highest_game_number + 1
):

    row = []

    for result in results:

        pick = result["picks"].get(
            game_number,
            ""
        )

        row.append(
            pick
        )

        row.append(
            ""
        )

    output_rows.append(
        row
    )


# ============================================================
# BUILD GOOGLE SHEETS TEXT
# ============================================================

clipboard_text = "\n".join(
    "\t".join(row)
    for row in output_rows
)


# ============================================================
# MAC CLIPBOARD
#
# If running on your Mac, pbcopy exists and the picks will
# still be copied directly to your Mac clipboard.
#
# On the online server, pbcopy does not exist, so this section
# simply gets skipped.
# ============================================================

if shutil.which("pbcopy"):

    subprocess.run(
        ["pbcopy"],
        input=clipboard_text.encode(
            "utf-8"
        ),
        check=True
    )

    print()

    print(
        "Copied to clipboard. "
        "Click the FIRST tiebreaker cell "
        "(top-left), then paste "
        "(Command + V)."
    )

    print()


# ============================================================
# ONLINE VERSION DATA
#
# The web app will read the data between these two markers.
# This does NOT interfere with the Mac version.
# ============================================================

print(
    "=== CLIPBOARD_DATA_START ==="
)

print(
    clipboard_text
)

print(
    "=== CLIPBOARD_DATA_END ==="
)


# ============================================================
# DONE
# ============================================================

print()
print("DONE")
print()


for result in results:

    if result["entry_id"]:

        print(
            f"{result['display_name']}: "
            f"W{result['week']} "
            f"(Entry {result['entry_id']})"
        )

    else:

        print(
            f"{result['display_name']}: "
            f"MISSING - blank placeholder used"
        )


print()


missing = [
    result["display_name"]
    for result in results
    if not result["entry_id"]
]


if missing:

    print(
        "Heads up - these people had no picks found "
        "and were left blank so the columns still line up:"
    )

    for name in missing:

        print(
            f"  - {name}"
        )

    print()
