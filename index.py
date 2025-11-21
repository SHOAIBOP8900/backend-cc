from flask import Flask, request, jsonify
from flask_cors import CORS
import re
from datetime import datetime
import time
from collections import defaultdict
import random

app = Flask(__name__)
# Enable CORS with more permissive settings
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Rate limiting storage (in-memory, use Redis for production)
request_counts = defaultdict(list)
RATE_LIMIT = 100  # requests per hour
RATE_WINDOW = 3600  # 1 hour in seconds

def check_rate_limit(ip):
    """Check if IP has exceeded rate limit"""
    now = time.time()
    # Remove old requests outside the window
    request_counts[ip] = [req_time for req_time in request_counts[ip] 
                          if now - req_time < RATE_WINDOW]
    
    if len(request_counts[ip]) >= RATE_LIMIT:
        return False
    
    request_counts[ip].append(now)
    return True

def luhn_check(card_number):
    """Validate card number using Luhn algorithm"""
    try:
        card_number = str(card_number)
        total = 0
        parity = len(card_number) % 2
        
        for i, digit in enumerate(card_number):
            d = int(digit)
            if i % 2 == parity:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        
        return total % 10 == 0
    except:
        return False

def validate_card_format(card_data):
    """Validate card format and details"""
    parts = [p.strip() for p in card_data.split('|')]
    
    if len(parts) < 4:
        return None, "Invalid format"
    
    card_number = re.sub(r'\D', '', parts[0])
    month = parts[1].zfill(2)
    year = parts[2]
    cvv = parts[3]
    
    # Validate card number length
    if len(card_number) < 13 or len(card_number) > 19:
        return None, "Invalid card number length"
    
    # Validate month
    try:
        month_int = int(month)
        if month_int < 1 or month_int > 12:
            return None, "Invalid month"
    except:
        return None, "Invalid month format"
    
    # Validate year
    try:
        if len(year) == 2:
            year = f"20{year}"
        year_int = int(year)
        current_year = datetime.now().year
        if year_int < current_year or len(year) != 4:
            return None, "Invalid or expired year"
    except:
        return None, "Invalid year format"
    
    # Validate CVV
    if len(cvv) < 3 or len(cvv) > 4 or not cvv.isdigit():
        return None, "Invalid CVV"
    
    return {
        'card_number': card_number,
        'month': month,
        'year': year,
        'cvv': cvv,
        'original': card_data
    }, None

@app.route('/api/validate', methods=['POST'])
def validate_card():
    """Validate single card"""
    client_ip = request.remote_addr
    
    # Check rate limit
    if not check_rate_limit(client_ip):
        return jsonify({
            'error': 'Rate limit exceeded. Please try again later.'
        }), 429
    
    data = request.get_json()
    card_data = data.get('card', '')
    
    if not card_data:
        return jsonify({'error': 'No card data provided'}), 400
    
    # Validate format
    validated, error = validate_card_format(card_data)
    
    if error:
        return jsonify({
            'status': 'unknown',
            'message': error,
            'original': card_data
        })
    
    # Check Luhn
    is_valid = luhn_check(validated['card_number'])
    
    return jsonify({
        'status': 'live' if is_valid else 'dead',
        'message': 'Valid card' if is_valid else 'Invalid card',
        'original': card_data
    })

@app.route('/api/validate-batch', methods=['POST'])
def validate_batch():
    """Validate multiple cards"""
    client_ip = request.remote_addr
    
    # Check rate limit
    if not check_rate_limit(client_ip):
        return jsonify({
            'error': 'Rate limit exceeded. Please try again later.'
        }), 429
    
    data = request.get_json()
    cards = data.get('cards', [])
    
    if not cards or len(cards) > 100:  # Limit batch size
        return jsonify({'error': 'Invalid batch size (max 100)'}), 400
    
    results = []
    
    for card_data in cards:
        validated, error = validate_card_format(card_data)
        
        if error:
            results.append({
                'status': 'unknown',
                'message': error,
                'original': card_data
            })
        else:
            is_valid = luhn_check(validated['card_number'])
            results.append({
                'status': 'live' if is_valid else 'dead',
                'message': 'Valid card' if is_valid else 'Invalid card',
                'original': card_data
            })
    
    return jsonify({'results': results})

@app.route('/api/generate', methods=['POST'])
def generate_cards():
    """Generate credit cards"""
    client_ip = request.remote_addr
    
    # Check rate limit
    if not check_rate_limit(client_ip):
        return jsonify({
            'error': 'Rate limit exceeded. Please try again later.'
        }), 429
    
    data = request.get_json()
    bin_pattern = data.get('bin', '')
    quantity = data.get('quantity', 10)
    month = data.get('month', 'rnd')
    year = data.get('year', 'rnd')
    cvv = data.get('cvv', 'rnd')
    
    if not bin_pattern or len(bin_pattern) < 6:
        return jsonify({'error': 'Invalid BIN'}), 400
    
    if quantity < 1 or quantity > 10000:
        return jsonify({'error': 'Invalid quantity (1-10000)'}), 400
    
    generated = []
    current_year = datetime.now().year
    
    for _ in range(quantity):
        # Generate card number - Replace 'x' with random digits
        card_num = ''
        for char in bin_pattern:
            if char.lower() == 'x':
                card_num += str(random.randint(0, 9))
            else:
                card_num += char
        
        # Fill to 15 digits if needed
        while len(card_num) < 15:
            card_num += str(random.randint(0, 9))
        
        # Calculate Luhn check digit
        total = 0
        for i, digit in enumerate(card_num):
            d = int(digit)
            if i % 2 == 0:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        check_digit = (total * 9) % 10
        card_num += str(check_digit)
        
        # Generate month
        if month.lower() == 'rnd':
            final_month = str(random.randint(1, 12)).zfill(2)
        else:
            final_month = str(month).zfill(2)
        
        # Generate year
        if year.lower() == 'rnd':
            final_year = str(random.randint(current_year + 1, current_year + 7))
        else:
            final_year = year if len(year) == 4 else f"20{year}"
        
        # Generate CVV
        if cvv.lower() == 'rnd':
            final_cvv = str(random.randint(100, 999))
        else:
            final_cvv = str(cvv).zfill(3)
        
        generated.append(f"{card_num}|{final_month}|{final_year}|{final_cvv}")
    
    return jsonify({'cards': generated})

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'API is running'})

@app.route('/', methods=['GET'])
def home():
    """Home endpoint"""
    return jsonify({
        'message': 'Taitan CChecker Backend API',
        'version': '1.0',
        'endpoints': {
            'validate': '/api/validate',
            'validate_batch': '/api/validate-batch',
            'generate': '/api/generate',
            'health': '/health'
        }
    })

if __name__ == '__main__':
    print("🚀 Starting Taitan CChecker Backend API...")
    print("📡 API will be available at: http://127.0.0.1:5000")
    print("⚠️  For production, use a proper WSGI server like Gunicorn")
    app.run(debug=True, host='0.0.0.0', port=5000)