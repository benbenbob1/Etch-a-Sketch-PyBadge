import displayio


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
    display_size = (0, 0)
    display_bitmap = None # displayio.Bitmap
    display_palette = None # displayio.Palette

    cur_color_idx = 0 # color index
    off_color_idx = -1 # index of black in above array
    invis_color_idx = 0 # transparent, should be len(colors)+1, it is treated as an "invisible" color
    cur_pos = (0, 0)

    def __init__(self, board_display, rgbColors=[[255, 0, 0], [0, 0, 0]], offIdx=1):
        """
        display should come from board.DISPLAY
        rgbColors is array of [r,g,b] values for the color palette
        offIdx is the index of black in above array
        """

        self.colors = rgbColors
        self.off_color_idx = offIdx
        self.invis_color_idx = len(self.colors) + 1
        self.display = board_display

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

    def save_drawing(self):
        """
        Returns the name of the saved file, or False if file could not be saved
        """

        bmp_filename = "/" + str(time.time()) + ".bmp"
        adafruit_bitmapsaver.save_pixels(
            file_or_filename=bmp_filename,
            pixel_source=self.display_bitmap,
            palette=self.display_palette)
        return bmp_filename