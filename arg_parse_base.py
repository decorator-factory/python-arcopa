from dataclasses import dataclass
from functools import wraps
from typing import (
    Tuple, Dict, Set,
    TypeVar, Generic,
    Iterator, Iterable,
    Any, Callable,
    Type
)
import re

from typing import Optional


T = TypeVar("T", covariant=True)
U = TypeVar("U", covariant=True)


@dataclass(frozen=True)
class Match(Generic[T]):
    converted: T
    captured: str
    rest: str

    def replace_converted(self, converted: U) -> "Match[U]":
        return Match(converted, captured=self.captured, rest=self.rest)


def _match_description():
    pattern = Sequence([Integer(), Integer()])
    a_match = pattern.match("42 15 hello")
    assert a_match == Match([42, 15], "42 15", " hello")


# NON_CAPTURING is a special constant that will be ignored by Sequence
# when constructing a converted value
class _NonCapturingType:
    def __repr__(self):
        return "NON_CAPTURING"

NON_CAPTURING = _NonCapturingType()

DEBUG = False
_CURRENT_DEPTH = 0 # used for pretty-printing the parsing attempt tree

_WITH_LOGGER_ATTACHED: Set[Type["Spec"]] = set()


@dataclass
class Spec:
    def __new__(cls, *args):
        if DEBUG and cls not in _WITH_LOGGER_ATTACHED:
            # pretty print the attempt to parse a string
            @wraps(cls.match)
            def new_match(self, string: str, *args, **kwargs):
                global _CURRENT_DEPTH
                _CURRENT_DEPTH += 1

                print(
                    " |"
                    + "    " * _CURRENT_DEPTH
                    + f"... {self}.match({string!r})"
                    + f"*{args}" * bool(args)
                    + f"**{kwargs})" * bool(kwargs)
                )

                for m in self._raw_match(string, *args, **kwargs):
                    print(" |" + "    " * _CURRENT_DEPTH, ">", m)
                    yield m

                _CURRENT_DEPTH -= 1

            cls._raw_match = cls.match
            cls.match = new_match # type: ignore
            _WITH_LOGGER_ATTACHED.add(cls)

        return object.__new__(cls)


    def match(self, string: str) -> Iterator[Match[Any]]:
        """
        This method returns a generator that enumrates
        all possible matches for this spec.

        Sequence([
            Either([String(), Integer()],
            Either([String(), Integer()]
        )]).match("25 666") ->
            ["25", "666"],
            ["25", 666],
            [25, "666"],
            [25, 666]
        """
        raise NotImplementedError

    def first_match(self, string: str) -> Optional[Match[Any]]:
        """
        Return the first match, discarding all other matches
        if the result is ambiguous. If no match is found, return None.
        """

        try:
            return next(self.match(string))
        except StopIteration:
            return None

    def fmap(self, fn: Callable[[Any], "Spec"]) -> "Spec":
        """
        Transform the contents of a spec.

        Roughly speaking, MySpec(arg).fmap(f) = MySpec(f(arg)).

        Example: Sequence([a, b, c]).fmap(f) = Sequence([f(a), f(b), f(c)])
        """

        return self

    # def __repr__(self):
    #     return f"{self.__class__.__qualname__}(...)"


@dataclass
class End(Spec):
    """
    Succeed only if we're at the end of input (possibly with some whitespace)
    """

    def match(self, string: str):
        if re.match(r'^\s*$', string):
            yield Match(
                NON_CAPTURING,
                captured=string,
                rest=""
            )


@dataclass
class Exact(Spec):
    """
    Only match a given string
    """

    exact: str

    def match(self, string: str):
        escaped = re.escape(self.exact)
        if rematch := re.match(rf'^\s*{escaped}', string):
            _start, end = rematch.span()
            yield Match(
                self.exact,
                captured=string[:end],
                rest=string[end:]
            )


@dataclass
class Transform(Spec):
    """
    Transform the `converted` value using a function
    """

    spec: Spec
    transform_function: Callable

    def fmap(self, fn):
        return Transform(fn(self.spec), self.transform_function)

    def match(self, string: str):
        for m in self.spec.match(string):
            yield m.replace_converted(self.transform_function(m.converted))


@dataclass
class NonCapturing(Spec):
    """
    Match the subspec, but discard its conversion result
    """
    subspec: Spec

    def fmap(self, fn):
        return NonCapturing(fn(self.subspec))

    def match(self, string: str):
        for a_match in self.subspec.match(string):
            yield a_match.replace_converted(NON_CAPTURING)


@dataclass
class Integer(Spec):
    def match(self, string: str):
        if rematch := re.match(r'^\s*([+-]?[0-9]+)(?=\D|$)', string):
            _start, end = rematch.span()
            yield Match(
                int(rematch[1]),
                captured=string[:end],
                rest=string[end:]
            )


@dataclass
class Word(Spec):
    def match(self, string) -> Iterator[Match[str]]:
        if rematch := re.match(r'^\s*(\S+)(?=\s|$)', string):
            start, end = rematch.span()
            yield Match(
                rematch[1],
                captured=string[:end],
                rest=string[end:]
            )


@dataclass
class String(Spec):
    """
    Match anything, really. Use with caution.
    """

    def match(self, string) -> Iterator[Match[str]]:
        for i in range(len(string)-1, 0, -1):
            left, right = string[:i], string[i:]
            yield Match(
                left,
                captured=left,
                rest=right
            )


