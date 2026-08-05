from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChannelNames:
    outputs: dict[str, str] = field(default_factory=dict)   # "1" → "Pompa CO"
    inputs: dict[str, str] = field(default_factory=dict)    # "1" → "Czujnik przepływu"


@dataclass
class ModuleState:
    outputs: dict[str, bool] = field(default_factory=dict)
    inputs: dict[str, bool] = field(default_factory=dict)
    analog_inputs: dict[str, int] = field(default_factory=dict)   # 12xIO: 0–999 × 0.1 kΩ
    levels: dict[str, int] = field(default_factory=dict)           # dimmers/shades: 0–100 or 0–255
