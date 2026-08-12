# StructLayoutToolkitCodec

sltcodec is a small package for decoding and encoding bytearrays according to structured layout definitions. It uses sltcore for bit-level access and provides a simple API for turning a layout definition into binary data and back again.

## Installation

```bash
pip install sltcodec
```

## Primitive Type Set

`PRIMITIVE_TYPES` is the public set of built-in field types understood by the codec.

```python
from sltcodec import PRIMITIVE_TYPES

print(PRIMITIVE_TYPES)
# {'bool', 'signed int', 'int', 'unsigned int', 'float', 'bytearray', 'bytes'}
```

## Quick Example

`FieldDef.description` is an optional human-readable note that can be attached to each field definition.

`decode` returns a `StructInstance`.
`encode` accepts a `StructInstance` and a destination `bytearray`.

```python
from sltcore import InfoSize
from sltcodec import (FieldDef, FieldInstance, StructDef, StructInstance,
                      decode, encode)

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

encoded = encode(
    StructInstance(
        struct_def=StructDef(fields=struct_def),
        field_instances=[
            FieldInstance(struct_def[0], True),
            FieldInstance(struct_def[1], 0xA5),
        ],
    ),
    bytearray(),
)
decoded = decode(struct_def, encoded)

print(encoded)
print(decoded)
print(decoded.field_instances)
```

Output:

```python
bytearray(b"\xd2\x80")
StructInstance(struct_def=StructDef(...), field_instances=[...])
[FieldInstance(field_def=FieldDef(name='flag', offset=InfoSize(byte=0, bit=0), size=InfoSize(byte=0, bit=1), type='bool', scale=1.0, repeat=None), value=True),
 FieldInstance(field_def=FieldDef(name='value', offset=InfoSize(byte=0, bit=1), size=InfoSize(byte=1, bit=0), type='unsigned int', scale=1.0, repeat=None), value=165)]

```

## Nested Field Types

`FieldDef.type` can be a `StructDef`, not only a primitive type name.
This allows you to define an inline nested structure and keep `encode_field` / `decode_field` behavior symmetrical.

```python
from sltcore import InfoSize
from sltcodec import FieldDef, FieldInstance, StructDef, StructInstance, decode, encode

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

encoded = encode(
    StructInstance(
        struct_def=StructDef(fields=[parent_field_def]),
        field_instances=[
            FieldInstance(
                parent_field_def,
                StructInstance(
                    struct_def=StructDef(fields=child_struct_def),
                    field_instances=[
                        FieldInstance(child_struct_def[0], 3),
                        FieldInstance(child_struct_def[1], 4),
                    ],
                ),
            )
        ],
    ),
    bytearray(),
)

decoded = decode([parent_field_def], encoded)
print(encoded)
print(decoded)
print(decoded.field_instances)
```

Output:

```python
bytearray(b"\x03\x04")
StructInstance(struct_def=StructDef(...), field_instances=[...])
[FieldInstance(field_def=FieldDef(name='pair', offset=InfoSize(byte=0, bit=0), size=InfoSize(byte=2, bit=0), type=[...], scale=1.0, repeat=None),
               value=StructInstance(struct_def=StructDef(...), field_instances=[...]))]
```

## Expression-Based Type Selection

`FieldDef.type` can also be an expression string.
The expression is evaluated with previously processed field values in scope, so you can switch decoding/encoding type dynamically.

```python
from sltcore import InfoSize
from sltcodec import (FieldDef, FieldInstance, StructDef, StructInstance,
                      decode, encode)

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
encoded_int = encode(
    StructInstance(
        struct_def=StructDef(fields=struct_def),
        field_instances=[
            FieldInstance(struct_def[0], 1),
            FieldInstance(struct_def[1], 7),
        ],
    ),
    bytearray(),
)
decoded_int = decode(struct_def, encoded_int)

# kind=2 -> payload is float (4 bytes)
encoded_float = encode(
    StructInstance(
        struct_def=StructDef(fields=struct_def),
        field_instances=[
            FieldInstance(struct_def[0], 2),
            FieldInstance(struct_def[1], 1.5),
        ],
    ),
    bytearray(),
)
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
bytearray(b"\x01\x07") StructInstance(struct_def=StructDef(...), field_instances=[...])
bytearray(b"\x02?\xc0\x00\x00") StructInstance(struct_def=StructDef(...), field_instances=[...])
```

## Development

```bash
uv sync --all-extras
uv run pytest
```
