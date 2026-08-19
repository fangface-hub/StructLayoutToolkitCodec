"""Encoding and decoding of structured layouts into bytearrays."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sltcalc import SltEval
from sltcore import Info, InfoSize, bits_get, bits_set

from .types import (EnumDef, FieldDef, FieldInstance, StructDef, StructInstance,
                    StructLayout, TypeDict)

PRIMITIVE_TYPES = {
    "bool",
    "signed int",
    "int",
    "unsigned int",
    "float",
    "bytearray",
    "bytes",
}

# Backward-compatible alias for internal usage.
_PRIMITIVE_TYPES = PRIMITIVE_TYPES

_DEFAULT_PADDING_ALIGNMENT_BITS = 32


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


def save_struct_layout(struct_layout: StructLayout, path: str | Path) -> None:
    """Save a StructLayout to a JSON file."""
    if not isinstance(struct_layout, StructLayout):
        raise TypeError(
            "save_struct_layout() expects StructLayout for struct_layout")

    type_dict = struct_layout.type_dict
    payload = {
        "struct_def_name": struct_layout.struct_def_name,
        "type_dict": {
            "struct_dict": {
                name: struct_def.to_dict()
                for name, struct_def in type_dict.struct_dict.items()
            },
            "enum_dict": {
                name: enum_def.to_dict()
                for name, enum_def in type_dict.enum_dict.items()
            },
        },
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def load_struct_layout(path: str | Path) -> StructLayout:
    """Load a StructLayout from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    type_payload = data.get("type_dict")
    if isinstance(type_payload, dict):
        struct_payload = type_payload.get("struct_dict", {})
        enum_payload = type_payload.get("enum_dict", {})
    else:
        struct_payload = data.get("struct_dict", {})
        enum_payload = data.get("enum_dict", {})

    type_dict = TypeDict(
        struct_dict={
            name: StructDef.from_dict(struct_def_data)
            for name, struct_def_data in struct_payload.items()
        },
        enum_dict={
            name: EnumDef.from_dict(enum_def_data)
            for name, enum_def_data in enum_payload.items()
        },
    )

    struct_def_name = data.get("struct_def_name")
    if not struct_def_name:
        if struct_payload:
            struct_def_name = next(iter(struct_payload))
        else:
            struct_def_name = "StructLayout"

    return StructLayout(struct_def_name=struct_def_name, type_dict=type_dict)


def save_struct_def_dict(path: str | Path,
                         struct_def_dict: dict[str, StructDef]) -> None:
    """Save a structure definition dictionary to a JSON file."""
    save_struct_layout(
        StructLayout(struct_def_name="StructLayout",
                     type_dict=TypeDict(struct_dict=struct_def_dict)), path)


def load_struct_def_dict(path: str | Path) -> dict[str, StructDef]:
    """Load a structure definition dictionary from a JSON file."""
    return load_struct_layout(path).type_dict.struct_dict.items_dict()


def save_enum_def_dict(path: str | Path, enum_def_dict: dict[str,
                                                             EnumDef]) -> None:
    """Save an enum definition dictionary to a JSON file."""
    save_struct_layout(
        StructLayout(struct_def_name="StructLayout",
                     type_dict=TypeDict(enum_dict=enum_def_dict)), path)


def load_enum_def_dict(path: str | Path) -> dict[str, EnumDef]:
    """Load an enum definition dictionary from a JSON file."""
    return load_struct_layout(path).type_dict.enum_dict.items_dict()


def _resolve_info_size(value: InfoSize | str, env: dict[str, Any]) -> InfoSize:
    """Resolve an InfoSize value that can be static or expression-based."""
    if isinstance(value, str):
        stleval = SltEval(env)
        resolved_byte = stleval.eval(value)
        if isinstance(resolved_byte, InfoSize):
            return resolved_byte
        return InfoSize(resolved_byte, 0)
    return value


def _resolve_byte_swap(field_def: FieldDef, env: dict[str, Any]) -> bool:
    """Resolve a byte-swap flag that can be static or expression-based."""
    if isinstance(field_def.byte_swap, str):
        return bool(SltEval(env).eval(field_def.byte_swap))
    return field_def.byte_swap


def _resolve_repeat(value: int | str | None, env: dict[str, Any]) -> int | None:
    """Resolve a static or expression-based repeat count."""
    if isinstance(value, str):
        return int(SltEval(env).eval(value))
    return value


def _is_padding_field_def(field_def: FieldDef) -> bool:
    """Check whether a field definition represents padding."""
    return (field_def.name.startswith("padding[")
            and field_def.type in ["bytes", "bytearray"])


