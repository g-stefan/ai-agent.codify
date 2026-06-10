# MCP Desktop
# SPDX-FileCopyrightText: 2026 Grigore Stefan <g_stefan@yahoo.com>
# SPDX-License-Identifier: Apache-2.0

import re
import os
import sys
import time
import uvicorn
import argparse
import base64
import subprocess
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from typing import List, Any, Optional
from mcp.types import ImageContent
from pathlib import Path

# Check if PIL/Pillow is available for window grabbing
try:
    from PIL import ImageGrab, Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# --- OS Check ---
IS_WINDOWS = sys.platform.startswith("win")

# --- Windows Ctypes API Setup ---
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    
    # Structure definitions
    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG)
        ]
        
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p) # Using c_void_p for ULONG_PTR is highly portable and prevents pointer corruption
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD)
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_void_p) # Using c_void_p for ULONG_PTR
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("ki", KEYBDINPUT),
            ("mi", MOUSEINPUT),
            ("hi", HARDWAREINPUT)
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("u", INPUT_UNION)
        ]

    # Constants
    INPUT_KEYBOARD = 1
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_SCANCODE = 0x0008
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    # --- Robust 32/64-bit Safe Ctypes Declarations ---
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]

    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]

    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]

    user32.IsIconic.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]

    user32.ShowWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]

    user32.SetActiveWindow.restype = wintypes.HWND
    user32.SetActiveWindow.argtypes = [wintypes.HWND]

    user32.SetFocus.restype = wintypes.HWND
    user32.SetFocus.argtypes = [wintypes.HWND]

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetForegroundWindow.argtypes = []

    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]

    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, 
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, 
        wintypes.UINT
    ]

    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]

    user32.ClientToScreen.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]

    user32.GetClientRect.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]

    user32.SetCursorPos.restype = wintypes.BOOL
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

    user32.mouse_event.restype = None
    user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]

    user32.keybd_event.restype = None
    user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_void_p]

    user32.SendInput.restype = wintypes.UINT
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]

    user32.VkKeyScanW.restype = ctypes.c_short
    user32.VkKeyScanW.argtypes = [ctypes.c_wchar]

    user32.MapVirtualKeyW.restype = wintypes.UINT
    user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]


# --- Pre-parse --env-base ---
pre_parser = argparse.ArgumentParser(add_help=False)
pre_parser.add_argument("--env-base", type=str, default="")
pre_parser.add_argument("--tool-prefix", type=str, default="desktop_")
pre_parser.add_argument("--mcp-name", type=str, default="Desktop")
pre_args, _ = pre_parser.parse_known_args()

ENV_PREFIX = pre_args.env_base
TOOL_PREFIX = pre_args.tool_prefix
MCP_NAME = pre_args.mcp_name

def get_env_var(name: str, default: Any = None) -> Any:
    """Get an environment variable, optionally applying the env-base prefix."""
    if ENV_PREFIX:
        prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        env_key = f"{prefix}{name}"
    else:
        env_key = name
    return os.environ.get(env_key, default)


# Default desktop port is 48103 to avoid colliding with workspace server
PORT = int(get_env_var("PORT", "48103"))
WINDOW_NAME = get_env_var("WINDOW_NAME", "Desktop")

