### Pico W (Server) - CircuitPython ###
import os
import mdns
import wifi
import socketpool
import time
import rtc
import adafruit_requests
import adafruit_ntp
import board
import digitalio

class cPyNetConfig:
    def __init__(self, WIFI_SSID, WIFI_PASSWORD, NETPORT, BROADCAST_IP):
        # Initialize, connect, provision the network
        self.WIFI_SSID = os.getenv("WIFI_SSID")
        self.WIFI_PASSWORD = os.getenv("WIFI_PASS")
        self.HOSTNAME = os.getenv("HOSTNAME")
        self.BROADCAST_IP = "10.0.0.255"
        self.NETPORT = 5244
        self.MAX_RETRIES = 10
        self.activity = digitalio.DigitalInOut(board.LED)
        self.activity.direction = digitalio.Direction.OUTPUT
        # Sensor specific initializations
        self.device_version = "SMS v0.1"
        self.device_capabilities = "soil moisture"

    def net_activity(self, count):
        while count > 0:
            self.activity.value = True
            time.sleep(0.1)
            self.activity.value = False
            time.sleep(0.1)
            count -= 1
        
    # Use a loop to attempt to connect and configure a wifi net
    # we use the settings.toml for for story credentials
    def connect_to_wifi(self):
        if not self.WIFI_SSID or not self.WIFI_PASSWORD:
            raise ValueError("Missing required settings in settings.toml")
        attempt = 0
        delay = 3
        while self.MAX_RETRIES is None or attempt < self.MAX_RETRIES:
            if UNITTEST:
                print("Connecting to Wi-Fi...")

            try:
                wifi.radio.connect(self.WIFI_SSID, self.WIFI_PASSWORD)
                wifi.radio.hostname = self.HOSTNAME
                print(f"Connected to Wi-Fi @ {self.WIFI_SSID}")
                print(f"WIFI IP Address: {wifi.radio.ipv4_address}")
                self.net_activity(3)
                return True  # Exit the function once connected
            except Exception as e:
                attempt += 1
                print(f"Failed to connect to Wi-Fi @ {self.WIFI_SSID}: {e}")
                #print(f"Retrying ({attempt}/{self.MAX_RETRIES if self.MAX_RETRIES else '∞'}) in {delay} seconds...")
                time.sleep(delay)  # Wait before retrying
        if UNITTEST:
            print("Max retries reached. Could not connect to Wi-Fi.")
        return False  # Return False if connection is unsuccessful

    # Configure listening socket and mDNS,
    # this is where the HOSTNAME is set to allow for 'ping HOSTNAME.local' to work
    def config_net(self):
        if UNITTEST:
            print("Configuring network...")
        # Setup for Protocol handling
        try:
            pool = socketpool.SocketPool(wifi.radio)
            # Create a listening socket for UDP
            sock = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)     
            for _ in range(5):  # Try 5 times with delays
                try:
                    sock.bind(("0.0.0.0", self.NETPORT))
                    print("sock bind success...")
                    break  # If successful, exit retry loop
                except OSError as e:
                    if e.errno == 112:  # EADDRINUSE
                        print("Port still in use, retrying...")
                        time.sleep(1)
                    else:
                        raise  # Unexpected error
            mdns_server = mdns.Server(wifi.radio)
            mdns_server.hostname = self.HOSTNAME
            mdns_server.advertise_service(
                service_type="_debug",
                protocol="_udp",
                port=self.NETPORT
            )
            print(f"mDNS hostname set to {mdns_server.hostname}.local")
            return sock, mdns_server
        except Exception as e:
            print(f"Error with sock setup: {e}")
            return False

    # Initialize NTP client to allow for time requests
    def init_ntp(self):
        if UNITTEST:
            print("Initializing NTP client...")
        try:
            pool = socketpool.SocketPool(wifi.radio)
            ntp = adafruit_ntp.NTP(pool, server="pool.ntp.org", tz_offset=-7)  # Adjust tz_offset for your timezone
            rtc.set_time_source(ntp)
            now = time.localtime()
            print(f"Local Time: {now.tm_mon:02d}/{now.tm_mday:02d}/{now.tm_year} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}")
            return ntp
        except Exception as e:
            print(f"Failed to initialize NTP: {e}")
            return None


# Globals for filtering and sensor
UNITTEST = False

if UNITTEST:
    # Function to get the current timestamp
    def get_timestamp():
        now = time.localtime()
        return f"{now.tm_mon:02d}/{now.tm_mday:02d}/{now.tm_year} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

    # Load settings from settings.toml and check for no credentials
    WIFI_SSID = os.getenv("WIFI_SSID")
    WIFI_PASSWORD = os.getenv("WIFI_PASS")
    HOSTNAME = os.getenv("HOSTNAME")
    NETPORT = 5244
    MAX_RETRIES = 10
    BCAST_IP = "10.0.0.255"
    # instantiate the network configuration class
    netConf = cPyNetConfig(WIFI_SSID, WIFI_PASSWORD, NETPORT, BCAST_IP)

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

    print(f"Broadcasting {announcement.decode()} to {BCAST_IP}:{NETPORT} every 5 seconds")
    buffer = bytearray(1024)  # Create a buffer for incoming data
    while True:
        try:
            mySock.sendto(announcement, (BCAST_IP, NETPORT))
            print(f"{announcement.decode()} broadcasted")
        except OSError as e:
            if e.errno == 11:  # EAGAIN
                print("Send buffer full, retrying...")
                time.sleep(0.1)  # Small delay before retrying
            else:
                raise  # Raise other unexpected errors
            
        try:
            print(f"checking for response:")
            data, addr = mySock.recvfrom_into(buffer)  # 1024 is the buffer size
            received_msg = data.decode()

            print(f"Received response from {addr}: {received_msg}")

            print(f"{received_msg} received")
            if "ACK" in received_msg:
                mySock.sendto(f"{get_timestamp()} WAY?".encode(), addr)
            elif "WAY" in received_msg:
                mySock.sendto(f"{get_timestamp()} IAM: {netConf.HOSTNAME} {netConf.device_version}, {netConf.device_capabilities}".encode(), addr)
            continue
        except KeyboardInterrupt:
            #debug_print("\nShutting down server...")
            mySock.close()
        except Exception as e:
            print(f"No response yet: {e}")
       
        time.sleep(5)


