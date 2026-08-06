"""Type definitions for structured layout metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
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

    def split_repeat(self,
                     index: int,
                     offset: InfoSize | str | None = None) -> "FieldDef":
        """Create a single repeated-field definition for the given index."""
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
