"""
CHEERIVY vision AI — all tunable numbers live here.

Coordinate system (after calibration, everything is in CENTIMETRES):

    x → ; y ↓.  AI / P2 baseline at y = 0, human / P1 baseline at y = ARENA_H.
    The straight baselines run from x = X0 to x = X0 + BASE_W; the octagon's
    chamfered corners stick out to the sides of that (see arena.py).

Ball moving TOWARD the AI  <=>  vy < 0
"""

# ---------------------------------------------------------------- arena (cm)
# Measured on the real board (see measurements.svg for what each one means).
BASE_W = 38.0           # measured: inner width of the straight AI baseline wall (carriage rail length)
CARRIAGE_GAP = 38.0     # measured: AI carriage front face -> P1 carriage front face
CARRIAGE_DEPTH = 4.0    # measured: baseline wall -> carriage front face
CARRIAGE_W = 10.0       # measured: carriage width (left-right)
# Where each striker sits compared with its tape's centre (cm, + = to the right in the picture). The AI
# aims the striker, not the tape. 0 = aim the tape's centre. Set live in Settings > Camera & AI.
STRIKER_OFFSET_AI_CM = 0.0
STRIKER_OFFSET_P1_CM = 0.0
ARENA_H = CARRIAGE_GAP + 2 * CARRIAGE_DEPTH   # baseline to baseline
CHAMFER_DX = 0.0        # the board is a plain rectangle now (was 9.0 on the old octagon board)
CHAMFER_DY = 0.0        # (was 10.0)
END_STRAIGHT = 0.0      # (was 2.5)
BALL_RADIUS = 2.0       # measured: ball diameter 4 cm

X0 = CHAMFER_DX + 3.0   # left margin in the top-down image so the chamfers fit
ARENA_W = BASE_W + 2 * X0          # width of the top-down image (cm)
AI_LINE_Y = CARRIAGE_DEPTH + BALL_RADIUS  # ball CENTRE is here when it touches the AI carriage
CARRIAGE_MIN_X = X0 + CARRIAGE_W / 2           # carriage centre travel limits
CARRIAGE_MAX_X = X0 + BASE_W - CARRIAGE_W / 2

PX_PER_CM = 10          # resolution of the top-down (warped) image
VIEW_MARGIN_CM = 0.0    # extra picture shown around the calibrated board on the game page (0 = none)

# ---------------------------------------------------------------- camera
CAMERA_INDEX = 0        # 0 = Iriun on this Mac (1 = FaceTime). None = auto-pick
CAMERA_W, CAMERA_H = 1280, 720

# ---------------------------------------------------------------- colours
# Pick colours far apart on the colour wheel: orange ball + green (tia) carriage never get mixed up.
# Fine-tune live in the top-down view: LEFT-click the carriage tape, RIGHT-click the ball.
BALL_COLOR = "orange"       # "orange", "black", or any name in COLORS
CARRIAGE_COLOR = "green"    # "green", "blue" or "red"
P1_CARRIAGE_COLOR = "blue"  # AI vs AI: the tape on PLAYER 1's carriage (the camera AI drives it too)
# HSV ranges (OpenCV: hue 0-180, saturation and value 0-255). "black" = dark pixels instead.
COLORS = {
    "orange": [((5, 110, 110), (25, 255, 255))],
    "green":  [((35, 70, 60), (85, 255, 255))],
    "blue":   [((90, 80, 50), (130, 255, 255))],
    "red":    [((0, 90, 70), (10, 255, 255)), ((165, 90, 70), (180, 255, 255))],
    "black":  None,
}

# ---------------------------------------------------------------- ball detection
BALL_MAX_V = 80         # black ball only: HSV "value" below this counts as black
BALL_MIN_AREA_CM2 = 5.0      # 4 cm ball = 12.6 cm² from above
BALL_MAX_AREA_CM2 = 20.0
BALL_MIN_CIRCULARITY = 0.55
BALL_MAX_JUMP_CM = 25.0 # ignore detections that teleport further than this in one frame

# ---------------------------------------------------------------- carriage detection
CARRIAGE_BAND_CM = CARRIAGE_DEPTH + 8.0  # search for the carriage tape this close to the AI baseline
                                         # (generous: tape sits ABOVE the floor, so an angled camera shifts it)
