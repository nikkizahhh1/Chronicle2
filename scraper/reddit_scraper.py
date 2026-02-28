import requests
import boto3
import uuid
import json
import re
import time
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Reddit JSON API (no auth needed!)
REDDIT_API = "https://www.reddit.com"

# Foursquare API
FOURSQUARE_API_KEY = os.getenv('FOURSQUARE_API_KEY', '')
FOURSQUARE_API = "https://places-api.foursquare.com/places/search"

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('travel-pois')

# Target cities and their subreddits
CITIES = {
    'nyc': {'country': 'USA', 'subreddits': ['nyc', 'AskNYC']},
}

# Blacklist keywords - filter out non-tourist-appropriate venues
BLACKLIST_KEYWORDS = [
    # Tobacco/Vape
    'vape', 'vaping', 'smoke shop', 'tobacco', 'cigar', 'hookah', 'shisha',
    
    # Adult/Inappropriate
    'strip club', 'adult', 'gentlemen\'s club', 'massage parlor',
    
    # Financial services
    'pawn shop', 'payday loan', 'check cashing', 'money transfer', 'western union',
    
    # Chain stores (not hidden gems)
    'walmart', 'target', 'cvs', 'walgreens', 'duane reade', 'rite aid',
    'mcdonald', 'burger king', 'wendy', 'taco bell', 'kfc', 'subway sandwich',
    'starbucks', 'dunkin',
    
    # Automotive
    'gas station', 'auto repair', 'car wash', 'tire shop', 'mechanic',
    
    # Utilities/Services
    'laundromat', 'dry clean', 'storage unit', 'post office', 'fedex', 'ups',
    
    # Potentially sketchy
    'liquor store', 'dispensary', 'cannabis',
    
    # Medical/Practical
    'urgent care', 'clinic', 'pharmacy', 'dentist', 'hospital'
]

# Keywords to find local recommendations
KEYWORDS = [
    # Strong hidden/underrated signals
    "hidden gem",
    "off the beaten path",
    "secret spot",
    "underrated",
    "slept on",
    "under the radar",
    "little-known",
    "not well known",

    # Small/local-business signals
    "hole in the wall",
    "mom and pop",
    "family-owned",
    "local joint",
    "neighborhood spot",

    # Locals-only phrasing
    "locals love",
    "real locals know",
    "locals go here",
    "my go-to spot",
    "our go-to spot",

    # Cheap hidden gems
    "affordable",
    "best bang for your buck",
    "good for the price",

    # Authentic/longtime local places
    "authentic",
    "real deal",
    "been around forever",
    "old school"
]

# Category keywords
CATEGORIES = {
    'Food & Drink': [
        'restaurant', 'cafe', 'coffee', 'bakery', 'brunch',
        'brewery', 'winery', 'bar', 'food truck', 'dessert'
    ],
    'Adventure & Outdoors': [
        'hiking', 'biking', 'surfing', 'swimming',
        'kayaking', 'camping', 'outdoor'
    ],
    'Nature & Scenic': [
        'park', 'beach', 'lake', 'waterfall',
        'botanical garden', 'viewpoint', 'sunset'
    ],
    'Culture & History': [
        'museum', 'gallery', 'temple', 'church',
        'historic', 'cultural', 'market'
    ],
    'Nightlife & Entertainment': [
        'club', 'live music', 'concert',
        'comedy', 'karaoke', 'arcade'
    ],
    'Well-Being': [
        'spa', 'yoga', 'meditation',
        'wellness', 'relaxing', 'quiet'
    ],
    'Shopping': [
        'boutique', 'thrift', 'vintage',
        'flea market', 'bookstore'
    ]
}

def extract_pois_from_text(text: str, city: str) -> List[str]:
    """Extract potential POI names from text"""
    potential_pois = []
    
    patterns = [
        r'visit (?:the )?([A-Z][a-zA-Z\s]{3,30})',
        r'go to (?:the )?([A-Z][a-zA-Z\s]{3,30})',
        r'([A-Z][a-zA-Z\s]{3,30}) is (?:amazing|great|beautiful|worth)',
        r'check out (?:the )?([A-Z][a-zA-Z\s]{3,30})'
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        potential_pois.extend(matches)
    
    return [poi.strip() for poi in potential_pois if len(poi.strip()) > 3]

def categorize_poi(text: str) -> tuple:
    """Determine category and activity intensity from context"""
    text_lower = text.lower()
    
    category = 'Culture & History'  # Default fallback
    for cat, keywords in CATEGORIES.items():
        if any(keyword in text_lower for keyword in keywords):
            category = cat
            break
    
    intensity = 3
    if any(word in text_lower for word in ['relaxing', 'peaceful', 'quiet', 'chill']):
        intensity = 2
    elif any(word in text_lower for word in ['hiking', 'climbing', 'adventure', 'active']):
        intensity = 4
    
    return category, intensity

def estimate_budget(text: str) -> str:
    """Estimate budget level from context"""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ['free', 'cheap', 'budget', 'affordable']):
        return 'low'
    elif any(word in text_lower for word in ['expensive', 'luxury', 'upscale', 'fancy']):
        return 'high'
    return 'medium'

