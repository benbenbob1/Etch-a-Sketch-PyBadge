# Information on the adafruit_lis3dh module here:
# https://learn.adafruit.com/adafruit-lis3dh-triple-axis-accelerometer-breakout/python-circuitpython#circuitpython-installation-of-lis3dh-library-2997957-11
import adafruit_lis3dh
import array
from audioio import AudioOut
from audiocore import RawSample
import board
import busio
import digitalio
import displayio
import gamepadshift
import math
import neopixel_write
import time

"""
Etch-a-Sketch for the PyBadge!

Required modules (instructions here: https://learn.adafruit.com/welcome-to-circuitpython/circuitpython-libraries)
    adafruit_lis3dh.mpy
    adafruit_bus_device/ <- this is a folder

Buttons:
    A    - Rotate cursor color
    B    - Rotate cursor size
    Dpad - Move cursor and draw

    Shake device (there will be a countdown) or hold Select for 2 seconds - Reset drawing

Features:
    Shake to reset, with sound and led feedback
    PyBadge leds will match cursor color
    Sound and button press library for the PyBadge

"""

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

# Set board display brightness
board.DISPLAY.brightness = DISPLAY_BRIGHTNESS

# Setup accelerometer
i2c = busio.I2C(board.SCL, board.SDA)
accel_interrupt = digitalio.DigitalInOut(board.ACCELEROMETER_INTERRUPT)
lis3dh = adafruit_lis3dh.LIS3DH_I2C(i2c, int1=accel_interrupt)

# Setup neopixel leds
neopixel_pin = digitalio.DigitalInOut(board.NEOPIXEL)
neopixel_pin.direction = digitalio.Direction.OUTPUT

# Setup gamepad shift register
data = digitalio.DigitalInOut(board.BUTTON_OUT)
clock = digitalio.DigitalInOut(board.BUTTON_CLOCK)
latch = digitalio.DigitalInOut(board.BUTTON_LATCH)
gp = gamepadshift.GamePadShift(clock=clock, data=data, latch=latch)

# Setup speaker
speaker_enable = digitalio.DigitalInOut(board.SPEAKER_ENABLE)
speaker_enable.switch_to_output(value=True)
audio = AudioOut(board.SPEAKER)

class AudioHelper:
    SPEAKER_VOLUME = 0.3 # Increase this to increase the volume of the tones

    playing = False
    audio = None
    prev_time = 0 # time at the start of the previous note start
    prev_note_len_s = 0 # time previous note was requested for, in seconds
    note_queue = [] # array of tuples like (freq, timeS) to play in order, FIFO

    def __init__(self, audio):
        self.audio = audio

    def _generate_sin_wave(self, freqHz):
        length = 8000 // freqHz
        sine_wave = array.array("H", [0] * length)
        for i in range(length):
            sine_wave[i] = int((1 + math.sin(math.pi * 2 * i / length)) * self.SPEAKER_VOLUME * (2 ** 15 - 1))
        return sine_wave

    def _frequency_from_note_and_octave(self, note_name, octave=5):
        all_notes = ['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#']
        note = note_name.upper()

        note_idx = 3 # default to C5
        try:
            note_idx = all_notes.index(note)
        except ValueError:
            return 0 # silence

        if note_idx < 3:
            octave = octave + 1

        octave_offset = (octave - 1) * 12
        converted_key = converted_key = note_idx + octave_offset + 1
        return int(440 * math.pow(2, (converted_key - 49) / 12))

    def play_tone(self, freq_hz=440, time_s=0.1):
        sine_wave = []

        if freq_hz > 0:
            sine_wave = RawSample(self._generate_sin_wave(freq_hz))
        else:
            freq_hz = 0

        if self.playing:
            self.note_queue.append((freq_hz, time_s))
        else:
            if freq_hz != 0:
                audio.play(sine_wave, loop=True)
            self.prev_time = time.monotonic()
            self.prev_note_len_s = time_s
            self.playing = True

    def play_note(self, note_and_octave="C5", time_s=0.1):
        """
        Note can be like 'A#5', 'C4', or 'R'
        """

        if len(note_and_octave) > 3:
            print("Cannot play note " + note_and_octave)
            return

        note_name = 'R' # rest/silence
        octave = 5

        note_end_idx = 1
        if len(note_and_octave) > 1:
            if len(note_and_octave) == 3:
                note_end_idx = 2
            octave = int(note_and_octave[-1:])
        note_name = note_and_octave[:note_end_idx]
        self.play_tone(self._frequency_from_note_and_octave(note_name, octave), time_s)

    def stop(self):
        audio.stop()
        self.playing = False

    def tick(self):
        if self.playing:
            if time.monotonic() - self.prev_time >= self.prev_note_len_s:
                self.stop()
        if not self.playing:
            if len(self.note_queue) > 0: # schedule next note if queued
                next_note = self.note_queue.pop(0) # like (freq, time)
                self.play_tone(next_note[0], next_note[1])