# --- Workspace Configuration (Aligned with mcp-server-workspace) ---
WORKSPACE_DIR = get_env_var("DIR", "Workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)


# --- Keyboard Mapping Configurations ---

# Mapping for non-character key values: (VirtualKeyCode, isExtendedKey)
KEY_MAP = {
    "enter": (0x0D, False),
    "tab": (0x09, False),
    "backspace": (0x08, False),
    "escape": (0x1B, False),
    "space": (0x20, False),
    "up": (0x26, True),
    "down": (0x28, True),
    "left": (0x25, True),
    "right": (0x27, True),
    "delete": (0x2E, True),
    "home": (0x24, True),
    "end": (0x23, True),
    "page_up": (0x21, True),
    "page_down": (0x22, True),
    "f1": (0x70, False),
    "f2": (0x71, False),
    "f3": (0x72, False),
    "f4": (0x73, False),
    "f5": (0x74, False),
    "f6": (0x75, False),
    "f7": (0x76, False),
    "f8": (0x77, False),
    "f9": (0x78, False),
    "f10": (0x79, False),
    "f11": (0x7A, False),
    "f12": (0x7B, False),
}

# Mapping for xdotool unix keys
UNIX_KEY_MAP = {
    "enter": "Return",
    "tab": "Tab",
    "backspace": "BackSpace",
    "escape": "Escape",
    "space": "space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "delete": "Delete",
    "home": "Home",
    "end": "End",
    "page_up": "Prior",
    "page_down": "Next",
    "f1": "F1",
    "f2": "F2",
    "f3": "F3",
    "f4": "F4",
    "f5": "F5",
    "f6": "F6",
    "f7": "F7",
    "f8": "F8",
    "f9": "F9",
    "f10": "F10",
    "f11": "F11",
    "f12": "F12"
}


# --- Helper Automation Functions ---

def get_safe_path(base_folder: str, user_path: str) -> Path:
    """
    Validates a path to ensure it cannot escape the specified base_folder
    using path traversal (e.g., '../').
    """
    base_dir = Path(base_folder).resolve()
    target_path = (base_dir / user_path).resolve()

    if not target_path.is_relative_to(base_dir):
        raise PermissionError(
            f"Security Error: Path traversal detected! '{user_path}' is outside the allowed directory."
        )

    if target_path == base_dir:
        raise IsADirectoryError(
            "Security Error: Target path cannot be the base directory itself."
        )

    return target_path


def run_command(args: List[str]) -> str:
    """Runs a shell command and returns output (for Unix fallbacks)."""
    res = subprocess.run(args, capture_output=True, text=True, check=True)
    return res.stdout.strip()


def find_window(window_name: str):
    """
    Finds a window by title pattern. First matches exact window titles,
    then matches partial/case-insensitive window titles.
    """
    if not IS_WINDOWS:
        raise OSError("Standard window enumeration is only implemented for Windows.")
        
    found_windows = []
    
    def callback(hwnd, extra):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                title = buffer.value
                if window_name.lower() in title.lower():
                    found_windows.append((hwnd, title))
        return True
        
    _enum_callback = WNDENUMPROC(callback)
    user32.EnumWindows(_enum_callback, 0)
    
    if not found_windows:
        raise ValueError(f"No visible window found containing '{window_name}' in its title.")
        
    # Exact case-sensitive match priority
    for hwnd, title in found_windows:
        if title == window_name:
            return hwnd, title
            
    # Exact case-insensitive match priority
    for hwnd, title in found_windows:
        if title.lower() == window_name.lower():
            return hwnd, title
            
    # Return first partial match
    return found_windows[0]


def activate_window(hwnd):
    """
    Brings the target window to the foreground, activates it, 
    and ensures it gains focus by utilizing a combination of robust Win32 techniques.
    """
    # 1. Restore the window if minimized, otherwise ensure it is shown
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9) # SW_RESTORE
    else:
        user32.ShowWindow(hwnd, 5) # SW_SHOW
    time.sleep(0.5) # Allow system to process show/restore painting

    # 2. We will attempt a few iterations to force foreground activation
    # in case of initial background application lock restrictions.
    for attempt in range(3):
        fore_hwnd = user32.GetForegroundWindow()
        if fore_hwnd == hwnd:
            # Already in foreground, make sure it has input focus
            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)
            break
            
        current_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        fore_thread_id = user32.GetWindowThreadProcessId(fore_hwnd, None)
        
        attached = False
        # Attach thread input to the foreground thread to bypass LockSetForegroundWindow locks
        if fore_thread_id != current_thread_id and fore_thread_id != 0:
            if user32.AttachThreadInput(current_thread_id, fore_thread_id, True):
                attached = True
                
        try:
            # Force the window to the top of Z-Order
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)
            
            # Request foreground focus
            user32.SetForegroundWindow(hwnd)
            
        finally:
            if attached:
                user32.AttachThreadInput(current_thread_id, fore_thread_id, False)
                
        # Reinforce with standard focus functions
        user32.BringWindowToTop(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
        
        # Allow focus state to settle briefly
        time.sleep(0.5)


def get_client_rect_screen(hwnd):
    """Returns the screen coordinates (left, top, right, bottom) of a window's client area."""
    rect = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    
    # Map top-left client coordinate (0,0) to screen coordinate space
    pt_top_left = POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt_top_left))
    
    # Map bottom-right client coordinate to screen coordinate space
    pt_bottom_right = POINT(width, height)
    user32.ClientToScreen(hwnd, ctypes.byref(pt_bottom_right))
    
    return (pt_top_left.x, pt_top_left.y, pt_bottom_right.x, pt_bottom_right.y)


