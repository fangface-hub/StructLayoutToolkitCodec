"""Encoding and decoding of structured layouts into bytearrays."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sltcalc import SltEval
from sltcore import Info, InfoSize, bits_get, bits_set

_PRIMITIVE_TYPES = {
    "bool",
    "signed int",
    "int",
    "unsigned int",
    "float",
    "bytearray",
    "bytes",
}


@dataclass(frozen=True)
class FieldDef:
    """A field in a structured layout."""
    name: str = field(default_factory=str,
                      metadata={"desc": "The name of the field"})
    offset: InfoSize | str = field(default_factory=InfoSize,
                                   metadata={"desc": "The offset of the field"})
    size: InfoSize | str = field(default_factory=InfoSize,
                                 metadata={"desc": "The size of the field"})
    type: str | list["FieldDef"] = field(
        default_factory=str, metadata={"desc": "The type of the field"})
    scale: float = field(default=1.0,
                         metadata={"desc": "The scale of the field"})
    repeat: int | None = field(
        default=None, metadata={"desc": "The repeat count of the field"})
    description: str | None = field(
        default=None, metadata={"desc": "The description of the field"})

    def split_repeat(self,
                     index: int,
                     offset: InfoSize | str | None = None) -> "FieldDef":
        """Create a single repeated-field definition for the given index.

        Parameters
        ----------
        index : int
            The index of the repeated field.
        offset : InfoSize | str | None, optional
            The offset of the repeated field, by default None.
        """
        return FieldDef(name=f"{self.name}[{index}]",
                        offset=self.offset if offset is None else offset,
                        size=self.size,
                        type=self.type,
                        scale=self.scale,
                        repeat=None,
                        description=self.description)

    def to_dict(self) -> dict[str, Any]:
        """Convert this field definition to a JSON-serializable dictionary."""
        return {
            "name": self.name,
            "offset": self._serialize_value(self.offset),
            "size": self._serialize_value(self.size),
            "type": self._serialize_type(self.type),
            "scale": self.scale,
            "repeat": self.repeat,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldDef":
        """Create a field definition from a JSON-serializable dictionary."""
        return cls(
            name=data.get("name", ""),
            offset=cls._deserialize_value(data.get("offset")),
            size=cls._deserialize_value(data.get("size")),
            type=cls._deserialize_type(data.get("type")),
            scale=data.get("scale", 1.0),
            repeat=data.get("repeat"),
            description=data.get("description"),
        )

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, InfoSize):
            return {
                "__type__": "InfoSize",
                "byte": value.byte,
                "bit": value.bit,
            }
        return value

    @classmethod
    def _deserialize_value(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("__type__") == "InfoSize":
            return InfoSize(value["byte"], value["bit"])
        return value

    @staticmethod
    def _serialize_type(value: Any) -> Any:
        if isinstance(value, list):
            return [field.to_dict() for field in value]
        return value

    @classmethod
    def _deserialize_type(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [cls.from_dict(item) for item in value]
        return value


def field_def_to_json(field_def: FieldDef) -> str:
    """Serialize a field definition to a JSON string."""
    return json.dumps(field_def.to_dict(), ensure_ascii=False, indent=2)


def field_def_from_json(data: str) -> FieldDef:
    """Deserialize a field definition from a JSON string."""
    return FieldDef.from_dict(json.loads(data))


def save_field_def_dict(path: str | Path,
                        field_def_dict: dict[str, FieldDef]) -> None:
    """Save a field definition dictionary to a JSON file."""
    payload = {
        name: field_def.to_dict()
        for name, field_def in field_def_dict.items()
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def load_field_def_dict(path: str | Path) -> dict[str, FieldDef]:
    """Load a field definition dictionary from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        name: FieldDef.from_dict(field_def_data)
        for name, field_def_data in data.items()
    }


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


