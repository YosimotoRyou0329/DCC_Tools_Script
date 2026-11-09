"""The list of objects to sync, stored in the scene (fileInfo) by UUID so renames keep working.

Objects are expected to end up in groups: a listed node syncs its whole top-level group
(the top-most transform above it), so grouping a listed cube with other objects later brings
the other objects along, and ungrouping drops what is no longer in that group.
"""
import json

from maya import cmds
from maya.api import OpenMaya as om

FILE_INFO_KEY = "mayaUnityPreviewSyncList"


class SyncList:
    def __init__(self):
        self.uuids = []
        self.load()

    # ------------------------------------------------------------------ persistence (scene)
    def load(self):
        values = cmds.fileInfo(FILE_INFO_KEY, query=True) or []
        try:
            data = json.loads(values[0].encode().decode("unicode_escape")) if values else []
        except (ValueError, UnicodeError):
            data = []
        self.uuids = [u for u in data if isinstance(u, str)]

    def save(self):
        cmds.fileInfo(FILE_INFO_KEY, json.dumps(self.uuids))

    # ------------------------------------------------------------------ editing
    def add(self, nodes):
        """Add DAG nodes (names or long names). Returns how many were new."""
        added = 0
        for node in nodes:
            for uuid in cmds.ls(node, uuid=True, type="dagNode") or []:
                if uuid not in self.uuids:
                    self.uuids.append(uuid)
                    added += 1
        if added:
            self.save()
        return added

    def remove(self, uuids):
        before = len(self.uuids)
        self.uuids = [u for u in self.uuids if u not in set(uuids)]
        if len(self.uuids) != before:
            self.save()

    def clear(self):
        if self.uuids:
            self.uuids = []
            self.save()

    # ------------------------------------------------------------------ queries
    def items(self):
        """[(uuid, long name or None when the node no longer exists)]"""
        result = []
        for uuid in self.uuids:
            names = cmds.ls(uuid, long=True) or []
            result.append((uuid, names[0] if names else None))
        return result

    def groups(self):
        """One row per synced top-level group: [(root long name or None, [uuids])].

        Several listed objects inside one group (group4 and its pCube3, pCube4 ...) are one row,
        because the whole group is synced anyway. Missing nodes get a row each.
        """
        rows, index = [], {}
        for uuid, name in self.items():
            root = self.root_of(name) if name else None
            if root is None:
                rows.append((None, [uuid]))
            elif root in index:
                rows[index[root]][1].append(uuid)
            else:
                index[root] = len(rows)
                rows.append((root, [uuid]))
        return rows

    def roots(self):
        """Top-level transforms ("|group3") of the listed nodes that still exist."""
        if not self.uuids:
            return set()
        names = cmds.ls(*self.uuids, long=True) or []
        return {"|" + name.split("|")[1] for name in names if name.startswith("|") and len(name) > 1}

    def root_of(self, long_name):
        return "|" + long_name.split("|")[1] if long_name and long_name.startswith("|") else long_name

    def contains(self, dag_path, roots=None):
        """True when the mesh at dag_path is under the top-level group of a listed node."""
        roots = self.roots() if roots is None else roots
        return bool(roots) and self.root_of(dag_path.fullPathName()) in roots