@dataclass
class StringWithout(Spec):
    """
    Match anything except for any of the given characters.
    """

    exclude: set


    def __post_init__(self):
        self.exclude = set(self.exclude)

    def match(self, string: str):
        if string == "":
            return

        for first_bad_index, char in enumerate(string):
            if char in self.exclude:
                break

        for i in range(1, first_bad_index+1): # type: ignore
            left, right = string[:i], string[i:]
            yield Match(
                left,
                captured=left,
                rest=right
            )


@dataclass
class Either(Spec):
    def __init__(self, options: Iterable[Spec]):
        self.options = list(options)

    def fmap(self, fn):
        return Either(fn(option) for option in self.options)

    def match(self, string: str):
        for spec in self.options:
            yield from spec.match(string)

    def __repr__(self):
        return f"EitherSpec({'|'.join(map(str,self.options))})"


@dataclass
class Sequence(Spec):
    def __init__(self, sequence: Iterable[Spec]):
        self.sequence = list(sequence)

    def fmap(self, fn):
        return Sequence(fn(spec) for spec in self.sequence)

    def breadth_first(self, string: str):
        # Traverse the tree of possible matches breadth-first

        # `current_leaves` is a list containing all the leaves forming
        # a horizontal layer of each iteration (since each iteration of
        # the `while` loop corresponds to a specific tree depth level)

        #                                   current_leaves:
        #                       root     -> [root]
        #                     /     \
        #                    a       b   -> [a, b]
        #                  /  \      |
        #                a1   a2     b1  -> [a1, a2, b1]
        current_leaves = [[m] for m in self.sequence[0].match(string)]

        children = list(reversed(self.sequence))
        children.pop()

        while current_leaves and children:
            child = children.pop()
            new_leaves = []
            for leaf in current_leaves:
                thenceforth_string = leaf[-1].rest
                new_leaves.extend(
                    [*leaf, m] for m in child.match(thenceforth_string) if m
                )
            current_leaves = new_leaves

        for subtree in current_leaves:
            last_match = subtree[-1]

            # captured string of a sequence is the sum of strings captured
            # by each sequence element
            captured = ''.join(m.captured for m in subtree)

            converted = [
                m.converted for m in subtree
                if m.converted is not NON_CAPTURING
            ]

            yield Match(
                converted,
                captured=captured,
                rest=last_match.rest
            )

    def depth_first(self, string: str) -> Iterator[Match[Any]]:
        # TODO: implement depth-first search that will be enabled
        # once a certain threshold is reached in breadth-first search
        # or something like that.
        raise NotImplementedError

    def match(self, string: str, *, greedy=False) -> Iterator[Match[list]]:
        # An empty sequence is a valid spec
        if self.sequence == []:
            yield Match(
                [],
                captured="",
                rest=string
            )

        if greedy:
            yield from self.depth_first(string)
        else:
            yield from self.breadth_first(string)


@dataclass
class ZeroOrMore(Spec):
    def __init__(self, subspec: Spec):
        self.subspec = subspec

    def fmap(self, fn):
        return ZeroOrMore(fn(self.subspec))

    def traverse(self, string: str, history: Tuple[Match[Any], ...] = ()):
        # attempt to match (), (spec,), (spec, spec), (spec, spec, spec), ...
        yield history
        for m in self.subspec.match(string):
            yield from self.traverse(m.rest, history + (m,))

    def match(self, string):
        for history in self.traverse(string):
            captured = ''.join(m.captured for m in history)

            converted = [
                m.converted for m in history
                if m.converted is not NON_CAPTURING
            ]

            if history == ():
                rest = string
            else:
                rest = history[-1].rest

            yield Match(
                converted,
                captured=captured,
                rest=rest
            )


@dataclass
class OneOrMore(Spec):
    def __init__(self, subspec: Spec):
        self.subspec = subspec

    def fmap(self, fn):
        return OneOrMore(fn(self.subspec))

    def match(self, string: str) -> Iterator[Match[list]]:
        # It's exactly like ZeroOrMore, but without the empty match
        for m in ZeroOrMore(self.subspec).match(string):
            if m.converted != []:
                yield m


@dataclass
class NamedOr(Spec):
    def __init__(self, options_dict: Dict[str, Spec]):
        self.options_dict = options_dict  # {name: spec}

    def fmap(self, fn):
        return NamedOr({
            name: fn(spec) for name, spec in self.options_dict.items()
        })

    def match(self, string):
        for name, spec in self.options_dict.items():
            for m in spec.match(string):
                yield m.replace_converted({name: m.converted})


@dataclass
class NamedAnd(Spec):
    def __init__(self, sequence_dict: Dict[str, Spec]):
        self.sequence_dict = sequence_dict  # {name: spec}

    def fmap(self, fn):
        return NamedAnd({
            name: fn(spec) for name, spec in self.sequence_dict.items()
        })

    def match(self, string):
        seq = Sequence(self.sequence_dict.values())
        # match a sequence of specs
        # and then just assign keys to the
        # matched objects
        for m in seq.match(string):
            yield m.replace_converted({
                name: captured
                for (name, captured)
                in zip(
                    self.sequence_dict.keys(),
                    m.converted
                )
            })
