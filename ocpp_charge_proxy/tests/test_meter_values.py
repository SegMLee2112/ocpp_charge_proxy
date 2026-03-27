from src.charger_sim import ChargerReading
from src.meter_values import build_charging_meter_values, build_idle_meter_values


def _make_reading(**kwargs) -> ChargerReading:
    defaults = dict(
        power_kw=7.27, voltage=230.0, current_a=31.61,
        frequency_hz=50.01, power_offered_kw=7.4, current_offered_a=32,
    )
    defaults.update(kwargs)
    return ChargerReading(**defaults)


def test_idle_meter_values_single_entry():
    mv = build_idle_meter_values(energy_register_wh=10500)
    assert len(mv) == 1


def test_idle_meter_values_has_four_measurands():
    mv = build_idle_meter_values(energy_register_wh=10500)
    measurands = {sv["measurand"] for sv in mv[0]["sampledValue"]}
    assert measurands == {
        "Power.Active.Import", "Power.Active.Export",
        "Energy.Active.Import.Register", "Energy.Active.Export.Register",
    }


def test_idle_power_is_zero():
    mv = build_idle_meter_values(energy_register_wh=10500)
    power_sv = [sv for sv in mv[0]["sampledValue"] if sv["measurand"] == "Power.Active.Import"][0]
    assert power_sv["value"] == "0.0"
    assert power_sv["unit"] == "W"


def test_idle_export_is_zero():
    mv = build_idle_meter_values(energy_register_wh=10500)
    export_sv = [sv for sv in mv[0]["sampledValue"] if sv["measurand"] == "Power.Active.Export"][0]
    assert float(export_sv["value"]) == 0.0
    assert export_sv["unit"] == "W"
    export_energy_sv = [sv for sv in mv[0]["sampledValue"] if sv["measurand"] == "Energy.Active.Export.Register"][0]
    assert float(export_energy_sv["value"]) == 0.0
    assert export_energy_sv["unit"] == "Wh"


def test_idle_energy_register():
    mv = build_idle_meter_values(energy_register_wh=10500)
    energy_sv = [sv for sv in mv[0]["sampledValue"] if sv["measurand"] == "Energy.Active.Import.Register"][0]
    assert energy_sv["value"] == "10500.0"
    assert energy_sv["unit"] == "Wh"


def test_idle_meter_values_have_metadata():
    mv = build_idle_meter_values(energy_register_wh=10500)
    for sv in mv[0]["sampledValue"]:
        assert sv["format"] == "Raw"
        assert sv["location"] == "Outlet"
        assert sv["context"] == "Sample.Periodic"


def test_charging_meter_values_single_entry():
    mv = build_charging_meter_values(
        reading=_make_reading(), energy_register_wh=10500,
    )
    assert len(mv) == 1


def test_charging_meter_values_has_seven_measurands():
    """Real Wallbox reports 7 measurands (no SoC)."""
    mv = build_charging_meter_values(
        reading=_make_reading(), energy_register_wh=10500,
    )
    measurands = {sv["measurand"] for sv in mv[0]["sampledValue"]}
    assert measurands == {
        "Power.Active.Import", "Power.Active.Export",
        "Frequency", "Current.Offered", "Power.Offered",
        "Energy.Active.Import.Register", "Energy.Active.Export.Register",
    }


def test_charging_uses_reading_values():
    reading = _make_reading(power_kw=7.25, current_a=31.52, frequency_hz=50.03)
    mv = build_charging_meter_values(
        reading=reading, energy_register_wh=10500,
    )
    samples = {sv["measurand"]: sv["value"] for sv in mv[0]["sampledValue"]}
    assert samples["Power.Active.Import"] == "7250.0"  # W not kW
    assert samples["Current.Offered"] == "32"
    assert samples["Frequency"] == "50.03"
    assert samples["Power.Offered"] == "7400"  # W not kW


def test_charging_units_are_watts():
    mv = build_charging_meter_values(
        reading=_make_reading(), energy_register_wh=10500,
    )
    samples = {sv["measurand"]: sv for sv in mv[0]["sampledValue"]}
    assert samples["Power.Active.Import"]["unit"] == "W"
    assert samples["Power.Active.Export"]["unit"] == "W"
    assert samples["Power.Offered"]["unit"] == "W"
    assert samples["Energy.Active.Import.Register"]["unit"] == "Wh"
    assert samples["Energy.Active.Export.Register"]["unit"] == "Wh"
    assert samples["Current.Offered"]["unit"] == "A"


def test_charging_export_is_zero():
    mv = build_charging_meter_values(
        reading=_make_reading(), energy_register_wh=10500,
    )
    samples = {sv["measurand"]: sv["value"] for sv in mv[0]["sampledValue"]}
    assert samples["Power.Active.Export"] == "0"
    assert samples["Energy.Active.Export.Register"] == "0"


def test_charging_meter_values_have_metadata():
    mv = build_charging_meter_values(
        reading=_make_reading(), energy_register_wh=10500,
    )
    for sv in mv[0]["sampledValue"]:
        assert sv["format"] == "Raw"
        assert sv["location"] == "Outlet"
        assert sv["context"] == "Sample.Periodic"


def test_charger_sim_steady_state():
    from src.charger_sim import ChargerSimulator
    sim = ChargerSimulator()
    sim.start_charging()
    readings = [sim.sample().power_kw for _ in range(100)]
    assert all(0.1 <= r <= 7.5 for r in readings)
    mean = sum(readings) / len(readings)
    assert 7.15 <= mean <= 7.40  # should cluster around 7.27


def test_charger_sim_idle():
    from src.charger_sim import ChargerSimulator
    sim = ChargerSimulator()
    reading = sim.sample()
    assert reading.power_kw == 0.0
    assert reading.current_a == 0.0
    assert reading.power_offered_kw == 0.0
