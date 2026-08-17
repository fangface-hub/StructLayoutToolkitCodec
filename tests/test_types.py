"""Tests for sltcodec type metadata serialization."""
from enum import Enum

from sltcore import InfoSize

from sltcodec import (EnumDef, FieldDef, FieldInstance, StructDef,
                      StructInstance, TypeDict)


class ValueKind(Enum):
    """Enum used for EnumDef metadata tests."""
    A = 1
    B = 2


def test_field_def_json_round_trip():
    """Test that FieldDef can be serialized and deserialized from JSON."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         description="A value")

    payload = field_def.to_json()
    restored = FieldDef.from_json(payload)

    assert restored == field_def
    assert restored.description == "A value"


def test_field_def_to_json_from_json_round_trip():
    """Test FieldDef.to_json/from_json round-trip conversion."""
    enum_def = EnumDef(
        name="ValueKind",
        values={member.name: member.value
                for member in ValueKind})
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         scale=2.0,
                         repeat=3,
                         description="A repeated value",
                         range_expression="0 <= value <= 255",
                         enum_def_name=enum_def.name)

    payload = field_def.to_json()
    restored = FieldDef.from_json(payload)

    assert restored == field_def
    assert restored.range_expression == "0 <= value <= 255"
    assert restored.enum_def_name == enum_def.name
    assert restored.to_dict()["enum_def_name"] == "ValueKind"


def test_field_def_byte_swap_json_round_trip():
    """Test that expression-based byte_swap metadata is preserved."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(2, 0),
                         type="unsigned int",
                         byte_swap="kind == 1")

    restored = FieldDef.from_json(field_def.to_json())

    assert restored == field_def
    assert restored.byte_swap == "kind == 1"


def test_enum_def_to_json_from_json_round_trip():
    """Test EnumDef.to_json/from_json round-trip conversion."""
    enum_def = EnumDef(name="Status",
                       description="Status enum",
                       values={
                           "OK": 1,
                           "NG": 2
                       })

    payload = enum_def.to_json()
    restored = EnumDef.from_json(payload)

    assert restored == enum_def
    assert restored.to_dict() == {
        "name": "Status",
        "description": "Status enum",
        "values": {
            "OK": 1,
            "NG": 2,
        },
    }


def test_enum_def_to_dict_from_dict_round_trip():
    """Test EnumDef.to_dict/from_dict round-trip conversion."""
    enum_def = EnumDef(name="Mode",
                       description="Mode enum",
                       values={
                           "AUTO": 0,
                           "MANUAL": 1,
                       })

    payload = enum_def.to_dict()
    restored = EnumDef.from_dict(payload)

    assert restored == enum_def
    assert payload == {
        "name": "Mode",
        "description": "Mode enum",
        "values": {
            "AUTO": 0,
            "MANUAL": 1,
        },
    }


def test_enum_def_serialize_deserialize_round_trip():
    """Test EnumDef.serialize/deserialize round-trip conversion."""
    enum_def = EnumDef(name="State",
                       description="State enum",
                       values={
                           "ON": 1,
                           "OFF": 0,
                       })

    payload = enum_def.serialize()
    restored = EnumDef.deserialize(payload)

    assert restored == enum_def
    assert payload == {
        "__type__": "EnumDef",
        "name": "State",
        "description": "State enum",
        "values": {
            "ON": 1,
            "OFF": 0,
        },
    }


def test_field_instance_from_value_sets_enum_item_from_field_enum_def():
    """Test FieldInstance.from_value sets enum_item from field enum_def."""
    enum_def = EnumDef(name="Mode", values={"AUTO": 0, "MANUAL": 1})
    field_def = FieldDef(name="mode",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         enum_def_name=enum_def.name)

    field_instance = FieldInstance.from_value(
        field_def, 1, type_dict=TypeDict(enum_dict={enum_def.name: enum_def}))

    assert field_instance.enum_item == ("MANUAL", 1)


