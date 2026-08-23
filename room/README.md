# The Room

A 3D studio you sit inside while the pipeline runs. Each agent in
`manager.py`'s state machine is a person at a desk with a laptop; the Manager
assigns work by sending them mail, which arrives **on that agent's own
screen**; anything needing a human decision appears on one large screen beside
the table in the middle of the room, where there is a full game of Ludo to
play while you wait.

This is the whole-app surface, not one screen — Studio is the first room in it.
Clips and anything after it get their own space in the same building, reusing
this camera model, lighting system and screen-content pattern rather than
switching out to flat pages.

## Running it

```bash
cd room
npm install
npm run dev          # http://localhost:5273/room/
```

`npm run build` writes `room/dist`, which `web/server.py` mounts at `/room`
when it exists — so a built room is served by the same FastAPI app as the
rest of Santa Studio, on the same origin as the API.

Query params: `?speed=8` runs the simulated pipeline about eight times faster,
which is the quickest way to see every stage and both approval gates.
`?ludoStep=400` sets the milliseconds a token spends on each square (default
190), which is how you watch a move land square by square.

## Controls

| | |
|---|---|
| drag | orbit the room (auto-rotates until you first touch it) |
| scroll | zoom — past the wall for a dollhouse view of the whole floor |
| click a desk | fly over that agent's shoulder and read their screen |
| click the table | sit down at the Ludo board |
| `R` / `Space` | roll (at the table) |
| `1`–`4` | move that token, or click the token itself |
| `Esc` | back to the room |
| `L` | lights |

Dark and light are not a skin: `L` switches the room's own lights. Dark leaves
the place lit by the agents' screens; light brings up the ceiling rig, the
pendant over the table and every desk lamp.

The decision screen is built as an actual monitor — anodised bezel, glass with
a reflection on it, a standby LED in the chin — and asks for attention by
lighting its *panel* and throwing light into the room, not by glowing round the
edges. The board on the table is turned so that screen lands in the seated
player's eyeline: from the chair you can read the headline and click either
button without moving the camera.

## Layout

```
src/
  store.js            room state: theme, focus, per-agent status, the open decision
  theme.js            accent colours for anything that reads as a screen
  net/events.js       the event vocabulary the room understands
  sim/                a stand-in backend that speaks that vocabulary
    agents.js         the roster: one character per pipeline state
    feeds.js          placeholder mail and per-role output
    pipelineSim.js    walks the real STATE_SEQUENCE, raises the real gates
  world/
    layout.js         where every object and camera pose is
    CameraRig.jsx     orbit + zoom + eased fly-to-focus, one model everywhere
    Lighting.jsx      the light switch
    RoomShell.jsx     floor, wall, ceiling, plants
    Scene.jsx         assembly
  studio/
    AgentDesk.jsx     desk, chair, laptop, lamp, the person
    SeatedFigure.jsx  a seated human
    LaptopScreen.jsx  canvas -> screen texture, repainted only when it must be
    screenDraw.js     the in-laptop UIs (inbox, browser, editor, waveform, ...)
    ApprovalScreen.jsx the one screen that talks to you
    approvalDraw.js   its UI, and the button rects its clicks are tested against
  ludo/
    engine.js         complete standard ruleset, pure, no React
    boardTexture.js   the board, painted
    useLudoGame.js    turns, stepwise movement, the opponent
    LudoTable.jsx     table, board, tokens, dice, two players
  ui/Hud.jsx          the little flat UI that's left
```

## The Ludo game

A real game, not a mini-game. Standard cross board: four 6×6 yards, a 52-cell
shared ring, five-cell home lanes into the centre triangle. Two players — you
in red, the opponent in yellow — four tokens each.

Enforced: a token leaves the yard only on a six; a six repeats your turn, and
three sixes in a row forfeits it (and the forfeited streak does not follow the
turn to the next player); landing on an opponent sends them home unless the
square is a start or a star; finishing needs an exact count, so an overshoot
simply isn't a legal move; if nothing can move, the room says so before the
turn passes. Tokens walk the board one cell per hop for exactly the number
rolled — they never jump to the destination, and tokens sharing a safe square
stand beside each other so a stack stays countable.

Capturing or sending a token home does *not* grant an extra turn here — the
spec's rule list is implemented exactly as written, and only a six repeats.

`engine.js` has no dependencies, so it can be played by a script:

```js
import * as E from "./src/ludo/engine.js";
let g = E.createGame();
while (!g.winner) {
  const die = E.roll();
  const moves = E.legalMoves(g, g.turn, die);
  g = moves.length
    ? E.applyMove(g, g.turn, E.chooseMove(g, g.turn, die, moves), die).game
    : E.passTurn(g, g.turn);
}
```

## Wiring it to the real pipeline

Everything on screen today comes from `sim/pipelineSim.js`. It emits the events
in `net/events.js` and nothing else touches the store, so connecting the real
backend means replacing the source, not the scene:

```js
const ws = new WebSocket(`ws://${location.host}/ws/runs/${runId}`);
ws.onmessage = (m) => applyEvent(useStudio, JSON.parse(m.data));
```

What the backend still needs for that, none of which exists yet:

- a WebSocket endpoint on `web/server.py` — the app is polling-only today
  (`GET /api/runs/{id}/status`);
- a fourth `ApprovalHandler` implementation alongside CLI, Telegram and web,
  so gates arrive here as `{ type: "gate" }` and the answer goes back through
  `PipelineManager.step(decision=...)`;
- per-agent progress events. The agents currently produce their output in one
  piece and return it; the `line` events that make a screen look alive need
  the agents to emit intermediate output as they go.

Until then, `feeds.js` stands in for all three.

## Dev handles

In `npm run dev` only, `window.__studio` is the store (`window.__studio
.getState().focusDesk("research")`) and `window.__rig` is the live camera
state. Both are compiled out of a production build.

## Performance note

The room keeps roughly a dozen point lights alive at once (one per desk, plus
the ceiling rig) so that turning the lights on is a real lighting change
rather than an exposure trick. That is comfortable on a GPU and slow under
software rendering — if you are testing in a headless browser with SwiftShader,
expect single-digit frame rates and give camera transitions time to finish.
