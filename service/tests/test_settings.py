import json
import pytest
from sunlight.settings import Settings, load, save, from_dict


def test_defaults():
    s = Settings()
    assert (s.wake, s.days, s.length_min, s.hold_min) == ("06:30", [0, 1, 2, 3, 4], 30, 30)
    assert s.floor and s.sunset and s.enabled and not s.stay_on


def test_load_missing_file_gives_defaults(tmp_path):
    assert load(tmp_path / "none.json") == Settings()


def test_load_corrupt_file_gives_defaults(tmp_path):
    p = tmp_path / "s.json"; p.write_text("{not json")
    assert load(p) == Settings()


def test_roundtrip(tmp_path):
    p = tmp_path / "s.json"
    s = Settings(wake="07:05", days=[5, 6], length_min=45)
    save(s, p)
    assert load(p) == s
    assert json.loads(p.read_text())["wake"] == "07:05"


@pytest.mark.parametrize("bad", [
    {"wake": "25:00"}, {"wake": "7:5x"}, {"length_min": 5}, {"length_min": 61},
    {"hold_min": -1}, {"days": [7]}, {"days": "mon"},
])
def test_validate_rejects(bad):
    with pytest.raises(ValueError):
        from_dict({**Settings().to_dict(), **bad})


def test_from_dict_ignores_unknown_keys():
    assert from_dict({"wake": "05:00", "junk": 1}).wake == "05:00"