def validate_poi_with_foursquare(poi_name: str, city: str) -> Optional[Dict]:
    """
    Validate POI exists and get details from Foursquare
    Returns None if POI is too popular, doesn't exist, or is blacklisted
    """
    # Check blacklist first (before API call)
    poi_name_lower = poi_name.lower()
    if any(keyword in poi_name_lower for keyword in BLACKLIST_KEYWORDS):
        print(f"  ❌ '{poi_name}' blacklisted (inappropriate venue)")
        return None
    
    if not FOURSQUARE_API_KEY:
        print("Warning: FOURSQUARE_API_KEY not set, skipping validation")
        return {'valid': True, 'lat': None, 'lon': None}
    
    try:
        headers = {
            'Authorization': f'Bearer {FOURSQUARE_API_KEY}',
            'Accept': 'application/json',
            'X-Places-Api-Version': '2025-06-17'
        }
        
        params = {
            'query': poi_name,
            'near': city,
            'limit': 1
        }
        
        response = requests.get(FOURSQUARE_API, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = data.get('results', [])
        
        if not results:
            print(f"  ❌ '{poi_name}' not found on Foursquare")
            return None
        
        place = results[0]
        
        # Check categories for blacklisted terms
        categories = place.get('categories', [])
        for category in categories:
            category_name = category.get('name', '').lower()
            if any(keyword in category_name for keyword in BLACKLIST_KEYWORDS):
                print(f"  ❌ '{poi_name}' blacklisted category ({category_name})")
                return None
        
        # Get rating/popularity data (new API format)
        stats = place.get('stats', {})
        total_ratings = stats.get('total_ratings', 0)
        
        # If stats not available, try popularity field
        if total_ratings == 0:
            popularity = place.get('popularity', 0)
            total_ratings = popularity
        
        # Filter by popularity (more lenient if no data available)
        if total_ratings > 500:
            print(f"  ❌ '{poi_name}' too popular ({total_ratings} ratings)")
            return None
        
        # Skip validation if no rating data (keep the POI)
        if total_ratings == 0:
            print(f"  ⚠️  '{poi_name}' no rating data, keeping anyway")
        elif total_ratings < 5:
            print(f"  ❌ '{poi_name}' too few ratings ({total_ratings} ratings)")
            return None
        
        # Get coordinates (new API uses latitude/longitude directly)
        lat = place.get('latitude')
        lon = place.get('longitude')
        
        # Fallback to geocodes if direct coords not available
        if not lat or not lon:
            geocodes = place.get('geocodes', {}).get('main', {})
            lat = geocodes.get('latitude')
            lon = geocodes.get('longitude')
        
        print(f"  ✅ '{poi_name}' validated ({total_ratings} ratings)")
        
        return {
            'valid': True,
            'lat': lat,
            'lon': lon,
            'foursquare_ratings': total_ratings,
            'foursquare_id': place.get('fsq_place_id', place.get('fsq_id'))  # Handle both old and new
        }
        
    except Exception as e:
        print(f"  ⚠️  Error validating '{poi_name}': {e}")
        return None

def scrape_subreddit(subreddit_name: str, city: str, limit: int = 50) -> List[Dict]:
    """Scrape a subreddit for POI recommendations using Reddit JSON API"""
    print(f"Scraping r/{subreddit_name} for {city}...")
    
    pois = []
    headers = {'User-Agent': 'TravelAssistant/1.0'}
    
    for keyword in KEYWORDS:  # Using all keywords for comprehensive coverage
        query = f"{city} {keyword}"
        
        try:
            # Search using Reddit's JSON API
            url = f"{REDDIT_API}/r/{subreddit_name}/search.json"
            params = {
                'q': query,
                'limit': 25,
                'restrict_sr': 'on',
                'sort': 'relevance'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            posts = data.get('data', {}).get('children', [])
            
            for post_wrapper in posts:
                post = post_wrapper.get('data', {})
                title = post.get('title', '')
                selftext = post.get('selftext', '')
                full_text = f"{title} {selftext}"
                
                poi_names = extract_pois_from_text(full_text, city)
                
                for poi_name in poi_names:
                    category, intensity = categorize_poi(full_text)
                    budget = estimate_budget(full_text)
                    
                    poi = {
                        'poi_id': str(uuid.uuid4()),
                        'name': poi_name,
                        'city': city.title(),
                        'country': CITIES[city]['country'],
                        'category': category,
                        'budget_level': budget,
                        'activity_intensity': intensity,
                        'reddit_mentions': 1,
                        'source_url': f"https://reddit.com{post.get('permalink', '')}",
                        'description': title[:200],
                        'scraped_at': datetime.now(timezone.utc).isoformat()
                    }
                    
                    pois.append(poi)
                
                # Get comments from the post
                post_id = post.get('id', '')
                if post_id:
                    try:
                        comment_url = f"{REDDIT_API}/r/{subreddit_name}/comments/{post_id}.json"
                        comment_response = requests.get(comment_url, headers=headers, timeout=15)
                        comment_response.raise_for_status()
                        comment_data = comment_response.json()
                        
                        # Comments are in the second element of the response
                        if len(comment_data) > 1:
                            comments = comment_data[1].get('data', {}).get('children', [])
                            
                            for comment_wrapper in comments[:5]:  # Limit to 5 comments per post
                                comment = comment_wrapper.get('data', {})
                                body = comment.get('body', '')
                                
                                if body and body != '[deleted]' and body != '[removed]':
                                    comment_pois = extract_pois_from_text(body, city)
                                    
                                    for poi_name in comment_pois:
                                        category, intensity = categorize_poi(body)
                                        budget = estimate_budget(body)
                                        
                                        poi = {
                                            'poi_id': str(uuid.uuid4()),
                                            'name': poi_name,
                                            'city': city.title(),
                                            'country': CITIES[city]['country'],
                                            'category': category,
                                            'budget_level': budget,
                                            'activity_intensity': intensity,
                                            'reddit_mentions': 1,
                                            'source_url': f"https://reddit.com{post.get('permalink', '')}",
                                            'description': body[:200],
                                            'scraped_at': datetime.now(timezone.utc).isoformat()
                                        }
                                        
                                        pois.append(poi)
                        
                        time.sleep(5)  # Increased delay to avoid rate limiting
                    except Exception as e:
                        print(f"  Error getting comments: {e}")
                        continue
            
            time.sleep(5)  # Increased delay to avoid rate limiting
        
        except Exception as e:
            print(f"  Error scraping {keyword}: {e}")
            continue
    
    return pois

def save_to_dynamodb(pois: List[Dict]):
    """Save POIs to DynamoDB"""
    print(f"Saving {len(pois)} POIs to DynamoDB...")
    
    with table.batch_writer() as batch:
        for poi in pois:
            batch.put_item(Item=poi)
    
    print("Saved successfully!")

def save_to_json(pois: List[Dict], filename: str = 'pois_backup.json'):
    """Save POIs to JSON file as backup"""
    with open(filename, 'w') as f:
        json.dump(pois, f, indent=2)
    print(f"Backup saved to {filename}")

def main():
    all_pois = []
    
    print(f"\n🔍 Starting scrape with Foursquare validation...")
    print(f"Foursquare API Key: {'✅ Set' if FOURSQUARE_API_KEY else '❌ Not set'}\n")
    
    for city, config in CITIES.items():
        for subreddit in config['subreddits']:
            pois = scrape_subreddit(subreddit, city, limit=20)
            all_pois.extend(pois)
    
    print(f"\n📊 Scraped {len(all_pois)} POIs from Reddit")
    print(f"🔍 Validating with Foursquare...\n")
    
    # Validate each POI with Foursquare
    validated_pois = []
    for poi in all_pois:
        foursquare_data = validate_poi_with_foursquare(poi['name'], poi['city'])
        
        if foursquare_data:
            # Add Foursquare data to POI
            poi['lat'] = foursquare_data.get('lat')
            poi['lon'] = foursquare_data.get('lon')
            poi['foursquare_ratings'] = foursquare_data.get('foursquare_ratings', 0)
            if 'foursquare_id' in foursquare_data:
                poi['foursquare_id'] = foursquare_data['foursquare_id']
            validated_pois.append(poi)
        
        time.sleep(0.5)  # Rate limiting for Foursquare
    
    print(f"\n✅ {len(validated_pois)} POIs passed validation")
    print(f"❌ {len(all_pois) - len(validated_pois)} POIs filtered out\n")
    
    # Remove duplicates by name+city
    unique_pois = {}
    for poi in validated_pois:
        key = f"{poi['name'].lower()}_{poi['city'].lower()}"
        if key not in unique_pois:
            unique_pois[key] = poi
        else:
            # Increment mention count if duplicate
            unique_pois[key]['reddit_mentions'] += 1
    
    final_pois = list(unique_pois.values())
    
    print(f"📍 Total unique POIs: {len(final_pois)}\n")
    
    save_to_json(final_pois)
    save_to_dynamodb(final_pois)

if __name__ == "__main__":
    main()
