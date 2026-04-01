import os
from dotenv import load_dotenv
from plexapi.myplex import MyPlexAccount
import xml.etree.ElementTree as ET

load_dotenv('.env')
account = MyPlexAccount(token=os.getenv('PLEX_TOKEN'))

for item in account.watchlist():
    if getattr(item, 'type', '') == 'show':
        print(f"Inspecting: {item.title}")
        try:
            for s in item.seasons():
                print(f"  --- Season {s.seasonNumber} XML ---")
                print(ET.tostring(s._data, encoding='unicode'))
        except Exception as e:
            print(f"Failed to fetch seasons: {e}")
