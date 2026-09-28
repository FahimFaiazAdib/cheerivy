"""
CHEERIVY — Vision AI (Layer B)

    python3 main.py --sim        # virtual arena, no hardware needed
    python3 main.py              # phone camera + HC-05
    python3 main.py --cam 1      # force a camera index
    python3 main.py --no-send    # real camera, but never talk to the robot (tracking test)

    python3 main.py --no-show    # only the vision AI window, no live show
    python3 main.py --no-voice   # live show without George's commentary

Keys:  space start/pause AI (starts PAUSED)   a / d drive carriage by hand (while paused)
       x swap left/right   1/2/3 difficulty   f test-fire   z freeze   c recalibrate   q quit
Mouse: click the red tape on the right-hand (top-down) view to lock its colour.

Live show window (see show/TARGET.md):
       connecting screen (waits for the robot; s = play without it) -> 1 / 2 choose single or
       two players -> type names + ENTER: the robot starts that game.
       k kick off without the robot   h / j goal for player / AI   e end match   v fullscreen
       r replay highlights   ENTER rematch   n new game (back to the menu)
The AI unpauses by itself at kick-off and pauses again at full time. In two-player games it
stays paused: the camera only watches and shows the prediction.
"""
import argparse
import os
import time

import cv2
import numpy as np

import config as C
from calibrate import Calibration, run_calibration
from camera import Camera, SimArena
from controller import Controller
from link import Link
from predictor import Predictor
from tracker import Tracker
from show import Show

os.chdir(os.path.dirname(os.path.abspath(__file__)))  # calib.json lives next to this file


def to_px(p):
    return int(p[0] * C.PX_PER_CM), int(p[1] * C.PX_PER_CM)


