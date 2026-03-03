import time
import threading
import ctypes
import ctypes.wintypes as _wt
import tkinter as tk
from tkinter import messagebox
from pynput import mouse, keyboard

# ── Win32 SendInput fast-path: direct click injection, bypasses pynput ─────────
try:
    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", _wt.LONG), ("dy", _wt.LONG),
                    ("mouseData", _wt.DWORD), ("dwFlags", _wt.DWORD),
                    ("time", _wt.DWORD), ("dwExtraInfo", ctypes.POINTER(_wt.ULONG))]
    class _INPUT(ctypes.Structure):
        _fields_ = [("type", _wt.DWORD), ("mi", _MOUSEINPUT)]
    _LDOWN = _INPUT(type=0, mi=_MOUSEINPUT(dwFlags=0x0002))
    _LUP   = _INPUT(type=0, mi=_MOUSEINPUT(dwFlags=0x0004))
    _SI    = ctypes.sizeof(_INPUT)
    _send  = ctypes.windll.user32.SendInput
    def _win_press():   _send(1, ctypes.byref(_LDOWN), _SI)
    def _win_release(): _send(1, ctypes.byref(_LUP),   _SI)
    _USE_WINSEND = True
    # Raise Windows timer resolution to 1 ms for accurate sleep
    try: ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception: pass
except Exception:
    _USE_WINSEND = False

# ── Hybrid sleep: OS sleep + micro-spin for the final 1 ms ───────────────────
_SPIN = 0.001
def _precise_sleep(dt):
    if dt <= 0:
        return
    if dt > _SPIN:
        time.sleep(dt - _SPIN)
    end = time.perf_counter() + dt
    while time.perf_counter() < end:
        pass

running = False
click_thread = None
stop_event = threading.Event()
hotkey_combo = set()
pressed_keys = set()
hotkey_pressed = False
is_typing = False
mouse_controller = mouse.Controller()
pynput_btn = mouse.Button.left


def click_loop(cps, duty):
    period    = max(0.0001, 1.0 / cps)
    down_time = period * max(0.0, min(1.0, duty / 100.0))

    # Choose fastest available click backend
    if _USE_WINSEND:
        press, release = _win_press, _win_release
    else:
        _btn = pynput_btn
        _mc  = mouse_controller
        press   = lambda: _mc.press(_btn)
        release = lambda: _mc.release(_btn)

    # Pre-bind hot-path symbols to locals (avoids global/attr lookup each iteration)
    stop_is_set = stop_event.is_set
    sleep       = _precise_sleep
    perf        = time.perf_counter
    after       = root.after

    next_tick = perf()
    while not stop_is_set():
        now = perf()
        if now > next_tick + period:   # skip missed ticks; don't burst
            next_tick = now
        sleep(next_tick - now)
        if stop_is_set():
            break
        press()
        if down_time > 0:
            sleep(down_time)
        release()
        next_tick += period
    after(0, lambda: status_var.set("Status: STOPPED"))


def start_clicking():
    global running, click_thread
    if running:
        return
    running = True
    stop_event.clear()
    click_thread = threading.Thread(target=click_loop, args=(get_cps(), get_duty()), daemon=True)
    click_thread.start()
    status_var.set("Status: RUNNING")


def stop_clicking():
    global running
    if running:
        running = False
        stop_event.set()
        status_var.set("Status: STOPPED")


def get_cps():
    try:
        return max(1.0, min(1000.0, float(cps_entry.get())))
    except Exception:
        return 10.0


def get_duty():
    try:
        return max(0.0, min(100.0, float(duty_entry.get())))
    except Exception:
        return 50.0


def normalize_key(key):
    if isinstance(key, keyboard.Key):
        name = key.name.upper()
        if name in ("SHIFT", "SHIFT_L", "SHIFT_R"):
            return "SHIFT"
        if name in ("CTRL", "CONTROL_L", "CONTROL_R"):
            return "CTRL"
        if name in ("ALT", "OPTION_L", "OPTION_R", "ALT_L", "ALT_R"):
            return "ALT"
        if name in ("CMD", "COMMAND", "COMMAND_L", "COMMAND_R", "META_L", "META_R"):
            return "CMD"
        return name
    return str(key).replace("'", "").upper()


