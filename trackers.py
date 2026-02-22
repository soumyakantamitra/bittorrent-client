from extractTorrentData import ExtractTorrentData

import requests
import urllib.parse
import hashlib
import socket
import struct
import os

# ---- Values you must already have ----
announce_url, info = ExtractTorrentData()
# announce_url = "http://tracker.example.com:6969/announce"
# info_hash = b'\x12\x34\x56...'   # 20 byte SHA1 digest (raw bytes!)
# file_length = 300224677          # from torrent info dictionary

# ---- Generate peer_id (20 bytes total) ----
peer_id = b'-CC0101-' + os.urandom(12)

if b'length' in info:  # single file
    left = info[b'length']
else:  # multiple files
    left = sum(f[b'length'] for f in info[b'files'])

# print(left)
print(info)

params = {
    'info_hash': info,
    'peer_id': peer_id,
    'port': 6881,
    'uploaded': 0,
    'downloaded': 0,
    'left': 0,
    'compact': 1
}

# response = requests.get(announce_url, params=params)

# print("Status:", response.status_code)