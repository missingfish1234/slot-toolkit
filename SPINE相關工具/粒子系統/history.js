(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.ParticleHistory = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // Snapshots are immutable, with unchanged branches shared between commands.
  // Callers may identify replace-only source assets to avoid traversing a rig
  // or copying a PNG on each pointer movement. Never mark editable data as such.
  function create(options = {}) {
    const maxSteps = Math.max(1, Math.floor(options.maxSteps || 100));
    const maxBytes = Math.max(1024, Number(options.maxBytes) || 96 * 1024 * 1024);
    const immutable = typeof options.immutable === 'function' ? options.immutable : () => false;
    const same = typeof options.same === 'function' ? options.same : (a, b) => a === b;
    const onChange = typeof options.onChange === 'function' ? options.onChange : () => {};
    const memo = new WeakMap(), nodes = new Map(), strings = new Map();
    let entries = [], cursor = -1, group = null, estimatedBytes = 0;

    function snapshot(value, previous, path = '') {
      if (!value || typeof value !== 'object') return value;
      const cached = immutable(value, path) && memo.get(value);
      if (cached) return cached;
      const array = Array.isArray(value), keys = Object.keys(value);
      const compatible = previous && typeof previous === 'object' && Array.isArray(previous) === array;
      let unchanged = !!compatible && Object.keys(previous).length === keys.length;
      const result = array ? [] : {};
      for (const key of keys) {
        const present = compatible && Object.prototype.hasOwnProperty.call(previous, key);
        const child = snapshot(value[key], present ? previous[key] : undefined, path ? path + '.' + key : key);
        Object.defineProperty(result, key, {value: child, enumerable: true, writable: true, configurable: true});
        if (!present || child !== previous[key]) unchanged = false;
      }
      const frozen = unchanged ? previous : Object.freeze(result);
      if (immutable(value, path)) memo.set(value, frozen);
      return frozen;
    }
    // Count the retained graph, not JSON size times the number of commands.
    // Shared images, strings and rig branches consume the budget only once.
    function retain(value) {
      if (typeof value === 'string') {
        const count = strings.get(value) || 0; strings.set(value, count + 1);
        if (!count) estimatedBytes += 16 + value.length * 2;
      } else if (value && typeof value === 'object') {
        const count = nodes.get(value) || 0; nodes.set(value, count + 1);
        if (count) return;
        const keys = Object.keys(value); estimatedBytes += 48 + keys.length * 16;
        for (const key of keys) { retain(key); retain(value[key]); }
      }
    }
    function release(value) {
      if (typeof value === 'string') {
        const count = strings.get(value) || 0;
        if (count > 1) strings.set(value, count - 1);
        else if (count) { strings.delete(value); estimatedBytes -= 16 + value.length * 2; }
      } else if (value && typeof value === 'object') {
        const count = nodes.get(value) || 0;
        if (count > 1) { nodes.set(value, count - 1); return; }
        if (!count) return;
        nodes.delete(value); const keys = Object.keys(value); estimatedBytes -= 48 + keys.length * 16;
        for (const key of keys) { release(key); release(value[key]); }
      }
    }
    function info() {
      return {canUndo: cursor > 0, canRedo: cursor >= 0 && cursor < entries.length - 1,
        undoCount: Math.max(0, cursor), redoCount: Math.max(0, entries.length - cursor - 1),
        estimatedBytes, grouped: !!group};
    }
    function notify() { onChange(info()); }
    function replaceCurrent(value) {
      if (value === entries[cursor]) return;
      retain(value); release(entries[cursor]); entries[cursor] = value;
    }
    function trim() {
      while (entries.length > maxSteps + 1 || estimatedBytes > maxBytes && entries.length > 2) {
        if (cursor > 0) { release(entries.shift()); cursor--; }
        else release(entries.pop());
      }
    }
    function reset(value) {
      entries.forEach(release); entries = []; cursor = -1; group = null;
      const first = snapshot(value); retain(first); entries = [first]; cursor = 0; notify();
      return first;
    }
    function commit(next) {
      const current = entries[cursor];
      if (same(next, current)) { replaceCurrent(next); return false; }
      while (entries.length > cursor + 1) release(entries.pop());
      retain(next); entries.push(next); cursor++; trim(); return true;
    }
    function observe(value) {
      if (cursor < 0) { reset(value); return false; }
      // Capture only the final state of a gesture. The baseline is already
      // frozen, so restoring on Escape creates no command or redo invalidation.
      if (group) { group.latest = value; return false; }
      const changed = commit(snapshot(value, entries[cursor])); notify(); return changed;
    }
    function begin(value) {
      if (group) end(value);
      observe(value); group = {latest: value}; notify();
    }
    function end(value) {
      if (!group) return false;
      const latest = value === undefined ? group.latest : value; group = null;
      const changed = commit(snapshot(latest, entries[cursor])); notify(); return changed;
    }
    function undo(value) {
      if (group) end(value);
      if (cursor <= 0) return null;
      cursor--; notify(); return entries[cursor];
    }
    function redo(value) {
      if (group) end(value);
      if (cursor < 0 || cursor >= entries.length - 1) return null;
      cursor++; notify(); return entries[cursor];
    }
    return {reset, observe, begin, end, undo, redo, info,
      current: () => cursor < 0 ? null : entries[cursor]};
  }
  return {create};
});