def _resolve_field_type(
        field_type: str | list[FieldDef],
        field_def_dict: dict[str, Any] | None = None,
        env: dict[str, Any] | None = None) -> str | list[FieldDef]:
    """Resolve a field type that can be primitive, named, or nested."""
    if isinstance(field_type, list):
        return field_type
    if field_type in _PRIMITIVE_TYPES:
        return field_type

    sub_field_defs = _get_field_def(field_type, field_def_dict, env)
    if isinstance(sub_field_defs, list):
        return sub_field_defs
    if isinstance(sub_field_defs, str) and sub_field_defs in _PRIMITIVE_TYPES:
        return sub_field_defs
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
    field_def_dict: dict[str, Any] | None = None
) -> tuple[InfoSize, InfoSize, Info] | None:
    """Resolve a field definition into an offset, size, and info payload."""
    offset = _resolve_offset(field_def, env)
    size = _resolve_size(field_def, env)
    if size.byte == 0 and size.bit == 0:
        return None

    resolved_type = _resolve_field_type(field_def.type, field_def_dict, env)
    if isinstance(resolved_type, list):
        nested_bytes = encode(list(value), field_def_dict)
        info = Info.from_bytes(bytes(nested_bytes), size, scale=field_def.scale)
    else:
        info = _encode_primitive(resolved_type, value, size, field_def.scale)
    return offset, size, info


def _normalize_parallel_count(parallel_count: int) -> int:
    """Validate and normalize the requested parallel count."""
    if parallel_count < 1:
        raise ValueError("parallel_count must be greater than or equal to 1")
    return parallel_count


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


def _can_parallelize_repeated_field(field_def: FieldDef,
                                    current_offset: InfoSize | None) -> bool:
    """Check whether repeated-field processing can be parallelized safely."""
    if current_offset is None:
        return False
    if isinstance(field_def.offset, str):
        return False
    if isinstance(field_def.size, str):
        return False
    if (isinstance(field_def.type, str)
            and field_def.type not in _PRIMITIVE_TYPES):
        return False
    return True


def encode_field(field_def: FieldDef,
                 value: Any,
                 buf: bytearray,
                 env: dict[str, Any] | None = None,
                 field_def_dict: dict[str, Any] | None = None) -> None:
    """Encode a single field into a bytearray."""
    if env is None:
        env = {}

    prepared = _prepare_field_info(field_def, value, env, field_def_dict)
    if prepared is None:
        return

    offset, size, info = prepared
    required_bytes = (offset + size).bytes
    if len(buf) < required_bytes:
        buf.extend(b"\x00" * (required_bytes - len(buf)))

    bits_set(buf, offset, info)


def encode(result: list[tuple[FieldDef, Any]],
           field_def_dict: dict[str, Any] | None = None,
           parallel_count: int = 1) -> bytearray:
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
    parallel_count = _normalize_parallel_count(parallel_count)
    buf = bytearray()
    env: dict[str, Any] = {}

    for field_def, value in result:
        if field_def.repeat is not None and field_def.repeat > 1:
            current_offset = _resolve_offset(field_def, env)
            resolved_size = _resolve_size(field_def, env)
            values = list(value)

            if (parallel_count > 1 and isinstance(current_offset, InfoSize)
                    and isinstance(field_def.size, InfoSize) and
                    _can_parallelize_repeated_field(field_def, current_offset)):
                offsets: list[InfoSize] = []
                offset_cursor = current_offset
                for _ in range(field_def.repeat):
                    offsets.append(offset_cursor)
                    offset_cursor += resolved_size

                repeated_fields = [
                    _split_repeated_field(field_def, index, env, offsets[index])
                    for index in range(field_def.repeat)
                ]

                with ThreadPoolExecutor(max_workers=parallel_count) as executor:
                    futures = [
                        executor.submit(_prepare_field_info,
                                        repeated_fields[index], values[index],
                                        env.copy(), field_def_dict)
                        for index in range(field_def.repeat)
                    ]
                    prepared_results = [future.result() for future in futures]

                for index, prepared in enumerate(prepared_results):
                    if prepared is None:
                        continue
                    offset, size, info = prepared
                    required_bytes = (offset + size).bytes
                    if len(buf) < required_bytes:
                        buf.extend(b"\x00" * (required_bytes - len(buf)))
                    bits_set(buf, offset, info)
                    env[repeated_fields[index].name] = values[index]
                continue

            for i in range(field_def.repeat):
                field_def_repeat = _split_repeated_field(
                    field_def, i, env, current_offset)
                encode_field(field_def_repeat, values[i], buf, env,
                             field_def_dict)
                env[field_def_repeat.name] = values[i]
                if isinstance(current_offset, InfoSize) and isinstance(
                        resolved_size, InfoSize):
                    current_offset += resolved_size
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
    info = bits_get(data, offset, size, scale=field_def.scale)
    resolved_type = _resolve_field_type(field_def.type, field_def_dict, env)
    if isinstance(resolved_type, list):
        return decode(resolved_type, bytearray(info.to_bytes), field_def_dict)
    if resolved_type == "bool":
        return info.to_bool
    if resolved_type == "signed int":
        return info.to_signed_int
    if resolved_type in ["int", "unsigned int"]:
        return info.to_unsigned_int
    if resolved_type == "float":
        return info.to_float
    if resolved_type in ["bytearray", "bytes"]:
        return info.to_bytes
    return info.raw_value


