# script for prototyping on the picow using circuitpython
# this script reads wifi credentials from the settings.toml file,
# connects to the wifi net, sets the hostname, and using an NTP server to set device time
# http requests (200) are used to trigger the reading of sensor data and responding with the data
from microcontroller import watchdog as wdt
from watchdog import WatchDogMode
import microcontroller
import board
import rtc
import time
import os
import sys
import adafruit_logging as logging
import cPyNetConf
import smSensor
import json
from collections import OrderedDict

# Function to format the time in a customized format
def format_time(t):
    return f"{{t.tm_mon:02d}/t.tm_mday:02d}/{t.tm_year} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

# Function to get the current timestamp
def get_timestamp():
    now = time.localtime()
    return f"{{now.tm_mon:02d}/now.tm_mday:02d}/{now.tm_year} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

last_print_time = time.monotonic()

def debug_print(msg):
    global last_print_time
    return
    if time.monotonic() - last_print_time > 10:  # Limit to once every 10 sec
        print(msg)
        last_print_time = time.monotonic()  # Store logs in memory (can print later)


# Globals for filtering and sensor
UNITTEST = True

# Main function is where the work is performed
def main():
    # Connect to Wi-Fi
    print(f"Soil Sensor Initializing...")
    # Redirects output to avoid crashing Thonny
    # Enable Watchdog Timer
    wdt.timeout = 8  # Set the watchdog timeout to 8 seconds (maximum supported)
    wdt.mode = WatchDogMode.RESET
    
    logger = logging.getLogger('debug')
    
    # Load settings from settings.toml and check for no credentials
    WIFI_SSID = os.getenv("WIFI_SSID")
    WIFI_PASSWORD = os.getenv("WIFI_PASS")
    HOSTNAME = os.getenv("HOSTNAME")
    BCAST_IP = "10.0.0.255"
    NETPORT = 5244
    MAX_RETRIES = 10
    #instantiate cPyNetConf class as netConf
    netConf = cPyNetConf.cPyNetConfig(WIFI_SSID, WIFI_PASSWORD, NETPORT, BCAST_IP)

    # instatiate smSensor class as sensor
    # Initialize the soil moisture sensor on the appropriate analog pin
    moisture_pin = board.A0
    threshold_pin = board.GP1
    sensor = smSensor.SoilMoistureSensor(moisture_pin, threshold_pin)
    
    #setup some timers
    last_ntp_update = time.monotonic()
    ntp_interval = 60
    last_update = time.monotonic()
    update_interval = 10  # Time interval in seconds
    now = time.localtime()
    #debug_print(f"Initial UTC Time: {format_time(now)}")


    # configure wifi and network 
    netConf.connect_to_wifi()
    mySock, myServer = netConf.config_net()
    if not mySock:
        print("Network setup failed. Exiting...")
        exit()
    else:
        print(f"sock setup complete: {mySock}, {myServer}")
    # initial ntp time source and set rtc
    netConf.init_ntp()
    
    # initialize variables
    announcement = b"ITAOT"
    announce_recv = False

    print(f"Broadcasting {announcement.decode()} to {BCAST_IP}:{NETPORT} every 5 seconds")
    buffer = bytearray(1024)  # Create a buffer for incoming data
    while True:
        if not announce_recv:
            try:
                mySock.sendto(announcement, (BCAST_IP, NETPORT))
                logger.debug(f"{announcement.decode()} broadcasted")
            except OSError as e:
                if e.errno == 11:  # EAGAIN
                    logger.debug("Send buffer full, retrying...")
                    time.sleep(0.1)  # Small delay before retrying
                else:
                    raise  # Raise other unexpected errors
            
        try:
            logger.info(f"checking for response:")
            data, addr = mySock.recvfrom_into(buffer)  # 1024 is the buffer size
            received_msg = data.decode()
            annouce_recv = True

            #debug_print(f"Received response from {addr}: {received_msg}")

            #debug_print(f"{received_msg} received")
            if "ACK" in received_msg:
                mySock.sendto(f"{get_timestamp()} WAY?".encode(), addr)
            elif "WAY" in received_msg:
                mySock.sendto(f"{get_timestamp()} IAM: {netConf.HOSTNAME} {netConf.device_version}, {netConf.device_capabilities}".encode(), addr)
            elif "/current_data" in received_msg:
                # Check if the sensor update interval has elapsed
                current_time = time.monotonic()
                if current_time - last_update >= update_interval:
                    # Read sensor data and apply filtering
                    #raw_value = read_seesaw_soil_moisture()
                    timestamp = get_timestamp()
                    voltage, moisture = sensor.read_moisture_percentage()
                    threshold_state = sensor.read_threshold()
                    stable = sensor.voltage_stable(voltage)
                    stability_marker = '*' if stable else '+'
                    formatted_output = f"[{timestamp}] Voltage: {voltage:.3f}V, Moisture: {moisture:.1f}%, Threshold: {threshold_state} {stability_marker}"
                    mySock.sendto(f"{formatted_output}".encode(), addr)
                    if UNITTEST:
                     logger.info(formatted_output)

                    last_update = current_time
            continue
        except KeyboardInterrupt:
            #debug_print("\nShutting down server...")
            mySock.close()
        except Exception as e:
            logger.info(f"No response yet: {e}")
       
        time.sleep(5)

# Run the main function
if __name__ == "__main__":
    main()


