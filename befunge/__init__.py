from enum import Enum
from random import randint
from argparse import ArgumentParser
from pathlib import Path
from time import sleep
from io import StringIO
from itertools import chain
from curses import wrapper


class OperatorException(Exception):
    def __init__(self, op):
        super().__init__(f'Could not parse operator {op}')


class Direction(Enum):
    RIGHT = 0
    UP = 1
    LEFT = 2
    DOWN = 3

    def __add__(self, other):
        return Direction((self.value + other) % len(Direction))

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        return Direction((self.value - other) % len(Direction))

    def __rsub__(self, other):
        return self - other


class Input(list):
    def __call__(self):
        return self.pop(0)


class Grid(dict):
    def __init__(self, code=None, version=None):
        self.version = version or 'b93'
        self.cursor = True
        if self.version == 'b93':
            self.shape = 80, 25
        else:
            self.shape = None
        self._ip = [0, 0]
        self.direction = Direction.RIGHT
        super().__init__()
        for y, line in enumerate(code.splitlines()):
            for x, char in enumerate(line):
                self[(x, y)] = char

    def wrap(self, value, dim):
        if self.shape is None:
            return value
        else:
            return value % self.shape[dim]

    @property
    def x(self):
        return self._ip[0]

    @x.setter
    def x(self, value):
        self._ip[0] = self.wrap(value, 0)

    @property
    def y(self):
        return self._ip[1]

    @y.setter
    def y(self, value):
        self._ip[1] = self.wrap(value, 1)

    def __getitem__(self, key):
        return self.get(key, ord(' '))

    def __setitem__(self, key, value):
        super().__setitem__(tuple(self.wrap(k, i) for i, k in enumerate(key)),
                            ord(value) if isinstance(value, str) else value)

    def __repr__(self):
        lines = []
        for (x, y), value in self.items():
            while len(lines) <= y:
                lines.append([])
            while len(lines[y]) <= x:
                lines[y].append(' ')
            lines[y][x] = chr(value) if 32 <= value <= 126 or 161 <= value <= 255 else chr(164)
        lines = [''.join(line) for line in lines]
        if self.cursor:
            return '\n'.join(lines[:self.y] +
                             [lines[self.y][:self.x] +
                              '\x1b[37m\x1b[40m' + lines[self.y][self.x] + '\033[0m' +
                              lines[self.y][self.x + 1:]] +
                             lines[self.y + 1:])
        else:
            return '\n'.join(lines)

    @property
    def op(self):
        return self[self.x, self.y]

    def advance(self):
        match self.direction:
            case Direction.RIGHT:
                self.x += 1
            case Direction.UP:
                self.y -= 1
            case Direction.LEFT:
                self.x -= 1
            case Direction.DOWN:
                self.y += 1


class Stack(list):
    def pop(self, index=-1):
        try:
            return super().pop(index)
        except IndexError:
            return 0

    def push(self, value):
        self.append(value)


