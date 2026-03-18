"""
Deterministic YAML serialization.

Ensures identical inputs always produce byte-identical YAML output by:
- Sorting all dictionary keys alphabetically
- Using consistent formatting (no flow style)
- Normalizing whitespace

Usage:
    from shared.utils.deterministic_yaml import ordered_dump, ordered_load

    data = {"z_key": 1, "a_key": 2, "nested": {"b": 3, "a": 4}}
    yaml_str = ordered_dump(data)
    # Output always has keys sorted: a_key, nested.a, nested.b, z_key
"""

from collections import OrderedDict

import yaml


class _OrderedDumper(yaml.SafeDumper):
    """YAML dumper that sorts dictionary keys for deterministic output."""
    pass


def _dict_representer(dumper, data):
    return dumper.represent_mapping(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        sorted(data.items()),
    )


_OrderedDumper.add_representer(dict, _dict_representer)
_OrderedDumper.add_representer(OrderedDict, _dict_representer)


def ordered_dump(data, stream=None, **kwargs):
    """Dump data to YAML with deterministic key ordering.

    Same inputs will always produce the same output string.
    """
    kwargs.setdefault("default_flow_style", False)
    kwargs.setdefault("sort_keys", True)
    kwargs.setdefault("allow_unicode", True)
    return yaml.dump(data, stream, Dumper=_OrderedDumper, **kwargs)


def ordered_load(stream):
    """Load YAML, preserving insertion order."""
    return yaml.safe_load(stream)
