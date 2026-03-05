import socket
from trackers import getHandshakeData

filePath = r"C:\Users\Lenovo\Downloads\Fedora-Budgie-Live-x86_64-43.torrent"

def handshake(infoHash, peerId, peerIp, peerPort):

    protocolString = b"BitTorrent protocol"
    protocolStringLength = bytes([len(protocolString)])
    reserved = b'\x00' * 8

    handshakeMsg = protocolStringLength + protocolString + reserved + infoHash + peerId

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)

    try:
        print(f"Connecting to {peerIp}:{peerPort}...")
        sock.connect((peerIp, peerPort))
        
        sock.sendall(handshakeMsg)
        
        response = b''
        while len(response) < 68:
            chunk = sock.recv(68 - len(response))
            if not chunk:
                # If chunk is empty, the remote side closed the connection
                break
            response += chunk

        #Receive the Peer's Handshake (Exactly 68 bytes back is expected)
        if len(response) < 68:
            print("Error: Incomplete handshake received.")
            sock.close()
            return None

        recvPeerStrLen = response[0]
        recvPeerStr = response[1:20]
        recvInfoHash = response[28:48]
        recvPeerId = response[48:68]

        if recvInfoHash != infoHash:
            print("Error: Info hash mismatch! They are sharing a different torrent.")
            sock.close()
            return None
            
        print(f"Handshake successful! Connected to peer: {peerId}")
        return sock
        
    except (socket.timeout, ConnectionRefusedError, socket.error) as e:
        print(f"Failed to connect to {peerIp}: {e}")
        return None


infoHash, peerId, peers = getHandshakeData(filePath)

for i, (ip, port) in enumerate(peers):
  print(f"Peer {i} is ip: {ip} port: {port}")
  handshake(infoHash, peerId, ip, port)