def send_keyboard_text(text: str):
    """
    Types a unicode string character-by-character on Windows.
    Tries to map characters to virtual keys and types using physical scancodes (KEYEVENTF_SCANCODE).
    If a character cannot be mapped to the layout, it falls back gracefully to KEYEVENTF_UNICODE.
    """
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12  # Alt key
    
    # Pre-resolve modifier scan codes
    sc_shift = user32.MapVirtualKeyW(VK_SHIFT, 0)
    sc_ctrl = user32.MapVirtualKeyW(VK_CONTROL, 0)
    sc_alt = user32.MapVirtualKeyW(VK_MENU, 0)
    
    for char in text:
        res = user32.VkKeyScanW(char)
        
        # Fallback: If character is not present in layout, inject as Unicode
        if res == -1:
            code_units = char.encode('utf-16-le')
            for i in range(0, len(code_units), 2):
                val = int.from_bytes(code_units[i:i+2], 'little')
                
                # Key Down
                ki_down = KEYBDINPUT(wVk=0, wScan=val, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=None)
                inp_down = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_down))
                user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
                time.sleep(0.01)
                
                # Key Up
                ki_up = KEYBDINPUT(wVk=0, wScan=val, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
                inp_up = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_up))
                user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))
                time.sleep(0.015)
                
            time.sleep(0.025)
            continue
            
        # Deconstruct VK and Modifier requirements
        vk = res & 0xFF
        shift_state = (res >> 8) & 0xFF
        
        shift_needed = bool(shift_state & 1)
        ctrl_needed = bool(shift_state & 2)
        alt_needed = bool(shift_state & 4)
        
        # Get target key scan code
        sc = user32.MapVirtualKeyW(vk, 0)
        
        # Press Modifiers
        if shift_needed:
            ki = KEYBDINPUT(wVk=0, wScan=sc_shift, dwFlags=KEYEVENTF_SCANCODE, time=0, dwExtraInfo=None)
            user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki))), ctypes.sizeof(INPUT))
            time.sleep(0.005)
        if ctrl_needed:
            ki = KEYBDINPUT(wVk=0, wScan=sc_ctrl, dwFlags=KEYEVENTF_SCANCODE, time=0, dwExtraInfo=None)
            user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki))), ctypes.sizeof(INPUT))
            time.sleep(0.005)
        if alt_needed:
            ki = KEYBDINPUT(wVk=0, wScan=sc_alt, dwFlags=KEYEVENTF_SCANCODE, time=0, dwExtraInfo=None)
            user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki))), ctypes.sizeof(INPUT))
            time.sleep(0.005)
            
        # Press primary character
        ki_down = KEYBDINPUT(wVk=0, wScan=sc, dwFlags=KEYEVENTF_SCANCODE, time=0, dwExtraInfo=None)
        user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_down))), ctypes.sizeof(INPUT))
        time.sleep(0.01)
        
        # Release primary character
        ki_up = KEYBDINPUT(wVk=0, wScan=sc, dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
        user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_up))), ctypes.sizeof(INPUT))
        time.sleep(0.01)
        
        # Release modifiers (in reverse order)
        if alt_needed:
            ki = KEYBDINPUT(wVk=0, wScan=sc_alt, dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
            user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki))), ctypes.sizeof(INPUT))
            time.sleep(0.005)
        if ctrl_needed:
            ki = KEYBDINPUT(wVk=0, wScan=sc_ctrl, dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
            user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki))), ctypes.sizeof(INPUT))
            time.sleep(0.005)
        if shift_needed:
            ki = KEYBDINPUT(wVk=0, wScan=sc_shift, dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
            user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki))), ctypes.sizeof(INPUT))
            time.sleep(0.005)
            
        # Standard hardware stabilization delay
        time.sleep(0.02)


