# script for prototyping on the picow using circuitpython
# this script reads wifi credentials from the settings.toml file,
# connects to the wifi net, sets the hostname, and using an NTP server to set device time
import os
from microcontroller import watchdog as w
from watchdog import WatchDogMode
import socketpool
import wifi
import mdns
import time
import rtc
import adafruit_ntp

# Load settings from settings.toml and check for no credentials
WIFI_SSID = os.getenv("WIFI_SSID")
WIFI_PASSWORD = os.getenv("WIFI_PASS")
HOSTNAME = os.getenv("HOSTNAME")

if not WIFI_SSID or not WIFI_PASSWORD:
    raise ValueError("Missing required settings in settings.toml")

# Use wifi library to connect to Wi-Fi
def connect_to_wifi():
    print("Connecting to Wi-Fi...")
    try:
        wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
        wifi.radio.hostname = HOSTNAME
        print("Connected to Wi-Fi!")
        print(f"IP Address: {wifi.radio.ipv4_address}")
    except Exception as e:
        print(f"Failed to connect to Wi-Fi: {e}")
        raise

# Configure mDNS, this is where the HOSTNAME is set to allow for 'ping HOSTNAME.local' to work
def configure_mdns():
    print("Configuring mDNS...")
    try:
        pool = socketpool.SocketPool(wifi.radio)
        mdns_server = mdns.Server(wifi.radio)
        mdns_server.hostname = HOSTNAME
        mdns_server.advertise_service(
            service_type="_http",
            protocol="_tcp",
            port=5244
        )
        print(f"mDNS hostname set to {mdns_server.hostname}.local")
    except Exception as e:
        print(f"Failed to configure mDNS: {e}")
        raise

# Initialize NTP client to allow for time requests
def initialize_ntp():
    print("Initializing NTP client...")
    pool = socketpool.SocketPool(wifi.radio)
    ntp = adafruit_ntp.NTP(pool, server="pool.ntp.org", tz_offset=0)  # Adjust tz_offset for your timezone
    rtc.set_time_source(ntp)
    return ntp

# Function to format the time in a customized format
def format_time(t):
    return f"{t.tm_year}-{t.tm_mon:02d}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

# Main function
def main():
    # Connect to Wi-Fi
    connect_to_wifi()

    # Configure mDNS
    configure_mdns()

    # Initialize NTP
    ntp = initialize_ntp()
    last_ntp_update = time.monotonic()
    ntp_interval = 3600

    # Enable Watchdog Timer
    w.timeout = 8  # Set the watchdog timeout to 8 seconds (maximum supported)
    w.mode = WatchDogMode.RESET

    # Variables for non-blocking timing
    last_time_printed = time.monotonic()
    time_interval = 15  # Time interval in seconds

    now = time.localtime()
    print(f"Initial UTC Time: {format_time(now)}")

    # Main loop
    while True:
        try:
            # Refresh Watchdog Timer
            w.feed()

            # Check if the print time interval has elapsed
            current_time = time.monotonic()
            if current_time - last_time_printed >= time_interval:
                # Get and print current time
                now = time.localtime()
                print(f"Current UTC Time: {format_time(now)}")
                last_time_printed = current_time
            # Check if the ntp time interval has elapsed
            if current_time - last_ntp_update >= ntp_interval:
                    ntp = initialize_ntp()

            # Perform other non-blocking tasks here (if needed)
            pass

        except Exception as e:
            print(f"An error occurred: {e}")
            w.feed()

# Run the main function
if __name__ == "__main__":
    main()
