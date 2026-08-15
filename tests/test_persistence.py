"""Tests for StructLayout persistence."""
import json
from pathlib import Path

from sltcore import InfoSize

from sltcodec import (EnumDef, FieldDef, StructDef, StructLayout, TypeDict,
                      load_struct_layout, save_struct_layout)


def test_layout_load_and_save_struct_dict(tmp_path: Path):
    """Test StructLayout save/load for struct definitions."""
    struct_def = StructDef(name="ValueStruct",
                           description="Single value struct",
                           fields=[
                               FieldDef(name="value",
                                        offset=InfoSize(0, 0),
                                        size=InfoSize(1, 0),
                                        type="unsigned int",
                                        description="A value")
                           ])
    layout = StructLayout(
        struct_def_name="ValueStruct",
        type_dict=TypeDict(struct_dict={"ValueStruct": struct_def}),
    )
    path = tmp_path / "field_defs.json"

    save_struct_layout(layout, path)
    saved_field = json.loads(path.read_text(
    ))["type_dict"]["struct_dict"]["ValueStruct"]["fields"][0]

    assert isinstance(saved_field["offset"], dict)
    assert isinstance(saved_field["size"], dict)
    loaded = load_struct_layout(path)

    assert loaded == layout
    assert loaded.type_dict.struct_dict["ValueStruct"] == struct_def


def test_layout_load_and_save_enum_dict(tmp_path: Path):
    """Test StructLayout save/load for enum definitions."""
    enum_def = EnumDef(name="Status",
                       description="Status enum",
                       values={
                           "OK": 1,
                           "NG": 2
                       })
    layout = StructLayout(
        struct_def_name="Status",
        type_dict=TypeDict(enum_dict={"Status": enum_def}),
    )
    path = tmp_path / "enum_defs.json"

    save_struct_layout(layout, path)
    loaded = load_struct_layout(path)

    assert loaded == layout
    assert loaded.type_dict.enum_dict["Status"] == enum_def