class Button:
    def __init__(self, name, debounce, register_bit):
        self.name = name
        self.debounce = debounce
        self.up_callback = None
        self.down_callback = None
        self.register_bit = register_bit
        self.long_press_callback = None
        # How long the button must be pressed for to register long press, in seconds
        self.long_press_time_s = 1.0

class ButtonPress:
    """
    Handles button checking from the button shift register.
    Will debounce certain buttons. For these buttons, only up/down callback function will
    be called even if the button is held down.
    """

    buttons = [
        Button("B", True, 1),
        Button("A", True, 2),
        Button("Start", True, 4),
        Button("Select", True, 8),
        Button("Right", False, 16),
        Button("Down", False, 32),
        Button("Up", False, 64),
        Button("Left", False, 128)
    ]

    def __init__(self):
        self.prev_button_status = {}
        self.long_press_status = {} # Saves when each press started
        for btn in range(len(self.buttons)):
            self.prev_button_status[self.buttons[btn].name] = False
            self.long_press_status[self.buttons[btn].name] = 0

    def button_from_name(self, name):
        for btn in range(len(self.buttons)):
            if self.buttons[btn].name == name:
                return self.buttons[btn]
        return None

    def exec_if_not_none(self, to_exec):
        if to_exec is not None:
            to_exec()

    def check_pressed(self, btn_register, log=False):
        """
        btn_register is an 8 bit number containing all of the currently pressed buttons
        """

        cur_time = time.monotonic()

        for btn in range(len(self.buttons)):
            cur_btn = self.buttons[btn]
            if btn_register & cur_btn.register_bit:
                if cur_btn.long_press_callback is not None:
                    if self.long_press_status[cur_btn.name] > 0:
                        time_diff = cur_time - self.long_press_status[cur_btn.name]
                        if time_diff >= cur_btn.long_press_time_s:
                            if log:
                                print(cur_btn.name + " long press")
                            self.exec_if_not_none(cur_btn.long_press_callback)
                            self.long_press_status[cur_btn.name] = 0
                    else:
                        self.long_press_status[cur_btn.name] = cur_time
                if not cur_btn.debounce or (cur_btn.debounce and not self.prev_button_status[cur_btn.name]):
                    if log:
                        print(cur_btn.name)
                    self.exec_if_not_none(cur_btn.down_callback)
                    self.prev_button_status[cur_btn.name] = True
            else:
                if cur_btn.long_press_callback is not None:
                    # If button was pressed earlier and now released, set long press status to 0
                    if self.long_press_status[cur_btn.name] > 0:
                        self.long_press_status[cur_btn.name] = 0
                if cur_btn.debounce and self.prev_button_status[cur_btn.name]:
                    self.exec_if_not_none(cur_btn.up_callback)
                    self.prev_button_status[cur_btn.name] = False

