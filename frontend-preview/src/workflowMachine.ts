export type InteractionPhase = 'idle' | 'tracking' | 'pressed' | 'morphing' | 'settling' | 'suspended';
export type WorkflowState = {
  phase: InteractionPhase;
  selected: number;
  revision: number;
  enabled: boolean;
  visible: boolean;
  hovering: boolean;
  focused: boolean;
  pressed: boolean;
  morphing: boolean;
  settling: boolean;
};
export type WorkflowEvent =
  | { type: 'ENABLE'; value: boolean }
  | { type: 'VISIBILITY'; value: boolean }
  | { type: 'SELECT'; index: number }
  | { type: 'MORPH_END' | 'REST'; revision: number }
  | { type: 'ENTER' | 'LEAVE' | 'FOCUS' | 'BLUR' | 'PRESS' | 'RELEASE' | 'CANCEL' };

function resolve(state: WorkflowState): WorkflowState {
  const phase: InteractionPhase = !state.enabled || !state.visible ? 'suspended'
    : state.pressed ? 'pressed'
    : state.morphing ? 'morphing'
    : state.settling ? 'settling'
    : state.hovering || state.focused ? 'tracking' : 'idle';
  return { ...state, phase };
}

export function initialWorkflowState(enabled: boolean): WorkflowState {
  return { phase: 'suspended', selected: 0, revision: 0, enabled, visible: false, hovering: false, focused: false, pressed: false, morphing: false, settling: false };
}

/** Explicit transitions keep fast input, cancellation, and stale completions predictable. */
export function workflowReducer(state: WorkflowState, event: WorkflowEvent): WorkflowState {
  if (event.type === 'SELECT') {
    if (!Number.isInteger(event.index) || event.index < 0 || event.index > 2 || event.index === state.selected) return state;
    return resolve({ ...state, selected: event.index, revision: state.revision + 1,
      morphing: state.enabled && state.visible, settling: false, pressed: false });
  }
  if (event.type === 'ENABLE' || event.type === 'VISIBILITY') {
    const key = event.type === 'ENABLE' ? 'enabled' : 'visible';
    if (state[key] === event.value) return state;
    return resolve({ ...state, [key]: event.value,
      ...(!event.value ? { pressed: false, hovering: false, morphing: false, settling: false, revision: state.revision + 1 } : {}) });
  }
  if (!state.enabled || !state.visible) return state;
  switch (event.type) {
    case 'ENTER': return resolve({ ...state, hovering: true, settling: false });
    case 'FOCUS': return resolve({ ...state, focused: true, settling: false });
    // A pointer press can blur the previously focused button before pointerup.
    // Window blur/cancel handles abandoning a press; focus changes must preserve it.
    case 'BLUR': return resolve({ ...state, focused: false, settling: !state.hovering && !state.pressed });
    case 'LEAVE': return resolve({ ...state, hovering: false, pressed: false, settling: true });
    case 'PRESS': return resolve({ ...state, pressed: true, settling: false });
    case 'RELEASE': return resolve({ ...state, pressed: false, settling: !state.morphing });
    case 'CANCEL': return resolve({ ...state, pressed: false, hovering: false, settling: !state.morphing });
    case 'MORPH_END':
      return event.revision === state.revision && state.morphing
        ? resolve({ ...state, morphing: false, settling: true }) : state;
    case 'REST':
      return event.revision === state.revision && state.settling
        ? resolve({ ...state, settling: false }) : state;
  }
}
