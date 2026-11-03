export const CONTOUR_COUNT = 18;
const SAMPLES = 33;
export type ContourGeometry = number[][];

// Identical point order and command topology across all three configurations.
function makeShape(chapter: number): ContourGeometry {
  return Array.from({ length: CONTOUR_COUNT }, (_, ring) => {
    const points: number[] = [];
    for (let sample = 0; sample < SAMPLES; sample++) {
      const t = sample / (SAMPLES - 1);
      let x: number;
      let y: number;
      if (chapter === 1) {
        // Review: loose contours gather into ordered, gently bowed ribbons.
        x = 405 + ring * 16 + 90 * Math.cos((t - .5) * Math.PI * 1.7)
          + 15 * Math.sin(t * Math.PI * 2 + ring * .12);
        y = 200 + (t - .5) * 630 + ring * 2;
      } else {
        const angle = (chapter === 2 ? -2.8 : -2.35) + t * (chapter === 2 ? 5.6 : 4.7);
        const radius = (chapter === 2 ? 76 : 92) + ring * (chapter === 2 ? 16 : 18);
        const warp = 1 + .09 * Math.sin(angle * 3 + (chapter === 2 ? 1.9 : .6)) + .05 * Math.cos(angle * 2);
        const vertical = Math.sin(angle) * radius * (chapter === 2 ? .87 : .72) * warp;
        x = (chapter === 2 ? 505 : 545) + Math.cos(angle) * radius * warp - vertical * (chapter === 2 ? -.13 : .22);
        y = (chapter === 2 ? 215 : 200) + vertical;
      }
      points.push(x, y);
    }
    return points;
  });
}

export const CONTOUR_SHAPES = [makeShape(0), makeShape(1), makeShape(2)];
export const copyGeometry = (shape: ContourGeometry) => shape.map(points => [...points]);

export function contourPath(points: number[], pointerX = 0, pointerY = 0, pressure = 0): string {
  const deformed: number[] = [];
  for (let i = 0; i < points.length; i += 2) {
    const x = points[i];
    const y = points[i + 1];
    const dx = x - (485 + pointerX * 105);
    const dy = y - (200 + pointerY * 140);
    const influence = Math.exp(-(dx * dx + dy * dy) / 85000);
    deformed.push(
      x + pointerX * 34 * influence - dx * pressure * .11 * influence,
      y + pointerY * 28 * influence - dy * pressure * .11 * influence,
    );
  }
  const n = (value: number) => value.toFixed(2);
  let path = `M ${n(deformed[0])} ${n(deformed[1])}`;
  for (let i = 0; i < deformed.length - 2; i += 2) {
    const previous = Math.max(0, i - 2);
    const next = i + 2;
    const after = Math.min(deformed.length - 2, i + 4);
    path += ` C ${n(deformed[i] + (deformed[next] - deformed[previous]) / 6)} ${n(deformed[i + 1] + (deformed[next + 1] - deformed[previous + 1]) / 6)}, ${n(deformed[next] - (deformed[after] - deformed[i]) / 6)} ${n(deformed[next + 1] - (deformed[after + 1] - deformed[i + 1]) / 6)}, ${n(deformed[next])} ${n(deformed[next + 1])}`;
  }
  return path;
}
