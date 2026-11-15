"""DRIFT - a top-down drifting game for Python + pygame.

    pip install pygame
    python drift.py

Controls
    W / Up      throttle            A / Left    steer left
    S / Down    brake / reverse     D / Right   steer right
    Space       handbrake           R           reset
    M           mute sound          Esc         quit

Hold the throttle and steer hard at speed to power-slide, or tap the handbrake
going into a corner. Longer drifts build a multiplier. Points are banked when
you straighten out, and lost if you hit a wall.

The physics and world code at the top does not need pygame, so it can be
tested (and rendered) without opening a window.
"""
import math
import random
from array import array

try:
    import pygame
except ImportError:  # the physics / world code below still works without it
    pygame = None

# ------------------------------------------------------------------ settings
WIN_W, WIN_H = 1100, 700
WORLD_W, WORLD_H = 3000, 2000
FPS = 60
KMH = 0.27                 # pixels/second -> displayed km/h
BARRIER = 30               # thickness of the red/white wall around the arena

ASPHALT = (52, 54, 60)
CIRCLE = (1500, 900)       # centre of the painted drift circle
RING_R = 340               # radius of the cone ring
START = (1500, 1500, -math.pi / 2)   # x, y, heading (facing up the screen)


# --------------------------------------------------------------------- car
class Car:
    LENGTH = 62
    WIDTH = 32
    RADIUS = 26

    ENGINE = 950.0          # px/s^2 at full throttle
    BRAKE = 1100.0
    REVERSE = 520.0
    MAX_REVERSE = 240.0
    DRAG = 0.4              # rolling resistance
    QDRAG = 0.00169         # air resistance; together they cap speed near 640 px/s
    STEER_RATE = 2.9        # rad/s at full lock
    ALIGN = 2.0             # how strongly the car tries to point where it travels
    GRIP_NORMAL = 9.0       # lateral grip (higher = stickier)
    GRIP_POWER = 2.1        # throttle + hard steering at speed
    GRIP_HANDBRAKE = 0.7

    def __init__(self, x, y, heading):
        self.x, self.y, self.heading = x, y, heading
        self.vx = self.vy = 0.0
        self.vf = self.vl = 0.0     # velocity along / across the car
        self.steer = 0.0
        self.throttle = self.brake = 0.0
        self.handbrake = False

    @property
    def speed(self):
        return math.hypot(self.vx, self.vy)

    @property
    def slip_deg(self):
        """Angle between where the car points and where it is travelling."""
        if self.vf <= 0 or self.speed < 40:
            return 0.0
        return math.degrees(math.atan2(abs(self.vl), self.vf))

    def update(self, dt, throttle, brake, steer_in, handbrake):
        """Advance one step. Returns the impact speed if a wall was hit."""
        rate = 8.0 if steer_in else 12.0          # wheel recentres faster
        self.steer += (steer_in - self.steer) * min(1.0, rate * dt)
        self.throttle, self.brake, self.handbrake = throttle, brake, handbrake

        fx, fy = math.cos(self.heading), math.sin(self.heading)
        rx, ry = -fy, fx
        vf = self.vx * fx + self.vy * fy
        vl = self.vx * rx + self.vy * ry
        speed = math.hypot(vf, vl)

        if throttle:
            vf += self.ENGINE * throttle * dt
        if brake:
            if vf > 10:
                vf = max(0.0, vf - self.BRAKE * dt)
            else:
                vf = max(vf - self.REVERSE * dt, -self.MAX_REVERSE)
        vf -= (self.DRAG * vf + self.QDRAG * vf * abs(vf)) * dt
        if handbrake:
            vf *= math.exp(-0.9 * dt)

        grip = self.GRIP_NORMAL
        if handbrake:
            grip = self.GRIP_HANDBRAKE
        elif throttle > 0.1 and abs(self.steer) > 0.6 and speed > 330:
            grip = self.GRIP_POWER
        vl *= math.exp(-grip * dt)

        sign = 1.0 if vf > -30 else -1.0          # steering flips in reverse
        yaw = self.steer * self.STEER_RATE * min(1.0, speed / 240.0) * sign
        if handbrake:
            yaw *= 1.5
        if vf > 20:                                 # self-aligning torque
            yaw += self.ALIGN * math.atan2(vl, vf) * min(1.0, speed / 200.0)

        # rebuild the world velocity with the *old* axes, then turn the car
        self.vx = fx * vf + rx * vl
        self.vy = fy * vf + ry * vl
        self.heading += yaw * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

        fx, fy = math.cos(self.heading), math.sin(self.heading)
        self.vf = self.vx * fx + self.vy * fy
        self.vl = -self.vx * fy + self.vy * fx

        return self._walls()

    def _walls(self):
        m = BARRIER + self.RADIUS - 2
        impact = 0.0
        if self.x < m:
            self.x, impact = m, max(impact, -self.vx)
            self.vx, self.vy = abs(self.vx) * 0.3, self.vy * 0.7
        elif self.x > WORLD_W - m:
            self.x, impact = WORLD_W - m, max(impact, self.vx)
            self.vx, self.vy = -abs(self.vx) * 0.3, self.vy * 0.7
        if self.y < m:
            self.y, impact = m, max(impact, -self.vy)
            self.vy, self.vx = abs(self.vy) * 0.3, self.vx * 0.7
        elif self.y > WORLD_H - m:
            self.y, impact = WORLD_H - m, max(impact, self.vy)
            self.vy, self.vx = -abs(self.vy) * 0.3, self.vx * 0.7
        return impact


