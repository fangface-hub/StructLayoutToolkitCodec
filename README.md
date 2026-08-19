# StructLayoutToolkitCodec Development

This repository contains `sltcodec`, a Python package for encoding and
decoding bytearrays according to structured layout definitions.

The package description and user-facing API examples used for PyPI are in
[README_pypi.md](README_pypi.md).

## Development Setup

This project requires Python 3.12 or newer and uses `uv` for dependency and
environment management.

```bash
uv sync --all-extras
```

The project also keeps a local virtual environment at `.venv` when using the
standard `uv` workflow.

## Run Tests

Run the complete test suite:

```bash
uv run pytest
```

Run a focused test module:

```bash
uv run pytest tests/test_codec.py -q
uv run pytest tests/test_types.py -q
uv run pytest tests/test_persistence.py -q
```

Tests are organized by responsibility:

- `tests/test_codec.py`: encoding, decoding, padding, repetition, and byte swapping
- `tests/test_types.py`: field, enum, structure, and instance behavior
- `tests/test_persistence.py`: `StructLayout` JSON persistence

## Source Layout

```text
src/sltcodec/
    __init__.py    Public package exports
    codec.py       Encoding, decoding, and layout persistence
    types.py       Field, enum, structure, and layout types
tests/             Pytest test modules
```

## Public API Changes

`encode` and `decode` receive one `StructLayout` object. The structure
definition is resolved by `struct_layout.struct_def_name` from
`struct_layout.type_dict.struct_dict`; enum definitions are resolved from the
same `TypeDict`.

Layout persistence uses the explicit names `save_struct_layout` and
`load_struct_layout`. The former `save_type_dict` and `load_type_dict` API is
not part of the current public interface.

`FieldInstance` stays frozen. To change a decoded value, use
`FieldInstance.with_value(value, type_dict=None)`, which returns a new
instance instead of mutating the original. It keeps `field_def` and
`is_padding`, and recomputes `enum_item` from the new value and `type_dict`
by delegating to `FieldInstance.from_value`.

```python
updated_field = field_instance.with_value(
    new_value,
    struct_layout.type_dict,
)
```

Decoded sizes reflect the actual data consumed. `decode` sets
`StructInstance.size` to the end of the decoded layout, and `decode_field`
stores the actual size in `FieldInstance.field_def.size`. For nested structures,
the nested `StructInstance.size` is used; repeated fields advance each next
offset by the preceding element's actual size.

`FieldDef.repeat` also supports the special string value `"end"`.
When `repeat="end"`, decoding repeats until the input bytearray ends.
The decoder stops when the next element offset is out of range or when the
next element size would exceed the remaining input.

`StructDef` and `StructInstance` provide indexed accessors:

- `get_field(name)`: return the first matching item, or `None`.
- `get_fields(name)`: return all matching items as a list.

For `StructDef`, these accessors resolve by referenced structure name in
`FieldDef.type` (non-primitive types only). For `StructInstance`, they resolve
by `FieldInstance.field_def.name`.

## Versioning And Release

Version bump scripts are provided for patch, minor, and major releases:

```powershell
.\bump_patch.ps1
.\bump_minor.ps1
.\bump_major.ps1
```

Review the generated version change and run the full test suite before
building or publishing a package.

## Build

The package uses Hatchling as its build backend. The package metadata points
to `README_pypi.md` so the PyPI project page contains the consumer-facing
documentation rather than repository development notes.

```bash
uv build
```
