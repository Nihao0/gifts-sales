"""Low-level TL serialization helpers."""
import struct

VECTOR_CID = b"\x15\xc4\xb5\x1c"


def pack_int(v: int) -> bytes:
    return struct.pack("<i", v)


def pack_uint(v: int) -> bytes:
    return struct.pack("<I", v)


def pack_long(v: int) -> bytes:
    return struct.pack("<q", v)


def pack_bool(v: bool) -> bytes:
    # boolTrue  = 0x997275b5
    # boolFalse = 0xbc799737
    return b"\xb5\x75\x72\x99" if v else b"\x37\x97\x79\xbc"


def serialize_bytes(data: str | bytes) -> bytes:
    """TL bytes/string serialiser (length-prefixed, 4-byte aligned)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    length = len(data)
    if length <= 253:
        header = bytes([length])
        padding = (-(length + 1)) % 4
    else:
        header = b"\xfe" + struct.pack("<I", length)[:3]
        padding = (-length) % 4
    return header + data + b"\x00" * padding


def pack_vector(items: list, serialize_item) -> bytes:
    return VECTOR_CID + pack_int(len(items)) + b"".join(serialize_item(x) for x in items)
