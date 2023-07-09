from typing import NamedTuple


class Theme(NamedTuple):
    background: str
    foreground: str
    details: str

    def to_json(self):
        return list(self)


named = {
    "pink": Theme("#f3d7e6", "#5a5559", "#bfa8a8"),
    "gold": Theme("#292929", "#C5B067", "#171717"),
    "gray": Theme("#cbe2f3", "#555758", "#a1afba"),
    "blue": Theme("#B5D3FF", "#54575c", "#88ade7"),
}
