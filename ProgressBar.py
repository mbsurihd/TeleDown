import os
import sys
import msvcrt
from typing import NamedTuple
import time

def RawPrint(s: str, flush: bool = False):
    sys.stdout.write(s)
    if flush:
        sys.stdout.flush()

ESC = '\x1B'
RESET = f'{ESC}[0m'
CLEAR_AFTER_CURSOR = f'{ESC}[0J'
CURSOR_POS = f'{ESC}[6n'
SAVE_CURSOR = f'{ESC}7'
RESTORE_CURSOR = f'{ESC}8'
CURSOR_INVISIBLE = f'{ESC}[?25l'
CURSOR_VISIBLE = f'{ESC}[?25h'

def MOVE_UP (count: int) ->str:
    return f'{ESC}[{count}A'

def MOVE_DOWN (count: int) ->str:
    return f'{ESC}[{count}B'

def COLOR_FG (ID: int) ->str:
    return f'{ESC}[38;5;{ID}m'

def COLOR_BG (ID: int) ->str:
    return f'{ESC}[48;5;{ID}m'

def MOVE_CURSOR(LINE: int, COLUMN: int):
    return f'{ESC}[{LINE};{COLUMN}H'

class Position(NamedTuple):
    row: int = 0
    col: int = 0

def get_cursor_pos() -> Position:
    clear_input_buffer()
    RawPrint(CURSOR_POS, True)
    _resp = b''
    time.sleep(0.1)
    while msvcrt.kbhit():
        _resp += msvcrt.getch()
    _pos = _resp[2::][:-1:].decode('ansi').split(';')
    return Position(int(_pos[0]), int(_pos[1]))

def clamp (min: float, max: float, value: float) ->float:
    if value < min:
        return min
    elif value > max:
        return max
    else:
        return value

def clear_input_buffer():
    while msvcrt.kbhit():
        msvcrt.getch()

MINIMUM_BAR_WIDTH = 26

def CreateProgressBar (BackGround: int, ForeGround: int, Text: int):
    print()
    RawPrint(MOVE_UP(1))
    start = get_cursor_pos()
    term_size = os.get_terminal_size()
    total_width = term_size.columns - start.col + 1
    if total_width < MINIMUM_BAR_WIDTH:
        print()
        total_width = term_size.columns
        start = get_cursor_pos()
    complete = False

    def ProgressBarCallback(Progress: float):
        nonlocal complete
        nonlocal start
        if complete:
            return
        RawPrint(SAVE_CURSOR, True)
        RawPrint(CURSOR_INVISIBLE, True)
        Progress = clamp(0.0, 1.0, Progress)
        term_size = os.get_terminal_size()

        total_width = term_size.columns - start.col + 1

        RawPrint(MOVE_CURSOR(start.row, start.col), True)
        if total_width < MINIMUM_BAR_WIDTH:
            RawPrint(COLOR_FG(Text))
            RawPrint(f'{Progress:3.2%}', True)
        else:
            bg_width = total_width - 9
            fg_width = int(Progress * bg_width)
            RawPrint(COLOR_BG(BackGround))
            RawPrint(" " * bg_width, True)
            RawPrint(RESET)
            RawPrint(COLOR_FG(Text), True)
            RawPrint(f'{Progress:3.2%}'.rjust(8))
            RawPrint(MOVE_CURSOR(start.row, start.col))
            RawPrint(RESET)
            RawPrint(COLOR_BG(ForeGround))
            RawPrint(" " * fg_width, True)

        RawPrint(RESET)
        RawPrint(RESTORE_CURSOR, True)
        RawPrint(CURSOR_VISIBLE, True)

    print()
    return ProgressBarCallback

def TimedPromptKey (timeout: float, key: str):
    start = time.time()
    now = start
    pos = get_cursor_pos()
    while now - start <= timeout:
        RawPrint(MOVE_CURSOR(pos.row, pos.col))
        RawPrint(CLEAR_AFTER_CURSOR)
        RawPrint(COLOR_BG(231))
        RawPrint(COLOR_FG(26))
        RawPrint(f"{round(timeout - (now - start))}", True)
        RawPrint(RESET)
        if msvcrt.kbhit():
            k = msvcrt.getch().decode('utf-8')
            print(flush=True)
            if k == key:
                return True
        now = time.time()
    print(flush=True)
    return False
