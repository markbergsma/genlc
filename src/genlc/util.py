# genlc/util.py

"""
Utility classes and functions for genlc
"""


import logging
import math
from typing import Set, Union

import click

logger = logging.getLogger(__name__)


def vol_dB_from_pct(vol_pct: float) -> float:
    """Converts a volume percentage to a dB value"""

    return 20 * math.log10(vol_pct / 100.0)


def vol_sint24_from_dB(vol_dB: float) -> int:
    """Converts a volume in dB to a 24 bit linear integer"""

    vol_ratio = 10 ** (vol_dB / 20.0)
    return int(vol_ratio * (2 ** 23 - 1))


def dBSPL_from_sint24(vol_linear: int) -> float:
    """Converts a linear value to dBSPL"""

    p0 = 20.0  # uPa    # FIXME: GLM sets mic reference level at 70
    return 20 * math.log10(float(vol_linear) / p0)


class VolumeParamType(click.ParamType):
    """Click Volume parameter type

    This class converts a string value to a decibel float.
    Two formats are accepted:
    - a percentage (0.0 - 100.0), with suffix '%'
    - a decibel (-130.0 - 0), with suffix 'dB'
    """

    name = "volume"

    def convert(self, value, param, ctx):
        if isinstance(value, float):
            return value

        try:
            if value.endswith("%"):
                # Map volume percentage to range of -120.0 to 0.0 dB
                vol_pct = click.FloatRange(min=0.0001, max=100.0, clamp=True).convert(
                    value.replace("%", ""), param, ctx
                )
                # Convert percentage [0, 100] to dB value [-130.0, 0.0]
                value = vol_dB_from_pct(vol_pct)
            elif value.lower().endswith("db"):
                value = value.lower().replace("db", "")
            else:
                self.fail("Please specify suffix '%' or 'dB'", param, ctx)
            return click.FloatRange(min=-130.0, max=0.0).convert(value, param, ctx)
        except ValueError:
            self.fail(f"{value!r} is not a valid volume string", param, ctx)


class MonitorListParamType(click.ParamType):
    """Click MonitorList parameter type

    This class parses a comma separated list of ints
    (monitor addresses/#serials) and converts it into a set
    """

    name = "monitorlist"

    def convert(self, value: Union[str, Set], param, ctx) -> Set[Union[int, str]]:
        if isinstance(value, set):
            return value

        try:
            parts = (part.strip() for part in value.split(","))
            return {
                id if id[0] == "#" and id[1:].isnumeric() else int(id) for id in parts
            }
        except ValueError:
            self.fail(f"{value!r} is not a valid monitor list", param, ctx)
