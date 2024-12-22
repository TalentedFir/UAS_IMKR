import RPi.GPIO as GPIO
import time
import board
import digitalio
import adafruit_max31865
import paho.mqtt.client as mqtt

# Konfigurasi Pin GPIO untuk sensor ultrasonik
TRIG_PIN = 23  # Pin GPIO untuk Trigger
ECHO_PIN = 24  # Pin GPIO untuk Echo

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG_PIN, GPIO.OUT)
GPIO.setup(ECHO_PIN, GPIO.IN)

# Inisialisasi SPI dan sensor MAX31865
spi = board.SPI()
cs = digitalio.DigitalInOut(board.D12)
sensor = adafruit_max31865.MAX31865(spi, cs, wires=3)

# Konfigurasi MQTT
broker = "broker.mqtt-dashboard.com"  # Ganti dengan alamat broker MQTT Anda
port = 1883  # Port MQTT default
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Terhubung ke broker MQTT")
    else:
        print(f"Gagal terhubung ke broker MQTT, kode: {rc}")

def on_publish(client, userdata, mid):
    print("Data berhasil dipublikasikan")

mqtt_client.on_connect = on_connect
mqtt_client.on_publish = on_publish

try:
    mqtt_client.connect(broker, port, keepalive=60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"Gagal menghubungkan ke broker MQTT: {e}")
    exit()

# Fungsi untuk membaca jarak dengan sensor ultrasonik
def baca_jarak(timeout=0.02):
    # Kirim sinyal Trigger (10µs HIGH)
    GPIO.output(TRIG_PIN, True)
    time.sleep(0.00001)
    GPIO.output(TRIG_PIN, False)

    # Tunggu sinyal HIGH pada Echo (dengan timeout)
    start_time = time.time()
    while GPIO.input(ECHO_PIN) == 0:
        if time.time() - start_time > timeout:
            return None  # Gagal membaca sinyal Echo (timeout)

    # Catat waktu mulai pulsa Echo
    pulse_start = time.time()

    # Tunggu sinyal LOW pada Echo (dengan timeout)
    while GPIO.input(ECHO_PIN) == 1:
        if time.time() - pulse_start > timeout:
            return None  # Gagal membaca sinyal Echo (timeout)

    # Catat waktu akhir pulsa Echo
    pulse_end = time.time()

    # Hitung durasi pulsa Echo
    durasi = pulse_end - pulse_start

    # Hitung jarak dalam cm
    jarak = (durasi * 34300) / 2
    return jarak

# Fungsi untuk mengonversi jarak ke level
def konversi_jarak_ke_level(jarak):
    # Jarak antara 13 cm (0%) dan 3 cm (100%)
    if jarak is None:
        return None
    if jarak < 3:
        return 100
    if jarak > 13:
        return 0
    # Hitung level dalam persen
    level = ((13 - jarak) / (13 - 3)) * 100
    return level

# Buffer untuk moving average
moving_average_buffer = []
buffer_size = 16  #g digunakan untuk moving average

def moving_average(value):
    global moving_average_buffer
    if value is not None:
        moving_average_buffer.append(value)
        if len(moving_average_buffer) > buffer_size:
            moving_average_buffer.pop(0)  # Hapus nilai lama jika buffer penuh
    if len(moving_average_buffer) > 0:
        return sum(moving_average_buffer) / len(moving_average_buffer)
    return None

try:
    while True:
        # Baca data dari sensor ultrasonik
        raw_jarak = baca_jarak()
        smoothed_jarak = moving_average(raw_jarak)

        if smoothed_jarak is None:
            print("Sensor ultrasonik tidak terhubung atau pembacaan gagal.")
        elif 0 <= smoothed_jarak <= 25:
            level = konversi_jarak_ke_level(smoothed_jarak)
            print(f"Level (smoothed): {level:.2f}%")

        # Baca data dari sensor suhu MAX31865
        try:
            temperature = sensor.temperature
            print('Temperature (MAX31865): {0:0.3f}C'.format(temperature))
        except Exception as e:
            print(f"Kesalahan pembacaan sensor MAX31865: {e}")

        # Publikasikan data ke MQTT
        if smoothed_jarak is not None:
            mqtt_client.publish("data/level", str(level))
        if 'temperature' in locals():
            mqtt_client.publish("data/temperature", str(temperature))

        # Jeda 1 detik sebelum pembacaan berikutnya
        time.sleep(1)

except KeyboardInterrupt:
    print("Program dihentikan.")
    GPIO.cleanup()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()