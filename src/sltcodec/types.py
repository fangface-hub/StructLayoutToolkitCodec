"""Type definitions for structured layout metadata."""
from __future__ import annotations

import json
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from functools import total_ordering
from typing import Any, Dict, Iterator, Optional

from sltcalc import SltEval
from sltcore import Info, InfoSize

_PRIMITIVE_FIELD_TYPES = {
    "bool",
    "signed int",
    "int",
    "unsigned int",
    "float",
    "bytearray",
    "bytes",
}


@total_ordering
@dataclass(frozen=True)
class EnumDef:
    """An enumeration definition."""
    name: str = field(default_factory=str,
                      metadata={"desc": "The name of the enum"})
    description: str | None = field(
        default=None, metadata={"desc": "The description of the enum"})
    values: dict[str, int] = field(
        default_factory=dict,
        metadata={"desc": "The mapping of enum names to integer values"},
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert this enum definition to a JSON-serializable dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "values": self.values,
        }

    def to_json(self) -> str:
        """Convert this enum definition to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnumDef":
        """Create an enum definition from a JSON-serializable dictionary."""
        name = data.get("name", "")
        description = data.get("description")
        values = data.get("values", {})
        return cls(name=name, description=description, values=values)

    def serialize(self) -> dict[str, Any]:
        """Serialize this enum definition with an explicit type tag."""
        return {
            "__type__": "EnumDef",
            "name": self.name,
            "description": self.description,
            "values": self.values,
        }

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> "EnumDef":
        """Deserialize an enum definition from a typed dictionary."""
        if data.get("__type__") != "EnumDef":
            raise ValueError("Invalid EnumDef payload")
        return cls(
            name=data.get("name", ""),
            description=data.get("description"),
            values=data.get("values", {}),
        )

    @classmethod
    def from_json(cls, data: str) -> "EnumDef":
        """Create an enum definition from a JSON string."""
        return cls.from_dict(json.loads(data))

    def __lt__(self, other: object) -> bool:
        """Compare enum definitions using a stable serialized sort key."""
        if not isinstance(other, EnumDef):
            return NotImplemented
        return self._sort_key() < other._sort_key()

    def _sort_key(self) -> tuple[Any, ...]:
        """Build a stable comparison key for ordering enum definitions."""
        return (
            self.name,
            "" if self.description is None else self.description,
            json.dumps(self.values, sort_keys=True),
        )


@total_ordering
@dataclass(frozen=True)
class FieldDef:
    """A field in a structured layout."""
    name: str = field(default_factory=str,
                      metadata={"desc": "The name of the field"})
    offset: InfoSize | str = field(default_factory=InfoSize,
                                   metadata={"desc": "The offset of the field"})
    size: InfoSize | str = field(default_factory=InfoSize,
                                 metadata={"desc": "The size of the field"})
    type: str | "StructDef" = field(default_factory=str,
                                    metadata={"desc": "The type of the field"})
    scale: float = field(default=1.0,
                         metadata={"desc": "The scale of the field"})
    repeat: int | str | None = field(
        default=None, metadata={"desc": "The repeat count of the field"})
    description: str | None = field(
        default=None, metadata={"desc": "The description of the field"})
    range_expression: str | None = field(
        default=None, metadata={"desc": "The value range expression"})
    enum_def_name: str | None = field(
        default=None,
        metadata={"desc": "The name of the enum definition for the field"})
    byte_swap: bool | str = field(
        default=False,
        metadata={"desc": "Whether to reverse the field byte order"})

    def __lt__(self, other: object) -> bool:
        """Compare field definitions using a stable serialized sort key."""
        if not isinstance(other, FieldDef):
            return NotImplemented
        return self._sort_key() < other._sort_key()

    def to_dict(self) -> dict[str, Any]:
        """Convert this field definition to a JSON-serializable dictionary."""

        def _serialize_info_like(value: Any) -> Any:
            if isinstance(value, (Info, InfoSize)):
                return json.loads(value.to_json())
            return value

        return {
            "name":
            self.name,
            "offset":
            _serialize_info_like(self.offset),
            "size":
            _serialize_info_like(self.size),
            "type": {
                "__type__": "StructDef",
                "fields": self.type.to_dict(),
            } if isinstance(self.type, StructDef) else {
                "__type__": "StructDef",
                "fields": [field.to_dict() for field in self.type],
            } if isinstance(self.type, list) else self.type,
            "scale":
            self.scale,
            "repeat":
            self.repeat,
            "description":
            self.description,
            "range_expression":
            self.range_expression,
            "enum_def_name":
            self.enum_def_name,
            "byte_swap":
            self.byte_swap,
        }

    def to_json(self) -> str:
        """Convert this field definition to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldDef":
        """Create a field definition from a JSON-serializable dictionary."""
        name = data.get("name", "")
        offset_data = data.get("offset")
        size_data = data.get("size")
        type_data = data.get("type")
        scale = data.get("scale", 1.0)
        repeat = data.get("repeat")
        description = data.get("description")
        range_expression = data.get("range_expression")
        enum_def_name = data.get("enum_def_name")
        byte_swap = data.get("byte_swap", False)

        def _deserialize_info_like(value: Any) -> Any:
            if isinstance(value, dict):
                value_type = value.get("__type__")
                if value_type == "Info":
                    return Info.deserialize(json.dumps(value))
                if value_type == "InfoSize":
                    return InfoSize.deserialize(json.dumps(value))
                return value
            if not isinstance(value, str):
                return value
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                return value
            if (isinstance(parsed_value, dict)
                    and parsed_value.get("__type__") == "Info"):
                return Info.deserialize(value)
            if (isinstance(parsed_value, dict)
                    and parsed_value.get("__type__") == "InfoSize"):
                return InfoSize.deserialize(value)
            return value

        offset = _deserialize_info_like(offset_data)
        size = _deserialize_info_like(size_data)

        if (isinstance(type_data, dict)
                and type_data.get("__type__") == "StructDef"):
            type_value = StructDef.from_dict(type_data["fields"])
        elif isinstance(type_data, list):
            # Backward-compatibility for legacy list-based nested types.
            type_value = StructDef.from_dict(type_data)
        else:
            type_value = type_data

        return cls(
            name=name,
            offset=offset,
            size=size,
            type=type_value,
            scale=scale,
            repeat=repeat,
            description=description,
            range_expression=range_expression,
            enum_def_name=enum_def_name,
            byte_swap=byte_swap,
        )

    @classmethod
    def from_json(cls, data: str) -> "FieldDef":
        """Create a field definition from a JSON string."""
        return cls.from_dict(json.loads(data))

    def _sort_key(self) -> tuple[Any, ...]:
        """Build a stable comparison key for ordering field definitions."""
        return (
            self._sortable_info_size_or_expr(self.offset),
            self._sortable_info_size_or_expr(self.size),
            self.name,
            self._sortable_type(self.type),
            self.scale,
            self._sortable_repeat(self.repeat),
            "" if self.description is None else self.description,
            "" if self.range_expression is None else self.range_expression,
            "" if self.enum_def_name is None else self.enum_def_name,
            self._sortable_byte_swap(self.byte_swap),
        )

    @staticmethod
    def _sortable_info_size_or_expr(value: InfoSize | str) -> tuple[Any, ...]:
        """Build a comparable key for InfoSize-or-expression values."""
        if isinstance(value, InfoSize):
            return (0, value.byte, value.bit)
        return (1, value)

    @staticmethod
    def _sortable_repeat(value: int | str | None) -> tuple[int, int | str]:
        """Build a comparable key for static or expression repeat counts."""
        if value is None:
            return 0, -1
        if isinstance(value, int):
            return 1, value
        return 2, value

    @staticmethod
    def _sortable_type(value: str | "StructDef") -> tuple[Any, ...]:
        """Build a comparable key for primitive or nested field types."""
        if isinstance(value, StructDef):
            return (0, json.dumps(value.to_dict(), sort_keys=True))
        return (1, value)

    @staticmethod
    def _sortable_byte_swap(value: bool | str) -> tuple[int, str]:
        """Build a comparable key for a byte-swap flag or expression."""
        if isinstance(value, bool):
            return 0, str(value)
        return 1, value


