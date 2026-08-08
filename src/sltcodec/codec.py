"""Encoding and decoding of structured layouts into bytearrays."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sltcalc import SltEval
from sltcore import Info, InfoSize, bits_get, bits_set

from .types import FieldDef, FieldInstance, StructDef, StructInstance

_PRIMITIVE_TYPES = {
    "bool",
    "signed int",
    "int",
    "unsigned int",
    "float",
    "bytearray",
    "bytes",
}


def _as_field_defs(struct_def: StructDef | list[FieldDef]) -> list[FieldDef]:
    """Normalize StructDef/list inputs to a list of field definitions."""
    if isinstance(struct_def, StructDef):
        return struct_def.fields
    return struct_def


def _validate_struct_instance(struct_instance: StructInstance) -> None:
    """Validate that encode input is a well-typed StructInstance."""
    if not isinstance(struct_instance, StructInstance):
        raise TypeError("encode() expects StructInstance for struct_instance")
    for index, field_instance in enumerate(struct_instance.field_instances):
        if not isinstance(field_instance, FieldInstance):
            raise TypeError(
                "encode() expects StructInstance.field_instances to be "
                "list[FieldInstance]. "
                f"Invalid item at index {index}: "
                f"{type(field_instance).__name__}")


def save_struct_def_dict(path: str | Path,
                         struct_def_dict: dict[str, StructDef]) -> None:
    """Save a structure definition dictionary to a JSON file."""
    payload = {
        name: struct_def.to_dict()
        for name, struct_def in struct_def_dict.items()
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def load_struct_def_dict(path: str | Path) -> dict[str, StructDef]:
    """Load a structure definition dictionary from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        name: StructDef.from_dict(field_def_data)
        for name, field_def_data in data.items()
    }


def _resolve_info_size(value: InfoSize | str, env: dict[str, Any]) -> InfoSize:
    """Resolve an InfoSize value that can be static or expression-based."""
    if isinstance(value, str):
        stleval = SltEval(env)
        resolved_byte = stleval.eval(value)
        return InfoSize(resolved_byte, 0)
    return value


def _resolve_offset(field_def: FieldDef, env: dict[str, Any]) -> InfoSize:
    """Resolve a field offset that can be static or expression-based."""
    return _resolve_info_size(field_def.offset, env)


def _resolve_size(field_def: FieldDef, env: dict[str, Any]) -> InfoSize:
    """Resolve a field size that can be static or expression-based."""
    return _resolve_info_size(field_def.size, env)


def _is_padding_field_def(field_def: FieldDef) -> bool:
    """Check whether a field definition represents padding."""
    return (field_def.name.startswith("padding[")
            and field_def.type in ["bytes", "bytearray"])


def _info_size_to_bits(info_size: InfoSize) -> int:
    """Convert InfoSize to an absolute bit count."""
    return info_size.byte * 8 + info_size.bit


def _info_size_from_bits(total_bits: int) -> InfoSize:
    """Create InfoSize from an absolute bit count."""
    return InfoSize(total_bits >> 3, total_bits & 0x7)


def _resolve_field_type(field_type: str | StructDef,
                        struct_def_dict: dict[str, StructDef] | None = None,
                        env: dict[str, Any] | None = None) -> str | StructDef:
    """Resolve a field type that can be primitive, named, or nested."""
    if isinstance(field_type, StructDef):
        return field_type
    if field_type in _PRIMITIVE_TYPES:
        return field_type

    resolved_struct_def = _get_struct_def(field_type, struct_def_dict, env)
    if isinstance(resolved_struct_def, StructDef):
        return resolved_struct_def
    if (isinstance(resolved_struct_def, str)
            and resolved_struct_def in _PRIMITIVE_TYPES):
        return resolved_struct_def
    return field_type


def _encode_primitive(field_type: str, value: Any, size: InfoSize,
                      scale: float) -> Info:
    """Convert a primitive typed value into an Info object for bits_set."""
    if field_type == "bool":
        return Info.from_bool(bool(value), size, scale=scale)
    if field_type == "signed int":
        return Info.from_signed_int(int(value), size, scale=scale)
    if field_type in ["int", "unsigned int"]:
        return Info.from_unsigned_int(int(value), size, scale=scale)
    if field_type == "float":
        return Info.from_float(float(value), size, scale=scale)
    if field_type in ["bytearray", "bytes"]:
        return Info.from_bytes(bytes(value), size, scale=scale)
    if isinstance(value, (bytes, bytearray)):
        return Info.from_bytes(bytes(value), size, scale=scale)
    if isinstance(value, bool):
        return Info.from_bool(value, size, scale=scale)
    if isinstance(value, int):
        return Info.from_unsigned_int(value, size, scale=scale)

    return Info(raw_value=value, info_size=size, scale=scale)


