import functools
import itertools
import curses
import threading
import visidata

from wcwidth import wcswidth

screen_contents = {}

class AttrDict(dict):
    'Augment a dict with more convenient .attr syntax.  not-present keys return None.'
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            if k.startswith("__"):
                raise AttributeError
            return None

    def __setattr__(self, k, v):
        self[k] = v

    def __dir__(self):
        return self.keys()


class Colors:
    def __init__(self):
        self.color_pairs = {}  # (fgcolornum, bgcolornum) -> pairnum

    @functools.cached_property
    def colors(self):
        'not computed until curses color has been initialized'
        return {x[6:]:getattr(curses, x) for x in dir(curses) if x.startswith('COLOR_') and x != 'COLOR_PAIRS'}

    def keys(self):
        return self.colors.keys()

    def get(self, colorstr):
        attrs = 0
        fgbg = [7, 0]
        i = 0
        for x in colorstr.split():
            if x == 'on': i = 1
            elif attr := getattr(curses, 'A_' + x.upper(), None):
                attrs |= attr
            else:
                fgbg[i] = int(x) if x.isdigit() else self.colors.get(x.upper(), 0)

        pairnum = self.color_pairs.get(tuple(fgbg), None)
        if not pairnum:
            pairnum = len(self.color_pairs)+1
            curses.init_pair(pairnum, *fgbg)
            self.color_pairs[tuple(fgbg)] = pairnum
        return curses.color_pair(pairnum) | attrs

colors = Colors()


keycodes = { getattr(curses, k):k for k in dir(curses) if k.startswith('KEY_') }
keycodes.update({chr(i): '^'+chr(64+i) for i in range(32)})
def getkey(scr):
    try:
        ch = scr.get_wch()
        return keycodes.get(ch, ch)
    except curses.error:
        return ''


def wc_rjust(text, length, padding=' '):
    return padding * max(0, (length - wcswidth(text))) + text

def wc_center(text, length, padding=' '):
    x = max(0, (length - wcswidth(text)))
    return padding*(x//2) + text + padding*((x+1)//2)

def wc_ljust(text, length, padding=' '):
    return text + padding * max(0, (length - wcswidth(text)))


def asyncthread(func):
    @functools.wraps(func)
    def _execAsync(*args, **kwargs):
        thread = threading.Thread(target=func, daemon=True, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return _execAsync


def fail(s):
    raise Exception(s)


class Box:
    def __init__(self, scr, x1, y1, w=None, h=None):
        self.scr = scr
        self.h = h or scr.getmaxyx()[0]-1
        self.w = w or scr.getmaxyx()[1]-2
        self.x1 = x1
        self.y1 = y1

    @property
    def x2(self):
        return self.x1+self.w

    @x2.setter
    def x2(self, v):
        self.w = v-self.x1

    @property
    def y2(self):
        return self.y1+self.h

    @y2.setter
    def y2(self, v):
        self.h = v-self.y1

    def erase(self):
        screen_contents.clear()
        for y in range(self.y1, self.y2+1):
            self.scr.addstr(y, 0, ' '*self.w, 0)

    def draw(self, yr, xr, s, attr=0):
        'Draw *s* into box.  *yr* an *xr* in relative coordinates; may be ranges.'
        if isinstance(attr, str):
            attr = colors.get(attr)

        if not isinstance(yr, range): yr = range(yr, yr+1)
        if not isinstance(xr, range): xr = range(xr, xr+1)
        ymax, xmax = self.scr.getmaxyx()
        if self.y1+max(yr) > ymax: fail('need taller screen (at least %s)' % max(yr))
        if self.x1+max(xr) > xmax: fail('need wider screen (at least %s)' % max(xr))
        for y in yr:
            for x in xr:
                screen_contents[(self.x1+x, self.y1+y)] = (s, attr)
                self.scr.addstr(self.y1+y, self.x1+x, s, attr)

    def contains(self, x, y):
        '*xr* and *yr* in screen coordinates.'
        return self.x1 <= x < self.x2 and self.y1 <= y < self.y2

    def box(self, x1=0, y1=0, dx=0, color=''):
        if self.w <= 0 or self.h <= 0: return
        attr = colors.get(color)
        x2, y2=x1+self.w, y1+self.h
        self.draw(0, range(x1, x2), '━', attr)
        self.draw(y2, range(x1, x2), '━', attr)
        self.draw(range(y1, y2), x1, '┃', attr)
        self.draw(range(y1, y2), x2, '┃', attr)
        self.draw(y1, x1, '┏', attr)
        self.draw(y1, x2, '┓', attr)
        self.draw(y2, x1, '┗', attr)
        self.draw(y2, x2, '┛', attr)
        if dx:
            self.draw(y1, range(x1+dx, x2, dx), '┯', attr)
            self.draw(y1, range(x1+dx, x2, dx), '┯', attr)
            self.draw(range(y1+1, y2), range(x1+dx, x2, dx), '│', attr)
            self.draw(y2, range(x1+dx, x2, dx), '┷', attr)

    def rjust(self, s, x=0, y=0, w=0, color=' '):
        w = w or self.w
        return self.ljust(s, x=self.x1+x+w-wcswidth(s)-1, y=y, color=color)

    def center(self, s, x=0, y=0, w=0, padding=' '):
        x += max(0, ((w or self.w) - wcswidth(s)))
        return self.ljust(s, x=self.x1+x//2, y=y, w=w-x)

    def ljust(self, s, x=0, y=0, w=0, color=' '):
        if self.w <= 0 or self.h <= 0: return
        if y > self.h: fail(f'{y}/{self.h}')

        scrh, scrw = self.scr.getmaxyx()
        attr = colors.get(color)
        pre = ''
        xi = x
        for c in s:
            cw = wcswidth(c)
            if xi+cw >= self.w:
                break
            if cw == 0:
                pre += c
            elif cw < 0: # not printable
                pass
            else:
                self.draw(y, xi, pre+c, attr)
                pre = ''
                xi += cw

        # add blanks to fill width
        for i in range(xi-x, w+1):
            self.draw(y, xi+i, ' ', attr)

        return w or xi-x

    def blit(self, tile, *, y1=0, x1=0, y2=None, x2=None, xoff=0, yoff=0):
        y2 = y2 or self.h-1
        x2 = x2 or self.w-1
        y = y1
        lines = list(itertools.zip_longest(tile.lines, tile.pcolors))
        while y < y2:
          if y-y1+yoff >= len(lines):
              try:
                  self.draw(y, x1, ' '*(x2-x1), 0)
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
                    attr = colors.get(tile.palette[cmask]) if cmask else 0
                    try:
                        self.draw(y, x, pre+c, attr)
                    except curses.error:
                        raise Exception(f'y={y} x={x}')
                    x += w
                    pre = ''
                i += 1

            y += 1

        while y < y2:
          try:
            self.draw(y, x1, ' '*(x2-x1), 0)
            y += 1
          except curses.error:
              raise Exception(y, y2)


def input(scr, prompt, **kwargs):
    ymax, xmax = scr.getmaxyx()
    promptlen = visidata.clipdraw(scr, ymax-1, 0, prompt, 0, w=xmax-1)

    r = visidata.vd.editline(scr, ymax-1, promptlen, xmax-promptlen-2, **kwargs)
    curses.flushinp()
    return r