@total_ordering
@dataclass(frozen=True)
class FieldInstance:
    """A decoded/encodable field value with its field definition."""
    field_def: FieldDef = field(metadata={"desc": "The field definition"})
    value: Any = field(metadata={"desc": "The decoded/encodable value"})
    enum_item: tuple[str, int] | None = field(
        default=None,
        metadata={"desc": "Matched enum item for this value"},
    )
    is_padding: bool = field(
        default=False,
        metadata={"desc": "Whether this field instance represents padding"},
    )

    def __lt__(self, other: object) -> bool:
        """Compare field instances using their field definition order."""
        if not isinstance(other, FieldInstance):
            return NotImplemented
        return self.field_def < other.field_def

    def range_check(self, env: dict[str, Any] | None = None) -> Any | None:
        """Evaluate range_expression and return its evaluated result."""
        range_expression = self.field_def.range_expression
        if range_expression is None:
            return None

        eval_env = {} if env is None else dict(env)
        eval_env[self.field_def.name] = self.value
        stleval = SltEval(eval_env)
        return stleval.eval(range_expression)

    @classmethod
    def from_value(cls,
                   field_def: FieldDef,
                   value: Any,
                   type_dict: "TypeDict | None" = None,
                   is_padding: bool = False) -> "FieldInstance":
        """Create a FieldInstance and attach a matched enum item if any."""
        enum_def = cls._resolve_enum_def(field_def, type_dict)
        enum_item = cls._resolve_enum_item(enum_def, value)
        return cls(field_def=field_def,
                   value=value,
                   enum_item=enum_item,
                   is_padding=is_padding)

    def with_value(self,
                   value: Any,
                   type_dict: "TypeDict | None" = None) -> "FieldInstance":
        """Return a new FieldInstance with the given value applied."""
        return type(self).from_value(field_def=self.field_def,
                                     value=value,
                                     type_dict=type_dict,
                                     is_padding=self.is_padding)

    @staticmethod
    def _resolve_enum_def(field_def: FieldDef,
                          type_dict: "TypeDict | None") -> EnumDef | None:
        """Resolve enum definition from field metadata or lookup dictionary."""
        if type_dict is None:
            return None
        enum_dict = type_dict.enum_dict
        if len(enum_dict) == 0:
            return None
        if field_def.enum_def_name is not None:
            return enum_dict.get(field_def.enum_def_name)
        if isinstance(field_def.type, str) and field_def.type in enum_dict:
            return enum_dict[field_def.type]
        return enum_dict.get(field_def.name)

    @staticmethod
    def _resolve_enum_item(enum_def: EnumDef | None,
                           value: Any) -> tuple[str, int] | None:
        """Resolve one enum values item that matches the given value."""
        if enum_def is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        for enum_name, enum_value in enum_def.values.items():
            if enum_value == value:
                return enum_name, enum_value
        return None


