from flask import Flask
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Gauge
import requests
import threading
import time
import os

app = Flask(__name__)
metrics = PrometheusMetrics(app)

# Криптовалютні метрики
btc_price = Gauge('crypto_price_usd', 'Cryptocurrency price in USD', ['coin'])

def fetch_crypto_prices():
    while True:
        try:
            url = 'https://api.coingecko.com/api/v3/simple/price'
            params = {'ids': 'bitcoin,ethereum,solana', 'vs_currencies': 'usd'}
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            btc_price.labels(coin='bitcoin').set(data['bitcoin']['usd'])
            btc_price.labels(coin='ethereum').set(data['ethereum']['usd'])
            btc_price.labels(coin='solana').set(data['solana']['usd'])
        except Exception as e:
            print(f'Error fetching prices: {e}')
        time.sleep(60)

t = threading.Thread(target=fetch_crypto_prices, daemon=True)
t.start()

@app.route('/')
def hello():
    return 'Hello from Cloud-Project on AWS EC2!'

@app.route('/health')
def health():
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

