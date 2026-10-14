# SmartMed AI — Complete Offline Flask Project

## Start here (Windows + VS Code)

1. Download and extract this ZIP.
2. In VS Code, choose **File > Open Folder** and select the extracted `SmartMed_AI_Final` folder.
3. Choose **Terminal > New Terminal**.
4. Run these commands one at a time (do not type the `PS ...>` prompt itself):

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python app.py
   ```

5. Keep the terminal open. When Flask says it is running, open this address in your browser:
   http://127.0.0.1:5000

If PowerShell blocks activation, you can skip activation and run:
`py -m pip install -r requirements.txt`
then:
`py app.py`

## What is included

- Home page with SmartMed AI logo and navigation
- Register/login and user dashboard
- Health questions and health-entry history
- Text and PDF/CSV/TXT report upload/extraction (supported formats depend on installed libraries)
- Food and nutrition guidance
- Fitness plans and fitness activity entries
- Healthcare discovery using a map/search link
- Progress tracker, trends and HealthPoints/rewards
- SQLite database created locally

## Offline intelligence: what it does and does not do

This project runs locally and does not require a paid AI API. It uses Python text processing, keyword/topic matching and rule-based responses (an introductory NLP-style approach). It is **not** a trained machine-learning model, neural network, or ChatGPT-like generative model. It can miss unusual phrasing, spelling errors, context, and complex questions. Do not rely on it for diagnosis or emergencies.

Report extraction reads supported text where possible; it cannot reliably interpret every scanned/image-only medical report. Uploaded files should be treated as private and sensitive. Healthcare discovery opens a search/map link and does not verify provider credentials, availability, or quality.

## Points

HealthPoints are demonstration engagement points for recording activities and using sections of the app. They are not money, medical outcomes, or a clinical reward recommendation.

## Troubleshooting

- `can't open file ... app.py`: use `Get-ChildItem` in the VS Code terminal. If you only see a folder named `SmartMed_AI_Final`, run `cd .\\SmartMed_AI_Final` or open that inner folder in VS Code.
- `requirements.txt` not found: the terminal is in the wrong folder. Open the folder that contains both `app.py` and `requirements.txt`.
- `127.0.0.1 refused to connect`: start the server with `python app.py` and keep the terminal open.
- To stop the server, click the terminal and press `Ctrl+C`.

## Before public deployment

This is a learning prototype, not a production medical service. Before public use, add CSRF protection, secure cookie settings, robust authorization/privacy controls, upload malware scanning, retention/deletion controls, logging protections, tests, and professional security review. Set a strong `SMARTMED_SECRET_KEY`, disable debug mode, and use HTTPS. Do not upload real patient information to a public demo.


## Visual images
The dashboard now includes a healthcare hero banner and photos on the quick-action cards. Health, report review, food, fitness/walking, healthcare discovery, tracker, trends, and rewards pages each have a relevant visual banner. Images are stored locally in `static/images/`, so the visuals do not require an internet connection. The original SmartMed AI logo is preserved in `static/smartmed-logo.png`.
