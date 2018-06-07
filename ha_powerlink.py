import uuid
import requests
import xml.etree.ElementTree as ET
import paho.mqtt.client as mqtt
import time
import ConfigParser
import io
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

configfile_name = 'ha_powerlink.ini'
logfile_name = 'ha_powerlink.log'
use_logfile = False
debug_level = 1   # 0 = error, 1 = info, 2 = debug, 3 = trace

if use_logfile == True:
    log_handler = RotatingFileHandler(logfile_name, mode='a', maxBytes=5*1024*1024, backupCount=2, encoding=None, delay=False)
else:
    log_handler = logging.StreamHandler()
log_formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
log_handler.setFormatter(log_formatter)
log_handler.setLevel(logging.DEBUG)
logger = logging.getLogger('root')
logger.setLevel(logging.DEBUG)
logger.addHandler(log_handler)

def errorprint(string):
    global debug_level
    if debug_level >= 0: logger.error(string)

def infoprint(string):
    global debug_level
    if debug_level >= 1: logger.info(string)

def debugprint(string):
    global debug_level
    if debug_level >= 2: logger.debug(string)

def traceprint(string):
    global debug_level
    if debug_level >= 3: logger.trace(string)

# Read config file
# Don't change the defaults - use the .ini file to override
defaults = {
    "plink_usr": "Admin",           # User login for Powerlink web interface
    "plink_pwd": "Admin123",        # Password for Powerlink web interface
    "plink_ip": "192.168.0.200",    # IP address of Powerlink
    "plink_refresh": "1",           # How often to recheck the alarm status (seconds)
    "ha_interval": "10",            # How often to send the alarm status to HA (seconds)
    "ha_alarm_state_topic": "home/alarm",         # HA alarm state topic
    "ha_alarm_command_topic": "home/alarm/set",   # HA alarm command topic
    "ha_sensor_state_topic": "home/alarm/sensor", # HA sensor state topic
    "ignore_first_cmd": "True",     # Ignore the first command when connecting to MQTT
                                    #   false means that the current HA status will take effect
    "mqtt_port": "1883",            # MQTT port
    "mqtt_host": "127.0.0.1",       # MQTT address
    "mqtt_timeout": "60",           # MQTT timeout
    "mqtt_usr": "",                 # MQTT username (optional)
    "mqtt_pwd": "",                 # MQTT password (optional)
    "plink_token": uuid.uuid4().hex
}
if os.path.isfile(configfile_name):
    with open(configfile_name) as f:
        my_config = f.read()
    config = ConfigParser.RawConfigParser(defaults)
    config.readfp(io.BytesIO(my_config))
    plink_usr = config.get('Settings', 'plink_usr')
    plink_pwd = config.get('Settings', 'plink_pwd')
    plink_ip = config.get('Settings', 'plink_ip')
    plink_refresh = config.getint('Settings', 'plink_refresh')
    ha_interval = config.getint('Settings', 'ha_interval')
    ha_alarm_state_topic = config.get('Settings', 'ha_alarm_state_topic')
    ha_alarm_command_topic = config.get('Settings', 'ha_alarm_command_topic')
    ha_sensor_state_topic = config.get('Settings', 'ha_sensor_state_topic')
    ignore_first_cmd = config.getboolean('Settings', 'ignore_first_cmd')
    mqtt_host = config.get('Settings', 'mqtt_host')
    mqtt_port = config.getint('Settings', 'mqtt_port')
    mqtt_timeout = config.getint('Settings', 'mqtt_timeout')
    mqtt_usr = config.get('Settings', 'mqtt_usr')
    mqtt_pwd = config.get('Settings', 'mqtt_pwd')
    plink_token = config.get('Settings', 'plink_token')
    config.set('Settings', 'plink_token', plink_token)
    with open(configfile_name, 'wb') as configfile:
        config.write(configfile)
else:
    errorprint("Configuration file missing.")
    sys.exit(1)

# Powerlink Commands
url = 'http://'+plink_ip
cmd_login = url+'/web/ajax/login.login.ajax.php'
cmd_logout = url+'/web/login.php?act=logout'
cmd_arming = url+'/web/ajax/security.main.status.ajax.php'
cmd_status = url+'/web/ajax/alarm.chkstatus.ajax.php'
cmd_logs = url+'/web/ajax/setup.log.ajax.php'
cmd_autologout = url+'/web/ajax/system.autologout.ajax.php'
cmd_search = url+'/web/ajax/home.search.ajax.php'
loginpage = url+'/web/login.php'
panelpage = url+'/web/panel.php'
framepage = url+'/web/frameSetup_ViewLog.php'

STATE_OK = "Ok"
STATE_OPEN = "Open"
STATE_ALARM = "Alarm"
STATE_LOWBAT = "Low Battery"

alarm_status_response = ''
alarm_status = 'unknown'
alarm_triggered = False
curr_index = 0
status_last_sent = time.time()

