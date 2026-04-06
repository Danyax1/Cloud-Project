from flask import Flask
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Gauge
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import requests
import threading
import time
import os

app = Flask(__name__)
metrics = PrometheusMetrics(app)

# Prometheus metrics
crypto_price = Gauge('crypto_price_usd', 'Cryptocurrency price in USD', ['coin'])

# InfluxDB config
INFLUX_URL = os.environ.get('INFLUXDB_URL')
INFLUX_TOKEN = os.environ.get('INFLUXDB_TOKEN')
INFLUX_ORG = os.environ.get('INFLUXDB_ORG', 'myorg')
INFLUX_BUCKET = os.environ.get('INFLUXDB_BUCKET', 'crypto')

def get_influx_client():
    if INFLUX_URL and INFLUX_TOKEN:
        return InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    return None

def fetch_crypto_prices():
    while True:
        try:
            url = 'https://api.coingecko.com/api/v3/simple/price'
            params = {'ids': 'bitcoin,ethereum,solana', 'vs_currencies': 'usd'}
            r = requests.get(url, params=params, timeout=10)
            data = r.json()

            coins = {
                'bitcoin': data['bitcoin']['usd'],
                'ethereum': data['ethereum']['usd'],
                'solana': data['solana']['usd']
            }

            # Prometheus
            for coin, price in coins.items():
                crypto_price.labels(coin=coin).set(price)

            # Influx
            client = get_influx_client()
            if client:
                write_api = client.write_api(write_options=SYNCHRONOUS)
                for coin, price in coins.items():
                    point = Point("crypto_price") \
                        .tag("coin", coin) \
                        .field("price_usd", float(price))
                    write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
                client.close()

        except Exception as e:
            print(f'Error: {e}')
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