def on_press(key):
    global hotkey_pressed
    k = normalize_key(key)
    pressed_keys.add(k)
    if key == keyboard.Key.esc:
        stop_clicking()
        return
    if is_typing:
        return
    if hotkey_combo and hotkey_combo.issubset(pressed_keys) and not hotkey_pressed:
        hotkey_pressed = True
        if running:
            root.after(0, stop_clicking)
        else:
            root.after(0, start_clicking)


def on_release(key):
    global hotkey_pressed
    k = normalize_key(key)
    pressed_keys.discard(k)
    if k in hotkey_combo:
        hotkey_pressed = False


listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()


def on_entry_focus_in(event):
    global is_typing
    is_typing = True


def on_entry_focus_out(event):
    global is_typing
    is_typing = False


def set_hotkey():
    root.focus()
    temp_win = tk.Toplevel(root)
    temp_win.title("Set Hotkey")
    temp_win.geometry("300x130")
    temp_win.resizable(False, False)
    temp_win.focus_force()
    tk.Label(temp_win, text="Press your hotkey combo…", font=("Arial", 12)).pack(pady=12)
    display_var = tk.StringVar(value="—")
    tk.Label(temp_win, textvariable=display_var, font=("Arial", 11, "bold")).pack()
    keys_pressed_temp = set()

    def clean_key(sym):
        sym = sym.upper()
        if sym in ("SHIFT_L", "SHIFT_R"): return "SHIFT"
        if sym in ("CONTROL_L", "CONTROL_R"): return "CTRL"
        if sym in ("ALT_L", "ALT_R", "OPTION_L", "OPTION_R"): return "ALT"
        if sym in ("COMMAND_L", "COMMAND_R", "COMMAND", "META_L", "META_R"): return "CMD"
        return sym

    def on_key(event):
        keys_pressed_temp.add(clean_key(event.keysym))
        display_var.set("+".join(sorted(keys_pressed_temp)))

    def on_key_release(event):
        global hotkey_combo
        if keys_pressed_temp:
            hotkey_combo = set(keys_pressed_temp)
            hotkey_display_var.set("Hotkey: " + "+".join(sorted(hotkey_combo)))
            keys_pressed_temp.clear()
            pressed_keys.clear()
            temp_win.destroy()

    temp_win.bind_all("<KeyPress>", on_key)
    temp_win.bind_all("<KeyRelease>", on_key_release)


root = tk.Tk()
root.title("Jaidev's AutoClicker (Windows)")
root.geometry("300x290")
root.resizable(False, False)

PAD = {"padx": 16, "pady": 6}

tk.Label(root, text="CPS (Clicks Per Second):", anchor="w").pack(fill="x", **PAD)
cps_entry = tk.Entry(root, font=("Arial", 12))
cps_entry.insert(0, "54.53")
cps_entry.pack(fill="x", padx=16)
cps_entry.bind("<FocusIn>", on_entry_focus_in)
cps_entry.bind("<FocusOut>", on_entry_focus_out)

tk.Label(root, text="Duty Cycle (0 – 100%):", anchor="w").pack(fill="x", **PAD)
duty_entry = tk.Entry(root, font=("Arial", 12))
duty_entry.insert(0, "18.37")
duty_entry.pack(fill="x", padx=16)
duty_entry.bind("<FocusIn>", on_entry_focus_in)
duty_entry.bind("<FocusOut>", on_entry_focus_out)

hotkey_display_var = tk.StringVar(value="Hotkey: NONE")
tk.Label(root, textvariable=hotkey_display_var, fg="#0055cc", font=("Arial", 11)).pack(**PAD)

tk.Button(root, text="Set Hotkey", command=set_hotkey, width=14).pack(pady=4)

status_var = tk.StringVar(value="Status: STOPPED")
tk.Label(root, textvariable=status_var, font=("Arial", 13, "bold")).pack(pady=10)

tk.Label(root, text="ESC = stop instantly  |  Run as Admin if clicks fail in games",
         fg="gray", font=("Arial", 8), wraplength=260).pack()

root.mainloop()
