"""Detecting whether anything is currently using a camera.

CoreMediaIO mirrors CoreAudio's property API, so this is the video twin of
``audio.py``: ``kCMIODevicePropertyDeviceIsRunningSomewhere`` is what the green
camera indicator and tools like OverSight read. It needs no camera permission,
because checking is not capturing.

Camera activity is the highest-precision meeting signal there is. Almost nothing
except a video call turns your camera on, whereas a microphone gets used by
dictation, voice notes, and Siri. Its weakness is recall: plenty of real
meetings happen with the camera off.
"""

import ctypes
import ctypes.util

# Virtual cameras that report as running whenever their host app is open.
DEFAULT_IGNORED_CAMERAS = (
    "obs virtual",
    "screen",
    "desk view",
    "snap camera",
    "mmhmm",
    "camo",
)

_SYSTEM_OBJECT = 1
_UTF8 = 0x08000100


def _fourcc(code):
    return int.from_bytes(code.encode(), "big")


_PROP_DEVICES = _fourcc("dev#")
_PROP_RUNNING_SOMEWHERE = _fourcc("gone")
_PROP_NAME = _fourcc("lnam")
_SCOPE_GLOBAL = _fourcc("glob")


class _Address(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32),
    ]


class CameraUnavailable(RuntimeError):
    """Raised when CoreMediaIO cannot be reached (non-macOS, or a load failure)."""


_frameworks = {}


def _load():
    if not _frameworks:
        cmio = ctypes.util.find_library("CoreMediaIO")
        cf = ctypes.util.find_library("CoreFoundation")
        if not cmio or not cf:
            raise CameraUnavailable("CoreMediaIO is only available on macOS")
        _frameworks["cmio"] = ctypes.CDLL(cmio)
        _frameworks["cf"] = ctypes.CDLL(cf)
    return _frameworks["cmio"], _frameworks["cf"]


def _property_size(obj, selector):
    cmio, _ = _load()
    address = _Address(selector, _SCOPE_GLOBAL, 0)
    size = ctypes.c_uint32(0)
    status = cmio.CMIOObjectGetPropertyDataSize(
        ctypes.c_uint32(obj), ctypes.byref(address), 0, None, ctypes.byref(size)
    )
    return size.value if status == 0 else 0


def _property(obj, selector, ctype):
    # CMIOObjectGetPropertyData takes a "data used" out-parameter that its
    # CoreAudio counterpart does not, so the signatures are not interchangeable.
    cmio, _ = _load()
    address = _Address(selector, _SCOPE_GLOBAL, 0)
    value = ctype()
    used = ctypes.c_uint32(0)
    status = cmio.CMIOObjectGetPropertyData(
        ctypes.c_uint32(obj),
        ctypes.byref(address),
        0,
        None,
        ctypes.c_uint32(ctypes.sizeof(ctype)),
        ctypes.byref(used),
        ctypes.byref(value),
    )
    return value if status == 0 else None


def camera_name(device_id):
    """Return a camera's human-readable name."""
    cmio, cf = _load()
    address = _Address(_PROP_NAME, _SCOPE_GLOBAL, 0)
    ref = ctypes.c_void_p()
    used = ctypes.c_uint32(0)
    status = cmio.CMIOObjectGetPropertyData(
        ctypes.c_uint32(device_id),
        ctypes.byref(address),
        0,
        None,
        ctypes.c_uint32(ctypes.sizeof(ctypes.c_void_p)),
        ctypes.byref(used),
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


def cameras():
    """Return the ids of every camera device known to the system."""
    cmio, _ = _load()
    size = _property_size(_SYSTEM_OBJECT, _PROP_DEVICES)
    count = size // ctypes.sizeof(ctypes.c_uint32)
    if count == 0:
        return []

    devices = (ctypes.c_uint32 * count)()
    address = _Address(_PROP_DEVICES, _SCOPE_GLOBAL, 0)
    used = ctypes.c_uint32(0)
    status = cmio.CMIOObjectGetPropertyData(
        ctypes.c_uint32(_SYSTEM_OBJECT),
        ctypes.byref(address),
        0,
        None,
        ctypes.c_uint32(size),
        ctypes.byref(used),
        devices,
    )
    return list(devices) if status == 0 else []


def is_ignored(name, ignored=DEFAULT_IGNORED_CAMERAS):
    """True when a camera name matches an ignore pattern, case-insensitively."""
    lowered = name.lower()
    return any(pattern.lower() in lowered for pattern in ignored)


def active_cameras(ignored=DEFAULT_IGNORED_CAMERAS):
    """Return the names of cameras currently in use."""
    active = []
    for device_id in cameras():
        running = _property(device_id, _PROP_RUNNING_SOMEWHERE, ctypes.c_uint32)
        if not (running and running.value):
            continue
        name = camera_name(device_id)
        if not is_ignored(name, ignored):
            active.append(name)
    return active


def camera_in_use(ignored=DEFAULT_IGNORED_CAMERAS):
    """True when something is capturing from a real camera."""
    try:
        return bool(active_cameras(ignored))
    except CameraUnavailable:
        return False
