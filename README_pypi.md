# StructLayoutToolkitCodec

`sltcodec` encodes and decodes bytearrays according to structured layout definitions. It uses `sltcore` for bit-level access.

## Installation

```bash
pip install sltcodec
```

## Quick Example

`StructLayout` bundles the root structure name with its `TypeDict`. Pass the same layout to both `encode` and `decode`.

```python
from sltcore import InfoSize
from sltcodec import (
    FieldDef,
    FieldInstance,
    StructDef,
    StructInstance,
    StructLayout,
    TypeDict,
    decode,
    encode,
)

fields = [
    FieldDef(name="flag", offset=InfoSize(0, 0), size=InfoSize(0, 1), type="bool"),
    FieldDef(name="value", offset=InfoSize(0, 1), size=InfoSize(1, 0), type="unsigned int"),
]
struct_def = StructDef(name="Packet", fields=fields)
layout = StructLayout(
    struct_def_name="Packet",
    type_dict=TypeDict(struct_dict={"Packet": struct_def}),
)
instance = StructInstance(
    struct_def=struct_def,
    field_instances=[
        FieldInstance(fields[0], True),
        FieldInstance(fields[1], 0xA5),
    ],
)

encoded = encode(layout, instance, bytearray())
decoded = decode(layout, encoded)
```

`decode` returns a `StructInstance` whose `size` is the actual end of the
decoded layout. `decode_field` stores the actual decoded size in the returned
`FieldInstance.field_def.size`. For nested `StructDef` fields, that size comes
from the nested `StructInstance.size`; for repeated fields, the next element's
offset advances by the actual size of the previous element.

`FieldDef.repeat` also accepts the special string value `"end"`. When
`repeat="end"`, decoding repeats until the input bytearray ends. Decoding
stops when the next element offset is out of range or when the next element
size would exceed the remaining input.

## Field Types

The public `PRIMITIVE_TYPES` set contains:

```python
{"bool", "signed int", "int", "unsigned int", "float", "bytearray", "bytes"}
```

`FieldDef.type` may also be a nested `StructDef` or an expression string. Expressions can use values from previously processed fields, allowing dynamic types, sizes, and repeat counts. Repeated fields, byte swapping, padding, ranges, and enum metadata are supported.

## Enums And Named Structures

Store named structures in `TypeDict.struct_dict` and enums in `TypeDict.enum_dict`. A field refers to an enum by its `enum_def_name`; the codec resolves it through `StructLayout.type_dict`.

```python
from sltcore import InfoSize
from sltcodec import EnumDef, FieldDef, StructDef, StructLayout, TypeDict, decode

enum_def = EnumDef(name="Status", values={"OK": 0, "NG": 1})
packet = StructDef(
    name="Packet",
    fields=[FieldDef(
        name="status",
        offset=InfoSize(0, 0),
        size=InfoSize(1, 0),
        type="unsigned int",
        enum_def_name="Status",
    )],
)
layout = StructLayout(
    struct_def_name="Packet",
    type_dict=TypeDict(
        struct_dict={"Packet": packet},
        enum_dict={"Status": enum_def},
    ),
)

decoded = decode(layout, bytearray(b"\x01"))
assert decoded.field_instances[0].enum_item == ("NG", 1)
```

## Saving And Loading

Persist a complete `StructLayout`, including its root structure name, structure definitions, and enum definitions, with `save_struct_layout` and `load_struct_layout`.

```python
from pathlib import Path
from sltcodec import load_struct_layout, save_struct_layout

path = Path("struct_layout.json")
save_struct_layout(layout, path)
loaded = load_struct_layout(path)
assert loaded == layout
```

`InfoSize` values are stored as typed JSON dictionaries. Expression-based offsets and sizes remain strings and are evaluated when the layout is used.

## Public API Reference

The following symbols are exported by `sltcodec.__all__` in this order:

