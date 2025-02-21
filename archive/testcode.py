import time
import wifi
import socketpool
import mdns
import board
import busio
from adafruit_seesaw.seesaw import Seesaw

SSID = "PeaceHill"
PASSWORD = "C0smoSag@n"
HOSTNAME = "soilsensor"

wifi.radio.connect(SSID, PASSWORD)
print(f"Connected to {SSID}, IP address: {wifi.radio.ipv4_address}")

mdns_server = mdns.Server(wifi.radio)
mdns_server.hostname = HOSTNAME
mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=80)

i2c = busio.I2C(board.GP5, board.GP4)
seesaw = Seesaw(i2c, addr=0x36)

pool = socketpool.SocketPool(wifi.radio)
server = pool.socket()
server.bind(("0.0.0.0", 80))
server.listen(5)
server.setblocking(False)  # Keep it non-blocking

print(f"Server running as {HOSTNAME}.local on port 80")

while True:
    try:
        try:
            conn, addr = server.accept()
            if not conn:
                time.sleep(0.1)
                continue

            print(f"Connection from {addr}, conn type: {type(conn)}")

        except OSError as e:
            if e.errno == 11:  # EAGAIN / No connection yet
                time.sleep(0.1)
                continue
            else:
                print("Error accepting connection:", e)
                continue

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
            print("No data received after retries. Closing connection.")
            conn.close()
            continue

        # Convert received bytes to a string
        request_str = request_buffer[:bytes_received].decode("utf-8")
        print("Received request:", request_str)

        # Prepare HTTP response
        if "GET /hello" in request_str:
            response = "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 20\r\nConnection: close\r\n\r\nHello from Pico W!"
        elif "GET /moisture" in request_str:
            #moisture = ss.moisture_read()
            moisture = 1233
            response = f"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {len(str(moisture))}\r\nConnection: close\r\n\r\nMoisture: {moisture}"
        else:
            response = "HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: 9\r\nConnection: close\r\n\r\nNot Found"

        print(f"Sending response:\n{response}")
        conn.send(response.encode("utf-8"))
        conn.close()
        print("Response sent successfully.")

    except Exception as e:
        print("Unexpected error:", e)
