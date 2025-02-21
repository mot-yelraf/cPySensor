# script for prototyping on the picow using circuitpython
# this script reads wifi credentials from the settings.toml file,
# connects to the wifi net, sets the hostname, and using an NTP server to set device time
import os
from microcontroller import watchdog as w
from watchdog import WatchDogMode
import board
import busio
import digitalio
import socketpool
import wifi
import mdns
import time
import rtc
import adafruit_requests
import adafruit_ntp
from adafruit_seesaw.seesaw import Seesaw

import json

# Load settings from settings.toml and check for no credentials
WIFI_SSID = os.getenv("WIFI_SSID")
WIFI_PASSWORD = os.getenv("WIFI_PASS")
HOSTNAME = os.getenv("HOSTNAME")
HTTPPORT = 5244
if not WIFI_SSID or not WIFI_PASSWORD:
    raise ValueError("Missing required settings in settings.toml")

# Globals for filtering and sensor
alpha = 0.1  # IIR filter coefficient
filtered_value = None
unitTest = False

# I2C Setup
i2c = busio.I2C(board.GP5, board.GP4)
seesaw = Seesaw(i2c, addr=0x36)

# On board LED setup
led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT

# Use wifi library to connect to Wi-Fi
def connect_to_wifi():
    if unitTest == True:
        print("Connecting to Wi-Fi...")
    try:
        wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
        wifi.radio.hostname = HOSTNAME
        print(f"Connected to Wi-Fi @ {WIFI_SSID}")
        print(f"IP Address: {wifi.radio.ipv4_address}")
    except Exception as e:
        print(f"Failed to connect to Wi-Fi @ {WIFI_SSID}: {e}")
        raise

# Configure mDNS, this is where the HOSTNAME is set to allow for 'ping HOSTNAME.local' to work
def configure_mdns():
    if unitTest == True:
        print("Configuring mDNS...")
    try:
        pool = socketpool.SocketPool(wifi.radio)
        mdns_server = mdns.Server(wifi.radio)
        mdns_server.hostname = HOSTNAME
        mdns_server.advertise_service(
            service_type="_http",
            protocol="_tcp",
            port=HTTPPORT
        )
        print(f"mDNS hostname set to {mdns_server.hostname}.local")
    except Exception as e:
        print(f"Failed to configure mDNS: {e}")
        raise

# Initialize NTP client to allow for time requests
def initialize_ntp():
    if unitTest == True:
        print("Initializing NTP client...")
    try:
        pool = socketpool.SocketPool(wifi.radio)
        ntp = adafruit_ntp.NTP(pool, server="pool.ntp.org", tz_offset=0)  # Adjust tz_offset for your timezone
        rtc.set_time_source(ntp)
        return ntp
    except Exception as e:
        print(f"Failed to initialize NTP: {e}")
        return None

# Start HTTP server using Adafruit Requests
def start_http_server():
    if unitTest:
        print("Starting HTTP server using adafruit_requests...")
    try:
        pool = socketpool.SocketPool(wifi.radio)
        requests = adafruit_requests.Session(pool, ssl_context=None)

        try:
            # Mock server functionality: Look for GET requests
            raw_value = read_soil_moisture()
            filtered_value = apply_iir_filter(raw_value) if raw_value else None

            # Simulate responding to an HTTP GET request
            request = requests.get(f"http://0.0.0.0:{HTTPPORT}/", timeout=1)
            print(f"Request received: {request.text}")

            # Create HTTP Response
            response_data = http_response(raw_value, filtered_value)
            print(f"Sending response: {response_data}")
            request.send(response_data)

        except Exception as e:
            print(f"Error processing HTTP request: {e}")
    except Exception as e:
        print(f"Failed to start HTTP server: {e}")

    
