from dataclasses import dataclass
import itertools
import contextlib
import sys
import curses
import curses.panel

import visidata
from darkdraw import *

options = AttrDict()

scroll_rate = 4

def colorstr_from_attr(attr):
            colorpair = curses.pair_number(attr)
            fg, bg = curses.pair_content(colorpair)
            r = f'{fg} on {bg}'
            if attr & curses.A_BOLD: r += ' bold'
            if attr & curses.A_UNDERLINE: r += ' underline'
            return r

def remove_attr(colorstr, attrstr):
    return ' '.join(x for x in colorstr.split() if x != attrstr)


class DarkDraw:
    def __init__(self, screen):
        self.scr = None  # curses scr
        self.main = screen

        self._status = ''
        self.lastkey = ''
        self.prefixes = ['^[']
        self.cursor_x, self.cursor_y = 0, 0
        self.left_x, self.top_y = 0, 0
        self.current_ch = ' '
        self.current_color = ' '
        self.codepage = 0x2600

        self.press_y = 0
        self.press_x = 0
        self.extras = []

        self.box_colors = None
        self.box_chars = None


    @property
    def current_bg(self):
        colorpair = curses.pair_number(colors.get(self.current_color))
        fg, bg = curses.pair_content(colorpair)
        return f'on {bg}'

    @property
    def current_fg(self):
        colorpair = curses.pair_number(colors.get(self.current_color))
        fg, bg = curses.pair_content(colorpair)
        return f'{fg}'

    @property
    def current_attr(self):
        r = []
        if 'bold' in self.current_color: r.append('bold')
        if 'underline' in self.current_color: r.append('underline')
        return ' '.join(r)

    def check_cursor(self):
        scrh, scrw = self.scr.getmaxyx()
        if self.cursor_x < self.left_x:      self.left_x = self.cursor_x
        if self.cursor_x > self.left_x+scrw: self.left_x = self.cursor_x-scrw
        if self.cursor_y < self.top_y:       self.top_y = self.cursor_y
        if self.cursor_y > self.top_y+scrh:  self.top_y = self.cursor_y-scrh

    def draw(self):
        scr = self.scr
        scrh, scrw = scr.getmaxyx()

        mainbox = Box(scr, 0, 0, scrw, scrh-2)
        mainbox.erase()
        mainbox.blit(self.main, yoff=self.top_y, xoff=self.left_x)

        ## right status on bottom row
        right_status = f'{self.lastkey: <10s} {self.cursor_x:2d},{self.cursor_y:2d} / {scrw},{scrh}'

        sbox = Box(scr, 0, scrh-1) # the last line
        rstatw = sbox.rjust(right_status, color='bold')

        ## left status
        x = 1
        x += sbox.ljust(self.current_ch, x=x, w=2, color='white')
        x += sbox.ljust(self.current_fg, x=x, w=4, color=self.current_fg)
        x += sbox.ljust(self.current_bg, x=x, w=4, color=self.current_bg)
        x += sbox.ljust(self.current_attr, x=x, w=12, color=self.current_attr)

        sbox.ljust(self._status, x=x+2)

        ## color palette
        self.box_colors.erase()
        self.box_colors.box()
        for i in range(0, 240):
            self.box_colors.ljust('██', y=i//36+1, x=(i%36)*2+3, color=f'{i+16}')

        self.box_chars.erase()
        self.box_chars.box(color='bold 242 on 0')
        ## character palette
        for i in range(256):
            self.box_chars.ljust(chr(self.codepage+i), y=i//16+1, x=(i%16)*3+6, w=3, color='white')
            self.box_chars.center(f'U+{self.codepage:4X}', y=self.box_chars.h)

        for i in range(16):
            self.box_chars.ljust('0123456789ABCDEF'[i], y=i+1, color='bold 242 on 0')
            self.box_chars.ljust('0123456789ABCDEF'[i], x=i*3+6, color='bold 242 on 0')

        for x in self.extras:
            x(scr)

        scr.refresh()
        curses.doupdate()

    def handle_mouse(self, x, y, b):
        if b & curses.BUTTON1_PRESSED:   self.handle_press(x, y, 1)
        elif b & curses.BUTTON1_RELEASED: self.handle_release(x, y, 1)
        elif b & curses.BUTTON1_CLICKED: self.handle_click(x, y, 1)
        elif b & curses.BUTTON2_PRESSED:   self.handle_press(x, y, 2)
        elif b & curses.BUTTON2_RELEASED: self.handle_release(x, y, 2)
        elif b & curses.BUTTON2_CLICKED: self.handle_click(x, y, 2)
        elif b & curses.BUTTON3_PRESSED:   self.handle_press(x, y, 3)
        elif b & curses.BUTTON3_RELEASED: self.handle_release(x, y, 3)
        elif b & curses.BUTTON3_CLICKED: self.handle_click(x, y, 3)
        else:
            self.lastkey += f'{b}({x}, {y})'

    def handle_key(self, ch):
        if self.lastkey not in self.prefixes:
            self.lastkey = ''

        self._status = ''

        if ch == 'KEY_MOUSE':
            id, x, y, z, bstate = curses.getmouse()
            return self.handle_mouse(x, y, bstate)

        self.lastkey += str(ch)
        if ch in self.prefixes: return
        elif ch == '^S':        self.main.save(input(self.scr, "save as: ", value=self.main.fn))
        elif ch == 'KEY_UP':    self.cursor_y -= scroll_rate; self.top_y -= scroll_rate
        elif ch == 'KEY_DOWN':  self.cursor_y += scroll_rate; self.top_y += scroll_rate
        elif ch == 'KEY_RIGHT': self.cursor_x += scroll_rate; self.left_x += scroll_rate
        elif ch == 'KEY_LEFT':  self.cursor_x -= scroll_rate; self.left_x -= scroll_rate
        elif ch == 'KEY_SRIGHT': self.cursor_x += 1
        elif ch == 'KEY_SLEFT': self.cursor_x -= 1
        elif ch == 513:         self.cursor_y += 1
        elif ch == 529:         self.cursor_y -= 1
        elif ch == 'KEY_NPAGE': self.codepage += 0x100
        elif ch == 'KEY_PPAGE': self.codepage -= 0x100
        elif ch == 'c':         self.box_colors.h = -self.box_colors.h
        elif ch == 'C':         self.box_chars.h = -self.box_chars.h
        elif ch == ' ':         self.main.set_ch(self.cursor_x, self.cursor_y, self.current_ch)
        elif ch == '>':         self.main.set_bg(self.cursor_x, self.cursor_y, self.current_bg)
        elif ch == '<':         self.main.set_fg(self.cursor_x, self.cursor_y, self.current_fg)
        elif ch == 'a':         self.main.set_attr(self.cursor_x, self.cursor_y, self.current_attr)
        elif ch == 'U':         self.current_color = 'underline ' + remove_attr(self.current_color, 'underline')
        elif ch == 'u':         self.current_color = remove_attr(self.current_color, 'underline')
        elif ch == 'B':         self.current_color = 'bold ' + remove_attr(self.current_color, 'bold')
        elif ch == 'b':         self.current_color = remove_attr(self.current_color, 'bold')
        elif ch == '^Y':        
            with visidata.SuspendCurses():
                visidata.view(app)
        else:
            self.status(f"unknown key '{ch}'")

    def handle_click(self, x, y, b):
        self.lastkey += f'C{b}({x}, {y})'
        if b == 1:  # left click to move cursor
            self.cursor_y = self.top_y + y
            self.cursor_x = self.left_x + x

    def handle_press(self, x, y, b):
        if b == 3:  # right press to pick up
            def _pickup(scr):
                attr = 0
                r = screen_contents.get((x,y), None)
                if r:
                    attr = r[1]
                scr.chgat(y, x, 1, attr | curses.A_UNDERLINE)
            self.extras.append(_pickup)

        self.press_y = y
        self.press_x = x

        self.lastkey = f'P{b}({x}, {y})'

    def handle_release(self, x, y, b):
        self.lastkey = f'R{b}({x}, {y})'
        if b == 1:
            self.box_cursor = Box(self.scr, self.press_x, self.press_y, x-self.press_x, y-self.press_y)
        elif b == 3:
            if self.press_y != y or self.press_x != x:
                fail('cursor moved')

            r = screen_contents.get((x,y), None)
            if not r:
                fail("no contents there")
            if self.box_chars.contains(x,y):
                if r:
                    self.current_ch = r[0]
                    self.status(f'char now {self.current_ch}')
            elif self.box_colors.contains(x,y):
                if r:
                    self.current_color = str(r[1]) # colorstr_from_attr(attr)
                    self.status(f'color now {self.current_color}')
            else:
                if r:
                    self.current_ch = ch
                    self.current_color = colorstr_from_attr(attr)
                    self.status(f'color now {self.current_color}')
                    self.status(f'char now {self.current_ch}')


    def status(self, *args):
        self._status = ' '.join(map(str, args))

    def run(self, scr):
        self.scr = scr

        self.box_colors = Box(scr, 0, 0, 77, 8)
        self.box_chars = Box(scr, 0, 8, 58, 17)

        while True:
            self.check_cursor()
            self.draw()
            ch = getkey(self.scr)

            if not ch: continue
            elif ch == 'q': return
            elif ch == '^L':
                self.scr.clear()
                self.scr.refresh()
                curses.doupdate()
            else:
                try:
                    self.handle_key(ch)
                except Exception as e:
                    self.status(str(e))
                    if options.debug:
                        raise
                except visidata.EscapeException as e:
                    self.status(str(e))


class Tile:
    def __init__(self, fn):
        self.pcolors = []  # list of list of colorcode
        self.lines = []  # list of list of char
        self.palette = {}  # colorcode -> colorstr
        self.fn = fn

        with open(fn) as fp:
          for line in fp.readlines():
            line = line[:-1]
            if not line: continue
            if line.startswith('#C '):  #C S fg on bg underline reverse
                self.palette[line[3]] = line[4:].strip()
            elif line.startswith('#M '):  #M mask of color id (S above) corresponding to line
                self.pcolors.append(line[3:])
            else:
                self.lines.append(line)

    def save(self, fn):
        with open(fn, mode='w') as fp:
            for ch, colorstr in self.palette.items():
                fp.write(f"#C {ch} {colorstr}\n")

            for y in range(len(self.pcolors)):
                fp.write("#M " + ''.join(self.pcolors[y]) + "\n")

            for y in range(len(self.lines)):
                fp.write(''.join(self.lines[y]) + "\n")

        self.status(f"saved to {fn}")

    def get_ch(self, x, y):
        return self.lines[y%len(self.lines)][x]

    def get_pcolor(self, x, y):
        return self.pcolors[y%len(self.lines)][x]

    def get_color(self, x, y):
        pc = self.get_pcolor(x, y)
        return self.palette[pc]



def tui_main(scr):
    curses.raw()
    curses.meta(1)
    curses.mousemask(-1)
    curses.curs_set(False)

    with contextlib.suppress(curses.error):
        curses.curs_set(0)
    scr.timeout(30)

    inputfns = []

    for arg in sys.argv[1:]:
        if arg in ['-d', '--debug']: options.debug = True
        else:
            inputfns.append(arg)

    global app
    app = DarkDraw(*(Tile(fn) for fn in inputfns))
    app.run(scr)
