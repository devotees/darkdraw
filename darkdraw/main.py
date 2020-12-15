import sys
import itertools
import curses
from darkdraw import *

scroll_rate = 4

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
        self.current_pcolor = ' '

    def check_cursor(self):
        scrh, scrw = self.scr.getmaxyx()
        if self.cursor_x < self.left_x:      self.left_x = self.cursor_x
        if self.cursor_x > self.left_x+scrw: self.left_x = self.cursor_x-scrw
        if self.cursor_y < self.top_y:       self.top_y = self.cursor_y
        if self.cursor_y > self.top_y+scrh:  self.top_y = self.cursor_y-scrh

    def draw(self):
        scr = self.scr
        scrh, scrw = scr.getmaxyx()

        right_status = f'{self.lastkey: <10s}  {self.cursor_y:2d},{self.cursor_x:2d} / {scrh:2d},{scrw:2d}'
        scr.addstr(scrh-1, scrw-len(right_status)-1, right_status, colors.get('green'))

        left_status = f'{self.current_ch} {self.current_pcolor}  | {self._status}'
        left_status = wc_ljust(left_status, scrw-len(right_status)-3)
        scr.addstr(scrh-1, 1, left_status)

        self.main.blit(scr, yoff=self.top_y, xoff=self.left_x)

        scr.move(self.cursor_y-self.top_y, self.cursor_x-self.left_x)

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
            try:
                return self.handle_mouse(x, y, bstate)
            except Exception as e:
                self.status(e)
                return

        self.lastkey += str(ch)

        if ch == 'KEY_UP':      self.cursor_y -= scroll_rate; self.top_y -= scroll_rate
        elif ch == 'KEY_DOWN':  self.cursor_y += scroll_rate; self.top_y += scroll_rate
        elif ch == 'KEY_RIGHT': self.cursor_x += scroll_rate; self.left_x += scroll_rate
        elif ch == 'KEY_LEFT':  self.cursor_x -= scroll_rate; self.left_x -= scroll_rate
        elif ch == 'KEY_SRIGHT': self.cursor_x += 1
        elif ch == 'KEY_SLEFT':  self.cursor_x -= 1
        elif ch == 513:         self.cursor_y += 1
        elif ch == 529:         self.cursor_y -= 1
        else:
            self.status(f"unknown key '{ch}'")

    def handle_click(self, x, y, b):
        self.lastkey += f'C{b}({x}, {y})'
        if b == 1:  # left click to move cursor
            self.cursor_y = self.top_y + y
            self.cursor_x = self.left_x + x
        elif b == 3:  # right click
            self.current_ch = self.main.get_ch(self.left_x+x, self.top_y+y)
            self.current_pcolor = self.main.get_pcolor(self.left_x+x, self.top_y+y)

    def handle_press(self, x, y, b):
        self.lastkey += f'P{b}({x}, {y})'

    def handle_release(self, x, y, b):
        self.lastkey += f'R{b}({x}, {y})'

    def status(self, *args):
        self._status = ' '.join(map(str, args))

    def run(self, scr):
        self.scr = scr
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


class Tile:
    def __init__(self, fp):
        self.mask = []
        self.lines = []
        self.palette = {}  # ch -> colorstr

        for line in fp.readlines():
            line = line[:-1]
            if not line: continue
            if line.startswith('#C '):  #C S fg on bg underline reverse
                self.palette[line[3]] = line[4:]
            elif line.startswith('#M '):  #M mask of color id (S above) corresponding to line
                self.mask.append(line[3:])
            else:
                self.lines.append(line)

    def get_ch(self, x, y):
        return self.lines[y%len(self.lines)][x]

    def get_pcolor(self, x, y):
        return self.mask[y%len(self.lines)][x]

    def blit(self, scr, *, y1=0, x1=0, y2=None, x2=None, xoff=0, yoff=0):
        scrh, scrw = scr.getmaxyx()
        y2 = y2 or scrh-1
        x2 = x2 or scrw-1
        y = y1
        lines = list(itertools.zip_longest(self.lines, self.mask))
        while y < y2:
          if y-y1+yoff >= len(lines):
              try:
                  scr.addstr(y, x1, ' '*(x2-x1), 0)
                  y += 1
              except curses.error:
                  raise Exception(y, y2)
              continue
          else:
            line, linemask = lines[(y-y1+yoff)%len(lines)]
            pre = ''
            x = x1
            i = 0
            while x < x2:
                c = line[(xoff+i)%len(line)]
                cmask = linemask[(xoff+i)%len(linemask)] if linemask else 0
                w = wcswidth(c)
                if w == 0:
                    pre = c
                elif w < 0: # not printable
                    pass
                else:
                    attr = colors.get(self.palette[cmask]) if cmask else 0
                    try:
                        scr.addstr(y, x, pre+c, attr)
                    except curses.error:
                        raise Exception(f'y={y} x={x}')
                    x += w
                    pre = ''
                i += 1

            y += 1

        while y < y2:
          try:
            scr.addstr(y, x1, ' '*(x2-x1), 0)
            y += 1
          except curses.error:
              raise Exception(y, y2)



def tui_main(scr):
    curses.mousemask(-1)
    scr.timeout(30)

    app = DarkDraw(Tile(open(sys.argv[1])))
    scrh, scrw = scr.getmaxyx()
    app.cursor_x = scrw//2
    app.cursor_y = scrh//2
    app.run(scr)
