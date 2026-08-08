# Your Draft Helper App

## What this does
- Reads your ranked player list from your Google Sheet
- Checks your Sleeper league to see who's already been drafted
- Shows you only the players still available, updating every 15 seconds

## One-time setup: make your Google Sheet readable

Your app needs to read your sheet without you having to log in every time.
The simplest way is to "publish" it as a plain data file:

1. Open your Google Sheet
2. Click **File > Share > Publish to web**
3. Under "Link", make sure it's set to publish the whole sheet (or just
   "Sheet1"), and change the format dropdown to **Comma-separated values (.csv)**
4. Click **Publish**, then confirm

That's it - no password or key needed for this part.

## Running the app

Open Terminal and type these commands one at a time:

    cd path/to/fantasy-draft-app
    pip3 install -r requirements.txt
    python3 app.py

Then open your browser and go to:

    http://localhost:5000

Leave the Terminal window open while you use the app - closing it stops
the app. To stop it on purpose, click into the Terminal window and press
Control + C.
