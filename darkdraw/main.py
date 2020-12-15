import curses
from darkdraw import *

class DarkDraw:
    def __init__(self):
        self.scr = None
        self._status = ''

    def draw(self):
        scr = self.scr
        scrh, scrw = scr.getmaxyx()
        scr.addstr(scrh-1, scrw-10, '%s %s' % (scrh, scrw), colors.get('red'))

    def handle_key(self, ch):
        pass

    def status(self, s):
        self._status = str(s)

    def run(self, scr):
        self.scr = scr
        while True:
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


def tui_main(scr):
    curses.mousemask(-1)
    scr.timeout(30)

    app = DarkDraw()
    app.run(scr)
