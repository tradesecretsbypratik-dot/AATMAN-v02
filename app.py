from flask import Flask, jsonify
from flask_cors import CORS
import upstox_client
from upstox_client.rest import ApiException
import os
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)
CORS(app)

# ── Upstox credentials from Render environment variables ──
API_KEY      = os.environ.get('UPSTOX_API_KEY', '')
API_SECRET   = os.environ.get('UPSTOX_API_SECRET', '')
REDIRECT_URI = os.environ.get('UPSTOX_REDIRECT_URI', '')
ACCESS_TOKEN = os.environ.get('UPSTOX_ACCESS_TOKEN', '')

# ── Calculate next Nifty expiry (Tuesday) ──
def get_next_expiry():
    IST = pytz.timezone('Asia/Kolkata')
    now = datetime.now(IST)
    # Tuesday = weekday 1
    days_ahead = (1 - now.weekday()) % 7
    if days_ahead == 0:
        # Today is Tuesday
        if now.hour >= 15 and now.minute >= 30:
            days_ahead = 7  # roll to next week
    expiry = now + timedelta(days=days_ahead)
    return expiry.strftime('%Y-%m-%d')

# ── Root: health check ──
@app.route('/')
def index():
    return jsonify({'status': 'AATMAN V.02 server running', 'time': str(datetime.now())})

# ── Option Chain endpoint ──
@app.route('/option-chain')
def option_chain():
    try:
        expiry_date = get_next_expiry()

        configuration = upstox_client.Configuration()
        configuration.access_token = ACCESS_TOKEN
        api_version = '2.0'

        api_instance = upstox_client.OptionsApi(
            upstox_client.ApiClient(configuration)
        )

        # Nifty 50 instrument key
        instrument_key = 'NSE_INDEX|Nifty 50'

        response = api_instance.get_option_chain_data(
            instrument_key=instrument_key,
            expiry_date=expiry_date,
            api_version=api_version
        )

        raw = response.data
        strikes = []
        total_call_oi = 0
        total_put_oi  = 0
        max_call_oi   = 0
        max_put_oi    = 0
        call_wall     = 0
        put_base      = 0

        for item in raw:
            price    = item.strike_price
            call_oi  = item.call_options.market_data.oi if item.call_options and item.call_options.market_data else 0
            put_oi   = item.put_options.market_data.oi  if item.put_options  and item.put_options.market_data  else 0

            strikes.append({
                'price':  price,
                'callOI': call_oi,
                'putOI':  put_oi
            })

            total_call_oi += call_oi
            total_put_oi  += put_oi

            if call_oi > max_call_oi:
                max_call_oi = call_oi
                call_wall   = price
            if put_oi > max_put_oi:
                max_put_oi = put_oi
                put_base   = price

        pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0

        return jsonify({
            'pcr':      pcr,
            'callWall': call_wall,
            'putBase':  put_base,
            'expiry':   expiry_date,
            'strikes':  sorted(strikes, key=lambda x: x['price'])
        })

    except ApiException as e:
        return jsonify({'error': f'Upstox API error: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=False)