def _mode_enum_fixture() -> tuple[EnumDef, FieldDef, TypeDict]:
    """Build an enum-backed field definition and its type dictionary."""
    enum_def = EnumDef(name="Mode", values={"AUTO": 0, "MANUAL": 1})
    field_def = FieldDef(name="mode",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         enum_def_name=enum_def.name)
    type_dict = TypeDict(enum_dict={enum_def.name: enum_def})
    return enum_def, field_def, type_dict


def test_field_instance_with_value_keeps_original_unchanged():
    """Test FieldInstance.with_value does not mutate the original."""
    _, field_def, type_dict = _mode_enum_fixture()
    original = FieldInstance.from_value(field_def, 0, type_dict=type_dict)

    original.with_value(1, type_dict)

    assert original.value == 0
    assert original.enum_item == ("AUTO", 0)


def test_field_instance_with_value_returns_new_instance():
    """Test FieldInstance.with_value returns a new instance with the value."""
    _, field_def, type_dict = _mode_enum_fixture()
    original = FieldInstance.from_value(field_def, 0, type_dict=type_dict)

    updated = original.with_value(1, type_dict)

    assert updated is not original
    assert updated.value == 1


def test_field_instance_with_value_preserves_field_def_and_padding():
    """Test FieldInstance.with_value preserves field_def and is_padding."""
    _, field_def, type_dict = _mode_enum_fixture()
    original = FieldInstance.from_value(field_def,
                                        0,
                                        type_dict=type_dict,
                                        is_padding=True)

    updated = original.with_value(1, type_dict)

    assert updated.field_def is original.field_def
    assert updated.is_padding is True


def test_field_instance_with_value_updates_enum_item():
    """Test FieldInstance.with_value recomputes a matching enum_item."""
    _, field_def, type_dict = _mode_enum_fixture()
    original = FieldInstance.from_value(field_def, 0, type_dict=type_dict)

    updated = original.with_value(1, type_dict)

    assert updated.enum_item == ("MANUAL", 1)


def test_field_instance_with_value_clears_unmatched_enum_item():
    """Test FieldInstance.with_value clears enum_item when unmatched."""
    _, field_def, type_dict = _mode_enum_fixture()
    original = FieldInstance.from_value(field_def, 0, type_dict=type_dict)

    updated = original.with_value(7, type_dict)

    assert updated.enum_item is None


