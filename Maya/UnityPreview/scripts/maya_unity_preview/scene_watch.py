"""Event-driven mesh sync.

Maya API callbacks only *mark* meshes as changed; a short single-shot Qt timer then hands the
batch to the tool on the main thread. Nothing is polled: when nothing changes, nothing runs.

Watched events
- mesh edited / transform moved  : node dirty-plug callback on each mesh shape
- material (shading group) change : attribute-changed callback (instObjGroups connections)
- mesh renamed                    : name-changed callback (old Unity object is removed)
- mesh created / deleted          : DG node added / removed callbacks
- new scene / open scene          : everything is removed in Unity, then re-sent
"""
from maya import cmds
from maya.api import OpenMaya as om

from .qt import QtCore

BATCH_MS = 120


def _remove_callbacks(ids):
    for callback_id in ids:
        try:
            om.MMessage.removeCallback(callback_id)
        except RuntimeError:
            pass


class SceneWatch(QtCore.QObject):
    """flush(paths, removed_names) -> bool. Return False when busy; the batch is retried."""

    def __init__(self, flush, parent=None):
        super().__init__(parent)
        self._flush = flush
        self._watched = {}       # handle hash -> (MObjectHandle, [callback ids])
        self._sent_names = {}    # handle hash -> DAG path last sent to Unity
        self._dirty = {}         # handle hash -> MObjectHandle
        self._removed = set()    # Unity names to remove
        self._stale_callbacks = []
        self._global_callbacks = []
        self.active = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(BATCH_MS)
        self._timer.timeout.connect(self._on_timer)

    # ------------------------------------------------------------------ lifecycle
    def start(self):
        if self.active:
            return
        self.active = True
        self._global_callbacks = [
            om.MDGMessage.addNodeAddedCallback(self._node_added, "mesh"),
            om.MDGMessage.addNodeRemovedCallback(self._node_removed, "mesh"),
            om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeNew, self._before_scene),
            om.MSceneMessage.addCallback(om.MSceneMessage.kBeforeOpen, self._before_scene),
            om.MSceneMessage.addCallback(om.MSceneMessage.kAfterNew, self._after_scene),
            om.MSceneMessage.addCallback(om.MSceneMessage.kAfterOpen, self._after_scene),
        ]
        self._watch_all(mark_dirty=True)

    def stop(self):
        self.active = False
        self._timer.stop()
        _remove_callbacks(self._global_callbacks)
        self._global_callbacks = []
        for _, ids in self._watched.values():
            _remove_callbacks(ids)
        _remove_callbacks(self._stale_callbacks)
        self._watched.clear()
        self._stale_callbacks = []
        self._dirty.clear()
        self._removed.clear()
        self._sent_names.clear()

    def resend_all(self):
        """Mark every mesh as changed (e.g. after Unity restarted)."""
        if self.active:
            self._sent_names.clear()
            self._watch_all(mark_dirty=True)

    # ------------------------------------------------------------------ watching
    def _watch_all(self, mark_dirty):
        selection = om.MSelectionList()
        for shape in cmds.ls(type="mesh", long=True, noIntermediate=True) or []:
            try:
                selection.add(shape)
            except RuntimeError:
                continue
        for i in range(selection.length()):
            self._watch(selection.getDependNode(i), mark_dirty)

    def _watch(self, node, mark_dirty):
        handle = om.MObjectHandle(node)
        key = handle.hashCode()
        if key not in self._watched:
            ids = [
                om.MNodeMessage.addNodeDirtyPlugCallback(node, self._mesh_dirty),
                om.MNodeMessage.addAttributeChangedCallback(node, self._attribute_changed),
                om.MNodeMessage.addNameChangedCallback(node, self._name_changed),
            ]
            self._watched[key] = (handle, ids)
        if mark_dirty:
            self._mark(handle)

    def _mark(self, handle):
        self._dirty[handle.hashCode()] = handle
        if not self._timer.isActive():
            self._timer.start()

    # ------------------------------------------------------------------ callbacks (mark only)
    def _mesh_dirty(self, node, plug, *_):
        self._mark(om.MObjectHandle(node))

    def _attribute_changed(self, message, plug, other_plug, *_):
        if message & (om.MNodeMessage.kConnectionMade | om.MNodeMessage.kConnectionBroken):
            self._mark(om.MObjectHandle(plug.node()))

    def _name_changed(self, node, previous_name, *_):
        self._mark(om.MObjectHandle(node))

    def _node_added(self, node, *_):
        if self.active:
            self._watch(node, mark_dirty=True)

    def _node_removed(self, node, *_):
        key = om.MObjectHandle(node).hashCode()
        entry = self._watched.pop(key, None)
        if entry:
            self._stale_callbacks.extend(entry[1])   # removed later, outside this callback
        self._dirty.pop(key, None)
        name = self._sent_names.pop(key, None)
        if name:
            self._removed.add(name)
            if not self._timer.isActive():
                self._timer.start()

    def _before_scene(self, *_):
        self._removed.update(self._sent_names.values())
        self._sent_names.clear()
        self._dirty.clear()
        for _, ids in self._watched.values():
            self._stale_callbacks.extend(ids)
        self._watched.clear()
        self._on_timer()

    def _after_scene(self, *_):
        if self.active:
            self._watch_all(mark_dirty=True)

    # ------------------------------------------------------------------ batch
    def _on_timer(self):
        _remove_callbacks(self._stale_callbacks)
        self._stale_callbacks = []
        if not self.active:
            return
        paths, renamed_from, keys = [], set(), []
        for key, handle in list(self._dirty.items()):
            if not handle.isValid() or not handle.isAlive():
                continue
            node = handle.object()
            if om.MFnDagNode(node).isIntermediateObject:
                continue
            path = om.MDagPath.getAPathTo(node).fullPathName()
            previous = self._sent_names.get(key)
            if previous and previous != path:
                renamed_from.add(previous)
            paths.append(path)
            keys.append((key, path))
        removed = (self._removed | renamed_from) - set(paths)
        if not paths and not removed:
            self._dirty.clear()
            return
        if not self._flush(paths, sorted(removed)):
            self._timer.start()      # busy: keep the batch and try again shortly
            return
        self._dirty.clear()
        self._removed.clear()
        for key, path in keys:
            self._sent_names[key] = path