def draw(flat, arena, ball, carriage_x, pred, ctrl, cmd, status, fps, link, paused):
    s = C.PX_PER_CM
    h, w = flat.shape[:2]
    cv2.polylines(flat, [np.int32([to_px(p) for p in arena.poly])], True, (255, 150, 0), 1)
    y_line = int(C.AI_LINE_Y * s)
    cv2.line(flat, (0, y_line), (w, y_line), (255, 150, 0), 1)
    cv2.line(flat, (0, int(C.CARRIAGE_BAND_CM * s)), (w, int(C.CARRIAGE_BAND_CM * s)), (180, 180, 180), 1)

    path = pred.path()
    if path:
        cv2.polylines(flat, [np.int32([to_px(p) for p in path])], False, (0, 200, 0), 2)
        cv2.circle(flat, to_px(path[-1]), 8, (0, 200, 0), -1)
    if ball:
        cv2.circle(flat, to_px(ball), int(C.BALL_RADIUS * s) + 4, (0, 255, 255), 2)
        tip = (ball[0] + pred.vx * 0.2, ball[1] + pred.vy * 0.2)
        cv2.arrowedLine(flat, to_px(ball), to_px(tip), (255, 0, 255), 2)
    cv2.line(flat, (int(ctrl.target * s), 0), (int(ctrl.target * s), y_line + 8), (0, 200, 0), 2)
    if carriage_x is not None:
        cx = int(carriage_x * s)
        half = int(C.CARRIAGE_W / 2 * s)
        cv2.rectangle(flat, (cx - half, 2), (cx + half, y_line), (0, 0, 255), 2)

    speed = (pred.vx ** 2 + pred.vy ** 2) ** 0.5
    lines = [status,
             f"CMD {cmd}  | {link.mode}{f' echo {link.echo_count}' if link.ser else ''}{' L/R SWAPPED' if link.swap else ''} | level {ctrl.level} | {fps:4.1f} fps",
             f"ball {'--' if not ball else f'{ball[0]:4.1f},{ball[1]:4.1f}'} cm  v={speed:4.0f} cm/s",
             f"carriage {'--' if carriage_x is None else f'{carriage_x:4.1f}'} cm  target {ctrl.target:4.1f}"]
    panel = np.zeros((22 * len(lines) + 10, w, 3), np.uint8)
    for i, t in enumerate(lines):
        cv2.putText(panel, t, (8, 22 * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return np.vstack([flat, panel])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="virtual arena, no hardware")
    ap.add_argument("--cam", type=int, default=C.CAMERA_INDEX)
    ap.add_argument("--port", help="serial port of the HC-05 (auto-detect if omitted)")
    ap.add_argument("--no-send", action="store_true", help="never send commands to the robot")
    ap.add_argument("--no-show", action="store_true", help="no live show window")
    ap.add_argument("--no-voice", action="store_true", help="live show without voice commentary")
    ap.add_argument("--match-seconds", type=int, help="match length for the show's clock (default 180, sim 60)")
    args = ap.parse_args()

    match_seconds = args.match_seconds or (60 if args.sim else 180)
    source = SimArena(match_seconds) if args.sim else Camera(args.cam)
    if args.sim:
        cal = Calibration(source.corners, source.wall_px)
        link = Link(sink=source, enabled=False)  # simulator never touches the real HC-05
    else:
        cal = Calibration.load() or run_calibration(source)
        if cal is None:
            return
        link = Link(port=args.port, enabled=not args.no_send)

    tracker, pred, ctrl = Tracker(cal.arena), Predictor(cal.arena), Controller()
    paused = not args.sim  # real robot: nothing moves until you press space
    manual, manual_until = "S", 0.0
    win = "CHEERIVY vision AI"
    cv2.namedWindow(win)
    flat_holder = {}

    def on_mouse(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN and "img" in flat_holder:
            ox = flat_holder["offset_x"]
            if x >= ox and y < flat_holder["img"].shape[0]:
                tracker.sample_red(flat_holder["img"], x - ox, y)

    mouse_ready = False
    last_seq, fps, t_prev = -1, 0.0, time.time()

    show, show_win, show_seq, show_phase = None, "CHEERIVY LIVE", -1, None
    if not args.no_show:
        show = Show(cal, voice=not args.no_voice, match_seconds=match_seconds,
                    send=link.send, robot=not args.no_send)
        cv2.namedWindow(show_win, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(show_win, 1280, 720)
        show_phase = show.phase

    try:
        while True:
            frame, stamp, seq = source.read()
            if seq == last_seq:
                time.sleep(0.001)
                continue
            last_seq = seq
            now = time.time()
            fps = 0.9 * fps + 0.1 / max(now - t_prev, 1e-3)
            t_prev = now

            flat = cal.warp(frame)
            flat_clean = flat.copy() if show else None
            ball, carriage_x = tracker.process(flat)
            if ball:
                pred.update(stamp, *ball)
            elif pred.hist and stamp - pred.hist[-1][0] > 0.25:
                pred.reset()  # lost the ball for a while — forget old motion

            cmd, fire, status = ctrl.update(pred, carriage_x, now)
            if paused:
                cmd, fire = (manual if now < manual_until else "S"), False
                status = "PAUSED - space to start AI, a/d to drive by hand"
            link.move(cmd)
            if fire:
                link.send("F")
            mcu_lines = link.read_lines() + (source.pop_lines() if args.sim else [])
            for line in mcu_lines:
                if line != "READY" and not (args.sim and line.startswith("G ")):
                    print("[mcu]", line)
                if show:
                    show.on_line(line)

            if show:
                show.link_state = link.mode
                show.update(frame, flat_clean, stamp,
                            {"ball": ball, "vx": pred.vx, "vy": pred.vy, "path": pred.path(),
                             "hit": pred.intercept(), "carriage_x": carriage_x, "target": ctrl.target,
                             "status": status})
                # the AI plays during a match and rests before / after it
                if show.phase != show_phase:
                    if show.phase == "LIVE":
                        paused = show.game == 2     # two players: the AI only watches
                    elif show_phase == "LIVE":
                        paused = True
                    show_phase = show.phase
                seq, img = show.image()
                if img is not None and seq != show_seq:
                    cv2.imshow(show_win, img)
                    show_seq = seq

            flat_holder["img"] = flat.copy()
            view = draw(flat, cal.arena, ball, carriage_x, pred, ctrl, cmd, status, fps, link, paused)
            cam_small = cv2.resize(frame, (int(frame.shape[1] * view.shape[0] / frame.shape[0]), view.shape[0]))
            flat_holder["offset_x"] = cam_small.shape[1]
            cv2.imshow(win, np.hstack([cam_small, view]))
            if not mouse_ready:  # macOS: attach only after the window has shown an image
                cv2.setMouseCallback(win, on_mouse)
                mouse_ready = True

            k = cv2.waitKey(1) & 0xFF
            if k == 255:
                continue
            if show and show.on_key(k):
                continue
            if k == ord("v") and show:
                show.fullscreen = not show.fullscreen
                cv2.setWindowProperty(show_win, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_FULLSCREEN if show.fullscreen else cv2.WINDOW_NORMAL)
            elif k == ord("q"):
                break
            elif k == ord(" "):
                paused = not paused
            elif k in (ord("a"), ord("d")) and paused:
                manual, manual_until = ("L" if k == ord("a") else "R"), time.time() + 0.25
            elif k == ord("x"):
                link.swap = not link.swap
                print(f"[link] L/R swap {'ON' if link.swap else 'OFF'} (set SWAP_LR = {link.swap} in config.py to keep it)")
            elif k in (ord("1"), ord("2"), ord("3")):
                ctrl.set_difficulty(int(chr(k)))
            elif k == ord("f"):
                link.send("F")
            elif k == ord("z"):
                link.send("Z")
            elif k == ord("c") and not args.sim:
                cal = run_calibration(source) or cal
                tracker, pred = Tracker(cal.arena), Predictor(cal.arena)
    finally:
        if show:
            show.close()
        link.close()
        source.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
