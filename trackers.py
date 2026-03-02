from extractTorrentData import ExtractTorrentData
from bencoding import encode, decode
import requests
import urllib.parse
import hashlib
import socket
import struct
import os

filePath = r"C:\Users\Lenovo\Downloads\Fedora-Budgie-Live-x86_64-43.torrent"

def get_info_hash(data):
    encoded_info = encode(data)
    return hashlib.sha1(encoded_info).digest()

def get_size(info):
    if b'length' in info:  #in case of single file
        return info[b'length']
    else:                  #in case of multiple files
        return sum(file[b'length'] for file in info[b'files'])

def parse_peers(peer_bytes):
    peers = []
    for i in range(0, len(peer_bytes), 6):
        ip = socket.inet_ntoa(peer_bytes[i:i+4])
        port = struct.unpack(">H", peer_bytes[i+4:i+6])[0]
        peers.append((ip, port))
    return peers


announce_url, info = ExtractTorrentData(filePath)

peer_id = b'-CC0101-' + os.urandom(12)

info_hash = get_info_hash(info)
left = get_size(info)
params = {
    'info_hash': info_hash,
    'peer_id': peer_id,
    'port': 6881,
    'uploaded': 0,
    'downloaded': 0,
    'left': left,
    'compact': 1
}

response = requests.get(announce_url, params=params)

tracker_response = decode(response.content)

peers = parse_peers(tracker_response[b'peers'])

if __name__ == "__main__":
    print(left)
    print(announce_url)
    print("Status:", response.status_code, response.reason)
    print(response.url)
    print(tracker_response)
    print("Got", len(peers), "Peers")
    for i, (ip, port) in enumerate(peers):
        print(f"Peer {i} is ip: {ip} port: {port}")