import struct
import hashlib
import os
import threading
from queue import Queue
from peerProtocol import handshake, handlePeer, sendMessage, getMessage, hasPiece
from trackers import getHandshakeData

BLOCK_SIZE = 16384  # 16KB is the standard for BitTorrent blocks
MAX_REQUESTS = 20
NUM_THREADS = 10

completed_pieces = 0
counter_lock = threading.Lock()

# Sends a Request (ID 6) message.
def requestBlock(sock, pieceIndex, begin, length):
    
    payload = struct.pack(">III", pieceIndex, begin, length)
    sendMessage(sock, 6, payload)

# Downloads pieces by requesting them in 16KB blocks.
def downloadPiece(sock, pieceIndex, pieceSize):   
    pieceData = bytearray(pieceSize)
    downloadedBytes = 0
    requestedBytes = 0

    print(f"[*] Downloading Piece #{pieceIndex} ({pieceSize} bytes)...")

    while downloadedBytes < pieceSize:

        while requestedBytes < pieceSize and (requestedBytes - downloadedBytes) < MAX_REQUESTS * BLOCK_SIZE:

            currentBlockSize = min(BLOCK_SIZE, pieceSize - requestedBytes)
            
            requestBlock(sock, pieceIndex, requestedBytes, currentBlockSize)
            requestedBytes += currentBlockSize

        messageId, payload = getMessage(sock)

        if messageId == 7: # Piece (ID 7) Message
            index, begin = struct.unpack_from(">II", payload)
            blockData = payload[8:]
            
            pieceData[begin:begin + len(blockData)] = blockData
            downloadedBytes += len(blockData)
            
            # Progress bar
            # percent = (downloadedBytes / pieceSize) * 100
            # print(f" [+] Progress: {percent:.1f}%", end='\r')
            
        elif messageId == "closed":
            print("\n  [!] Connection lost.")
            return None
        elif messageId == "keep-alive":
            continue
        else:
            # Ignore other messages
            continue

    print(f"\n  [!] Piece #{pieceIndex} download finished.")
    return pieceData

def verifyPiece(pieceData, pieceIndex, pieceHashes):
    # Each hash in the 'pieces' string is exactly 20 bytes long
    start = pieceIndex * 20
    end = start + 20
    expectedHash = pieceHashes[start:end]
    
    actualHash = hashlib.sha1(pieceData).digest()
    return actualHash == expectedHash

def isPieceAlreadyDownloaded(pieceIndex, pieceLength, totalLength, pieceHashes, filePath):
    if not os.path.exists(filePath):
        return False

    # Calculate size of this piece
    currentPieceSize = pieceLength
    totalPieces = (totalLength + pieceLength - 1) // pieceLength
    if pieceIndex == totalPieces - 1:
        currentPieceSize = totalLength - (pieceIndex * pieceLength)

    try:
        with open(filePath, "rb") as f:
            # Jump to the start of the piece
            f.seek(pieceIndex * pieceLength)

            data = f.read(currentPieceSize)
            
            if len(data) != currentPieceSize:
                return False
                
            return verifyPiece(data, pieceIndex, pieceHashes)
    except Exception:
        return False

def pieceWorker(pieceQueue, infoHash, peerId, peers, totalLength, pieceLength, pieceHashes, outputFile):
    global completed_pieces
    totalPieces = (totalLength + pieceLength - 1) // pieceLength

    # Find a Peer
    for ip, port in peers:
        try:
            sock = handshake(infoHash, peerId, ip, port)

            if not sock:
                continue

            sock.settimeout(10.0)
            bitfield = handlePeer(sock)

            # Skip absent pieces
            if not bitfield:
                sock.close()
                continue

            while not pieceQueue.empty():
                pieceIndex = pieceQueue.get()

                if not hasPiece(bitfield, pieceIndex):
                    pieceQueue.put(pieceIndex) # Return it, this peer doesn't have it
                    break

                currentPieceSize = pieceLength
                if pieceIndex == totalPieces - 1:
                    #in case of last piece
                    currentPieceSize = totalLength - (pieceIndex * pieceLength)

                # Download and verify
                data = downloadPiece(sock, pieceIndex, currentPieceSize)
                if data and verifyPiece(data, pieceIndex, pieceHashes):
                    with open(outputFile, "rb+") as f:
                        f.seek(pieceIndex * pieceLength)
                        f.write(data)
                    
                    with counter_lock:
                        completed_pieces += 1
                        progress = (completed_pieces / totalPieces) * 100
                        print(f"\r[*] PROGRESS: {progress:.2f}% | Pieces: {completed_pieces}/{totalPieces}   ", end='', flush=True)
                    
                    pieceQueue.task_done()
                else:
                    pieceQueue.put(pieceIndex) # Failed download, return it
                    break
            sock.close()

        except Exception:
            continue


def runDownloader(infoHash, peerId, peers, totalLength, pieceLength, pieceHashes):
    global completed_pieces

    outputFile = r"downloads\downloaded_file.iso"
    totalPieces = (totalLength + pieceLength - 1) // pieceLength
    print(f"[*] Total pieces to download: {totalPieces}")

    # Pre-allocate the file on disk
    print(f"[*] Pre-allocating {totalLength} bytes for {outputFile}...")
    if not os.path.exists("downloads"): os.makedirs("downloads")
    if not os.path.exists(outputFile):
        with open(outputFile, "wb") as f:
            f.seek(totalLength - 1)
            f.write(b"\0")
    
    pieceQueue = Queue()
    for pieceIndex in range(totalPieces):
        if isPieceAlreadyDownloaded(pieceIndex, pieceLength, totalLength, pieceHashes, outputFile):
            completed_pieces += 1
        else:
            pieceQueue.put(pieceIndex)

    print(f"[*] Starting {NUM_THREADS} threads. Already have {completed_pieces} pieces.")
    
    for _ in range(NUM_THREADS):
        t = threading.Thread(target=pieceWorker, args=(pieceQueue, infoHash, peerId, peers, totalLength, pieceLength, pieceHashes, outputFile))
        t.daemon = True
        t.start()

    pieceQueue.join()
    print("[!] All downloads finished.")


if __name__ == "__main__":
    filePath = r"C:\Users\Lenovo\Downloads\Fedora-Budgie-Live-x86_64-43.torrent"
    infoHash, peerId, peers, totalLen, pieceLen, hashes = getHandshakeData(filePath)
    
    runDownloader(infoHash, peerId, peers, totalLen, pieceLen, hashes)