| Symbol | Description |
| --- | --- |
| `PRIMITIVE_TYPES` | Set of built-in field type names supported by the codec. |
| `EnumDef` | Immutable definition of an enumeration. |
| `EnumDict` | Dictionary-like container for `EnumDef` objects. |
| `FieldDef` | Immutable definition of one structured field. |
| `FieldInstance` | Immutable field definition and decoded/encodable value pair. |
| `StructDef` | Immutable definition that groups fields into a structure. |
| `StructDict` | Dictionary-like container for `StructDef` objects. |
| `StructInstance` | Decoded/encodable structure instance containing field instances. |
| `StructLayout` | Bundle of the root structure name and its `TypeDict`. |
| `TypeDict` | Bundle of named structure and enum dictionaries. |
| `decode` | Decode bytes according to a `StructLayout`. |
| `encode` | Encode a `StructInstance` according to a `StructLayout`. |
| `load_struct_layout` | Load a `StructLayout` from JSON. |
| `save_struct_layout` | Save a `StructLayout` as JSON. |

### Types (`types.py`)

Classes are listed in their definition order. The member tables show the
dataclass fields or constructor attributes. Methods beginning with `_` are
internal implementation details and are omitted from the public method tables.

#### `EnumDef`

| Member | Type | Description |
| --- | --- | --- |
| `name` | `str` | Enumeration name. |
| `description` | `str \| None` | Optional description. |
| `values` | `dict[str, int]` | Mapping from enumeration names to integer values. |

| Method | Description |
| --- | --- |
| `to_dict()` | Convert the definition to a JSON-compatible dictionary. |
| `to_json()` | Convert the definition to a JSON string. |
| `from_dict(data)` | Create an `EnumDef` from a dictionary. |
| `serialize()` | Convert the definition to a typed dictionary. |
| `deserialize(data)` | Create an `EnumDef` from a typed dictionary. |
| `from_json(data)` | Create an `EnumDef` from a JSON string. |
| `__lt__(other)` | Compare enum definitions using their serialized ordering. |

#### `FieldDef`

| Member | Type | Description |
| --- | --- | --- |
| `name` | `str` | Field name. |
| `offset` | `InfoSize \| str` | Static offset or expression. |
| `size` | `InfoSize \| str` | Static size or expression. |
| `type` | `str \| StructDef` | Primitive, named, or nested field type. |
| `scale` | `float` | Numeric scale applied to the field. |
| `repeat` | `int \| str \| None` | Number of repeated field values, an expression that evaluates to the count, or `"end"` to decode repeatedly until input end. |
| `description` | `str \| None` | Optional field description. |
| `range_expression` | `str \| None` | Optional value-range expression. |
| `enum_def_name` | `str \| None` | Name of the associated enum definition. |
| `byte_swap` | `bool \| str` | Whether to reverse bytes, or an expression controlling it. |

| Method | Description |
| --- | --- |
| `to_dict()` | Convert the definition to a JSON-compatible dictionary. |
| `to_json()` | Convert the definition to a JSON string. |
| `from_dict(data)` | Create a `FieldDef` from a dictionary. |
| `from_json(data)` | Create a `FieldDef` from a JSON string. |
| `__lt__(other)` | Compare field definitions using their serialized ordering. |

#### `FieldInstance`

| Member | Type | Description |
| --- | --- | --- |
| `field_def` | `FieldDef` | Definition of the field. |
| `value` | `Any` | Decoded or encodable field value. |
| `enum_item` | `tuple[str, int] \| None` | Matching enum name and value, when available. |
| `is_padding` | `bool` | Whether this instance represents padding. |

| Method | Description |
| --- | --- |
| `range_check(env=None)` | Evaluate the field's range expression. |
| `from_value(field_def, value, type_dict=None, is_padding=False)` | Create an instance and resolve matching enum metadata. |
| `with_value(value, type_dict=None)` | Return a new instance with the given value; keeps `field_def` and `is_padding` and recomputes `enum_item`. |
| `__lt__(other)` | Compare field instances using field-definition order. |

#### `StructDef`

| Member | Type | Description |
| --- | --- | --- |
| `name` | `str` | Structure name. |
| `description` | `str` | Structure description. |
| `fields` | `list[FieldDef]` | Ordered field definitions. |

| Method | Description |
| --- | --- |
| `get_field(struct_def_name)` | Return the first field whose `type` references the given structure name. |
| `get_fields(struct_def_name)` | Return all fields whose `type` references the given structure name. |
| `to_dict()` | Convert the definition to a JSON-compatible dictionary. |
| `to_json()` | Convert the definition to a JSON string. |
| `from_dict(data)` | Create a `StructDef` from a dictionary or legacy field list. |
| `from_json(data)` | Create a `StructDef` from a JSON string. |
| `__lt__(other)` | Compare structure definitions using their serialized ordering. |

#### `StructInstance`

