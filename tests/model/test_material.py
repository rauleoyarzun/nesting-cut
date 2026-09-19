import pytest

from nesting.model.material import Material, allowed_angles, load_materials

FREE = Material("mdf18", 1830.0, 2600.0, grain_tolerance=180.0)
GRAIN = Material("multilam18", 1220.0, 2440.0, grain_tolerance=5.0)


def test_free_rotation_allows_every_angle():
    angles = [0.0, 15.0, 90.0, 137.0, 180.0, 270.0]
    assert allowed_angles(FREE, angles) == angles


def test_grain_constraint_keeps_only_zero_and_one_eighty():
    assert allowed_angles(GRAIN, [0.0, 90.0, 180.0, 270.0]) == [0.0, 180.0]


def test_grain_constraint_allows_angles_inside_the_tolerance():
    assert allowed_angles(GRAIN, [0.0, 3.0, 8.0, 177.0, 183.0]) == [0.0, 3.0, 177.0, 183.0]


def test_360_is_treated_as_zero():
    assert allowed_angles(GRAIN, [360.0]) == [360.0]


def test_negative_angles_are_handled():
    assert allowed_angles(GRAIN, [-3.0, -90.0]) == [-3.0]


def test_an_empty_angle_list_stays_empty():
    assert allowed_angles(GRAIN, []) == []


def test_loads_the_bundled_catalogue(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "mdf18:\n"
        "  placa: [1830, 2600]\n"
        "  tolerancia_veta: 180\n"
        "multilam18:\n"
        "  placa: [1220, 2440]\n"
        "  tolerancia_veta: 5\n",
        encoding="utf-8",
    )
    materials = load_materials(catalogue)

    assert set(materials) == {"mdf18", "multilam18"}
    assert materials["mdf18"].sheet_w == 1830.0
    assert materials["mdf18"].sheet_h == 2600.0
    assert materials["mdf18"].grain_tolerance == 180.0
    assert materials["mdf18"].name == "mdf18"
    assert materials["multilam18"].grain_tolerance == 5.0


def test_a_missing_field_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text("roto:\n  placa: [100, 200]\n", encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    assert "tolerancia_veta" in str(info.value)
    assert "roto" in str(info.value)


def test_a_malformed_sheet_size_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text("roto:\n  placa: [100]\n  tolerancia_veta: 5\n", encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    assert "placa" in str(info.value)


def test_the_shipped_catalogue_is_valid():
    from nesting.model.material import DEFAULT_MATERIALS_PATH
    materials = load_materials(DEFAULT_MATERIALS_PATH)
    assert "mdf18" in materials
    assert materials["mdf18"].sheet_w == 1830.0


# --- Hallazgo 1: errores que hoy se filtran crudos ---


def test_a_non_numeric_sheet_size_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "roto:\n  placa: [\"a\", \"b\"]\n  tolerancia_veta: 5\n", encoding="utf-8"
    )
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    message = str(info.value)
    assert "roto" in message
    assert "placa" in message


def test_a_non_numeric_grain_tolerance_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "roto:\n  placa: [100, 200]\n  tolerancia_veta: cinco\n", encoding="utf-8"
    )
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    message = str(info.value)
    assert "roto" in message
    assert "tolerancia_veta" in message


def test_a_catalogue_whose_root_is_a_list_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text("- roto\n- otro\n", encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    message = str(info.value)
    assert "mapeo" in message


def test_a_catalogue_whose_root_is_a_bare_string_is_reported_clearly(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text("esto no es un catalogo\n", encoding="utf-8")
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    message = str(info.value)
    assert "mapeo" in message


# --- Hallazgo 2: rangos no validados ---


def test_a_negative_sheet_width_is_rejected(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "roto:\n  placa: [-100, 200]\n  tolerancia_veta: 5\n", encoding="utf-8"
    )
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    message = str(info.value)
    assert "roto" in message
    assert "placa" in message
    assert "-100" in message


def test_a_zero_sheet_height_is_rejected(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "roto:\n  placa: [100, 0]\n  tolerancia_veta: 5\n", encoding="utf-8"
    )
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    message = str(info.value)
    assert "roto" in message
    assert "placa" in message
    assert "0" in message


def test_a_negative_grain_tolerance_is_rejected(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "roto:\n  placa: [100, 200]\n  tolerancia_veta: -5\n", encoding="utf-8"
    )
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    message = str(info.value)
    assert "roto" in message
    assert "tolerancia_veta" in message
    assert "-5" in message


def test_a_grain_tolerance_over_180_is_rejected(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "roto:\n  placa: [100, 200]\n  tolerancia_veta: 200\n", encoding="utf-8"
    )
    with pytest.raises(ValueError) as info:
        load_materials(catalogue)
    message = str(info.value)
    assert "roto" in message
    assert "tolerancia_veta" in message
    assert "200" in message


# --- Hallazgo 3: 90 grados ya es rotacion libre, igual que 180 ---


def test_ninety_degrees_is_already_free_rotation_like_180():
    ninety = Material("ninety", 1000.0, 1000.0, grain_tolerance=90.0)
    angles = [0.0, 15.0, 90.0, 137.0, 180.0, 270.0]
    assert allowed_angles(ninety, angles) == allowed_angles(FREE, angles) == angles


# --- No regresion ---


def test_the_shipped_catalogue_has_all_four_materials():
    from nesting.model.material import DEFAULT_MATERIALS_PATH
    materials = load_materials(DEFAULT_MATERIALS_PATH)
    assert set(materials) == {"mdf18", "mdf15", "multilam18", "fenolico18"}


def test_a_catalogue_at_the_boundary_values_loads_fine(tmp_path):
    catalogue = tmp_path / "m.yaml"
    catalogue.write_text(
        "libre:\n"
        "  placa: [1, 1]\n"
        "  tolerancia_veta: 180\n"
        "estricto:\n"
        "  placa: [1, 1]\n"
        "  tolerancia_veta: 0\n",
        encoding="utf-8",
    )
    materials = load_materials(catalogue)
    assert materials["libre"].grain_tolerance == 180.0
    assert materials["estricto"].grain_tolerance == 0.0
    assert materials["libre"].sheet_w == 1.0
    assert materials["estricto"].sheet_h == 1.0
