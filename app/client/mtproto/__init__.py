"""
Register custom TL types so Telethon's reader can deserialise responses
that contain constructor IDs unknown to the bundled layer.

Import this module before making any MTProto calls.
"""
from telethon.tl.alltlobjects import tlobjects

from .types import StarsAmount

# Each entry maps constructor_id → class with a from_reader classmethod.
# Telethon's BinaryReader falls back to tlobjects[cid].from_reader(reader)
# when it encounters an unknown constructor ID.
_CUSTOM_TYPES = [
    StarsAmount,
]

for _t in _CUSTOM_TYPES:
    tlobjects[_t.CONSTRUCTOR_ID] = _t
