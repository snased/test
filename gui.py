import sys
import pygame

from logic import (
    BallWorld,
    WorldConfig,
    InputState,
)


# ------------
# Configuration
# ------------
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 600
BACKGROUND_COLOR = (255, 255, 255)  # white
TARGET_FPS = 120

# Start with this many random balls
INITIAL_BALL_COUNT = 60

# Suction visuals and parameters
SUCTION_RADIUS = 100.0
SUCTION_COLOR = (40, 120, 255)
SUCTION_ALPHA = 50

# Deletion zone (x, y, w, h) in pixels; bottom-right corner
DELETION_ZONE = (WINDOW_WIDTH - 140, WINDOW_HEIGHT - 120, 120, 100)
DELETION_COLOR_FILL = (255, 80, 80)
DELETION_ALPHA = 35
DELETION_BORDER = (220, 30, 30)

# Spit parameters
SPIT_COUNT = 3
SPIT_SPEED = 320.0


def rgb_float_to_int(c):
    """Convert color from [0.0, 1.0] float tuple to [0, 255] int tuple."""
    r = max(0, min(255, int(round(c[0] * 255))))
    g = max(0, min(255, int(round(c[1] * 255))))
    b = max(0, min(255, int(round(c[2] * 255))))
    return (r, g, b)


def make_world():
    """Create and initialize the ball world."""
    # You can tweak boundary to "wrap" or "bounce"
    cfg = WorldConfig(
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        boundary="wrap",
        linear_damping=0.05,
        gravity=(0.0, 0.0),
    )
    world = BallWorld(cfg, rng_seed=1337)
    # Set deletion zone
    world.set_deletion_zone(DELETION_ZONE)
    # Add initial random balls
    for _ in range(INITIAL_BALL_COUNT):
        world.add_random_ball()
    return world


def draw_suction(surface, pos):
    """Draw the suction effect visualization."""
    overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
    pygame.draw.circle(overlay, (*SUCTION_COLOR, SUCTION_ALPHA), (int(pos[0]), int(pos[1])), int(SUCTION_RADIUS), 0)
    pygame.draw.circle(overlay, SUCTION_COLOR, (int(pos[0]), int(pos[1])), int(SUCTION_RADIUS), 2)
    surface.blit(overlay, (0, 0))


def draw_deletion_zone(surface):
    """Draw the deletion zone rectangle."""
    x, y, w, h = DELETION_ZONE
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    overlay.fill((*DELETION_COLOR_FILL, DELETION_ALPHA))
    surface.blit(overlay, (x, y))
    pygame.draw.rect(surface, DELETION_BORDER, pygame.Rect(x, y, w, h), 2)


def run():
    """Main game loop."""
    pygame.init()
    try:
        screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Ball World")
        clock = pygame.time.Clock()

        world = make_world()

        sucking_enabled = False
        pointer_pos = None

        # For right-click spit direction: aim from press to release
        rmb_down = False
        rmb_down_pos = (0.0, 0.0)

        running = True
        while running:
            dt = clock.tick(TARGET_FPS) / 1000.0

            # --- Input handling ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # LMB: start suction
                        sucking_enabled = True
                    elif event.button == 3:  # RMB: start aiming for spit
                        rmb_down = True
                        rmb_down_pos = pygame.mouse.get_pos()
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:  # LMB up: stop suction
                        sucking_enabled = False
                    elif event.button == 3 and rmb_down:  # RMB release: spit
                        rmb_down = False
                        release_pos = pygame.mouse.get_pos()
                        dx = release_pos[0] - rmb_down_pos[0]
                        dy = release_pos[1] - rmb_down_pos[1]
                        # Default direction if click without drag
                        if abs(dx) < 1e-3 and abs(dy) < 1e-3:
                            dx, dy = 1.0, 0.0

                        # Queue spit request from pointer release position
                        # toward drag direction
                        spit_req = {
                            "count": SPIT_COUNT,
                            "position": (float(release_pos[0]), float(release_pos[1])),
                            "direction": (float(dx), float(dy)),
                            "speed": SPIT_SPEED,
                        }

                        inputs = InputState(
                            pointer=(float(release_pos[0]), float(release_pos[1])),
                            sucking_enabled=False,
                            suction_radius=SUCTION_RADIUS,
                            spit_requests=[spit_req],
                        )
                        world.step(dt=0.0, inputs=inputs)  # process spit immediately this frame

            pointer_pos = pygame.mouse.get_pos()

            # --- Build input state for this frame ---
            inputs = InputState(
                pointer=(float(pointer_pos[0]), float(pointer_pos[1])),
                sucking_enabled=bool(sucking_enabled),
                suction_radius=SUCTION_RADIUS,
                spit_requests=[],
            )

            # --- Sim step ---
            world.step(dt, inputs)

            # --- Render ---
            screen.fill(BACKGROUND_COLOR)

            # Deletion zone
            draw_deletion_zone(screen)

            # Balls
            for b in world.balls:
                color = rgb_float_to_int(b.color)
                pygame.draw.circle(screen, color, (int(b.position[0]), int(b.position[1])), int(b.radius))

            # Suction overlay
            if sucking_enabled and pointer_pos is not None:
                draw_suction(screen, pointer_pos)

            # HUD: inventory count
            font = pygame.font.SysFont(None, 20)
            inv_text = font.render(f"Inventory: {len(world.inventory)}", True, (30, 30, 30))
            screen.blit(inv_text, (10, 8))

            # HUD: instructions
            hint = font.render("LMB: vacuum | RMB drag+release: spit x3", True, (60, 60, 60))
            screen.blit(hint, (10, 30))

            pygame.display.flip()
    finally:
        pygame.quit()


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

