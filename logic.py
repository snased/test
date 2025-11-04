from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import math
import random


# ===============
# Public data API
# ===============


Color = Tuple[float, float, float]  # RGB in [0.0, 1.0]
Vec2 = Tuple[float, float]
Rect = Tuple[float, float, float, float]  # x, y, w, h


@dataclass
class Ball:
    id: int
    position: Vec2
    velocity: Vec2
    radius: float
    color: Color
    mass: float = 1.0

    def copy(self) -> "Ball":
        return Ball(
            id=self.id,
            position=(self.position[0], self.position[1]),
            velocity=(self.velocity[0], self.velocity[1]),
            radius=self.radius,
            color=(self.color[0], self.color[1], self.color[2]),
            mass=self.mass,
        )


@dataclass
class WorldConfig:
    width: float
    height: float
    # Boundary behavior: "wrap" or "bounce"
    boundary: str = "wrap"
    # Global damping applied to velocity each second (0..1, 0 = no damping)
    linear_damping: float = 0.0
    # Gravity acceleration (x, y)
    gravity: Vec2 = (0.0, 0.0)
    # Coefficient for suction attraction (units: px/s^2 per px distance)
    suction_strength: float = 10.0
    # Distance (px) at which a ball is considered captured into inventory
    capture_distance: float = 12.0
    # Max speed clamp (0 disables)
    max_speed: float = 0.0


@dataclass
class InputState:
    # Pointer position if present
    pointer: Optional[Vec2] = None
    # When true, pointer acts as a vacuum that sucks nearby balls
    sucking_enabled: bool = False
    # Radius of suction effect around pointer
    suction_radius: float = 80.0
    # Requests to spit balls from inventory back into the world
    # Each request: {"count": int, "position": (x, y), "direction": (dx, dy), "speed": float}
    spit_requests: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class WorldEvents:
    # Emitted events from last step
    events: List[Dict[str, Any]] = field(default_factory=list)

    def emit(self, type_: str, **payload: Any) -> None:
        self.events.append({"type": type_, **payload})