def test_field_instance_with_value_without_type_dict():
    """Test FieldInstance.with_value works for plain fields."""
    field_def = FieldDef(name="count",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int")
    original = FieldInstance.from_value(field_def, 1)

    updated = original.with_value(2)

    assert updated.value == 2
    assert updated.enum_item is None
    assert original.value == 1


def test_struct_def_metadata_json_round_trip():
    """Test that StructDef name/description are preserved in JSON."""
    child = FieldDef(name="value",
                     offset=InfoSize(0, 0),
                     size=InfoSize(1, 0),
                     type="unsigned int")
    parent = FieldDef(name="payload",
                      offset=InfoSize(0, 0),
                      size=InfoSize(1, 0),
                      type=StructDef(name="Payload",
                                     description="Payload layout",
                                     fields=[child]))

    payload = parent.to_json()
    restored = FieldDef.from_json(payload)

    assert isinstance(restored.type, StructDef)
    assert restored.type.name == "Payload"
    assert restored.type.description == "Payload layout"
    assert restored.type.fields == [child]


def test_struct_instance_size_json_round_trip():
    """Test that StructInstance size is preserved in the instance state."""
    struct_instance = StructInstance(
        size=InfoSize(8, 0),
        struct_def=StructDef(name="SizedStruct",
                             description="Sized struct",
                             fields=[]),
    )

    assert struct_instance.size == InfoSize(8, 0)


def test_struct_def_to_json_from_json_round_trip():
    """Test StructDef.to_json/from_json round-trip conversion."""
    struct_def = StructDef(name="ValueStruct",
                           description="Single value struct",
                           fields=[
                               FieldDef(name="value",
                                        offset=InfoSize(0, 0),
                                        size=InfoSize(1, 0),
                                        type="unsigned int",
                                        description="A value")
                           ])

    payload = struct_def.to_json()
    restored = StructDef.from_json(payload)

    assert restored == struct_def


def test_struct_instance_field_instance_interface():
    """Test StructInstance interface for field_instances operations."""
    field_def_0 = FieldDef(name="b",
                           offset=InfoSize(1, 0),
                           size=InfoSize(1, 0),
                           type="unsigned int")
    field_def_1 = FieldDef(name="a",
                           offset=InfoSize(0, 0),
                           size=InfoSize(1, 0),
                           type="unsigned int")
    struct_instance = StructInstance(struct_def=StructDef(fields=[
        field_def_0,
        field_def_1,
    ]))

    struct_instance.append_field_instance(FieldInstance(field_def_0, 1))
    struct_instance.extend_field_instances([FieldInstance(field_def_1, 2)])

    assert len(struct_instance) == 2
    assert struct_instance[0] == FieldInstance(field_def_1, 2)
    assert [field_instance.value
            for field_instance in struct_instance] == [2, 1]


def test_struct_instance_initial_field_instances_are_sorted():
    """Test that StructInstance sorts initial field_instances."""
    later = FieldInstance(
        FieldDef(name="b",
                 offset=InfoSize(1, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"), 2)
    earlier = FieldInstance(
        FieldDef(name="a",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"), 1)

    struct_instance = StructInstance(
        struct_def=StructDef(fields=[later.field_def, earlier.field_def]),
        field_instances=[later, earlier],
    )

    assert struct_instance.field_instances == [earlier, later]


def test_struct_instance_rebuilds_padding_when_field_instances_change():
    """Test that padding entries are rebuilt after field instance updates."""
    tail_field_def = FieldDef(name="tail",
                              offset=InfoSize(2, 0),
                              size=InfoSize(1, 0),
                              type="unsigned int")
    head_field_def = FieldDef(name="head",
                              offset=InfoSize(0, 0),
                              size=InfoSize(1, 0),
                              type="unsigned int")
    struct_instance = StructInstance(
        size=InfoSize(3, 0),
        struct_def=StructDef(fields=[tail_field_def, head_field_def]),
        field_instances=[FieldInstance(tail_field_def, 0xAA)],
    )

    struct_instance.append_field_instance(FieldInstance(head_field_def, 0x55))

    assert [
        field_instance.field_def.name
        for field_instance in struct_instance.field_instances
    ] == ["head", "padding[0]", "tail"]
    assert struct_instance.field_instances[1].is_padding is True
    assert struct_instance.field_instances[1].value == b"\x00"


def test_field_instance_sort_uses_field_def_order():
    """Test that FieldInstance sorting delegates to FieldDef ordering."""
    later = FieldInstance(
        FieldDef(name="later",
                 offset=InfoSize(1, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"), 2)
    earlier = FieldInstance(
        FieldDef(name="earlier",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"), 1)

    assert sorted([later, earlier]) == [earlier, later]


def test_field_instance_range_check_evaluates_expression_with_field_env():
    """Test that range_check evaluates expression with field name bound."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         range_expression="0 <= value <= limit")
    field_instance = FieldInstance(field_def=field_def, value=7)

    assert field_instance.range_check({"limit": 10}) is True
    assert field_instance.range_check({"limit": 5}) is False


def test_field_instance_range_check_returns_none_when_expression_is_none():
    """Test that range_check returns None when range_expression is None."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         range_expression=None)
    field_instance = FieldInstance(field_def=field_def, value=7)

    assert field_instance.range_check() is None


def test_struct_instance_size_property_returns_initial_size():
    """Test that StructInstance size is initialized from the provided value."""
    struct_instance = StructInstance(size=InfoSize(5, 0),
                                     struct_def=StructDef())

    assert struct_instance.size == InfoSize(5, 0)


def test_struct_instance_size_property_uses_field_extent_when_available():
    """Test that StructInstance size grows with instance field layout."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(1, 0),
                         size=InfoSize(2, 0),
                         type="unsigned int")
    struct_instance = StructInstance(
        size=InfoSize(1, 0),
        struct_def=StructDef(fields=[field_def]),
        field_instances=[FieldInstance(field_def=field_def, value=0x1234)],
    )

    assert struct_instance.size == InfoSize(3, 0)