@total_ordering
@dataclass(frozen=True)
class StructDef:
    """A structured layout definition that groups multiple fields."""
    name: str = field(default_factory=str,
                      metadata={"desc": "The name of the structure"})
    description: str = field(
        default_factory=str,
        metadata={"desc": "The description of the structure"},
    )
    fields: list[FieldDef] = field(
        default_factory=list,
        metadata={"desc": "The fields of the structure"},
    )
    _fields_by_struct_def_name: dict[str, list[FieldDef]] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        """Build field index grouped by referenced struct definition name."""
        self._rebuild_struct_def_name_index()

    def __lt__(self, other: object) -> bool:
        """Compare structure definitions using a stable serialized sort key."""
        if not isinstance(other, StructDef):
            return NotImplemented
        return self._sort_key() < other._sort_key()

    def _sort_key(self) -> tuple[Any, ...]:
        """Build a stable comparison key for ordering structure definitions."""
        return (
            self.name,
            "" if self.description is None else self.description,
            json.dumps([field.to_dict() for field in self.fields],
                       sort_keys=True),
        )

    def get_fields(self, struct_def_name: str) -> list[FieldDef]:
        """Return fields that reference the given struct definition name."""
        self._rebuild_struct_def_name_index()
        return list(self._fields_by_struct_def_name.get(struct_def_name, []))

    def get_field(self, struct_def_name: str) -> FieldDef | None:
        """Return the first field that references the given name."""
        self._rebuild_struct_def_name_index()
        fields = self._fields_by_struct_def_name.get(struct_def_name)
        if not fields:
            return None
        return fields[0]

    @staticmethod
    def _field_struct_def_name(field_def: FieldDef) -> str | None:
        """Resolve struct definition name referenced by a field type."""
        field_type = field_def.type
        if isinstance(field_type, StructDef):
            return field_type.name or None
        if (isinstance(field_type, str) and field_type
                and field_type not in _PRIMITIVE_FIELD_TYPES):
            return field_type
        return None

    def _rebuild_struct_def_name_index(self) -> None:
        """Rebuild struct_def_name index from current fields."""
        fields_by_name: dict[str, list[FieldDef]] = {}
        for field_def in self.fields:
            struct_def_name = self._field_struct_def_name(field_def)
            if struct_def_name is None:
                continue
            if struct_def_name not in fields_by_name:
                fields_by_name[struct_def_name] = []
            fields_by_name[struct_def_name].append(field_def)
        object.__setattr__(self, "_fields_by_struct_def_name", fields_by_name)

    def to_dict(self) -> dict[str, Any]:
        """Convert this structure definition to JSON-serializable data."""
        return {
            "name": self.name,
            "description": self.description,
            "fields": [field_def.to_dict() for field_def in self.fields],
        }

    def to_json(self) -> str:
        """Convert this structure definition to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any] | list[dict[str, Any]],
    ) -> "StructDef":
        """Create a structure definition from JSON-serializable data."""
        if isinstance(data, list):
            # Backward-compatibility for legacy list-only StructDef payloads.
            return cls(fields=[FieldDef.from_dict(item) for item in data])
        name = data.get("name", "")
        description = data.get("description", "")
        fields_data = data.get("fields", [])
        fields = [FieldDef.from_dict(item) for item in fields_data]
        return cls(name=name, description=description, fields=fields)

    @classmethod
    def from_json(cls, data: str) -> "StructDef":
        """Create a structure definition from a JSON string."""
        return cls.from_dict(json.loads(data))


@total_ordering
@dataclass
class StructInstance:
    """A decoded/encodable structure instance."""
    struct_def: StructDef = field(
        default_factory=StructDef,
        metadata={"desc": "The structure definition"},
    )
    field_instances: list[FieldInstance] = field(
        default_factory=list,
        metadata={"desc": "The decoded/encodable field instances"},
    )
    size: InfoSize = field(
        default_factory=InfoSize,
        metadata={"desc": "The total size of the structure instance"},
    )
    _field_instances_by_field_def_name: dict[str, list[FieldInstance]] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        """Normalize stored field instances to sorted order."""
        self._sort_field_instances()
        self._update_size()
        self._rebuild_padding_field_instances()

    def append_field_instance(self, field_instance: FieldInstance) -> None:
        """Append one field instance to this structure instance."""
        if not isinstance(field_instance, FieldInstance):
            raise TypeError("field_instance must be FieldInstance")
        self.field_instances.append(field_instance)
        self._update_size()
        self._rebuild_padding_field_instances()

    def extend_field_instances(self,
                               field_instances: list[FieldInstance]) -> None:
        """Append multiple field instances to this structure instance."""
        for field_instance in field_instances:
            if not isinstance(field_instance, FieldInstance):
                raise TypeError("field_instance must be FieldInstance")
        self.field_instances.extend(field_instances)
        self._update_size()
        self._rebuild_padding_field_instances()

    def __iter__(self):
        """Iterate over stored field instances."""
        return iter(self.field_instances)

    def __len__(self) -> int:
        """Return the number of stored field instances."""
        return len(self.field_instances)

    def __getitem__(self, index: int) -> FieldInstance:
        """Return one field instance by index."""
        return self.field_instances[index]

    def get_fields(self, field_def_name: str) -> list[FieldInstance]:
        """Return field instances that match the given field definition name."""
        return list(
            self._field_instances_by_field_def_name.get(field_def_name, []))

    def get_field(self, field_def_name: str) -> FieldInstance | None:
        """Return the first field instance that matches the given name."""
        field_instances = self._field_instances_by_field_def_name.get(
            field_def_name)
        if not field_instances:
            return None
        return field_instances[0]

    def __lt__(self, other: object) -> bool:
        """Compare structure instances using a stable serialized sort key."""
        if not isinstance(other, StructInstance):
            return NotImplemented
        return self._sort_key() < other._sort_key()

    def _sort_key(self) -> tuple[Any, ...]:
        """Build a stable comparison key for ordering structure instances."""
        return (
            self.struct_def._sort_key(),
            json.dumps([
                field_instance.to_dict()
                for field_instance in self.field_instances
            ],
                       sort_keys=True),
        )

    def _sort_field_instances(self) -> None:
        """Keep field instances sorted by FieldDef order."""
        self.field_instances.sort()

    def _rebuild_field_def_name_index(self) -> None:
        """Rebuild field_def.name index from current field instances."""
        field_instances_by_name: dict[str, list[FieldInstance]] = {}
        for field_instance in self.field_instances:
            field_def_name = field_instance.field_def.name
            if field_def_name not in field_instances_by_name:
                field_instances_by_name[field_def_name] = []
            field_instances_by_name[field_def_name].append(field_instance)
        self._field_instances_by_field_def_name = field_instances_by_name

    def _rebuild_padding_field_instances(self) -> None:
        """Rebuild padding field instances for gaps between stored values."""
        non_padding_instances = [
            field_instance for field_instance in self.field_instances
            if not field_instance.is_padding
        ]
        non_padding_instances.sort()

        has_unresolved_layout = any(
            not isinstance(field_instance.field_def.offset, InfoSize)
            or not isinstance(field_instance.field_def.size, InfoSize)
            for field_instance in non_padding_instances)
        if has_unresolved_layout:
            # Layout expressions are resolved later in codec paths.
            self.field_instances = non_padding_instances
            self._sort_field_instances()
            self._update_size()
            self._rebuild_field_def_name_index()
            return

        rebuilt_instances: list[FieldInstance] = []
        current_offset = InfoSize(0, 0)
        padding_index = 0

        for field_instance in non_padding_instances:
            field_def = field_instance.field_def
            field_offset = field_def.offset
            field_size = field_def.size
            if field_offset > current_offset:
                gap_size = field_offset - current_offset
                if gap_size.byte > 0 or gap_size.bit > 0:
                    rebuilt_instances.append(
                        FieldInstance(
                            field_def=FieldDef(
                                name=f"padding[{padding_index}]",
                                offset=current_offset,
                                size=gap_size,
                                type="bytes",
                                description="Auto-generated padding",
                            ),
                            value=bytearray(gap_size.byte),
                            is_padding=True,
                        ))
                    padding_index += 1
            rebuilt_instances.append(field_instance)
            current_offset = field_offset + field_size

        if self.size > current_offset:
            gap_size = self.size - current_offset
            if gap_size.byte > 0 or gap_size.bit > 0:
                rebuilt_instances.append(
                    FieldInstance(
                        field_def=FieldDef(
                            name=f"padding[{padding_index}]",
                            offset=current_offset,
                            size=gap_size,
                            type="bytes",
                            description="Auto-generated padding",
                        ),
                        value=bytearray(gap_size.byte),
                        is_padding=True,
                    ))

        self.field_instances = rebuilt_instances
        self._sort_field_instances()
        self._update_size()
        self._rebuild_field_def_name_index()

    def _update_size(self) -> None:
        """Update the instance size from the current field layout."""
        if not self.field_instances:
            return

        max_end_offset = InfoSize(0, 0)
        for field_instance in self.field_instances:
            field_def = field_instance.field_def
            if not isinstance(field_def.offset, InfoSize):
                continue
            if not isinstance(field_def.size, InfoSize):
                continue
            field_offset = field_def.offset
            field_size = field_def.size
            field_end = field_offset + field_size
            if field_end > max_end_offset:
                max_end_offset = field_end

        if max_end_offset > self.size:
            self.size = max_end_offset


@dataclass
class EnumDict(MutableMapping):
    """A dictionary-like container for EnumDef objects."""
    _items: Dict[str, "EnumDef"]

    def __init__(self, items: Optional[Dict[str, "EnumDef"]] = None):
        self._items = items or {}

    def __getitem__(self, key: str) -> "EnumDef":
        return self._items[key]

    def __setitem__(self, key: str, value: "EnumDef"):
        self._items[key] = value

    def __delitem__(self, key: str):
        del self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def items_dict(self) -> Dict[str, "EnumDef"]:
        """Return the underlying dictionary of EnumDef objects.
           Returns:
               Dict[str, EnumDef]: The underlying dictionary
               of EnumDef objects."""
        return self._items


@dataclass
class StructDict(MutableMapping):
    """A dictionary-like container for StructDef objects. """
    _items: Dict[str, "StructDef"]

    def __init__(self, items: Optional[Dict[str, "StructDef"]] = None):
        self._items = items or {}

    def __getitem__(self, key: str) -> "StructDef":
        return self._items[key]

    def __setitem__(self, key: str, value: "StructDef"):
        self._items[key] = value

    def __delitem__(self, key: str):
        del self._items[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def items_dict(self) -> Dict[str, "StructDef"]:
        """Return the underlying dictionary of StructDef objects.
           Returns:
               Dict[str, StructDef]: The underlying dictionary
               of StructDef objects."""
        return self._items


@dataclass
class TypeDict:
    """A dictionary-like container for EnumDef and StructDef objects."""
    enum_dict: EnumDict
    struct_dict: StructDict

    def __init__(
        self,
        enum_dict: Optional[Dict[str, "EnumDef"]] = None,
        struct_dict: Optional[Dict[str, "StructDef"]] = None,
    ):
        """Initialize TypeDict with optional EnumDef
           and StructDef dictionaries."""
        self.enum_dict = EnumDict(enum_dict)
        self.struct_dict = StructDict(struct_dict)


@dataclass
class StructLayout:
    """A structured layout that combines a StructDef and its TypeDict."""
    struct_def_name: str
    type_dict: TypeDict

    def __init__(self, struct_def_name: str, type_dict: TypeDict):
        """Initialize StructLayout with a structure definition name
           and a TypeDict containing EnumDef and StructDef objects."""
        self.struct_def_name = struct_def_name
        self.type_dict = type_dict
