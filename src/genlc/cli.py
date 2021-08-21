# cli.py

# TODO: More uniformity/consistency in cli commands and help messages

import logging
import time
from typing import Sequence, Set

import click
import hid

from genlc import __version__, const, gnet, sam, transport, util
from genlc.gnet import GNetTimeoutException

VOLUME = util.VolumeParamType()
MONITORS_OPTION = click.option(
    "--monitors",
    "-m",
    type=util.MonitorListParamType(),
    help="SAM monitor addresses (comma separated)",
)

sg: sam.SAMGroup = None
usb_adapter: sam.USBAdapter = None


def validated_monitors(
    monitors: Set[sam.BaseDevice],
    allow_address_1: bool = False,
    default_all: bool = True,
) -> Sequence[sam.BaseDevice]:
    """Return a validated sequence of monitors

    Args:
        monitors: Set of monitor addresses, as parsed by MonitorListParamType
        allow_address_1: Include address 1 (the USB adapter) as a valid monitor target
        default_all: Whether monitor == None implies returning all discovered monitors

    Return:
        A sequence of BaseDevice instances that were both discovered and specified

    Raises:
        click.BadParameter: if a monitor specified was not discovered
    """

    sg = click.get_current_context().obj["samgroup"]
    discovered_monitors = {
        device.address: device
        for device in sg.discover_monitors(all=True)
        if device.address != 1 or allow_address_1
    }
    if monitors is None and default_all:
        return list(discovered_monitors.values())

    try:
        return [discovered_monitors[addr] for addr in monitors]
    except KeyError:
        raise click.BadParameter(
            f"Monitor list {monitors} contains unassigned addresses "
            f"(monitors that were not discovered): {monitors.difference(discovered_monitors)}"
        )


def get_samgroup() -> sam.SAMGroup:
    """Make a connection with the USB adapter and instantiate a GLM object"""

    try:
        hid_glm_adapter = hid.Device(const.GENELEC_GLM_VID, const.GENELEC_GLM_PID)
        usbtransport = transport.USBTransport(hid_glm_adapter)
        return sam.SAMGroup(usbtransport)
    except hid.HIDException as he:
        raise click.ClickException(f"Opening USB device: {he}")


def discover_monitors():
    list(sg.discover_monitors())


@click.group(chain=True)
@click.version_option(version=__version__)
@click.option("--debug/--no-debug", default=False)
@click.pass_context
def main(ctx, debug):
    """Allows control of a Genelec monitor group or individual SAM monitors"""

    global sg, usb_adapter

    logging.basicConfig(level=(logging.DEBUG if debug else None))
    sg = get_samgroup()
    usb_adapter = sam.USBAdapter(sg)

    # Ensure ctx.obj exists as a dict, store samgroup instance
    ctx.ensure_object(dict)
    ctx.obj["samgroup"] = sg
    ctx.with_resource(sg.transport.adapter)


@main.command()
def discover():
    """Discover devices on the GLM network"""

    hid_glm_adapter = sg.transport.adapter
    click.echo(
        (
            f"Found USB adapter: {hid_glm_adapter.manufacturer} {hid_glm_adapter.product} "
            f"with serial #{hid_glm_adapter.serial}"
        ),
    )
    try:
        click.echo(f"[1] {usb_adapter.query_hardware()[0]}")
        click.echo(f"\tsoftware {usb_adapter.query_software()}")
        click.echo(f"\tbar code {usb_adapter.query_barcode()}")
        click.echo(f"\tmicrophone serial #{usb_adapter.query_mic_serial()}")
    except gnet.GNetTimeoutException as te:
        raise click.ClickException(f"Timeout communicating with the GLM adapter: {te}")

    for monitor in sg.discover_monitors(all=True):
        if monitor.address == 1:
            # Skip the USBAdapter here
            continue

        try:
            monitor.query_hardware()
            monitor.query_software()
            monitor.query_barcode()
        except gnet.GNetTimeoutException as te:
            click.echo(f"Timeout communicating with monitor {monitor}", err=True)
        else:
            click.echo(f"[{monitor.address}] {monitor.hardware[0]}")
            click.echo(f"\tserial #{monitor.serial}")
            click.echo(
                f"\tsoftware {monitor.software_str.split(';')[2]} {monitor.software_str.split(';')[4]}"
            )
            click.echo(f"\tbar code {monitor.barcode}")


