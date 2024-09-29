from oauth2client.service_account import ServiceAccountCredentials

def get_google_sheets_credentials() -> ServiceAccountCredentials:
    return ServiceAccountCredentials.from_json_keyfile_name('./data/gspread.json',
      ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive',
      'https://www.googleapis.com/auth/spreadsheets']) # type: ignore