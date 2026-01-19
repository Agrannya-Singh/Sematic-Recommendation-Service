import urllib.request
import json
import os

def verify_omdb_key(api_key, title="Inception"):
    print(f"Verifying OMDB API key: {api_key} for movie: {title}")
    url = f"http://www.omdbapi.com/?t={title.replace(' ', '+')}&apikey={api_key}"
    try:
        with urllib.request.urlopen(url) as response:
            status_code = response.getcode()
            print(f"Status Code: {status_code}")
            if status_code == 200:
                data = json.loads(response.read().decode())
                print("Response Data (Truncated):")
                print(json.dumps(data, indent=2)[:500] + "...")
                if data.get("Response") == "True":
                    print("\nSUCCESS: OMDB API key is valid and returning data.")
                    return True
                else:
                    print(f"\nFAILURE: OMDB returned error: {data.get('Error')}")
            else:
                print(f"\nFAILURE: API returned status code {status_code}")
    except Exception as e:
        print(f"\nERROR: {e}")
    return False

if __name__ == "__main__":
    key = os.getenv("OMDB_API_KEY")
    if key:
        verify_omdb_key(key)
    else:
        print("Please set OMDB_API_KEY environment variable.")