@main.command()
@click.option(
    "--volume",
    type=VOLUME,
    required=True,
    help="volume in dB or %",
    metavar="VOLUME %/dB",
)
def set_volume(volume: float):
    """Set volume for all GLM devices"""

    click.echo(f"Setting volume to {volume:.2f} dB")
    sg.set_volume_glm(volume)


@main.command()
@click.option("--count", type=click.INT, default=1, help="Poll INTEGER times")
@click.option("--continuous", is_flag=True, default=False, help="Continuous polling")
@click.option(
    "--interval", type=click.FLOAT, default=1.0, help="Repeat every FLOAT seconds"
)
def poll(count, continuous, interval):
    """Poll parameters of SAM monitors"""
    discover_monitors()
    # Poll the monitors
    monitors = sg.devices.values()
    while continuous or count > 0:
        count -= 1
        for monitor in monitors:
            try:
                monitor.poll()
            except GNetTimeoutException:
                continue
            else:
                click.echo(
                    f"[{monitor.address}] "
                    + ", ".join(
                        (f"{f}: {v:.3f}" for f, v in monitor.poll_fields.items())
                    )
                )
        if interval and (continuous or count > 0):
            discover_monitors()
            time.sleep(interval)


@main.command()
def wakeup():
    """Wake up all SAM monitors"""

    click.echo("Waking up all SAM monitors")
    sg.wakeup_all()


@main.command()
def shutdown():
    """Shutdown all SAM monitors"""

    click.echo("Putting all SAM monitors to sleep")
    sg.shutdown_all()


@main.command()
@MONITORS_OPTION
def mute(monitors):
    """Mute a SAM monitor"""

    for monitor in validated_monitors(monitors):
        click.echo(f"Muting monitor {monitor}")
        monitor.mute()


@main.command()
@MONITORS_OPTION
def unmute(monitors):
    """Unmute a SAM monitor"""

    for monitor in validated_monitors(monitors):
        click.echo(f"Unmuting monitor {monitor}")
        monitor.mute(mute=False)


# Experimental commands below here


@main.command()
@MONITORS_OPTION
@click.option("--gain", type=click.INT)
def gain(monitors, gain):
    """Set SAM monitor gain"""

    for monitor in validated_monitors(monitors):
        click.echo(f"Setting gain of monitor {monitor} to {gain}")
        monitor.set_digisum_gain(gain)


@main.command()
@MONITORS_OPTION
@click.option(
    "--value",
    type=click.IntRange(min=0, max=255),
    required=False,
    hidden=True,
    help="Bypass parameter value to send to the monitor",
)
@click.option("--mute/--unmute", required=False, default=None, help="Mute/unmute sound")
@click.option(
    "--led-color",
    type=click.Choice(["green", "red", "yellow", "off"], case_sensitive=False),
    required=False,
    help="LED color, or disable (off)",
)
@click.option(
    "--led-pulsing/--led-solid",
    required=False,
    default=None,
    help="Solid or pulsing LED light",
)
@click.option(
    "--invert-led-enable",
    is_flag=True,
    required=False,
    default=None,
    help="Invert LED on/off",
)
def bypass(monitors, **kwargs):
    """Set monitor bypass"""

    for monitor in validated_monitors(monitors):
        click.echo(
            f"Setting monitor {monitor} to bypass: "
            f"{({k: v for (k, v) in kwargs.items() if v is not None})}"
        )
        monitor.bypass(**kwargs)


@main.command()
@MONITORS_OPTION
@click.option(
    "--xo-freq",
    type=click.INT,
    required=False,
    default=const.DEFAULT_XO_FREQ,
    help="Crossover frequency (Hz)",
)
def bass_manage(monitors, xo_freq: int):
    """Configure bass management"""

    for monitor in validated_monitors(monitors):
        if xo_freq is not None:
            click.echo(
                f"Setting bass management crossover frequency of monitor {monitor} to {xo_freq} Hz"
            )
            monitor.bass_manage_xo(xo_freq)
