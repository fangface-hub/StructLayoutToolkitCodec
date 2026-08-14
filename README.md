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
[FieldInstance(field_def=FieldDef(name='pair', offset=InfoSize(byte=0, bit=0), size=InfoSize(byte=2, bit=0), type=StructDef(...), scale=1.0, repeat=None),
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

## Saving And Loading Type Dictionaries

You can persist reusable structure and enum definitions together via
`TypeDict` with `save_type_dict` / `load_type_dict`.

`InfoSize` values in `offset` and `size` are saved as typed dictionaries in
JSON. Expression-based offsets and sizes remain strings and are resolved when
the definition is used.

```python
from pathlib import Path

from sltcore import InfoSize
from sltcodec import EnumDef, FieldDef, StructDef, TypeDict, load_type_dict, save_type_dict

type_dict = TypeDict(
    struct_dict={
        "Header": StructDef(
            name="Header",
            description="Simple header",
            fields=[
                FieldDef(name="kind", offset=InfoSize(0, 0), size=InfoSize(1, 0), type="unsigned int"),
                FieldDef(name="flags", offset=InfoSize(1, 0), size=InfoSize(1, 0), type="unsigned int"),
            ],
        )
    },
    enum_dict={
        "Status": EnumDef(name="Status", values={"OK": 0, "NG": 1}),
    }
)

path = Path("struct_defs.json")
save_type_dict(path, type_dict)
loaded = load_type_dict(path)

print(loaded.struct_dict["Header"].name)
print(loaded.struct_dict["Header"].description)
print(loaded.enum_dict["Status"].values["NG"])
```

Example output:

```python
Header
Simple header
1
```

## Enum Definitions

`FieldDef.enum_def_name` holds only the name of an `EnumDef`, not the definition
itself. In practice, `TypeDict` is most useful when you pass both
`type_dict.struct_dict` and `type_dict.enum_dict` together: one resolves named
layout types and the other resolves enum labels. The example below uses both in
one decode flow.

```python
from sltcore import InfoSize
from sltcodec import EnumDef, EnumDict, FieldDef, StructDef, StructDict, TypeDict, decode

enum_dict = EnumDict({"Status": EnumDef(name="Status", values={"OK": 0, "NG": 1})})

packet_struct = StructDef(
    name="Packet",
    fields=[
        FieldDef(name="status",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int",
                 enum_def_name="Status"),
    ],
)

struct_dict = StructDict({"Packet": packet_struct})

type_dict = TypeDict(struct_dict=struct_dict.items_dict(),
                     enum_dict=enum_dict.items_dict())

decoded = decode(type_dict.struct_dict["Packet"],
                 bytearray(b"\x01"),
                 type_dict=type_dict)

print(decoded.field_instances[0].value)
print(decoded.field_instances[0].enum_item)
```

Output:

```python
1
('NG', 1)
```

You can also persist enum definitions by name through `TypeDict` using
`save_type_dict` / `load_type_dict`.

## Development

```bash
uv sync --all-extras
uv run pytest
```
