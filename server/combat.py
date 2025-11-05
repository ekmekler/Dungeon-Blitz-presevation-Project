import struct

from BitBuffer import BitBuffer
from Character import save_characters
from Commands import build_loot_drop_packet
from bitreader import BitReader
from constants import LinkUpdater
from globals import send_consumable_update


def handle_entity_destroy(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        entity_id = br.read_method_9()
    except Exception as e:
        print(f"[{session.addr}] [PKT0D] Parse error: {e}, raw={payload.hex()}")
        return

    if entity_id in session.entities:
        del session.entities[entity_id]

    if session.clientEntID == entity_id:
        session.clientEntID = None

    for other in all_sessions:
        if (other is not session
            and other.world_loaded
            and other.current_level == session.current_level):
            try:
                other.conn.sendall(data)
                print(f"[{session.addr}] [PKT0D] Broadcasted destroy to {other.addr}")
            except Exception as e:
                print(f"[{session.addr}] [PKT0D] Error sending to {other.addr}: {e}")

def PKTTYPE_BUFF_TICK_DOT(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        target_id     = br.read_method_9()
        source_id     = br.read_method_9()
        power_type_id = br.read_method_9()
        amount        = br.read_method_24()
    except Exception as e:
        print(f"[{session.addr}] [PKT79] Parse error: {e}, raw={payload.hex()}")
        return

    print(f"[{session.addr}] [PKT79] Buff tick: target={target_id}, "
          f"source={source_id}, power={power_type_id}, amount={amount}")

    for other in all_sessions:
        if (other is not session
            and other.world_loaded
            and other.current_level == session.current_level):
            try:
                other.conn.sendall(data)
            except Exception as e:
                print(f"[{session.addr}] [PKT79] Forward error to {other.addr}: {e}")

def handle_respawn_ack(session, data, all_sessions):

    br = BitReader(data[4:], debug=False)
    try:
        entity_id = br.read_method_9()
        spawn_pos = br.read_method_24()
        used_potion = bool(br.read_method_15())
    except Exception as e:
        print(f"[{session.addr}] [PKT82] Parse error: {e}")
        return

    # Update server state: mark entity alive at spawn_pos
    ent = session.entities.get(entity_id)
    if ent is not None:
        ent['pos_x'] = spawn_pos
        ent['pos_y'] = 0
        ent['is_alive'] = True
        print(f"[{session.addr}] [PKT82] Entity {entity_id} respawned at {spawn_pos}, potion={used_potion}")

        for other in all_sessions:
            if other is not session and other.world_loaded and other.current_level == session.current_level:
                other.conn.sendall(data)
    else:
        print(f"[{session.addr}] [PKT82] Unknown entity {entity_id}")

def handle_request_respawn(session, data, all_sessions):
    br = BitReader(data[4:], debug=False)
    try:
        use_potion = bool(br.read_method_15())
    except:
        return

    if use_potion:
        for char in session.char_list:
            if char['name'] == session.current_character:
                for item in char.get('consumables', []):
                    if item.get('consumableID') == 9:
                        if item['count'] > 0:
                            item['count'] -= 1
                            new_count = item['count']
                            print(f"[{session.addr}] [PKT77] Used potion, new count={new_count}")
                            save_characters(session.user_id, session.char_list)
                            send_consumable_update(session.conn, 9, new_count)
                        break
                break

    # 4) Send RESPAWN_COMPLETE (0x80)
    #TODO....
    # compute actual spawn location
    spawn_pos = 0
    bb = BitBuffer()
    bb.write_signed_method_45(spawn_pos)
    bb.write_method_11(1 if use_potion else 0, 1)
    body = bb.to_bytes()
    session.conn.sendall(struct.pack(">HH", 0x80, len(body)) + body)

    heal_amount = 10000
    bb2 = BitBuffer()
    bb2.write_method_9(session.clientEntID or 0)
    bb2.write_method_24(heal_amount)
    body2 = bb2.to_bytes()
    session.conn.sendall(struct.pack(">HH", 0x78, len(body2)) + body2)
    print(f"[{session.addr}] [PKT77] Respawned at {spawn_pos}, potion_used={use_potion}")

def handle_grant_reward(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=True)
    try:
        grantor_id    = br.read_method_9()
        target_id     = br.read_method_9()

        flag_showXP   = bool(br.read_method_15())
        xp_rate       = br.read_float()

        flag_showGold = bool(br.read_method_15())
        gold_rate     = br.read_float()

        flag_showHeal = bool(br.read_method_15())
        flag_showMana = bool(br.read_method_15())

        code_xpType   = br.read_method_9()
        code_goldType = br.read_method_9()
        code_manaType = br.read_method_9()
        code_healType = br.read_method_9()

        # **NOW** read the drop coordinates:
        drop_x = br.read_method_24()   # signed 24-bit
        drop_y = br.read_method_24()   # signed 24-bit

        has_extra     = bool(br.read_method_15())
        extra_id      = br.read_method_9() if has_extra else None

    except Exception as e:
        print("…parsing error…")
        return

    # now build loot_drops using the true drop_x, drop_y:
    loot_drops = []
    if flag_showXP:
        loot_drops.append(('xp', code_xpType, int(xp_rate)))
    if flag_showGold:
        loot_drops.append(('gold', code_goldType, int(gold_rate)))
    if flag_showHeal:
        loot_drops.append(('healing', code_healType, 0))
    if flag_showMana:
        loot_drops.append(('mana', code_manaType, 0))
    if extra_id:
        # the client expects two fixed‐width values for gear:
        loot_drops.append(('gear', extra_id, extra_id))

    # broadcast one 0x32 per drop:
    for rtype, v1, v2 in loot_drops:
        pkt = build_loot_drop_packet(
            entity_id=target_id,
            x=drop_x,
            y=drop_y,
            reward_type=rtype,
            value1=v1,
            value2=v2
        )
        for other in all_sessions:
            if other.world_loaded and other.current_level == session.current_level:
                other.conn.sendall(pkt)

def handle_power_hit(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        target_id = br.read_method_9()
        source_id = br.read_method_9()

        # 3) Read damage/effect value
        value     = br.read_method_24()
        power_id  = br.read_method_9()

        # 5) Optional param5 (var-int)
        has_p5    = bool(br.read_method_15())
        param5    = br.read_method_9() if has_p5 else 0

        # 6) Optional param6 (var-int)
        has_p6    = bool(br.read_method_15())
        param6    = br.read_method_9() if has_p6 else 0

        # 7) Final boolean flag (crit? or similar)
        param7    = bool(br.read_method_15())

        props = {
            'target_id': target_id,
            'source_id': source_id,
            'value':      value,
            'power_id':   power_id,
            'param5':     param5 if has_p5 else None,
            'param6':     param6 if has_p6 else None,
            'flag':       param7,
        }
        #print(f"[{session.addr}] [PKT0A] Parsed power-hit:")
        #pprint.pprint(props, indent=4)

        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)

    except Exception as e:
        print(f"[{session.addr}] [PKT0A] Error parsing power-hit: {e}, raw={payload.hex()}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)

def handle_projectile_explode(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        entity_id       = br.read_method_9()
        remote_missile  = br.read_method_9()
        x = br.read_method_24()
        y = br.read_method_24()
        flag = bool(br.read_method_15())
        props = {
            'entity_id':      entity_id,
            'remote_missile': remote_missile,
            'x':              x,
            'y':              y,
            'flag':           flag,
        }
        #print(f"[{session.addr}] [PKT0E] Parsed projectile-explode:")
        #pprint.pprint(props, indent=4)

        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)

    except Exception as e:
        print(f"[{session.addr}] [PKT0E] Error parsing projectile explode: {e}, raw={payload.hex()}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)

def handle_add_buff(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        entity_id  = br.read_method_9()
        param2     = br.read_method_9()
        param3     = br.read_method_9()
        param5     = br.read_method_9()   # note: client writes param5 _before_ param4
        param4     = br.read_method_9()
        param6     = br.read_method_9()

        has_vector = bool(br.read_method_15())
        vector     = []
        if has_vector:
            length = br.read_method_9()
            for _ in range(length):
                power_node_type_id = br.read_method_9()
                mod_count          = br.read_method_9()
                mods               = [br.read_method_560() for _ in range(mod_count)]
                vector.append({
                    'power_node_type_id': power_node_type_id,
                    'mod_values':         mods
                })

        props = {
            'entity_id': entity_id,
            'param2':     param2,
            'param3':     param3,
            'param4':     param4,
            'param5':     param5,
            'param6':     param6,
            'vector':     vector if has_vector else None
        }
        #print(f"[{session.addr}] [PKT0B] Parsed add-buff:")
        #pprint.pprint(props, indent=4)

        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)

    except Exception as e:
        print(f"[{session.addr}] [PKT0B] Error parsing add-buff: {e}, raw={payload.hex()}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)

def handle_remove_buff(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=False)
    try:
        entity_id   = br.read_method_9()
        buff_type   = br.read_method_9()
        instance_id = br.read_method_9()

        props = {
            'entity_id':   entity_id,
            'buff_type':   buff_type,
            'instance_id': instance_id,
        }
        #print(f"[{session.addr}] [PKT0C] Parsed remove-buff:")
        #pprint.pprint(props, indent=4)

        for other in all_sessions:
            if (other is not session
                and other.world_loaded
                and other.current_level == session.current_level):
                other.conn.sendall(data)
                print(f"[{session.addr}] [PKT0C] Broadcasted to {other.addr}")

    except Exception as e:
        print(f"[{session.addr}] [PKT0C] Error parsing remove-buff: {e}, raw={payload.hex()}")
        if br.debug:
            for line in br.get_debug_log():
                print(line)

def handle_change_max_speed(session, data, all_sessions):
    payload = data[4:]
    br = BitReader(payload, debug=True)

    try:
        entity_id = br.read_method_4()
        speed_mod_int = br.read_method_4()
    except Exception as e:
        return

    # Find the entity
    entity = session.entities.get(entity_id)
    if not entity:
        #print(f"[{session.addr}] [PKT0x8A] Entity {entity_id} not found")
        return

    # Update the entity's behaviorSpeedMod
    entity['behaviorSpeedMod'] = speed_mod_int * LinkUpdater.VELOCITY_DEFLATE
    #print(f"[{session.addr}] [PKT0x8A] Updated entity {entity_id} behaviorSpeedMod to {entity['behaviorSpeedMod']}")

    bb = BitBuffer()
    bb.write_method_4(entity_id)
    bb.write_method_4(speed_mod_int)  # Send the original integer value
    payload = bb.to_bytes()
    packet = struct.pack(">HH", 0x8A, len(payload)) + payload
    for other_session in all_sessions:
        if other_session.world_loaded and other_session.current_level == session.current_level:
            other_session.conn.sendall(packet)