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
    field_def_dict = {"pair": child_field_defs}
    parent_field_def = FieldDef(name="pair",
                                offset=InfoSize(0, 0),
                                size=InfoSize(2, 0),
                                type="pair")
    child_values = [
        (child_field_defs[0], 3),
        (child_field_defs[1], 4),
    ]

    encoded = encode([(parent_field_def, child_values)], field_def_dict)

    assert encoded == bytearray(b"\x03\x04")
    decoded = decode([parent_field_def], encoded, field_def_dict)

    assert decoded[0][0] == parent_field_def
    assert [(field_def.name, value) for field_def, value in decoded[0][1]] == [
        ("left", b"\x03"),
        ("right", b"\x04"),
    ]