class BallWorld:
    """
    Pure game-logic world for balls. No rendering or I/O.

    Responsibilities:
    - Ball movement and boundary handling
    - Suction into inventory using a pointer-controlled vacuum
    - Spitting balls back into the world from inventory
    - Color mixing on ball contact (non-physical; no repulsion)
    - Deletion zone for removing balls

    External integration:
    - Use `step(dt, inputs)` each frame
    - Query `balls`, `inventory`, and the returned `WorldEvents` for UI updates
    """

    def __init__(self, config: WorldConfig, rng_seed: Optional[int] = None) -> None:
        self.config = config
        self._rng = random.Random(rng_seed)
        self._next_id = 1
        self._deletion_zone: Optional[Rect] = None
        self._balls: List[Ball] = []
        self._inventory: List[Ball] = []

    # -------------
    # Public access
    # -------------
    @property
    def balls(self) -> List[Ball]:
        return self._balls

    @property
    def inventory(self) -> List[Ball]:
        return self._inventory

    def set_deletion_zone(self, rect: Optional[Rect]) -> None:
        """Define or clear the rectangular deletion zone (x, y, w, h)."""
        self._deletion_zone = rect

    def add_ball(
        self,
        position: Vec2,
        radius: float,
        color: Color,
        velocity: Vec2 = (0.0, 0.0),
        mass: float = 1.0,
        ball_id: Optional[int] = None,
    ) -> Ball:
        if ball_id is None:
            ball_id = self._next_and_increment_id()
        ball = Ball(ball_id, position, velocity, radius, _clamp_color(color), mass)
        self._balls.append(ball)
        return ball

    def remove_ball_by_id(self, ball_id: int) -> Optional[Ball]:
        for i, b in enumerate(self._balls):
            if b.id == ball_id:
                return self._balls.pop(i)
        return None

    def add_random_ball(self, radius_range: Tuple[float, float] = (8.0, 16.0)) -> Ball:
        r = self._rng.uniform(*radius_range)
        x = self._rng.uniform(r, self.config.width - r)
        y = self._rng.uniform(r, self.config.height - r)
        vx = self._rng.uniform(-60.0, 60.0)
        vy = self._rng.uniform(-60.0, 60.0)
        color = (self._rng.random(), self._rng.random(), self._rng.random())
        return self.add_ball((x, y), r, color, (vx, vy))

    # ---------
    # Simulation
    # ---------
    def step(self, dt: float, inputs: Optional[InputState] = None) -> WorldEvents:
        events = WorldEvents()
        inputs = inputs or InputState()

        # 1) Spit requests processed first so new balls can move same frame
        if inputs.spit_requests:
            for req in inputs.spit_requests:
                self._handle_spit_request(req, events)
            # Prevent re-processing if the same InputState instance is reused
            inputs.spit_requests.clear()

        # 2) Apply suction forces if enabled
        if inputs.sucking_enabled and inputs.pointer is not None:
            self._apply_suction(inputs.pointer, inputs.suction_radius, dt)

        # 3) Integrate motion
        self._integrate(dt)

        # 4) Boundary handling
        self._handle_boundaries()

        # 5) Deletion zone check
        self._apply_deletion_zone(events)

        # 6) Color mixing on contact (no repulsion)
        self._apply_color_mixing(events)

        # 7) Capture into inventory if pointer vacuum is close enough
        if inputs.sucking_enabled and inputs.pointer is not None:
            self._capture_into_inventory(inputs.pointer, events)

        return events

    # -----------------
    # Internal mechanics
    # -----------------
    def _next_and_increment_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    def _apply_suction(self, pointer: Vec2, radius: float, dt: float) -> None:
        px, py = pointer
        strength = self.config.suction_strength
        for b in self._balls:
            bx, by = b.position
            dx = px - bx
            dy = py - by
            dist = math.hypot(dx, dy)
            if dist <= 1e-6 or dist > radius:
                continue
            nx = dx / dist
            ny = dy / dist
            # Force magnitude increases closer to center (inverse falloff)
            falloff = max(0.05, 1.0 - dist / radius)
            accel = strength * falloff
            ax = nx * accel
            ay = ny * accel
            b.velocity = (b.velocity[0] + ax * dt, b.velocity[1] + ay * dt)

    def _integrate(self, dt: float) -> None:
        gx, gy = self.config.gravity
        damping = self.config.linear_damping
        clamp_speed = self.config.max_speed
        for b in self._balls:
            vx = b.velocity[0] + gx * dt
            vy = b.velocity[1] + gy * dt
            if damping > 0.0:
                damp = max(0.0, 1.0 - damping * dt)
                vx *= damp
                vy *= damp
            if clamp_speed > 0.0:
                speed = math.hypot(vx, vy)
                if speed > clamp_speed:
                    scale = clamp_speed / max(speed, 1e-6)
                    vx *= scale
                    vy *= scale
            px = b.position[0] + vx * dt
            py = b.position[1] + vy * dt
            b.position = (px, py)
            b.velocity = (vx, vy)

    def _handle_boundaries(self) -> None:
        w, h = self.config.width, self.config.height
        mode = self.config.boundary
        if mode == "wrap":
            for b in self._balls:
                px, py = b.position
                r = b.radius
                # Wrap using radius as margin to keep center within bounds nicely
                if px < -r:
                    px = w + r
                elif px > w + r:
                    px = -r
                if py < -r:
                    py = h + r
                elif py > h + r:
                    py = -r
                b.position = (px, py)
        elif mode == "bounce":
            for b in self._balls:
                px, py = b.position
                vx, vy = b.velocity
                r = b.radius
                if px - r < 0.0 and vx < 0.0:
                    px = r
                    vx *= -1.0
                if px + r > w and vx > 0.0:
                    px = w - r
                    vx *= -1.0
                if py - r < 0.0 and vy < 0.0:
                    py = r
                    vy *= -1.0
                if py + r > h and vy > 0.0:
                    py = h - r
                    vy *= -1.0
                b.position = (px, py)
                b.velocity = (vx, vy)
        else:
            # Unknown mode: clamp silently
            for b in self._balls:
                px = min(max(b.radius, b.position[0]), w - b.radius)
                py = min(max(b.radius, b.position[1]), h - b.radius)
                b.position = (px, py)

    def _apply_deletion_zone(self, events: WorldEvents) -> None:
        if not self._deletion_zone:
            return
        x, y, w, h = self._deletion_zone
        kept: List[Ball] = []
        for b in self._balls:
            bx, by = b.position
            # Use exclusive upper bounds (<) for proper rectangle semantics
            if x <= bx < x + w and y <= by < y + h:
                events.emit("deleted", ball_id=b.id)
                continue
            kept.append(b)
        self._balls = kept

    def _apply_color_mixing(self, events: WorldEvents) -> None:
        n = len(self._balls)
        if n <= 1:
            return
        # Snapshot original colors so multiple collisions in the same frame
        # use pre-collision colors instead of cascaded updates.
        original_color_by_id = {b.id: b.color for b in self._balls}
        for i in range(n):
            bi = self._balls[i]
            for j in range(i + 1, n):
                bj = self._balls[j]
                if _circles_touch(bi.position, bi.radius, bj.position, bj.radius):
                    c_old_i = original_color_by_id.get(bi.id, bi.color)
                    c_old_j = original_color_by_id.get(bj.id, bj.color)
                    c_mix = vivid_color_mix(c_old_i, c_old_j)
                    # Symmetric mixing; both adopt the mixed color
                    bi.color = c_mix
                    bj.color = c_mix
                    events.emit(
                        "mixed",
                        ball_ids=(bi.id, bj.id),
                        color_before=(c_old_i, c_old_j),
                        color_after=c_mix,
                    )

    def _capture_into_inventory(self, pointer: Vec2, events: WorldEvents) -> None:
        capture_dist = self.config.capture_distance
        px, py = pointer
        kept: List[Ball] = []
        for b in self._balls:
            bx, by = b.position
            if math.hypot(px - bx, py - by) <= capture_dist:
                self._inventory.append(b)
                events.emit("sucked", ball_id=b.id)
            else:
                kept.append(b)
        self._balls = kept

    def _handle_spit_request(self, req: Dict[str, Any], events: WorldEvents) -> None:
        count = int(max(1, req.get("count", 1)))
        pos: Vec2 = tuple(req.get("position", (self.config.width * 0.5, self.config.height * 0.5)))  # type: ignore
        dir_vec: Vec2 = tuple(req.get("direction", (1.0, 0.0)))  # type: ignore
        speed: float = float(req.get("speed", 200.0))

        dx, dy = dir_vec
        mag = math.hypot(dx, dy)
        if mag <= 1e-6:
            dx, dy = 1.0, 0.0
            mag = 1.0
        nx, ny = dx / mag, dy / mag

        for _ in range(min(count, len(self._inventory))):
            ball = self._inventory.pop(0)
            # Slight positional jitter to avoid identical overlap
            jx = (self._rng.random() - 0.5) * ball.radius * 0.5
            jy = (self._rng.random() - 0.5) * ball.radius * 0.5
            vx = nx * speed + (self._rng.random() - 0.5) * 20.0
            vy = ny * speed + (self._rng.random() - 0.5) * 20.0
            ball.position = (pos[0] + jx, pos[1] + jy)
            ball.velocity = (vx, vy)
            self._balls.append(ball)
            events.emit("spat", ball_id=ball.id, position=ball.position, velocity=ball.velocity)


