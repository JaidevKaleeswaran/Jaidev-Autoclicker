

import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pynput import mouse, keyboard
import subprocess

# Try to import pyautogui as a fallback
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# -------------------------------
# GLOBAL VARIABLES
# -------------------------------
running = False
click_thread = None
stop_event = threading.Event()

hotkey_combo = set()      # keys required to activate
pressed_keys = set()      # currently pressed keys
hotkey_pressed = False    # ensures one toggle per press

mouse_controller = mouse.Controller()

# -------------------------------
# CLICK LOOP
# -------------------------------
def click_loop(cps, duty, button):
    try:
        period = max(0.0001, 1.0 / cps)
        duty_amount = max(0, min(100, duty)) / 100
        down_time = period * duty_amount
        up_time = period - down_time

        btn_str = "left" if button == "Left" else "right"
        pynput_btn = mouse.Button.left if button == "Left" else mouse.Button.right

        print(f"Starting loop. CPS={cps}, Duty={duty}%, Period={period}")

        # Update visual indicator to GREEN
        root.after(0, lambda: indicator_canvas.config(bg="green"))

        while not stop_event.is_set():
            # FLASH indicator occasionally to prove loop is running
            # (Doing this too fast might lag GUI, so maybe just keep it green)
            
            if PYAUTOGUI_AVAILABLE:
                # PyAutoGUI handles clicks more robustly on some macOS setups?
                # But it doesn't support 'holding' as easily with precise timing in a loop
                # without blocking. actually it does with keyDown/keyUp equivalent for mouse.
                # However, for autoclicker, we usually just want 'click'.
                # But duty cycle implies holding.
                try:
                   # Try pynput first as it is better for duty cycle
                   mouse_controller.press(pynput_btn)
                   time.sleep(down_time)
                   mouse_controller.release(pynput_btn)
                   time.sleep(up_time)
                except Exception:
                   # Fallback to pyautogui click (no duty cycle support really)
                   pyautogui.click(button=btn_str)
                   time.sleep(period)
            else:
                # Absolute fallback to pynput
                mouse_controller.press(pynput_btn)
                time.sleep(down_time)
                mouse_controller.release(pynput_btn)
                time.sleep(up_time)

    except Exception as e:
        print(f"Error in click_loop: {e}")
        root.after(0, lambda: status_var.set(f"Error: {e}"))
    finally:
         root.after(0, lambda: indicator_canvas.config(bg="red"))

