"""
CHEERIVY — Vision AI (Layer B)

    python3 main.py              # phone camera + HC-05: the new game opens in the browser (F = fullscreen)
    python3 main.py --old-show   # ... with the old OpenCV show window instead
    python3 main.py --sim        # virtual arena, no hardware needed (old show window)
    python3 main.py --cam 1      # force a camera index
    python3 main.py --no-send    # real camera, but never talk to the robot (tracking test)

    python3 main.py --no-show    # only the vision AI window, no live show
    python3 main.py --no-voice   # live show without George's commentary

Keys:  space start/pause AI (starts PAUSED)   a / d drive carriage by hand (while paused)
       x swap left/right (AI carriage)   y swap left/right (player 1's carriage, AI vs AI)
       1/2/3 difficulty   f test-fire   z freeze   c recalibrate   q quit
       b  AI vs AI on/off: the camera AI drives PLAYER 1's carriage too (blue tape on it);
          the next match started from the show is played AI vs AI
       servo tuning (saved on the robot):    p  switch player 1 <-> player 2
             [ / ]  rest angle -/+ 1    - / =  swing smaller / bigger    /  test strike
       m  robot speaker test (DFPlayer): a commentary clip from /MP3 every 5 s; m again = stop
       n  DFPlayer "next track" (same as touching its IO2 pin to GND)
       , / .  robot speaker volume down / up (0..30)
                                             /  test strike
Mouse, in the right-hand (top-down) view: LEFT-click a carriage tape to lock its colour
       (top half = AI carriage, bottom half = player 1's carriage in AI vs AI),
       RIGHT-click the ball to lock the ball's colour (colours are set in config.py).

Live show window (see show/TARGET.md):
       connecting screen (waits for the robot; s = play without it) -> 1 / 2 choose single or
       two players -> type names + ENTER: the robot starts that game.
       k kick off without the robot   h / j goal for player / AI   e end match   v fullscreen
       r replay highlights   ENTER rematch   n new game (back to the menu)
The AI unpauses by itself at kick-off and pauses again at full time. In two-player games it
stays paused: the camera only watches and shows the prediction.
"""
import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

import config as C
from goals import GoalWatcher
from calibrate import Calibration, run_calibration
from camera import Camera, SimArena
from controller import Controller
from arena import Arena
from link import Link
from predictor import Predictor
from tracker import Tracker
from show import Show

os.chdir(os.path.dirname(os.path.abspath(__file__)))  # calib.json lives next to this file


def to_px(p):
    return int(p[0] * C.PX_PER_CM), int(p[1] * C.PX_PER_CM)


def mirrored(arena):
    """The board seen from player 1's end: the same AI then plays player 1's side (AI vs AI)."""
    return Arena([(x, C.ARENA_H - y) for x, y in arena.poly])


