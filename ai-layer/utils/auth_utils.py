import jwt
import os
from typing import Optional, Dict

def verify_token(token: str) -> Optional[Dict]:
    try:
        secret = os.environ.get('JWT_SECRET')
        payload = jwt.decode(token, secret, algorithms=['HS256'])
        return payload
    except jwt.InvalidTokenError:
        return None

def extract_user_id(event: Dict) -> Optional[str]:
    auth_header = event.get('headers', {}).get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header.replace('Bearer ', '')
    payload = verify_token(token)
    return payload.get('user_id') if payload else None