class Befunge(Grid):
    def __init__(self, code=None, version=None, inputs=None):
        super().__init__(code, version)
        self.output = None
        if inputs is None:
            self.input = input
        else:
            self.input = Input(inputs)
        self.stack = Stack()
        self.string = False
        self.steps = 0
        self.terminated = False
        self.operations = {'b93': '+-*/%!`><^v?_|":\\$.,#pg&~@ 1234567890'}[self.version]

    @staticmethod
    def from_file(file, version=None, inputs=None):
        file = Path(file)
        if version is None:
            match file.suffix:
                case '.bf':
                    version = 'b93'
                case suffix:
                    version = suffix.strip('.')
        return Befunge(file.read_text(), version, inputs)

    def __repr__(self):
        return f'grid:\n{super().__repr__()}\n\nstack:\n{self.stack}'

    def __iter__(self):
        return self

    def __next__(self):
        if self.step().terminated:
            raise StopIteration
        return self

    def run(self):
        for _ in self:
            pass

    def debug(self, time_step):
        def fun(stdscr):
            def scr_input():
                height, width = stdscr.getmaxyx()
                stdscr.move(height - 1, 0)
                stdscr.clrtoeol()
                stdscr.addstr(height - 1, 0, 'input?')
                stdscr.move(self.y + 1, self.x)
                stdscr.refresh()
                return stdscr.getstr()

            self.output = StringIO()
            self.cursor = False
            if not isinstance(self.input, Input):
                self.input = scr_input
            stdscr.clear()
            stdscr.refresh()

            for b in chain((self,), self):
                height, width = stdscr.getmaxyx()
                stdscr.clear()
                stdscr.addstr(f'{b}\n\noutput:\n{b.output.getvalue()}\n\nstep:\n{b.steps}')
                if time_step > 0:
                    stdscr.move(b.y + 1, b.x)
                    stdscr.refresh()
                    sleep(time_step)
                else:
                    stdscr.addstr(height - 1, 0, 'Press any key to continue.')
                    stdscr.move(b.y + 1, b.x)
                    stdscr.refresh()
                    stdscr.getch()

            height, width = stdscr.getmaxyx()
            stdscr.move(height - 1, 0)
            stdscr.clrtoeol()
            stdscr.addstr(height - 1, 0, 'Press any key to quit.')
            stdscr.move(self.y + 1, self.x)
            stdscr.getch()

        try:
            wrapper(fun)
        except KeyboardInterrupt:
            pass

    def step(self, n=1):
        m = 0
        while m < n:
            if self.string:
                if self.op == ord('"'):
                    self.string = False
                else:
                    self.stack.push(self.op)
            elif chr(self.op) in self.operations:
                match chr(self.op):
                    case '+':
                        self.stack.push(self.stack.pop() + self.stack.pop())
                    case '-':
                        self.stack.push(self.stack.pop(-2) - self.stack.pop())
                    case '*':
                        self.stack.push(self.stack.pop() * self.stack.pop())
                    case '/':
                        self.stack.push(self.stack.pop(-2) // self.stack.pop())
                    case '%':
                        self.stack.push(self.stack.pop(-2) % self.stack.pop())
                    case '!':
                        self.stack.push(int(not self.stack.pop()))
                    case '`':
                        self.stack.push(int(self.stack.pop() < self.stack.pop()))
                    case '>':
                        self.direction = Direction.RIGHT
                    case '<':
                        self.direction = Direction.LEFT
                    case '^':
                        self.direction = Direction.UP
                    case 'v':
                        self.direction = Direction.DOWN
                    case '?':
                        self.direction = Direction(randint(0, 3))
                    case '_':
                        self.direction = Direction(2 * bool(self.stack.pop()))
                    case '|':
                        self.direction = Direction(3 - 2 * bool(self.stack.pop()))
                    case '[':
                        self.direction += 1
                    case ']':
                        self.direction -= 1
                    case '"':
                        self.string = True
                    case ':':
                        if len(self.stack):
                            self.stack.push(self.stack[-1])
                    case '\\':
                        if len(self.stack) > 1:
                            self.stack.push(self.stack.pop(-2))
                    case '$':
                        self.stack.pop()
                    case '.':
                        print(str(self.stack.pop()) + ' ', end='', file=self.output)
                    case ',':
                        print(chr(self.stack.pop()), end='', file=self.output)
                    case '#':
                        self.advance()
                    case 'p':
                        self[self.stack.pop(-2), self.stack.pop()] = self.stack.pop(-3)
                    case 'g':
                        self.stack.push(self[self.stack.pop(-2), self.stack.pop()])
                    case '&':
                        self.stack.push(int(self.input()))
                    case '~':
                        self.stack.push(ord(self.input()))
                    case '@':
                        self.terminated = True
                    case ' ':
                        pass
                    case op:
                        self.stack.append(int(op))
            else:
                raise OperatorException(self.op)
            self.advance()
            if not (not self.string and self.op == ord(' ')):
                m += 1
                self.steps += 1
        return self


def main():
    parser = ArgumentParser(description='Display info and save as tif')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('file', help='funge code file', nargs='?')
    group.add_argument('-s', '--string', help='funge code string', default=None)
    parser.add_argument('-v', '--version', help='funge version: b93, b98', type=str, default=None)
    parser.add_argument('-d', '--debug', help='debug, steps / second, 0: continue on key press', type=float, default=-1)
    parser.add_argument('-i', '--inputs', help='inputs for when befunge asks for it', nargs='*')
    args = parser.parse_args()
    if args.file:
        befunge = Befunge.from_file(args.file, args.version, args.inputs)
    else:
        befunge = Befunge(args.string, args.version, args.inputs)

    if args.debug < 0:
        befunge.run()
    else:
        befunge.debug(args.debug)
