import time
import board
import smSensor

# Initialize the soil moisture sensor on the appropriate analog pin
moisture_pin = board.A0
threshold_pin = board.GP1

sensor = smSensor.SoilMoistureSensor(moisture_pin, threshold_pin)

def get_timestamp():
    now = time.localtime()
    return f"{now.tm_mon:02d}/{now.tm_mday:02d}/{now.tm_year} {now.tm_hour:02d}:{now.tm_min:02d}:{now.tm_sec:02d}"

def main():
    read_data = 10.0
    interval = 0.1
    count = 10.0 
    while True:
        if count >= read_data:
            timestamp = get_timestamp()
            volts, voltage, moisture = sensor.read_moisture_percentage()
            threshold_state = sensor.read_threshold()
            stable = sensor.voltage_stable(voltage)
            stability_marker = '*' if stable else '+'
            print(f"[{timestamp}] Reading: {volts:.3f}V, Voltage: {voltage:.3f}V, Moisture: {moisture:.1f}%, Threshold: {threshold_state} {stability_marker}")
            count = 0.0
            time.sleep(interval)
        else:
            count += 0.1
            time.sleep(interval)

################################################################################
### run the main() routine (see above)    
if __name__=="__main__":
    main()