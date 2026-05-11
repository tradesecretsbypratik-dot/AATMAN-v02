from flask import Flask, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# NSE requires browser-like headers or it returns 401/403
NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.nseindia.com/option-chain',
    'Connection': 'keep-alive',
}

NSE_OC_URL  = 'https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY'
NSE_BASE_URL = 'https://www.nseindia.com'

# ── Session with cookies (NSE requires this) ──
def get_nse_session():
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    session.get(NSE_BASE_URL, timeout=10)
    session.get('https://www.nseindia.com/option-chain', timeout=10)
    return session

# ── Root: health check ──
@app.route('/')
def index():
    return jsonify({'status': 'AATMAN V.02 running on NSE direct feed'})

# ── Option Chain endpoint ──
@app.route('/option-chain')
def option_chain():
    try:
        session  = get_nse_session()
        response = session.get(NSE_OC_URL, timeout=15)

        if response.status_code != 200:
            return jsonify({'error': f'NSE returned {response.status_code}'}), 500

        raw     = response.json()
        records = raw.get('records', {})
        data    = records.get('data', [])

        if not data:
            return jsonify({'error': 'No data from NSE'}), 500

        strikes_map = {}

        for entry in data:
            price = entry.get('strikePrice')
            if price is None:
                continue
            if price not in strikes_map:
                strikes_map[price] = {'price': price, 'callOI': 0, 'putOI': 0}
            if 'CE' in entry:
                strikes_map[price]['callOI'] += entry['CE'].get('openInterest', 0)
            if 'PE' in entry:
                strikes_map[price]['putOI']  += entry['PE'].get('openInterest', 0)

        strikes = sorted(strikes_map.values(), key=lambda x: x['price'])

        # ── Metrics ──
        total_call_oi = sum(s['callOI'] for s in strikes)
        total_put_oi  = sum(s['putOI']  for s in strikes)
        pcr       = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0
        call_wall = max(strikes, key=lambda x: x['callOI'])['price']
        put_base  = max(strikes, key=lambda x: x['putOI'])['price']

        # ── Keep only 40 strikes nearest to ATM ──
        atm_price = records.get('underlyingValue', 0)
        if atm_price:
            strikes = sorted(strikes, key=lambda x: abs(x['price'] - atm_price))[:40]
            strikes = sorted(strikes, key=lambda x: x['price'])

        return jsonify({
            'pcr':      pcr,
            'callWall': call_wall,
            'putBase':  put_base,
            'atm':      atm_price,
            'expiry':   records.get('expiryDates', [''])[0],
            'strikes':  strikes
        })

    except requests.exceptions.Timeout:
        return jsonify({'error': 'NSE request timed out'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False)
