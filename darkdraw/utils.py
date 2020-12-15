import functools
import curses
import threading

from wcwidth import wcswidth


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


def draw(scr, yr, xr, s, colorstr='', funcs=[]):
    if colorstr:
        attr = colors.get(colorstr)
    else:
        attr = 0

    if not isinstance(yr, range): yr = range(yr, yr+1)
    if not isinstance(xr, range): xr = range(xr, xr+1)
    ymax, xmax = scr.getmaxyx()
    for y in yr:
        for x in xr:
            if x >= xmax: fail('need wider terminal (at least %s)' % max(xr))
            if y >= ymax: fail('need taller terminal (at least %s)' % max(yr))
            scr.addstr(y, x, s, attr)


def box(scr, y1, x1, y2, x2, dx=0):
    draw(scr, y1, range(x1, x2), '━')
    draw(scr, y2, range(x1, x2), '━')
    draw(scr, range(y1, y2), x1, '┃')
    draw(scr, range(y1, y2), x2, '┃')
    draw(scr, y1, x1, '┏')
    draw(scr, y1, x2, '┓')
    draw(scr, y2, x1, '┗')
    draw(scr, y2, x2, '┛')
    if dx:
        draw(scr, y1, range(x1+dx, x2, dx), '┯')
        draw(scr, y1, range(x1+dx, x2, dx), '┯')
        draw(scr, range(y1+1, y2), range(x1+dx, x2, dx), '│')
        draw(scr, y2, range(x1+dx, x2, dx), '┷')

