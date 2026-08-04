"""Tests for the sltcodec module."""
from sltcore import InfoSize

from sltcodec import FieldDef, decode, encode


def test_encode_and_decode_round_trip():
    """Test that encoding and then decoding returns the original data."""
    field_defs = [
        FieldDef(name="flag",
                 offset=InfoSize(0, 0),
                 size=InfoSize(0, 1),
                 type="bool"),
        FieldDef(name="value",
                 offset=InfoSize(0, 1),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
    ]

    encoded = encode([(field_defs[0], True), (field_defs[1], 0xA5)])

    assert encoded == bytearray(b"\xd2\x80")
    assert decode(field_defs, encoded) == [
        (field_defs[0], True),
        (field_defs[1], 165),
    ]


def test_encode_layout_handles_repeat():
    """Test that encoding a layout with a repeated field works correctly."""
    field_defs = [
        FieldDef(name="value",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int",
                 repeat=2),
    ]

    encoded = encode([(field_defs[0], [1, 2])])

    assert encoded == bytearray(b"\x01\x02")
    assert decode(field_defs, encoded) == [
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
                                type=child_field_defs)
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


def test_type_expression_uses_previous_field_value():
    """Test that a type expression can depend on a previously decoded field."""
    field_defs = [
        FieldDef(name="kind",
                 offset=InfoSize(0, 0),
                 size=InfoSize(1, 0),
                 type="unsigned int"),
        FieldDef(name="payload",
                 offset=InfoSize(1, 0),
                 size="{1: 1, 2: 4}[kind]",
                 type="{1: 'int', 2: 'float'}[kind]"),
    ]

    encoded_int = encode([(field_defs[0], 1), (field_defs[1], 7)])
    decoded_int = decode(field_defs, encoded_int)
    assert decoded_int == [(field_defs[0], 1), (field_defs[1], 7)]

    encoded_float = encode([(field_defs[0], 2), (field_defs[1], 1.5)])
    decoded_float = decode(field_defs, encoded_float)
    assert decoded_float[0] == (field_defs[0], 2)
    assert decoded_float[1][0] == field_defs[1]
    assert decoded_float[1][1] == 1.5
