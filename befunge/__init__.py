import os
import sys
import re
import curses
from random import randint
from argparse import ArgumentParser
from pathlib import Path
from time import sleep
from io import StringIO
from itertools import chain, takewhile, dropwhile
from datetime import datetime
from ._version import __version__


class StopExecution(Exception):
    pass


class Input(list):
    def __call__(self):
        return self.pop(0)


class Stack(list):
    def copy(self):
        return __class__(super().copy())

    def pop(self, *args, **kwargs):
        try:
            return super().pop()
        except IndexError:
            return 0

    def push(self, value):
        self.append(value)


class StackStack(list):
    def __repr__(self):
        return '\n'.join(str(stack) for stack in self[::-1])

    def copy(self):
        return __class__(stack.copy() for stack in self)

    def push(self, value):
        self.append(value)


class IP:
    def __init__(self, funge, stackstack=None, position=(0, 0), delta=(1, 0), offset=(0, 0), version=982):
        self.funge = funge
        self.id = len([ip.id for ip in self.funge.ips]) if hasattr(self.funge, 'ip') else 0
        self.stackstack = stackstack or StackStack([Stack()])
        self.position = position
        self.delta = delta
        self.offset = offset
        self.version = version
        self.string = False
        self.fingerprint_ops = {}
        if self.op in (ord(' '), ord(';')):
            self.advance()

    @property
    def stack(self):
        if not self.stackstack:
            self.stackstack.append(Stack())
        return self.stackstack[-1]

    @stack.setter
    def stack(self, stack):
        if self.stackstack:
            self.stackstack[-1] = stack
        else:
            self.stackstack.append(stack)

    @property
    def op(self):
        return self.funge[self.position]

    def copy(self):
        return __class__(self.funge, self.stackstack.copy(), self.position, self.delta)

    def reverse(self):
        self.delta = -self.delta[0], -self.delta[1]

    def turn_right(self):
        self.delta = -self.delta[1], self.delta[0]

    def turn_left(self):
        self.delta = self.delta[1], -self.delta[0]

    def read_string(self):
        string = ''
        while True:
            f = self.stack.pop()
            if f == 0:
                return string
            else:
                string += chr(f)

    def read_fingerprint(self):
        n = self.stack.pop()
        t = 0
        for _ in range(n):
            t *= 256
            t += self.stack.pop()
        return t

    def not_implemented(self):
        print(f'operator {self.op} at {self.position} not implemented', file=self.funge.output)
        self.reverse()

    def get_info(self, n):
        time = datetime.now()
        match n:
            case 1:
                yield 15
            case 2:
                yield 2**1024  # as much as the memory can hold
            case 3:
                yield sum([256 ** i * ord(char) for i, char in enumerate('wpfunge')])
            case 4:
                yield __version__.replace('.', '')
            case 5:
                yield 1
            case 6:
                yield ord(os.path.sep)
            case 7:
                yield 2
            case 8:
                yield self.id
            case 9:
                yield 0
            case 10:
                yield from self.position
            case 11:
                yield from self.delta
            case 12:
                yield from self.offset
            case 13:
                yield from self.funge.extent[::2]
            case 14:
                yield from self.funge.extent[1::2]
            case 15:
                yield (time.year - 1900) * 256 * 256 + time.month * 256 + time.day
            case 16:
                yield time.hour * 256 * 256 + time.minute * 256 + time.second
            case 17:
                yield len(self.stackstack)
            case 18:
                yield from (len(stack) for stack in self.stackstack[::-1])
            case 19:
                yield 0
                yield from [ord(char) for arg in sys.argv[2:] for char in f'{arg}\x00'][::-1]
                yield 0
                yield from [ord(char) for char in Path(sys.argv[1]).name][::-1]
            case 20:
                yield 0
                yield from [ord(char) for key, value in os.environ.items() for char in f'{key}={value}\x00'][::-1]
            case i:
                i -= 20
                yield self.stack[-i] if len(self.stack) >= i else 0

    def step(self, k=False):
        if self.string:
            match chr(self.op):
                case '"':
                    self.string = False
                case s:
                    self.stack.push(ord(s))
        elif self.op in self.fingerprint_ops:
            try:
                self.fingerprint_ops[self.op]()
            except Exception:
                self.reverse()
        elif 0 <= self.op < 255:
            match chr(self.op):
                case '+':
                    self.stack.push(self.stack.pop() + self.stack.pop())
                case '-':
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.push(a - b)
                case '*':
                    self.stack.push(self.stack.pop() * self.stack.pop())
                case '/':
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.push(a // b)
                case '%':
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.push(a % b)
                case '!':
                    self.stack.push(int(not self.stack.pop()))
                case '`':
                    self.stack.push(int(self.stack.pop() < self.stack.pop()))
                case '>':
                    self.delta = 1, 0
                case '<':
                    self.delta = -1, 0
                case '^':
                    self.delta = 0, -1
                case 'v':
                    self.delta = 0, 1
                case '?':
                    self.delta = ((-1, 0), (1, 0), (0, -1), (0, 1))[randint(0, 3)]
                case '_':
                    self.delta = ((1, 0), (-1, 0))[bool(self.stack.pop())]
                case '|':
                    self.delta = ((0, 1), (0, -1))[bool(self.stack.pop())]
                case '"':
                    self.string = True
                case ':':
                    a = self.stack.pop()
                    self.stack.push(a)
                    self.stack.push(a)
                case '\\':
                    b, a = self.stack.pop(), self.stack.pop()
                    self.stack.push(b)
                    self.stack.push(a)
                case '$':
                    self.stack.pop()
                case '.':
                    print(str(self.stack.pop()) + ' ', end='', file=self.funge.output)
                case ',':
                    print(chr(self.stack.pop()), end='', file=self.funge.output)
                case '#':
                    self.move()
                case 'p':
                    y, x, a = self.stack.pop(), self.stack.pop(), self.stack.pop()
                    self.funge[x + self.offset[0], y + self.offset[1]] = a
                case 'g':
                    y, x = self.stack.pop(), self.stack.pop()
                    self.stack.push(self.funge[x + self.offset[0], y + self.offset[1]])
                case '&':
                    try:
                        self.stack.push(int(''.join(
                            takewhile(lambda i: i.isdigit(), dropwhile(lambda i: not i.isdigit(), self.funge.input())))))
                    except Exception:
                        self.delta = -self.delta[0], -self.delta[1]
                case '~':
                    try:
                        self.stack.push(ord(self.funge.input()))
                    except Exception:
                        self.reverse()
                case '@':
                    return
                case ' ':
                    self.advance()
                    yield self.step()
                    return
                # 98 from here
                case '[':
                    self.turn_left()
                case ']':
                    self.turn_right()
                case '\'':
                    self.move()
                    self.stack.push(self.op)
                case '{':
                    n = self.stack.pop()
                    cells = -n * [0] if n < 0 else self.stack[-n:][::-1]
                    for coordinate in self.offset:
                        self.stack.push(coordinate)
                    self.stackstack.push(Stack())
                    for cell in cells:
                        self.stack.push(cell)
                    self.offset = self.next_pos
                case '}':
                    n = self.stack.pop()
                    cells = -n * [0] if n < 0 else [self.stack.pop() for _ in range(n)][::-1]
                    self.stackstack.pop()
                    y, x = self.stack.pop(), self.stack.pop()
                    self.offset = x, y
                    for cell in cells:
                        self.stack.push(cell)
                case '=':
                    self.stack.push(os.system(self.read_string()))
                case '(':
                    # no fingerprints are implemented
                    self.read_fingerprint()
                    # self.fingerprint_ops[] = lambda i: i
                    self.reverse()
                case ')':
                    self.read_fingerprint()
                    # self.fingerprint_ops.pop()
                case 'i':
                    file = Path(self.read_string())
                    flags, y0, x0 = self.stack.pop(), self.stack.pop(), self.stack.pop()
                    try:
                        text = file.read_text()
                        if flags % 2:
                            width, height = len(text), 1
                            for x, char in enumerate(text, x0):
                                self.funge[x, y0] = char
                        else:
                            text = text.splitlines()
                            height = len(text)
                            width = max([len(line) for line in text])
                            self.funge.insert_code([line + ' ' * (width - len(line)) for line in text], x0, y0)
                    except Exception:
                        width, height = 0, 0
                    self.stack.push(x0)
                    self.stack.push(y0)
                    self.stack.push(width)
                    self.stack.push(height)
                case 'j':
                    for _ in range(self.stack.pop()):
                        self.move()
                case 'k':
                    self.advance()
                    ips = [self]
                    for n in range(self.stack.pop()):
                        ips = [i for ip in ips for i in ip.step(True)]
                    yield from ips
                    return
                case 'n':
                    self.stack = Stack()
                case 'o':
                    file = Path(self.read_string())
                    flags, x0, y0, width, height = (self.stack.pop() for _ in range(5))
                    try:
                        if flags % 2:
                            text = '\n'.join([''.join([chr(self.funge[x, y]) for x in range(x0, x0 + width)]).rstrip(' ')
                                              for y in range(y0, y0 + height)]).rstrip('\n')
                        else:
                            text = '\n'.join([''.join([chr(self.funge[x, y]) for x in range(x0, x0 + width)])
                                              for y in range(y0, y0 + height)])
                        file.write_text(text)
                    except Exception:
                        self.reverse()
                case 'q':
                    raise StopExecution()
                case 'r':
                    self.reverse()
                case 's':
                    self.move()
                    self.funge[self.position] = self.stack.pop()
                case 't':
                    new = self.copy()
                    new.reverse()
                    yield new.advance()
                case 'u':
                    if len(self.stackstack) > 1:
                        n = self.stack.pop()
                        for _ in range(abs(n)):
                            toss = self.stackstack.pop()
                            toss.push(self.stack.pop())
                            self.stackstack.push(toss)
                    else:
                        self.reverse()
                case 'w':
                    b, a = self.stack.pop(), self.stack.pop()
                    if a < b:
                        self.turn_left()
                    elif a > b:
                        self.turn_right()
                case 'x':
                    dy, dx = self.stack.pop(), self.stack.pop()
                    self.delta = dx, dy
                case 'y':
                    n = self.stack.pop()
                    if n <= 0:
                        for j in range(1, 21):
                            for i in self.get_info(j):
                                self.stack.push(i)
                    else:
                        for i in self.get_info(n):
                            self.stack.push(i)
                case 'z':
                    pass
                case d:
                    if d in '1234567890':
                        self.stack.push(int(d))
                    elif d in 'abcdef':
                        self.stack.push(ord(d) - 87)
                    else:
                        self.not_implemented()
        else:
            self.not_implemented()
        if not k:
            self.advance()
        yield self

    @property
    def next_pos(self):
        pos = tuple(p + d for p, d in zip(self.position, self.delta))
        # TODO: analytic solution
        if not all(a <= p < b for p, a, b in zip(pos, self.funge.extent[::2], self.funge.extent[1::2])):
            while True:
                pos = tuple(p - d for p, d in zip(pos, self.delta))
                if not all(a <= p < b for p, a, b in zip(pos, self.funge.extent[::2], self.funge.extent[1::2])):
                    break
            pos = tuple(p + d for p, d in zip(pos, self.delta))
        return pos

    def move(self):
        self.position = self.next_pos

    def advance(self):
        """ move the ip to the next valid instruction """
        if self.string:
            if self.op == ord(' ') and self.version // 10 > 93:
                while self.op == ord(' '):
                    self.move()
            else:
                self.move()
        else:
            while True:
                if self.op != ord(';'):
                    self.move()
                if self.op == ord(';'):
                    self.move()
                    while self.op != ord(';'):
                        self.move()
                    self.move()
                while self.op == ord(' '):
                    self.move()
                if self.op != ord(';'):
                    break
        return self


class Befunge(dict):
    def __init__(self, code=None, inputs=None):
        super().__init__()
        self.extent = [0, 0, 0, 0]  # xl, xr, yt, yb
        if code.startswith(r'#!/usr/bin/env befunge') or code.startswith(r'#!/usr/bin/env -S befunge'):
            code = '\n'.join(code.splitlines()[1:])
        self.insert_code(code)
        self.output = None
        if inputs is None:
            self.input = input
        else:
            self.input = Input(inputs)
        self.string = False
        self.steps = 0
        self.terminated = False
        self.ips = [IP(self)]

    def insert_code(self, code, x0=0, y0=0):
        if isinstance(code, str):
            code = code.splitlines()
        for y, line in enumerate(code, y0):
            for x, char in enumerate(line, x0):
                self[x, y] = char

    def __getitem__(self, key):
        return self.get(key, ord(' '))

    def __setitem__(self, key, value):
        if key[0] < self.extent[0]:
            self.extent[0] = key[0]
        if key[0] >= self.extent[1]:
            self.extent[1] = key[0] + 1
        if key[1] < self.extent[2]:
            self.extent[2] = key[2]
        if key[1] >= self.extent[3]:
            self.extent[3] = key[1] + 1
        super().__setitem__(key, ord(value) if isinstance(value, str) else value)

    def __repr__(self):
        lines = []
        for (x, y), value in self.items():
            while len(lines) <= y:
                lines.append([])
            while len(lines[y]) <= x:
                lines[y].append(' ')
            lines[y][x] = chr(value) if 32 <= value <= 126 or 161 <= value <= 255 else chr(164)

        for ip in self.ips:
            lines[ip.position[1]][ip.position[0]] = f'\x1b[37m\x1b[40m{lines[ip.position[1]][ip.position[0]]}\033[0m'
        return 'grid:\n' + '\n'.join([''.join(line) for line in lines]) + '\n\n' + \
               'stacks:\n' + '\n-\n'.join(str(ip.stackstack) for ip in self.ips)

    @staticmethod
    def from_file(file, inputs=None):
        file = Path(file)
        return Befunge(file.read_text(), inputs)

    def __iter__(self):
        return self

    def __next__(self):
        if self.step().terminated:
            raise StopIteration
        return self

    def run(self):
        for _ in self:
            pass

    def debug(self, time_step=None):
        def fun(stdscr):
            def scr_input():
                height, width = stdscr.getmaxyx()
                stdscr.move(height - 1, 0)
                stdscr.clrtoeol()
                stdscr.addstr(height - 1, 0, 'input?'[:width])
                stdscr.refresh()
                return stdscr.getstr()

            curses.curs_set(False)
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
            pattern = re.compile(r'\x1b\[[\d;]+m')
            self.output = StringIO()
            if not isinstance(self.input, Input):
                self.input = scr_input
            stdscr.clear()
            stdscr.refresh()

            for b in chain((self,), self, (self,)):
                height, width = stdscr.getmaxyx()
                stdscr.clear()
                b_str = re.sub(pattern, '', str(b))
                for y, line in enumerate(f'{b_str}\n\noutput:\n{b.output.getvalue()}\n\nstep:\n{b.steps}'.splitlines()):
                    if y >= height:
                        break
                    stdscr.addstr(y, 0, line[:width])

                for ip in b.ips:
                    x, y = ip.position
                    if x < width and y < height:
                        stdscr.addstr(y + 1, x, b_str.splitlines()[y + 1][x], curses.color_pair(1))
                if b.terminated:
                    stdscr.addstr(height - 1, 0, 'Press any key to quit.'[:width])
                    stdscr.refresh()
                    stdscr.getch()
                elif time_step is None:
                    stdscr.addstr(height - 1, 0, 'Press any key to continue.'[:width])
                    stdscr.refresh()
                    stdscr.getch()
                else:
                    stdscr.refresh()
                    sleep(time_step)

        try:
            curses.wrapper(fun)
        except KeyboardInterrupt:
            pass

    def step(self, n=1):
        for i in range(n):
            self.steps += 1
            try:
                self.ips = [i for ip in self.ips for i in ip.step()]
            except StopExecution:
                self.ips = []
            if not self.ips:
                self.terminated = True
                return self
        return self


def main():
    parser = ArgumentParser(description='Funge interpreter and debugger')
    parser.add_argument('input', help='funge code file or string')
    parser.add_argument('args', help='arguments to the funge (& or ~)', nargs='*')
    parser.add_argument('-v', '--version', help='show interpreter\'s version number and exit',
                        action='version', version=__version__)
    parser.add_argument('-d', '--debug', help='debug, step on key press or steps / second',
                        type=float, default=False, nargs='?')
    args = parser.parse_args()

    if Path(args.input).exists():
        befunge = Befunge.from_file(args.input, args.args or None)
    else:
        befunge = Befunge(args.input, args.args or None)

    if args.debug is False:
        befunge.run()
    else:
        befunge.debug(args.debug)
