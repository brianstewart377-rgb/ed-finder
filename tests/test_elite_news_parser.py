from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps' / 'api' / 'src'))

from routers import news
from routers.news import extract_elite_news_items


def test_extract_elite_news_items_prefers_headline_text_and_deduplicates_urls():
    html = '''
    <html>
      <body>
        <a href="/news/nomad-available-now-arx-early-access">30 June 2026</a>
        <a href="/news/nomad-available-now-arx-early-access">Nomad – Available Now Via ARX Early Access</a>
        <a href="/news/galnet/vista-genomics-seeks-exploration-data-sanguineous-rim">2 July 3312</a>
        <a href="/news/galnet/vista-genomics-seeks-exploration-data-sanguineous-rim">Vista Genomics Seeks Exploration Data From Sanguineous Rim</a>
        <a href="/news">News</a>
      </body>
    </html>
    '''

    items = extract_elite_news_items(html, limit=4)

    assert items == [
        {
            'title': 'Nomad – Available Now Via ARX Early Access',
            'url': 'https://www.elitedangerous.com/news/nomad-available-now-arx-early-access',
            'source': 'news',
        },
        {
            'title': 'Vista Genomics Seeks Exploration Data From Sanguineous Rim',
            'url': 'https://www.elitedangerous.com/news/galnet/vista-genomics-seeks-exploration-data-sanguineous-rim',
            'source': 'galnet',
        },
    ]


def test_extract_elite_news_items_accepts_locale_prefixed_news_urls():
    html = '''
    <html>
      <body>
        <a href="/en-US/news/nomad-available-now-arx-early-access">June 30, 2026</a>
        <a href="/en-US/news/nomad-available-now-arx-early-access">Nomad – Available Now Via ARX Early Access</a>
        <a href="/en-US/news/galnet/vista-genomics-seeks-exploration-data-sanguineous-rim">July 2, 3312</a>
        <a href="/en-US/news/galnet/vista-genomics-seeks-exploration-data-sanguineous-rim">Vista Genomics Seeks Exploration Data From Sanguineous Rim</a>
      </body>
    </html>
    '''

    items = extract_elite_news_items(html, limit=4)

    assert items == [
        {
            'title': 'Nomad – Available Now Via ARX Early Access',
            'url': 'https://www.elitedangerous.com/news/nomad-available-now-arx-early-access',
            'source': 'news',
        },
        {
            'title': 'Vista Genomics Seeks Exploration Data From Sanguineous Rim',
            'url': 'https://www.elitedangerous.com/news/galnet/vista-genomics-seeks-exploration-data-sanguineous-rim',
            'source': 'galnet',
        },
    ]


def test_fallback_payload_keeps_official_news_links_available():
    payload = news._fallback_payload(limit=2)

    assert payload['stale'] is True
    assert payload['source_url'] == 'https://www.elitedangerous.com/news'
    assert payload['items'] == [
        {
            'title': 'Open official Elite Dangerous news',
            'url': 'https://www.elitedangerous.com/news',
            'source': 'news',
        },
        {
            'title': 'Open official Galnet',
            'url': 'https://www.elitedangerous.com/en-US/Galnet',
            'source': 'galnet',
        },
    ]