def send_single_key(vk: int, extended: bool = False):
    """Sends a single virtual key code down and up event on Windows using scan codes."""
    sc = user32.MapVirtualKeyW(vk, 0)
    
    # Key Down
    flags_down = KEYEVENTF_SCANCODE
    if extended:
        flags_down |= KEYEVENTF_EXTENDEDKEY
    ki_down = KEYBDINPUT(wVk=0, wScan=sc, dwFlags=flags_down, time=0, dwExtraInfo=None)
    inp_down = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_down))
    user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
    time.sleep(0.01)
    
    # Key Up
    flags_up = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
    if extended:
        flags_up |= KEYEVENTF_EXTENDEDKEY
    ki_up = KEYBDINPUT(wVk=0, wScan=sc, dwFlags=flags_up, time=0, dwExtraInfo=None)
    inp_up = INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki_up))
    user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))
    time.sleep(0.015)


def send_key_combination(combo_str: str):
    """
    Executes a sequential keyboard combination key-down, staging, then reverse key-up on Windows.
    Splits keys on '+' (e.g., 'ctrl+a').
    """
    parts = [p.strip().lower() for p in combo_str.split("+")]
    vks = []
    extended_flags = []
    
    modifier_map = {
        "ctrl": 0x11,
        "control": 0x11,
        "shift": 0x10,
        "alt": 0x12,
        "win": 0x5B,
        "super": 0x5B,
        "command": 0x5B
    }
    
    for part in parts:
        if part in modifier_map:
            vks.append(modifier_map[part])
            extended_flags.append(False)
        elif part in KEY_MAP:
            vk, ext = KEY_MAP[part]
            vks.append(vk)
            extended_flags.append(ext)
        elif len(part) == 1:
            res = user32.VkKeyScanW(part)
            if res != -1:
                vks.append(res & 0xFF)
                extended_flags.append(False)
            else:
                raise ValueError(f"Unknown key character in combination: '{part}'")
        else:
            raise ValueError(f"Unknown key in combination: '{part}'")
            
    # Stage down sequence
    for vk, ext in zip(vks, extended_flags):
        sc = user32.MapVirtualKeyW(vk, 0)
        flags = KEYEVENTF_SCANCODE
        if ext:
            flags |= KEYEVENTF_EXTENDEDKEY
        ki = KEYBDINPUT(wVk=0, wScan=sc, dwFlags=flags, time=0, dwExtraInfo=None)
        user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki))), ctypes.sizeof(INPUT))
        time.sleep(0.01)
        
    time.sleep(0.05)
    
    # Stage up sequence in reverse order
    for vk, ext in zip(reversed(vks), reversed(extended_flags)):
        sc = user32.MapVirtualKeyW(vk, 0)
        flags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
        if ext:
            flags |= KEYEVENTF_EXTENDEDKEY
        ki = KEYBDINPUT(wVk=0, wScan=sc, dwFlags=flags, time=0, dwExtraInfo=None)
        user32.SendInput(1, ctypes.byref(INPUT(type=INPUT_KEYBOARD, u=INPUT_UNION(ki=ki))), ctypes.sizeof(INPUT))
        time.sleep(0.01)


def get_unix_combo_string(combo_str: str) -> str:
    """Parses standard combo layout 'ctrl+a' or 'ctrl+Return' into xdotool notation format."""
    parts = [p.strip().lower() for p in combo_str.split("+")]
    unix_parts = []
    for part in parts:
        if part in ["ctrl", "control"]:
            unix_parts.append("ctrl")
        elif part == "shift":
            unix_parts.append("shift")
        elif part == "alt":
            unix_parts.append("alt")
        elif part in ["win", "super", "command"]:
            unix_parts.append("super")
        elif part in UNIX_KEY_MAP:
            unix_parts.append(UNIX_KEY_MAP[part])
        else:
            unix_parts.append(part)
    return "+".join(unix_parts)


# --- Unix/Linux Fallback Helper Functions ---

