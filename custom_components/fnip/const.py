"""Constants and module-type metadata for the FutureNow FNIP integration."""
from __future__ import annotations

from dataclasses import dataclass

DOMAIN = "fnip"
DEFAULT_PORT = 7078

CONF_MAC = "mac"
CONF_MODULE_TYPE = "module_type"
CONF_CHANNELS = "channels"
CONF_OUTPUTS = "outputs"
CONF_INPUTS = "inputs"
CONF_ROLE = "role"
CONF_NAME = "name"

ROLE_LIGHT = "light"
ROLE_SWITCH = "switch"
ROLE_COVER = "cover"

# Module types with live, tested FNIP commands in fnip_mcp_server (v1 scope).
# MZT / RGB&010 intentionally excluded — no implemented/tested commands yet.
TYPE_REL = "REL"
TYPE_IO = "IO"
TYPE_DIM = "DIM"
TYPE_PWM = "PWM"
TYPE_SH = "SH"


@dataclass(frozen=True)
class ModuleTypeSpec:
    key: str
    label: str
    n_outputs: int
    n_inputs: int
    # Fixed HA domain for outputs: None means the role is user-selectable
    # (light vs switch) in the config flow — only true for REL/IO.
    output_domain: str | None
    level_scale: int | None = None  # None = no LEV support (plain ON/OFF)
    has_position: bool = False      # True = cover-style GOTO/STOP semantics


MODULE_TYPES: dict[str, ModuleTypeSpec] = {
    TYPE_REL: ModuleTypeSpec(
        key=TYPE_REL, label="FNIP-8x10A / FNIP-8x16A (Relay)",
        n_outputs=8, n_inputs=8, output_domain=None,
    ),
    TYPE_IO: ModuleTypeSpec(
        key=TYPE_IO, label="FNIP-12xIO (12 In / 13 Out)",
        n_outputs=13, n_inputs=12, output_domain=None,
    ),
    TYPE_DIM: ModuleTypeSpec(
        key=TYPE_DIM, label="FNIP-6x2AD (Dimmer)",
        n_outputs=6, n_inputs=6, output_domain=ROLE_LIGHT, level_scale=100,
    ),
    TYPE_PWM: ModuleTypeSpec(
        key=TYPE_PWM, label="FNIP-12xPWM (PWM/RGB)",
        n_outputs=12, n_inputs=12, output_domain=ROLE_LIGHT, level_scale=255,
    ),
    TYPE_SH: ModuleTypeSpec(
        key=TYPE_SH, label="FNIP-4xSH (Shade)",
        n_outputs=4, n_inputs=8, output_domain=ROLE_COVER, level_scale=100,
        has_position=True,
    ),
}


def detect_type_from_mtype(mtype_string: str) -> str | None:
    """Map a raw 'FN,MTYPE,<string>' payload to one of MODULE_TYPES' keys.

    Mirrors the substring matching already proven in test_device.py's
    run_tests() — keep these two in sync if a new type string is seen live.
    """
    s = mtype_string.upper()
    if "12XIO" in s:
        return TYPE_IO
    if "6X2AD" in s or s == TYPE_DIM:
        return TYPE_DIM
    if "8X16A" in s or "8X10A" in s or s == TYPE_REL:
        return TYPE_REL
    if "4XSH" in s or s == TYPE_SH:
        return TYPE_SH
    if "12XPWM" in s or s == TYPE_PWM:
        return TYPE_PWM
    return None
