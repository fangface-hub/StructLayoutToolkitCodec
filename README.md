# StructLayoutToolkitCodec

sltcodec is a small package for decoding and encoding bytearrays according to structured layout definitions. It uses sltcore for bit-level access and provides a simple API for turning a layout definition into binary data and back again.

## Installation

```bash
pip install sltcodec
```

## Quick Example

```python
from sltcore import InfoSize
from sltcodec import FieldDef, decode, encode

field_defs = [
    FieldDef(name="flag",
             offset=InfoSize(0, 0),
             size=InfoSize(0, 1),
             type="bool"),
    FieldDef(name="value",
             offset=InfoSize(0, 1),
             size=InfoSize(1, 0),
             type="unsigned int"),
]

encoded = encode([(field_defs[0], True), (field_defs[1], 0xA5)])
decoded = decode(field_defs, encoded)

print(encoded)
print(decoded)
```

Output:

```python
bytearray(b"\xd2\x80")
[(FieldDef(name='flag', offset=InfoSize(byte=0, bit=0), size=InfoSize(byte=0, bit=1), type='bool', repeat=None), True),
 (FieldDef(name='value', offset=InfoSize(byte=0, bit=1), size=InfoSize(byte=1, bit=0), type='unsigned int', repeat=None), 165)]

```

## Development

```bash
uv sync --all-extras
uv run pytest
```
