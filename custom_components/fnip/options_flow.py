"""Options flow for FutureNow FNIP — edit channel names/roles after setup."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CHANNELS,
    CONF_INPUTS,
    CONF_MODULE_TYPE,
    CONF_NAME,
    CONF_OUTPUTS,
    CONF_ROLE,
    MODULE_TYPES,
    ROLE_LIGHT,
    ROLE_SWITCH,
)


class FnipOptionsFlow(OptionsFlow):
    """Re-run the channel-naming step against the entry's current values."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        module_type = self._entry.data[CONF_MODULE_TYPE]
        spec = MODULE_TYPES[module_type]
        current = self._entry.data.get(CONF_CHANNELS, {CONF_OUTPUTS: {}, CONF_INPUTS: {}})

        if user_input is not None:
            outputs: dict[str, dict[str, str]] = {}
            for ch in range(1, spec.n_outputs + 1):
                ch_s = str(ch)
                role = (
                    user_input.get(f"out_{ch_s}_role", ROLE_SWITCH)
                    if spec.output_domain is None
                    else spec.output_domain
                )
                outputs[ch_s] = {
                    CONF_ROLE: role,
                    CONF_NAME: user_input.get(f"out_{ch_s}_name", f"Output {ch_s}"),
                }

            inputs: dict[str, dict[str, str]] = {}
            for ch in range(1, spec.n_inputs + 1):
                ch_s = str(ch)
                inputs[ch_s] = {
                    CONF_NAME: user_input.get(f"in_{ch_s}_name", f"Input {ch_s}"),
                }

            new_data = dict(self._entry.data)
            new_data[CONF_CHANNELS] = {CONF_OUTPUTS: outputs, CONF_INPUTS: inputs}
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            return self.async_create_entry(title="", data={})

        fields: dict[Any, Any] = {}
        cur_out = current.get(CONF_OUTPUTS, {})
        cur_in = current.get(CONF_INPUTS, {})

        for ch in range(1, spec.n_outputs + 1):
            ch_s = str(ch)
            existing = cur_out.get(ch_s, {})
            fields[
                vol.Optional(f"out_{ch_s}_name", default=existing.get(CONF_NAME, f"Output {ch_s}"))
            ] = str
            if spec.output_domain is None:
                fields[
                    vol.Optional(f"out_{ch_s}_role", default=existing.get(CONF_ROLE, ROLE_SWITCH))
                ] = selector.SelectSelector(
                    selector.SelectSelectorConfig(options=[ROLE_LIGHT, ROLE_SWITCH])
                )

        for ch in range(1, spec.n_inputs + 1):
            ch_s = str(ch)
            existing = cur_in.get(ch_s, {})
            fields[
                vol.Optional(f"in_{ch_s}_name", default=existing.get(CONF_NAME, f"Input {ch_s}"))
            ] = str

        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
