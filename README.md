# Fitbit Data Export

A Python script to export the last 30 days of Fitbit data to a CSV file.

## Data Exported

The script exports the following Fitbit data for each day:
- Date
- Weight
- Calories Burned
- Steps
- Sleep Start Time
- Sleep Stop Time
- Minutes Asleep

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Register a Fitbit App

1. Go to [Fitbit Developer](https://dev.fitbit.com/apps/new)
2. Create a new app with the following settings:
   - OAuth 2.0 Application Type: Personal
   - Callback URL: http://localhost:8080/
   - Default access type: Read-Only

### 3. Get API Credentials

After creating your app, you'll need to:
1. Note your **Client ID** and **Client Secret**
2. Generate an access token and refresh token (you may need to use a tool like Postman or a authorization code flow to get these tokens)

### 4. Configure Environment Variables

Edit the `.env` file with your Fitbit API credentials:

```
FITBIT_CLIENT_ID=your_client_id_here
FITBIT_CLIENT_SECRET=your_client_secret_here
FITBIT_ACCESS_TOKEN=your_access_token_here
FITBIT_REFRESH_TOKEN=your_refresh_token_here
```

## Usage

Run the script:

```bash
python fetch_fitbit_data.py
```

The script will:
1. Fetch data for the last 30 days
2. Export the data to a CSV file named `fitbit_data_YYYYMMDD_HHMMSS.csv` in the current directory
3. Handle token refresh if your access token has expired

## Notes

- The script uses the Fitbit API which has rate limits. If you encounter rate limiting issues, the script may fail.
- Some data may be missing if you didn't record it on your Fitbit device (e.g., if you didn't wear your device while sleeping).
