from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime
import os

app = Flask(__name__, static_folder='.')
CORS(app)

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
client = MongoClient(MONGO_URI)
db = client['gamepoint']
saves = db['saves']

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/save', methods=['POST'])
def save_game():
    data = request.get_json()
    data['savedAt'] = datetime.utcnow().isoformat()
    saves.replace_one({'slot': 'default'}, {'slot': 'default', **data}, upsert=True)
    return jsonify({'ok': True})

@app.route('/api/load', methods=['GET'])
def load_game():
    doc = saves.find_one({'slot': 'default'}, {'_id': 0, 'slot': 0})
    if not doc:
        return jsonify({'ok': False, 'msg': 'Aucune sauvegarde'})
    return jsonify({'ok': True, 'data': doc})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
