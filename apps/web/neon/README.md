# Neon Alley

A ghost in a wet neon street at night.  Gather the fifteen sparks (the
gold ones only from the air), keep out of the drones' beams, and leave
by the gate at the far end, which opens when the last spark is taken.

The rules are LOVA -- `lib/neon.lova`, sixteen examples, most of them
relations the rules must satisfy -- run in the page by the native
runtime compiled to WebAssembly (`native/lova-wasm`).  The picture and
the sound are three.js and WebAudio; nothing is a downloaded asset.
The page asks the rules what happens sixty times a second and draws
what they answer.

```bash
python apps/web/neon/build.py --serve        # builds the module, assembles site/, serves it
# http://127.0.0.1:8765/
python apps/web/neon/build.py --no-cargo     # reuse the built module
lova check apps/web/neon/neon_web.lova       # the rules' examples
```

Keys: WASD or arrows to move, Space to jump (hold it to float down),
R to restart, M to mute.  On a touch screen, buttons.

| File | What |
|---|---|
| `neon_web.lova` | what the page opens: the rules as one record |
| `web/rules.js` | the session: `tick`, `scene`, `layout`, fixed point to metres |
| `web/world.js` | the street, buildings, signs, cables, the gate |
| `web/actors.js` | the ghost, sparks, drones, particles |
| `web/fx.js` | renderer, bloom, the CRT pass, rain |
| `web/audio.js` | the music and the sounds, synthesised |
| `web/main.js` | the loop, input, camera, HUD |
