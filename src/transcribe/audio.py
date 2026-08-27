"""Detecting whether anything is currently using an audio input device.

macOS exposes this through CoreAudio's ``kAudioDevicePropertyDeviceIsRunningSomewhere``,
which is the same signal the menu-bar microphone indicator uses. It works for
any application, so a browser tab in Google Meet counts as much as Zoom, and it
needs no microphone permission: reading the property is not listening.

The point of this module is to answer "is a call happening" without having to
recognise every conferencing app.
"""

import ctypes
import ctypes.util

# Virtual and loopback devices that are routinely "running" whether or not a
# human is in a meeting, and would otherwise trigger recording constantly.
DEFAULT_IGNORED_DEVICES = (
    "steam streaming",
    "blackhole",
    "loopback",
    "soundflower",
    "aggregate",
    "multi-output",
    "zoomaudiodevice",
    "obs virtual",
    "krisp",
)

_SYSTEM_OBJECT = 1
_UTF8 = 0x08000100


def _fourcc(code):
    """CoreAudio selectors are four-character codes packed into a uint32."""
    return int.from_bytes(code.encode(), "big")


_PROP_DEVICES = _fourcc("dev#")
_PROP_RUNNING_SOMEWHERE = _fourcc("gone")
_PROP_STREAMS = _fourcc("stm#")
_PROP_NAME = _fourcc("lnam")
_SCOPE_GLOBAL = _fourcc("glob")
_SCOPE_INPUT = _fourcc("inpt")


class _Address(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32),
    ]


class AudioUnavailable(RuntimeError):
    """Raised when CoreAudio cannot be reached (non-macOS, or a load failure)."""


_frameworks = {}


def _load():
    """Load CoreAudio and CoreFoundation once."""
    if not _frameworks:
        core_audio = ctypes.util.find_library("CoreAudio")
        core_foundation = ctypes.util.find_library("CoreFoundation")
        if not core_audio or not core_foundation:
            raise AudioUnavailable("CoreAudio is only available on macOS")
        _frameworks["ca"] = ctypes.CDLL(core_audio)
        _frameworks["cf"] = ctypes.CDLL(core_foundation)
    return _frameworks["ca"], _frameworks["cf"]


def _property_size(obj, selector, scope):
    ca, _ = _load()
    address = _Address(selector, scope, 0)
    size = ctypes.c_uint32(0)
    status = ca.AudioObjectGetPropertyDataSize(
        ctypes.c_uint32(obj), ctypes.byref(address), 0, None, ctypes.byref(size)
    )
    return size.value if status == 0 else 0


def _property(obj, selector, scope, ctype):
    ca, _ = _load()
    address = _Address(selector, scope, 0)
    size = ctypes.c_uint32(ctypes.sizeof(ctype))
    value = ctype()
    status = ca.AudioObjectGetPropertyData(
        ctypes.c_uint32(obj),
        ctypes.byref(address),
        0,
        None,
        ctypes.byref(size),
        ctypes.byref(value),
    )
    return value if status == 0 else None


def device_name(device_id):
    """Return a device's human-readable name."""
    ca, cf = _load()
    address = _Address(_PROP_NAME, _SCOPE_GLOBAL, 0)
    size = ctypes.c_uint32(ctypes.sizeof(ctypes.c_void_p))
    ref = ctypes.c_void_p()
    status = ca.AudioObjectGetPropertyData(
        ctypes.c_uint32(device_id),
        ctypes.byref(address),
        0,
        None,
        ctypes.byref(size),
        ctypes.byref(ref),
    )
    if status != 0 or not ref:
        return f"device {device_id}"

    cf.CFStringGetCStringPtr.restype = ctypes.c_char_p
    pointer = cf.CFStringGetCStringPtr(ref, _UTF8)
    if pointer:
        return pointer.decode("utf-8", "replace")
    buffer = ctypes.create_string_buffer(512)
    if cf.CFStringGetCString(ref, buffer, 512, _UTF8):
        return buffer.value.decode("utf-8", "replace")
    return f"device {device_id}"


def input_devices():
    """Return the ids of every audio device that has an input stream."""
    ca, _ = _load()
    size = _property_size(_SYSTEM_OBJECT, _PROP_DEVICES, _SCOPE_GLOBAL)
    count = size // ctypes.sizeof(ctypes.c_uint32)
    if count == 0:
        return []

    devices = (ctypes.c_uint32 * count)()
    address = _Address(_PROP_DEVICES, _SCOPE_GLOBAL, 0)
    total = ctypes.c_uint32(size)
    status = ca.AudioObjectGetPropertyData(
        ctypes.c_uint32(_SYSTEM_OBJECT),
        ctypes.byref(address),
        0,
        None,
        ctypes.byref(total),
        devices,
    )
    if status != 0:
        return []
    # A device with no input stream is an output; it can never mean "on a call".
    return [d for d in devices if _property_size(d, _PROP_STREAMS, _SCOPE_INPUT) > 0]


def is_ignored(name, ignored=DEFAULT_IGNORED_DEVICES):
    """True when a device name matches an ignore pattern, case-insensitively."""
    lowered = name.lower()
    return any(pattern.lower() in lowered for pattern in ignored)


def active_input_devices(ignored=DEFAULT_IGNORED_DEVICES):
    """Return the names of input devices currently in use.

    Virtual and loopback devices are filtered out: several of them report as
    running whenever their host application is open, which has nothing to do
    with whether a meeting is happening.
    """
    active = []
    for device_id in input_devices():
        running = _property(device_id, _PROP_RUNNING_SOMEWHERE, _SCOPE_GLOBAL, ctypes.c_uint32)
        if not (running and running.value):
            continue
        name = device_name(device_id)
        if not is_ignored(name, ignored):
            active.append(name)
    return active


def microphone_in_use(ignored=DEFAULT_IGNORED_DEVICES):
    """True when something is capturing from a real input device."""
    try:
        return bool(active_input_devices(ignored))
    except AudioUnavailable:
        return False
