"""Header sanity checks that catch a bad build/patch before it becomes a
silent runtime crash — surfaced to the uploader as a warning, not a rejection."""
from __future__ import annotations

import struct


def md_header_warning(system_key: str, data: bytes) -> str | None:
    """Genesis/Mega Drive: the header's ROM end address (0x1A4-0x1A7) tells the
    cartridge memory map where the ROM stops. A patcher that grows the file
    (Korean translation, hack) without bumping this field leaves the tail of
    the ROM unmapped — genesis_plus_gx can crash/hang once code jumps past the
    declared end. Catch the mismatch here, at upload time."""
    if system_key != "md" or len(data) < 0x1A8:
        return None
    declared_size = struct.unpack(">I", data[0x1A4:0x1A8])[0] + 1
    if declared_size == len(data):
        return None
    return (f"헤더에 적힌 ROM 크기({declared_size:#x})가 실제 파일 크기({len(data):#x})와 달라요 — "
            "패치 과정에서 헤더가 안 갱신된 것 같습니다. 에뮬레이터에서 크래시/멈춤이 발생할 수 있어요.")
