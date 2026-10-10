"""The list of objects to sync, stored in the scene (fileInfo) by UUID so renames keep working.

A listed transform or group syncs every mesh below it; a listed mesh shape syncs itself.
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

    def contains(self, dag_path):
        """True when the mesh at dag_path or one of its parents is in the list."""
        if not self.uuids:
            return False
        wanted = set(self.uuids)
        path = om.MDagPath(dag_path)
        while path.length() > 0:
            if om.MFnDependencyNode(path.node()).uuid().asString() in wanted:
                return True
            path.pop()
        return False
