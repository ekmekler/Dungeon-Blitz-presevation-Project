class GameState:
    """
    Global group/party state.

    - groups: gid -> { "leader": name_lower, "members": [name_lower, ...] }
    - char_to_group: name_lower -> gid
    """
    def __init__(self):
        self.groups = {}
        self.char_to_group = {}

    def _norm(self, name: str) -> str:
        return (name or "").strip().lower()

    def get_gid_for_name(self, name: str):
        return self.char_to_group.get(self._norm(name))

    def get_group_for_name(self, name: str):
        gid = self.get_gid_for_name(name)
        if gid is None:
            return None, None
        return gid, self.groups.get(gid)

    def create_group(self, leader_name: str, gid: int):
        """
        Creates a new group with the given leader and ID.
        """
        leader_key = self._norm(leader_name)
        group = {
            "leader": leader_key,
            "members": [leader_key],   # keep order: leader first
        }
        self.groups[gid] = group
        self.char_to_group[leader_key] = gid
        return gid, group

    def add_member(self, gid: int, name: str):
        group = self.groups.get(gid)
        if not group:
            return None
        key = self._norm(name)
        if key not in group["members"]:
            group["members"].append(key)
        self.char_to_group[key] = gid
        return group

    def remove_member(self, name: str):
        """
        Remove a char from its group.
        Returns (gid, group) after removal (group might now be empty),
        or (None, None) if not in any group.
        """
        key = self._norm(name)
        gid = self.char_to_group.pop(key, None)
        if gid is None:
            return None, None

        group = self.groups.get(gid)
        if not group:
            return gid, None

        if key in group["members"]:
            group["members"].remove(key)

        # If the removed member was leader and others remain,
        # promote first member to leader.
        if key == group["leader"]:
            if group["members"]:
                group["leader"] = group["members"][0]
            else:
                group["leader"] = None

        return gid, group

    def set_leader(self, gid: int, name: str):
        group = self.groups.get(gid)
        if not group:
            return None
        key = self._norm(name)
        if key not in group["members"]:
            return group

        # Move new leader to front of member list
        group["members"] = [m for m in group["members"] if m != key]
        group["members"].insert(0, key)
        group["leader"] = key
        return group

    def disband_group(self, gid: int):
        group = self.groups.pop(gid, None)
        if not group:
            return
        for m in group["members"]:
            self.char_to_group.pop(m, None)

state = GameState()