def decode(field_defs: list[FieldDef],
           data: bytearray | bytes,
           field_def_dict: dict[str, Any] | None = None,
           parallel_count: int = 1) -> list[tuple[FieldDef, Any]]:
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
    parallel_count = _normalize_parallel_count(parallel_count)
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
        current_offset = _resolve_offset(field_def, env)
        resolved_size = _resolve_size(field_def, env)
        if (parallel_count > 1 and isinstance(current_offset, InfoSize)
                and isinstance(field_def.size, InfoSize)
                and _can_parallelize_repeated_field(field_def, current_offset)):
            offsets: list[InfoSize] = []
            offset_cursor = current_offset
            for _ in range(field_def.repeat):
                offsets.append(offset_cursor)
                offset_cursor += resolved_size

            repeated_fields = [
                _split_repeated_field(field_def, index, env, offsets[index])
                for index in range(field_def.repeat)
            ]

            with ThreadPoolExecutor(max_workers=parallel_count) as executor:
                futures = [
                    executor.submit(decode_field, repeated_fields[index], data,
                                    env.copy(), field_def_dict)
                    for index in range(field_def.repeat)
                ]
                decoded_values = [future.result() for future in futures]

            for index, value in enumerate(decoded_values):
                if value is not None:
                    env[repeated_fields[index].name] = value
                    result.append((repeated_fields[index], value))
            continue

        for i in range(field_def.repeat):
            field_def_repeat = _split_repeated_field(field_def, i, env,
                                                     current_offset)
            value = decode_field(field_def_repeat, data, env, field_def_dict)
            if value is not None:
                env[field_def_repeat.name] = value
                result.append((field_def_repeat, value))
            if isinstance(current_offset, InfoSize) and isinstance(
                    resolved_size, InfoSize):
                current_offset += resolved_size

    return result


def _get_field_def(field_def_name: str,
                   field_def_dict: dict[str, Any] | None = None,
                   env: dict[str, Any] | None = None) -> Any:
    """Get a field definition from a dictionary or evaluate it.

    Parameters
    ----------
    field_def_name : str
        The name of the field definition to get.
    field_def_dict : dict[str, Any] | None, optional
        A dictionary of field definitions, by default None.
    env : dict[str, Any] | None, optional
        The environment for evaluating the field definition, by default None.

    Returns
    -------
    Any
        The field definition, or None if not found.
    """
    if field_def_dict and field_def_name in field_def_dict:
        return field_def_dict[field_def_name]

    stleval = SltEval(env)
    try:
        eval_result = stleval.eval(field_def_name)
    except (SyntaxError, NameError, TypeError, ValueError):
        return None

    if isinstance(eval_result, str) and eval_result in _PRIMITIVE_TYPES:
        return eval_result
    if isinstance(eval_result,
                  str) and field_def_dict and eval_result in field_def_dict:
        return field_def_dict[eval_result]
    return None
