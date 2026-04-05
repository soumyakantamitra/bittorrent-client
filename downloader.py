import random
import struct
import hashlib
import os
import threading
import time
from queue import Empty, Queue
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
            
        elif messageId == "closed":
            print("\n  [!] Connection lost.")
            return None
        elif messageId == "keep-alive":
            continue
        else:
            continue

    return pieceData

def verifyPiece(pieceData, pieceIndex, pieceHashes):
    # Each hash in the 'pieces' string is exactly 20 bytes long
    start = pieceIndex * 20
    end = start + 20
    expectedHash = pieceHashes[start:end]
    
    actualHash = hashlib.sha1(pieceData).digest()
    return actualHash == expectedHash

def verifyDownload(outputFile, totalLength, pieceLength, pieceHashes):
    totalPieces = (totalLength + pieceLength - 1) // pieceLength
    failedPieces = []

    print(f"[*] Verifying {totalPieces} pieces...")

    for pieceIndex in range(totalPieces):
        currentPieceSize = pieceLength
        if pieceIndex == totalPieces - 1:
            currentPieceSize = totalLength - (pieceIndex * pieceLength)

        with open(outputFile, "rb") as f:
            f.seek(pieceIndex * pieceLength)
            data = f.read(currentPieceSize)

        if not verifyPiece(data, pieceIndex, pieceHashes):
            failedPieces.append(pieceIndex)

        # Progress
        progress = ((pieceIndex + 1) / totalPieces) * 100
        print(f"\r[*] Verifying... {progress:.1f}%", end='', flush=True)

    print()
    if not failedPieces:
        print("[+] Verification passed! All pieces are correct.")
    else:
        print(f"[!] Verification FAILED! {len(failedPieces)} corrupt pieces: {failedPieces}")

    return failedPieces

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

def progressMonitor(totalPieces, pieceLength):
    global completed_pieces
    lastCount = completed_pieces
    startTime = time.time()

    while True:
        time.sleep(1)
        
        with counter_lock:
            currentCount = completed_pieces
        
        # Speed
        piecesInLastSecond = currentCount - lastCount
        speed = (piecesInLastSecond * pieceLength) / (1024 * 1024)
        
        
        elapsedTime = time.time() - startTime
        downloadedMbs = (currentCount * pieceLength) / (1024 * 1024)
        avgSpeed = downloadedMbs / elapsedTime if elapsedTime > 0 else 0
        
        progress = (currentCount / totalPieces) * 100
        remainingPieces = totalPieces - currentCount
        
        # ETA
        if avgSpeed > 0:
            remainingSeconds = (remainingPieces * pieceLength) / (avgSpeed * 1024 * 1024)
            eta = time.strftime("%H:%M:%S", time.gmtime(remainingSeconds))
        else:
            eta = "Calculating..."

        
        print(f"\r[*] {progress:.2f}% | {currentCount}/{totalPieces} pcs | {speed:.2f} MB/s | ETA: {eta}    ", end='', flush=True)
        
        lastCount = currentCount
        
        if currentCount >= totalPieces:
            print(f"\n\n--- Download Summary ---")
            print(f"Total Time: {time.strftime('%M:%S', time.gmtime(elapsedTime))}")
            print(f"Average Speed: {avgSpeed:.2f} MB/s")
            break

def reconstructFiles(outputFile, files, baseDir="downloads"):
    # Single file torrent — nothing to reconstruct
    if files is None:
        return

    print("[*] Reconstructing file structure...")
    offset = 0

    for fileInfo in files:
        fileLength = fileInfo[b'length']
        filePath = os.path.join(baseDir, *[p.decode() for p in fileInfo[b'path']])

        os.makedirs(os.path.dirname(filePath), exist_ok=True)

        print(f"[+] Writing {filePath} ({fileLength} bytes)...")
        with open(outputFile, "rb") as src:
            src.seek(offset)
            with open(filePath, "wb") as dst:
                remaining = fileLength
                while remaining > 0:
                    chunk = src.read(min(1024 * 1024, remaining))  # 1MB at a time
                    dst.write(chunk)
                    remaining -= len(chunk)

        offset += fileLength
    
    os.remove(outputFile)

    print("[+] File reconstruction complete.")

