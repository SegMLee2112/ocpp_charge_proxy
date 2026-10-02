from src.persistence import Persistence


def test_load_energy_register_default(tmp_path):
    p = Persistence(data_dir=str(tmp_path))
    assert p.load_energy_register_wh() == 0


def test_save_and_load_energy_register(tmp_path):
    p = Persistence(data_dir=str(tmp_path))
    p.save_energy_register_wh(12345)
    assert p.load_energy_register_wh() == 12345


def test_load_corrupt_file_returns_default(tmp_path):
    p = Persistence(data_dir=str(tmp_path))
    path = tmp_path / "energy_register.json"
    path.write_text("not json{{{")
    assert p.load_energy_register_wh() == 0


def test_serial_number_generated_and_persisted(tmp_path):
    p = Persistence(data_dir=str(tmp_path))
    serial = p.load_serial_number()
    assert len(serial) == 6
    assert serial.isdigit()
    # Second call returns same value
    assert p.load_serial_number() == serial


def test_seed_energy_register_applies_when_higher(tmp_path):
    p = Persistence(data_dir=str(tmp_path))
    p.save_energy_register_wh(1000)
    assert p.seed_energy_register_wh(6582198) is True
    assert p.load_energy_register_wh() == 6582198


def test_seed_energy_register_ignored_when_lower_or_equal(tmp_path):
    """A stale seed must never move the meter backwards."""
    p = Persistence(data_dir=str(tmp_path))
    p.save_energy_register_wh(6583000)
    assert p.seed_energy_register_wh(6582198) is False
    assert p.seed_energy_register_wh(6583000) is False
    assert p.load_energy_register_wh() == 6583000


def test_seed_energy_register_on_fresh_install(tmp_path):
    p = Persistence(data_dir=str(tmp_path))
    assert p.seed_energy_register_wh(500) is True
    assert p.load_energy_register_wh() == 500


def test_offline_queue_round_trip(tmp_path):
    p = Persistence(data_dir=str(tmp_path))
    assert p.load_offline_queue() == []
    p.save_offline_queue([{"seq": 1, "action": "StopTransactionPayload", "payload": {"meter_stop": 1}}])
    assert Persistence(data_dir=str(tmp_path)).load_offline_queue()[0]["payload"]["meter_stop"] == 1
