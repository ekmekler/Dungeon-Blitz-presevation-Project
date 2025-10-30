# Brain.py
import time
import struct
from typing import Dict, Tuple, Optional, List
from BitBuffer import BitBuffer

AGGRO_RADIUS = 250          # match client
LEASH_DISTANCE = 600        # simple leash
NPC_SPEED = 180.0           # units/sec horizontal chase speed
TICK_MS = 1               # brain tick interval

class _EntityConsts:
    const_316 = 6

ENTITY_STATE_IDLE = 1
ENTITY_STATE_MOVING = 0

# ──────────────────────────────────────────────────────────────
# Shared server-side brain memory per NPC
# ──────────────────────────────────────────────────────────────
class _NPCBrainState:
    __slots__ = ("home_x", "home_y", "state", "target_id",
                 "last_tick_ms", "last_x", "last_y")
    def __init__(self, x: int, y: int):
        self.home_x = x
        self.home_y = y
        self.state = "IDLE"
        self.target_id: Optional[int] = None
        self.last_tick_ms = 0
        self.last_x = x
        self.last_y = y

_BRAINS: Dict[str, Dict[int, _NPCBrainState]] = {}

# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────

def _now_ms() -> int:
    return int(time.time() * 1000)

def _dist2(ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = ax - bx, ay - by
    return dx*dx + dy*dy

def _sign(v: float) -> int:
    return -1 if v < 0 else (1 if v > 0 else 0)

def _get_brain(level: str, npc_id: int, spawn_x: int, spawn_y: int) -> _NPCBrainState:
    m = _BRAINS.setdefault(level, {})
    b = m.get(npc_id)
    if b is None:
        b = _NPCBrainState(spawn_x, spawn_y)
        m[npc_id] = b
    return b


def _write_method_24(bb, val: int):
    if val < -0x800000: val = -0x800000
    if val >  0x7FFFFF: val =  0x7FFFFF
    if val < 0:
        val = (1 << 24) + val
    bb.write_method_6(val, 24)

def _build_pkt_0x07(entity_id: int,
                    delta_x: int, delta_y: int, delta_vx: int,
                    ent_state: int,
                    flags: Dict[str, bool],
                    airborne: bool = False,
                    velocity_y: int = 0) -> bytes:

    bb = BitBuffer()
    bb.write_method_4(entity_id)
    _write_method_24(bb, delta_x)
    _write_method_24(bb, delta_y)
    _write_method_24(bb, delta_vx)
    bb.write_method_6(ent_state, _EntityConsts.const_316)
    bb.write_method_6(1 if flags.get('b_left') else 0, 1)
    bb.write_method_6(1 if flags.get('b_running') else 0, 1)
    bb.write_method_6(1 if flags.get('b_jumping') else 0, 1)
    bb.write_method_6(1 if flags.get('b_dropping') else 0, 1)
    bb.write_method_6(1 if flags.get('b_backpedal') else 0, 1)

    # 4) airborne & vy
    bb.write_method_6(1 if airborne else 0, 1)
    if airborne:
        _write_method_24(bb, velocity_y)

    payload = bb.to_bytes()
    return struct.pack(">HH", 0x07, len(payload)) + payload

# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def tick_npc_brains(all_sessions: List, dt_ms: Optional[int] = None):
    """
    Drive server-side NPC brains. Call this on a timer (e.g., every 50-100ms)
    from the main loop *after* processed incoming packets for the tick.

    all_sessions: your existing list of sessions.
    Each session is expected to have:
      - world_loaded: bool
      - current_level: str
      - entities: Dict[int, dict]  # includes NPCs & players in that session’s view
      - conn: socket
    We treat the level as a shared space; we’ll broadcast 0x07 to everyone in that level.
    """
    now = _now_ms()

    # Gather players by level for target selection
    players_by_level: Dict[str, Dict[int, Tuple[int,int]]] = {}
    for s in all_sessions:
        if not s.world_loaded or not s.current_level:
            continue
        # find the client entity position
        ent = s.entities.get(s.clientEntID, None)
        if not ent:
            continue
        px, py = ent.get('pos_x'), ent.get('pos_y')
        if px is None or py is None:
            continue
        players_by_level.setdefault(s.current_level, {})[s.clientEntID] = (px, py)

    # For each level, walk through NPCs (we’ll scan the first session that has them)
    for s in all_sessions:
        if not s.world_loaded or not s.current_level:
            continue
        level = s.current_level
        if getattr(s, "_brains_done_level", None) == level:
            continue
        setattr(s, "_brains_done_level", level)
        npc_list = []
        for sess in all_sessions:
            if sess.world_loaded and sess.current_level == level:
                for eid, e in sess.entities.items():
                    if not e or e.get('is_player'):
                        continue
                    if 'name' in e:
                        npc_list.append((eid, e))
                break

        if not npc_list:
            continue

        def _broadcast(pkt_bytes: bytes):
            for sess in all_sessions:
                if sess.world_loaded and sess.current_level == level:
                    try:
                        sess.conn.sendall(pkt_bytes)
                    except Exception:
                        pass

        pl_map = players_by_level.get(level, {})

        for npc_id, npc in npc_list:
            x = npc.get('pos_x', npc.get('x', 0))
            y = npc.get('pos_y', npc.get('y', 0))
            vx = npc.get('velocity_x', 0)
            brain = _get_brain(level, npc_id,
                               int(npc.get('spawn_x', x)),
                               int(npc.get('spawn_y', y)))

            if now - brain.last_tick_ms < TICK_MS:
                continue
            dt = (now - brain.last_tick_ms) / 1000.0 if brain.last_tick_ms else (TICK_MS / 1000.0)
            brain.last_tick_ms = now

            if brain.target_id is None:
                best, best_d2 = None, None
                for pid, (px, py) in pl_map.items():
                    d2 = _dist2(x, y, px, py)
                    if d2 <= AGGRO_RADIUS * AGGRO_RADIUS and (best_d2 is None or d2 < best_d2):
                        best, best_d2 = pid, d2
                if best is not None:
                    brain.target_id = best
                    brain.state = "CHASE"
            else:
                ppos = pl_map.get(brain.target_id)
                if ppos is None:
                    brain.target_id = None
                    brain.state = "RETURN"

            if brain.state == "CHASE" and brain.target_id is not None:
                px, py = pl_map.get(brain.target_id, (x, y))
                if _dist2(x, y, brain.home_x, brain.home_y) > LEASH_DISTANCE * LEASH_DISTANCE:
                    brain.target_id = None
                    brain.state = "RETURN"

            target_x = x
            if brain.state == "CHASE" and brain.target_id is not None:
                px, py = pl_map.get(brain.target_id, (x, y))
                dir_x = _sign(px - x)
                target_x = x + dir_x * NPC_SPEED * dt
            elif brain.state == "RETURN":
                if abs(x - brain.home_x) <= 2:
                    brain.state = "IDLE"
                    target_x = brain.home_x
                else:
                    dir_x = _sign(brain.home_x - x)
                    target_x = x + dir_x * NPC_SPEED * dt

            new_x = int(round(target_x))
            new_y = int(round(y))

            old_x = int(npc.get('pos_x', new_x))
            old_y = int(npc.get('pos_y', new_y))
            dx = new_x - old_x
            dy = new_y - old_y
            dvx = int((dx / max(dt, 1e-3)))

            npc['pos_x'] = new_x
            npc['pos_y'] = new_y
            npc['velocity_x'] = dvx
            npc['ent_state'] = ENTITY_STATE_MOVING if (dx or dy) else ENTITY_STATE_IDLE
            npc['b_left'] = (dx < 0)
            npc['b_running'] = bool(dx)
            npc['b_jumping'] = False
            npc['b_dropping'] = False
            npc['b_backpedal'] = False

            # build & broadcast 0x07 if anything changed
            if dx or dy or dvx or brain.last_x != new_x or brain.last_y != new_y:
                pkt = _build_pkt_0x07(
                    entity_id=npc_id,
                    delta_x=dx,
                    delta_y=dy,
                    delta_vx=dvx,
                    ent_state=npc.get('ent_state', ENTITY_STATE_IDLE),
                    flags={
                        'b_left': npc['b_left'],
                        'b_running': npc['b_running'],
                        'b_jumping': npc['b_jumping'],
                        'b_dropping': npc['b_dropping'],
                        'b_backpedal': npc['b_backpedal'],
                    },
                    airborne=False,
                    velocity_y=0,
                )
                _broadcast(pkt)

            brain.last_x, brain.last_y = new_x, new_y
