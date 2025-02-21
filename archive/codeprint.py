# script for prototyping on the picow using circuitpython
# this script reads wifi credentials from the settings.toml file,
# connects to the wifi net, sets the hostname, and using an NTP server to set device time
# http requests (200) are used to trigger the reading of sensor data and responding with the data
from microcontroller import watchdog as wdt
from watchdog import WatchDogMode
import microcontroller
import board
import busio
import digitalio
import rtc
import time
import os
import sys
import supervisor
import socketpool
import wifi
import mdns
import adafruit_ntp
from adafruit_seesaw.seesaw import Seesaw
import json
from collections import OrderedDict

# Load settings from settings.toml and check for no credentials
WIFI_SSID = os.getenv("WIFI_SSID")
WIFI_PASSWORD = os.getenv("WIFI_PASS")
HOSTNAME = os.getenv("HOSTNAME")
HTTPPORT = 5244
MAX_RETRIES = 10
if not WIFI_SSID or not WIFI_PASSWORD:
    raise ValueError("Missing required settings in settings.toml")

# Globals for filtering and sensor
alpha = 0.1  # IIR filter coefficient
filtered_value = None
unitTest = False

# I2C Setup, used for sensor communications
i2c = busio.I2C(board.GP5, board.GP4)
seesaw = Seesaw(i2c, addr=0x36)
device_version = "SoilMoisture v0.1"

# On board LED setup
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

def flash_led(count):
    while count > 0:
        led.value = True
        time.sleep(0.1)
        led.value = False
        time.sleep(0.1)
        count -= 1
        
# Use a loop to attempt to connect and configure a wifi net
# we use the settings.toml for for story credentials
def connect_to_wifi():
    attempt = 0
    delay = 3
    while MAX_RETRIES is None or attempt < MAX_RETRIES:
        if unitTest:
            debug_print("Connecting to Wi-Fi...")

        try:
            wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
            wifi.radio.hostname = HOSTNAME
            debug_print(f"Connected to Wi-Fi @ {WIFI_SSID}")
            debug_print(f"IP Address: {wifi.radio.ipv4_address}")
            flash_led(3)
            return True  # Exit the function once connected
        except Exception as e:
            attempt += 1
            debug_print(f"Failed to connect to Wi-Fi @ {WIFI_SSID}: {e}")
            debug_print(f"Retrying ({attempt}/{MAX_RETRIES if MAX_RETRIES else '∞'}) in {delay} seconds...")
            time.sleep(delay)  # Wait before retrying

    print("Max retries reached. Could not connect to Wi-Fi.")
    return False  # Return False if connection is unsuccessful

# Configure listening socket and mDNS,
# this is where the HOSTNAME is set to allow for 'ping HOSTNAME.local' to work
def config_net():
    if unitTest:
        debug_print("Configuring network...")
    # Setup for HTTP handling
    try:
        pool = socketpool.SocketPool(wifi.radio)
        # Create a listening socket
        sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
        sock.bind(("0.0.0.0", HTTPPORT))
        sock.listen(1)
        sock.setblocking(False)  # Prevents blocking issues
        debug_print(f"Socket type set: {sock.type}")
        mdns_server = mdns.Server(wifi.radio)
        mdns_server.hostname = HOSTNAME
        mdns_server.advertise_service(
            service_type="_http",
            protocol="_tcp",
            port=HTTPPORT
        )
        debug_print(f"mDNS hostname set to {mdns_server.hostname}.local")
        return sock, mdns_server
    except Exception as e:
        print(f"Error with sock setup: {e}")
        return False

# Initialize NTP client to allow for time requests
def initialize_ntp():
    if unitTest:
        debug_print("Initializing NTP client...")
    try:
        pool = socketpool.SocketPool(wifi.radio)
        ntp = adafruit_ntp.NTP(pool, server="pool.ntp.org", tz_offset=-7)  # Adjust tz_offset for your timezone
        rtc.set_time_source(ntp)
        return ntp
    except Exception as e:
        debug_print(f"Failed to initialize NTP: {e}")
        return None

# HTTP Response
def http_response(raw_value, filtered_value):
    timestamp = get_timestamp()
    response_data = OrderedDict({
        "sm_timestamp": timestamp,
        "sm_raw_moisture": raw_value,
        "sm_filtered_moisture": filtered_value
    }) 
    return json.dumps(response_data)
    #return f"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{response_data}"

# Function to format the time in a customized format
def format_time(t):
    return f"{t.tm_mday:02d}/{t.tm_mon:02d}/{t.tm_year} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

# Function to get the current timestamp
def get_timestamp():
    now = time.localtime()
    return f"{now.tm_mday:02d}/{now.tm_mon:02d}/{now.tm_year} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

# Function to read soil moisture
def read_soil_moisture():
    try:
        flash_led(1)
        return seesaw.moisture_read()
    except Exception as e:
        debug_print(f"Failed to read soil moisture: {e}")
        return None

# IIR Filter to smooth the soil moisture data
def apply_iir_filter(raw_value):
    global filtered_value
    if filtered_value is None:
        filtered_value = raw_value
    else:
        filtered_value = alpha * raw_value + (1 - alpha) * filtered_value
    return filtered_value

