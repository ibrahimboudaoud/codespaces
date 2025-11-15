"""
Air-Scribble Armband — Real-time drawing app.

Supports:
 - Serial input (pyserial)
 - UDP input (socket)

Expected line formats (CSV, newline terminated):
 1) emg,ax,ay,az,gx,gy,gz
 2) emg,yaw,pitch,roll

Controls in the Pygame window:
 - C : clear canvas
 - S : save screenshot (saved as 'air_scribble_<timestamp>.png')
 - ESC or window close : quit

Dependencies:
 pip install pygame pyserial
"""

import sys
import threading
import queue
import time
import math
import pygame
import argparse
import os
from datetime import datetime

# Optional import for serial backend
try:
    import serial
except Exception:
    serial = None

# --------- Configuration ----------
DEFAULT_BAUD = 115200
EMG_THRESHOLD = 400        # default threshold for pen-down (tune for your sensor)
EMG_HYSTERESIS = 25       # hysteresis to avoid flicker
SMOOTHING = 0.85          # smoothing factor for position (0..1)
SENSITIVITY = 200         # maps motion -> screen pixels (tune)
UDP_PORT = 5005
# ---------------------------------

DataItem = dict  # simple alias

def parse_line(line: str):
    """
    Parse one incoming line and return a dict:
      { 'emg': float, 'type': 'raw'/'orient', 'acc': (ax,ay,az) or None, 'gyro':(...), 'orient': (yaw,pitch,roll) or None }
    Returns None if cannot parse.
    """
    # sanitize
    s = line.strip()
    if not s:
        return None
    # allow both comma and space separated
    parts = [p for p in s.replace(',', ' ').split() if p]
    # try floats
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None

    if len(nums) >= 7:
        # assume emg,ax,ay,az,gx,gy,gz
        emg, ax, ay, az, gx, gy, gz = nums[:7]
        return {'emg': emg, 'type': 'raw', 'acc': (ax, ay, az), 'gyro': (gx, gy, gz), 'orient': None}
    elif len(nums) >= 4:
        # assume emg,yaw,pitch,roll
        emg, yaw, pitch, roll = nums[:4]
        return {'emg': emg, 'type': 'orient', 'acc': None, 'gyro': None, 'orient': (yaw, pitch, roll)}
    else:
        return None

# ---------------- Input backends ----------------
def serial_reader_thread(port, baud, q, stop_event):
    if serial is None:
        print("pyserial not installed or failed import. Serial backend disabled.")
        stop_event.set()
        return
    try:
        ser = serial.Serial(port, baud, timeout=1)
        print(f"[serial] opened {port} @ {baud}")
    except Exception as e:
        print(f"[serial] failed to open {port}: {e}")
        stop_event.set()
        return
    with ser:
        while not stop_event.is_set():
            try:
                line = ser.readline().decode(errors='ignore')
            except Exception as e:
                print(f"[serial] read error: {e}")
                break
            if not line:
                continue
            parsed = parse_line(line)
            if parsed:
                q.put(parsed)
    print("[serial] thread exiting")

import socket
def udp_reader_thread(bind_ip, bind_port, q, stop_event):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind_ip, bind_port))
    sock.settimeout(1.0)
    print(f"[udp] listening on {bind_ip}:{bind_port}")
    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"[udp] error: {e}")
            break
        line = data.decode(errors='ignore').strip()
        parsed = parse_line(line)
        if parsed:
            q.put(parsed)
    sock.close()
    print("[udp] thread exiting")

# -------------------------------------------------
def orient_to_xy(yaw, pitch, roll, screen_w, screen_h):
    """
    Convert yaw/pitch/roll (degrees) to screen coordinates.
    This is a simple projection:
     - yaw -> x
     - pitch -> y
    Center is (screen_w/2, screen_h/2)
    """
    x = (yaw / 180.0) * (screen_w / 2) + screen_w / 2
    y = -(pitch / 90.0) * (screen_h / 2) + screen_h / 2
    return x, y

def acc_to_xy(ax, ay, az, screen_w, screen_h, last_pos=None, sensitivity=SENSITIVITY):
    """
    Convert small accelerometer movement deltas into cursor movement.
    We integrate gyro-ish motion by simple scaling of ax/ay to pixels per update.
    If last_pos provided, return new position clamped to screen.
    """
    # map ax/ay (assuming small) to pixel delta
    dx = ax * sensitivity
    dy = -ay * sensitivity
    if last_pos is None:
        x = screen_w / 2 + dx
        y = screen_h / 2 + dy
    else:
        x = last_pos[0] + dx
        y = last_pos[1] + dy
    # clamp
    x = max(0, min(screen_w - 1, x))
    y = max(0, min(screen_h - 1, y))
    return x, y

