from typing import List, Dict, Union, Type, Any, Iterable

import arg_parse_base as _base
from arg_parse_base import Spec

def _convert(spec):
    if isinstance(spec, list):
        return _base.Sequence(spec).fmap(_convert)

    elif isinstance(spec, dict):
        return _base.NamedAnd(spec).fmap(_convert)

    elif isinstance(spec, str):
        return _base.NonCapturing(_base.Exact(spec)).fmap(_convert)

    elif isinstance(spec, _base.Spec):
        return spec.fmap(_convert)

    elif spec == int:
        return _base.Integer()

    elif spec == str:
        return _base.String()

    else:
        raise TypeError("Invalid spec")


ConvenientSpec =\
    Union[
        List[Any],
        Type[int],
        Type[str],
    ]


def ignore(spec: ConvenientSpec):
    return _base.NonCapturing(spec) # type: ignore


word = _base.Word()


def without(excluded_characters: Iterable[str]):
    return _base.StringWithout(excluded_characters)


def literal(string: str):
    return _base.Exact(string)


def one_or_more(spec: ConvenientSpec):
    return _base.OneOrMore(spec) # type: ignore


def zero_or_more(spec: ConvenientSpec):
    return _base.OneOrMore(spec) # type: ignore


def either(*specs: ConvenientSpec):
    return _base.Either(specs) # type: ignore


def tag(**mapping: Dict[str, ConvenientSpec]):
    return _base.NamedOr(mapping) # type: ignore


def record(**mapping: Dict[str, ConvenientSpec]):
    return _base.NamedOr(mapping) # type: ignore


def transform(spec: ConvenientSpec, fn):
    return _base.Transform(spec, fn) # type: ignore


def match(pattern, string):
    if isinstance(pattern, list):
        pattern = pattern + [_base.End()]
    else:
        pattern = [pattern, _base.End()]

    return _convert(pattern).first_match(string)
