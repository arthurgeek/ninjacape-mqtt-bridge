# Ninja Cape MQTT Bridge

## What it is

Python script for grabbing JSON data over serial from the NinjaCape and 
publishing it as MQTT messages.

## Ninja Blocks

Ninja Blocks is a now defunct software project that typically used
a Beagle Bone Black (BBB) and Arduino based Ninja Cape to do smart home
(home automation, IOT) type things. It was web based using cloud severs
that are long dead now.

The usefulness of the Ninja Cape is that it had 433MHz wireless comms
and talked to a variety of sensors that came with the Ninja Blocks kit.
These included door bell (button), proximity sensor, temperature sensor,
PIR sensor.

The Ninja Cape uses normal 9600 baud serial to talk with BBB to report
433Mhz messages it receives from sensors.

The script in this repo replaces all that Ninja Blocks code with a 
simple script that reads the serial messages from Ninja Cape and 
publishes them with MQTT so that you can integrate with Home Assistant
or OpenHAB.

## Requirements

You need to have an MQTT broker installed, such as http://mosquitto.org/

It you use Hassio for Home Assistant, you can install its MQTT plugin.

You need a Python 3.5 environment on the target device. It can be a 
Ninja Blocks Beagle Bone Black or Raspberry Pi.

I used BBB and put a fresh Debian image on it with SD card.

The python script requires python libraries for PySerial and Paho MQTT

```
pip install pyserial
pip install paho-mqtt
```

## MQTT Details
MQTT messages are structured as follows:

* Messages received on 433Mhz as published to:
  * topic = `/ninjaCape/input/<DeviceID>` 
  * payload = `DeviceData`

* Messages to be sent to ninja cape should be published to:
  * topic = `/ninjaCape/output/<DeviceID>` 
  * payload = `DeviceData`
  * These messages are only to change LEDs so far as I know (status and eyes)
  * The script subscribes to all updates on `/ninjaCape/output/#`

```
Device Type   Device
11            Generic switch device (Sockets, Buttons, PIRs)
30            Humidity Sensor
31            Temperature Sensor
999           NinjaBlock Status Light
1007          NinjaBlock Eyes
```

Full list of device ids on the [web archive](https://web.archive.org/web/20160505082642/http://shop.ninjablocks.com/pages/device-ids)

## TODO List
* Make it daemon-ised.  At the moment I'm just running it in a 'screen' instance.
* Catch invalid JSON messages and throw an error, instead of just ignoring it.
