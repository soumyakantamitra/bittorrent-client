import bencodepy

bc = bencodepy.Bencode(
    encoding=None
)

def encode(value):
  return bc.encode(value)

def decode(value):
  return bc.decode(value)


# print(bc.encode("abd"))
# print(bc.decode("i20e"))
# print(bencodepy.decode('d5:title7:Examplee'))
# print(bc.decode('d5:title7:Examplee'))