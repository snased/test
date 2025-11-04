Ball World (GUI)

Requirements
- Python 3.9+
- pygame (installed via requirements.txt)

Install
```bash
pip install -r requirements.txt
```

Run
```bash
python main.py
```

Controls
- Left Mouse: hold to vacuum (suck balls into inventory)
- Right Mouse: drag to aim, release to spit a few balls toward the drag direction
- Esc: quit

Notes
- White background, balls move and mix colors on contact (no repulsion).
- Bottom-right red rectangle is the deletion zone.
- Tweak constants in `main.py` (e.g., `INITIAL_BALL_COUNT`, window size).

