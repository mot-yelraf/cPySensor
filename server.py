### Pico W (Server) - CircuitPython ###
import os
import mdns
import wifi
import socketpool
import time
import adafruit_requests
import adafruit_ntp
import board
import digitalio

# Load settings from settings.toml and check for no credentials
WIFI_SSID = os.getenv("WIFI_SSID")
WIFI_PASSWORD = os.getenv("WIFI_PASS")
HOSTNAME = os.getenv("HOSTNAME")
HTTPPORT = 5244
MAX_RETRIES = 10
BROADCAST_IP = "10.0.0.255"
if not WIFI_SSID or not WIFI_PASSWORD:
    raise ValueError("Missing required settings in settings.toml")

# Globals for filtering and sensor
unitTest = True

# I2C Setup, used for sensor communications
device_version = "SMS v0.1"
device_capabilities = "soil moisture"

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
            print("Connecting to Wi-Fi...")

        try:
            wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
            wifi.radio.hostname = HOSTNAME
            #debug_print(f"Connected to Wi-Fi @ {WIFI_SSID}")
            print(f"WIFI IP Address: {wifi.radio.ipv4_address}")
            flash_led(3)
            return True  # Exit the function once connected
        except Exception as e:
            attempt += 1
            #debug_print(f"Failed to connect to Wi-Fi @ {WIFI_SSID}: {e}")
            #debug_print(f"Retrying ({attempt}/{MAX_RETRIES if MAX_RETRIES else '∞'}) in {delay} seconds...")
            time.sleep(delay)  # Wait before retrying
    if unitTest:
        print("Max retries reached. Could not connect to Wi-Fi.")
    return False  # Return False if connection is unsuccessful

# Configure listening socket and mDNS,
# this is where the HOSTNAME is set to allow for 'ping HOSTNAME.local' to work
def config_net():
    if unitTest:
        print("Configuring network...")
    # Setup for HTTP handling
    try:
        pool = socketpool.SocketPool(wifi.radio)
        # Create a listening socket
        sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)     
        for _ in range(5):  # Try 5 times with delays
            try:
                sock.bind(("0.0.0.0", HTTPPORT))
                print("sock bind success...")
                break  # If successful, exit retry loop
            except OSError as e:
                if e.errno == 112:  # EADDRINUSE
                    print("Port still in use, retrying...")
                    time.sleep(1)
                else:
                    raise  # Unexpected error
        #sock.listen(1)
        #sock.setblocking(False)  # Prevents blocking issues
        #debug_print(f"Socket type set: {sock.type}")
        mdns_server = mdns.Server(wifi.radio)
        mdns_server.hostname = HOSTNAME
        mdns_server.advertise_service(
            service_type="_debug",
            protocol="_udp",
            port=HTTPPORT
        )
        #debug_print(f"mDNS hostname set to {mdns_server.hostname}.local")
        return sock, mdns_server
    except Exception as e:
        print(f"Error with sock setup: {e}")
        return False

# Initialize NTP client to allow for time requests
def init_ntp():
    if unitTest:
        print("Initializing NTP client...")
    try:
        pool = socketpool.SocketPool(wifi.radio)
        ntp = adafruit_ntp.NTP(pool, server="pool.ntp.org", tz_offset=-7)  # Adjust tz_offset for your timezone
        rtc.set_time_source(ntp)
        return ntp
    except Exception as e:
        #debug_print(f"Failed to initialize NTP: {e}")
        return None

# Function to get the current timestamp
def get_timestamp():
    now = time.localtime()
    return f"{now.tm_mon:02d}/{now.tm_mday:02d}/{now.tm_year} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

connect_to_wifi()
mySock, myServer = config_net()
if not mySock:
    print("Network setup failed. Exiting...")
    exit()
else:
    print(f"sock setup complete: {mySock}, {myServer}")
init_ntp()
announcement = b"ITAOT"

print(f"Broadcasting {announcement.decode()} to {BROADCAST_IP}:{HTTPPORT} every 5 seconds")
buffer = bytearray(1024)  # Create a buffer for incoming data
while True:
    try:
        mySock.sendto(announcement, (BROADCAST_IP, HTTPPORT))
        print(f"{announcement.decode()} broadcasted")
        pass  # Exit loop if successful
    except OSError as e:
        if e.errno == 11:  # EAGAIN
            print("Send buffer full, retrying...")
            time.sleep(0.1)  # Small delay before retrying
        else:
            raise  # Raise other unexpected errors
        
    try:
        print(f"checking for response:")
        bytes_received = mySock.recv_into(buffer)
        if bytes_received:
            received_msg = buffer[:bytes_received].decode()
            print(f"Received response: {received_msg}")
        print(f"Received response from {addr}:")
        response_msg = data.decode()
        print(f"{response_msg} received")
        if "ACK" in response_msg:
            sock.sendto(f"{get_timestamp()} WAY?".encode(), addr)
        elif "WAY" in response_msg:
            mySock.sendto(f"{get_timestamp()} IAM: {HOSTNAME} {device_version}, {device_capabilities}".encode(), addr)
        continue
    except KeyboardInterrupt:
        #debug_print("\nShutting down server...")
        mySock.close()
    except Exception as e:
        print(f"No response yet: {e}")
   
    time.sleep(5)
