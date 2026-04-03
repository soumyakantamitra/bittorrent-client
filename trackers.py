import random
from bencoding import encode, decode
from pathlib import Path
import requests
import hashlib
import socket
import struct
import os

def extractTorrentData(filePath):
    filePathObj = Path(filePath)
    with filePathObj.open(mode='rb') as f:
      torrentData = decode(f.read()) 
    return torrentData

def getInfoHash(data):
    encodedInfo = encode(data)
    return hashlib.sha1(encodedInfo).digest()

def getSize(info):
    if b'length' in info:  #in case of single file
        return info[b'length']
    else:                  #in case of multiple files
        return sum(file[b'length'] for file in info[b'files'])

def getFiles(info):
    if b'length' in info:
        return None
    else:
        return info[b'files']

def parsePeers(peerBytes):
    peers = []
    for i in range(0, len(peerBytes), 6):
        ip = socket.inet_ntoa(peerBytes[i:i+4])
        port = struct.unpack(">H", peerBytes[i+4:i+6])[0]
        peers.append((ip, port))
    return peers

def getHttpTrackerPeers(announceUrl, infoHash, peerId, totalLength):
    params = {
        'info_hash': infoHash,
        'peer_id': peerId,
        'port': 6881,
        'uploaded': 0,
        'downloaded': 0,
        'left': totalLength,
        'compact': 1
    }

    response = requests.get(announceUrl, params=params)
    trackerResponse = decode(response.content)
    return parsePeers(trackerResponse[b'peers'])

def getUdpTrackerPeers(url, infoHash, peerId, totalLength):

    host = url.split("://")[1].split(":")[0]
    port = int(url.split(":")[2].split("/")[0])
 
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)
 
    try:
        connectionId = 0x41727101980  # magic constant required by UDP tracker protocol
        action = 0
        transactionId = random.randint(0, 0xFFFFFFFF)
 
        connectRequest = struct.pack(">QII", connectionId, action, transactionId)
        sock.sendto(connectRequest, (host, port))
 
        response = sock.recv(16)
        respAction, respTransaction, newConnectionId = struct.unpack(">IIQ", response)
 
        if respAction != 0 or respTransaction != transactionId:
            raise Exception("Invalid connect response")
 
        action = 1
        transactionId = random.randint(0, 0xFFFFFFFF)
        downloaded = 0
        left = totalLength
        uploaded = 0
        event = 0  # 0 = none, 1 = completed, 2 = started, 3 = stopped
        ip = 0
        key = random.randint(0, 0xFFFFFFFF)
        numWant = -1  # -1 = default
        listenPort = 6881
 
        announceRequest = struct.pack(
            ">QII20s20sQQQIIIiH",
            newConnectionId, action, transactionId,
            infoHash, peerId,
            downloaded, left, uploaded,
            event, ip, key, numWant, listenPort
        )
        sock.sendto(announceRequest, (host, port))
 
        response = sock.recv(4096)
        action, transactionId, interval, leechers, seeders = struct.unpack_from(">IIIII", response)
 
        peers = parsePeers(response[20:])  # peer data starts at byte 20
        return peers
 
    finally:
        sock.close()

def getHandshakeData(filePath):
    torrentData = extractTorrentData(filePath)
    announceUrl = torrentData[b'announce']
    info = torrentData[b'info']
    peerId = b'-CC0101-' + os.urandom(12)

    infoHash = getInfoHash(info)
    totalLength = getSize(info)
    files = getFiles(info)

    urlString = announceUrl.decode()
    try:
        if urlString.startswith("http"):
            peers = getHttpTrackerPeers(urlString, infoHash, peerId, totalLength)
        elif urlString.startswith("udp"):
            peers = getUdpTrackerPeers(urlString, infoHash, peerId, totalLength)
        else:
            print(f"[!] Unsupported tracker protocol, skipping: {urlString}")
    except Exception as e:
        print(f"[!] Tracker failed ({urlString}): {e}")

    if not peers:
        raise Exception("[!] Could not get peers from any tracker")

    pieceLength = info[b'piece length']
    hashes = info[b'pieces']

    return infoHash, peerId, peers, totalLength, files, pieceLength, hashes

