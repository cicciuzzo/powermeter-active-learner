# engine/__init__.py
# State constants shared across all modules

IDLE = 0
WASHER = 1
DRYER = 2
BOTH = 3

STATE_NAMES: dict[int, str] = {
    IDLE: "IDLE",
    WASHER: "WASHER",
    DRYER: "DRYER",
    BOTH: "BOTH",
}