def draw(flat, arena, ball, carriage_x, pred, ctrl, cmd, status, fps, link, paused, p1=None):
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

    if p1:                                  # AI vs AI: player 1's side, drawn the right way up
        p1_x, pred1, ctrl1 = p1
        y1 = int((C.ARENA_H - C.AI_LINE_Y) * s)
        path1 = pred1.path()
        if path1:
            cv2.polylines(flat, [np.int32([to_px((x, C.ARENA_H - y)) for x, y in path1])], False, (255, 120, 0), 2)
            cv2.circle(flat, to_px((path1[-1][0], C.ARENA_H - path1[-1][1])), 8, (255, 120, 0), -1)
        cv2.line(flat, (int(ctrl1.target * s), y1 - 8), (int(ctrl1.target * s), h), (255, 120, 0), 2)
        if p1_x is not None:
            half = int(C.CARRIAGE_W / 2 * s)
            cv2.rectangle(flat, (int(p1_x * s) - half, y1), (int(p1_x * s) + half, h - 2), (255, 0, 0), 2)

    speed = (pred.vx ** 2 + pred.vy ** 2) ** 0.5
    lines = [status,
             f"CMD {cmd}  | {link.mode}{f' echo {link.echo_count}' if link.ser else ''}{' L/R SWAPPED' if link.swap else ''} | level {ctrl.level} | {fps:4.1f} fps",
             f"ball {'--' if not ball else f'{ball[0]:4.1f},{ball[1]:4.1f}'} cm  v={speed:4.0f} cm/s",
             f"carriage {'--' if carriage_x is None else f'{carriage_x:4.1f}'} cm  target {ctrl.target:4.1f}",
             f"motor {ctrl.motor_speed:3.0f} cm/s  rail {ctrl.rail_lo:4.1f}..{ctrl.rail_hi:4.1f} cm"]
    if p1:
        p1_x, pred1, ctrl1 = p1
        lines.append(f"AI vs AI  P1 carriage {'--' if p1_x is None else f'{p1_x:4.1f}'} cm  target {ctrl1.target:4.1f}"
                     f"  motor {ctrl1.motor_speed:3.0f}{'  L/R SWAPPED' if link.swap1 else ''}")
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
    ap.add_argument("--robot-voice", action="store_true", help="play the commentary on the robot's speaker (DFPlayer)")
    ap.add_argument("--match-seconds", type=int, help="match length for the show's clock (default 180, sim 60)")
    ap.add_argument("--old-show", action="store_true", help="the old OpenCV show window instead of the browser game")
    ap.add_argument("--screen-port", type=int, default=8316, help="web port of the browser game")
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
    # AI vs AI: a second AI for player 1's carriage. It sees the board mirrored (its own end on top),
    # so it's exactly the same predictor + controller as the AI side's.
    aivai = False
    pred1, ctrl1 = Predictor(mirrored(cal.arena)), Controller()
    paused = not args.sim  # real robot: nothing moves until you press space
    manual, manual_until = "S", 0.0
    win = "CHEERIVY vision AI"
    cv2.namedWindow(win)
    flat_holder = {}

    def on_mouse(event, x, y, *_):
        if event in (cv2.EVENT_LBUTTONDOWN, cv2.EVENT_RBUTTONDOWN) and "img" in flat_holder:
            ox = flat_holder["offset_x"]
            if x >= ox and y < flat_holder["img"].shape[0]:
                if event == cv2.EVENT_LBUTTONDOWN:
                    tracker.sample_carriage(flat_holder["img"], x - ox, y)
                else:
                    tracker.sample_ball(flat_holder["img"], x - ox, y)

    mouse_ready = False
    last_seq, fps, t_prev = -1, 0.0, time.time()

    # The new browser game (cheerivy_ai/ui): it runs the match; the robot follows it in "screen mode".
    live = None
    if not args.no_show and not args.old_show and not args.sim:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui"))
        from live import LiveGame
        live = LiveGame(link, port=args.screen_port, sound=not args.no_voice)

    show, show_win, show_seq, show_phase = None, "CHEERIVY LIVE", -1, None
    if not args.no_show and not live:
        show = Show(cal, voice=not args.no_voice, match_seconds=match_seconds,
                    send=link.send, robot=not args.no_send, robot_voice=args.robot_voice)
        cv2.namedWindow(show_win, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
        cv2.resizeWindow(show_win, 1280, 720)
        show_phase = show.phase

    goals = GoalWatcher() if (C.CAMERA_GOALS and not args.sim) else None
    servos, p1_asked = {1: None, 2: None}, False   # each player's servo angles, as reported by the robot
    tune = 1                                        # which player's servo the [ ] - = / keys change
    # The angles are also kept here on the laptop: burning the chip erases its EEPROM, so on every
    # connect the saved angles are sent back to the robot.
    ANGLES_FILE = "servo_angles.json"
    try:
        with open(ANGLES_FILE) as f:
            saved_angles = {int(k): v for k, v in json.load(f).items()}
    except (OSError, ValueError):
        saved_angles = {}
    TUNE_CMD = {1: ("H", "J", "U"), 2: ("Q", "W", "T")}   # rest, strike, test/report
    sound_test, sound_next_t, sound_i = False, 0.0, 0
    df_volume = C.ROBOT_VOLUME
    sd_tracks = {}
    try:
        with open(os.path.join("show", "voice_bank", "sd_tracks.json")) as f:
            sd_tracks = json.load(f)
    except (OSError, ValueError):
        pass
    crowd_n = sd_tracks.get("crowd/ambience.wav", 201)
    test_clips = sorted(n for rel, n in sd_tracks.items() if not rel.startswith(("crowd/", "names/"))) \
        or list(range(1, 201))
    cam_score = {"H": 0, "A": 0}
    in_match = False
    was_debug = False
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
            flat_clean = flat.copy() if (show or live) else None
            ball, carriage_x, p1_x = tracker.process(flat)
            if ball:
                pred.update(stamp, *ball)
            elif pred.hist and stamp - pred.hist[-1][0] > 0.25:
                pred.reset()  # lost the ball for a while — forget old motion
            if aivai:
                if ball:
                    pred1.update(stamp, ball[0], C.ARENA_H - ball[1])
                elif pred1.hist and stamp - pred1.hist[-1][0] > 0.25:
                    pred1.reset()

            if live:                                # the browser game decides when the AI plays
                if (live.mode == "aivai") != aivai:
                    aivai = live.mode == "aivai"
                    tracker.find_p1 = aivai
                    pred1.reset()
                    if not aivai:
                        link.move1("S")
                        link.move1(None)
                if live.difficulty != ctrl.level:
                    ctrl.set_difficulty(live.difficulty)
                    ctrl1.set_difficulty(live.difficulty)
                paused = not live.ai_plays()
                if live.want_recalibrate and not args.sim:
                    live.want_recalibrate = False
                    cal = run_calibration(source) or cal
                    tracker, pred = Tracker(cal.arena), Predictor(cal.arena)
                    pred1 = Predictor(mirrored(cal.arena))
                    tracker.find_p1 = aivai
                    continue
            cmd, fire, status = ctrl.update(pred, carriage_x, now)
            if ctrl.swap_request:
                ctrl.swap_request = False
                link.swap = not link.swap
                print(f"[ai] carriage moved the wrong way twice -> L/R swap {'ON' if link.swap else 'OFF'} automatically")
            if paused:
                cmd, fire = (manual if now < manual_until else "S"), False
                status = "PAUSED - space to start AI, a/d to drive by hand"
            debug = bool(live and live.debug)
            if debug:                               # Settings > Debug: the keyboard drives both carriages
                cmd, fire = live.manual_cmd(2, now), False
                status = "DEBUG: motor & striker test (joysticks / W A S D / arrows)"
                link.move1(live.manual_cmd(1, now))
            elif was_debug and not aivai:
                link.move1("S")
                link.move1(None)
            was_debug = debug
            link.move(cmd)
            if aivai and not debug:                 # player 1's carriage, driven by the second AI
                cmd1, fire1, status1 = ctrl1.update(pred1, p1_x, now)
                if ctrl1.swap_request:
                    ctrl1.swap_request = False
                    link.swap1 = not link.swap1
                    print(f"[ai] player 1's carriage moved the wrong way -> its L/R swap "
                          f"{'ON' if link.swap1 else 'OFF'} (set SWAP_LR_P1 = {link.swap1} in config.py to keep it)")
                if paused:
                    cmd1, fire1 = "S", False
                link.move1(cmd1)
                if fire1:
                    link.send("G")
            if sound_test and now >= sound_next_t:
                n = test_clips[sound_i % len(test_clips)]
                sound_i += 1
                link.send(f"P{n};")
                print(f"[sound] playing /MP3/{n:04d}.mp3")
                sound_next_t = now + 5.0
            if not p1_asked and link.ser and not args.sim:
                p1_asked = True
                link.send(f"V{df_volume};")                # robot speaker volume from config.py
                for who, (c_rest, c_strike, c_test) in TUNE_CMD.items():
                    a = saved_angles.get(who)
                    if a:                               # put the laptop's saved angles back on the robot
                        link.send(f"{c_rest}{a['rest']};{c_strike}{a['strike']};")
                        print(f"[servo] sending player {who}'s saved angles to the robot: "
                              f"rest {a['rest']}°, strike {a['strike']}°")
                    else:
                        link.send(f"{c_test}0;")        # the robot replies "P<n>SERVO <rest> <strike>"
            if fire:
                link.send("F")
            mcu_lines = link.read_lines() + (source.pop_lines() if args.sim else [])
            for line in mcu_lines:
                if live and line.startswith("G ") and goals:
                    goals = None
                    print("[goal] the robot's goal sensors work -> camera goal detection OFF")
                if live and live.on_line(line):
                    continue
                if line.startswith(("P1SERVO", "P2SERVO")):
                    try:
                        _, r, s_ = line.split()
                        who = int(line[1])
                        servos[who] = {"rest": int(r), "strike": int(s_)}
                        saved_angles[who] = servos[who]
                        try:
                            with open(ANGLES_FILE, "w") as f:
                                json.dump(saved_angles, f)
                        except OSError:
                            pass
                        mark = "  <- [ ] - = / tune this one" if who == tune else ""
                        print(f"[servo] player {who}: rest {r}°, strike {s_}°, swing {abs(int(r) - int(s_))}° "
                              f"(saved on the robot){mark}")
                    except ValueError:
                        pass
                    continue
                if line != "READY" and not (args.sim and line.startswith("G ")):
                    print("[mcu]", line)
                if line.startswith("G ") and goals and not args.sim:
                    goals = None
                    print("[goal] the robot's goal sensors work -> camera goal detection OFF")
                if line.startswith("START"):
                    in_match = True
                elif line.startswith("END"):
                    in_match = False
                elif line.startswith("T "):
                    in_match = True
                if show:
                    show.on_line(line)

            # Camera goals (until the laser sensors are wired): only during a match.
            if goals and live:
                if live.in_play():
                    who = goals.update(stamp, ball, pred.vy)
                    if who:
                        print(f"[goal] camera: {'player 1' if who == 'H' else 'AI side'} scores")
                        live.goal(who, camera=True)
            elif goals and in_match:
                who = goals.update(stamp, ball, pred.vy)
                if who:
                    cam_score[who] += 1
                    print(f"[goal] camera: {'HUMAN' if who == 'H' else 'AI'} scores  "
                          f"({cam_score['H']} - {cam_score['A']})")
                    if show:
                        show.on_line(f"G {who} {cam_score['H']} {cam_score['A']}")
            if goals and any(x.startswith("START") for x in mcu_lines):
                goals, cam_score = GoalWatcher(), {"H": 0, "A": 0}     # new match: 0 - 0

            if live:
                r = lambda v: round(float(v), 1)
                board = {"ball": [r(ball[0]), r(ball[1])] if ball else None,
                         "vel": [r(pred.vx), r(pred.vy)],
                         "path": [[r(x), r(y)] for x, y in pred.path()],
                         "ai_x": None if carriage_x is None else r(carriage_x),
                         "p1_x": None if (p1_x is None or not aivai) else r(p1_x),
                         "path1": [[r(x), r(C.ARENA_H - y)] for x, y in pred1.path()] if aivai else []}
                live.frame(stamp, flat_clean, board, pred.slope)

            if show:
                show.link_state = link.mode
                show.update(frame, flat_clean, stamp,
                            {"ball": ball, "vx": pred.vx, "vy": pred.vy, "path": pred.path(),
                             "hit": pred.intercept(), "carriage_x": carriage_x, "target": ctrl.target,
                             "status": status})
                # the AI plays during a match and rests before / after it
                if show.phase != show_phase:
                    if show.phase == "LIVE":
                        paused = show.game == 2 and not aivai   # two players: the AI only watches
                    elif show_phase == "LIVE":
                        paused = True
                    show_phase = show.phase
                seq, img = show.image()
                if img is not None and seq != show_seq:
                    cv2.imshow(show_win, img)
                    show_seq = seq

            flat_holder["img"] = flat.copy()
            view = draw(flat, cal.arena, ball, carriage_x, pred, ctrl, cmd, status, fps, link, paused,
                        (p1_x, pred1, ctrl1) if aivai else None)
            cam_small = cv2.resize(frame, (int(frame.shape[1] * view.shape[0] / frame.shape[0]), view.shape[0]))
            flat_holder["offset_x"] = cam_small.shape[1]
            cv2.imshow(win, np.hstack([cam_small, view]))
            if not mouse_ready:  # macOS: attach only after the window has shown an image
                cv2.setMouseCallback(win, on_mouse)
                mouse_ready = True

            k = cv2.waitKey(1) & 0xFF
            if k == 255:
                continue
            if k in (ord(","), ord(".")) and not (show and show.phase == "NAMES"):
                df_volume = max(0, min(30, df_volume + (2 if k == ord(".") else -2)))
                link.send(f"V{df_volume};")
                print(f"[sound] robot speaker volume {df_volume} / 30  (set ROBOT_VOLUME = {df_volume} in config.py to keep it)")
                continue
            if k == ord("n") and not (show and show.phase == "NAMES"):
                link.send(f"V{df_volume};")
                link.send("X1;")
                print("[sound] DFPlayer: next track (like touching IO2)")
                continue
            if k == ord("m") and not (show and show.phase == "NAMES"):
                sound_test = not sound_test
                if sound_test:
                    link.send(f"V{df_volume};")
                    sound_next_t = time.time() + 0.5
                    print(f"[sound] test ON: a commentary clip from /MP3 every 5 s, volume {df_volume} (m = stop)")
                else:
                    link.send("P0;")
                    print("[sound] test OFF")
                continue
            if k == ord("p") and not (show and show.phase == "NAMES"):
                tune = 2 if tune == 1 else 1
                link.send(f"{TUNE_CMD[tune][2]}0;")   # the robot replies with that servo's angles
                print(f"[servo] the [ ] - = / keys now tune PLAYER {tune}'s servo")
                continue
            if chr(k) in "[]-=/" and not (show and show.phase == "NAMES"):
                sv = servos[tune] or {}
                c_rest, c_strike, c_test = TUNE_CMD[tune]
                if chr(k) == "/":
                    link.send(f"{c_test}1;")
                elif "rest" in sv:
                    if chr(k) in "[]":
                        link.send(f"{c_rest}{max(0, min(180, sv['rest'] + (1 if k == ord(']') else -1)))};")
                    else:                               # - smaller swing, = bigger swing
                        toward_rest = 1 if sv["strike"] < sv["rest"] else -1
                        step = toward_rest if k == ord("-") else -toward_rest
                        link.send(f"{c_strike}{max(0, min(180, sv['strike'] + step))};")
                else:
                    link.send(f"{c_test}0;")            # ask the robot for the current angles first
                    print(f"[servo] asking the robot for player {tune}'s angles, press again")
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
            elif k == ord("y"):
                link.swap1 = not link.swap1
                link.current1 = None                # resend player 1's move the new way round
                print(f"[link] player 1 L/R swap {'ON' if link.swap1 else 'OFF'} "
                      f"(set SWAP_LR_P1 = {link.swap1} in config.py to keep it)")
            elif k == ord("x"):
                link.swap = not link.swap
                print(f"[link] L/R swap {'ON' if link.swap else 'OFF'} (set SWAP_LR = {link.swap} in config.py to keep it)")
            elif k in (ord("1"), ord("2"), ord("3")):
                ctrl.set_difficulty(int(chr(k)))
                ctrl1.set_difficulty(int(chr(k)))
            elif k == ord("b") and live:
                print("[ai] choose AI VS AI on the game screen (home menu)")
            elif k == ord("b"):
                aivai = not aivai
                tracker.find_p1 = aivai
                pred1.reset()
                if show:
                    show.aivai = aivai
                if not aivai:
                    link.move1("S")
                    link.move1(None)
                if aivai:
                    print("[ai] AI vs AI ON: the camera AI drives player 1 too (blue tape; left-click it in the "
                          "bottom half to lock its colour). Start a match from the show.")
                else:
                    print("[ai] AI vs AI OFF")
            elif k == ord("f"):
                link.send("F")
            elif k == ord("z"):
                link.send("Z")
            elif k == ord("c") and not args.sim:
                cal = run_calibration(source) or cal
                tracker, pred = Tracker(cal.arena), Predictor(cal.arena)
                pred1 = Predictor(mirrored(cal.arena))
                tracker.find_p1 = aivai
    finally:
        if live:
            link.send("O0;")                        # leave the robot locked
        if show:
            show.close()
        link.close()
        source.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
