import { useEffect, type RefObject } from 'react';

const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));
const variables = ['--wm-hero-shift', '--wm-scroll-progress', '--wm-art-shift', '--wm-photo-shift', '--wm-pointer-x', '--wm-pointer-y'];

/** One scheduled frame per input event; no idle animation loop or React scroll renders. */
export default function useScrollMotion(ref: RefObject<HTMLDivElement>, enabled: boolean) {
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const reset = () => variables.forEach(name => root.style.setProperty(name, '0'));
    reset();
    if (!enabled) return;

    const hero = root.querySelector<HTMLElement>('.wm-hero');
    const workflow = root.querySelector<HTMLElement>('.wm-workflow');
    const photo = root.querySelector<HTMLElement>('.wm-perspective-image');
    const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
    let frame = 0;
    let pointerX = 0;
    let pointerY = 0;
    const update = () => {
      frame = 0;
      if (document.hidden) return;
      const viewport = innerHeight;
      const bounds = root.getBoundingClientRect();
      const heroBounds = hero?.getBoundingClientRect();
      const workflowBounds = workflow?.getBoundingClientRect();
      const photoBounds = photo?.getBoundingClientRect();
      const centered = (rect: DOMRect) => clamp((viewport / 2 - rect.top - rect.height / 2) / viewport, -1, 1);
      const values = [
        heroBounds ? clamp(-heroBounds.top / heroBounds.height) * 48 : 0,
        clamp(-bounds.top / Math.max(1, bounds.height - viewport)),
        workflowBounds ? centered(workflowBounds) * 30 : 0,
        photoBounds ? centered(photoBounds) * 12 : 0,
        pointerX, pointerY,
      ];
      variables.forEach((name, index) => root.style.setProperty(name, values[index].toFixed(4)));
    };
    const schedule = () => { if (!frame && !document.hidden) frame = requestAnimationFrame(update); };
    const move = (event: PointerEvent) => {
      if (!finePointer.matches || event.pointerType === 'touch' || !workflow) return;
      const rect = workflow.getBoundingClientRect();
      pointerX = (clamp((event.clientX - rect.left) / rect.width) - .5) * 12;
      pointerY = (clamp((event.clientY - rect.top) / rect.height) - .5) * 10;
      schedule();
    };
    const leave = () => { pointerX = 0; pointerY = 0; schedule(); };
    const visibility = () => {
      if (document.hidden) { cancelAnimationFrame(frame); frame = 0; }
      else schedule();
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(root);
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule, { passive: true });
    document.addEventListener('visibilitychange', visibility);
    workflow?.addEventListener('pointermove', move, { passive: true });
    workflow?.addEventListener('pointerleave', leave);
    finePointer.addEventListener('change', leave);
    schedule();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      document.removeEventListener('visibilitychange', visibility);
      workflow?.removeEventListener('pointermove', move);
      workflow?.removeEventListener('pointerleave', leave);
      finePointer.removeEventListener('change', leave);
      reset();
    };
  }, [ref, enabled]);
}
