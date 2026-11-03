import { useCallback, useEffect, useReducer, useRef, type HTMLAttributes, type RefObject } from 'react';
import type { ContourFieldHandle } from './ContourField';
import { initialWorkflowState, workflowReducer } from './workflowMachine';

export default function useWorkflowInteraction(section: RefObject<HTMLElement>, art: RefObject<ContourFieldHandle>, enabled: boolean) {
  const [state, send] = useReducer(workflowReducer, enabled, initialWorkflowState);
  const pointer = useRef({ id: -1, x: 0, y: 0, pressed: false });

  useEffect(() => {
    send({ type: 'ENABLE', value: enabled });
    if (!enabled) { pointer.current.pressed = false; art.current?.resetPointer(); }
  }, [enabled, art]);

  useEffect(() => {
    const element = section.current;
    if (!element) return;
    let inView = false;
    const sync = () => {
      const visible = inView && !document.hidden;
      send({ type: 'VISIBILITY', value: visible });
      if (!visible) { pointer.current.pressed = false; art.current?.resetPointer(); }
    };
    const observer = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; sync(); }, { threshold: 0 });
    observer.observe(element);
    document.addEventListener('visibilitychange', sync);
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', sync); };
  }, [section, art]);

  const release = useCallback((cancelled = false) => {
    if (!pointer.current.pressed && !cancelled) return;
    pointer.current.pressed = false;
    pointer.current.id = -1;
    if (cancelled) art.current?.resetPointer();
    else art.current?.setPointer(pointer.current.x, pointer.current.y, false);
    send({ type: cancelled ? 'CANCEL' : 'RELEASE' });
  }, [art]);

  useEffect(() => {
    const up = (event: PointerEvent) => { if (event.pointerId === pointer.current.id) release(); };
    const cancel = (event: PointerEvent) => { if (event.pointerId === pointer.current.id) release(true); };
    const blur = () => release(true);
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', cancel);
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', cancel);
      window.removeEventListener('blur', blur);
    };
  }, [release]);

  useEffect(() => {
    if (state.phase !== 'settling') return;
    const timer = window.setTimeout(() => send({ type: 'REST', revision: state.revision }), 220);
    return () => clearTimeout(timer);
  }, [state.phase, state.revision]);

  const select = useCallback((index: number) => send({ type: 'SELECT', index }), []);
  const settled = useCallback(() => send({ type: 'MORPH_END', revision: state.revision }), [state.revision]);
  const bindings: HTMLAttributes<HTMLElement> = {
    onPointerEnter: event => { if (enabled && event.pointerType !== 'touch') send({ type: 'ENTER' }); },
    onPointerMove: event => {
      if (!enabled || event.pointerType === 'touch' || !matchMedia('(hover: hover) and (pointer: fine)').matches) return;
      const rect = event.currentTarget.getBoundingClientRect();
      pointer.current.x = Math.max(-1, Math.min(1, ((event.clientX - rect.left) / rect.width - .5) * 2));
      pointer.current.y = Math.max(-1, Math.min(1, ((event.clientY - rect.top) / rect.height - .5) * 2));
      art.current?.setPointer(pointer.current.x, pointer.current.y, pointer.current.pressed);
    },
    onPointerDown: event => {
      if (!enabled || event.button !== 0 || !event.isPrimary) return;
      pointer.current.id = event.pointerId;
      pointer.current.pressed = true;
      send({ type: 'PRESS' });
      art.current?.setPointer(pointer.current.x, pointer.current.y, true);
    },
    onPointerLeave: () => {
      pointer.current.pressed = false;
      pointer.current.id = -1;
      art.current?.resetPointer();
      send({ type: 'LEAVE' });
    },
    onLostPointerCapture: () => { if (pointer.current.pressed) release(true); },
    onFocusCapture: () => send({ type: 'FOCUS' }),
    onBlurCapture: event => {
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) send({ type: 'BLUR' });
    },
  };
  return { state, select, settled, bindings };
}
