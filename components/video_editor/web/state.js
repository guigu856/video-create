export function createEditorState() {
  const listeners = new Set();
  const state = {
    project: null,
    selectedClipId: null,
    playheadSeconds: 0,
    pixelsPerSecond: 80,
    isPlaying: false,
  };

  function emit(reason) {
    for (const listener of listeners) {
      listener(state, reason);
    }
  }

  return {
    get value() {
      return state;
    },

    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    setProject(project) {
      state.project = project;
      const selected = findClip(project, state.selectedClipId);
      if (!selected) state.selectedClipId = null;
      state.playheadSeconds = Math.min(state.playheadSeconds, projectDuration(project));
      emit("project");
    },

    selectClip(clipId) {
      state.selectedClipId = clipId;
      emit("selection");
    },

    setPlayhead(seconds) {
      const duration = projectDuration(state.project);
      state.playheadSeconds = Math.max(0, Math.min(Number(seconds) || 0, duration));
      emit("playhead");
    },

    setPlaying(isPlaying) {
      state.isPlaying = Boolean(isPlaying);
      emit("playback");
    },

    setPixelsPerSecond(value) {
      state.pixelsPerSecond = Math.max(30, Math.min(180, Number(value) || 80));
      emit("zoom");
    },
  };
}

export function allClips(project) {
  if (!project) return [];
  return project.tracks.flatMap((track) =>
    track.clips.map((clip) => ({ track, clip })),
  );
}

export function findClip(project, clipId) {
  if (!project || !clipId) return null;
  return allClips(project).find(({ clip }) => clip.id === clipId) ?? null;
}

export function findAsset(project, assetId) {
  if (!project || !assetId) return null;
  return project.assets.find((asset) => asset.id === assetId) ?? null;
}

export function projectDuration(project) {
  return allClips(project).reduce(
    (duration, { clip }) => Math.max(duration, clip.timeline_start + clip.duration),
    0,
  );
}

export function visibleClips(project, seconds) {
  return allClips(project).filter(
    ({ clip }) =>
      seconds >= clip.timeline_start && seconds < clip.timeline_start + clip.duration,
  );
}

const TRANSFORM_PROPS = ["x", "y", "width", "height", "rotation", "opacity"];

function interpolateProperty(points, base, localTime) {
  if (localTime <= points[0][0]) return base;
  for (let i = 0; i < points.length - 1; i += 1) {
    const [t0, v0] = points[i];
    const [t1, v1] = points[i + 1];
    if (localTime < t1) return v0 + ((v1 - v0) * (localTime - t0)) / (t1 - t0);
  }
  return points[points.length - 1][1];
}

export function transformAt(clip, seconds) {
  const base = clip.transform;
  const keyframes = clip.keyframes ?? [];
  if (keyframes.length === 0) return base;
  const localTime = seconds - clip.timeline_start;
  const result = { ...base };
  for (const prop of TRANSFORM_PROPS) {
    const points = keyframes
      .filter((kf) => kf[prop] != null)
      .map((kf) => [kf.time, kf[prop]]);
    if (points.length >= 2) result[prop] = interpolateProperty(points, base[prop], localTime);
  }
  return result;
}

export function formatTimecode(seconds) {
  const safeSeconds = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safeSeconds / 60);
  const remainder = safeSeconds - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${remainder.toFixed(3).padStart(6, "0")}`;
}