# ======================
# Geometry/Color helpers
# ======================


def _circles_touch(p1: Vec2, r1: float, p2: Vec2, r2: float) -> bool:
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    rr = r1 + r2
    return (dx * dx + dy * dy) <= rr * rr


def _clamp_color(c: Color) -> Color:
    return (
        max(0.0, min(1.0, c[0])),
        max(0.0, min(1.0, c[1])),
        max(0.0, min(1.0, c[2])),
    )


def vivid_color_mix(c1: Color, c2: Color) -> Color:
    """
    Universal mathematical mixing in RGB space.

    The resulting color is the exact component-wise average of the two inputs:
    (r, g, b) = ((r1 + r2) / 2, (g1 + g2) / 2, (b1 + b2) / 2)
    """
    r = (c1[0] + c2[0]) * 0.5
    g = (c1[1] + c2[1]) * 0.5
    b = (c1[2] + c2[2]) * 0.5
    return _clamp_color((r, g, b))


# -----------
# HSL helpers
# -----------


def rgb_to_hsl(r: float, g: float, b: float) -> Tuple[float, float, float]:
    mx = max(r, g, b)
    mn = min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = ((g - b) / d + (6.0 if g < b else 0.0)) / 6.0
    elif mx == g:
        h = ((b - r) / d + 2.0) / 6.0
    else:
        h = ((r - g) / d + 4.0) / 6.0
    return h % 1.0, s, l


def hsl_to_rgb(h: float, s: float, l: float) -> Tuple[float, float, float]:
    if s == 0.0:
        return l, l, l

    def hue_to_rgb(p: float, q: float, t: float) -> float:
        t = t % 1.0
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r = hue_to_rgb(p, q, h + 1 / 3)
    g = hue_to_rgb(p, q, h)
    b = hue_to_rgb(p, q, h - 1 / 3)
    return r, g, b


# ==================
# Convenience factory
# ==================


def create_default_world(width: float, height: float, rng_seed: Optional[int] = 1337) -> BallWorld:
    cfg = WorldConfig(width=width, height=height, boundary="wrap", linear_damping=0.05, gravity=(0.0, 0.0))
    return BallWorld(cfg, rng_seed=rng_seed)


__all__ = [
    "Color",
    "Vec2",
    "Rect",
    "Ball",
    "WorldConfig",
    "InputState",
    "WorldEvents",
    "BallWorld",
    "vivid_color_mix",
    "create_default_world",
]

