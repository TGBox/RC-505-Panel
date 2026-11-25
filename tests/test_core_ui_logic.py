from rc_505_panel.core.actions import DEFAULT_KEYS, Action, ActionBus
from rc_505_panel.core.device_watch import DeviceStatus, detect, find_storage
from rc_505_panel.core.models import DeviceMode


def test_action_bus_dispatch_and_log():
    bus, seen = ActionBus(), []
    bus.subscribe(seen.append)
    a = Action("drop", 3, source="key")
    bus.dispatch(a)
    assert seen == [a] and bus.log[-1] == a


def test_default_keys():
    assert DEFAULT_KEYS["F2"] == Action("drop", 2, source="key")
    assert DEFAULT_KEYS["Ctrl+F5"].name == "stop" and DEFAULT_KEYS["Ctrl+F5"].track == 5


def test_find_storage(tmp_path):
    drive = tmp_path / "J"
    assert find_storage([drive]) is None
    (drive / "ROLAND" / "DATA").mkdir(parents=True)
    (drive / "ROLAND" / "WAVE").mkdir()
    assert find_storage([drive]) == drive / "ROLAND"
    assert find_storage([tmp_path]) == drive / "ROLAND"           # eine Ebene tiefer (/media/<user>)


def test_detect_storage_has_priority(tmp_path):
    (tmp_path / "ROLAND" / "DATA").mkdir(parents=True)
    (tmp_path / "ROLAND" / "WAVE").mkdir()
    st = detect(extra_storage=[tmp_path])
    assert st.mode is DeviceMode.STORAGE and st.roland == tmp_path / "ROLAND"
    assert DeviceStatus(DeviceMode.OFFLINE).label == "OFFLINE"
