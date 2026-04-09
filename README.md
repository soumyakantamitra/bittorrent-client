# BitTorrent Client

A BitTorrent client written in Python from scratch. Supports downloading torrents from both HTTP and UDP trackers, multi-file torrents, download resumption, and piece verification.


## Features

- HTTP and UDP tracker support
- Multithreaded downloading with persistent peer connections
- Piece-level SHA1 verification during and after download
- Download resumption i.e., already downloaded pieces are skipped on restart
- Corrupt piece re-downloading after final verification
- Multi-file torrent reconstruction into the correct folder structure


## Project Structure

```
bencoding.py      Wrapper around bencodepy for encoding and decoding torrent data
trackers.py       Tracker communication : fetches peer lists over HTTP and UDP
peerProtocol.py   BitTorrent peer wire protocol : handshake, messages, bitfield
downloader.py     Core download engine : piece queue, worker threads, verification
```


## How It Works

### 1. Parsing the torrent file

The `.torrent` file is a bencoded dictionary containing metadata about the torrent like tracker URLs, file names, file sizes, piece length, and SHA1 hashes for every piece. `trackers.py` reads this file and extracts everything needed to start a download.

### 2. Getting peers from trackers

The client contacts trackers listed in the torrent's `announce` and `announce-list` fields to get a list of peers currently sharing the torrent. Both HTTP and UDP tracker protocols are supported. Peers from all trackers are combined into a single deduplicated pool.

**HTTP trackers** are contacted with a simple GET request containing the info hash, peer ID, and download stats.

**UDP trackers** require a two-step protocol : a connect request to obtain a connection ID, followed by an announce request using that connection ID to get the peer list.

### 3. Peer handshake

For each peer, a TCP connection is established and a BitTorrent handshake is performed. The handshake verifies that the peer is sharing the same torrent by comparing info hashes. After a successful handshake, the peer sends a bitfield indicating which pieces it has available.

### 4. Downloading pieces

Pieces are distributed across worker threads via a queue. Each thread connects to peers and downloads pieces that the peer has available. A piece is not downloaded as one unit, it is broken into 16KB blocks (the standard followed by the BitTorrent protocol) and requested sequentially with pipelining.

Once all blocks of a piece are received, the piece is verified against its SHA1 hash from the torrent file. If verification passes, the piece is written to disk. If it fails, the piece is returned to the queue to be retried with a different peer.

Each thread maintains a persistent connection to a peer and keeps downloading pieces from it as long as the peer is responsive, avoiding the overhead of repeated handshakes.

### 5. Verification

After all pieces are downloaded, the entire file is verified piece by piece. Any corrupt pieces are re-downloaded from the peer list before the final output is written.

### 6. File reconstruction

For multi-file torrents, all pieces are downloaded into a single contiguous blob on disk. After verification, the blob is split into individual files according to the file list in the torrent metadata, recreating the original folder structure. The blob is deleted after reconstruction is complete.



## Requirements

```
pip install -r requirements.txt
```


## Usage

Set the `filePath` variable at the bottom of `downloader.py` to the path of your `.torrent` file:

```python
if __name__ == "__main__":
    filePath = r"C:\path\to\your\file.torrent"
    infoHash, peerId, peers, totalLen, files, pieceLen, hashes = getHandshakeData(filePath)
    runDownloader(infoHash, peerId, peers, totalLen, files, pieceLen, hashes)
```

Then run:

```
python downloader.py
```

Downloaded files will appear in the newly created `downloads/` directory inside your current directory.


## Configuration

These constants at the top of `downloader.py` can be adjusted:

| Constant | Default | Description |
|---|---|---|
| `BLOCK_SIZE` | 16384 | Block size in bytes. Recommended by the BitTorrent protocol, do not change. |
| `MAX_REQUESTS` | 20 | Maximum number of block requests pipelined to a peer at once. |
| `NUM_THREADS` | 10 | Number of parallel download threads. Increasing may or may not improve download speed. |
|


## BitTorrent Protocol Overview

A piece is the unit of verification. Every piece has a fixed size (defined by the torrent creator, typically 256KB to 4MB) except the last piece which is whatever size remains. Each piece's SHA1 hash is stored in the torrent file and used to verify the downloaded data.

A block is the unit of transfer. Peers will reject requests larger than 16KB, so every piece is downloaded by requesting multiple 16KB blocks and assembling them.

A bitfield is a compact binary representation of which pieces a peer has. Each bit corresponds to one piece where 1 means the peer has it, 0 means it does not.

The choke/unchoke mechanism controls upload bandwidth on the peer's side. A peer will not send data until it has unchoked you. Sending an Interested message signals that you want data, after which the peer may unchoke you.

For detailed information on the BitTorrent protocol specifications, refer to [BEP 0003](https://www.bittorrent.org/beps/bep_0003.html).