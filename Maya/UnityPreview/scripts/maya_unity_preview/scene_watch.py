"""Event-driven mesh sync.

Maya API callbacks only *mark* meshes as changed; a short single-shot Qt timer then hands the
batch to the controller on the main thread. Nothing is polled: when nothing changes, nothing runs.

Watched events (per mesh shape)
- transform / parent moved          : MDagMessage world-matrix-modified (works with Evaluation Manager)
- vertices edited, attributes set   : node dirty-plug + attribute-set callbacks
- material (shading group) changed  : attribute-changed (instObjGroups connections)
- renamed                           : name-changed (old Unity object is removed)
Global events
- mesh created / deleted            : DG node added / removed
- manipulator released, undo, redo,
  time changed                      : every watched target is re-checked
- new scene / open scene            : everything is removed in Unity, then re-sent
Dependencies (set by the controller after each send)
- material / file / bump2d node changed : every mesh using it is re-sent (with its MATERIAL_DEF)

Only meshes for which `is_target(MDagPath)` is True are sent; a mesh that stops being a
target (removed from the sync list) is removed from Unity.
"""
from maya import cmds
from maya.api import OpenMaya as om

from .qt import QtCore

BATCH_MS = 120
RECHECK_EVENTS = ("DragRelease", "Undo", "Redo", "timeChanged")


def _remove_callbacks(ids):
    for callback_id in ids:
        try:
            om.MMessage.removeCallback(callback_id)
        except RuntimeError:
            pass


class SceneWatch(QtCore.QObject):
    """flush(paths, removed_names) -> bool. Return False when busy; the batch is retried."""

    def __init__(self, flush, is_target=None, on_scene_opened=None, parent=None):
        super().__init__(parent)
        self._flush = flush
        self._is_target = is_target or (lambda dag_path: True)
        self._on_scene_opened = on_scene_opened
        self._watched = {}       # handle hash -> (MObjectHandle, [callback ids])
        self._sent_names = {}    # handle hash -> DAG path last sent to Unity
        self._dirty = {}         # handle hash -> MObjectHandle
        self._removed = set()    # Unity names to remove
        self._deps = {}          # dependency hash -> (MObjectHandle, [callback ids], {mesh hashes})
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
        for event in RECHECK_EVENTS:
            try:
                self._global_callbacks.append(om.MEventMessage.addEventCallback(event, self._recheck))
            except RuntimeError:
                pass
        self._watch_all(mark_dirty=True)

    def stop(self):
        self.active = False
        self._timer.stop()
        _remove_callbacks(self._global_callbacks)
        self._global_callbacks = []
        for _, ids in self._watched.values():
            _remove_callbacks(ids)
        for _, ids, _meshes in self._deps.values():
            _remove_callbacks(ids)
        self._deps.clear()
        _remove_callbacks(self._stale_callbacks)
        self._watched.clear()
        self._stale_callbacks = []
        self._dirty.clear()
        self._removed.clear()
        self._sent_names.clear()

    def refresh(self):
        """Re-evaluate every mesh against is_target (sync list changed / resend requested)."""
        if self.active:
            self._watch_all(mark_dirty=True)

    def resend_all(self):
        """Forget what Unity has and send every target again."""
        if self.active:
            self._sent_names.clear()
            self._watch_all(mark_dirty=True)

    # ------------------------------------------------------------------ dependencies (materials)
    def set_dependencies(self, mesh_path, nodes):
        """Re-send mesh_path whenever one of `nodes` (material, file, bump2d...) changes."""
        if not self.active:
            return
        mesh_key = self._key_of(mesh_path)
        if mesh_key is None:
            return
        for name in nodes:
            selection = om.MSelectionList()
            try:
                selection.add(name)
            except RuntimeError:
                continue
            node = selection.getDependNode(0)
            handle = om.MObjectHandle(node)
            dep_key = handle.hashCode()
            if dep_key not in self._deps:
                callback = om.MNodeMessage.addAttributeChangedCallback(
                    node, lambda *_args, d=dep_key: self.mark_dependents(d))
                self._deps[dep_key] = (handle, [callback], set())
            self._deps[dep_key][2].add(mesh_key)

    def mark_dependents(self, dep):
        """dep: dependency hash or node name. Marks every mesh that uses it."""
        if not isinstance(dep, int):
            dep = self._key_of(dep)
        entry = self._deps.get(dep)
        if not entry:
            return
        for mesh_key in entry[2]:
            watched = self._watched.get(mesh_key)
            if watched:
                self._mark(watched[0])

    @staticmethod
    def _key_of(name):
        selection = om.MSelectionList()
        try:
            selection.add(name)
        except RuntimeError:
            return None
        return om.MObjectHandle(selection.getDependNode(0)).hashCode()

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
            try:
                dag_path = om.MDagPath.getAPathTo(node)
                ids.append(om.MDagMessage.addWorldMatrixModifiedCallback(
                    dag_path, lambda *_args, h=handle: self._mark(h)))
            except RuntimeError:
                pass   # node not in the DAG yet (just created); dirty / attribute callbacks still work
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
        if message & (om.MNodeMessage.kConnectionMade | om.MNodeMessage.kConnectionBroken
                      | om.MNodeMessage.kAttributeSet):
            self._mark(om.MObjectHandle(plug.node()))

    def _name_changed(self, node, previous_name, *_):
        self._mark(om.MObjectHandle(node))

    def _recheck(self, *_):
        for key in list(self._sent_names):
            entry = self._watched.get(key)
            if entry:
                self._mark(entry[0])

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
        for _, ids, _meshes in self._deps.values():
            self._stale_callbacks.extend(ids)
        self._watched.clear()
        self._deps.clear()
        self._on_timer()

    def _after_scene(self, *_):
        if self._on_scene_opened:
            self._on_scene_opened()
        if self.active:
            self._watch_all(mark_dirty=True)

    # ------------------------------------------------------------------ batch
    def _on_timer(self):
        _remove_callbacks(self._stale_callbacks)
        self._stale_callbacks = []
        if not self.active:
            return
        paths, renamed_from, sent, dropped = [], set(), [], []
        for key, handle in list(self._dirty.items()):
            if not handle.isValid() or not handle.isAlive():
                continue
            node = handle.object()
            if om.MFnDagNode(node).isIntermediateObject:
                continue
            dag_path = om.MDagPath.getAPathTo(node)
            path = dag_path.fullPathName()
            previous = self._sent_names.get(key)
            if not self._is_target(dag_path):
                if previous:
                    renamed_from.add(previous)   # no longer in the sync list -> remove in Unity
                    dropped.append(key)
                continue
            if previous and previous != path:
                renamed_from.add(previous)
            paths.append(path)
            sent.append((key, path))
        removed = (self._removed | renamed_from) - set(paths)
        if not paths and not removed:
            self._dirty.clear()
            return
        if not self._flush(paths, sorted(removed)):
            self._timer.start()      # busy: keep the batch and try again shortly
            return
        self._dirty.clear()
        self._removed.clear()
        for key in dropped:
            self._sent_names.pop(key, None)
        for key, path in sent:
            self._sent_names[key] = path