| Member | Type | Description |
| --- | --- | --- |
| `struct_def` | `StructDef` | Structure definition for the instance. |
| `field_instances` | `list[FieldInstance]` | Stored field instances, kept in field order. |
| `size` | `InfoSize` | Total structure size. |

| Method | Description |
| --- | --- |
| `append_field_instance(field_instance)` | Append one field instance. |
| `extend_field_instances(field_instances)` | Append multiple field instances. |
| `get_field(field_def_name)` | Return the first field instance whose `field_def.name` matches. |
| `get_fields(field_def_name)` | Return all field instances whose `field_def.name` matches. |
| `__iter__()` | Iterate over field instances. |
| `__len__()` | Return the number of field instances. |
| `__getitem__(index)` | Get a field instance by index. |
| `__post_init__()` | Normalize field order, size, and generated padding after construction. |
| `__lt__(other)` | Compare structure instances using their serialized ordering. |

#### `EnumDict`

| Member | Type | Description |
| --- | --- | --- |
| `_items` | `dict[str, EnumDef]` | Stored enum definitions. Use mapping operations or `items_dict()`. |

| Method | Description |
| --- | --- |
| `__getitem__(key)` | Get an enum definition by name. |
| `__setitem__(key, value)` | Store an enum definition. |
| `__delitem__(key)` | Delete an enum definition. |
| `__iter__()` | Iterate over enum names. |
| `__len__()` | Return the number of enum definitions. |
| `items_dict()` | Return the underlying dictionary. |

#### `StructDict`

| Member | Type | Description |
| --- | --- | --- |
| `_items` | `dict[str, StructDef]` | Stored structure definitions. Use mapping operations or `items_dict()`. |

| Method | Description |
| --- | --- |
| `__getitem__(key)` | Get a structure definition by name. |
| `__setitem__(key, value)` | Store a structure definition. |
| `__delitem__(key)` | Delete a structure definition. |
| `__iter__()` | Iterate over structure names. |
| `__len__()` | Return the number of structure definitions. |
| `items_dict()` | Return the underlying dictionary. |

#### `TypeDict`

| Member | Type | Description |
| --- | --- | --- |
| `enum_dict` | `EnumDict` | Named enum definitions. |
| `struct_dict` | `StructDict` | Named structure definitions. |

`TypeDict(enum_dict=None, struct_dict=None)` constructs both containers from
optional dictionaries.

#### `StructLayout`

| Member | Type | Description |
| --- | --- | --- |
| `struct_def_name` | `str` | Key of the root structure in `type_dict.struct_dict`. |
| `type_dict` | `TypeDict` | Structure and enum definitions used for resolution. |

`StructLayout(struct_def_name, type_dict)` constructs a layout bundle.

### Codec (`codec.py`)

The following public definitions are listed in their definition order. Names
beginning with `_` are internal helpers and are not part of the public API.

| Definition | Signature | Description |
| --- | --- | --- |
| `PRIMITIVE_TYPES` | `set[str]` | Built-in field type names. |
| `save_struct_layout` | `(struct_layout, path) -> None` | Save a layout to a JSON file. |
| `load_struct_layout` | `(path) -> StructLayout` | Load a layout from a JSON file. |
| `save_struct_def_dict` | `(path, struct_def_dict) -> None` | Save a structure-definition dictionary through the layout format. |
| `load_struct_def_dict` | `(path) -> dict[str, StructDef]` | Load a structure-definition dictionary. |
| `save_enum_def_dict` | `(path, enum_def_dict) -> None` | Save an enum-definition dictionary through the layout format. |
| `load_enum_def_dict` | `(path) -> dict[str, EnumDef]` | Load an enum-definition dictionary. |
| `encode` | `(struct_layout, struct_instance, buf, padding_alignment_bits=32) -> bytearray` | Encode a complete structure. |
| `decode_field` | `(field_def, data, env=None, type_dict=None, padding_alignment_bits=32) -> FieldInstance \| None` | Decode one field. |
| `decode` | `(struct_layout, data, padding_alignment_bits=32) -> StructInstance` | Decode a complete structure. |

`save_struct_def_dict`, `load_struct_def_dict`, `save_enum_def_dict`, and
`load_enum_def_dict` are available from `sltcodec.codec` for dictionary-level
compatibility. The package root exports the complete `StructLayout` API:
`save_struct_layout` and `load_struct_layout`.
