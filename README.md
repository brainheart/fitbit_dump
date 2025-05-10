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

Run the script with one of the following options:

```bash
# Default: get last 8 days of data
python fitbit_export.py                      # Outputs to fitbit_export-YYYY-MM-DD_to_YYYY-MM-DD.csv

# Get a specified number of days from today
python fitbit_export.py --days 30            # Outputs to fitbit_export-YYYY-MM-DD_to_YYYY-MM-DD.csv

# Get data for a specific date range
python fitbit_export.py --start 2025-04-01 --end 2025-04-30

# Get data for a single specific date
python fitbit_export.py --date 2025-04-15

# Control the order of date processing
python fitbit_export.py --days 30 --desc     # Process newest to oldest dates
python fitbit_export.py --start 2025-01-01 --end 2025-04-30 --asc  # Process oldest to newest (default)

# Specify a custom filename without date range
python fitbit_export.py --days 30 --output custom.csv

# Use the original filename without date range
python fitbit_export.py --days 30 --no-date-in-filename   # Outputs to fitbit_export.csv
```

For backwards compatibility, you can also use the original positional arguments:

```bash
python fitbit_export.py 30 my_data.csv  # 30 days → my_data.csv
```

The script will:
1. Authenticate with Fitbit on first run (opens a browser window)
2. Fetch the requested data one day at a time
3. Write each day's data to the CSV as soon as it's retrieved
4. Process dates in the specified order (oldest to newest by default)
5. Handle token refresh if your access token has expired
6. Include date range in the output filename by default

## Notes

- The script writes data incrementally, so if it's interrupted, you'll still have partial data
- By default, dates are processed from oldest to newest (--asc), but you can use --desc to process newest to oldest
- CSV filenames now include the date range by default (e.g., fitbit_export-2025-04-26_to_2025-05-03.csv)
- Use --no-date-in-filename to revert to the original filename behavior
- The script uses the Fitbit API which has rate limits. If you encounter rate limiting issues, the script may fail.
- Some data may be missing if you didn't record it on your Fitbit device (e.g., if you didn't wear your device while sleeping).
