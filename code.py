# Information on the adafruit_lis3dh module here:
# https://learn.adafruit.com/adafruit-lis3dh-triple-axis-accelerometer-breakout/python-circuitpython#circuitpython-installation-of-lis3dh-library-2997957-11
import adafruit_lis3dh
from audio import Audio
from audioio import AudioOut
import board
import busio
import digitalio
from draw import Draw
import gamepadshift
from input import ButtonPress
import neopixel_write
import time

NUM_LEDS = 5
LED_BRIGHTNESS = 0.05 # 0 to 1
DISPLAY_BRIGHTNESS = 0.8 # 0 to 1
TICK_RATE_S = 0.1 # seconds, update frequency in main loop (button detection, drawing, etc)

ACCEL_SHAKE_THRESH = 8 # threshold for shake detection: this is the difference between subsequent accelerometer values
SHAKE_TO_CLEAR_TIME_S = 1.5 # if the device is shaken consistently for this many seconds, it will trigger a screen clear

SHAKE_TUNE = ["G#5", "F5", "E5", "C5"]
SHAKE_TUNE_NOTE_LEN_S = 0.2

# white, red, yellow, green, blue, purple, black
COLORS_RGB = [[255,255,255], [255,0,0], [255,180,0], [0,255,0], [0,0,255], [255,0,255], [0,0,0]]
cur_color_idx = 0 # color from index of above array

board.DISPLAY.brightness = DISPLAY_BRIGHTNESS # set board display brightness

# Setup accelerometer
i2c = busio.I2C(board.SCL, board.SDA)
accel_interrupt = digitalio.DigitalInOut(board.ACCELEROMETER_INTERRUPT)
lis3dh = adafruit_lis3dh.LIS3DH_I2C(i2c, int1=accel_interrupt)

# Setup neopixel leds
neopixel_pin = digitalio.DigitalInOut(board.NEOPIXEL)
neopixel_pin.direction = digitalio.Direction.OUTPUT

# Setup gamepad shift register for button reading
data = digitalio.DigitalInOut(board.BUTTON_OUT)
clock = digitalio.DigitalInOut(board.BUTTON_CLOCK)
latch = digitalio.DigitalInOut(board.BUTTON_LATCH)
gp = gamepadshift.GamePadShift(clock=clock, data=data, latch=latch)

# Setup speaker
speaker_enable = digitalio.DigitalInOut(board.SPEAKER_ENABLE)
speaker_enable.switch_to_output(value=True)
audio = AudioOut(board.SPEAKER)

drawer = None
tone_player = None

def move_up():
    drawer.draw_and_move_cursor(0, -1)
def move_down():
    drawer.draw_and_move_cursor(0, 1)
def move_left():
    drawer.draw_and_move_cursor(-1, 0)
def move_right():
    drawer.draw_and_move_cursor(1, 0)

def rotate_color():
    global cur_color_idx
    cur_color_idx = cur_color_idx + 1
    if cur_color_idx >= len(COLORS_RGB):
        cur_color_idx = 0
    drawer.set_color(cur_color_idx)
    show_color_on_leds(COLORS_RGB[cur_color_idx], NUM_LEDS)

def show_color_on_leds(color_rgb, led_count=NUM_LEDS):
    # neopixels are in GREEN, RED, BLUE order (not sure why?)
    new_color = [
        int(color_rgb[1] * LED_BRIGHTNESS),
        int(color_rgb[0] * LED_BRIGHTNESS),
        int(color_rgb[2] * LED_BRIGHTNESS)
    ]
    led_count_diff = NUM_LEDS - led_count
    pix = new_color * NUM_LEDS # This creates an array of length NUM_LEDS with each value = new_color
    if led_count < NUM_LEDS: # if provided led count is lower than NUM_LEDS, fill the remaining frame with black
        for led in range(led_count_diff):
            led_idx = (NUM_LEDS - 1 - led) * 3
            pix[led_idx + 0] = 0
            pix[led_idx + 1] = 0
            pix[led_idx + 2] = 0
    neopixel_write.neopixel_write(neopixel_pin, bytearray(pix)) # write the colors to the leds

