'''
Class definition for soil moisture class that is using an analog sensor for measurement
of a voltage that is converted to a moisture percentage
'''
import analogio
import digitalio

class SoilMoistureSensor:
    def __init__(self, moisture_pin, threshold_pin, min_voltage=3.0, max_voltage=1.80):
        """Initialize the soil moisture sensor"""
        self.sensor = analogio.AnalogIn(moisture_pin)
        self.min_voltage = min_voltage
        self.max_voltage = max_voltage
        self.threshold = digitalio.DigitalInOut(threshold_pin)
        self.threshold.direction = digitalio.Direction.INPUT
        self.threshold.pull = digitalio.Pull.UP
        self.voltage_history = []
        self.ema_voltage = None  # Initialize the EMA voltage value
        self.alpha = 0.3  # Smoothing factor (tweak as needed)

    def read_voltage(self):
        """Read and return the voltage from the analog input"""
        return (self.sensor.value * 3.3) / 65535
    
    def get_filtered_voltage(self):
        """Apply an exponential moving average (EMA) filter to smooth voltage readings."""
        voltage = self.read_voltage()
        if self.ema_voltage is None:
            self.ema_voltage = voltage  # Initialize on first sample
        else:
            self.ema_voltage = (self.alpha * voltage) + ((1 - self.alpha) * self.ema_voltage)
        return self.ema_voltage

    def read_moisture_percentage(self):
        """Convert the voltage reading to a percentage moisture level"""
        volts = self.read_voltage()
        voltage = self.get_filtered_voltage()
        moisture = (voltage - self.min_voltage) / (self.max_voltage - self.min_voltage) * 100
        moisture = max(0, min(100, moisture))  # Clamp values between 0-100%
        return volts ,voltage, moisture

    def read_threshold(self):
        """Read and return the state of the threshold input"""
        return self.threshold.value

    def voltage_stable(self, voltage):
        """Check if the last three measurement differences are within +/-0.005V"""
        self.voltage_history.append(voltage)
        if len(self.voltage_history) > 4:
            self.voltage_history.pop(0)
        
        if len(self.voltage_history) < 4:
            return False  # Not enough data yet
        
        diffs = [abs(self.voltage_history[i] - self.voltage_history[i-1]) for i in range(1, 4)]
        return all(diff <= 0.005 for diff in diffs)
