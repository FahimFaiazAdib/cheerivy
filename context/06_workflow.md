# Workflow and commands

- Code is edited on the Mac and pushed to GitHub `FahimFaiazAdib/cheerivy`, branch
  **`cheerivy-v5-lobby-2p`**. Atiq pulls on his Windows PC, burns the chip there and plays there.
- Atiq's PC: Git Bash, Python 3.11 (`C:\Python311`), the robot's Bluetooth on **COM10**, the repo at
  `~/cheerivy`, the browser is Edge.
- Give commands **one per code block** (so each can be run on its own).

## Start a game (Atiq's PC, Git Bash)
```bash
cd ~/cheerivy
git pull origin cheerivy-v5-lobby-2p
cd cheerivy_ai
python main.py --port COM10
```
`main.py` must be run from inside `cheerivy_ai/`. The game opens at `localhost:8316` (F = fullscreen).
Stop with Ctrl+C. After moving the camera: Settings › Camera & AI › Recalibrate board.

## Burn the firmware (only when `main.c` / `CHEERIVY.hex` changed)
```bash
cd ~/cheerivy/CHEERIVY_burn
./avrdude.exe -C avrdude.conf -c usbasp -p m32 -B 32 -U flash:w:../CHEERIVY.hex:i
```
Back to the known-good firmware: the same with `../finalworkingcherivy.hex`.

## Voice files (not in git)
Shared as a zip whose paths start with `cheerivy_ai/…`; on Atiq's PC:
```bash
cd ~/cheerivy
python -m zipfile -e "$HOME/Downloads/<the zip>.zip" .
```

## On the Mac
- Firmware: `make`, then `cp main.hex CHEERIVY.hex` (and into `CHEERIVY_burn/`).
- Check Python on the old versions before pushing: `uv run --python 3.9 python -m py_compile <files>`
  (and 3.11). Tests: `python test_predictor.py`.
- Simulator: `python cheerivy_ai/main.py --sim`, or the page alone: `python cheerivy_ai/ui/server.py`.
- Rendering voices (F5-TTS, slow, Apple GPU): `cd cheerivy_ai/ui && HF_HUB_OFFLINE=1 uv run --python 3.12
  --with f5-tts --with soundfile python render_lines.py` (skips what is already rendered).
