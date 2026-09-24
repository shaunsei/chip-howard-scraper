import requests
from bs4 import BeautifulSoup
import re
import subprocess
import warnings
import shutil

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
# ============================================================

def find_latest_entry(soup, person):

    for table in soup.find_all("table"):

        rows = table.find_all("tr")

        weekly_columns = []

        for row in rows:

            cells = row.find_all(["th", "td"])

            for index, cell in enumerate(cells):

                text = cell.get_text(
                    " ",
                    strip=True
                )

                match = re.fullmatch(
                    r"W(\d+)",
                    text
                )

                if match:

                    weekly_columns.append(
                        (
                            int(match.group(1)),
                            index
                        )
                    )

            if weekly_columns:
                break

        if not weekly_columns:
            continue

        weekly_columns.sort(
            reverse=True
        )

        for row in rows:

            cells = row.find_all(
                ["td", "th"]
            )

            if not cells:
                continue

            row_name = cells[0].get_text(
                " ",
                strip=True
            )

            if row_name != person:
                continue

            for week_number, column_index in weekly_columns:

                if column_index >= len(cells):
                    continue

                weekly_cell = cells[column_index]

                cell_html = str(weekly_cell)

                match = re.search(
                    r"ContestEntryView\.aspx\?id=(\d+)",
                    cell_html,
                    re.IGNORECASE
                )

                if match:

                    return {
                        "week": week_number,
                        "entry_id": match.group(1)
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

    entry_html = str(entry_label)

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

        game_number = int(game_number)

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

                    selected_text = team1_soup.get_text(
                        " ",
                        strip=True
                    )

                else:

                    selected_text = team2_soup.get_text(
                        " ",
                        strip=True
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

print("Getting live standings page...")

standings_html = get_page(
    STANDINGS_URL
)

print("Live standings loaded.")
print()


standings_soup = BeautifulSoup(
    standings_html,
    "html.parser"
)


# ============================================================
# GET EACH PERSON
# ============================================================

results = []

for person in PEOPLE:

    print(
        f"Looking up: {person}"
    )

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

        if not entry_info:

            print(
                "No available entry found - "
                "using blank placeholder."
            )

        else:

            week = entry_info["week"]
            entry_id = entry_info["entry_id"]

            print(
                f"Latest week: W{week}"
            )

            print(
                f"Entry ID: {entry_id}"
            )

            print(
                "Downloading picks..."
            )

            entry_url = (
                "http://www.chiphoward.com/"
                f"ContestEntryView.aspx?id={entry_id}"
            )

            entry_html = get_page(
                entry_url
            )

            parsed = parse_entry(
                entry_html
            )

            tiebreaker_1 = parsed["tiebreaker_1"]
            tiebreaker_2 = parsed["tiebreaker_2"]
            picks = parsed["picks"]

            for warning in parsed["warnings"]:

                print(
                    f"  Warning: {warning}"
                )

            print(
                f"Successfully read: {DISPLAY_NAMES[person]}"
            )

    except Exception as error:

        print(
            f"Error reading {person}: {error} - "
            "using blank placeholder."
        )

        week = ""
        entry_id = ""
        tiebreaker_1 = ""
        tiebreaker_2 = ""
        picks = {}

    results.append({
        "username": person,
        "display_name": DISPLAY_NAMES[person],
        "week": week,
        "entry_id": entry_id,
        "tiebreaker_1": tiebreaker_1,
        "tiebreaker_2": tiebreaker_2,
        "picks": picks
    })

    print()


# ============================================================
# SORT EVERYTHING BY DISPLAY NAME
# ============================================================

results = sorted(
    results,
    key=lambda result: result["display_name"].lower()
)


# ============================================================
# SHOW THE FINAL ORDER
# ============================================================

print()
print("FINAL ALPHABETICAL ORDER:")
print()

for number, result in enumerate(results, start=1):

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

        if highest_in_entry > highest_game_number:

            highest_game_number = highest_in_entry

if highest_game_number == 0:

    highest_game_number = 10

print(
    f"Building {highest_game_number} game row(s)."
)

print()


for game_number in range(1, highest_game_number + 1):

    row = []

    for result in results:

        pick = result["picks"].get(
            game_number,
            ""
        )

        row.append(pick)

        row.append("")

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
        input=clipboard_text.encode("utf-8"),
        check=True
    )

    print()
    print(
        "Copied to clipboard. Click the FIRST tiebreaker cell "
        "(top-left), then paste (Command + V)."
    )
    print()


# ============================================================
# ONLINE VERSION DATA
#
# The web app will read the data between these two markers.
# This does NOT interfere with the Mac version.
# ============================================================

print("=== CLIPBOARD_DATA_START ===")
print(clipboard_text)
print("=== CLIPBOARD_DATA_END ===")


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
        "Heads up - these people had no picks found and "
        "were left blank so the columns still line up:"
    )

    for name in missing:

        print(
            f"  - {name}"
        )

    print()