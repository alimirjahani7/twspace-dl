#!/usr/bin/env python3
"""Test script to test the user_tweets function"""
import json
import urllib.parse
from twspace_dl.api import TwitterAPI


def get_cookie_dict(path):
    """Load cookies from Netscape cookie file format - only auth_token and ct0"""
    cookies = {}
    required_cookies = {'auth_token', 'ct0'}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) != 7:
                continue
            name = parts[5]
            # Only extract required cookies
            if name not in required_cookies:
                continue
            raw_value = parts[6]
            if raw_value.startswith('"') and raw_value.endswith('"'):
                raw_value = raw_value[1:-1]
            value = urllib.parse.unquote(raw_value)
            cookies[name] = value
    return cookies


# Initialize the API
api = TwitterAPI()

# Load cookies from cookies.txt
cookies_dict = get_cookie_dict('cookies.txt')

# Initialize the APIs with cookies
api.init_apis(cookies_dict)

# Test the user_tweets function
screen_name = "solquicks"  # You can change this to any Twitter username
number_of_tweets = 5  # Number of tweets to retrieve

print(f"Testing user_tweets for screen_name: {screen_name}")
print("-" * 80)

try:
    # First get the user ID
    print(f"Step 1: Getting user ID for @{screen_name}...")
    user_id = api.graphql_api.user_id(screen_name)
    print(f"User ID: {user_id}")

    # Then get the user's tweets
    print(f"\nStep 2: Retrieving {number_of_tweets} tweets...")
    result = api.graphql_api.user_tweets(user_id, number_of_tweets)

    # Pretty print the result
    print("\n" + "=" * 80)
    print("FULL API RESPONSE:")
    print("=" * 80)
    print(json.dumps(result, indent=2))

    # Extract tweet information if available
    print("\n" + "=" * 80)
    print(f"TWEETS FROM @{screen_name}:")
    print("=" * 80)

    if "data" in result and "user" in result["data"]:
        timeline = result["data"]["user"]["result"].get("timeline_v2", {})
        timeline_items = timeline.get("timeline", {}).get("instructions", [])

        tweet_count = 0
        for instruction in timeline_items:
            if instruction.get("type") == "TimelineAddEntries":
                entries = instruction.get("entries", [])
                for entry in entries:
                    content = entry.get("content", {})
                    if content.get("entryType") == "TimelineTimelineItem":
                        item_content = content.get("itemContent", {})
                        if item_content.get("itemType") == "TimelineTweet":
                            tweet_results = item_content.get("tweet_results", {})
                            tweet_data = tweet_results.get("result", {})
                            if tweet_data.get("__typename") == "Tweet":
                                tweet_count += 1
                                legacy = tweet_data.get("legacy", {})
                                created_at = legacy.get("created_at", "N/A")
                                full_text = legacy.get("full_text", "N/A")
                                retweet_count = legacy.get("retweet_count", 0)
                                favorite_count = legacy.get("favorite_count", 0)

                                print(f"\nTweet #{tweet_count}:")
                                print(f"  Created: {created_at}")
                                print(f"  Text: {full_text[:100]}..." if len(full_text) > 100 else f"  Text: {full_text}")
                                print(f"  Retweets: {retweet_count}, Likes: {favorite_count}")

    print(f"\n✓ Test completed successfully! Retrieved {tweet_count} tweets.")

except Exception as e:
    print(f"✗ Error occurred: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()