CARRIAGE_MIN_AREA_CM2 = 1.0
CARRIAGE_MASK_MARGIN = 1.5  # hide carriage footprint (+ this) from the ball detector
# STRIKE ZONES: a thin band just in front of each carriage's tape (as the camera sees it). A ball in
# it, moving or still, is struck at once (checked on its own, apart from the ball tracking).
STRIKE_ZONE_CM = 3.5        # depth of the band, from the tape's front edge towards the middle
STRIKE_ZONE_PAD_CM = 1.0    # the band is this much wider than the tape on each side
STRIKE_ZONE_MIN_CM2 = 1.5   # this much ball colour inside the band = the ball is there
STRIKE_ZONE_COOLDOWN_S = 0.5
WALL_MASK_MARGIN = 0.5      # ignore this much next to the walls (shadows / wall edges)

# ---------------------------------------------------------------- prediction
VEL_WINDOW_S = 0.15     # fit velocity over this much recent history
VEL_MIN_POINTS = 3
MIN_APPROACH_SPEED = 8.0   # cm/s; slower than this = not an "incoming" shot
SYSTEM_LATENCY_S = 0.07    # camera + processing + Bluetooth (HC-05)

# Board tilt: a thin sheet under the board makes it slope, so a slow ball slows down, stops and
# rolls back. Acceleration along the length in each half, cm/s² (+ = toward the P1 end, - = toward
# the AI end). These are only the starting values: the AI learns the real slope from the ball.
SLOPE_A_AI_HALF = 0.0
SLOPE_A_P1_HALF = 0.0
SLOPE_LEARN = True
SLOPE_MAX = 60.0           # ignore learned values beyond this (tracking glitches)
SLOPE_LEARN_S = 0.6        # a roll this long inside one half counts fully; shorter ones count less
SLOPE_LEARN_RATE = 0.15    # how fast a new measurement moves the learned value
SIM_SLOPE = (-6.0, 6.0)    # simulator only: (AI half, P1 half); sheet under the middle = both roll home

# ---------------------------------------------------------------- control
DEADBAND_CM = 1.5       # stop when |target - carriage| below this
SHOT_OK_CM = 3.0        # a shot coming: if it will land within this of the striker's centre, don't move
                        # (the plate is 10 cm wide; chasing the exact centre only makes it late)
IDLE_ZONE_CM = 8.0      # no shot coming: stay put anywhere within this of the middle (else come back to its edge)
HYSTERESIS_CM = 1.0     # extra margin before starting to move again
MOTOR_SPEED_CM_S = 30.0 # first guess of the carriage speed; the AI measures the real one while playing
MIN_MOVE_S = 0.04       # shortest drive pulse
MAX_MOVE_S = 0.6        # longest drive before looking again
SETTLE_S = 0.3          # after each move: wait this long so the camera shows where the carriage stopped
WRONG_WAY_CM = 2.0      # a move that went this far the wrong way -> swap L/R automatically
STALL_MOVE_CM = 0.7     # a move shorter than this near a rail end = the carriage is at the end
RAIL_MARGIN_CM = 1.0    # never aim closer than this to a rail end
FIRE_REACH_CM = CARRIAGE_W / 2  # flipper covers carriage_x ± this
FIRE_LEAD_S = 0.12      # fire this long before predicted arrival (servo swing time)
FIRE_COOLDOWN_S = 0.6
NEAR_BALL_CM = 4.0      # a slow ball this close in front of the AI line: go to it and hit it
HEARTBEAT_S = 0.1       # resend current command this often (firmware falls back to Mirror AI after 400 ms)
ROBOT_VOLUME = 14      # robot speaker (DFPlayer) volume 0..30; the PAM8610 amp has no knob, so set it here
CAMERA_GOALS = True     # count goals from the camera (turns itself off when the laser sensors report one)
LASER_GOALS = False     # True once the laser goal sensors are wired and tested. Until then the robot's
                        # goal messages are ignored (an unconnected sensor input can pick up motor noise)
SWAP_LR = True          # True if the carriage drives the WRONG way (press 'x' live to test)
SWAP_LR_P1 = False      # the same for PLAYER 1's carriage in AI vs AI (fixes itself if it drives the wrong way)

# Difficulty presets: (extra reaction delay s, target error cm, fire probability)
DIFFICULTY = {
    1: (0.20, 4.0, 0.6),   # Easy
    2: (0.10, 2.0, 0.85),  # Medium
    3: (0.00, 0.0, 1.0),   # Hard
}
DEFAULT_DIFFICULTY = 2

# ---------------------------------------------------------------- serial
BAUD = 9600
CALIB_FILE = "calib.json"
COLOURS_FILE = "colours.json"   # the colours taught in Settings > Re-teach colours
