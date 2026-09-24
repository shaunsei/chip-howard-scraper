from flask import Flask, jsonify, render_template_string
import subprocess
import sys
import os

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chip Howard Picks</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 700px;
            margin: 0 auto;
            padding: 25px 15px;
            background: #f5f5f5;
            color: #222;
        }

        h1 {
            text-align: center;
            margin-bottom: 25px;
        }

        button {
            width: 100%;
            padding: 16px;
            font-size: 18px;
            font-weight: bold;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            margin-bottom: 12px;
        }

        #runButton {
            background: #007aff;
            color: white;
        }

        #copyButton {
            background: #34c759;
            color: white;
        }

        button:disabled {
            background: #999;
            cursor: not-allowed;
        }

        textarea {
            width: 100%;
            box-sizing: border-box;
            min-height: 500px;
            padding: 12px;
            font-family: monospace;
            font-size: 14px;
            border: 1px solid #ccc;
            border-radius: 8px;
            background: white;
            resize: vertical;
        }

        #status {
            text-align: center;
            margin: 12px 0;
            font-size: 15px;
            min-height: 20px;
        }
    </style>
</head>

<body>

    <h1>Chip Howard Picks</h1>

    <button id="runButton" onclick="runScraper()">
        Run Latest Picks
    </button>

    <div id="status"></div>

    <textarea
        id="output"
        placeholder="Your picks will appear here..."
        readonly
    ></textarea>

    <button id="copyButton" onclick="copyPicks()" disabled>
        Copy for Google Sheets
    </button>

    <script>

        async function runScraper() {
            const runButton = document.getElementById("runButton");
            const copyButton = document.getElementById("copyButton");
            const output = document.getElementById("output");
            const status = document.getElementById("status");

            runButton.disabled = true;
            copyButton.disabled = true;
            output.value = "";

            status.textContent = "Running scraper...";

            try {
                const response = await fetch("/run");

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.error || "Something went wrong.");
                }

                output.value = data.clipboard;

                copyButton.disabled = false;

                status.textContent = "Latest picks loaded!";
            }

            catch (error) {
                status.textContent = "Error: " + error.message;
            }

            finally {
                runButton.disabled = false;
            }
        }


        function escapeHtml(text) {
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }


        function buildGoogleSheetsHtml(tsv) {

            const rows = tsv
                .split("\\n")
                .map(row => row.split("\\t"));

            let html = `
                <table
                    border="1"
                    cellspacing="0"
                    cellpadding="0"
                    style="border-collapse: collapse;"
                >
            `;

            rows.forEach((row, rowIndex) => {

                html += "<tr>";

                /*
                 * ROW 0 = entrant names
                 *
                 * Each entrant occupies TWO columns in the sheet,
                 * so merge the name across both columns.
                 */
                if (rowIndex === 0) {

                    for (let i = 0; i < row.length; i += 2) {

                        const name = row[i] || "";

                        html += `
                            <td colspan="2">
                                ${escapeHtml(name)}
                            </td>
                        `;
                    }
                }

                /*
                 * ROW 1 = tiebreaker scores
                 *
                 * These MUST remain two separate cells.
                 */
                else if (rowIndex === 1) {

                    row.forEach(cell => {

                        html += `
                            <td>
                                ${escapeHtml(cell || "")}
                            </td>
                        `;
                    });
                }

                /*
                 * ALL REMAINING ROWS = picks
                 *
                 * Each pick should occupy the merged two-column
                 * area belonging to that entrant.
                 */
                else {

                    for (let i = 0; i < row.length; i += 2) {

                        const pick = row[i] || "";

                        html += `
                            <td colspan="2">
                                ${escapeHtml(pick)}
                            </td>
                        `;
                    }
                }

                html += "</tr>";
            });

            html += "</table>";

            return html;
        }


        async function copyPicks() {

            const output = document.getElementById("output");
            const status = document.getElementById("status");

            const tsv = output.value;

            const html = buildGoogleSheetsHtml(tsv);

            try {

                /*
                 * Put BOTH versions on the clipboard.
                 *
                 * Google Sheets can use the HTML version,
                 * which preserves the merged cells.
                 */
                const clipboardItem = new ClipboardItem({
                    "text/plain": new Blob(
                        [tsv],
                        { type: "text/plain" }
                    ),

                    "text/html": new Blob(
                        [html],
                        { type: "text/html" }
                    )
                });

                await navigator.clipboard.write([
                    clipboardItem
                ]);

                status.textContent =
                    "Copied! Paste into Google Sheets.";

            }

            catch (error) {

                /*
                 * Fallback for browsers that don't support
                 * HTML clipboard data.
                 */
                try {

                    await navigator.clipboard.writeText(tsv);

                    status.textContent =
                        "Copied! Paste into Google Sheets.";

                }

                catch (fallbackError) {

                    output.focus();
                    output.select();
                    document.execCommand("copy");

                    status.textContent =
                        "Copied! Paste into Google Sheets.";
                }
            }
        }

    </script>

</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/run")
def run_scraper():

    try:

        scraper_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "scraper.py"
        )

        result = subprocess.run(
            [sys.executable, scraper_path],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:

            return jsonify({
                "error": result.stderr or "Scraper failed."
            }), 500

        stdout = result.stdout

        start_marker = "=== CLIPBOARD_DATA_START ==="
        end_marker = "=== CLIPBOARD_DATA_END ==="

        start = stdout.find(start_marker)
        end = stdout.find(end_marker)

        if start == -1 or end == -1:

            return jsonify({
                "error": "Could not find scraper output."
            }), 500

        start += len(start_marker)

        clipboard_data = stdout[start:end].strip()

        return jsonify({
            "clipboard": clipboard_data
        })

    except subprocess.TimeoutExpired:

        return jsonify({
            "error": "The scraper took too long to finish."
        }), 500

    except Exception as e:

        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run()
