from typing import Optional

class LZ4BlockError(Exception): ...

def compress(
    source: bytes,
    mode: str = ...,
    acceleration: int = ...,
    compression: int = ...,
    store_size: bool = ...,
    return_bytearray: bool = ...,
) -> bytes: ...

def decompress(
    source: bytes,
    uncompressed_size: int = ...,
    return_bytearray: bool = ...,
    dict: Optional[bytes] = ...,
) -> bytes: ...
