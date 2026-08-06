"""Tests for the sltcodec module."""
from pathlib import Path

from sltcore import InfoSize

from sltcodec import (FieldDef, StructDef, decode, encode, field_def_from_json,
                      field_def_to_json, load_struct_def_dict,
                      save_struct_def_dict)


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

    encoded = encode([(struct_def[0], True), (struct_def[1], 0xA5)])

    assert encoded == bytearray(b"\xd2\x80")
    assert decode(struct_def, encoded) == [
        (struct_def[0], True),
        (struct_def[1], 165),
    ]


def test_encode_layout_handles_repeat():
    """Test that encoding a layout with a repeated field works correctly."""
    struct_def = [
        FieldDef(name="value",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int",
                 repeat=2),
    ]

    encoded = encode([(struct_def[0], [1, 2])])

    assert encoded == bytearray(b"\x01\x02")
    assert decode(struct_def, encoded) == [
        (FieldDef(name="value[0]",
                  offset=InfoSize(0, 0),
                  size=InfoSize(1, 0),
                  type="unsigned int"), 1),
        (FieldDef(name="value[1]",
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
        (child_field_defs[0], 3),
        (child_field_defs[1], 4),
    ]

    encoded = encode([(parent_field_def, child_values)])

    assert encoded == bytearray(b"\x03\x04")
    decoded = decode([parent_field_def], encoded)

    assert decoded[0][0] == parent_field_def
    assert [(field_def.name, value) for field_def, value in decoded[0][1]] == [
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

    encoded = encode([(field_def, [1, 2])])
    decoded = decode([field_def], encoded)

    assert encoded == bytearray(b"\x01\x02")
    assert decoded[0][0].description == "A repeated value"
    assert decoded[1][0].description == "A repeated value"


def test_field_def_json_round_trip():
    """Test that FieldDef can be serialized and deserialized from JSON."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         description="A value")

    payload = field_def_to_json(field_def)
    restored = field_def_from_json(payload)

    assert restored == field_def
    assert restored.description == "A value"


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

    payload = field_def_to_json(parent)
    restored = field_def_from_json(payload)

    assert isinstance(restored.type, StructDef)
    assert restored.type.name == "Payload"
    assert restored.type.description == "Payload layout"
    assert restored.type.fields == [child]


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


def test_encode_and_decode_accept_parallel_count_for_repeated_fields():
    """Test that repeated-field encode/decode works with parallel_count."""
    field_def = FieldDef(name="value",
                         offset=InfoSize(0, 0),
                         size=InfoSize(1, 0),
                         type="unsigned int",
                         repeat=4)

    encoded = encode([(field_def, [1, 2, 3, 4])], parallel_count=2)
    decoded = decode([field_def], encoded, parallel_count=2)

    assert encoded == bytearray(b"\x01\x02\x03\x04")
    assert decoded == [
        (FieldDef(name="value[0]",
                  offset=InfoSize(0, 0),
                  size=InfoSize(1, 0),
                  type="unsigned int"), 1),
        (FieldDef(name="value[1]",
                  offset=InfoSize(1, 0),
                  size=InfoSize(1, 0),
                  type="unsigned int"), 2),
        (FieldDef(name="value[2]",
                  offset=InfoSize(2, 0),
                  size=InfoSize(1, 0),
                  type="unsigned int"), 3),
        (FieldDef(name="value[3]",
                  offset=InfoSize(3, 0),
                  size=InfoSize(1, 0),
                  type="unsigned int"), 4),
    ]


def test_parallel_count_falls_back_for_env_dependent_repeated_fields():
    """Test that env-dependent repeated fields stay sequential."""
    seed_field = FieldDef(name="seed",
                          offset=InfoSize(0, 0),
                          size=InfoSize(1, 0),
                          type="unsigned int")
    repeated_field = FieldDef(name="value",
                              offset="{1: 0, 2: 1}[seed]",
                              size=InfoSize(1, 0),
                              type="unsigned int",
                              repeat=2)

    encoded = encode([(seed_field, 2), (repeated_field, [5, 6])],
                     parallel_count=2)
    decoded = decode([seed_field, repeated_field], encoded, parallel_count=2)

    assert encoded == bytearray(b"\x02\x05\x06")
    assert decoded[0] == (seed_field, 2)
    assert decoded[1][0].name == "value[0]"
    assert decoded[1][0].offset == InfoSize(1, 0)
    assert decoded[1][1] == 5
    assert decoded[2][0].name == "value[1]"
    assert decoded[2][0].offset == InfoSize(2, 0)
    assert decoded[2][1] == 6


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

    encoded_int = encode([(struct_def[0], 1), (struct_def[1], 7)])
    decoded_int = decode(struct_def, encoded_int)
    assert decoded_int == [(struct_def[0], 1), (struct_def[1], 7)]

    encoded_float = encode([(struct_def[0], 2), (struct_def[1], 1.5)])
    decoded_float = decode(struct_def, encoded_float)
    assert decoded_float[0] == (struct_def[0], 2)
    assert decoded_float[1][0] == struct_def[1]
    assert decoded_float[1][1] == 1.5
