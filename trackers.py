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
  announceData = torrentData[b'announce']
  infoData = torrentData[b'info']
  
  return announceData, infoData

def getInfoHash(data):
    encodedInfo = encode(data)
    return hashlib.sha1(encodedInfo).digest()

def getSize(info):
    if b'length' in info:  #in case of single file
        return info[b'length']
    else:                  #in case of multiple files
        return sum(file[b'length'] for file in info[b'files'])

def parsePeers(peerBytes):
    peers = []
    for i in range(0, len(peerBytes), 6):
        ip = socket.inet_ntoa(peerBytes[i:i+4])
        port = struct.unpack(">H", peerBytes[i+4:i+6])[0]
        peers.append((ip, port))
    return peers

def getHandshakeData(filePath):
    announceUrl, info = extractTorrentData(filePath)
    peerId = b'-CC0101-' + os.urandom(12)

    infoHash = getInfoHash(info)
    left = getSize(info)
    params = {
        'info_hash': infoHash,
        'peer_id': peerId,
        'port': 6881,
        'uploaded': 0,
        'downloaded': 0,
        'left': left,
        'compact': 1
    }

    response = requests.get(announceUrl, params=params)
    trackerResponse = decode(response.content)
    peers = parsePeers(trackerResponse[b'peers'])

    return infoHash, peerId, peers

