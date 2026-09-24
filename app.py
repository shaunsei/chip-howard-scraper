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


        async function copyPicks() {
            const output = document.getElementById("output");
            const status = document.getElementById("status");

            try {
                await navigator.clipboard.writeText(output.value);

                status.textContent =
                    "Copied! You can now paste into Google Sheets.";

            }

            catch (error) {
                output.focus();
                output.select();
                document.execCommand("copy");

                status.textContent =
                    "Copied! You can now paste into Google Sheets.";
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