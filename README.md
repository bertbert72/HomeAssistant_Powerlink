# HomeAssistant_Powerlink
Powerlink platform for use with Home Assistant and the MQTT alarm component.

Requires an MQTT broker to be installed and configured.  Sensors can then be created to monitor the alarm, as well as turning it on/off.  Example config:

```
alarm_control_panel:
  - platform: mqtt
    state_topic: home/alarm
    command_topic: home/alarm/set
    payload_disarm: Disarm
    payload_arm_home: ArmHome
    payload_arm_away: ArmAway
    name: House Alarm

sensor:
  - platform: powerlink2
    state_topic: home/alarm
    command_topic: home/alarm/set
    sensor_topic: home/alarm/sensor
    sensor_battery_topic: home/alarm/sensorbattery
    host: !secret alarm_host
    scan_interval: 1
    ignore_first_cmd: True
    alarm_user: !secret alarm_user
    alarm_password: !secret alarm_password

binary_sensor:
  - platform: mqtt
    state_topic: "home/alarm/sensor1"
    payload_on: Open
    payload_off: Ok
    device_class: door
    name: Front Door
  - platform: mqtt
    state_topic: "home/alarm/sensor2"
    payload_on: Open
    payload_off: Ok
    device_class: motion
    name: Downstairs
  - platform: mqtt
    state_topic: "home/alarm/sensor3"
    payload_on: Open
    payload_off: Ok
    device_class: motion
    name: Kitchen
  - platform: mqtt
    state_topic: "home/alarm/sensor4"
    payload_on: Open
    payload_off: Ok
    device_class: door
    name: Patio Doors
  - platform: mqtt
    state_topic: "home/alarm/sensor5"
    payload_on: Open
    payload_off: Ok
    device_class: motion
    name: Upstairs
  - platform: mqtt
    state_topic: "home/alarm/sensor6"
    payload_on: Open
    payload_off: Ok
    device_class: door
    name: Back Door
  - platform: mqtt
    state_topic: "home/alarm/sensorbattery1"
    payload_on: Low
    payload_off: Ok
    device_class: battery
    name: Front Door Battery
  - platform: mqtt
    state_topic: "home/alarm/sensorbattery2"
    payload_on: Low
    payload_off: Ok
    device_class: battery
    name: Downstairs Battery
  - platform: mqtt
    state_topic: "home/alarm/sensorbattery3"
    payload_on: Low
    payload_off: Ok
    device_class: battery
    name: Kitchen Battery
  - platform: mqtt
    state_topic: "home/alarm/sensorbattery4"
    payload_on: Low
    payload_off: Ok
    device_class: battery
    name: Patio Doors Battery
  - platform: mqtt
    state_topic: "home/alarm/sensorbattery5"
    payload_on: Low
    payload_off: Ok
    device_class: battery
    name: Upstairs Battery
  - platform: mqtt
    state_topic: "home/alarm/sensorbattery6"
    payload_on: Low
    payload_off: Ok
    device_class: battery
    name: Back Door Battery
```
