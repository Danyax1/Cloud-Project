from flask import Flask, render_template, jsonify
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Gauge
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import hvac
import requests
import threading
import time
import os

app = Flask(__name__)
metrics = PrometheusMetrics(app)

crypto_price = Gauge('crypto_price_usd', 'Cryptocurrency price in USD', ['coin'])

INFLUX_URL = os.environ.get('INFLUXDB_URL')
INFLUX_TOKEN = os.environ.get('INFLUXDB_TOKEN')
INFLUX_ORG = os.environ.get('INFLUXDB_ORG', 'myorg')
INFLUX_BUCKET = os.environ.get('INFLUXDB_BUCKET', 'crypto')

VAULT_ADDR = os.environ.get('VAULT_ADDR')
VAULT_TOKEN = os.environ.get('VAULT_TOKEN')

# Save latest prices
latest_prices = {'bitcoin': 0, 'ethereum': 0, 'solana': 0}

def get_coingecko_url():
    try:
        if VAULT_ADDR and VAULT_TOKEN:
            client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
            secret = client.secrets.kv.read_secret_version(path='crypto/config')
            return secret['data']['data']['COINGECKO_API_URL']
    except Exception as e:
        print(f'Vault error: {e}')
    return 'https://api.coingecko.com/api/v3/simple/price'

def fetch_crypto_prices():
    while True:
        try:
            url = get_coingecko_url()
            params = {'ids': 'bitcoin,ethereum,solana', 'vs_currencies': 'usd'}
            r = requests.get(url, params=params, timeout=10)
            data = r.json()

            coins = {
                'bitcoin': data['bitcoin']['usd'],
                'ethereum': data['ethereum']['usd'],
                'solana': data['solana']['usd']
            }

            latest_prices.update(coins)

            # Prometheus
            for coin, price in coins.items():
                crypto_price.labels(coin=coin).set(price)

            # InfluxDB
            if INFLUX_URL and INFLUX_TOKEN:
                client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
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
def index():
    return render_template('crypto.html')

@app.route('/api/prices')
def api_prices():
    return jsonify(latest_prices)

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/api/stats')
def api_stats():
    coin = request.args.get('coin', 'bitcoin')
    hours = int(request.args.get('hours', 1))

    try:
        if not INFLUX_URL or not INFLUX_TOKEN:
            return jsonify({'error': 'InfluxDB not configured'})

        client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        query_api = client.query_api()

        query = f'''
        from(bucket: "{INFLUX_BUCKET}")
          |> range(start: -{hours}h)
          |> filter(fn: (r) => r._measurement == "crypto_price")
          |> filter(fn: (r) => r._field == "price_usd")
          |> filter(fn: (r) => r.coin == "{coin}")
        '''

        tables = query_api.query(query)
        prices = [record.get_value() for table in tables for record in table.records]
        client.close()

        if not prices:
            return jsonify({'error': 'No data for this period. Wait a few minutes for data to accumulate.'})

        return jsonify({
            'coin': coin,
            'hours': hours,
            'avg': round(sum(prices) / len(prices), 2),
            'min': round(min(prices), 2),
            'max': round(max(prices), 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