def find_window_unix(window_name: str) -> str:
    """Finds an X11 window matching name pattern and returns window ID."""
    try:
        out = run_command(["xdotool", "search", "--name", window_name])
        ids = out.split()
        if not ids:
            raise ValueError(f"No window found matching '{window_name}'")
        return ids[-1] # Return latest instance
    except Exception:
        raise ValueError(f"No window found matching name '{window_name}'. Ensure xdotool is running.")


async def capture_unix(window_name: str) -> Any:
    """Unix fallback capture implementation utilizing xdotool and maim/import/scrot."""
    try:
        window_id = find_window_unix(window_name)
        try:
            run_command(["xdotool", "windowactivate", window_id])
            time.sleep(0.2)
        except Exception:
            pass
            
        temp_file = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"mcp_cap_{window_id}.png")
        captured = False
        
        # Attempt maim
        try:
            run_command(["maim", "-i", window_id, temp_file])
            captured = True
        except Exception:
            pass
            
        # Attempt ImageMagick
        if not captured:
            try:
                run_command(["import", "-window", window_id, temp_file])
                captured = True
            except Exception:
                pass
                
        # Attempt scrot
        if not captured:
            try:
                run_command(["scrot", "-u", temp_file])
                captured = True
            except Exception:
                pass
                
        if not captured:
            return "Error: Could not capture. Ensure 'maim', ImageMagick 'import', or 'scrot' is installed."
            
        with open(temp_file, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
            
        try:
            os.remove(temp_file)
        except Exception:
            pass
            
        return ImageContent(type="image", data=b64_data, mimeType="image/png")
    except Exception as e:
        return f"Error capturing on Linux: {str(e)}. Please check if 'xdotool' and capture tools are installed."


# --- Initialize MCP Server ---
mcp = FastMCP(MCP_NAME, stateless_http=True, json_response=False)


# --- MCP Tools ---

@mcp.tool(name=f"{TOOL_PREFIX}screen_capture")
async def screen_capture() -> Any:
    """
    Capture the desktop as an image.
    Always run this tool FIRST to inspect the screen layout, read text, or identify coordinate bounds.
    Always run this tool AFTER an interaction (clicking or typing) to verify the new visual state of the desktop.
    """
    if not HAS_PILLOW:
        return "Error: The Pillow library is required for capture functionality. Please install it with 'pip install pillow'."
        
    if IS_WINDOWS:
        try:
            hwnd, title = find_window(WINDOW_NAME)
            
            # Foreground focus window to ensure full paint visibility during screen capture
            activate_window(hwnd)
            time.sleep(0.3) # Allow operating system window painting and settling
            
            left, top, right, bottom = get_client_rect_screen(hwnd)
            width = right - left
            height = bottom - top
            
            if width <= 0 or height <= 0:
                return f"Error: Invalid bounds ({width}x{height}). Desktop might be minimized."
                
            # Grab bounding box from the screen canvas
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
            
            # Convert PIL image to PNG raw bytes base64 stream
            from io import BytesIO
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            b64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            return ImageContent(
                type="image",
                data=b64_data,
                mimeType="image/png"
            )
        except Exception as e:
            return f"Error capturing window on Windows: {str(e)}"
    else:
        # Unix fallback
        return await capture_unix(WINDOW_NAME)


@mcp.tool(name=f"{TOOL_PREFIX}print_screen")
async def print_screen(filename: str = "screenshot.png") -> str:
    """
    Capture the desktop screen and save it to a file inside the Workspace directory.
    Use this to save step-by-step records of operations.
    
    Args:
        filename: The output filename (e.g. 'screenshot.png' or 'subfolder/cap.png')
    """
    try:
        filepath = get_safe_path(WORKSPACE_DIR, filename)
        # Ensure parent directories exist
        filepath.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        return f"Error: Permission denied. {str(e)}"
    except IsADirectoryError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error resolving target path: {str(e)}"

    if IS_WINDOWS:
        if not HAS_PILLOW:
            return "Error: The Pillow library is required for capture functionality. Please install it with 'pip install pillow'."
        try:
            hwnd, title = find_window(WINDOW_NAME)
            
            # Foreground focus window to ensure full paint visibility during screen capture
            activate_window(hwnd)
            time.sleep(0.3) # Allow operating system window painting and settling
            
            left, top, right, bottom = get_client_rect_screen(hwnd)
            width = right - left
            height = bottom - top
            
            if width <= 0 or height <= 0:
                return f"Error: Window '{title}' has invalid bounds ({width}x{height}). It might be minimized."
                
            # Grab bounding box from the screen canvas
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
            img.save(filepath, format="PNG")
            
            return f"Successfully saved screen capture to '{filename}' (Workspace: {WORKSPACE_DIR})."
        except Exception as e:
            return f"Error capturing window on Windows: {str(e)}"
    else:
        # Unix fallback
        try:
            window_id = find_window_unix(WINDOW_NAME)
            try:
                run_command(["xdotool", "windowactivate", window_id])
                time.sleep(0.2)
            except Exception:
                pass
                
            captured = False
            
            # Attempt maim
            try:
                run_command(["maim", "-i", window_id, str(filepath)])
                captured = True
            except Exception:
                pass
                
            # Attempt ImageMagick
            if not captured:
                try:
                    run_command(["import", "-window", window_id, str(filepath)])
                    captured = True
                except Exception:
                    pass
                    
            # Attempt scrot
            if not captured:
                try:
                    run_command(["scrot", "-u", str(filepath)])
                    captured = True
                except Exception:
                    pass
                    
            if not captured:
                return "Error: Could not capture. Ensure 'maim', ImageMagick 'import', or 'scrot' is installed."
                
            return f"Successfully saved screen capture to '{filename}'."
        except Exception as e:
            return f"Error capturing on Linux: {str(e)}. Please check if 'xdotool' and capture tools are installed."


@mcp.tool(name=f"{TOOL_PREFIX}click")
async def click(x: int, y: int, double: bool = False) -> str:
    """
    Click at a specific x/y pixel offset within the target desktop area.
    Run the 'screen_capture' tool beforehand to visually map and locate target coordinates (x, y).
    
    Args:
        x: Horizontal pixel offset from the top-left corner (0) of the desktop.
        y: Vertical pixel offset from the top-left corner (0) of the desktop.
        double: Set to True to trigger a double-click (often required on Windows to open desktop items or select word segments). Default is False.
    """
    if IS_WINDOWS:
        try:
            hwnd, title = find_window(WINDOW_NAME)
            
            # Focus and bring the window fully to the front to receive mouse interactions
            activate_window(hwnd)
            time.sleep(0.5) # Increased sleep to ensure complete painting & system activation
            
            # Map coordinates to screen space
            pt = POINT(x, y)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            screen_x, screen_y = pt.x, pt.y
            
            # Position cursor and trigger absolute mouse events
            user32.SetCursorPos(screen_x, screen_y)
            time.sleep(0.15) # Wait for cursor positioning to complete
            
            # Determine click iterations (1 for standard, 2 for double click)
            iterations = 2 if double else 1
            
            for i in range(iterations):
                # Perform mouse click (mouse down then mouse up)
                # MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004
                user32.mouse_event(0x0002, 0, 0, 0, None)
                time.sleep(0.05)
                user32.mouse_event(0x0004, 0, 0, 0, None)
                # Quick pause between clicks during double-click to satisfy system timing
                if i < iterations - 1:
                    time.sleep(0.1)
            
            click_type = "double-clicked" if double else "clicked"
            return f"Successfully {click_type} coords ({x}, {y})"
        except Exception as e:
            return f"Error performing click on Windows: {str(e)}"
    else:
        # Unix (xdotool)
        try:
            window_id = find_window_unix(WINDOW_NAME)
            run_command(["xdotool", "windowactivate", window_id])
            time.sleep(0.1)
            
            click_args = ["xdotool", "mousemove", "--window", window_id, str(x), str(y)]
            if double:
                click_args += ["click", "--repeat", "2", "--delay", "100", "1"]
            else:
                click_args += ["click", "1"]
                
            run_command(click_args)
            click_type = "double-clicked" if double else "clicked"
            return f"Successfully {click_type} client coords ({x}, {y}) on Unix window '{WINDOW_NAME}' (ID: {window_id})."
        except Exception as e:
            return f"Error performing click on Unix: {str(e)}. Ensure 'xdotool' is installed."


@mcp.tool(name=f"{TOOL_PREFIX}type_text")
async def type_text(text: str) -> str:
    """
    Type a string of printable characters (letters, numbers, symbols) into the active control/text field.
    
    IMPORTANT: This tool ONLY inputs raw characters. It does NOT automatically submit forms or press Enter.
    If you are executing commands in a terminal or submitting login/search forms, you MUST run the
    'press_enter' tool immediately after typing to execute your command or submit the input.
    """
    if IS_WINDOWS:
        try:
            hwnd, title = find_window(WINDOW_NAME)
            
            # Bring window and standard focus forward
            activate_window(hwnd)
            time.sleep(0.2) # Give window ample time to prepare to receive focus inputs
            
            # Send key inputs
            send_keyboard_text(text)
            
            return f"Successfully typed provided text."
        except Exception as e:
            return f"Error sending text input on Windows: {str(e)}"
    else:
        # Unix (xdotool) - Updated with a matching 40ms human delay parameter
        try:
            window_id = find_window_unix(WINDOW_NAME)
            run_command(["xdotool", "windowactivate", window_id])
            time.sleep(0.1)
            run_command(["xdotool", "type", "--delay", "40", "--window", window_id, text])
            return f"Successfully typed text in Unix window '{WINDOW_NAME}' (ID: {window_id})."
        except Exception as e:
            return f"Error typing text on Unix: {str(e)}. Ensure 'xdotool' is installed."


@mcp.tool(name=f"{TOOL_PREFIX}press_enter")
async def press_enter() -> str:
    """
    Press the 'Enter' (Return) key on the keyboard.
    Call this tool immediately after 'type' to submit search bars, execute command-line instructions,
    confirm popup dialogs, or submit form logins.
    """
    if IS_WINDOWS:
        try:
            hwnd, title = find_window(WINDOW_NAME)
            activate_window(hwnd)
            time.sleep(0.15)
            send_single_key(0x0D, False) # VK_RETURN = 0x0D
            return "Successfully pressed Enter."
        except Exception as e:
            return f"Error pressing Enter key on Windows: {str(e)}"
    else:
        try:
            window_id = find_window_unix(WINDOW_NAME)
            run_command(["xdotool", "windowactivate", window_id])
            time.sleep(0.1)
            run_command(["xdotool", "key", "--window", window_id, "Return"])
            return f"Successfully pressed Enter in Unix window '{WINDOW_NAME}' (ID: {window_id})."
        except Exception as e:
            return f"Error pressing Enter key on Unix: {str(e)}. Ensure 'xdotool' is installed."


@mcp.tool(name=f"{TOOL_PREFIX}press_key")
async def press_key(key: str) -> str:
    """
    Press a specific non-character navigation or function keyboard key.
    Useful for navigation, closing popups, or erasing entries.
    
    Args:
        key: The key to press. Must be exactly one of:
             - 'tab'       : Cycle through form input fields, links, or buttons
             - 'backspace' : Delete the character directly preceding the cursor
             - 'delete'    : Delete the character directly following the cursor
             - 'escape'    : Dismiss open context menus, focus traps, or close windows
             - 'space'     : Press spacebar (useful for ticking active UI checkboxes)
             - 'up', 'down', 'left', 'right' : Arrow keys for navigation in lists or grids
             - 'home', 'end' : Jump cursor position to the start or end of the text line
             - 'page_up', 'page_down' : Scroll standard viewport containers up or down
             - 'f1' to 'f12' : Function keys
    """
    key_lower = key.strip().lower()
    
    if IS_WINDOWS:
        if key_lower not in KEY_MAP:
            return f"Error: Unsupported key '{key}'. Please use one of the supported keys listed in the tool description."
        try:
            hwnd, title = find_window(WINDOW_NAME)
            activate_window(hwnd)
            time.sleep(0.15)
            vk, ext = KEY_MAP[key_lower]
            send_single_key(vk, ext)
            return f"Successfully pressed key '{key}'."
        except Exception as e:
            return f"Error pressing key '{key}' on Windows: {str(e)}"
    else:
        if key_lower not in UNIX_KEY_MAP:
            return f"Error: Unsupported key '{key}'. Please use one of the supported keys listed in the tool description."
        try:
            window_id = find_window_unix(WINDOW_NAME)
            run_command(["xdotool", "windowactivate", window_id])
            time.sleep(0.1)
            unix_key = UNIX_KEY_MAP[key_lower]
            run_command(["xdotool", "key", "--window", window_id, unix_key])
            return f"Successfully pressed key '{key}' in Unix window '{WINDOW_NAME}' (ID: {window_id})."
        except Exception as e:
            return f"Error pressing key '{key}' on Unix: {str(e)}. Ensure 'xdotool' is installed."


@mcp.tool(name=f"{TOOL_PREFIX}key_combination")
async def key_combination(combination: str) -> str:
    """
    Perform a multi-key shortcut sequence simultaneously (e.g., ctrl+c, alt+f4).
    Extremely useful for copy-paste tasks, mass-selecting text, or saving documents.
    
    Args:
        combination: Key combination separated by '+' signs (e.g., 'ctrl+a', 'ctrl+c', 'ctrl+v', 'ctrl+z', 'alt+f4', 'ctrl+shift+t').
    """
    if IS_WINDOWS:
        try:
            hwnd, title = find_window(WINDOW_NAME)
            activate_window(hwnd)
            time.sleep(0.15)
            send_key_combination(combination)
            return f"Successfully performed key combination '{combination}'."
        except Exception as e:
            return f"Error executing key combination '{combination}' on Windows: {str(e)}"
    else:
        try:
            window_id = find_window_unix(WINDOW_NAME)
            run_command(["xdotool", "windowactivate", window_id])
            time.sleep(0.1)
            unix_combo = get_unix_combo_string(combination)
            run_command(["xdotool", "key", "--window", window_id, unix_combo])
            return f"Successfully executed key combination '{combination}' on Unix."
        except Exception as e:
            return f"Error executing key combination '{combination}' on Unix: {str(e)}. Ensure 'xdotool' is installed."


# --- Authentication Middleware (Matching starlette ecosystem) ---

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Enforces API key token validation on incoming HTTP requests."""
    def __init__(self, app, api_key: str):
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        x_api_key = request.headers.get("X-API-Key")

        provided_key = None
        if auth_header and auth_header.startswith("Bearer "):
            provided_key = auth_header.split(" ", 1)[1]
        elif x_api_key:
            provided_key = x_api_key

        if not provided_key or provided_key != self.api_key:
            return JSONResponse(
                {"detail": "Unauthorized: Invalid or missing API Key"}, status_code=401
            )

        return await call_next(request)


# --- Core Launch Sequence ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Desktop Automation MCP Server")
    parser.add_argument(
        "--stdio", action="store_true", help="Run in standard stdio mode"
    )
    parser.add_argument(
        "--mcp", action="store_true", help="Run in HTTP streaming mode (current default)"
    )
    parser.add_argument("--api-key", type=str, help="Require API key validation for incoming HTTP requests")
    parser.add_argument(
        "--env-base",
        type=str,
        help="Prefix for environment variables to isolate multiple servers (e.g., DESKTOP)",
    )
    parser.add_argument(
        "--tool-prefix",
        type=str,
        default="desktop_",
        help="Custom registration prefix for MCP tools",
    )
    parser.add_argument(
        "--mcp-name",
        type=str,
        default="Desktop",
        help="Custom registration server name, default: Desktop",
    )

    args = parser.parse_args()

    if ENV_PREFIX:
        actual_prefix = ENV_PREFIX if ENV_PREFIX.endswith("_") else f"{ENV_PREFIX}_"
        print(
            f"Using environment variable prefix: '{actual_prefix}' (e.g. expecting {actual_prefix}PORT)",
            file=sys.stderr,
        )

    if args.stdio:
        mcp.run()
    else:
        starlette_app = mcp.streamable_http_app()

        if args.api_key:
            starlette_app.add_middleware(APIKeyAuthMiddleware, api_key=args.api_key)

        starlette_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        uvicorn.run(starlette_app, host="127.0.0.1", port=PORT)