def reDownloadCorruptPieces(failedPieces, infoHash, peerId, peers, totalLength, pieceLength, pieceHashes, outputFile):
    global completed_pieces
    totalPieces = (totalLength + pieceLength - 1) // pieceLength

    print(f"[!] Re-downloading {len(failedPieces)} corrupt pieces...")

    for ip, port in peers:
        if not failedPieces:
            break
        try:
            sock = handshake(infoHash, peerId, ip, port)
            if not sock:
                continue

            sock.settimeout(5.0)
            bitfield = handlePeer(sock)
            if not bitfield:
                sock.close()
                continue

            stillFailed = []
            for pieceIndex in failedPieces:
                if not hasPiece(bitfield, pieceIndex):
                    stillFailed.append(pieceIndex)
                    continue

                currentPieceSize = pieceLength
                if pieceIndex == totalPieces - 1:
                    currentPieceSize = totalLength - (pieceIndex * pieceLength)

                data = downloadPiece(sock, pieceIndex, currentPieceSize)
                if data and verifyPiece(data, pieceIndex, pieceHashes):
                    with open(outputFile, "rb+") as f:
                        f.seek(pieceIndex * pieceLength)
                        f.write(data)
                    print(f"[+] Re-downloaded piece {pieceIndex} successfully.")
                else:
                    stillFailed.append(pieceIndex)

            failedPieces = stillFailed
            sock.close()

        except Exception:
            continue

    if failedPieces:
        print(f"[!] Still corrupt after re-download: {failedPieces}")
    else:
        print("[+] All corrupt pieces fixed!")

def pieceWorker(pieceQueue, infoHash, peerId, peers, totalLength, pieceLength, pieceHashes, outputFile):
    global completed_pieces
    totalPieces = (totalLength + pieceLength - 1) // pieceLength
 
    while True:
        with counter_lock:
            if completed_pieces >= totalPieces:
                return
 
        for ip, port in peers:
            with counter_lock:
                if completed_pieces >= totalPieces:
                    return
                
            try:
                pieceIndex = pieceQueue.get(timeout=3)
            except Empty:
                with counter_lock:
                    if completed_pieces >= totalPieces:
                        return
                continue

            currentPieceSize = pieceLength
            if pieceIndex == totalPieces - 1:
                currentPieceSize = totalLength - (pieceIndex * pieceLength)
 
            if isPieceAlreadyDownloaded(pieceIndex, pieceLength, totalLength, pieceHashes, outputFile):
                with counter_lock:
                    completed_pieces += 1
                pieceQueue.task_done()
                continue
 
            try:
                sock = handshake(infoHash, peerId, ip, port)
                if not sock:
                    pieceQueue.put(pieceIndex)
                    continue

                sock.settimeout(5.0)
                bitfield = handlePeer(sock)

                if not bitfield:
                    sock.close()
                    pieceQueue.put(pieceIndex)
                    continue

                currentPiece = pieceIndex
                while True:
                    if not hasPiece(bitfield, currentPiece):
                        pieceQueue.put(currentPiece)
                        try:
                            currentPiece = pieceQueue.get(timeout=3)
                        except Empty:
                            break
                        continue

                    currentPieceSize = pieceLength
                    if currentPiece == totalPieces - 1:
                        currentPieceSize = totalLength - (currentPiece * pieceLength)

                    data = downloadPiece(sock, currentPiece, currentPieceSize)

                    if data and verifyPiece(data, currentPiece, pieceHashes):
                        with open(outputFile, "rb+") as f:
                            f.seek(currentPiece * pieceLength)
                            f.write(data)
                        with counter_lock:
                            completed_pieces += 1
                        pieceQueue.task_done()

                        try:
                            currentPiece = pieceQueue.get(timeout=3)
                        except Empty:
                            break
                    else:
                        # Download failed, return piece
                        pieceQueue.put(currentPiece)
                        break

                sock.close()

            except Exception:
                pieceQueue.put(pieceIndex)
                continue
 
        else:
            time.sleep(5)

def runDownloader(infoHash, peerId, peers, totalLength, files, pieceLength, pieceHashes):
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
        shuffledPeerList = list(peers)
        random.shuffle(shuffledPeerList)
        t = threading.Thread(target=pieceWorker, args=(pieceQueue, infoHash, peerId, shuffledPeerList, totalLength, pieceLength, pieceHashes, outputFile))
        t.daemon = True
        t.start()
        time.sleep(0.2)

    monitor = threading.Thread(target=progressMonitor, args=(totalPieces, pieceLength))
    monitor.daemon = True
    monitor.start()

    # To stop the script with Keyboard Interrupt
    try:
        while True:
            if completed_pieces >= totalPieces:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[!] User interrupted the download. Progress saved.")
        return
    
    monitor.join()

    print("[!] All downloads finished.")

    failedPieces = verifyDownload(outputFile, totalLength, pieceLength, pieceHashes)
    
    # Redownload any corrupt pieces
    if failedPieces:
        reDownloadCorruptPieces(failedPieces, infoHash, peerId, peers, totalLength, pieceLength, pieceHashes, outputFile)
        verifyDownload(outputFile, totalLength, pieceLength, pieceHashes)
    
    reconstructFiles(outputFile, files)

if __name__ == "__main__":
    #location of torrent file
    filePath = r"C:\Users\Lenovo\Downloads\Fedora-Budgie-Live-x86_64-43.torrent"
    infoHash, peerId, peers, totalLen, files, pieceLen, hashes = getHandshakeData(filePath)
    
    runDownloader(infoHash, peerId, peers, totalLen, files, pieceLen, hashes)