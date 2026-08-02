"""Encoding and decoding of structured layouts into bytearrays."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sltcalc import SltEval
from sltcore import Info, InfoSize, bits_get, bits_set


@dataclass(frozen=True)
class FieldDef:
    """A field in a structured layout."""
    name: str = field(default_factory=str,
                      metadata={"desc": "The name of the field"})
    offset: InfoSize | str = field(default_factory=InfoSize,
                                   metadata={"desc": "The offset of the field"})
    size: InfoSize | str = field(default_factory=InfoSize,
                                 metadata={"desc": "The size of the field"})
    type: str = field(default_factory=str,
                      metadata={"desc": "The type of the field"})
    repeat: int | None = field(
        default=None, metadata={"desc": "The repeat count of the field"})


def _resolve_offset(field_def: FieldDef, env: dict[str, Any]) -> InfoSize:
    """Resolve a field offset that can be static or expression-based."""
    if isinstance(field_def.offset, str):
        stleval = SltEval(env)
        offset_byte = stleval.eval(field_def.offset)
        return InfoSize(offset_byte, 0)
    return field_def.offset


def _resolve_size(field_def: FieldDef, env: dict[str, Any]) -> InfoSize:
    """Resolve a field size that can be static or expression-based."""
    if isinstance(field_def.size, str):
        stleval = SltEval(env)
        size_byte = stleval.eval(field_def.size)
        return InfoSize(size_byte, 0)
    return field_def.size


def _to_info(field_def: FieldDef, value: Any, size: InfoSize,
             field_def_dict: dict[str, Any] | None) -> Info:
    """Convert a typed value into an Info object for bits_set."""
    if field_def.type == "bool":
        return Info.from_bool(bool(value), size)
    if field_def.type == "signed int":
        return Info.from_signed_int(int(value), size)
    if field_def.type in ["int", "unsigned int"]:
        return Info.from_unsigned_int(int(value), size)
    if field_def.type == "float":
        return Info.from_float(float(value), size)
    if field_def.type in ["bytearray", "bytes"]:
        return Info.from_bytes(bytes(value), size)

    if field_def_dict and field_def.type in field_def_dict:
        nested = encode(value, field_def_dict)
        return Info.from_bytes(bytes(nested), size)

    if isinstance(value, (bytes, bytearray)):
        return Info.from_bytes(bytes(value), size)
    if isinstance(value, bool):
        return Info.from_bool(value, size)
    if isinstance(value, int):
        return Info.from_unsigned_int(value, size)

    return Info(raw_value=value, info_size=size)


def encode_field(field_def: FieldDef,
                 value: Any,
                 buf: bytearray,
                 env: dict[str, Any] | None = None,
                 field_def_dict: dict[str, Any] | None = None) -> None:
    """Encode a single field into a bytearray."""
    if env is None:
        env = {}

    offset = _resolve_offset(field_def, env)
    size = _resolve_size(field_def, env)
    if size.byte == 0 and size.bit == 0:
        return

    required_bytes = (offset + size).bytes
    if len(buf) < required_bytes:
        buf.extend(b"\x00" * (required_bytes - len(buf)))

    info = _to_info(field_def, value, size, field_def_dict)
    bits_set(buf, offset, info)


def encode(result: list[tuple[FieldDef, Any]],
           field_def_dict: dict[str, Any] | None = None) -> bytearray:
    """Encode decode() result into a bytearray.

    Parameters
    ----------
    result : list[tuple[FieldDef, Any]]
        The decode() result to encode.
    field_def_dict : dict[str, Any] | None, optional
        A dictionary of field definitions, by default None.

    Returns
    -------
    bytearray
        The encoded bytearray.
    """
    buf = bytearray()
    env: dict[str, Any] = {}

    for field_def, value in result:
        if field_def.repeat is not None and field_def.repeat > 1:
            current_offset = _resolve_offset(field_def, env)
            values = list(value)

            for i in range(field_def.repeat):
                field_def_repeat = FieldDef(name=f"{field_def.name}[{i}]",
                                            offset=current_offset,
                                            size=field_def.size,
                                            type=field_def.type,
                                            repeat=None)
                encode_field(field_def_repeat, values[i], buf, env,
                             field_def_dict)
                env[field_def_repeat.name] = values[i]
                if isinstance(current_offset, InfoSize) and isinstance(
                        field_def.size, InfoSize):
                    current_offset += field_def.size
            continue

        encode_field(field_def, value, buf, env, field_def_dict)
        env[field_def.name] = value

    return buf


def decode_field(field_def: FieldDef,
                 data: bytearray | bytes,
                 env: dict[str, Any] | None = None,
                 field_def_dict: dict[str, Any] | None = None) -> Any:
    """Decode a single field from a bytearray according to a field definition.

    Parameters
    ----------
    field_def : FieldDef
        The definition of the field to decode.
    data : bytearray | bytes
        The data to decode.
    env : dict[str, Any] | None, optional
        The environment for evaluating expressions, by default None.
    field_def_dict : dict[str, Any] | None, optional
        A dictionary of field definitions, by default None.
    Returns
    -------
    Any
        The decoded field value.
    """
    if env is None:
        env = {}
    offset = _resolve_offset(field_def, env)
    size = _resolve_size(field_def, env)
    if size.byte == 0 and size.bit == 0:
        return None
    info = bits_get(data, offset, size)
    if field_def.type == "bool":
        return info.to_bool
    if field_def.type in ["int", "signed int"]:
        return info.to_signed_int
    if field_def.type == "unsigned int":
        return info.to_unsigned_int
    if field_def.type == "float":
        return info.to_float
    if field_def.type in ["bytearray", "bytes"]:
        return info.to_bytes
    if field_def_dict and field_def.type in field_def_dict:
        sub_field_defs = field_def_dict[field_def.type]
        sub_values = decode(sub_field_defs, info.to_bytes, field_def_dict)
        return sub_values
    return info.raw_value


def decode(
        field_defs: list[FieldDef],
        data: bytearray | bytes,
        field_def_dict: dict[str, Any] | None = None
) -> list[tuple[FieldDef, Any]]:
    """Decode a bytearray into field values according to a layout.

    Parameters
    ----------
    field_defs : list[FieldDef]
        The definitions of the fields to decode.
    data : bytearray | bytes
        The data to decode.
    field_def_dict : dict[str, Any] | None, optional
        A dictionary of field definitions, by default None.
    Returns
    -------
    list[tuple[FieldDef, Any]]
        The decoded field values.
    """
    result: list[tuple[FieldDef, Any]] = []
    env = {}

    for field_def in field_defs:
        # Handle non-repeated fields
        if field_def.repeat is None or field_def.repeat <= 1:
            value = decode_field(field_def, data, env, field_def_dict)
            if value is not None:
                env[field_def.name] = value
                result.append((field_def, value))
            continue
        # Handle repeated fields
        current_offset = field_def.offset
        for i in range(field_def.repeat):
            field_def_repeat = FieldDef(name=f"{field_def.name}[{i}]",
                                        offset=current_offset,
                                        size=field_def.size,
                                        type=field_def.type,
                                        repeat=None)
            value = decode_field(field_def_repeat, data, env, field_def_dict)
            if value is not None:
                env[field_def_repeat.name] = value
                result.append((field_def_repeat, value))
            if isinstance(current_offset, InfoSize) and isinstance(
                    field_def.size, InfoSize):
                current_offset += field_def.size

    return result
