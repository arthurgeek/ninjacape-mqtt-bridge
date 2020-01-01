#!/usr/bin/python
"""
Interface the NinjaCape to MQTT

For use with Home Assistant or OpenHAB.

 * reads data from serial port and publishes on MQTT client
 * writes data to serial port from MQTT subscriptions

Uses the Python MQTT client from the Mosquitto project http://mosquitto.org (now in Paho)

https://github.com/tazard/ninjacape-mqtt-bridge

Originally by perrin7
Reworked by tazard 2019-12-30
"""

# TODO: Consider handling SIGTERM --
#  https://stackoverflow.com/questions/18499497/how-to-process-sigterm-signal-gracefully
#  https://stackabuse.com/handling-unix-signals-in-python/

import json
import subprocess
import threading
import time

import paho.mqtt.client as mqtt
import serial

# Settings
config_path = 'config.json'
# serial_dev_path = '/dev/ttyO1'  # for BBB
# # serial_dev_path = '/dev/ttyAMA0' # for RPi
#
# broker = "hassio"  # mqtt broker
# port = 1883  # mqtt broker port
#
# # Pins for serial UART
# # (on BBB A5C with 2019-08 image requires these to be set)
# # Set to empty list if no pins need to be configured on your platform
# uart_pins = [
#     # "P9.26",
#     # "P9.24",
# ]

debug = True  # Debug printing
dummy_serial = False  # Fake serial for testing

# buffer of data to output to the serial port
outputData = []


class FakeSerial:
    """Fake serial object for local testing"""
    def flushInput(self):
        pass

    def readline(self):
        while True:
            pass

    def write(self, message):
        pass

    def close(self):
        pass


class Config:
    def __init__(self, path):
        """JSON config file for this script"""
        with open(path, 'r') as f:
            j = json.load(f)
        self.j = j
        self.mqtt_host = j['mqtt']['host']
        self.mqtt_port = j['mqtt']['port']
        self.mqtt_auth_enabled = j['mqtt']['auth']['enabled']
        self.mqtt_auth_user = j['mqtt']['auth']['user']
        self.mqtt_auth_pass = j['mqtt']['auth']['pass']
        self.serial_path = j['serial']['path']
        self.serial_uart_pins = j['serial']['uart_pins']


def mqtt_on_connect(client, userdata, flags, rc):
    if rc == 0:
        # rc 0 successful connect
        print("Connected")
    else:
        print("Connection failed, rc={}".format(rc))
        raise Exception
    # subscribe to the output MQTT messages
    client.subscribe("ninjaCape/output/#")


def mqtt_on_publish(client, userdata, mid):
    if debug:
        print("Published. mid:", mid)


def mqtt_on_subscribe(client, userdata, mid, granted_qos):
    if debug:
        print("Subscribed. mid:", mid)


def mqtt_on_ninja_cape_output(client, userdata, msg):
    """Queue message to be sent to ninja cape over serial"""
    if debug:
        print("Output Data: ", msg.topic, "data:", msg.payload)
    # add to outputData list
    outputData.append(msg)


def mqtt_on_unhandled_message(client, userdata, message):
    if debug:
        print("Unhandled Message Received: ", message.topic, message.paylod)


def cleanup(ser, mqtt):
    """Called on exit to close serial and disconnect MQTT"""
    print("Ending and cleaning up")
    ser.close()
    mqtt.loop_stop()


def mqtt_to_json_output(mqtt_message):
    """convert mqtt_message into a json string for ninja cape serial"""
    topics = mqtt_message.topic.split('/')
    data = mqtt_message.payload.decode()
    # JSON message in ninjaCape form
    json_data = '{"DEVICE": [{"G":"0","V":0,"D":' + str(topics[2]) + ',"DA":"' + data + '"}]})'
    return json_data


def serial_read_and_publish(ser, mqtt):
    """thread for reading serial data and publishing to MQTT client"""
    ser.flushInput()

    while True:
        line = ser.readline()  # this is blocking
        line = line.decode()
        if debug:
            print()
            cleaned_line = line.replace('\r', '').replace('\n', '')
            print("Received from ninja cape:\n{}".format(cleaned_line))

        # split the JSON packet up here and publish on MQTT
        json_data = json.loads(line)

        if 'DEVICE' in json_data:
            # Received device update
            try:
                device = str(json_data['DEVICE'][0]['D']) + "_" + str(json_data['DEVICE'][0]['G'])
                message = str(json_data['DEVICE'][0]['DA'])
            except KeyError as e:
                print("Error while extracting device or message from received DEVICE JSON data: {}".format(e))
            else:
                # No exceptions - data ok
                topic = "ninjaCape/input/" + device
                print("Publishing MQTT: topic='{}', message='{}'".format(topic, message))
                mqtt.publish(topic, message)
        elif 'ACK' in json_data:
            # Received ACK
            # {"ACK":[{"G":"0","V":0,"D":1007,"DA":"FFFF00"}]}
            try:
                device = str(json_data['ACK'][0]['D']) + "_" + str(json_data['ACK'][0]['G'])
                message = str(json_data['ACK'][0]['DA'])
            except KeyError as e:
                print("Error while extracting device or message from received ACK JSON data: {}".format(e))
            else:
                print("ACK from ninjaCape: device='{}', message='{}'".format(device, message))
        else:
            print("Unknown message type: {}".format(json_data))


def main():
    # load config
    config = Config(config_path)

    if len(config.serial_uart_pins) > 0:
        print("Setting up UART pins")
        for pin in config.serial_uart_pins:
            command = "config-pin {} uart".format(pin)
            print(" running: {}".format(command))
            subprocess.check_call(command, shell=True)

    # Connect serial port
    if not dummy_serial:
        print("Connecting... {}".format(config.serial_path))
        # timeout 0 for non-blocking. Set to None for blocking.
        ser = serial.Serial(config.serial_path, 9600, timeout=None)
    else:
        ser = FakeSerial()

    # create an mqtt client
    mqtt_client = mqtt.Client("ninjaCape")

    # attach MQTT callbacks
    mqtt_client.on_connect = mqtt_on_connect
    mqtt_client.on_publish = mqtt_on_publish
    mqtt_client.on_subscribe = mqtt_on_subscribe
    mqtt_client.on_message = mqtt_on_unhandled_message
    mqtt_client.message_callback_add("ninjaCape/output/#", mqtt_on_ninja_cape_output)

    # connect to MQTT broker
    if config.mqtt_auth_enabled:
        mqtt_client.username_pw_set(config.mqtt_auth_user, config.mqtt_auth_pass)
    mqtt_client.connect(config.mqtt_host, config.mqtt_port, 60)

    # Thread for MQTT client
    mqtt_client.loop_start()

    # Thread for reading serial from ninja cape
    serial_thread = threading.Thread(target=serial_read_and_publish, args=(ser, mqtt_client))
    serial_thread.daemon = True
    serial_thread.start()

    try:
        # main thread
        while True:
            # writing to serial port if there is data available
            if len(outputData) > 0:
                # print "***data to OUTPUT:",mqtt_to_JSON_output(outputData[0])
                serial_message = mqtt_to_json_output(outputData.pop())
                print("Sending this on serial:\n{}".format(serial_message))
                ser.write(serial_message.encode())

            time.sleep(0.5)

    # handle deliberate closure gracefully
    except KeyboardInterrupt:
        print("Interrupt received")
        cleanup(ser, mqtt_client)


if __name__ == "__main__":
    main()
