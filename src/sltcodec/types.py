"""Type definitions for structured layout metadata."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import total_ordering
from typing import Any

from sltcalc import SltEval
from sltcore import Info, InfoSize


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
    repeat: int | None = field(
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

    def split_repeat(self,
                     index: int,
                     offset: InfoSize | str | None = None,
                     size: InfoSize | str | None = None) -> "FieldDef":
        """Create a single repeated-field definition for the given index."""
        split_name = f"{self.name}[{index}]"
        split_offset_source = self.offset if offset is None else offset
        split_size_source = self.size if size is None else size
        split_offset = self._replace_name_in_expression(split_offset_source,
                                                        self.name, split_name)
        split_size = self._replace_name_in_expression(split_size_source,
                                                      self.name, split_name)
        split_type = self._replace_name_in_expression(self.type, self.name,
                                                      split_name)
        split_range_expression = self._replace_name_in_expression(
            self.range_expression, self.name, split_name)
        split_byte_swap = self._replace_name_in_expression(
            self.byte_swap, self.name, split_name)

        return FieldDef(name=split_name,
                        offset=split_offset,
                        size=split_size,
                        type=split_type,
                        scale=self.scale,
                        repeat=None,
                        description=self.description,
                        range_expression=split_range_expression,
                        enum_def_name=self.enum_def_name,
                        byte_swap=split_byte_swap)

    @staticmethod
    def _replace_name_in_expression(value: Any, old_name: str,
                                    new_name: str) -> Any:
        """Replace standalone old_name tokens in expression-like strings."""
        if not isinstance(value, str):
            return value
        pattern = (rf"(?<![0-9A-Za-z_]){re.escape(old_name)}"
                   rf"(?![0-9A-Za-z_])")
        return re.sub(pattern, lambda _: new_name, value)

    def __lt__(self, other: object) -> bool:
        """Compare field definitions using a stable serialized sort key."""
        if not isinstance(other, FieldDef):
            return NotImplemented
        return self._sort_key() < other._sort_key()

    def to_dict(self) -> dict[str, Any]:
        """Convert this field definition to a JSON-serializable dictionary."""
        return {
            "name":
            self.name,
            "offset":
            self.offset.serialize() if isinstance(self.offset,
                                                  (Info,
                                                   InfoSize)) else self.offset,
            "size":
            self.size.serialize() if isinstance(self.size,
                                                (Info,
                                                 InfoSize)) else self.size,
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
            -1 if self.repeat is None else self.repeat,
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
                   enum_def_dict: dict[str, EnumDef] | None = None,
                   is_padding: bool = False) -> "FieldInstance":
        """Create a FieldInstance and attach a matched enum item if any."""
        enum_def = cls._resolve_enum_def(field_def, enum_def_dict)
        enum_item = cls._resolve_enum_item(enum_def, value)
        return cls(field_def=field_def,
                   value=value,
                   enum_item=enum_item,
                   is_padding=is_padding)

    @staticmethod
    def _resolve_enum_def(
            field_def: FieldDef,
            enum_def_dict: dict[str, EnumDef] | None) -> EnumDef | None:
        """Resolve enum definition from field metadata or lookup dictionary."""
        if not enum_def_dict:
            return None
        if field_def.enum_def_name is not None:
            return enum_def_dict.get(field_def.enum_def_name)
        if isinstance(field_def.type, str) and field_def.type in enum_def_dict:
            return enum_def_dict[field_def.type]
        return enum_def_dict.get(field_def.name)

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