def rear_wheels(car):
    fx, fy = math.cos(car.heading), math.sin(car.heading)
    back = -0.30 * car.LENGTH
    side = car.WIDTH / 2 - 3
    return [(car.x + fx * back - fy * s, car.y + fy * back + fx * s)
            for s in (-side, side)]


def car_shapes(car):
    """The car as a list of (polygon points in world space, colour)."""
    fx, fy = math.cos(car.heading), math.sin(car.heading)
    k = car.LENGTH / 46.0              # the shapes below are drawn for a 46 px car

    def tf(pts, dx=0.0, dy=0.0):
        return [(car.x + (fx * lx - fy * ly) * k + dx, car.y + (fy * lx + fx * ly) * k + dy)
                for lx, ly in pts]

    def box(x0, x1, y0, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    body = [(-23, -9), (-20, -12), (14, -12), (21, -8), (23, -5),
            (23, 5), (21, 8), (14, 12), (-20, 12), (-23, 9)]
    shapes = [(tf(body, 4, 5), (30, 31, 35))]                      # shadow

    steer = car.steer * 0.55
    cs, sn = math.cos(steer), math.sin(steer)
    for wx, wy, turn in ((15, -11, True), (15, 11, True),
                         (-14, -11, False), (-14, 11, False)):
        pts = box(-5, 5, -2.5, 2.5)
        if turn:
            pts = [(px * cs - py * sn, px * sn + py * cs) for px, py in pts]
        shapes.append((tf([(wx + px, wy + py) for px, py in pts]), (16, 16, 18)))

    red = (214, 48, 49)
    shapes += [
        (tf(body), red),
        (tf(box(-9, 2, -9, 9)), (168, 34, 38)),                    # roof
        (tf([(2, -9), (9, -7), (9, 7), (2, 9)]), (28, 38, 54)),    # windscreen
        (tf([(-13, -8), (-9, -9), (-9, 9), (-13, 8)]), (28, 38, 54)),
        (tf(box(9, 23, -2, 2)), (240, 240, 240)),                  # stripes
        (tf(box(-9, 2, -2, 2)), (240, 240, 240)),
        (tf(box(-23, -13, -2, 2)), (240, 240, 240)),
        (tf(box(20, 23, -10, -6)), (255, 244, 190)),               # headlights
        (tf(box(20, 23, 6, 10)), (255, 244, 190)),
    ]
    braking = car.brake > 0 and car.vf > 10
    tail = (255, 70, 55) if braking else (110, 20, 22)
    shapes += [(tf(box(-23, -21, -10, -6)), tail),
               (tf(box(-23, -21, 6, 10)), tail)]
    return shapes


# -------------------------------------------------------------- world / cones
class Cone:
    R = 11

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.vx = self.vy = 0.0


def cone_shapes(cone):
    """Cone as concentric circles: (dx, dy, radius, colour)."""
    return [(2, 3, 11, (30, 31, 35)), (0, 0, 11, (245, 120, 25)),
            (0, 0, 7, (240, 240, 240)), (0, 0, 4, (245, 120, 25))]


class World:
    def __init__(self, seed=7):
        rnd = random.Random(seed)
        cx, cy = CIRCLE
        self.cones = []
        for k in range(18):                                  # ring to drift around
            a = math.radians(k * 20)
            self.cones.append(Cone(cx + RING_R * math.cos(a), cy + RING_R * math.sin(a)))
        for i in range(9):                                   # slalom
            self.cones.append(Cone(520 + (60 if i % 2 else -60), 520 + i * 110))
        while len(self.cones) < 18 + 9 + 16:                 # scattered cones
            x, y = rnd.uniform(140, WORLD_W - 140), rnd.uniform(140, WORLD_H - 140)
            if math.hypot(x - cx, y - cy) < RING_R + 80:
                continue
            if 380 < x < 660 and 380 < y < 1500:
                continue
            if math.hypot(x - START[0], y - START[1]) < 200:
                continue
            self.cones.append(Cone(x, y))

    def update(self, dt, car):
        """Move the cones; returns how hard the car hit one this frame (0 = none)."""
        hit = 0.0
        for c in self.cones:
            dx, dy = c.x - car.x, c.y - car.y
            d = math.hypot(dx, dy)
            reach = car.RADIUS + Cone.R
            if 1e-6 < d < reach:
                nx, ny = dx / d, dy / d
                c.x, c.y = car.x + nx * reach, car.y + ny * reach
                rel = (car.vx - c.vx) * nx + (car.vy - c.vy) * ny
                if rel > 0:
                    hit = max(hit, rel)
                    c.vx += nx * rel * 1.4
                    c.vy += ny * rel * 1.4
                    car.vx -= nx * rel * 0.08
                    car.vy -= ny * rel * 0.08
            c.x += c.vx * dt
            c.y += c.vy * dt
            damp = math.exp(-2.5 * dt)
            c.vx *= damp
            c.vy *= damp
            lo = BARRIER + Cone.R
            if c.x < lo or c.x > WORLD_W - lo:
                c.x = min(max(c.x, lo), WORLD_W - lo)
                c.vx = -c.vx * 0.5
            if c.y < lo or c.y > WORLD_H - lo:
                c.y = min(max(c.y, lo), WORLD_H - lo)
                c.vy = -c.vy * 0.5
        return hit


# ---------------------------------------------------- tyre marks and smoke
class Skids:
    def __init__(self):
        self.prev = None
        self.new = []              # segments not yet drawn: (x1, y1, x2, y2, alpha)
        self.active = False

    def update(self, car):
        slide = abs(car.vl) > 85 and car.speed > 90
        locked = car.handbrake and car.speed > 120
        self.active = slide or locked
        pts = rear_wheels(car)
        if self.active:
            alpha = int(max(70, min(190, abs(car.vl) * 0.8 + (60 if locked else 0))))
            if self.prev:
                for a, b in zip(self.prev, pts):
                    self.new.append((a[0], a[1], b[0], b[1], alpha))
            self.prev = pts
        else:
            self.prev = None

    def pop(self):
        out, self.new = self.new, []
        return out


class Smoke:
    MAX = 260

    def __init__(self):
        self.p = []                # [x, y, vx, vy, age, life, size]
        self.acc = 0.0
        self.rnd = random.Random(3)

    def update(self, dt, car, active):
        if active:
            self.acc += dt * 70
            n, self.acc = int(self.acc), self.acc % 1.0
            r = self.rnd
            for _ in range(n):
                for wx, wy in rear_wheels(car):
                    self.p.append([wx, wy, car.vx * 0.15 + r.uniform(-25, 25),
                                   car.vy * 0.15 + r.uniform(-25, 25),
                                   0.0, r.uniform(0.7, 1.3), r.uniform(5, 8)])
        damp = math.exp(-1.5 * dt)
        for q in self.p:
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[2] *= damp
            q[3] *= damp
            q[4] += dt
        self.p = [q for q in self.p if q[4] < q[5]][-self.MAX:]

    @staticmethod
    def look(q):
        t = q[4] / q[5]
        return q[6] + t * 20, int(95 * (1 - t) ** 1.5)     # radius, alpha


# ------------------------------------------------------------------ scoring
class DriftScore:
    def __init__(self):
        self.total = self.best = 0
        self.points = 0.0
        self.time = 0.0
        self.mult = 1
        self.idle = 0.0
        self.drifting = False
        self.banner = ""
        self.banner_age = 99.0
        self.banked_now = 0          # points banked this frame (for the chime)

    def update(self, dt, car, crashed):
        self.banner_age += dt
        self.banked_now = 0
        self.drifting = car.slip_deg > 15 and car.speed > 180
        if crashed and self.points > 0:
            self._say("CRASH!")
            self._reset()
        elif self.drifting:
            self.idle = 0.0
            self.time += dt
            self.mult = 1 + min(7, int(self.time / 1.2))
            self.points += abs(car.vl) / 6.0 * self.mult * dt
        elif self.points > 0:
            self.idle += dt
            if self.idle > 0.7:
                pts = int(self.points)
                self.total += pts
                self.best = max(self.best, self.total)
                if pts >= 10:
                    self._say("+%d" % pts)
                    self.banked_now = pts
                self._reset()

    def _say(self, text):
        self.banner, self.banner_age = text, 0.0

    def _reset(self):
        self.points = self.time = self.idle = 0.0
        self.mult = 1


def hud_data(car, score):
    return {
        "kmh": int(car.speed * KMH),
        "ratio": min(1.0, car.speed / 640.0),
        "angle": int(car.slip_deg),
        "drifting": score.drifting,
        "points": int(score.points),
        "mult": score.mult,
        "total": score.total,
        "best": score.best,
        "banner": score.banner if score.banner_age < 1.6 else "",
    }


# ----------------------------------------------------- synthesized sounds
# Everything is generated in code, so there are no audio files to ship.
RATE = 22050
ENGINE_HZ = (40, 56, 76, 100, 132, 168)    # multiples of 4 so each 0.5 s loop is seamless


def synth_engine(freq, seconds=0.5):
    """A looping engine note: a stack of harmonics, softly clipped."""
    out = []
    for i in range(int(RATE * seconds)):
        ph = 2 * math.pi * freq * i / RATE
        s = sum(math.sin(h * ph + h) / h ** 0.8 for h in range(1, 9))
        s *= 1.0 + 0.3 * math.sin(ph / 2)               # uneven firing
        out.append(math.tanh(0.6 * s))
    return out


def synth_squeal(seconds=0.5):
    """A looping tyre squeal: wobbling high tones with a raspy edge."""
    out = []
    for i in range(int(RATE * seconds)):
        t = i / RATE
        p1 = 2 * math.pi * 1850 * t + 3 * math.sin(2 * math.pi * 8 * t)
        p2 = 2 * math.pi * 2480 * t + 2 * math.sin(2 * math.pi * 6 * t)
        p3 = 2 * math.pi * 3110 * t
        s = 0.6 * math.sin(p1) + 0.5 * math.sin(p2) + 0.3 * math.sin(p3)
        out.append(0.7 * s * (0.75 + 0.25 * math.sin(2 * math.pi * 90 * t)))
    return out


def synth_hit(f0, seconds, noise, decay):
    """A one-shot impact: a falling thump plus a burst of filtered noise."""
    rnd = random.Random(1)
    out, phase, low = [], 0.0, 0.0
    for i in range(int(RATE * seconds)):
        t = i / RATE
        phase += 2 * math.pi * (38 + f0 * math.exp(-14 * t)) / RATE
        low += 0.3 * (rnd.uniform(-1, 1) - low)
        out.append(math.sin(phase) * math.exp(-decay * t)
                   + noise * low * math.exp(-decay * 2.2 * t))
    return out


def synth_chime():
    """A two-note 'ding' for banking a drift."""
    out = []
    for i in range(int(RATE * 0.6)):
        t = i / RATE
        s = 0.5 * math.sin(2 * math.pi * 880 * t) * math.exp(-6 * t)
        s += 0.35 * math.sin(2 * math.pi * 1320 * t) * math.exp(-6 * t)
        if t > 0.12:
            s += 0.45 * math.sin(2 * math.pi * 1760 * (t - 0.12)) * math.exp(-8 * (t - 0.12))
        out.append(s)
    return out


def pcm(samples, gain=0.8):
    """Float samples (-1..1) -> 16-bit mono bytes for pygame.mixer.Sound."""
    return array("h", (int(max(-1.0, min(1.0, s * gain)) * 32767) for s in samples)).tobytes()


# ------------------------------------------------------- track decoration
def background_ops():
    """The arena floor as drawing primitives in world coordinates:
    ("rect", x, y, w, h, colour), ("circle", x, y, r, colour, width),
    ("line", x1, y1, x2, y2, colour, width)."""
    ops = []
    rnd = random.Random(11)

    for _ in range(40):                                      # patched asphalt
        ops.append(("rect", rnd.uniform(60, WORLD_W - 400), rnd.uniform(60, WORLD_H - 150),
                    rnd.uniform(120, 380), rnd.uniform(30, 90), (48, 50, 56)))
    for _ in range(9000):                                    # grain
        d = rnd.choice((-1, 1)) * rnd.randint(4, 10)
        ops.append(("rect", rnd.randrange(WORLD_W), rnd.randrange(WORLD_H),
                    rnd.choice((2, 3)), 2, (ASPHALT[0] + d, ASPHALT[1] + d, ASPHALT[2] + d + 2)))

    white, yellow = (222, 224, 228), (226, 190, 60)

    def dashed_circle(cx, cy, r, color, width, dash, gap):
        a = 0.0
        while a < 360:
            pts = [(cx + r * math.cos(math.radians(a + dash * f)),
                    cy + r * math.sin(math.radians(a + dash * f))) for f in (0, 0.5, 1)]
            ops.append(("line", pts[0][0], pts[0][1], pts[1][0], pts[1][1], color, width))
            ops.append(("line", pts[1][0], pts[1][1], pts[2][0], pts[2][1], color, width))
            a += dash + gap

    def dashed_line(x1, y1, x2, y2, color, width, dash, gap):
        length = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        d = 0.0
        while d < length:
            e = min(d + dash, length)
            ops.append(("line", x1 + ux * d, y1 + uy * d, x1 + ux * e, y1 + uy * e, color, width))
            d += dash + gap

    cx, cy = CIRCLE
    dashed_circle(cx, cy, RING_R, white, 6, 9, 5)
    dashed_circle(cx, cy, 240, yellow, 5, 7, 7)
    ops.append(("circle", cx, cy, 120, white, 5))
    ops.append(("circle", cx, cy, 16, yellow, 0))

    dashed_line(520, 430, 520, 1500, white, 5, 40, 30)       # slalom guide
    dashed_line(300, 1700, 2700, 1700, white, 6, 80, 60)     # straight
    for i in range(8):                                       # parking bays
        x = 2150 + i * 90
        ops.append(("line", x, 320, x, 560, white, 5))
    ops.append(("line", 2150, 320, 2780, 320, white, 5))
    for i in range(8):                                       # chequered start line
        for j in range(2):
            c = white if (i + j) % 2 == 0 else (30, 30, 34)
            ops.append(("rect", 1440 + i * 10, 1560 + j * 10, 10, 10, c))

    for x in range(0, WORLD_W, 60):                          # red/white barrier
        c = (200, 40, 42) if (x // 60) % 2 == 0 else (236, 236, 238)
        ops.append(("rect", x, 0, 60, BARRIER, c))
        ops.append(("rect", x, WORLD_H - BARRIER, 60, BARRIER, c))
    for y in range(0, WORLD_H, 60):
        c = (200, 40, 42) if (y // 60) % 2 == 0 else (236, 236, 238)
        ops.append(("rect", 0, y, BARRIER, 60, c))
        ops.append(("rect", WORLD_W - BARRIER, y, BARRIER, 60, c))
    ops.append(("rect", BARRIER, BARRIER, WORLD_W - 2 * BARRIER, 4, (30, 31, 35)))
    ops.append(("rect", BARRIER, BARRIER, 4, WORLD_H - 2 * BARRIER, (30, 31, 35)))
    return ops


# -------------------------------------------------------------- pygame part
def draw_ops(surface, ops, ox=0, oy=0):
    for op in ops:
        kind = op[0]
        if kind == "rect":
            _, x, y, w, h, c = op
            pygame.draw.rect(surface, c, (int(x - ox), int(y - oy), int(w), int(h)))
        elif kind == "circle":
            _, x, y, r, c, width = op
            pygame.draw.circle(surface, c, (int(x - ox), int(y - oy)), int(r), width)
        else:
            _, x1, y1, x2, y2, c, width = op
            pygame.draw.line(surface, c, (x1 - ox, y1 - oy), (x2 - ox, y2 - oy), width)


def text(screen, font, msg, pos, color=(255, 255, 255), anchor="topleft"):
    img = font.render(msg, True, color)
    rect = img.get_rect(**{anchor: pos})
    screen.blit(font.render(msg, True, (0, 0, 0)), rect.move(2, 2))
    screen.blit(img, rect)


def draw_hud(screen, fonts, hud):
    big, mid, small = fonts
    text(screen, mid, "SCORE %d" % hud["total"], (24, 18))
    text(screen, small, "BEST  %d" % hud["best"], (26, 50), (190, 195, 205))
    text(screen, small, "WASD / arrows  |  SPACE handbrake  |  R reset  |  M mute  |  ESC quit",
         (WIN_W - 24, 20), (190, 195, 205), "topright")

    if hud["points"] > 0:
        col = (255, 214, 64) if hud["drifting"] else (200, 205, 215)
        text(screen, big, "%d" % hud["points"], (WIN_W // 2, 70), col, "midtop")
        text(screen, mid, "DRIFT  x%d" % hud["mult"], (WIN_W // 2, 126), col, "midtop")
    if hud["banner"]:
        bad = hud["banner"].startswith("CRASH")
        text(screen, big, hud["banner"], (WIN_W // 2, WIN_H // 2 - 150),
             (255, 90, 80) if bad else (120, 235, 140), "midtop")

    x, y, w = 24, WIN_H - 70, 260
    r = hud["ratio"]
    pygame.draw.rect(screen, (18, 18, 22), (x - 3, y - 3, w + 6, 20))
    pygame.draw.rect(screen, (int(60 + 195 * r), int(225 - 150 * r), 70), (x, y, int(w * r), 14))
    text(screen, big, "%d" % hud["kmh"], (x + 118, y - 62), anchor="topright")
    text(screen, small, "km/h", (x + 128, y - 36), (190, 195, 205))
    text(screen, small, "ANGLE %d°" % hud["angle"], (x + w + 24, y - 4), (190, 195, 205))


class Audio:
    """Engine (crossfaded loops + a simple gearbox), tyre squeal and impacts.
    If there is no sound device the game just runs silently."""
    GEARS = (0, 130, 250, 370, 490, 700)         # speed (px/s) where each gear ends

    def __init__(self):
        self.ok = False
        self.muted = False
        self.rpm = 0.1
        self.squeal = 0.0
        self.cool = 0.0
        if not pygame.mixer.get_init():
            return
        try:
            def make(samples):
                return pygame.mixer.Sound(buffer=pcm(samples))

            self.engines = [make(synth_engine(f)) for f in ENGINE_HZ]
            self.squeal_snd = make(synth_squeal())
            self.crash = make(synth_hit(80, 0.8, 1.8, 5))
            self.thump = make(synth_hit(110, 0.35, 0.8, 10))
            self.tock = make(synth_hit(320, 0.2, 0.5, 22))
            self.chime = make(synth_chime())

            loops = self.engines + [self.squeal_snd]
            pygame.mixer.set_num_channels(16)
            pygame.mixer.set_reserved(len(loops))      # keep these channels for the loops
            for i, snd in enumerate(loops):
                snd.set_volume(0.0)                    # start silent, fade in via set_volume
                pygame.mixer.Channel(i).play(snd, loops=-1)
            self.ok = True
        except pygame.error:
            self.ok = False

    def toggle(self):
        self.muted = not self.muted

    def update(self, dt, car, impact, cone_hit, banked):
        if not self.ok:
            return
        speed = car.speed
        gear = 0
        while gear < len(self.GEARS) - 2 and speed >= self.GEARS[gear + 1]:
            gear += 1
        lo, hi = self.GEARS[gear], self.GEARS[gear + 1]
        frac = min(1.0, max(0.0, (speed - lo) / (hi - lo)))
        target = min(1.0, 0.1 + 0.75 * frac + (0.15 if car.throttle else 0.0))
        self.rpm += (target - self.rpm) * min(1.0, 12 * dt)

        loud = 0.0 if self.muted else 0.16 + (0.14 if car.throttle else 0.0)
        pos = self.rpm * (len(self.engines) - 1)
        for i, snd in enumerate(self.engines):         # blend the two nearest pitches
            snd.set_volume(loud * max(0.0, 1.0 - abs(pos - i)))

        slide = abs(car.vl) if car.speed > 80 else 0.0
        want = min(1.0, max(0.0, (slide - 70) / 220.0))
        if car.handbrake and car.speed > 120:
            want = max(want, 0.5)
        self.squeal += (want - self.squeal) * min(1.0, 15 * dt)
        self.squeal_snd.set_volume(0.0 if self.muted else 0.45 * self.squeal)

        self.cool -= dt
        if self.muted:
            return
        if impact > 60 and self.cool <= 0:
            snd = self.crash if impact > 150 else self.thump
            snd.set_volume(min(1.0, impact / 450.0 + 0.2))
            snd.play()
            self.cool = 0.15
        elif cone_hit > 60 and self.cool <= 0:
            self.tock.set_volume(min(1.0, cone_hit / 400.0 + 0.1))
            self.tock.play()
            self.cool = 0.1
        if banked:
            self.chime.set_volume(0.5)
            self.chime.play()


def main():
    if pygame is None:
        print("This game needs pygame. Install it with:\n    pip install pygame")
        return

    try:                                   # mono, exactly this format, small buffer
        pygame.mixer.init(RATE, -16, 1, 512, allowedchanges=0)
    except (pygame.error, TypeError):
        pass                               # pygame.init() below will try defaults
    pygame.init()
    global WIN_W, WIN_H
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    WIN_W, WIN_H = screen.get_size()
    pygame.display.set_caption("DRIFT")
    clock = pygame.time.Clock()
    audio = Audio()
    if audio.ok:
        print("Sound: ON  (you should hear a short chime now; press M to mute)")
        audio.chime.set_volume(0.4)
        audio.chime.play()
    else:
        print("Sound: OFF - no working audio device was found, the game will be silent.")
    names = "consolas,dejavusansmono,couriernew,monospace"
    fonts = (pygame.font.SysFont(names, 54, True),
             pygame.font.SysFont(names, 28, True),
             pygame.font.SysFont(names, 18, True))

    floor = pygame.Surface((WORLD_W, WORLD_H)).convert()
    floor.fill(ASPHALT)
    draw_ops(floor, background_ops())
    marks = pygame.Surface((WORLD_W, WORLD_H), pygame.SRCALPHA)

    puffs = {}                                   # radius -> cached smoke sprite

    def puff(radius):
        radius = max(2, int(radius) // 2 * 2)
        if radius not in puffs:
            s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (226, 228, 232), (radius, radius), radius)
            puffs[radius] = s
        return puffs[radius]

    def new_round():
        return Car(*START), World(), Skids(), Smoke(), DriftScore()

    car, world, skids, smoke, score = new_round()
    best = 0
    cam = [car.x - WIN_W / 2, car.y - WIN_H / 2]
    running = True
    started = False
    touch_points = {}
    mouse_controls = {}

    def button(surface, rect, label, font, fill=(28, 31, 39), edge=(235, 125, 35)):
        pygame.draw.rect(surface, fill, rect, border_radius=16)
        pygame.draw.rect(surface, edge, rect, width=3, border_radius=16)
        img = font.render(label, True, (255, 255, 255))
        surface.blit(img, img.get_rect(center=rect.center))

    def draw_mobile_controls():
        # Large translucent-style touch pads; drawn as simple high-contrast controls.
        y = WIN_H - 100
        controls = [
            (pygame.Rect(24, y - 28, 86, 76), "LEFT"),
            (pygame.Rect(120, y - 28, 86, 76), "RIGHT"),
            (pygame.Rect(WIN_W - 206, y - 28, 86, 76), "BRAKE"),
            (pygame.Rect(WIN_W - 110, y - 28, 86, 76), "GAS"),
            (pygame.Rect(WIN_W // 2 - 58, y - 28, 116, 76), "HANDBRAKE"),
        ]
        for rect, label in controls:
            button(screen, rect, label, fonts[2], (25, 29, 38), (245, 145, 45))
        button(screen, pygame.Rect(WIN_W - 104, 18, 86, 42), "RESET", fonts[2], (40, 30, 30), (220, 75, 65))

    def touch_inputs():
        throttle = brake = 0.0
        steer = 0.0
        handbrake = False
        y = WIN_H - 100
        left = pygame.Rect(24, y - 28, 86, 76)
        right = pygame.Rect(120, y - 28, 86, 76)
        stop = pygame.Rect(WIN_W - 206, y - 28, 86, 76)
        gas = pygame.Rect(WIN_W - 110, y - 28, 86, 76)
        hb = pygame.Rect(WIN_W // 2 - 58, y - 28, 116, 76)
        for px, py in touch_points.values():
            if left.collidepoint(px, py): steer = -1.0
            if right.collidepoint(px, py): steer = 1.0
            if stop.collidepoint(px, py): brake = 1.0
            if gas.collidepoint(px, py): throttle = 1.0
            if hb.collidepoint(px, py): handbrake = True
        return throttle, brake, steer, handbrake

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.FINGERDOWN:
                px, py = e.x * WIN_W, e.y * WIN_H
                if not started:
                    started = True
                else:
                    touch_points[e.finger_id] = (px, py)
                    if pygame.Rect(WIN_W - 104, 18, 86, 42).collidepoint(px, py):
                        best = max(best, score.best)
                        car, world, skids, smoke, score = new_round()
                        score.best = best
                        marks.fill((0, 0, 0, 0))
            elif e.type == pygame.FINGERMOTION:
                touch_points[e.finger_id] = (e.x * WIN_W, e.y * WIN_H)
            elif e.type == pygame.FINGERUP:
                touch_points.pop(e.finger_id, None)
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_m:
                    audio.toggle()
                elif e.key == pygame.K_r:
                    best = max(best, score.best)
                    car, world, skids, smoke, score = new_round()
                    score.best = best
                    marks.fill((0, 0, 0, 0))

        if not started:
            screen.fill((17, 20, 28))
            title_font = pygame.font.SysFont("consolas", max(52, WIN_H // 7), True)
            text(screen, title_font, "DRIFT", (WIN_W // 2, WIN_H // 3), (245, 130, 35), "midtop")
            text(screen, fonts[1], "MOBILE DRIFT ARENA", (WIN_W // 2, WIN_H // 3 + WIN_H // 7), (205, 211, 222), "midtop")
            play_rect = pygame.Rect(WIN_W // 2 - 120, WIN_H * 2 // 3 - 35, 240, 76)
            button(screen, play_rect, "TAP TO PLAY", fonts[1])
            text(screen, fonts[2], "Touch controls  |  Drift to earn points", (WIN_W // 2, WIN_H - 35), (170, 180, 195), "midbottom")
            for event in pygame.event.get([pygame.FINGERDOWN, pygame.MOUSEBUTTONDOWN]):
                started = True
            pygame.display.flip()
            continue

        k = pygame.key.get_pressed()
        key_throttle = 1.0 if (k[pygame.K_w] or k[pygame.K_UP]) else 0.0
        key_brake = 1.0 if (k[pygame.K_s] or k[pygame.K_DOWN]) else 0.0
        key_steer = float(bool(k[pygame.K_d] or k[pygame.K_RIGHT])) - float(bool(k[pygame.K_a] or k[pygame.K_LEFT]))
        key_handbrake = bool(k[pygame.K_SPACE])
        touch_throttle, touch_brake, touch_steer, touch_handbrake = touch_inputs()
        throttle = max(key_throttle, touch_throttle)
        brake = max(key_brake, touch_brake)
        steer = touch_steer if touch_steer else key_steer
        handbrake = key_handbrake or touch_handbrake

        impact = car.update(dt, throttle, brake, steer, handbrake)
        hit = world.update(dt, car)
        skids.update(car)
        smoke.update(dt, car, skids.active)
        score.update(dt, car, impact > 150)
        audio.update(dt, car, impact, hit, score.banked_now)

        for x1, y1, x2, y2, a in skids.pop():
            pygame.draw.line(marks, (8, 8, 10, a), (x1, y1), (x2, y2), 4)

        tx = min(max(car.x + car.vx * 0.3 - WIN_W / 2, 0), WORLD_W - WIN_W)
        ty = min(max(car.y + car.vy * 0.3 - WIN_H / 2, 0), WORLD_H - WIN_H)
        cam[0] += (tx - cam[0]) * min(1.0, 5 * dt)
        cam[1] += (ty - cam[1]) * min(1.0, 5 * dt)
        cx, cy = int(cam[0]), int(cam[1])
        view = pygame.Rect(cx, cy, WIN_W, WIN_H)

        screen.blit(floor, (0, 0), view)
        screen.blit(marks, (0, 0), view)
        for c in world.cones:
            for dx, dy, r, col in cone_shapes(c):
                pygame.draw.circle(screen, col, (int(c.x + dx - cx), int(c.y + dy - cy)), r)
        for q in smoke.p:
            radius, alpha = Smoke.look(q)
            s = puff(radius)
            s.set_alpha(alpha)
            screen.blit(s, (int(q[0] - cx - s.get_width() / 2), int(q[1] - cy - s.get_height() / 2)))
        for pts, col in car_shapes(car):
            pygame.draw.polygon(screen, col, [(x - cx, y - cy) for x, y in pts])
        draw_hud(screen, fonts, hud_data(car, score))
        draw_mobile_controls()
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
