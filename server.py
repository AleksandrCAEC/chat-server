from flask import Flask, request, jsonify
import random
import string

app = Flask(__name__)
clients = {}

def generate_unique_code():
    random_digits = ''.join(random.choices(string.digits, k=7))
    return f"CAEC{random_digits}"

@app.route('/register-client', methods=['POST'])
def register_client():
    data = request.json
    unique_code = generate_unique_code()
    clients[unique_code] = {
        'name': data['name'],
        'phone': data['phone'],
        'email': data['email']
    }
    return jsonify({'uniqueCode': unique_code})

@app.route('/verify-code', methods=['POST'])
def verify_code():
    data = request.json
    code = data['code']
    if code in clients:
        return jsonify(clients[code])
    else:
        return jsonify({'error': 'Invalid code'}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
