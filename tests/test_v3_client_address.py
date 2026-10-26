"""Rate limits key on the visitor, not on the proxy hop (2026-10-26 sweep S1).

Production confirmed the problem: every one of 903 API requests in 24 hours
came from the web slot's address, so each limit was one bucket for the whole
site. The edge now trusts Cloudflare's CF-Connecting-IP only from Cloudflare's
published ranges, and every limit keys on the X-Real-IP the edge sets.
"""
from __future__ import annotations

import ipaddress
import os
import re
import sys
from pathlib import Path

import pytest
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')

from edfinder_api import config  # noqa: E402
from edfinder_api.routers import auth as auth_router  # noqa: E402

EDGE = ROOT / 'deploy' / 'v3-production' / 'public-auth-edge.nginx.conf'

# https://www.cloudflare.com/ips/ (last updated there 2023-09-28; checked 2026-10-26).
CLOUDFLARE = {
    '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '104.16.0.0/13', '104.24.0.0/14',
    '108.162.192.0/18', '131.0.72.0/22', '141.101.64.0/18', '162.158.0.0/15', '172.64.0.0/13',
    '173.245.48.0/20', '188.114.96.0/20', '190.93.240.0/20', '197.234.240.0/22', '198.41.128.0/17',
    '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32', '2405:8100::/32',
    '2a06:98c0::/29', '2c0f:f248::/32',
}


def _request(peer: str, real_ip: str = '') -> Request:
    headers = [(b'host', b'ed-finder.app')]
    if real_ip:
        headers.append((b'x-real-ip', real_ip.encode('latin-1')))
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'query_string': b'',
                    'headers': headers, 'client': (peer, 50000), 'server': ('ed-finder.app', 80),
                    'scheme': 'http'})


@pytest.mark.parametrize('peer,real_ip,expected', [
    ('172.23.0.2', '203.0.113.42', '203.0.113.42'),    # web slot relaying the edge's visitor
    ('172.23.0.2', '2001:db8::7', '2001:db8::7'),
    ('172.23.0.2', '', '172.23.0.2'),                  # nothing forwarded: the peer
    ('172.23.0.2', 'not-an-ip', '172.23.0.2'),         # garbage is never a key
    ('127.0.0.1', '203.0.113.42', '127.0.0.1'),        # loopback may not choose a key
    ('93.184.215.14', '203.0.113.42', '93.184.215.14'),  # public direct caller may not either
])
def test_trusted_client_address(peer, real_ip, expected):
    assert config.trusted_client_address(_request(peer, real_ip)) == expected


def test_every_rate_limit_uses_the_trusted_key():
    assert config.limiter._key_func is config.trusted_client_address
    assert auth_router._oauth_client_address is config.trusted_client_address
    source = '\n'.join(path.read_text(encoding='utf-8') for path in API_SRC.rglob('*.py'))
    assert 'get_remote_address' not in source


def test_edge_trusts_cloudflare_visitor_header_only_from_cloudflare():
    config_text = re.sub(r'#[^\n]*', '', EDGE.read_text(encoding='utf-8'))
    http_block = config_text[config_text.index('http {'):config_text.index('server {')]
    trusted = set(re.findall(r'^\s*set_real_ip_from ([0-9a-f.:/]+);$', http_block, re.M))
    assert trusted == CLOUDFLARE
    for network in trusted:
        assert not ipaddress.ip_network(network).is_private
    assert re.search(r'^\s*real_ip_header CF-Connecting-IP;$', http_block, re.M)
    # CF-Connecting-IP is a single address; recursion would let a client append its own.
    assert 'real_ip_recursive' not in config_text
    # Every proxied location overwrites X-Real-IP with the (now visitor) address.
    locations = re.findall(r'location [^{]+\{[^}]*proxy_pass[^}]*\}', config_text)
    assert locations
    for block in locations:
        assert 'proxy_set_header X-Real-IP $remote_addr;' in block, block
