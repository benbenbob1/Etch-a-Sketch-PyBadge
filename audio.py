import array
from audiocore import RawSample
import math
import time

class Audio:

    SPEAKER_VOLUME = 0.3 # (0 to 1) Increase this to increase the volume of the tones

    playing = False
    audio = None
    prev_time = 0 # time at the start of the previous note start
    prev_note_len_s = 0 # time previous note was requested for, in seconds
    note_queue = [] # array of tuples like (freq, timeS) to play in order, FIFO

    def __init__(self, audio):
        '''
        audio is of type audioio.AudioOut
        '''
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
                self.audio.play(sine_wave, loop=True)
            self.prev_time = time.monotonic()
            self.prev_note_len_s = time_s
            self.playing = True

    def play_note(self, note_and_octave="C5", time_s=0.1):
        '''
        Note can be like 'A#5', 'C4', or 'R'
        '''

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
        self.audio.stop()
        self.playing = False

    def tick(self):
        if self.playing:
            if time.monotonic() - self.prev_time >= self.prev_note_len_s:
                self.stop()
        if not self.playing:
            if len(self.note_queue) > 0: # schedule next note if queued
                next_note = self.note_queue.pop(0) # like (freq, time)
                self.play_tone(next_note[0], next_note[1])
