"""Tests for the sltcodec module."""
from enum import Enum
from pathlib import Path

import pytest
from sltcore import InfoSize

from sltcodec import (PRIMITIVE_TYPES, EnumDef, FieldDef, FieldInstance,
                      StructDef, StructInstance, decode, encode,
                      load_enum_def_dict, load_struct_def_dict,
                      save_enum_def_dict, save_struct_def_dict)
from sltcodec.codec import decode_field


class ValueKind(Enum):
    """Enum used for EnumDef metadata tests."""
    A = 1
    B = 2


def test_primitive_types_are_exposed_at_package_root():
    """Test that primitive types are exposed for external consumers."""
    assert PRIMITIVE_TYPES == {
        "bool",
        "signed int",
        "int",
        "unsigned int",
        "float",
        "bytearray",
        "bytes",
    }


def test_encode_and_decode_round_trip():
    """Test that encoding and then decoding returns the original data."""
    struct_def = [
        FieldDef(name="flag",
                 offset=InfoSize(0, 0),
                 size=InfoSize(0, 1),
                 type="bool"),
        FieldDef(name="value",
                 offset=InfoSize(0, 1),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
    ]

    encoded = encode(
        StructInstance(struct_def=StructDef(fields=struct_def),
                       field_instances=[
                           FieldInstance(struct_def[0], True),
                           FieldInstance(struct_def[1], 0xA5),
                       ]),
        bytearray(),
    )

    assert encoded == bytearray(b"\xd2\x80")
    decoded = decode(struct_def, encoded)
    assert isinstance(decoded, StructInstance)
    assert decoded.field_instances == [
        FieldInstance(struct_def[0], True),
        FieldInstance(struct_def[1], 165),
    ]
    assert encode(decoded, bytearray()) == encoded


def test_encode_layout_handles_repeat():
    """Test that encoding a layout with a repeated field works correctly."""
    struct_def = [
        FieldDef(name="value",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int",
                 repeat=2),
    ]

    encoded = encode(
        StructInstance(struct_def=StructDef(fields=struct_def),
                       field_instances=[FieldInstance(struct_def[0], [1, 2])]),
        bytearray(),
    )

    assert encoded == bytearray(b"\x01\x02")
    decoded = decode(struct_def, encoded)
    assert isinstance(decoded, StructInstance)
    assert decoded.field_instances == [
        FieldInstance(
            FieldDef(name="value[0]",
                     offset=InfoSize(0, 0),
                     size=InfoSize(1, 0),
                     type="unsigned int"), 1),
        FieldInstance(
            FieldDef(name="value[1]",
                     offset=InfoSize(1, 0),
                     size=InfoSize(1, 0),
                     type="unsigned int"), 2),
    ]


def test_encode_recurses_for_nested_field_types():
    """Test that encoding a field with a nested field type works correctly."""
    child_field_defs = [
        FieldDef(name="left",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
        FieldDef(name="right",
                 offset=InfoSize(1, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
    ]
    parent_field_def = FieldDef(name="pair",
                                offset=InfoSize(0, 0),
                                size=InfoSize(2, 0),
                                type=StructDef(fields=child_field_defs))
    child_values = [
        FieldInstance(child_field_defs[0], 3),
        FieldInstance(child_field_defs[1], 4),
    ]

    encoded = encode(
        StructInstance(
            struct_def=StructDef(fields=[parent_field_def]),
            field_instances=[
                FieldInstance(
                    parent_field_def,
                    StructInstance(
                        struct_def=StructDef(fields=child_field_defs),
                        field_instances=child_values,
                    ),
                )
            ]),
        bytearray(),
    )

    assert encoded == bytearray(b"\x03\x04")
    decoded = decode([parent_field_def], encoded)

    assert decoded.field_instances[0].field_def == parent_field_def
    nested_decoded = decoded.field_instances[0].value
    assert [(field_value.field_def.name, field_value.value)
            for field_value in nested_decoded.field_instances] == [
                ("left", 3),
                ("right", 4),
            ]


def test_repeated_field_preserves_description():
    """Test that repeated fields keep their description on decoded entries."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         repeat=2,
                         description="A repeated value")

    encoded = encode(
        StructInstance(struct_def=StructDef(fields=[field_def]),
                       field_instances=[FieldInstance(field_def, [1, 2])]),
        bytearray(),
    )
    decoded = decode([field_def], encoded)

    assert encoded == bytearray(b"\x01\x02")
    assert (
        decoded.field_instances[0].field_def.description == "A repeated value")
    assert (
        decoded.field_instances[1].field_def.description == "A repeated value")


def test_repeated_field_preserves_range_and_enum_metadata():
    """Test repeated fields preserve range/enum metadata on decoded entries."""
    enum_def = EnumDef(
        name="ValueKind",
        values={member.name: member.value
                for member in ValueKind})
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         repeat=2,
                         range_expression="0 <= value <= 255",
                         enum_def_name=enum_def.name)

    encoded = encode(
        StructInstance(struct_def=StructDef(fields=[field_def]),
                       field_instances=[FieldInstance(field_def, [1, 2])]),
        bytearray(),
    )
    decoded = decode([field_def], encoded)

    assert decoded.field_instances[0].field_def.range_expression == (
        "0 <= value[0] <= 255")
    assert decoded.field_instances[1].field_def.range_expression == (
        "0 <= value[1] <= 255")
    assert decoded.field_instances[0].field_def.enum_def_name == enum_def.name
    assert decoded.field_instances[1].field_def.enum_def_name == enum_def.name


def test_split_repeat_replaces_name_in_range_expression():
    """Test split_repeat replaces field-name tokens in range expressions."""
    field_def = FieldDef(
        name="value",
        offset=InfoSize(0, 0),
        size=InfoSize(1, 0),
        type="unsigned int",
        repeat=2,
        range_expression=("0 <= value and value <= limit and value_count"))

    split = field_def.split_repeat(1)

    assert split.name == "value[1]"
    assert split.range_expression == (
        "0 <= value[1] and value[1] <= limit and value_count")


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


def test_byte_swap_reverses_bytearray_input_and_output():
    """Test byte_swap reverses bytearray values symmetrically."""
    field_def = FieldDef(name="payload",
                         offset=InfoSize(0, 0),
                         size=InfoSize(3, 0),
                         type="bytearray",
                         byte_swap=True)

    encoded = encode(
        StructInstance(struct_def=StructDef(fields=[field_def]),
                       field_instances=[
                           FieldInstance(field_def, bytearray(b"\x01\x02\x03"))
                       ]),
        bytearray(),
    )
    decoded = decode([field_def], encoded)

    assert encoded == bytearray(b"\x03\x02\x01")
    assert decoded.field_instances == [
        FieldInstance(field_def, bytearray(b"\x01\x02\x03"))
    ]


def test_byte_swap_expression_uses_previous_field_value():
    """Test byte_swap expressions use values decoded or encoded before it."""
    kind_field = FieldDef(name="kind",
                          offset=InfoSize(0, 0),
                          size=InfoSize(1, 0),
                          type="unsigned int")
    value_field = FieldDef(name="value",
                           offset=InfoSize(1, 0),
                           size=InfoSize(2, 0),
                           type="unsigned int",
                           byte_swap="kind == 1")

    encoded = encode(
        StructInstance(struct_def=StructDef(fields=[kind_field, value_field]),
                       field_instances=[
                           FieldInstance(kind_field, 1),
                           FieldInstance(value_field, 0x1234),
                       ]),
        bytearray(),
    )
    decoded = decode([kind_field, value_field], encoded)

    assert encoded == bytearray(b"\x01\x34\x12")
    assert decoded.field_instances == [
        FieldInstance(kind_field, 1),
        FieldInstance(
            FieldDef(name="value",
                     offset=InfoSize(1, 0),
                     size=InfoSize(2, 0),
                     type="unsigned int",
                     byte_swap=True), 0x1234),
    ]


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


def test_decode_uses_enum_def_dict_to_set_enum_item():
    """Test decode uses enum_def_dict to resolve FieldInstance enum_item."""
    enum_def = EnumDef(name="Status", values={"OK": 1, "NG": 2})
    field_def = FieldDef(name="status",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int")

    decoded = decode([field_def],
                     bytearray(b"\x02"),
                     enum_def_dict={"status": enum_def})

    assert decoded.field_instances[0].value == 2
    assert decoded.field_instances[0].enum_item == ("NG", 2)


def test_field_instance_from_value_sets_enum_item_from_field_enum_def():
    """Test FieldInstance.from_value sets enum_item from field enum_def."""
    enum_def = EnumDef(name="Mode", values={"AUTO": 0, "MANUAL": 1})
    field_def = FieldDef(name="mode",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         enum_def_name=enum_def.name)

    field_instance = FieldInstance.from_value(
        field_def, 1, enum_def_dict={enum_def.name: enum_def})

    assert field_instance.enum_item == ("MANUAL", 1)


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


def test_struct_def_dict_load_and_save(tmp_path: Path):
    """Test that a StructDef dictionary can be saved and reloaded."""
    struct_def = StructDef(name="ValueStruct",
                           description="Single value struct",
                           fields=[
                               FieldDef(name="value",
                                        offset=InfoSize(0, 0),
                                        size=InfoSize(1, 0),
                                        type="unsigned int",
                                        description="A value")
                           ])
    path = tmp_path / "field_defs.json"

    save_struct_def_dict(path, {"value": struct_def})
    loaded = load_struct_def_dict(path)

    assert loaded["value"] == struct_def


def test_enum_def_dict_load_and_save(tmp_path: Path):
    """Test that an EnumDef dictionary can be saved and reloaded."""
    enum_def = EnumDef(name="Status",
                       description="Status enum",
                       values={
                           "OK": 1,
                           "NG": 2
                       })
    path = tmp_path / "enum_defs.json"

    save_enum_def_dict(path, {"status": enum_def})
    loaded = load_enum_def_dict(path)

    assert loaded["status"] == enum_def


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


def test_env_dependent_repeated_fields_decode_sequentially():
    """Test that env-dependent repeated fields decode in order."""
    seed_field = FieldDef(name="seed",
                          offset=InfoSize(0, 0),
                          size=InfoSize(1, 0),
                          type="unsigned int")
    repeated_field = FieldDef(name="value",
                              offset="{1: 0, 2: 1}[seed]",
                              size=InfoSize(1, 0),
                              type="unsigned int",
                              repeat=2)

    encoded = encode(
        StructInstance(struct_def=StructDef(fields=[
            seed_field,
            repeated_field,
        ]),
                       field_instances=[
                           FieldInstance(seed_field, 2),
                           FieldInstance(repeated_field, [5, 6]),
                       ]),
        bytearray(),
    )
    decoded = decode([seed_field, repeated_field], encoded)

    assert encoded == bytearray(b"\x02\x05\x06")
    assert decoded.field_instances[0] == FieldInstance(seed_field, 2)
    assert decoded.field_instances[1].field_def.name == "value[0]"
    assert decoded.field_instances[1].field_def.offset == InfoSize(1, 0)
    assert decoded.field_instances[1].value == 5
    assert decoded.field_instances[2].field_def.name == "value[1]"
    assert decoded.field_instances[2].field_def.offset == InfoSize(2, 0)
    assert decoded.field_instances[2].value == 6


def test_type_expression_uses_previous_field_value():
    """Test that a type expression can depend on a previously decoded field."""
    struct_def = [
        FieldDef(name="kind",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
        FieldDef(name="payload",
                 offset=InfoSize(1, 0),
                 size="{1: 1, 2: 4}[kind]",
                 type="{1: 'int', 2: 'float'}[kind]"),
    ]

    encoded_int = encode(
        StructInstance(struct_def=StructDef(fields=struct_def),
                       field_instances=[
                           FieldInstance(struct_def[0], 1),
                           FieldInstance(struct_def[1], 7),
                       ]),
        bytearray(),
    )
    decoded_int = decode(struct_def, encoded_int)
    assert decoded_int.field_instances[0] == FieldInstance(struct_def[0], 1)
    assert decoded_int.field_instances[1].field_def.offset == InfoSize(1, 0)
    assert decoded_int.field_instances[1].field_def.size == InfoSize(1, 0)
    assert decoded_int.field_instances[1].field_def.type == "int"
    assert decoded_int.field_instances[1].value == 7

    encoded_float = encode(
        StructInstance(struct_def=StructDef(fields=struct_def),
                       field_instances=[
                           FieldInstance(struct_def[0], 2),
                           FieldInstance(struct_def[1], 1.5),
                       ]),
        bytearray(),
    )
    decoded_float = decode(struct_def, encoded_float)
    assert decoded_float.field_instances[0] == FieldInstance(struct_def[0], 2)
    assert decoded_float.field_instances[1].field_def.offset == InfoSize(1, 0)
    assert decoded_float.field_instances[1].field_def.size == InfoSize(4, 0)
    assert decoded_float.field_instances[1].field_def.type == "float"
    assert decoded_float.field_instances[1].value == 1.5


def test_decode_inserts_padding_fields_for_gaps_and_trailing_space():
    """Test that decode inserts padding fields split by 4-byte boundaries."""
    struct_def = StructDef(fields=[
        FieldDef(name="head",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
        FieldDef(name="tail",
                 offset=InfoSize(6, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
    ])
    data = bytearray(b"\x11\xaa\xbb\xcc\xdd\xee\x22\x99\x88\x77")

    decoded = decode(struct_def, data)

    assert [
        field_instance.field_def.name
        for field_instance in decoded.field_instances
    ] == [
        "head",
        "padding[0]",
        "padding[1]",
        "tail",
    ]
    assert decoded.field_instances[1].field_def.offset == InfoSize(1, 0)
    assert decoded.field_instances[1].field_def.size == InfoSize(3, 0)
    assert decoded.field_instances[1].value == b"\xaa\xbb\xcc"
    assert decoded.field_instances[2].field_def.offset == InfoSize(4, 0)
    assert decoded.field_instances[2].field_def.size == InfoSize(2, 0)
    assert decoded.field_instances[2].value == b"\xdd\xee"


def test_decode_splits_padding_at_32_bit_boundaries():
    """Test split into 32-bit chunks when a gap crosses a boundary."""
    struct_def = StructDef(fields=[
        FieldDef(name="head",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
        FieldDef(name="tail",
                 offset=InfoSize(5, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
    ])
    decoded = decode(struct_def, bytearray(8))

    assert [
        field_instance.field_def.name
        for field_instance in decoded.field_instances
    ] == [
        "head",
        "padding[0]",
        "padding[1]",
        "tail",
    ]


def test_decode_splits_padding_with_custom_alignment_bits():
    """Test that decode can split padding by a custom bit alignment."""
    struct_def = StructDef(fields=[
        FieldDef(name="head",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
        FieldDef(name="tail",
                 offset=InfoSize(4, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
    ])
    data = bytearray(b"\x11\xaa\xbb\xcc\x22")

    decoded = decode(struct_def, data, padding_alignment_bits=16)

    assert [
        field_instance.field_def.name
        for field_instance in decoded.field_instances
    ] == [
        "head",
        "padding[0]",
        "padding[1]",
        "tail",
    ]
    assert decoded.field_instances[1].field_def.offset == InfoSize(1, 0)
    assert decoded.field_instances[1].field_def.size == InfoSize(1, 0)
    assert decoded.field_instances[1].value == b"\xaa"
    assert decoded.field_instances[2].field_def.offset == InfoSize(2, 0)
    assert decoded.field_instances[2].field_def.size == InfoSize(2, 0)
    assert decoded.field_instances[2].value == b"\xbb\xcc"


def test_decode_rejects_invalid_padding_alignment_bits():
    """Test that decode validates padding alignment bit size."""
    struct_def = StructDef(fields=[])

    with pytest.raises(
            ValueError,
            match=r"padding_alignment_bits must be a positive power of two"):
        decode(struct_def, bytearray(), padding_alignment_bits=24)


def test_encode_rejects_invalid_padding_alignment_bits():
    """Test that encode validates padding alignment bit size."""
    struct_instance = StructInstance(struct_def=StructDef(fields=[]))

    with pytest.raises(
            ValueError,
            match=r"padding_alignment_bits must be a positive power of two"):
        encode(struct_instance, bytearray(), padding_alignment_bits=0)


def test_encode_rejects_tuple_input():
    """Test that encode only accepts StructInstance input."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int")

    with pytest.raises(TypeError, match=r"expects StructInstance"):
        encode([(field_def, 1)], bytearray())


def test_decode_field_returns_field_instance():
    """Test that decode_field returns FieldInstance."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int")
    data = bytearray(b"\x7f")

    decoded = decode_field(field_def, data)

    assert decoded == FieldInstance(field_def=field_def, value=127)


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
                 type="unsigned int"),
        2,
    )
    earlier = FieldInstance(
        FieldDef(name="a",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
        1,
    )

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
    ] == [
        "head",
        "padding[0]",
        "tail",
    ]
    assert struct_instance.field_instances[1].is_padding is True
    assert struct_instance.field_instances[1].value == b"\x00"


def test_field_instance_sort_uses_field_def_order():
    """Test that FieldInstance sorting delegates to FieldDef ordering."""
    later = FieldInstance(
        FieldDef(name="later",
                 offset=InfoSize(1, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
        2,
    )
    earlier = FieldInstance(
        FieldDef(name="earlier",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
        1,
    )

    sorted_instances = sorted([later, earlier])

    assert sorted_instances == [earlier, later]


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

    result = field_instance.range_check()

    assert result is None


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


def test_encode_padding_fields_use_zero_value_and_extend_to_struct_size():
    """Test that padding fields are zeroed and trailing bytes are padded.

    Trailing bytes are padded until StructDef.size.
    """
    struct_def = StructDef(fields=[
        FieldDef(name="padding[0]",
                 offset=InfoSize(2, 0),
                 size=InfoSize(2, 0),
                 type="bytes")
    ])
    struct_instance = StructInstance(
        size=InfoSize(6, 0),
        struct_def=struct_def,
        field_instances=[
            FieldInstance(field_def=struct_def.fields[0], value=b"\xff\xff")
        ],
    )
    buf = bytearray(b"\x11\x22")

    encoded = encode(struct_instance, buf)

    assert encoded is buf
    assert encoded == bytearray(b"\x00\x00\x00\x00\x00\x00")


def test_encode_without_padding_does_not_extend_buf_to_struct_size():
    """Test that trailing size padding is skipped without padding fields."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int")
    struct_instance = StructInstance(
        size=InfoSize(4, 0),
        struct_def=StructDef(fields=[field_def]),
        field_instances=[FieldInstance(field_def=field_def, value=0x7F)],
    )
    buf = bytearray()

    encoded = encode(struct_instance, buf)

    assert encoded is buf
    assert encoded == bytearray(b"\x7f\x00\x00\x00")