class Draw:
    """
    Class for handling screen drawing and cursor positioning.
    More info on displayio/bitmaps here:
    https://learn.adafruit.com/circuitpython-display-support-using-displayio/bitmap-and-palette
    """
    cursor_sizes = [1, 2, 4, 8] # square cursor, this is the edge width
    cur_cursor_idx = 1 # current cursor (size), index in above array
    cur_cursor_size = cursor_sizes[cur_cursor_idx]
    cursor_bitmap = None # displayio.Bitmap
    cursor_grid = None # displayio.TileGrid
    cursor_bitmap_size = 0 # edge length of square cursor bitmap

    colors = [] # array of [r,g,b] values
    display = None
    display_size = (0,0)
    display_bitmap = None # displayio.Bitmap
    display_palette = None # displayio.Palette

    cur_color_idx = 0 # color index
    off_color_idx = -1 # index of black in above array
    invis_color_idx = 0 # transparent, should be len(colors)+1, it is treated as an "invisible" color
    cur_pos = (0,0)

    def __init__(self, display, rgbColors=[[255,0,0], [0,0,0]], offIdx=1):
        """
        display should come from board.DISPLAY
        rgbColors is array of [r,g,b] values for the color palette
        offIdx is the index of black in above array
        """

        self.colors = rgbColors
        self.off_color_idx = offIdx
        self.invis_color_idx = len(self.colors) + 1
        self.display = display

        self.display_size = (self.display.width, self.display.height)
        print("Initializing Draw with display size: " + str(self.display_size[0]) + " x " + str(self.display_size[1]))

        self.display_bitmap = displayio.Bitmap(self.display_size[0], self.display_size[1], len(self.colors))
        self.cursor_bitmap_size = max(self.cursor_sizes) # set bitmap width/height to biggest possible cursor size
        self.cursor_bitmap = displayio.Bitmap(self.cursor_bitmap_size, self.cursor_bitmap_size, len(self.colors))

        self.reset() # Setup screen and position cursor

        self.display_palette = displayio.Palette(len(self.colors))
        for c in range(len(self.colors)):
            self.display_palette[c] = self.colors[c]

        display_grid = displayio.TileGrid(self.display_bitmap, pixel_shader=self.display_palette, x=0, y=0)
        self.cursor_grid = displayio.TileGrid(self.cursor_bitmap, pixel_shader=self.display_palette, x=0, y=0)
        display_group = displayio.Group(max_size=2)
        display_group.append(display_grid)
        display_group.append(self.cursor_grid)
        self.display.show(display_group)

    def rotate_cursor(self):
        self.cur_cursor_idx = self.cur_cursor_idx + 1
        if self.cur_cursor_idx >= len(self.cursor_sizes):
            self.cur_cursor_idx = 0

        # If cursor is near the edge of the screen and the cursor size increases,
        # move the cursor position to accomodate the new size
        if self.cur_pos[0] + self.cur_cursor_size >= self.display_size[0]:
            self.cur_pos = (self.display_size[0]-self.cur_cursor_size, self.cur_pos[1])
        if self.cur_pos[1] + self.cur_cursor_size >= self.display_size[1]:
            self.cur_pos = (self.cur_pos[0], self.display_size[1]-self.cur_cursor_size)

        self.cur_cursor_size = self.cursor_sizes[self.cur_cursor_idx]

    def draw_and_move_cursor(self, delta_X=0, delta_Y=0):
        # Draw at new position, using current color idx
        for x in range(self.cur_cursor_size):
            for y in range(self.cur_cursor_size):
                self.display_bitmap[
                    min(self.cur_pos[0]+x, self.display_size[0]-1),
                    min(self.cur_pos[1]+y, self.display_size[1]-1)
                ] = self.cur_color_idx

        # Change cursor position
        if delta_X != 0:
            new_X = self.cur_pos[0] + delta_X
            if new_X >= 0 and new_X + (delta_X*(self.cur_cursor_size-1)) < self.display_size[0]:
                self.cur_pos = (max(min(new_X+(delta_X*(self.cur_cursor_size-1)), self.display_size[0]-self.cur_cursor_size), 0), self.cur_pos[1])
        if delta_Y != 0:
            new_Y = self.cur_pos[1] + delta_Y
            if new_Y >= 0 and new_Y + (delta_Y*(self.cur_cursor_size-1)) < self.display_size[1]:
                self.cur_pos = (self.cur_pos[0], max(min(new_Y+(delta_Y*(self.cur_cursor_size-1)), self.display_size[1]-self.cur_cursor_size), 0))

    def display_cursor(self, display=False):
        """
        Used for flashing the cursor to indicate current cursor position
        """

        cursor_color = self.cur_color_idx
        if self.cur_color_idx == self.off_color_idx:
            cursor_color = 0 # white
        if not display:
            cursor_color = self.off_color_idx
        self.cursor_grid.x = self.cur_pos[0]
        self.cursor_grid.y = self.cur_pos[1]
        display_color = cursor_color
        for x in range(self.cursor_bitmap_size):
            for y in range(self.cursor_bitmap_size):
                if (x < self.cur_cursor_size) and (y < self.cur_cursor_size):
                    display_color = cursor_color
                else:
                    display_color = self.invis_color_idx
                self.cursor_bitmap[x, y] = display_color

    def set_color(self, color_idx):
        self.cur_color_idx = color_idx

    def reset(self):
        # Start off cursor in the middle of the screen
        self.cur_pos = (int(self.display_size[0] / 2.0), int(self.display_size[1] / 2.0))
        # Initialize display to all black (set every pixel to black/off index)
        for x in range(self.display_size[0]):
            for y in range(self.display_size[1]):
                self.display_bitmap[x,y] = self.off_color_idx

drawer = Draw(board.DISPLAY, COLORS_RGB, 6)
tone_player = AudioHelper(audio)

def move_up():
    drawer.draw_and_move_cursor(0,-1)
def move_down():
    drawer.draw_and_move_cursor(0,1)
def move_left():
    drawer.draw_and_move_cursor(-1,0)
def move_right():
    drawer.draw_and_move_cursor(1,0)

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
        int(color_rgb[2] * LED_BRIGHTNESS)]
    led_count_diff = NUM_LEDS-led_count
    pix = new_color * NUM_LEDS # This creates an array of length NUM_LEDS with each value = new_color
    if led_count < NUM_LEDS: # if provided led count is lower than NUM_LEDS, fill the remaining frame with black
        for led in range(led_count_diff):
            led_idx = (NUM_LEDS-1-led)*3
            pix[led_idx+0] = 0
            pix[led_idx+1] = 0
            pix[led_idx+2] = 0
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
    button_checker = ButtonPress()
    button_checker.button_from_name("Up").down_callback = move_up
    button_checker.button_from_name("Down").down_callback = move_down
    button_checker.button_from_name("Left").down_callback = move_left
    button_checker.button_from_name("Right").down_callback = move_right
    button_checker.button_from_name("B").down_callback = on_btn_B
    button_checker.button_from_name("A").down_callback = on_btn_A
    button_checker.button_from_name("Select").long_press_time_s = 2.0
    button_checker.button_from_name("Select").long_press_callback = on_shake

    tone_player.play_note("C5", 0.2)
    tone_player.play_note("E5", 0.2)
    tone_player.play_note("G5", 0.2)

    cursor_on = False
    cursor_blink_iter = 5 # cursor blink rate is cursor_blink_iter * tick rate
    cursor_blink_counter = 0

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