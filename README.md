# Air-Scribble Armband

Draw in the air. Watch it show up on screen.

This started as a simple idea: strap an armband with an EMG sensor and a motion sensor onto your arm, flex to lower a "pen," move your arm to draw, and watch the line appear live in a window. That's basically it. No mouse, no tablet, just your arm and your muscle.

## What it actually does

The armband streams sensor data (either over serial from a wired connection, or over UDP from something like an ESP32 talking wifi) and the script turns that into a moving cursor on a Pygame canvas. Flex your muscle hard enough and the "pen" goes down. Move your arm and it draws. Relax and the pen lifts back up.

Under the hood it's running the sensor reading on a background thread so the drawing loop never stalls waiting on serial or network I/O. Every frame it drains the queue and just grabs the newest reading, on purpose, so a burst of sensor data doesn't pile up and make your drawing lag behind your actual arm movement.

## Two data formats it understands

The parser is flexible about your line format, comma or space separated, doesn't matter. It figures out which one you're sending based on how many numbers show up per line:

- `emg,ax,ay,az,gx,gy,gz` — raw accelerometer and gyro data. Accelerometer deltas get scaled and integrated into cursor movement, so this is more of a "keep pushing your arm to keep moving" feel.
- `emg,yaw,pitch,roll` — orientation data. Yaw maps straight to X, pitch maps straight to Y, so your arm's actual orientation is your cursor position. This one feels more direct.

Either way the EMG value is what controls pen up/down, using a threshold with hysteresis built in so you don't get flickering on and off right at the edge of the threshold.

## Controls

- `C` — clear the canvas
- `S` — save a screenshot (drops a timestamped PNG right in the folder)
- `ESC` or just closing the window — quit

There's a little overlay in the corner of the window showing your current mode, EMG threshold, and whether the pen thinks it's up or down, handy for tuning things live instead of guessing.

## Running it

```
pip install pygame pyserial
python mngrag.py --mode udp
```

or if you're wired in over serial:

```
python mngrag.py --mode serial --serial-port /dev/ttyUSB0
```

Everything's tunable from the command line: baud rate, UDP port, EMG threshold, all have sane defaults but you'll probably want to tweak the EMG threshold for your specific sensor and however hard you flex.

## Also in here

There's a second script, `proj.py`, that's a smaller side experiment: same EMG sensor, but instead of driving a cursor it maps how hard you're flexing straight to an audio tone, so you can literally hear your muscle activity. Different output, same core idea of turning EMG into something you can feel in real time.

## Why I built this

I wanted something where the feedback loop was instant and physical, flex your arm, see it happen right there on screen, not a chart, not a number, an actual drawing you made with your muscle. The EMG threshold and hysteresis and position smoothing all came out of just how noisy and twitchy raw sensor data actually is once you're staring at it live. Getting a clean, non-jittery line out of a signal that jumps around that much was most of the fun of building this.
