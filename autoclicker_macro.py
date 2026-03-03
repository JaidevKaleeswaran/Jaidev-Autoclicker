import time
import threading
import tkinter as tk
from tkinter import messagebox
from pynput import keyboard
import subprocess

# ── Hybrid sleep: OS sleep + micro-spin for the final 0.5 ms ──────────────────
_SPIN = 0.0005

def _precise_sleep(dt):
    if dt <= 0:
        return
    if dt > _SPIN:
        time.sleep(dt - _SPIN)
    end = time.perf_counter() + dt
    while time.perf_counter() < end:
        pass


# ── Global state ───────────────────────────────────────────────────────────────
running        = False
macro_thread   = None
stop_event     = threading.Event()
hotkey_combo   = set()
pressed_keys   = set()
hotkey_pressed = False
is_typing      = False

kb_controller  = keyboard.Controller()


# ── Key press loop ─────────────────────────────────────────────────────────────
def key_loop(target_key, interval, duty):
    """Repeatedly press `target_key` at `interval` seconds, with `duty`% hold time."""
    period    = max(0.001, interval)
    down_time = period * max(0.0, min(1.0, duty / 100.0))

    stop_is_set = stop_event.is_set
    sleep       = _precise_sleep
    perf        = time.perf_counter
    after       = root.after
    press       = kb_controller.press
    release     = kb_controller.release

    next_tick = perf()
    while not stop_is_set():
        now = perf()
        if now > next_tick + period:   # skip missed ticks — don't burst
            next_tick = now
        sleep(next_tick - now)
        if stop_is_set():
            break
        press(target_key)
        if down_time > 0:
            sleep(down_time)
        release(target_key)
        next_tick += period

    after(0, lambda: status_var.set("Status: STOPPED"))


# ── Start / stop ───────────────────────────────────────────────────────────────
def start_macro():
    global running, macro_thread
    if running:
        return
    key_str = key_entry.get().strip()
    if not key_str:
        messagebox.showwarning("No Key", "Please enter a key to press.")
        return
    target_key = key_str[0]          # single character key
    running = True
    stop_event.clear()
    macro_thread = threading.Thread(
        target=key_loop,
        args=(target_key, get_interval(), get_duty()),
        daemon=True,
    )
    macro_thread.start()
    status_var.set("Status: RUNNING")


def stop_macro():
    global running
    if running:
        running = False
        stop_event.set()
        status_var.set("Status: STOPPED")


# ── Input helpers ──────────────────────────────────────────────────────────────
def get_interval():
    try:
        return max(0.001, float(interval_entry.get()))
    except Exception:
        return 0.05   # default 50 ms → 20 presses/s


def get_duty():
    try:
        return max(0.0, min(100.0, float(duty_entry.get())))
    except Exception:
        return 50.0


# ── Hotkey normalisation ───────────────────────────────────────────────────────
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


# ── Global keyboard listener ───────────────────────────────────────────────────
def on_press(key):
    global hotkey_pressed
    k = normalize_key(key)
    pressed_keys.add(k)
    if key == keyboard.Key.esc:
        stop_macro()
        return
    if is_typing:
        return
    if hotkey_combo and hotkey_combo.issubset(pressed_keys) and not hotkey_pressed:
        hotkey_pressed = True
        if running:
            root.after(0, stop_macro)
        else:
            root.after(0, start_macro)


def on_release(key):
    global hotkey_pressed
    k = normalize_key(key)
    pressed_keys.discard(k)
    # Only clear the latch once the ENTIRE combo is lifted,
    # so OS key-repeat can never fire a second spurious toggle.
    if hotkey_pressed and not hotkey_combo.issubset(pressed_keys):
        hotkey_pressed = False


listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()


# ── Entry focus guards (prevent hotkey whilst typing) ─────────────────────────
def on_entry_focus_in(event):
    global is_typing
    is_typing = True


def on_entry_focus_out(event):
    global is_typing
    is_typing = False


