#!/usr/bin/env python3
"""
Fitbit Data Export Script
-------------------------
This script fetches the last 30 days of Fitbit data and saves it as a CSV file.
"""

import os
import csv
import requests
import datetime
import json
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables from .env file
load_dotenv()

class FitbitClient:
    """Client for interacting with the Fitbit API"""
    
    BASE_URL = "https://api.fitbit.com/1"
    
    def __init__(self):
        """Initialize the Fitbit client with credentials from environment variables"""
        self.client_id = os.getenv("FITBIT_CLIENT_ID")
        self.client_secret = os.getenv("FITBIT_CLIENT_SECRET")
        self.access_token = os.getenv("FITBIT_ACCESS_TOKEN")
        self.refresh_token = os.getenv("FITBIT_REFRESH_TOKEN")
        
        if not all([self.client_id, self.client_secret, self.access_token, self.refresh_token]):
            raise ValueError("Missing Fitbit API credentials in .env file")
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
    
    def refresh_access_token(self):
        """Refresh the access token if it has expired"""
        url = "https://api.fitbit.com/oauth2/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {self.client_secret}"
        }
        
        response = requests.post(url, data=payload, headers=headers)
        if response.status_code == 200:
            tokens = response.json()
            self.access_token = tokens["access_token"]
            self.refresh_token = tokens["refresh_token"]
            self.headers["Authorization"] = f"Bearer {self.access_token}"
            
            # Update tokens in environment variables
            os.environ["FITBIT_ACCESS_TOKEN"] = self.access_token
            os.environ["FITBIT_REFRESH_TOKEN"] = self.refresh_token
            
            print("Access token refreshed successfully")
        else:
            print(f"Failed to refresh token: {response.text}")
    
    def handle_api_call(self, url):
        """Generic method to handle API calls with token refresh if needed"""
        response = requests.get(url, headers=self.headers)
        
        if response.status_code == 401:  # Token expired
            self.refresh_access_token()
            response = requests.get(url, headers=self.headers)
            
        if response.status_code != 200:
            print(f"API call failed with status {response.status_code}: {response.text}")
            return None
        
        return response.json()
    
    def get_weight(self, date):
        """Get weight data for a specific date"""
        url = f"{self.BASE_URL}/user/-/body/log/weight/date/{date}.json"
        data = self.handle_api_call(url)
        
        if not data or not data.get("weight"):
            return None
        
        return data["weight"][0]["weight"] if data["weight"] else None
    
    def get_activity(self, date):
        """Get activity data (calories and steps) for a specific date"""
        url = f"{self.BASE_URL}/user/-/activities/date/{date}.json"
        data = self.handle_api_call(url)
        
        if not data:
            return None, None
        
        calories = data.get("summary", {}).get("caloriesOut", None)
        steps = data.get("summary", {}).get("steps", None)
        
        return calories, steps
    
    def get_sleep(self, date):
        """Get sleep data for a specific date"""
        url = f"{self.BASE_URL}/user/-/sleep/date/{date}.json"
        data = self.handle_api_call(url)
        
        if not data or not data.get("sleep") or len(data["sleep"]) == 0:
            return None, None, None
        
        # Get the main sleep record (not naps)
        main_sleep = None
        for sleep_record in data["sleep"]:
            if sleep_record.get("isMainSleep", False):
                main_sleep = sleep_record
                break
        
        if not main_sleep:
            main_sleep = data["sleep"][0]  # Take the first one if no main sleep is marked
        
        start_time = main_sleep.get("startTime", None)
        end_time = main_sleep.get("endTime", None)
        minutes_asleep = main_sleep.get("minutesAsleep", None)
        
        return start_time, end_time, minutes_asleep

def generate_date_range(days=30):
    """Generate a list of dates for the last N days"""
    today = datetime.now()
    date_list = []
    
    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        date_list.append(date_str)
    
    return date_list

def main():
    """Main function to fetch data and create CSV"""
    try:
        client = FitbitClient()
        date_range = generate_date_range(30)
        
        # Prepare CSV file
        csv_filename = f"fitbit_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        csv_headers = [
            "Date", "Weight", "Calories Burned", "Steps", 
            "Sleep Start Time", "Sleep Stop Time", "Minutes Asleep"
        ]
        
        with open(csv_filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(csv_headers)
            
            # Iterate through each date
            for date in date_range:
                print(f"Fetching data for {date}...")
                
                # Get weight data
                weight = client.get_weight(date)
                
                # Get activity data
                calories, steps = client.get_activity(date)
                
                # Get sleep data
                sleep_start, sleep_end, minutes_asleep = client.get_sleep(date)
                
                # Write row to CSV
                writer.writerow([
                    date, weight, calories, steps, 
                    sleep_start, sleep_end, minutes_asleep
                ])
        
        print(f"Data successfully exported to {csv_filename}")
        
    except Exception as e:
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()