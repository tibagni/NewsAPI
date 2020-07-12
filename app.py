import os
import requests
import json

from flask import Flask
from flask import request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

CACHE_TTL = 3 * 60 * 60

# Set PYTHONHASHSEED so strings have the same hash every time
os.environ['PYTHONHASHSEED'] = '0'

class Config(object):
    def __init__(self):
        self._defaults = {}
        if os.path.isfile("default_env.json"):
            with open("default_env.json") as f:
                self._defaults = json.loads(f.read())

        self.DEBUG = os.getenv('DEBUG', self._get_default('DEBUG')) == "True"
        self.DATABASE_URL = os.getenv(
            'DATABASE_URL', self._get_default('DATABASE_URL'))
        self.GNEWS_TOKEN = os.getenv(
            'GNEWS_TOKEN', self._get_default('GNEWS_TOKEN'))
        self.SQLALCHEMY_DATABASE_URI = self.DATABASE_URL

    def _get_default(self, key):
        return self._defaults[key] if key in self._defaults else None


app = Flask(__name__)
app.config.from_object(Config())
db = SQLAlchemy(app)


class NewsCache(db.Model):
    kw_hash = db.Column(db.BigInteger, primary_key=True)
    response_json = db.Column(db.String)
    updated_at = db.Column(db.DateTime)

    def __repr__(self):
        return f"kw_hash={self.kw_hash}, response_json={self.response_json}, updated_at={self.updated_at}"


def _fetch_news(keywords):
    print(f"Fetching news from API. kw {keywords}")
    token = app.config['GNEWS_TOKEN']
    url = f"https://gnews.io/api/v3/search?q={keywords}&token={token}"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()


def _get_cached_news(keywords):
    kw_hash = hash(keywords)
    print(f"Searching cache. kw: {keywords}. hash: {kw_hash}")

    cached_news = NewsCache.query.get(kw_hash)

    if cached_news:
        print("Cache HIT")
        now = datetime.now()
        cached_at = cached_news.updated_at
        time_since_cached = now - cached_at
        if time_since_cached.seconds > CACHE_TTL:
            print("... But it is too old. Invalidating...")
            # Invalidate the cache if its been too long
            db.session.delete(cached_news)
            db.session.commit()
            return None
        return cached_news.response_json

    print("Cache MISS")
    return None


def _add_to_cache(keywords, response_json):
    kw_hash = hash(keywords)
    print(f"Adding to cache. kw: {keywords}. hash: {kw_hash}")
    c = NewsCache(kw_hash=kw_hash,
                  response_json=json.dumps(response_json), updated_at=datetime.now())

    db.session.add(c)
    db.session.commit()

##### APIS #################################


@app.route("/api/news", methods=['GET'])
def get_news():
    keywords = request.args.get('keywords')
    news = _get_cached_news(keywords)
    if not news:
        news = _fetch_news(keywords)
        _add_to_cache(keywords, news)

    return news


if __name__ == "__main__":
    app.run(debug=True)