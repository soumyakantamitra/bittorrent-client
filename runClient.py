from downloader import runDownloader
from trackers import getHandshakeData


if __name__ == "__main__":
    #location of torrent file
    filePath = r"C:\path\to\your\file.torrent"
    infoHash, peerId, peers, totalLength, files, pieceLength, hashes = getHandshakeData(filePath)
    
    runDownloader(infoHash, peerId, peers, totalLength, files, pieceLength, hashes)