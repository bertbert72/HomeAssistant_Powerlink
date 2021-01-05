"""
Support for the Visonic Powerlink2

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/powerlink2
"""
import logging
import requests
import uuid
import xml.etree.ElementTree as ET
import time

import voluptuous as vol
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.components import mqtt
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import (CONF_HOST)
import homeassistant.helpers.config_validation as cv

VERSION = '0.1.0'

DATA_POWERLINK2 = 'powerlink2'

STATE_OK = "Ok"
STATE_OPEN = "Open"
STATE_ALARM = "Alarm"
STATE_LOW_BATTERY = "Low Battery"

BATTERY_UNDETERMINED = "Unknown"
BATTERY_OK = "Ok"
BATTERY_LOW = "Low"

ALARM_CMD_LOGIN = "/web/ajax/login.login.ajax.php"
ALARM_CMD_LOGOUT = "/web/login.php?act=logout"
ALARM_CMD_ARMING = "/web/ajax/security.main.status.ajax.php"
ALARM_CMD_STATUS = "/web/ajax/alarm.chkstatus.ajax.php"
ALARM_CMD_LOGS = "/web/ajax/setup.log.ajax.php"
ALARM_CMD_AUTO_LOGOUT = "/web/ajax/system.autologout.ajax.php"
ALARM_CMD_SEARCH = "/web/ajax/home.search.ajax.php"
ALARM_LOGIN_PAGE = "/web/login.php"
ALARM_PANEL_PAGE = "/web/panel.php"
ALARM_FRAME_PAGE = "/web/frameSetup_ViewLog.php"

CONF_STATE_TOPIC = "state_topic"
CONF_COMMAND_TOPIC = "command_topic"
CONF_SENSOR_TOPIC = "sensor_topic"
CONF_SENSOR_BATTERY_TOPIC = "sensor_battery_topic"
CONF_IGNORE_FIRST_CMD = "ignore_first_cmd"
CONF_ALARM_USER = "alarm_user"
CONF_ALARM_PASSWORD = "alarm_password"

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.All(
    PLATFORM_SCHEMA.extend({
        vol.Optional(CONF_STATE_TOPIC, default="home/alarm"): cv.string,
        vol.Optional(CONF_COMMAND_TOPIC, default="home/alarm/set"): cv.string,
        vol.Optional(CONF_SENSOR_TOPIC, default="home/alarm/sensor"): cv.string,
        vol.Optional(CONF_SENSOR_BATTERY_TOPIC, default="home/alarm/sensorbattery"): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_ALARM_USER): cv.string,
        vol.Required(CONF_ALARM_PASSWORD): cv.string,
        vol.Optional(CONF_IGNORE_FIRST_CMD, default=True): cv.boolean,
    }))


async def async_setup(hass, config, async_add_entities, discovery_info=None):

    sensors = []
    sensors.append(Powerlink2(config))
    async_add_entities(sensors)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):

    sensors = []
    sensors.append(Powerlink2(config))
    async_add_entities(sensors)


