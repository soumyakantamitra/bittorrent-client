import bencodepy

bc = bencodepy.Bencode(
    encoding=None
)

def encode(value):
  return bc.encode(value)

def decode(value):
  return bc.decode(value)

