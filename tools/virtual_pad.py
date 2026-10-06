"""Dev-only: create a virtual Xbox 360 pad via uinput and drive it from this terminal.

SDL maps it like real hardware, so it exercises the game's controller path end to end
(hotplug, mapping, stick thresholds) without a physical pad. Linux only.

Setup:   pip install evdev && sudo modprobe uinput && sudo chmod a+rw /dev/uinput
Run:     python tools/virtual_pad.py     (then start the game in another terminal)

Keys:    arrows = D-pad   WASD = left stick (tap)   j = A   k = B   p = Start   q = quit
"""
import select
import sys
import termios
import time
import tty

from evdev import AbsInfo, UInput, ecodes as e

BUTTONS = [e.BTN_A, e.BTN_B, e.BTN_X, e.BTN_Y, e.BTN_TL, e.BTN_TR,
           e.BTN_SELECT, e.BTN_START, e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR]
STICK = AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)
TRIGGER = AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)
HAT = AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)
CAPS = {
    e.EV_KEY: BUTTONS,
    e.EV_ABS: [(e.ABS_X, STICK), (e.ABS_Y, STICK), (e.ABS_Z, TRIGGER),
               (e.ABS_RX, STICK), (e.ABS_RY, STICK), (e.ABS_RZ, TRIGGER),
               (e.ABS_HAT0X, HAT), (e.ABS_HAT0Y, HAT)],
}

HOLD = 0.12  # seconds a tapped direction is held
BUTTON_KEYS = {"j": e.BTN_A, "k": e.BTN_B, "p": e.BTN_START}
STICK_KEYS = {"a": (e.ABS_X, -32767), "d": (e.ABS_X, 32767),
              "w": (e.ABS_Y, -32767), "s": (e.ABS_Y, 32767)}
HAT_KEYS = {"\x1b[A": (e.ABS_HAT0Y, -1), "\x1b[B": (e.ABS_HAT0Y, 1),
            "\x1b[D": (e.ABS_HAT0X, -1), "\x1b[C": (e.ABS_HAT0X, 1)}


def tap_button(ui: UInput, code: int) -> None:
    ui.write(e.EV_KEY, code, 1)
    ui.syn()
    time.sleep(HOLD)
    ui.write(e.EV_KEY, code, 0)
    ui.syn()


def tap_axis(ui: UInput, axis: int, value: int) -> None:
    ui.write(e.EV_ABS, axis, value)
    ui.syn()
    time.sleep(HOLD)
    ui.write(e.EV_ABS, axis, 0)
    ui.syn()


def read_key() -> str:
    ch = sys.stdin.read(1)
    if ch == "\x1b":
        while select.select([sys.stdin], [], [], 0.02)[0]:
            ch += sys.stdin.read(1)
            if len(ch) == 3:
                break
    return ch


def main() -> None:
    try:
        ui = UInput(CAPS, name="Microsoft X-Box 360 pad", vendor=0x045E, product=0x028E, version=0x0110)
    except PermissionError:
        sys.exit("No access to /dev/uinput. Run: sudo modprobe uinput && sudo chmod a+rw /dev/uinput")
    print("Virtual pad ready. Keys: arrows=D-pad  WASD=stick  j=A  k=B  p=Start  q=quit")
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            key = read_key()
            if key == "q":
                break
            if key in BUTTON_KEYS:
                tap_button(ui, BUTTON_KEYS[key])
            elif key in STICK_KEYS:
                tap_axis(ui, *STICK_KEYS[key])
            elif key in HAT_KEYS:
                tap_axis(ui, *HAT_KEYS[key])
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        ui.close()


if __name__ == "__main__":
    main()
