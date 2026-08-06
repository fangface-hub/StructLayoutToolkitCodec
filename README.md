# StructLayoutToolkitCodec

sltcodec is a small package for decoding and encoding bytearrays according to structured layout definitions. It uses sltcore for bit-level access and provides a simple API for turning a layout definition into binary data and back again.

## Installation

```bash
pip install sltcodec
```

## Quick Example

`FieldDef.description` is an optional human-readable note that can be attached to each field definition.

```python
from sltcore import InfoSize
from sltcodec import FieldDef, decode, encode

struct_def = [
    FieldDef(name="flag",
             offset=InfoSize(0, 0),
             size=InfoSize(0, 1),
             type="bool",
             scale=1.0,
             description="Whether the feature is enabled"),
    FieldDef(name="value",
             offset=InfoSize(0, 1),
             size=InfoSize(1, 0),
             type="unsigned int",
             scale=1.0,
             description="The encoded numeric payload"),
]

encoded = encode([(struct_def[0], True), (struct_def[1], 0xA5)])
decoded = decode(struct_def, encoded)

print(encoded)
print(decoded)
```

Output:

```python
bytearray(b"\xd2\x80")
[(FieldDef(name='flag', offset=InfoSize(byte=0, bit=0), size=InfoSize(byte=0, bit=1), type='bool', scale=1.0, repeat=None), True),
 (FieldDef(name='value', offset=InfoSize(byte=0, bit=1), size=InfoSize(byte=1, bit=0), type='unsigned int', scale=1.0, repeat=None), 165)]

```

## Nested Field Types

`FieldDef.type` can be a `StructDef`, not only a primitive type name.
This allows you to define an inline nested structure and keep `encode_field` / `decode_field` behavior symmetrical.

```python
from sltcore import InfoSize
from sltcodec import FieldDef, StructDef, decode, encode

child_struct_def = [
    FieldDef(name="left", offset=InfoSize(0, 0), size=InfoSize(1, 0), type="unsigned int"),
    FieldDef(name="right", offset=InfoSize(1, 0), size=InfoSize(1, 0), type="unsigned int"),
]

parent_field_def = FieldDef(
    name="pair",
    offset=InfoSize(0, 0),
    size=InfoSize(2, 0),
    type=StructDef(
        name="Pair",
        description="Two adjacent unsigned ints",
        fields=child_struct_def,
    ),
)

encoded = encode([
    (
        parent_field_def,
        [
            (child_struct_def[0], 3),
            (child_struct_def[1], 4),
        ],
    )
])

decoded = decode([parent_field_def], encoded)
print(encoded)
print(decoded)
```

Output:

```python
bytearray(b"\x03\x04")
[(FieldDef(name='pair', offset=InfoSize(byte=0, bit=0), size=InfoSize(byte=2, bit=0), type=[...], scale=1.0, repeat=None),
  [(FieldDef(name='left', offset=InfoSize(byte=0, bit=0), size=InfoSize(byte=1, bit=0), type='unsigned int', scale=1.0, repeat=None), 3),
   (FieldDef(name='right', offset=InfoSize(byte=1, bit=0), size=InfoSize(byte=1, bit=0), type='unsigned int', scale=1.0, repeat=None), 4)])]
```

## Expression-Based Type Selection

`FieldDef.type` can also be an expression string.
The expression is evaluated with previously processed field values in scope, so you can switch decoding/encoding type dynamically.

```python
from sltcore import InfoSize
from sltcodec import FieldDef, decode, encode

struct_def = [
    FieldDef(name="kind", offset=InfoSize(0, 0), size=InfoSize(1, 0), type="unsigned int"),
    FieldDef(
        name="payload",
        offset=InfoSize(1, 0),
        size="{1: 1, 2: 4}[kind]",
        type="{1: 'int', 2: 'float'}[kind]",
    ),
]

# kind=1 -> payload is int (1 byte)
encoded_int = encode([(struct_def[0], 1), (struct_def[1], 7)])
decoded_int = decode(struct_def, encoded_int)

# kind=2 -> payload is float (4 bytes)
encoded_float = encode([(struct_def[0], 2), (struct_def[1], 1.5)])
decoded_float = decode(struct_def, encoded_float)

print(encoded_int, decoded_int)
print(encoded_float, decoded_float)
```

## Saving And Loading StructDef Dictionaries

You can persist reusable structure definitions by name with
`save_struct_def_dict` / `load_struct_def_dict`.

```python
from pathlib import Path

from sltcore import InfoSize
from sltcodec import FieldDef, StructDef, load_struct_def_dict, save_struct_def_dict

struct_defs = {
    "Header": StructDef(
        name="Header",
        description="Simple header",
        fields=[
            FieldDef(name="kind", offset=InfoSize(0, 0), size=InfoSize(1, 0), type="unsigned int"),
            FieldDef(name="flags", offset=InfoSize(1, 0), size=InfoSize(1, 0), type="unsigned int"),
        ],
    )
}

path = Path("struct_defs.json")
save_struct_def_dict(path, struct_defs)
loaded = load_struct_def_dict(path)

print(loaded["Header"].name)
print(loaded["Header"].description)
```

Example output:

```python
bytearray(b"\x01\x07") [(FieldDef(...kind...), 1), (FieldDef(...payload...), 7)]
bytearray(b"\x02?\xc0\x00\x00") [(FieldDef(...kind...), 2), (FieldDef(...payload...), 1.5)]
```

## Development

```bash
uv sync --all-extras
uv run pytest
```