# -------------------------------
# PERMISSION CHECK
# -------------------------------
# -------------------------------
# PERMISSION CHECK
# -------------------------------
def check_permissions():
    """
    Checks if Accessibility permissions are granted.
    Also serves as a proxy for Input Monitoring since usually both are needed.
    """
    try:
        # Attempt to script System Events. This requires Accessibility permissions.
        # If not granted, this will fail (and MacOS might prompt the user).
        subprocess.check_call(
            ["osascript", "-e", 'tell application "System Events" to get name of every process'], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        return True
    except subprocess.CalledProcessError:
        return False

def request_permissions():
    """
    Prompts the user to enable permissions if check fails.
    """
    if not check_permissions():
        response = messagebox.askyesno(
            "Permissions Required", 
            "This autoclicker needs Accessibility and Input Monitoring permissions to work correctly.\n\n"
            "Would you like to open System Settings to enable them now?"
        )
        if response:
            open_permissions()
            return False # Indicate permissions were missing
    return True # Indicate permissions are likely OK or user ignored

# -------------------------------
# START / STOP FUNCTIONS
# -------------------------------
def start_clicking(cps, duty, button):
    global running, click_thread
    if running:
        return
    running = True
    stop_event.clear()
    click_thread = threading.Thread(
        target=click_loop,
        args=(cps, duty, button),
        daemon=True
    )
    click_thread.start()
    status_var.set("Status: RUNNING")

def stop_clicking():
    global running
    if running:
        running = False
        stop_event.set()
        status_var.set("Status: STOPPED")

# -------------------------------
# HOTKEY NORMALIZATION
# -------------------------------
def normalize_key(key):
    if isinstance(key, keyboard.Key):
        name = key.name.upper()
        if name in ["SHIFT", "SHIFT_L", "SHIFT_R"]:
            return "SHIFT"
        if name in ["CTRL", "CONTROL_L", "CONTROL_R"]:
            return "CTRL"
        if name in ["ALT", "OPTION_L", "OPTION_R", "ALT_L", "ALT_R"]:
            return "ALT"
        if name in ["CMD", "COMMAND", "COMMAND_L", "COMMAND_R", "META_L", "META_R"]:
            return "CMD"
        return name
    else:
        return str(key).replace("'", "").upper()

# -------------------------------
# HOTKEY LISTENER WITH SAFE TOGGLE
# -------------------------------
def on_press(key):
    global hotkey_pressed
    k = normalize_key(key)
    pressed_keys.add(k)
    
    # Debug update
    root.after(0, lambda k=k: update_debug_labels(k))

    if key == keyboard.Key.esc:
        stop_clicking()
        return

    if is_typing:
        return

    if hotkey_combo and hotkey_combo.issubset(pressed_keys):
        if not hotkey_pressed:
            hotkey_pressed = True
        
            if not hold_mode_var.get():
                if running:
                    stop_clicking()
                else:
                    start_clicking(get_cps(), get_duty(), click_type_var.get())
            
            else:
                if not running:
                     start_clicking(get_cps(), get_duty(), click_type_var.get())

def on_release(key):
    global hotkey_pressed
    k = normalize_key(key)
    pressed_keys.discard(k)

    root.after(0, lambda k=k: update_debug_labels(k + " (UP)"))

    if k in hotkey_combo:
        hotkey_pressed = False
        
        if hold_mode_var.get() and running:
             stop_clicking()
             

listener = keyboard.Listener(on_press=on_press, on_release=on_release)
listener.start()


is_typing = False

def on_entry_focus_in(event):
    global is_typing
    is_typing = True

def on_entry_focus_out(event):
    global is_typing
    is_typing = False

def get_cps():
    try:
        val = float(cps_entry.get())
        return max(1, min(1000, val))
    except:
        return 10

def get_duty():
    try:
        val = float(duty_entry.get())
        return max(0, min(100, val))
    except:
        return 50


def set_hotkey():

    root.focus()
    
    temp_win = tk.Toplevel(root)
    temp_win.title("Set Hotkey Combo")
    temp_win.geometry("300x150")
    temp_win.focus_force()

    tk.Label(temp_win, text="Press your hotkey combo…").pack(pady=10)
    display_var = tk.StringVar(value="Current: NONE")
    tk.Label(temp_win, textvariable=display_var).pack()

    keys_pressed_temp = set()

    def clean_key(key):
        key = key.upper()
        if key in ["SHIFT_L", "SHIFT_R"]:
            return "SHIFT"
        if key in ["CONTROL_L", "CONTROL_R"]:
            return "CTRL"
        if key in ["ALT_L", "ALT_R", "OPTION_L", "OPTION_R"]:
            return "ALT"
        if key in ["COMMAND_L", "COMMAND_R", "COMMAND", "META_L", "META_R"]:
            return "CMD"
        return key

    def on_key(event):
        k = clean_key(event.keysym)
        keys_pressed_temp.add(k)
        display_var.set("Current: " + "+".join(keys_pressed_temp))

    def on_key_release(event):
        global hotkey_combo
        if keys_pressed_temp:
            hotkey_combo.clear()
            for k in keys_pressed_temp:
                hotkey_combo.add(k)
            hotkey_display_var.set("Current Hotkey: " + "+".join(hotkey_combo))
            keys_pressed_temp.clear()
            temp_win.destroy()
            pressed_keys.clear()

    temp_win.bind_all("<KeyPress>", on_key)
    temp_win.bind_all("<KeyRelease>", on_key_release)

root = tk.Tk()
root.title("Jaidev's AutoClick")
root.geometry("350x550")

# Check permissions on startup
root.after(500, request_permissions)

tk.Label(root, text="CPS (Clicks Per Second):").pack()
cps_entry = tk.Entry(root)
cps_entry.insert(10, "54.53")
cps_entry.pack(pady=5)
cps_entry.bind("<FocusIn>", on_entry_focus_in)
cps_entry.bind("<FocusOut>", on_entry_focus_out)

tk.Label(root, text="Duty Cycle (0–100%):").pack()
duty_entry = tk.Entry(root)
duty_entry.insert(1, "18.37")
duty_entry.pack(pady=5)
duty_entry.bind("<FocusIn>", on_entry_focus_in)
duty_entry.bind("<FocusOut>", on_entry_focus_out)

tk.Label(root, text="Click Type:").pack()
click_type_var = tk.StringVar(value="Left")
ttk.Combobox(root, textvariable=click_type_var, values=["Left", "Right"]).pack(pady=5)

# Hold Mode Toggle
hold_mode_var = tk.BooleanVar(value=False)
tk.Checkbutton(root, text="Hold Mode (Click while holding)", variable=hold_mode_var).pack(pady=5)

tk.Button(root, text="Set Hotkey Combo", command=set_hotkey).pack(pady=10)

status_var = tk.StringVar(value="Status: STOPPED")
tk.Label(root, textvariable=status_var, font=("Arial", 14, "bold")).pack(pady=15)

# Hotkey Debug Info
hotkey_display_var = tk.StringVar(value="Current Hotkey: NONE")
tk.Label(root, textvariable=hotkey_display_var, fg="blue").pack(pady=5)

debug_last_key_var = tk.StringVar(value="Last Key: None")
tk.Label(root, textvariable=debug_last_key_var, font=("Courier", 10)).pack()

debug_held_keys_var = tk.StringVar(value="Held: {}")
tk.Label(root, textvariable=debug_held_keys_var, font=("Courier", 10)).pack()

def update_debug_labels(last_key):
    debug_last_key_var.set(f"Last Key: {last_key}")
    debug_held_keys_var.set(f"Held: {pressed_keys}")

# def test_single_click():
#     def run_test():
#         time.sleep(2)
#         try:
#             target_btn = mouse.Button.left if click_type_var.get() == "Left" else mouse.Button.right
#             print(f"Test clicking {target_btn} at {mouse_controller.position}")
#             mouse_controller.click(target_btn)
#             root.after(0, lambda: status_var.set(f"Status: Test Click OK"))
#         except Exception as e:
#             print(f"Test click failed: {e}")
#             root.after(0, lambda: status_var.set(f"Error: {e}"))
            
#     threading.Thread(target=run_test, daemon=True).start()
#     status_var.set("Status: Click in 2s...")

# tk.Button(root, text="Test Single Click (2s delay)", command=test_single_click).pack(pady=5)
    
# # Visual Status Indicator
# tk.Label(root, text="Active Indicator:").pack()
# indicator_canvas = tk.Canvas(root, width=40, height=20, bg="red", highlightthickness=0)
# indicator_canvas.pack(pady=5)

def open_permissions():
    # Open Accessibility
    subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
    # Open Input Monitoring (macos 10.15+)
    subprocess.run(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"])

if not PYAUTOGUI_AVAILABLE:
    tk.Label(root, text="To improve reliability:\npip install pyautogui", fg="blue").pack(pady=5)

tk.Button(root, text="Open Mac Permissions", command=open_permissions, fg="blue").pack(pady=5)

tk.Label(root, text="Press ESC anytime to stop instantly.", fg="red").pack()

root.mainloop()