def on_btn_B():
    tone_player.play_note("C5", 0.1)
    drawer.rotate_cursor()

def on_btn_A():
    tone_player.play_note("E5", 0.1)
    rotate_color()

def on_shake():
    tone_player.play_note("G5", 0.2)
    tone_player.play_note("E5", 0.2)
    tone_player.play_note("C5", 0.2)
    drawer.reset()
    show_color_on_leds(COLORS_RGB[cur_color_idx], NUM_LEDS)

def main_loop():
    global tone_player, drawer

    tone_player = Audio(audio)

    # Assign all of the button functions
    button_checker = ButtonPress()
    button_checker.button_from_name("Up").down_callback = move_up
    button_checker.button_from_name("Down").down_callback = move_down
    button_checker.button_from_name("Left").down_callback = move_left
    button_checker.button_from_name("Right").down_callback = move_right
    button_checker.button_from_name("B").down_callback = on_btn_B
    button_checker.button_from_name("A").down_callback = on_btn_A

    # As a backup, accept a 2 sec hold for the shake/clear command
    button_checker.button_from_name("Select").long_press_time_s = 2.0
    button_checker.button_from_name("Select").long_press_callback = on_shake

    # Intro tune
    tone_player.play_note("C5", 0.2)
    tone_player.play_note("E5", 0.2)
    tone_player.play_note("G5", 0.2)

    cursor_on = False
    cursor_blink_iter = 5 # cursor blink rate is cursor_blink_iter * tick rate
    cursor_blink_counter = 0

    drawer = Draw(board.DISPLAY, COLORS_RGB, 6)
    drawer.display_cursor(True)

    ticks_per_sec = 1.0 / TICK_RATE_S
    shake_counter = 0
    # Ticks with no shake, to allow a tolerance
    no_shake_counter = 0
    # Number of ticks until SHAKE_TO_CLEAR_TIME_S seconds have passed
    shake_ticks_to_activate = ticks_per_sec * SHAKE_TO_CLEAR_TIME_S
    shake_forgiveness = 2

    prev_X = 0
    prev_Y = 0
    prev_Z = 0

    prev_num_leds = NUM_LEDS
    new_num_leds = NUM_LEDS

    rotate_color()
    while True:
        button_checker.check_pressed(gp.get_pressed(), log=True)
        tone_player.tick()

        x, y, z = lis3dh.acceleration

        diff_X = abs(prev_X - x)
        diff_Y = abs(prev_Y - y)
        diff_Z = abs(prev_Z - z)

        if diff_X >= ACCEL_SHAKE_THRESH or diff_Y >= ACCEL_SHAKE_THRESH or diff_Z >= ACCEL_SHAKE_THRESH:
            no_shake_counter = 0

            # Show a countdown on the leds
            new_num_leds = int(NUM_LEDS - ((shake_counter / shake_ticks_to_activate) * NUM_LEDS))
            if new_num_leds != prev_num_leds:
                show_color_on_leds(COLORS_RGB[cur_color_idx], led_count=new_num_leds)
                # Every change in leds should result in a sound
                tone_player.play_note(SHAKE_TUNE[new_num_leds % len(SHAKE_TUNE)], SHAKE_TUNE_NOTE_LEN_S)
            prev_num_leds = new_num_leds
            if shake_counter >= shake_ticks_to_activate:
                on_shake()
                shake_counter = 0
            else:
                shake_counter = shake_counter + 1
        else:
            if shake_counter > 0:
                if no_shake_counter >= shake_forgiveness:
                    show_color_on_leds(COLORS_RGB[cur_color_idx], led_count=NUM_LEDS)
                    shake_counter = 0
                no_shake_counter = no_shake_counter + 1

        prev_X = x
        prev_Y = y
        prev_Z = z

        drawer.display_cursor(cursor_on)
        cursor_blink_counter = cursor_blink_counter + 1
        if cursor_blink_counter >= cursor_blink_iter:
            cursor_on = not cursor_on
            cursor_blink_counter = 0

        time.sleep(TICK_RATE_S)

main_loop()
