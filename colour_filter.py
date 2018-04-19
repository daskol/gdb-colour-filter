#!/usr/bin/env gdb
#   encoding: utf8
#   file: colour_filter.py

from typing import Iterator, Text

from gdb import parameter as get_parameter
from gdb import Frame, frame_filters, execute
from gdb.FrameDecorator import FrameDecorator


SCREEN_WIDTH = 160


class FrameColorizer(FrameDecorator):
    """FrameColorizer repeats all actions to get all common frame attribute and
    then spices a bit output with colours. Format of output string is following.

    #<depth> <address> in <function> (<frame_args>) at <filename>[:<line>]

    Notes: There is not special support Frame.elided() property.
    """

    def __init__(self, *args, depth=0, **kwargs):
        super(FrameColorizer, self).__init__(*args, **kwargs)

        self._depth = depth
        self.frame = super(FrameColorizer, self).inferior_frame()

    def __str__(self):
        is_print_address = get_parameter('print address')

        part1 = self.depth()
        part2 = self.function() + ' \033[1;37m(' + self.frame_args() + ')\033[0m'
        part3 = self.filename() + self.line()

        if is_print_address:
            part1 += '  ' + self.address() + ' in '
        else:
            part1 += ' '

        parts = part1 + part2 + ' at ' + part3

        if len(parts) > self.get_screen_width():
            shift_width = int(self.length(part1)) - 1
            shift_width -= 3 * int(is_print_address)  # compensate ' in ' part
            value = part1 + part2 + '\n'
            value += ' ' * shift_width + ' at ' + part3
        else:
            value = parts

        return value

    def address(self):
        address = super(FrameColorizer, self).address()
        return '\033[1;30m0x%016x\033[0m' % address

    def depth(self):
        return '\033[1;37m#%-3d\033[0m' % self._depth

    def filename(self):
        filename = super(FrameColorizer, self).filename()
        return '\033[0;36m%s\033[0m' % filename

    def frame_args(self):
        try:
            block = self.frame.block()
        except RuntimeError:
            block = None

        while block is not None:
            if block.function is not None:
                break
            block = block.superblock

        if block is None:
            return ''

        args = []

        for sym in block:
            if not sym.is_argument:
                continue;
            val = sym.value(self.frame)
            arg = '%s=%s' % (sym, val) if str(val) else str(sym)
            args.append(arg)

        return ', '.join(args)

    def function(self):
        func = super(FrameColorizer, self).function()

        # GDB could somehow resolve function name by its address.
        # See details here https://cygwin.com/ml/gdb/2017-12/msg00013.html
        if isinstance(func, int):
            # Here we have something like
            # > raise + 272 in section .text of /usr/lib/libc.so.6
            # XXX: gdb.find_pc_line
            symbol = gdb.execute('info symbol 0x%016x' % func, False, True)

            # But here we truncate layout in binary
            # > raise + 272
            name = symbol[:symbol.find('in section')].strip()

            # Check if we in format
            # > smthing + offset
            parts = name.rsplit(' ', 1)
            # > raise
            if len(parts) == 1:
                return name

            try:
                offset = hex(int(parts[1]))
            except ValueError:
                return name

            return '\033[1;34m' + parts[0] + ' ' + offset + '\033[0m'
        else:
            return '\033[1;34m' + func + '\033[0m'

    def get_screen_width(self):
        """Get screen width from GDB. Source format is following
        > Number of characters gdb thinks are in a line is 174.
        """
        # TODO: get screen width
        #string = gdb.execute('show width', True, False)
        #_, last = string.rsplit(' ', 1)
        #return int(last[:-1])
        return SCREEN_WIDTH

    def line(self):
        value = super(FrameColorizer, self).line()
        return '\033[0;35m:%d\033[0m' % value if value else ''

    @staticmethod
    def length(colored_string):
        """This function calculates length of string with terminal control
        sequences.
        """
        start = 0
        term_seq_len = 0

        while True:
            begin = colored_string.find('\033', start)

            if begin == -1:
                break

            end = colored_string.find('m', begin)

            if end == -1:
                end = len(s)

            term_seq_len += end - begin + 1
            start = end

        return len(colored_string) - term_seq_len


class FilterProxy:
    """FilterProxy class keep ensures that frame iterator will be comsumed
    properly on the first and the sole call.
    """

    def __init__(self, frames: Iterator[Frame]):
        self.frames = (FrameColorizer(frame, depth=ix)
                       for ix, frame in enumerate(frames))

    def __iter__(self):
        return self

    def __next__(self):
        self.unroll_stack()
        raise StopIteration

    def unroll_stack(self):
        output = (str(frame) for frame in self.frames)
        print('\n'.join(output))


class ColourFilter:

    def __init__(self, name='backtrace-filter', priority=0, enabled=True):
        """Frame filter with the lower priority that consumes every frame and
        colouring output.

        :param name: The name of the filter that GDB will display.
        :param priority: The priority of the filter relative to other filters.
        :param enabled: A boolean that indicates whether this filter is enabled
        and should be executed.
        """
        self.name = name
        self.priority = priority
        self.enabled = enabled

        # Register this frame filter with the global frame_filters
        # dictionary.
        frame_filters[self.name] = self

    def filter(self, iters: Iterator[Frame]) -> Iterator[Frame]:
        return FilterProxy(iters)


ColourFilter()  # register colour filter forcibly