def _prepare_field_info(
    field_def: FieldDef,
    value: Any,
    env: dict[str, Any],
    struct_def_dict: dict[str, StructDef] | None = None
) -> tuple[InfoSize, InfoSize, Info] | None:
    """Resolve a field definition into an offset, size, and info payload."""
    offset = _resolve_offset(field_def, env)
    size = _resolve_size(field_def, env)
    if size.byte == 0 and size.bit == 0:
        return None

    resolved_type = _resolve_field_type(field_def.type, struct_def_dict, env)
    if isinstance(resolved_type, StructDef):
        if not isinstance(value, StructInstance):
            raise TypeError(
                "Nested StructDef fields must be encoded with StructInstance "
                "values")
        nested_bytes = encode(value, bytearray(), struct_def_dict)
        info = Info.from_bytes(bytes(nested_bytes), size, scale=field_def.scale)
    else:
        info = _encode_primitive(resolved_type, value, size, field_def.scale)
    return offset, size, info


def _split_repeated_field(field_def: FieldDef,
                          index: int,
                          env: dict[str, Any],
                          offset: InfoSize | str | None = None) -> FieldDef:
    """Create a repeated-field definition with resolved offset and size."""
    resolved_offset = (_resolve_offset(field_def, env)
                       if offset is None else offset)
    resolved_size = _resolve_size(field_def, env)
    return FieldDef(name=f"{field_def.name}[{index}]",
                    offset=resolved_offset,
                    size=resolved_size,
                    type=field_def.type,
                    scale=field_def.scale,
                    repeat=None,
                    description=field_def.description)


def encode_field(field_def: FieldDef,
                 value: Any,
                 buf: bytearray,
                 env: dict[str, Any] | None = None,
                 struct_def_dict: dict[str, StructDef] | None = None) -> None:
    """Encode a single field into a bytearray."""
    if env is None:
        env = {}

    prepared = _prepare_field_info(field_def, value, env, struct_def_dict)
    if prepared is None:
        return

    offset, size, info = prepared
    required_bytes = (offset + size).bytes
    if len(buf) < required_bytes:
        buf.extend(b"\x00" * (required_bytes - len(buf)))

    bits_set(buf, offset, info)


def encode(struct_instance: StructInstance,
           buf: bytearray,
           struct_def_dict: dict[str, StructDef] | None = None) -> bytearray:
    """Encode decode() result into a bytearray.

    Parameters
    ----------
    struct_instance : StructInstance
        The structure instance to encode.
    buf : bytearray
        The base bytearray instance to write into.
    struct_def_dict : dict[str, StructDef] | None, optional
        A dictionary of structure definitions, by default None.

    Returns
    -------
    bytearray
        The encoded bytearray.
    """
    _validate_struct_instance(struct_instance)
    env: dict[str, Any] = {}
    has_padding = False

    for field_value in struct_instance.field_instances:
        field_def = field_value.field_def
        if _is_padding_field_def(field_def):
            has_padding = True
        value = field_value.value
        if _is_padding_field_def(field_def):
            padding_size = _resolve_size(field_def, env)
            value = bytearray(padding_size.bytes)
        if field_def.repeat is not None and field_def.repeat > 1:
            current_offset = _resolve_offset(field_def, env)
            resolved_size = _resolve_size(field_def, env)
            values = list(value)

            for i in range(field_def.repeat):
                field_def_repeat = _split_repeated_field(
                    field_def, i, env, current_offset)
                encode_field(field_def_repeat, values[i], buf, env,
                             struct_def_dict)
                env[field_def_repeat.name] = values[i]
                if isinstance(current_offset, InfoSize) and isinstance(
                        resolved_size, InfoSize):
                    current_offset += resolved_size
            continue

        encode_field(field_def, value, buf, env, struct_def_dict)
        env[field_def.name] = value

    if has_padding and struct_instance.size.bytes > len(buf):
        buf.extend(b"\x00" * (struct_instance.size.bytes - len(buf)))

    return buf


def decode_field(
    field_def: FieldDef,
    data: bytearray | bytes,
    env: dict[str, Any] | None = None,
    struct_def_dict: dict[str, StructDef] | None = None
) -> FieldInstance | None:
    """Decode a single field from a bytearray according to a field definition.

    Parameters
    ----------
    field_def : FieldDef
        The definition of the field to decode.
    data : bytearray | bytes
        The data to decode.
    env : dict[str, Any] | None, optional
        The environment for evaluating expressions, by default None.
    struct_def_dict : dict[str, StructDef] | None, optional
        A dictionary of structure definitions, by default None.
    Returns
    -------
    FieldInstance | None
        The decoded field instance, or None when size is zero.
    """
    if env is None:
        env = {}
    offset = _resolve_offset(field_def, env)
    size = _resolve_size(field_def, env)
    if size.byte == 0 and size.bit == 0:
        return None
    info = bits_get(data, offset, size, scale=field_def.scale)
    resolved_type = _resolve_field_type(field_def.type, struct_def_dict, env)
    if isinstance(resolved_type, StructDef):
        return FieldInstance(
            field_def=field_def,
            value=decode(resolved_type, bytearray(info.to_bytes),
                         struct_def_dict),
        )
    if resolved_type == "bool":
        return FieldInstance(field_def=field_def, value=info.to_bool)
    if resolved_type == "signed int":
        return FieldInstance(field_def=field_def, value=info.to_signed_int)
    if resolved_type in ["int", "unsigned int"]:
        return FieldInstance(field_def=field_def, value=info.to_unsigned_int)
    if resolved_type == "float":
        return FieldInstance(field_def=field_def, value=info.to_float)
    if resolved_type in ["bytearray", "bytes"]:
        return FieldInstance(field_def=field_def, value=info.to_bytes)
    return FieldInstance(field_def=field_def, value=info.raw_value)