def _validate_padding_alignment_bits(padding_alignment_bits: int) -> None:
    """Validate padding alignment as a positive power-of-two bit size."""
    if (isinstance(padding_alignment_bits, bool)
            or not isinstance(padding_alignment_bits, int)
            or padding_alignment_bits <= 0
            or (padding_alignment_bits & (padding_alignment_bits - 1)) != 0):
        raise ValueError(
            "padding_alignment_bits must be a positive power of two")


def _resolve_field_type(field_type: str | StructDef,
                        type_dict: TypeDict | None = None,
                        env: dict[str, Any] | None = None) -> str | StructDef:
    """Resolve a field type that can be primitive, named, or nested."""
    if isinstance(field_type, StructDef):
        return field_type
    if field_type in _PRIMITIVE_TYPES:
        return field_type

    resolved_struct_def = _get_struct_def(field_type, type_dict, env)
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
    type_dict: TypeDict | None = None,
    padding_alignment_bits: int = _DEFAULT_PADDING_ALIGNMENT_BITS,
) -> tuple[InfoSize, InfoSize, Info] | None:
    """Resolve a field definition into an offset, size, and info payload."""
    offset = _resolve_info_size(field_def.offset, env)
    size = _resolve_info_size(field_def.size, env)
    if size.byte == 0 and size.bit == 0:
        return None

    resolved_type = _resolve_field_type(field_def.type, type_dict, env)
    if isinstance(resolved_type, StructDef):
        if not isinstance(value, StructInstance):
            raise TypeError(
                "Nested StructDef fields must be encoded with StructInstance "
                "values")
        nested_bytes = encode(_layout_for_struct_def(value.struct_def,
                                                     type_dict,
                                                     name=field_def.name),
                              value,
                              bytearray(),
                              padding_alignment_bits=padding_alignment_bits)
        info = Info.from_bytes(bytes(nested_bytes), size, scale=field_def.scale)
    else:
        info = _encode_primitive(resolved_type, value, size, field_def.scale)
    return offset, size, info


