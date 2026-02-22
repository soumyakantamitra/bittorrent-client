from bencoding import decode
from pathlib import Path

# print(decode("i20e"))


def ExtractTorrentData(filePath = r"C:\Users\Lenovo\Downloads\tears-of-steel.torrent"):
  filePathObj = Path(filePath)
  with filePathObj.open(mode='rb') as f:
      torrent_data = decode(f.read())
  announce_data = torrent_data[b'announce']
  info_data = torrent_data[b'info']
  
  return announce_data, info_data

  