# HTTP Response
def http_response(raw_value, filtered_value):
    timestamp = get_timestamp()
    response_data = {
        "sm_timestamp": timestamp,
        "sm_raw_moisture": raw_value,
        "sm_filtered_moisture": filtered_value
    }
    return "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + json.dumps(response_data)

# Function to format the time in a customized format
def format_time(t):
    return f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

# Function to get the current timestamp
def get_timestamp():
    now = time.localtime()
    return f"{now.tm_year}-{now.tm_mon:02d}-{now.tm_mday:02d} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

# Function to read soil moisture
def read_soil_moisture():
    try:
        return seesaw.moisture_read()
    except Exception as e:
        print(f"Failed to read soil moisture: {e}")
        return None

# IIR Filter
def apply_iir_filter(raw_value):
    global filtered_value
    if filtered_value is None:
        filtered_value = raw_value
    else:
        filtered_value = alpha * raw_value + (1 - alpha) * filtered_value
    return filtered_value

# Main function
def main():
    # Connect to Wi-Fi
    print(f"Soil Sensor Initializing...")
    connect_to_wifi()

    # Configure mDNS
    configure_mdns()

    # Initialize NTP
    ntp = initialize_ntp()
    last_ntp_update = time.monotonic()
    ntp_interval = 60

    # Set up Adafruit Requests for HTTP handling
    print("Starting HTTP server...")
    pool = socketpool.SocketPool(wifi.radio)
    requests = adafruit_requests.Session(pool, ssl_context=None)
    # Create a listening socket
    sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    sock.bind((HOSTNAME, HOSTPORT))
    sock.listen(1)

    # Enable Watchdog Timer
    w.timeout = 8  # Set the watchdog timeout to 8 seconds (maximum supported)
    w.mode = WatchDogMode.RESET

    # Variables for non-blocking timing
    last_update = time.monotonic()
    update_interval = 10  # Time interval in seconds

    now = time.localtime()
    print(f"Initial UTC Time: {format_time(now)}")

    # Main loop
    while True:
        try:
            # Refresh Watchdog Timer
            w.feed()

            # Check if the sensor update interval has elapsed
            current_time = time.monotonic()
            if current_time - last_update >= update_interval:
                # Read sensor data and apply filtering
                raw_value = read_soil_moisture()
                if raw_value is not None:
                    filtered = apply_iir_filter(raw_value)
                last_update = current_time
                if unitTest:
                    print(f"{get_timestamp()} Raw: {raw_value} Filtered: {filtered}")

            # Check if the NTP update interval has elapsed
            if current_time - last_ntp_update >= ntp_interval:
                ntp = initialize_ntp()
                last_ntp_update = current_time

            # Handle incoming HTTP requests
            try:
                # Simulate an HTTP request response loop
                # Use the Adafruit Requests library to handle HTTP requests
                # Example: Assume we receive a GET request at "/"
                # You would typically poll a specific endpoint on your microcontroller
                '''
                request = requests.get(f"http://0.0.0.0:{HTTPPORT}/", timeout=5)

                # Create and send a response
                if "GET /" in request.text:
                    response = http_response(raw_value, filtered)
                    print(f"HTTP Response: {response}")
                    # Respond back to the HTTP client (if applicable)
                    request.send(response)
                '''
                conn, addr = sock.accept()
                print(f"Connection from {addr}")

                buffer = bytearray(1024)  # Create a buffer
                bytes_received = conn.recv_into(buffer)  # Read data properly
                request = buffer[:bytes_received].decode()  # Decode to string
                print(f"Received request: {request}")

                if "GET /moisture" in request:
                    moisture = sensor.moisture_read()
                    response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n{moisture}"
                    conn.send(response.encode())
                    print(f"Sent moisture data: {moisture}")

                conn.close()  # Close the connection properly
                
                
            except Exception as e:
                pass
                #print(f"Error processing HTTP request: {e}")

        except Exception as e:
            print(f"An error occurred: {e}")
            w.feed()


# Run the main function
if __name__ == "__main__":
    main()


