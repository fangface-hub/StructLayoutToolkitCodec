"""Type definitions for structured layout metadata."""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sltcore import Info, InfoSize


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
    enum_type: type[Enum] | None = field(default=None,
                                         metadata={"desc": "The enum type"})

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

        return FieldDef(name=split_name,
                        offset=split_offset,
                        size=split_size,
                        type=split_type,
                        scale=self.scale,
                        repeat=None,
                        description=self.description,
                        range_expression=split_range_expression,
                        enum_type=self.enum_type)

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
            "name": self.name,
            "offset": self._serialize_value(self.offset),
            "size": self._serialize_value(self.size),
            "type": self._serialize_type(self.type),
            "scale": self.scale,
            "repeat": self.repeat,
            "description": self.description,
            "range_expression": self.range_expression,
            "enum_type": self._serialize_enum_type(self.enum_type),
        }

    def to_json(self) -> str:
        """Convert this field definition to a JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

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
            range_expression=data.get("range_expression"),
            enum_type=cls._deserialize_enum_type(data.get("enum_type")),
        )

    @classmethod
    def from_json(cls, data: str) -> "FieldDef":
        """Create a field definition from a JSON string."""
        return cls.from_dict(json.loads(data))

    @staticmethod
    def _serialize_value(value: Any) -> Any:
        if isinstance(value, Info):
            return {
                "__type__": "Info",
                "value": value.to_json(),
            }
        if isinstance(value, InfoSize):
            return {
                "__type__": "InfoSize",
                "value": value.to_json(),
            }
        return value

    @classmethod
    def _deserialize_value(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("__type__") == "Info":
            return Info.from_json(value["value"])
        if isinstance(value, dict) and value.get("__type__") == "InfoSize":
            return InfoSize.from_json(value["value"])
        return value

    @staticmethod
    def _serialize_type(value: Any) -> Any:
        if isinstance(value, StructDef):
            return {
                "__type__": "StructDef",
                "fields": value.to_dict(),
            }
        if isinstance(value, list):
            # Backward-compatibility for legacy list-based nested types.
            return {
                "__type__": "StructDef",
                "fields": [field.to_dict() for field in value],
            }
        return value

    @classmethod
    def _deserialize_type(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("__type__") == "StructDef":
            return StructDef.from_dict(value["fields"])
        if isinstance(value, list):
            # Backward-compatibility for legacy list-based nested types.
            return StructDef.from_dict(value)
        return value

    @staticmethod
    def _serialize_enum_type(value: type[Enum] | None) -> Any:
        if value is None:
            return None
        return {
            "__type__": "EnumType",
            "module": value.__module__,
            "qualname": value.__qualname__,
        }

    @classmethod
    def _deserialize_enum_type(cls, value: Any) -> type[Enum] | None:
        if value is None:
            return None
        if not isinstance(value, dict) or value.get("__type__") != "EnumType":
            return None
        module_name = value.get("module")
        qualname = value.get("qualname")
        if not isinstance(module_name, str) or not isinstance(qualname, str):
            return None
        try:
            module = importlib.import_module(module_name)
            enum_type: Any = module
            for attr in qualname.split("."):
                enum_type = getattr(enum_type, attr)
            if isinstance(enum_type, type) and issubclass(enum_type, Enum):
                return enum_type
        except (ImportError, AttributeError, TypeError):
            return None
        return None

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
            self._sortable_enum_type(self.enum_type),
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
    def _sortable_enum_type(value: type[Enum] | None) -> str:
        """Build a comparable key for enum type metadata."""
        if value is None:
            return ""
        return f"{value.__module__}.{value.__qualname__}"


@dataclass(frozen=True)
class FieldInstance:
    """A decoded/encodable field value with its field definition."""
    field_def: FieldDef = field(metadata={"desc": "The field definition"})
    value: Any = field(metadata={"desc": "The decoded/encodable value"})
    is_padding: bool = field(
        default=False,
        metadata={"desc": "Whether this field instance represents padding"},
    )

    def __lt__(self, other: object) -> bool:
        """Compare field instances using their field definition order."""
        if not isinstance(other, FieldInstance):
            return NotImplemented
        return self.field_def < other.field_def


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
        return cls(name=data.get("name", ""),
                   description=data.get("description", ""),
                   fields=[
                       FieldDef.from_dict(item)
                       for item in data.get("fields", [])
                   ])

    @classmethod
    def from_json(cls, data: str) -> "StructDef":
        """Create a structure definition from a JSON string."""
        return cls.from_dict(json.loads(data))


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

        rebuilt_instances: list[FieldInstance] = []
        current_offset = InfoSize(0, 0)
        padding_index = 0

        for field_instance in non_padding_instances:
            field_def = field_instance.field_def
            field_offset = self._resolve_field_offset(field_def)
            field_size = self._resolve_field_size(field_def)
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
            field_offset = self._resolve_field_offset(field_def)
            field_size = self._resolve_field_size(field_def)
            field_end = field_offset + field_size
            if field_end > max_end_offset:
                max_end_offset = field_end

        if max_end_offset > self.size:
            self.size = max_end_offset

    @staticmethod
    def _resolve_field_offset(field_def: FieldDef) -> InfoSize:
        """Resolve field offsets to InfoSize values when possible."""
        if isinstance(field_def.offset, InfoSize):
            return field_def.offset
        return InfoSize(0, 0)

    @staticmethod
    def _resolve_field_size(field_def: FieldDef) -> InfoSize:
        """Resolve field sizes to InfoSize values when possible."""
        if isinstance(field_def.size, InfoSize):
            return field_def.size
        return InfoSize(0, 0)