def _repeated_field_def(field_def: FieldDef, index: int, offset: InfoSize,
                        size: InfoSize | str) -> FieldDef:
    """Create a resolved field definition for one repeated value."""
    repeated_name = f"{field_def.name}[{index}]"

    def replace_name(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        pattern = (rf"(?<![0-9A-Za-z_]){re.escape(field_def.name)}"
                   rf"(?![0-9A-Za-z_])")
        return re.sub(pattern, repeated_name, value)

    return FieldDef(
        name=repeated_name,
        offset=offset,
        size=size,
        type=replace_name(field_def.type),
        scale=field_def.scale,
        repeat=None,
        description=field_def.description,
        range_expression=replace_name(field_def.range_expression),
        enum_def_name=field_def.enum_def_name,
        byte_swap=replace_name(field_def.byte_swap),
    )


def encode_field(
    field_def: FieldDef,
    value: Any,
    buf: bytearray,
    env: dict[str, Any] | None = None,
    type_dict: TypeDict | None = None,
    padding_alignment_bits: int = _DEFAULT_PADDING_ALIGNMENT_BITS,
) -> None:
    """Encode a single field into a bytearray."""
    if env is None:
        env = {}

    prepared = _prepare_field_info(field_def, value, env, type_dict,
                                   padding_alignment_bits)
    if prepared is None:
        return

    offset, size, info = prepared
    if _resolve_byte_swap(field_def, env):
        info = info.byte_swap
    required_bytes = (offset + size).bytes
    if len(buf) < required_bytes:
        buf.extend(b"\x00" * (required_bytes - len(buf)))

    bits_set(buf, offset, info)


def encode(
    struct_layout: StructLayout,
    struct_instance: StructInstance,
    buf: bytearray,
    padding_alignment_bits: int = _DEFAULT_PADDING_ALIGNMENT_BITS,
) -> bytearray:
    """Encode decode() result into a bytearray.

    Parameters
    ----------
    struct_layout : StructLayout
        The structural layout bundle used to resolve the root definition and
        its type dictionary via ``struct_layout.type_dict``.
    struct_instance : StructInstance
        The structure instance to encode.
    buf : bytearray
        The base bytearray instance to write into.
    padding_alignment_bits : int, optional
        The padding alignment boundary in bits, by default 32.

    Returns
    -------
    bytearray
        The encoded bytearray.
    """
    _validate_struct_instance(struct_instance)
    _validate_padding_alignment_bits(padding_alignment_bits)
    if not isinstance(struct_layout, StructLayout):
        raise TypeError("encode() expects StructLayout for struct_layout")
    if struct_layout.type_dict is None:
        raise ValueError("StructLayout.type_dict is required for encode()")

    type_dict = struct_layout.type_dict
    env: dict[str, Any] = {}
    has_padding = False

    for field_value in struct_instance.field_instances:
        field_def = field_value.field_def
        repeat = _resolve_repeat(field_def.repeat, env)
        if _is_padding_field_def(field_def):
            has_padding = True
        value = field_value.value
        if _is_padding_field_def(field_def):
            padding_size = _resolve_info_size(field_def.size, env)
            value = bytearray(padding_size.bytes)
        if repeat is not None and repeat > 1:
            current_offset = _resolve_info_size(field_def.offset, env)
            values = list(value)

            for i in range(repeat):
                field_def_repeat = _repeated_field_def(field_def, i,
                                                       current_offset,
                                                       field_def.size)
                resolved_size = _resolve_info_size(field_def_repeat.size, env)
                encode_field(field_def_repeat, values[i], buf, env, type_dict,
                             padding_alignment_bits)
                env[field_def_repeat.name] = values[i]
                if isinstance(current_offset, InfoSize):
                    current_offset += resolved_size
            continue

        encode_field(field_def, value, buf, env, type_dict,
                     padding_alignment_bits)
        env[field_def.name] = value

    if has_padding and struct_instance.size.bytes > len(buf):
        buf.extend(b"\x00" * (struct_instance.size.bytes - len(buf)))

    return buf


def decode_field(
    field_def: FieldDef,
    data: bytearray | bytes,
    env: dict[str, Any] | None = None,
    type_dict: TypeDict | None = None,
    padding_alignment_bits: int = _DEFAULT_PADDING_ALIGNMENT_BITS,
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
    type_dict : TypeDict | None, optional
        Type dictionaries including structure and enum definitions,
        by default None.
    Returns
    -------
    FieldInstance | None
        The decoded field instance, or None when size is zero.
    """
    if env is None:
        env = {}
    offset = _resolve_info_size(field_def.offset, env)
    size = _resolve_info_size(field_def.size, env)
    if size.byte == 0 and size.bit == 0:
        return None
    info = bits_get(data, offset, size, scale=field_def.scale)
    byte_swap = _resolve_byte_swap(field_def, env)
    if byte_swap:
        info = info.byte_swap
    resolved_type = _resolve_field_type(field_def.type, type_dict, env)
    nested_value = None
    if isinstance(resolved_type, StructDef):
        nested_layout = _layout_for_struct_def(resolved_type,
                                               type_dict,
                                               name=field_def.name)
        nested_value = decode(nested_layout, bytearray(info.to_bytes),
                              padding_alignment_bits)
        actual_size = nested_value.size
    else:
        actual_size = info.info_size
    resolved_field_def = FieldDef(
        name=field_def.name,
        offset=offset,
        size=actual_size,
        type=resolved_type,
        scale=field_def.scale,
        repeat=field_def.repeat,
        description=field_def.description,
        range_expression=field_def.range_expression,
        enum_def_name=field_def.enum_def_name,
        byte_swap=byte_swap,
    )
    if isinstance(resolved_type, StructDef):
        return FieldInstance(
            field_def=resolved_field_def,
            value=nested_value,
        )
    if resolved_type == "bool":
        return FieldInstance.from_value(resolved_field_def,
                                        info.to_bool,
                                        type_dict=type_dict)
    if resolved_type == "signed int":
        return FieldInstance.from_value(resolved_field_def,
                                        info.to_signed_int,
                                        type_dict=type_dict)
    if resolved_type in ["int", "unsigned int"]:
        return FieldInstance.from_value(resolved_field_def,
                                        info.to_unsigned_int,
                                        type_dict=type_dict)
    if resolved_type == "float":
        return FieldInstance.from_value(resolved_field_def,
                                        info.to_float,
                                        type_dict=type_dict)
    if resolved_type in ["bytearray", "bytes"]:
        return FieldInstance.from_value(resolved_field_def,
                                        info.to_bytes,
                                        type_dict=type_dict)
    return FieldInstance.from_value(resolved_field_def,
                                    info.raw_value,
                                    type_dict=type_dict)


def _layout_for_struct_def(struct_def: StructDef,
                           type_dict: TypeDict | None = None,
                           name: str | None = None) -> StructLayout:
    """Create a StructLayout for a StructDef and optional TypeDict."""
    resolved_name = name or struct_def.name or "StructLayout"
    if type_dict is None:
        resolved_type_dict = TypeDict(struct_dict={resolved_name: struct_def})
    else:
        struct_dict = dict(type_dict.struct_dict.items_dict())
        if resolved_name not in struct_dict:
            struct_dict[resolved_name] = struct_def
        resolved_type_dict = TypeDict(
            enum_dict=type_dict.enum_dict.items_dict(),
            struct_dict=struct_dict,
        )
    return StructLayout(struct_def_name=resolved_name,
                        type_dict=resolved_type_dict)


def decode(
    struct_layout: StructLayout,
    data: bytearray | bytes,
    padding_alignment_bits: int = _DEFAULT_PADDING_ALIGNMENT_BITS,
) -> StructInstance:
    """Decode a bytearray into field values according to a layout.

    Parameters
    ----------
    struct_layout : StructLayout
        A layout bundle that resolves the root structure via
        ``struct_layout.type_dict.struct_dict[struct_layout.struct_def_name]``.
    data : bytearray | bytes
        The data to decode.
    padding_alignment_bits : int, optional
        The padding alignment boundary in bits, by default 32.
    Returns
    -------
    StructInstance
        The decoded structure instance.
    """
    _validate_padding_alignment_bits(padding_alignment_bits)
    if not isinstance(struct_layout, StructLayout):
        raise TypeError("decode() expects StructLayout for struct_layout")
    if struct_layout.type_dict is None:
        raise ValueError("StructLayout.type_dict is required for decode()")

    env = {}
    type_dict = struct_layout.type_dict
    struct_def_obj = type_dict.struct_dict[struct_layout.struct_def_name]
    result = StructInstance(struct_def=struct_def_obj)
    current_position = InfoSize(0, 0)
    padding_index = 0

    def append_padding_until(target_offset: InfoSize) -> None:
        nonlocal current_position, padding_index
        start_bits = current_position.bits
        end_bits = target_offset.bits
        if end_bits <= start_bits:
            return

        chunk_start_bits = start_bits
        while chunk_start_bits < end_bits:
            chunk_start = InfoSize(0, chunk_start_bits)
            bits_to_boundary = chunk_start.align_to(padding_alignment_bits).bits
            chunk_size_bits = bits_to_boundary or padding_alignment_bits
            chunk_end_bits = min(end_bits, chunk_start_bits + chunk_size_bits)
            padding_field_def = FieldDef(
                name=f"padding[{padding_index}]",
                offset=InfoSize(0, chunk_start_bits),
                size=InfoSize(0, chunk_end_bits - chunk_start_bits),
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
        repeat = _resolve_repeat(field_def.repeat, env)
        # Handle non-repeated fields
        if repeat is None or repeat <= 1:
            resolved_offset = _resolve_info_size(field_def.offset, env)
            append_padding_until(resolved_offset)
            field_instance = decode_field(field_def, data, env, type_dict,
                                          padding_alignment_bits)
            if field_instance is not None:
                env[field_instance.field_def.name] = field_instance.value
                result.append_field_instance(field_instance)
                current_position = (resolved_offset +
                                    _resolve_info_size(field_def.size, env))
            continue
        # Handle repeated fields
        current_offset = _resolve_info_size(field_def.offset, env)
        append_padding_until(current_offset)
        for i in range(repeat):
            field_def_repeat = _repeated_field_def(field_def, i, current_offset,
                                                   field_def.size)
            field_instance = decode_field(field_def_repeat, data, env,
                                          type_dict, padding_alignment_bits)
            if field_instance is not None:
                env[field_instance.field_def.name] = field_instance.value
                result.append_field_instance(field_instance)
                actual_size = field_instance.field_def.size
            else:
                actual_size = _resolve_info_size(field_def_repeat.size, env)
            if isinstance(current_offset, InfoSize) and isinstance(
                    actual_size, InfoSize):
                current_offset += actual_size
                current_position = current_offset

    actual_size = InfoSize(0, 0)
    for field_instance in result.field_instances:
        field_def = field_instance.field_def
        if (isinstance(field_def.offset, InfoSize)
                and isinstance(field_def.size, InfoSize)):
            field_end = field_def.offset + field_def.size
            if field_end > actual_size:
                actual_size = field_end
    result.size = actual_size
    append_padding_until(result.size)

    return result


def _get_struct_def(
    struct_def_name: str,
    type_dict: TypeDict | None = None,
    env: dict[str, Any] | None = None,
) -> StructDef | str | None:
    """Get a structure definition from a dictionary or evaluate it.

    Parameters
    ----------
    struct_def_name : str
        The name of the structure definition to get.
    type_dict : TypeDict | None, optional
        Type dictionaries including structure and enum definitions,
        by default None.
    env : dict[str, Any] | None, optional
        The environment for evaluating the structure definition,
        by default None.

    Returns
    -------
    StructDef | str | None
        The structure definition, primitive type, or None if not found.
    """
    struct_dict = None if type_dict is None else type_dict.struct_dict

    if struct_dict and struct_def_name in struct_dict:
        return struct_dict[struct_def_name]

    stleval = SltEval(env)
    try:
        eval_result = stleval.eval(struct_def_name)
    except (SyntaxError, NameError, TypeError, ValueError):
        return None

    if isinstance(eval_result, str) and eval_result in _PRIMITIVE_TYPES:
        return eval_result
    if (isinstance(eval_result, str) and struct_dict
            and eval_result in struct_dict):
        return struct_dict[eval_result]
    return None
