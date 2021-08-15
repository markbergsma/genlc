# genlc #

Unofficial module for managing Genelec SAM monitors through the GLM network adapter.

`genlc` is a Python module allowing (automatic or manual) control of Genelec loudspeakers (monitors/subwoofers) in the Smart Active Monitor range, i.e. those with GLM network connections. genlc currently implements the very basics, i.e. a _tiny_ subset of GLM:
* discovery of monitors on the network
* wakeup and shutdown
* polling of some parameters of monitors
* volume setting
* mute and unmute
* LED on/off/color/pulsing

A CLI application with the same name is included for easy control from the command line.

The GLM protocol used by Genelec is a proprietary binary protocol, which is being reverse engineered to implement genlc. Therefore there may be surprises, and YMMV. The code has been tested so far with 2x Genelec 8330 and a 7350 subwoofer.

My main use case is/was to better integrate my Genelec monitors into my Home Assistant setup for music listening and home theater applications, but with a generic Python module a lot more could be possible.

## genlc (CLI) usage ##

Show information about all SAM devices on the network:

    $ genlc discover

Set volume to -18 dB:

    $ genlc set-volume --volume=-18dB

Mute a single monitor with address `2`

    $ genlc mute -m 2

Show certain parameters of all monitors continuously, every 3s:

    $ genlc poll --continuous --interval 3

Combine multiple commands:

    $ genlc discover wakeup set-volume --volume=75% poll --count=10

...or even repeat the same ones:
    
    $ genlc bypass -m 2,3 --led-color red --led-pulsing bypass -m 4,5 --led-color yellow --led-solid

More usage information:

    $ genlc --help

## Installation ##
For now this is very experimental code, best pip3 install from the repository URL. I intend to publish it to PyPi once things are a bit more stable.

genlc depends on the libusb/libhid libraries to access the GLM USB adapter, and those should be installed separately. Best use the `libusb0` backend of `libusb`, although `hidraw0` could also work (untested). To install on e.g. a Debian-derived system, this should work:

    # apt-get install libhidapi-libusb0