def getheaders():
    global plink_token
    headers = {
        "Content-type": "application/x-www-form-urlencoded",
        "Accept-language": "en-GB,en-US;q=0.8,en;q=0.6",
        "Cookie": "PowerLink="+plink_token
    }
    return headers

def do_logincheck():
    # Attempt to login using current session token
    global plink_token, cmd_autologout, cmd_login, headers, config, configfile_name
    payload = {"task": "get_auto_logout_params"}
    r = requests.post(cmd_autologout, data=payload, headers=getheaders())
    traceprint("Powerlink connection check: " + r.content)
    if ('[RELOGIN]' in r.content or not r.content):
        debugprint("Powerlink login required")
        plink_token = uuid.uuid4().hex
        config.set('Settings', 'plink_token', plink_token)
        with open(configfile_name, 'wb') as configfile:
            config.write(configfile)
        payload = {"user": plink_usr, "pass": plink_pwd}
        r = requests.post(cmd_login, data=payload, headers=getheaders())
        debugprint(r.content)
        if r.content == False:
            return False
    else:
        debugprint("Using existing Powerlink connection")
    return True

def do_getstatus():
    # Get the current alarm status and notify HA if it changed
    global alarm_status, alarm_status_response, curr_index, ET
    payload = {"curindex": curr_index, "sesusername": plink_usr, "sesusermanager": "1"}
    r = requests.post(cmd_status, data=payload, headers=getheaders())
    root = ET.fromstring(r.content)
    t = root[0].text
    if '[NOCNG]' in t:
        traceprint("No change in status")
    elif '[RELOGIN]' in t:
        debugprint("Login expired")
        debugprint("Login result: " + str(do_logincheck()))
    else:
        alarm_status_response = ET.tostring(root)
        curr_index = t
        traceprint(alarm_status_response)
        curr_status = root.find('*/system/status').text
        debugprint("Status from alarm: " + curr_status)
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
            infoprint("Unknown status: " + curr_status)
        if alarm_triggered == True:
            new_status = 'triggered'
        if alarm_status != new_status:
            alarm_status = new_status
            client.publish(ha_alarm_state_topic, alarm_status, qos=0, retain=True)
            infoprint("Alarm status: " + alarm_status)
            status_last_sent = time.time()
    traceprint("Index: " + curr_index)

def do_sensorcheck():
    # Get the current alarm sensor status and send to HA
    global alarm_triggered, alarm_status_response
    root = ET.fromstring(alarm_status_response)
    sensors = root.findall("./detectors//detector")

    alarm_triggered = False
    for child in sensors:
        zone = "0"
        status = "None"
        isalarm = "None"
        for gchild in child:
            if gchild.tag == 'zone':
                zone = str(gchild.text)
            elif gchild.tag == 'status':
                status = str(gchild.text)
            elif gchild.tag == 'isalarm':
                isalarm = str(gchild.text)
        if status == "None":
            status = STATE_OK
        elif status == STATE_LOWBAT:
            status = STATE_OPEN
        else:
            debugprint("Sensor " + zone + " = " + status + ", alarm = " + isalarm)
            # if status != STATE_OPEN:
            debugprint("DUMP:" + alarm_status_response)
        if (isalarm == "yes" or status == STATE_ALARM):
            alarm_triggered = True
            # Workaround for boolean sensor
            status == STATE_OPEN
        client.publish(ha_sensor_state_topic+zone, status, qos=0, retain=True)

def do_setstatus(target_status):
    # Set the alarm status
    global cmd_arming
    payload = {"set": target_status}
    r = requests.post(cmd_arming, data=payload, headers=getheaders())

def do_logout():
    # Logout from the Powerlink server
    global cmd_logout
    payload = {}
    r = requests.post(cmd_logout, data=payload, headers=getheaders())

def on_connect(client, userdata, flags, rc):
    global alarm_status, just_connected
    debugprint("Connected with result code "+str(rc))
    client.subscribe(ha_alarm_command_topic)
    just_connected = True

def on_message(client, userdata, msg):
    global just_connected, ignore_first_cmd
    if just_connected == False or ignore_first_cmd == False:
        infoprint("Received command: " + msg.payload)
        do_setstatus(msg.payload)
    else:
        infoprint("Ignoring command: " + msg.payload)
        just_connected = False

# Connect to Powerlink
if do_logincheck() == True:
    infoprint("Powerlink connection successful")
else:
    errorprint("Powerlink login failed")
    sys.exit(1)

# Connect to MQTT
client = mqtt.Client()
if mqtt_usr != "":
    client.username_pw_set(mqtt_usr, password=mqtt_pwd)
client.on_connect = on_connect
client.on_message = on_message
client.connect(mqtt_host,mqtt_port,mqtt_timeout)

client.loop_start()
while True:
    do_getstatus()
    do_sensorcheck()
    if (time.time() - status_last_sent) > ha_interval:
        debugprint("Refresh HomeAssistant: " + alarm_status)
        client.publish(ha_alarm_state_topic, alarm_status, qos=0, retain=True)
        status_last_sent = time.time()
    time.sleep(plink_refresh)
