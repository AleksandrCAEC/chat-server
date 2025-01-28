import os
from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# Initialize Flask app
app = Flask(__name__)

# Set environment variables
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account_json")

# Helper function to check if required environment variables are set
def check_env_variables():
    return {
        "openai_key_set": os.getenv("OPENAI_API_KEY") is not None,
        "telegram_token_set": os.getenv("TELEGRAM_BOT_TOKEN") is not None,
        "google_credentials_path_set": os.getenv("GOOGLE_APPLICATION_CREDENTIALS") is not None,
    }

@app.route("/check-env", methods=["GET"])
def check_env():
    env_status = check_env_variables()
    return jsonify(env_status)

@app.route("/register-client", methods=["POST"])
def register_client():
    data = request.get_json()

    # Validate input data
    if not data or not all(k in data for k in ("name", "email", "phone")):
        return jsonify({"error": "Invalid input"}), 400

    name = data["name"]
    email = data["email"]
    phone = data["phone"]

    # Simulate client registration logic
    return jsonify({"message": "Client registered successfully", "client": {"name": name, "email": email, "phone": phone}}), 200

@app.route("/create-sheet", methods=["POST"])
def create_sheet():
    try:
        data = request.json
        title = data.get('title', 'New Spreadsheet')
        notes = data.get('notes', '')

        # Establish connection to Google Sheets API
        credentials = Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        service = build('sheets', 'v4', credentials=credentials)

        # Define the body of the sheet including the parent folder
        sheet_body = {
            'properties': {
                'title': title
            },
            'parents': ['1g1OtN7ID1lM01d0bLswGqLF0m2gQIcqo']  # Add this parameter
        }

        # Create a new sheet
        spreadsheet = service.spreadsheets().create(body=sheet_body, fields='spreadsheetId').execute()
        spreadsheet_id = spreadsheet.get('spreadsheetId')

        # Optionally add notes to the sheet
        if notes:
            requests_body = {
                'requests': [
                    {
                        'updateCells': {
                            'range': {
                                'sheetId': 0,
                                'startRowIndex': 0,
                                'startColumnIndex': 0
                            },
                            'rows': [
                                {
                                    'values': [
                                        {
                                            'userEnteredValue': {
                                                'stringValue': notes
                                            }
                                        }
                                    ]
                                }
                            ],
                            'fields': 'userEnteredValue'
                        }
                    }
                ]
            }
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=requests_body
            ).execute()

        return jsonify({
            'status': 'success',
            'spreadsheetId': spreadsheet_id,
            'spreadsheetLink': f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
            'message': f'Spreadsheet "{title}" created successfully.'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
