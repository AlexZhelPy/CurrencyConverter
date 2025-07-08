from flask import Flask, render_template, request, jsonify
from decimal import Decimal, InvalidOperation
import requests
from typing import Dict, Tuple, Optional
from pathlib import Path
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# Конфигурация
API_KEY = 'API_KEY'  # Зарегистрируйтесь на https://www.exchangerate-api.com/ для получения ключа
BASE_URL = 'https://v6.exchangerate-api.com/v6/'
CACHE_FILE = 'exchange_rates_cache.json'
CACHE_DURATION = timedelta(hours=1)

# Поддерживаемые валюты (ISO codes)
SUPPORTED_CURRENCIES = {
    'USD': '$', 'EUR': '€', 'GBP': '£', 'JPY': '¥',
    'AUD': 'A$', 'CAD': 'C$', 'CHF': 'Fr', 'CNY': '¥',
    'RUB': '₽', 'TRY': '₺', 'INR': '₹', 'BRL': 'R$'
}

class ExchangeRateAPI:
    def __init__(self):
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """Загружает кеш из файла"""
        if Path(CACHE_FILE).exists():
            with open(CACHE_FILE, 'r') as f:
                try:
                    data = json.load(f)
                    # Проверяем, не устарели ли данные
                    last_update = datetime.fromisoformat(data['last_update'])
                    if datetime.now() - last_update < CACHE_DURATION:
                        return data
                except (json.JSONDecodeError, KeyError):
                    pass
        return {'rates': {}, 'last_update': datetime.min.isoformat()}

    def _save_cache(self, data: Dict):
        """Сохраняет данные в кеш"""
        data['last_update'] = datetime.now().isoformat()
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f)

    def get_rates(self, base_currency: str = 'USD') -> Tuple[Optional[Dict], Optional[str]]:
        """
        Получает курсы валют относительно базовой валюты
        Возвращает (rates, error_message)
        """
        # Сначала проверяем кеш
        cached_data = self._load_cache()
        if base_currency in cached_data['rates']:
            return cached_data['rates'][base_currency], None

        # Если нет в кеше, делаем запрос к API
        try:
            response = requests.get(
                f"{BASE_URL}{API_KEY}/latest/{base_currency}",
                timeout=5
            )
            data = response.json()

            if data.get('result') == 'success':
                rates = data['conversion_rates']
                # Обновляем кеш
                self.cache['rates'][base_currency] = rates
                self._save_cache(self.cache)
                return rates, None
            else:
                return None, data.get('error-type', 'Unknown API error')

        except requests.exceptions.RequestException as e:
            return None, str(e)

    def convert(self, amount: Decimal, from_curr: str, to_curr: str) -> Tuple[Optional[Decimal], Optional[str]]:
        """
        Конвертирует сумму между валютами
        Возвращает (result, error_message)
        """
        if from_curr == to_curr:
            return amount, None

        try:
            rates, error = self.get_rates(from_curr)
            if error:
                return None, error

            if to_curr not in rates:
                return None, f"Валюта {to_curr} не поддерживается"

            return amount * Decimal(str(rates[to_curr])), None

        except Exception as e:
            return None, str(e)

# Инициализация API
exchange_api = ExchangeRateAPI()

@app.route('/', methods=['GET', 'POST'])
def index():
    """Главная страница с формой конвертации"""
    result = None
    error = None
    amount = ""
    from_curr = "USD"
    to_curr = "EUR"

    if request.method == 'POST':
        amount = request.form.get('amount', '')
        from_curr = request.form.get('from_curr', 'USD')
        to_curr = request.form.get('to_curr', 'EUR')

        if amount:
            try:
                amount_dec = Decimal(amount)
                if amount_dec <= 0:
                    error = "Сумма должна быть положительной"
                else:
                    result, error = exchange_api.convert(amount_dec, from_curr, to_curr)
            except InvalidOperation:
                error = "Некорректная сумма"

    return render_template(
        'index.html',
        currencies=SUPPORTED_CURRENCIES,
        amount=amount,
        from_curr=from_curr,
        to_curr=to_curr,
        result=result,
        error=error,
        from_symbol=SUPPORTED_CURRENCIES.get(from_curr, ''),
        to_symbol=SUPPORTED_CURRENCIES.get(to_curr, '')
    )

@app.route('/api/convert', methods=['GET'])
def api_convert():
    """API endpoint для конвертации"""
    amount = request.args.get('amount', '')
    from_curr = request.args.get('from', 'USD')
    to_curr = request.args.get('to', 'EUR')

    if not amount:
        return jsonify({'error': 'Не указана сумма'}), 400

    try:
        amount_dec = Decimal(amount)
        if amount_dec <= 0:
            return jsonify({'error': 'Сумма должна быть положительной'}), 400

        result, error = exchange_api.convert(amount_dec, from_curr, to_curr)

        if error:
            return jsonify({'error': error}), 400

        return jsonify({
            'amount': amount,
            'from': from_curr,
            'to': to_curr,
            'result': str(result),
            'symbol': SUPPORTED_CURRENCIES.get(to_curr, '')
        })

    except InvalidOperation:
        return jsonify({'error': 'Некорректная сумма'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Инициализация кеш-файла
    try:
        # Если файл не существует, создаем его с базовыми значениями
        if not Path(CACHE_FILE).exists():
            with open(CACHE_FILE, 'w') as f:
                json.dump({'rates': {}, 'last_update': datetime.min.isoformat()}, f)
    except Exception as e:
        print(f"Ошибка при инициализации кеш-файла: {e}")

    app.run(debug=True)

