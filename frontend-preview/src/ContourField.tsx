import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react';
import { CONTOUR_SHAPES, contourPath, copyGeometry } from './contourGeometry';
import type { InteractionPhase } from './workflowMachine';
import './contour-field.css';

type Props = { enabled: boolean; chapter: number; phase: InteractionPhase; onSettled?: () => void };
export type ContourFieldHandle = {
  setPointer: (x: number, y: number, pressed?: boolean) => void;
  resetPointer: () => void;
};
type Controller = ContourFieldHandle & { sync: (props: Props) => void; dispose: () => void };
const chapterIndex = (value: number) => Math.max(0, Math.min(2, Math.round(value)));
const clamp = (value: number) => Number.isFinite(value) ? Math.max(-1, Math.min(1, value)) : 0;

const ContourField = forwardRef<ContourFieldHandle, Props>(function ContourField(props, ref) {
  const svgRef = useRef<SVGSVGElement>(null);
  const controller = useRef<Controller | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const [initial] = useState(() => CONTOUR_SHAPES[chapterIndex(props.chapter)].map(points => contourPath(points)));

  useImperativeHandle(ref, () => ({
    setPointer: (x, y, pressed) => controller.current?.setPointer(x, y, pressed),
    resetPointer: () => controller.current?.resetPointer(),
  }), []);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const paths = Array.from(svg.querySelectorAll('path'));
    let targetChapter = chapterIndex(latest.current.chapter);
    let current = copyGeometry(CONTOUR_SHAPES[targetChapter]);
    let enabled = latest.current.enabled;
    let phase = latest.current.phase;
    let visible = false;
    let disposed = false;
    let frame = 0;
    let previousTime = 0;
    let paintedFrames = 0;
    let chapterPending = false;
    let chapterComplete: (() => void) | undefined;
    const pointer = { x: 0, y: 0, pressure: 0 };
    const targetPointer = { x: 0, y: 0, pressure: 0 };
    const canRun = () => enabled && phase !== 'suspended' && visible && !document.hidden && !disposed;
    const status = (value: string) => {
      if (svg.dataset.morphState !== value) svg.dataset.morphState = value;
    };
    const stop = () => { cancelAnimationFrame(frame); frame = 0; previousTime = 0; };
    const paint = () => {
      paths.forEach((path, index) => path.setAttribute('d', contourPath(current[index], pointer.x, pointer.y, pointer.pressure)));
      svg.dataset.morphFrame = String(++paintedFrames);
    };
    const notifyChapter = () => {
      if (!chapterPending) return;
      chapterPending = false;
      const complete = chapterComplete;
      chapterComplete = undefined;
      complete?.();
    };
    const staticShape = () => {
      current = copyGeometry(CONTOUR_SHAPES[targetChapter]);
      pointer.x = pointer.y = pointer.pressure = 0;
      targetPointer.x = targetPointer.y = targetPointer.pressure = 0;
      paint();
      notifyChapter();
    };
    const tick = (time: number) => {
      frame = 0;
      if (!canRun()) return;
      const dt = previousTime ? Math.min(34, time - previousTime) : 16;
      previousTime = time;
      const shapeMix = 1 - Math.exp(-dt / 92);
      const pointerMix = 1 - Math.exp(-dt / 70);
      const destination = CONTOUR_SHAPES[targetChapter];
      let shapeError = 0;
      current.forEach((points, ring) => points.forEach((value, index) => {
        const delta = destination[ring][index] - value;
        points[index] = Math.abs(delta) < .035 ? destination[ring][index] : value + delta * shapeMix;
        shapeError = Math.max(shapeError, Math.abs(destination[ring][index] - points[index]));
      }));
      let pointerError = 0;
      (['x', 'y', 'pressure'] as const).forEach(key => {
        const delta = targetPointer[key] - pointer[key];
        pointer[key] = Math.abs(delta) < .001 ? targetPointer[key] : pointer[key] + delta * pointerMix;
        pointerError = Math.max(pointerError, Math.abs(targetPointer[key] - pointer[key]));
      });
      paint();
      if (shapeError === 0) notifyChapter();
      if (shapeError > 0 || pointerError > 0) {
        status('running');
        frame = requestAnimationFrame(tick);
      } else {
        previousTime = 0;
        status('settled');
      }
    };
    const wake = () => {
      if (!canRun() || frame) return;
      status('running');
      frame = requestAnimationFrame(tick);
    };
    const visibility = () => {
      if (!canRun()) {
        stop();
        if (chapterPending) staticShape();
        status(enabled ? 'suspended' : 'paused');
      }
      else wake();
    };
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; visibility(); }, { threshold: 0 });
    observer.observe(svg);
    document.addEventListener('visibilitychange', visibility);

    const api: Controller = {
      setPointer(x, y, pressed) {
        if (!canRun()) return;
        targetPointer.x = clamp(x);
        targetPointer.y = clamp(y);
        if (pressed !== undefined) targetPointer.pressure = pressed ? 1 : 0;
        wake();
      },
      resetPointer() {
        targetPointer.x = targetPointer.y = targetPointer.pressure = 0;
        wake();
      },
      sync(next) {
        const chapter = chapterIndex(next.chapter);
        const changed = chapter !== targetChapter;
        const wasEnabled = enabled;
        const oldPhase = phase;
        enabled = next.enabled;
        phase = next.phase;
        if (changed) {
          targetChapter = chapter;
          chapterPending = true;
          chapterComplete = next.onSettled;
          svg.dataset.morphChapter = String(chapter);
        }
        if (!enabled) {
          stop();
          if (wasEnabled || changed) staticShape();
          status('paused');
          return;
        }
        if (!canRun()) {
          stop();
          // Hidden illustrations complete immediately; a visible tab panel must never
          // remain in its morphing state waiting for offscreen artwork to render.
          if (changed) staticShape();
          status('suspended');
          return;
        }
        if (phase === 'pressed') targetPointer.pressure = 1;
        else if (oldPhase === 'pressed') targetPointer.pressure = 0;
        if (changed || wasEnabled !== enabled || oldPhase === 'suspended'
          || (oldPhase === 'pressed') !== (phase === 'pressed')) wake();
      },
      dispose() {
        disposed = true;
        stop();
        observer.disconnect();
        document.removeEventListener('visibilitychange', visibility);
      },
    };
    controller.current = api;
    svg.dataset.morphChapter = String(targetChapter);
    svg.dataset.morphFrame = '0';
    status(enabled ? 'suspended' : 'paused');
    return () => { api.dispose(); controller.current = null; };
  }, []);

  useLayoutEffect(() => { controller.current?.sync(props); }, [props.enabled, props.chapter, props.phase]);

  return (
    <svg ref={svgRef} className={`wm-contour-field${props.enabled ? ' is-responsive' : ''}`}
      data-interaction-phase={props.phase} viewBox="0 0 640 400" preserveAspectRatio="xMaxYMid slice"
      aria-hidden="true" focusable="false" fill="none">
      <g className="wm-contour-lines">
        {initial.map((path, index) => (
          <path key={index} d={path} opacity={.58 + (index % 5) * .1} vectorEffect="non-scaling-stroke" />
        ))}
      </g>
    </svg>
  );
});

export default ContourField;
