import curses
from .main import tui_main

curses.wrapper(tui_main)
