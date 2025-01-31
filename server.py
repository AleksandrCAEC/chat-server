from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import openai
import requests
from clientdata import register_or_update_client, verify_client_code
import logging

# Указание пути к файлу service_account_json
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/service_account_json"

# Инициализация клиента OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Инициализация приложения Flask
app = Flask(__name__)
CORS(app)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/register-client', methods=['POST'])
def register_client():
    try:
        data = request.json
        result = register_or_update_client(data)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Ошибка в /register-client: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data.get('code', '').strip()

        if not code:
            logger.error("Код не был предоставлен")
            return jsonify({'status': 'error', 'message': 'Код не был предоставлен'}), 400

        client_data = verify_client_code(code)
        if client_data:
            logger.info(f"Клиент найден: {client_data}")
            return jsonify({'status': 'success', 'clientData': client_data}), 200
        else:
            logger.info(f"Клиент с кодом {code} не найден")
            return jsonify({'status': 'error', 'message': 'Неверный код'}), 404
    except Exception as e:
        logger.error(f"Ошибка в /verify-code: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
