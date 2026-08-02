from sltcore import InfoSize, bits_get, bits_set

buf = bytearray(2)
bits_set(buf, InfoSize(0, 0), InfoSize(0, 1), 1)
print(buf, buf.hex())
bits_set(buf, InfoSize(0, 1), InfoSize(0, 8), 0xA5)
print(buf, buf.hex())
print(bits_get(buf, InfoSize(0, 0), InfoSize(0, 1)).to_unsigned_int)
print(bits_get(buf, InfoSize(0, 1), InfoSize(0, 8)).to_unsigned_int)