def decode(
        struct_def: StructDef | list[FieldDef],
        data: bytearray | bytes,
        struct_def_dict: dict[str, StructDef] | None = None) -> StructInstance:
    """Decode a bytearray into field values according to a layout.

    Parameters
    ----------
    struct_def : StructDef | list[FieldDef]
        The definitions of the fields to decode.
    data : bytearray | bytes
        The data to decode.
    struct_def_dict : dict[str, StructDef] | None, optional
        A dictionary of structure definitions, by default None.
    Returns
    -------
    StructInstance
        The decoded structure instance.
    """
    env = {}
    struct_def_obj = (struct_def if isinstance(struct_def, StructDef) else
                      StructDef(fields=struct_def))
    result = StructInstance(struct_def=struct_def_obj)
    current_position = InfoSize(0, 0)
    padding_index = 0

    def append_padding_until(target_offset: InfoSize) -> None:
        nonlocal current_position, padding_index
        start_bits = _info_size_to_bits(current_position)
        end_bits = _info_size_to_bits(target_offset)
        if end_bits <= start_bits:
            return

        chunk_start_bits = start_bits
        while chunk_start_bits < end_bits:
            next_boundary_bits = ((chunk_start_bits // 32) + 1) * 32
            chunk_end_bits = min(end_bits, next_boundary_bits)
            padding_field_def = FieldDef(
                name=f"padding[{padding_index}]",
                offset=_info_size_from_bits(chunk_start_bits),
                size=_info_size_from_bits(chunk_end_bits - chunk_start_bits),
                type="bytes",
                description="Auto-generated padding",
            )
            padding_field_instance = decode_field(padding_field_def, data)
            if padding_field_instance is not None:
                result.append_field_instance(padding_field_instance)
            padding_index += 1
            chunk_start_bits = chunk_end_bits

        current_position = target_offset

    for field_def in _as_field_defs(struct_def_obj):
        # Handle non-repeated fields
        if field_def.repeat is None or field_def.repeat <= 1:
            resolved_offset = _resolve_offset(field_def, env)
            append_padding_until(resolved_offset)
            field_instance = decode_field(field_def, data, env, struct_def_dict)
            if field_instance is not None:
                env[field_instance.field_def.name] = field_instance.value
                result.append_field_instance(field_instance)
                current_position = (resolved_offset +
                                    _resolve_size(field_def, env))
            continue
        # Handle repeated fields
        current_offset = _resolve_offset(field_def, env)
        resolved_size = _resolve_size(field_def, env)
        append_padding_until(current_offset)
        for i in range(field_def.repeat):
            field_def_repeat = _split_repeated_field(field_def, i, env,
                                                     current_offset)
            field_instance = decode_field(field_def_repeat, data, env,
                                          struct_def_dict)
            if field_instance is not None:
                env[field_instance.field_def.name] = field_instance.value
                result.append_field_instance(field_instance)
                current_position = current_offset + resolved_size
            current_offset += resolved_size

    append_padding_until(result.size)

    return result


def _get_struct_def(
        struct_def_name: str,
        struct_def_dict: dict[str, StructDef] | None = None,
        env: dict[str, Any] | None = None) -> StructDef | str | None:
    """Get a structure definition from a dictionary or evaluate it.

    Parameters
    ----------
    struct_def_name : str
        The name of the structure definition to get.
    struct_def_dict : dict[str, StructDef] | None, optional
        A dictionary of structure definitions, by default None.
    env : dict[str, Any] | None, optional
        The environment for evaluating the structure definition,
        by default None.

    Returns
    -------
    StructDef | str | None
        The structure definition, primitive type, or None if not found.
    """
    if struct_def_dict and struct_def_name in struct_def_dict:
        return struct_def_dict[struct_def_name]

    stleval = SltEval(env)
    try:
        eval_result = stleval.eval(struct_def_name)
    except (SyntaxError, NameError, TypeError, ValueError):
        return None

    if isinstance(eval_result, str) and eval_result in _PRIMITIVE_TYPES:
        return eval_result
    if (isinstance(eval_result, str) and struct_def_dict
            and eval_result in struct_def_dict):
        return struct_def_dict[eval_result]
    return None
