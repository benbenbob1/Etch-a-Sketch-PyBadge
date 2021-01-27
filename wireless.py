from adafruit_esp32spi import adafruit_esp32spi
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
import adafruit_requests as requests


class Wireless:

    connected = False

    def __init__(self, spi, esp32_cs, esp32_ready, esp32_reset):
        self.spi = spi
        self.cs = esp32_cs
        self.ready = esp32_ready
        self.reset = esp32_reset

    def try_connect(self, ssid, password, log=True):
        esp = adafruit_esp32spi.ESP_SPIcontrol(self.spi, self.cs, self.ready, self.reset)
        requests.set_socket(socket, esp)

        if log:
            print("Connecting to " + ssid)

        max_tries = 3

        while not esp.is_connected:
            try:
                esp.connect_AP(ssid, password)
            except RuntimeError as e:
                if max_tries < 0:
                    if log:
                        print("Maximum tries exceeded. Could not connect to " + ssid, e)
                        return False
                continue

        self.connected = True
        if log:
            print("Connected to", str(esp.ssid, 'utf-8'), "\tRSSI:", esp.rssi)
            print("My IP address is", esp.pretty_ip(esp.ip_address))
        return True
