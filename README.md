# Travel Assistant - Backend

Serverless backend for the travel assistant app with Reddit-scraped POI knowledge base.

## Project Structure

```
travel-assistant/
├── scraper/              # Reddit scraping (run once to seed)
├── backend/              # Serverless API (AWS Lambda)
├── infrastructure/       # DynamoDB table definitions
└── README.md
```

## Setup

### 1. Install Dependencies

```bash
# Scraper
cd scraper
pip install -r requirements.txt

# Backend
cd ../backend
pip install -r requirements.txt
```

### 2. Configure AWS

```bash
aws configure
```

### 3. Create DynamoDB Tables

```bash
# Create POI table
cd scraper
python create_dynamodb_table.py

# Create users and trips tables
cd ../infrastructure
python dynamodb_tables.py
```

### 4. Seed POI Data (Run Once)

```bash
cd scraper
# No credentials needed - uses Pushshift API!
python reddit_scraper.py
```

This will scrape Reddit via Pushshift API and save ~200-500 POIs to DynamoDB.

### 5. Deploy Backend

```bash
cd backend
cp .env.example .env
# Edit .env with your JWT secret

# Install Serverless Framework
npm install -g serverless
npm install --save-dev serverless-python-requirements

# Deploy
serverless deploy
```

## API Endpoints

### Authentication
- `POST /auth/signup` - Create account
- `POST /auth/login` - Login

### Quiz
- `POST /quiz/submit` - Save quiz results
- `GET /quiz` - Get quiz results

### Trips
- `GET /trips` - List all trips
- `POST /trips` - Create new trip
- `GET /trips/{trip_id}` - Get trip details
- `PUT /trips/{trip_id}` - Update trip
- `DELETE /trips/{trip_id}` - Delete trip

## Backend Services

### POI Service
Query POIs from DynamoDB based on user preferences:
```python
from services.poi_service import get_pois_for_preferences

pois = get_pois_for_preferences(
    city='Nyc',
    categories=['Food & Drink', 'Culture & History', 'Nightlife & Entertainment'],
    budget_level='medium',
    min_intensity=2,
    max_intensity=4
)
```

### Route Optimizer
Optimize daily routes using nearest-neighbor algorithm:
```python
from services.route_optimizer import optimize_route, split_into_days

optimized = optimize_route(pois)
daily_routes = split_into_days(pois, days=3)
```

### Validation Service
Validate POIs exist in knowledge base:
```python
from services.validation_service import validate_itinerary_pois

validated = validate_itinerary_pois(itinerary)
```

## For AI Team

Backend provides these functions for itinerary generation:

```python
# Query available POIs
from services.poi_service import get_pois_for_preferences

# Validate POI exists
from services.validation_service import validate_poi_list

# Optimize route
from services.route_optimizer import optimize_route
```

## Cost Estimate

- DynamoDB: Free tier (25GB, 200M requests/month)
- Lambda: Free tier (1M requests/month)
- API Gateway: Free tier (1M requests/month)
- Reddit JSON API: Free (no authentication required)

Total: $0 for hackathon scale

## Notes

- Uses Reddit's public JSON API (no credentials needed!)
- Real-time data from Reddit
- Rate limited to ~60 requests/min (built-in delays)
