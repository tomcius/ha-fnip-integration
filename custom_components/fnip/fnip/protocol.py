from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class FNMessage:
    command: str
    channel: str   # always the physical channel number
    value: int     # ON/OFF → 1/0; LEV/VAL/etc. → raw integer


def build_command(*parts: str) -> str:
    """Return a FNIP command string: FN,CMD,p1,p2,...\r\n"""
    return "FN," + ",".join(parts) + "\r\n"


# Commands where protocol order is FN,CMD,STATUS,CHANNEL  (e.g. FN,OUT,ON,3)
_STATUS_COMMANDS = {"IN"}

# Commands where protocol order is FN,CMD,CHANNEL,VALUE  (e.g. FN,LEV,3,85)
_VALUE_COMMANDS = {
    "LEV", "VAL", "MONDUR", "RAMPRATE", "HOLDRATE",
    "MINLEV", "MAXLEV", "PRESLEV", "POW", "SCNO",
}

# FN,OUT,<STATUS|START|STOP>,channel[,level]
# ON/OFF → binary state; START → ramp started; STOP → ramp ended (level in 4th arg)
_3ARG_RE = re.compile(r"FN,(\w+),(\w+),(\w+)")
_4ARG_RE = re.compile(r"FN,(\w+),(\w+),(\w+),(\w+)")


def parse_messages(raw: str) -> list[FNMessage]:
    """Parse one or more FNIP messages from a raw received string."""
    messages = []
    remaining = raw

    while True:
        start = remaining.find("FN")
        end = remaining.find("\r")
        if start == -1 or end == -1 or end <= start:
            break

        segment = remaining[start:end]
        remaining = remaining[end + 1:]

        # Try 4-arg match first (e.g. FN,OUT,STOP,1,50)
        m4 = _4ARG_RE.match(segment)
        if m4:
            command, arg1, arg2, arg3 = m4.group(1), m4.group(2), m4.group(3), m4.group(4)
            # FN,OUT,STOP,channel,level  →  report the final level
            if command == "OUT" and arg1 == "STOP":
                channel = arg2
                value = int(arg3) if arg3.lstrip("-").isdigit() else 0
                messages.append(FNMessage(command="OUT_STOP", channel=channel, value=value))
            continue

        m3 = _3ARG_RE.match(segment)
        if not m3:
            continue

        command, arg1, arg2 = m3.group(1), m3.group(2), m3.group(3)

        if command == "OUT":
            if arg1 in ("ON", "OFF"):
                # FN,OUT,ON,3  →  relay state change
                channel = arg2
                value = 1 if arg1 == "ON" else 0
            elif arg1 == "START":
                # FN,OUT,START,channel  →  ramp started (arg2=channel, no value yet)
                messages.append(FNMessage(command="OUT_START", channel=arg2, value=0))
                continue
            else:
                continue
        elif command in _STATUS_COMMANDS:
            # FN,IN,ON,3  →  arg1=ON/OFF, arg2=channel
            channel = arg2
            value = 1 if arg1 == "ON" else 0
        else:
            # FN,LEV,3,85  →  arg1=channel, arg2=value
            channel = arg1
            value = int(arg2) if arg2.lstrip("-").isdigit() else 1

        messages.append(FNMessage(command=command, channel=channel, value=value))

    return messages
