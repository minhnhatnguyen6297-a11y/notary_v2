(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.DiagramStateStore = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function normalizeSnapshot(snapshot) {
    const state = snapshot && typeof snapshot === "object" ? snapshot : {};
    return {
      participants: Array.isArray(state.participants) ? state.participants : [],
      warnings: Array.isArray(state.warnings) ? state.warnings : [],
      shareMode: state.shareMode || "auto",
      engineState: state.engineState || null,
      engineInput: state.engineInput || null,
      engineResult: state.engineResult || null,
      calculationStatus: state.calculationStatus || "calculating",
      updatedAt: state.updatedAt || "",
    };
  }

  function createStore(initialSnapshot, onPublish) {
    const subscribers = new Set();
    let snapshot = normalizeSnapshot(initialSnapshot);
    let pendingSnapshot = null;
    let saving = false;
    let busyCount = 0;

    function emit(nextSnapshot) {
      snapshot = normalizeSnapshot(nextSnapshot);
      if (typeof onPublish === "function") {
        onPublish(snapshot);
      }
      subscribers.forEach((cb) => {
        try {
          cb(snapshot);
        } catch (err) {
          console.error("DiagramState subscriber failed", err);
        }
      });
      return snapshot;
    }

    return {
      getCommittedState() {
        return snapshot;
      },
      publish(nextSnapshot) {
        if (saving) {
          pendingSnapshot = normalizeSnapshot(nextSnapshot);
          snapshot = pendingSnapshot;
          return snapshot;
        }
        pendingSnapshot = null;
        return emit(nextSnapshot);
      },
      subscribe(cb, options = {}) {
        if (typeof cb !== "function") return function noop() {};
        subscribers.add(cb);
        if (options.replay !== false) {
          cb(snapshot);
        }
        return function unsubscribe() {
          subscribers.delete(cb);
        };
      },
      isSaving() {
        return saving;
      },
      setSaving(nextSaving) {
        saving = !!nextSaving;
        if (!saving && pendingSnapshot) {
          const replay = pendingSnapshot;
          pendingSnapshot = null;
          emit(replay);
        }
      },
      incrementBusy() {
        busyCount += 1;
        return busyCount;
      },
      decrementBusy() {
        busyCount = Math.max(0, busyCount - 1);
        return busyCount;
      },
      getBusyCount() {
        return busyCount;
      },
      isBusy() {
        return busyCount > 0;
      },
    };
  }

  return {
    normalizeSnapshot,
    createStore,
  };
});
