import json
import bcrypt
import uuid
from datetime import datetime, timezone, timedelta
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.dynamodb import get_dynamodb_table
from utils.auth_utils import generate_token
from utils.response import success_response, error_response

users_table = get_dynamodb_table('users')

def signup(event, context):
    """Handle user signup"""
    try:
        body = json.loads(event['body'])
        email = body.get('email')
        password = body.get('password')
        
        if not email or not password:
            return error_response(400, "Email and password required")
        
        # Check if user exists
        response = users_table.get_item(Key={'email': email})
        if 'Item' in response:
            return error_response(400, "User already exists")
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Create user
        user_id = str(uuid.uuid4())
        user = {
            'user_id': user_id,
            'email': email,
            'password_hash': password_hash,
            'quiz_results': {},
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        users_table.put_item(Item=user)
        
        # Generate token
        token = generate_token(user_id, email)
        
        return success_response({
            'user_id': user_id,
            'email': email,
            'token': token
        })
        
    except Exception as e:
        return error_response(500, str(e))

def login(event, context):
    """Handle user login"""
    try:
        body = json.loads(event['body'])
        email = body.get('email')
        password = body.get('password')
        
        if not email or not password:
            return error_response(400, "Email and password required")
        
        # Get user
        response = users_table.get_item(Key={'email': email})
        if 'Item' not in response:
            return error_response(401, "Invalid credentials")
        
        user = response['Item']
        
        # Verify password
        if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            return error_response(401, "Invalid credentials")
        
        # Generate token
        token = generate_token(user['user_id'], email)
        
        return success_response({
            'user_id': user['user_id'],
            'email': email,
            'token': token
        })
        
    except Exception as e:
        return error_response(500, str(e))