class Powerlink2(Entity):

    def __init__(self, config):
        self._name = 'powerlink2'
        self._plink_ip = config.get(CONF_HOST)
        self._plink_usr = config.get(CONF_ALARM_USER)
        self._plink_pwd = config.get(CONF_ALARM_PASSWORD)
        self._plink_token = uuid.uuid4().hex
        self._alarm_triggered = None
        self._alarm_status = None
        self._alarm_status_response = None
        self._curr_index = 0
        self._status_changed = True
        self._status_last_sent = None
        self._just_connected = None
        self._ignore_first_cmd = True
        self._client = None
        self._state = 'Unconnected'
        self._command_topic = config.get(CONF_COMMAND_TOPIC)
        self._state_topic = config.get(CONF_STATE_TOPIC)
        self._sensor_topic = config.get(CONF_SENSOR_TOPIC)
        self._battery_topic = config.get(CONF_SENSOR_BATTERY_TOPIC)
        self._qos = 0

        self.connect()

    @property
    def state(self):
        return self._state

    @property
    def name(self):
        return self._name

    def connect(self):
        _LOGGER.info("Powerlink2: initialising connection to [%s]", self._plink_ip)
        _LOGGER.info("Powerlink2: login check is " + str(self.do_logincheck()))

    def getheaders(self):
        headers = {
            "Content-type": "application/x-www-form-urlencoded",
            "Accept-language": "en-GB,en-US;q=0.8,en;q=0.6",
            "Cookie": "PowerLink=" + self._plink_token
        }
        return headers

    def do_logincheck(self):
        # Attempt to login using current session token
        url = 'http://' + self._plink_ip

        cmd_auto_logout = url + ALARM_CMD_AUTO_LOGOUT
        cmd_login = url + ALARM_CMD_LOGIN

        payload = {"task": "get_auto_logout_params"}
        r = requests.post(cmd_auto_logout, data=payload, headers=self.getheaders())
        _LOGGER.debug("Powerlink connection check: " + str(r.content))
        if '[RELOGIN]' in str(r.content) or not r.content:
            _LOGGER.debug("Powerlink login required")
            self._plink_token = uuid.uuid4().hex
            payload = {"user": self._plink_usr, "pass": self._plink_pwd}
            r = requests.post(cmd_login, data=payload, headers=self.getheaders())
            _LOGGER.debug(r.content)
            if not r.content:
                self._state = 'Unconnected'
                return False
            else:
                self._state = 'Connected'
        else:
            _LOGGER.debug("Using existing Powerlink connection")
        return True

    def do_getstatus(self):
        # Get the current alarm status and notify HA if it changed
        url = 'http://' + self._plink_ip

        cmd_status = url + ALARM_CMD_STATUS

        payload = {"curindex": self._curr_index, "sesusername": self._plink_usr, "sesusermanager": "1"}
        r = requests.post(cmd_status, data=payload, headers=self.getheaders())
        try:
            if '[NOCNG]' in str(r.content):
                self._status_changed = False
            elif '[RELOGIN]' in str(r.content):
                _LOGGER.debug("Login expired")
                _LOGGER.debug("New login result: " + str(self.do_logincheck()))
            else:
                root = ET.fromstring(r.content)
                t = root[0].text
                self._alarm_status_response = ET.tostring(root)
                if self._curr_index != t:
                    self._status_changed = True
                    self._curr_index = t
                else:
                    self._status_changed = False
                _LOGGER.debug(self._alarm_status_response)
                curr_status = root.find('*/system/status').text
                _LOGGER.debug("Status from alarm: " + curr_status)
                if curr_status == "Ready" or curr_status == "Not Ready":
                    new_status = 'disarmed'
                elif curr_status == "Exit Delay":
                    new_status = 'pending'
                elif curr_status == "HOME":
                    new_status = 'armed_home'
                elif curr_status == "AWAY":
                    new_status = 'armed_away'
                elif curr_status == "Entry Delay":
                    new_status = 'pending'
                # Check this one
                elif curr_status == "ALARM":
                    new_status = 'triggered'
                else:
                    new_status = 'unknown'
                    _LOGGER.info("Unknown status: " + curr_status)
                if self._alarm_triggered:
                    new_status = 'triggered'
                if self._alarm_status != new_status:
                    self._state = new_status
                    self._alarm_status = new_status
                    mqtt.async_publish(self.hass, self._state_topic, self._alarm_status, self._qos, True)
                    _LOGGER.info("Alarm status: " + self._alarm_status)
                    self._status_last_sent = time.time()
            _LOGGER.debug("Index: " + self._curr_index)
        except:
            _LOGGER.error("Unable to parse response: %s", str(r.content))

    def do_sensor_check(self):
        # Get the current alarm sensor status and send to HA

        root = ET.fromstring(self._alarm_status_response)
        sensors = root.findall("./detectors//detector")

        self._alarm_triggered = False
        for child in sensors:
            zone = "0"
            status = "None"
            is_alarm = "None"
            battery = BATTERY_UNDETERMINED
            for gchild in child:
                if gchild.tag == 'zone':
                    zone = str(gchild.text)
                elif gchild.tag == 'status':
                    status = str(gchild.text)
                elif gchild.tag == 'isalarm':
                    is_alarm = str(gchild.text)
            if status == "None":
                status = STATE_OK
                battery = BATTERY_OK
            else:
                _LOGGER.debug("Sensor " + zone + " = " + status + ", alarm = " + is_alarm)
                # if status != STATE_OPEN:
                _LOGGER.debug("DUMP:" + str(self._alarm_status_response))
            if status == STATE_LOW_BATTERY:
                battery = BATTERY_LOW
            if is_alarm == "yes" or status == STATE_ALARM:
                self._alarm_triggered = True
                # Workaround for boolean sensor
                status = STATE_OPEN
            if battery != BATTERY_UNDETERMINED:
                mqtt.async_publish(self.hass, self._battery_topic + zone, battery, self._qos, True)
                _LOGGER.debug("Setting battery to " + str(battery) + " for topic " + str(self._battery_topic + zone))
            if battery != BATTERY_LOW:
                mqtt.async_publish(self.hass, self._sensor_topic + zone, status, self._qos, True)
                _LOGGER.debug("Setting state to " + str(status) + " for topic " + str(self._sensor_topic + zone))

    def do_setstatus(self, target_status):
        # Set the alarm status
        url = 'http://' + self._plink_ip
        cmd_arming = url+'/web/ajax/security.main.status.ajax.php'

        payload = {"set": target_status}
        r = requests.post(cmd_arming, data=payload, headers=self.getheaders())

    def do_logout(self):
        # Logout from the Powerlink server
        url = 'http://' + self._plink_ip
        cmd_logout = url+'/web/login.php?act=logout'
        payload = {}
        r = requests.post(cmd_logout, data=payload, headers=self.getheaders())

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""
        async_track_state_change_event(
            self.hass, [self.entity_id], self._async_state_changed_listener
        )
        self._just_connected = True

        async def message_received(msg):
            """Run when new MQTT message has been received."""
            if not self._just_connected or not self._ignore_first_cmd:
                _LOGGER.info("Received command: %s", msg.payload)
                self.do_setstatus(msg.payload)
            else:
                _LOGGER.info("Ignoring command: %s", msg.payload)
                self._just_connected = False
            return

        await mqtt.async_subscribe(
            self.hass, self._command_topic, message_received, self._qos
        )

    async def _async_state_changed_listener(self, event):
        """Publish state change to MQTT."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return
        mqtt.async_publish(
            self.hass, self._state_topic, new_state.state, self._qos, True
        )

    def update(self):
        """Retrieve latest state."""
        self.do_getstatus()
        if self._status_changed:
            self.do_sensor_check()
        else:
            _LOGGER.debug("No status change")
