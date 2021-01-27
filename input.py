import time

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

    '''
    Handles button checking from the button shift register.
    Will debounce certain buttons. For these buttons, only up/down callback function will
    be called even if the button is held down.
    '''

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
        '''
        btn_register is an 8 bit number containing all of the currently pressed buttons
        '''

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