def http_request_handler(mySocket, raw_value, filtered):
    # buffer for receiving request
    buffer = bytearray(1024)  # Create a buffer
    debugFlag = False
    try:
        # Simulate an HTTP request response loop
        # Use the socket library to handle HTTP requests
        # Example: Assume we receive a GET request at "/"
        # You would typically poll a specific endpoint on your microcontroller
        addr = None
        conn, addr = mySocket.accept()
        if not conn:
            time.sleep(0.1)
            return -1

        if debugFlag:
            print(f"Connection from {addr}")

    except OSError as e:
        if e.errno == 11:  # EAGAIN / No connection yet
            time.sleep(0.1)
            return -11
        else:
            if debugFlag:
                print("Error accepting connection:", e)
            return -1

    # Create a mutable buffer (bytearray) for receiving request data
    request_buffer = bytearray(1024)
    max_attempts = 5  # Retry up to 5 times
    attempt = 0

    while attempt < max_attempts:
        try:
            bytes_received = conn.recv_into(request_buffer, len(request_buffer))
            if bytes_received > 0:
                break  # Exit loop if data is received
        except OSError as e:
            if e.errno == 11:  # EAGAIN, try again
                attempt += 1
                time.sleep(0.1)  # Small delay before retrying
                continue
            else:
                print("Error receiving data:", e)
                conn.close()
                continue
    
    if bytes_received == 0:
        if debugFlag:
            print("No data received after retries. Closing connection.")
        conn.close()
        return -1

    # Convert received bytes to a string
    request_str = request_buffer[:bytes_received].decode("utf-8")
    if debugFlag:
        debug_print("Received request:", request_str)

    # Prepare HTTP response
    if "GET /version" in request_str:
        response_body = f"{device_version}"
        response = "HTTP/1.1 200 OK\r\n"
        response += "Content-Type: application/json\r\n"
        response += "Access-Control-Allow-Origin: *\r\n"  # ✅ Enables CORS
        response += "Connection: close\r\n"
        response += f"Content-Length: {len(response_body)}\r\n"
        response += "\r\n"
        response += response_body
    elif "GET /moisture" in request_str:
        response_body = http_response(raw_value, filtered)
        response = "HTTP/1.1 200 OK\r\n"
        response += "Content-Type: application/json\r\n"
        response += "Access-Control-Allow-Origin: *\r\n"  # ✅ Enables CORS
        response += "Connection: close\r\n"
        response += f"Content-Length: {len(response_body)}\r\n"
        response += "\r\n"
        response += response_body               
        flash_led(1)
    else:
        response_body = f"Unknown Request"
        response = "HTTP/1.1 200 OK\r\n"
        response += "Content-Type: application/json\r\n"
        response += "Access-Control-Allow-Origin: *\r\n"  # ✅ Enables CORS
        response += "Connection: close\r\n"
        response += f"Content-Length: {len(response_body)}\r\n"
        response += "\r\n"
        response += response_body

    if debugFlag:
        debug_print(f"Sending response:\n{response}")
    conn.send(response.encode("utf-8"))
    conn.close()

last_print_time = time.monotonic()

def debug_print(msg):
    global last_print_time
    if time.monotonic() - last_print_time > 10:  # Limit to once every 10 sec
        print(msg)
        last_print_time = time.monotonic()  # Store logs in memory (can print later)


# Main function is where the work is performed
def main():
    # Connect to Wi-Fi
    print(f"Soil Sensor Initializing...")
    # Redirects output to avoid crashing Thonny
    # Enable Watchdog Timer
    wdt.timeout = 8  # Set the watchdog timeout to 8 seconds (maximum supported)
    wdt.mode = WatchDogMode.RESET
    connect_to_wifi()

    # Configure socket and mDNS
    # it seems as though having a local (main()) DNS object
    # is important for making the device name available on the network
    mySocket, name_server = config_net()

    # Initialize NTP
    ntp = initialize_ntp()
    last_ntp_update = time.monotonic()
    ntp_interval = 60


    # Variables for non-blocking timing
    last_update = time.monotonic()
    update_interval = 10  # Time interval in seconds

    now = time.localtime()
    print(f"Initial UTC Time: {format_time(now)}")

    # Main loop
    raw_value = None
    filtered = None
    while True:
        try:
            # Refresh Watchdog Timer
            wdt.feed()

            # Check if the sensor update interval has elapsed
            current_time = time.monotonic()
            if current_time - last_update >= update_interval:
                # Read sensor data and apply filtering
                raw_value = read_soil_moisture()
                if raw_value is not None:
                    filtered = apply_iir_filter(raw_value)
                last_update = current_time
                if unitTest:
                    debug_print(f"{get_timestamp()} Raw: {raw_value} Filtered: {filtered}")

            # Check if the NTP update interval has elapsed
            if current_time - last_ntp_update >= ntp_interval:
                ntp = initialize_ntp()
                last_ntp_update = current_time

            # Handle incoming HTTP requests
            req_results = http_request_handler(mySocket, raw_value, filtered)

        except Exception as e:
            print(f"Error Unknown: {e}")
            microcontroller.reset()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            mySocket.close()
            supervisor.reload()  # software reset

# Run the main function
if __name__ == "__main__":
    main()