# ── Hotkey setter dialog ───────────────────────────────────────────────────────
def set_hotkey():
    root.focus()
    temp_win = tk.Toplevel(root)
    temp_win.title("Set Hotkey")
    temp_win.geometry("300x160")
    temp_win.resizable(False, False)
    temp_win.focus_force()
    tk.Label(temp_win, text="Press your hotkey combo…", font=("Arial", 12)).pack(pady=10)
    display_var = tk.StringVar(value="—")
    tk.Label(temp_win, textvariable=display_var, font=("Arial", 11, "bold")).pack()
    keys_held = set()       # keys currently down
    pending_combo = set()   # last fully-held combo

    def clean_key(sym):
        sym = sym.upper()
        if sym in ("SHIFT_L", "SHIFT_R"):                         return "SHIFT"
        if sym in ("CONTROL_L", "CONTROL_R"):                      return "CTRL"
        if sym in ("ALT_L", "ALT_R", "OPTION_L", "OPTION_R"):     return "ALT"
        if sym in ("COMMAND_L", "COMMAND_R", "COMMAND", "META_L", "META_R"): return "CMD"
        return sym

    def on_key(event):
        keys_held.add(clean_key(event.keysym))
        pending_combo.clear()
        pending_combo.update(keys_held)
        display_var.set("+".join(sorted(pending_combo)))

    def on_key_release(event):
        keys_held.discard(clean_key(event.keysym))

    def confirm():
        global hotkey_combo
        if pending_combo:
            hotkey_combo = set(pending_combo)
            hotkey_display_var.set("Hotkey: " + "+".join(sorted(hotkey_combo)))
            pressed_keys.clear()
            temp_win.destroy()

    temp_win.bind_all("<KeyPress>",   on_key)
    temp_win.bind_all("<KeyRelease>", on_key_release)
    tk.Button(temp_win, text="SET", command=confirm, width=10,
              font=("Arial", 11, "bold"), bg="#0055cc", fg="white").pack(pady=10)


# ── Permissions helper (macOS) ─────────────────────────────────────────────────
def open_permissions():
    subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
    subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"])


def request_permissions():
    try:
        subprocess.check_call(
            ["osascript", "-e", 'tell application "System Events" to get name of every process'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        if messagebox.askyesno(
            "Permissions Required",
            "Needs Accessibility & Input Monitoring permissions.\n\nOpen System Settings?",
        ):
            open_permissions()


# ── GUI ────────────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("Jaidev's Key Macro")
root.geometry("300x320")
root.resizable(False, False)

PAD = {"padx": 16, "pady": 6}

# Key to press
tk.Label(root, text="Key to press:", anchor="w").pack(fill="x", **PAD)
key_entry = tk.Entry(root, font=("Arial", 12))
key_entry.insert(0, "x")
key_entry.pack(fill="x", padx=16)
key_entry.bind("<FocusIn>",  on_entry_focus_in)
key_entry.bind("<FocusOut>", on_entry_focus_out)

# Interval
tk.Label(root, text="Interval (seconds):", anchor="w").pack(fill="x", **PAD)
interval_entry = tk.Entry(root, font=("Arial", 12))
interval_entry.insert(0, "0.05")   # 20 presses/s default
interval_entry.pack(fill="x", padx=16)
interval_entry.bind("<FocusIn>",  on_entry_focus_in)
interval_entry.bind("<FocusOut>", on_entry_focus_out)

# Duty cycle
tk.Label(root, text="Duty Cycle (0 – 100%):", anchor="w").pack(fill="x", **PAD)
duty_entry = tk.Entry(root, font=("Arial", 12))
duty_entry.insert(0, "50")
duty_entry.pack(fill="x", padx=16)
duty_entry.bind("<FocusIn>",  on_entry_focus_in)
duty_entry.bind("<FocusOut>", on_entry_focus_out)

# Hotkey display + setter
hotkey_display_var = tk.StringVar(value="Hotkey: NONE")
tk.Label(root, textvariable=hotkey_display_var, fg="#0055cc", font=("Arial", 11)).pack(**PAD)
tk.Button(root, text="Set Hotkey", command=set_hotkey, width=14).pack(pady=4)

# Status
status_var = tk.StringVar(value="Status: STOPPED")
tk.Label(root, textvariable=status_var, font=("Arial", 13, "bold")).pack(pady=8)

tk.Label(root, text="ESC = stop instantly", fg="gray", font=("Arial", 9)).pack()

root.after(600, request_permissions)
root.mainloop()