def main():
    parser = argparse.ArgumentParser(description="Air Scribble - live drawing from ESP32 sensors")
    parser.add_argument('--mode', choices=['serial', 'udp'], default='udp')
    parser.add_argument('--serial-port', default='/dev/ttyUSB0', help='Serial port (e.g. COM3 or /dev/ttyUSB0)')
    parser.add_argument('--baud', type=int, default=DEFAULT_BAUD)
    parser.add_argument('--udp-ip', default='0.0.0.0', help='Bind IP for UDP')
    parser.add_argument('--udp-port', type=int, default=UDP_PORT)
    parser.add_argument('--emg-threshold', type=float, default=EMG_THRESHOLD)
    args = parser.parse_args()

    data_q = queue.Queue()
    stop_event = threading.Event()
    reader = None
    if args.mode == 'serial':
        t = threading.Thread(target=serial_reader_thread, args=(args.serial_port, args.baud, data_q, stop_event), daemon=True)
        t.start()
        reader = t
    else:
        t = threading.Thread(target=udp_reader_thread, args=(args.udp_ip, args.udp_port, data_q, stop_event), daemon=True)
        t.start()
        reader = t

    pygame.init()
    screen_w, screen_h = 1280, 720
    screen = pygame.display.set_mode((screen_w, screen_h))
    pygame.display.set_caption("Air-Scribble Armband")
    clock = pygame.time.Clock()
    canvas = pygame.Surface((screen_w, screen_h))
    canvas.fill((255, 255, 255))
    pen_down = False
    emg_threshold = args.emg_threshold
    last_emg_state = False
    last_pos = (screen_w/2, screen_h/2)
    smooth_pos = list(last_pos)
    running = True

    # drawing style
    pen_color = (10, 10, 10)
    pen_radius = 3

    # optional calibration / offset for sensor drift (simple)
    last_timestamp = time.time()
    # main loop
    while running:
        now = time.time()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_c:
                    canvas.fill((255,255,255))
                elif ev.key == pygame.K_s:
                    fn = f"air_scribble_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    pygame.image.save(canvas, fn)
                    print(f"Saved {fn}")

        # consume all queued sensor packets (process latest to reduce lag)
        latest = None
        while not data_q.empty():
            try:
                latest = data_q.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            emg = float(latest.get('emg', 0.0))
            # hysteresis
            if not pen_down and emg > emg_threshold + EMG_HYSTERESIS:
                pen_down = True
            elif pen_down and emg < emg_threshold - EMG_HYSTERESIS:
                pen_down = False

            if latest['type'] == 'orient' and latest['orient']:
                yaw, pitch, roll = latest['orient']
                tx, ty = orient_to_xy(yaw, pitch, roll, screen_w, screen_h)
                target = (tx, ty)
            elif latest['type'] == 'raw' and latest['acc']:
                ax, ay, az = latest['acc']
                # convert acceleration to small delta movement
                target = acc_to_xy(ax, ay, az, screen_w, screen_h, last_pos, sensitivity=SENSITIVITY/10.0)
            else:
                target = last_pos

            # smoothing
            smooth_pos[0] = smooth_pos[0] * SMOOTHING + target[0] * (1 - SMOOTHING)
            smooth_pos[1] = smooth_pos[1] * SMOOTHING + target[1] * (1 - SMOOTHING)
            curr_pos = (smooth_pos[0], smooth_pos[1])

            if pen_down:
                pygame.draw.circle(canvas, pen_color, (int(curr_pos[0]), int(curr_pos[1])), pen_radius)
                # draw a line from last_pos to curr_pos for continuity
                pygame.draw.line(canvas, pen_color, (int(last_pos[0]), int(last_pos[1])), (int(curr_pos[0]), int(curr_pos[1])), pen_radius*2)

            last_pos = curr_pos

        # render
        screen.fill((200, 200, 200))
        screen.blit(canvas, (0,0))
        # draw UI overlay: threshold + pen state
        font = pygame.font.SysFont(None, 24)
        txt = font.render(f"Mode: {args.mode}  EMG threshold: {emg_threshold}  Pen: {'DOWN' if pen_down else 'UP'}  (C=clear S=save)", True, (0,0,0))
        screen.blit(txt, (10, 10))
        pygame.display.flip()
        clock.tick(60)

    # shutdown
    stop_event.set()
    # give threads a moment
    time.sleep(0.2)
    pygame.quit()
    print("Exiting.")

if __name__ == "__main__":
    main()
