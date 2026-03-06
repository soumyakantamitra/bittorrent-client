import socket
import struct
from trackers import getHandshakeData

filePath = r"C:\Users\Lenovo\Downloads\Fedora-Budgie-Live-x86_64-43.torrent"

def receive(sock, length):
    data = b''
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            # Peer closed the connection
            return None
        data += chunk
    return data

def sendMessage(sock, messageId, payload = b''):
    length = len(payload) + 1
    message = struct.pack(">IB", length, messageId) + payload
    sock.sendall(message)

def getMessage(sock):
    response = receive(sock, 4)
    
    if not response:
        return "closed", None
    
    length = struct.unpack(">I", response)[0]

    #Keep-Alive (if length = 0)
    if length == 0:
        return "keep-alive", None
    
    #ID + Payload
    body = receive(sock, length)
    if not body:
        return "closed", None
    
    messageId = body[0]
    payload = body[1:]

    return messageId, payload

def has_piece(bitfield, piece_index):
    byte_idx = piece_index // 8
    bit_offset = 7 - (piece_index % 8)
    if byte_idx >= len(bitfield):
        return False
    return (bitfield[byte_idx] >> bit_offset) & 1

def handlePeer(sock):
    bitfield = None
    unchoked = False
    
    try:
        messageId, payload = getMessage(sock)
        
        if messageId == 5:
            bitfield = payload
            print(f"  [+] Received Bitfield ({len(bitfield)} bytes).")
        elif messageId == 1:
            unchoked = True
        
        print("  [>] Sending 'Interested'...")
        sendMessage(sock, 2)
        
        while not unchoked:
            messageId, payload = getMessage(sock)
            
            if messageId == "closed":
                print("  [!] Peer closed connection during negotiation.")
                return None
            elif messageId == 1:
                print("  [!] SUCCESS: Peer has Unchoked us!")
                unchoked = True
            elif messageId == 0:
                print("  [!] Peer Choked us. Waiting...")
            elif messageId == "keep-alive":
                continue
            else:
                print(f"Received other message ID: {messageId}, waiting for Unchoke..")
                pass
                
        return bitfield

    except Exception as e:
        print(f"  [!] Protocol error: {e}")
        return None

def handshake(infoHash, peerId, peerIp, peerPort):
    protocolString = b"BitTorrent protocol"
    protocolStringLength = bytes([len(protocolString)])
    reserved = b'\x00' * 8

    handshakeMsg = protocolStringLength + protocolString + reserved + infoHash + peerId

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(25)

    try:
        print(f"Connecting to {peerIp}:{peerPort}...")
        sock.connect((peerIp, peerPort))
        
        sock.sendall(handshakeMsg)
        
        response = receive(sock, 68)

        #Receive the Peer's Handshake (Exactly 68 bytes back is expected)
        if not response or len(response) < 68:
            print("Error: Incomplete handshake received.")
            sock.close()
            return None

        # recvPeerStrLen = response[0]
        # recvPeerStr = response[1:20]
        recvInfoHash = response[28:48]
        # recvPeerId = response[48:68]

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
    sock = handshake(infoHash, peerId, ip, port)
    
    if sock:
        peer_bitfield = handlePeer(sock)
            
        if peer_bitfield: #Testing
            if has_piece(peer_bitfield, 0):
                print("Peer has Piece #0. Ready to request blocks!")
            else:
                print("[*] Peer does not have Piece #0.")
            
        print("[!] Closing connection.")
        sock.close()