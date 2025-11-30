from Character import save_characters
from bitreader import BitReader
from constants import class_20


def handle_equip_pets(session, data, all_sessions):
    reader = BitReader(data[4:])

    pets = []
    for i in range(4):
        type_id = reader.read_method_6(7)
        unique_id = reader.read_method_9()
        pets.append((type_id, unique_id))

    (active_type, active_iter) = pets[0]
    resting = pets[1:]

    for char in session.char_list:
        if char.get("name") != session.current_character:
            continue

        char["activePet"] = {
            "typeID": active_type,
            "special_id": active_iter
        }

        char["restingPets"] = [
            {"typeID": resting[0][0], "special_id": resting[0][1]},
            {"typeID": resting[1][0], "special_id": resting[1][1]},
            {"typeID": resting[2][0], "special_id": resting[2][1]}
        ]

        save_characters(session.user_id, session.char_list)
        break


def handle_mount_equip_packet(session, data, all_sessions):
    reader = BitReader(data[4:])
    entity_id = reader.read_method_4()
    mount_id  = reader.read_method_6(class_20.const_297)

    char = next((c for c in session.char_list
                 if c.get("name") == session.current_character), None)

    char["equippedMount"] = mount_id
    session.player_data["characters"] = session.char_list
    save_characters(session.user_id, session.char_list)

    for other in all_sessions:
        if (
            other is not session
            and other.player_spawned
            and other.current_level == session.current_level
        ):
            other.conn.sendall(data)