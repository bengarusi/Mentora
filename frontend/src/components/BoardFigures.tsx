import type {
  BoardCoordinatePlaneBlock,
  BoardFractionBarsBlock,
  BoardGeometryFigureBlock,
  BoardNumberLineBlock,
} from "../types";

/**
 * SVG renderers for the picture blocks.
 *
 * Every one of these derives its geometry from the parameters the model supplied
 * — slope and intercept, numerator and denominator, dimensions — rather than
 * from coordinates the model drew itself. That is what makes a drawing unable to
 * contradict the numbers beside it. It does NOT make those numbers right for the
 * question; see app/board/validation.py for how far the checks reach.
 */

const INK = "var(--color-text)";
const ACCENT = "var(--color-primary)";
const MUTED = "var(--color-muted)";
const GRID = "var(--color-border)";

function round(value: number, places = 2): number {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
}

/** Ticks from min to max, guarded against a float step never landing on max. */
function ticksBetween(min: number, max: number, step: number): number[] {
  const out: number[] = [];
  for (let value = min; value <= max + step / 1000; value += step) {
    out.push(round(value, 4));
    if (out.length > 200) break;
  }
  return out;
}

// ---- fraction bars ---------------------------------------------------------

export function BoardFractionBars({ block }: { block: BoardFractionBarsBlock }) {
  const width = 320;
  const barHeight = 34;
  const gap = 16;
  const height = block.bars.length * (barHeight + gap);

  return (
    <svg
      className="board-figure"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      preserveAspectRatio="xMidYMid meet"
    >
      <title>{block.caption}</title>
      {block.bars.map((bar, index) => {
        const y = index * (barHeight + gap);
        const cellWidth = width / bar.denominator;
        // Shading comes straight from numerator/denominator, so a bar can never
        // be filled to a different amount than it claims.
        const shaded = Math.min(bar.numerator, bar.denominator);
        return (
          <g key={index}>
            {Array.from({ length: bar.denominator }, (_, cell) => (
              <rect
                key={cell}
                x={round(cell * cellWidth)}
                y={y}
                width={round(cellWidth)}
                height={barHeight}
                fill={cell < shaded ? ACCENT : "transparent"}
                fillOpacity={cell < shaded ? 0.75 : 1}
                stroke={GRID}
                strokeWidth={1}
              />
            ))}
            {bar.label && (
              <text x={4} y={y + barHeight + 13} fontSize={13} fill={MUTED}>
                {bar.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ---- number line -----------------------------------------------------------

export function BoardNumberLine({ block }: { block: BoardNumberLineBlock }) {
  const width = 480;
  const height = 96;
  const padding = 28;
  const axisY = 46;
  const span = block.max - block.min || 1;
  const toX = (value: number) =>
    padding + ((value - block.min) / span) * (width - padding * 2);

  const interval = block.interval;
  const intervalStart = interval?.start ?? block.min;
  const intervalEnd = interval?.end ?? block.max;

  return (
    <svg
      className="board-figure"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      preserveAspectRatio="xMidYMid meet"
    >
      <title>{block.caption}</title>

      {interval && (
        <line
          x1={round(toX(intervalStart))}
          y1={axisY}
          x2={round(toX(intervalEnd))}
          y2={axisY}
          stroke={ACCENT}
          strokeWidth={7}
          strokeOpacity={0.3}
          strokeLinecap="round"
        />
      )}

      <line x1={padding} y1={axisY} x2={width - padding} y2={axisY} stroke={INK} strokeWidth={2} />

      {ticksBetween(block.min, block.max, block.tick).map((value) => (
        <g key={value}>
          <line
            x1={round(toX(value))}
            y1={axisY - 6}
            x2={round(toX(value))}
            y2={axisY + 6}
            stroke={GRID}
            strokeWidth={1.5}
          />
          <text
            x={round(toX(value))}
            y={axisY + 22}
            fontSize={12}
            fill={MUTED}
            textAnchor="middle"
          >
            {value}
          </text>
        </g>
      ))}

      {block.points.map((point, index) => (
        <g key={index}>
          <circle
            cx={round(toX(point.value))}
            cy={axisY}
            r={7}
            fill={point.style === "open" ? "var(--color-surface)" : ACCENT}
            stroke={ACCENT}
            strokeWidth={2.5}
          />
          {point.label && (
            <text
              x={round(toX(point.value))}
              y={axisY - 14}
              fontSize={13}
              fill={ACCENT}
              textAnchor="middle"
            >
              {point.label}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

// ---- coordinate plane ------------------------------------------------------

export function BoardCoordinatePlane({ block }: { block: BoardCoordinatePlaneBlock }) {
  const width = 420;
  const height = 340;
  const pad = 32;
  const spanX = block.x_max - block.x_min || 1;
  const spanY = block.y_max - block.y_min || 1;
  const toX = (x: number) => pad + ((x - block.x_min) / spanX) * (width - pad * 2);
  const toY = (y: number) => height - pad - ((y - block.y_min) / spanY) * (height - pad * 2);

  /** Clip y = mx + b to the visible window. The line is derived here, never sent
   * by the model, so what is drawn always matches the equation shown. */
  const segment = (slope: number, intercept: number) => {
    const at = (x: number) => slope * x + intercept;
    let [x1, x2] = [block.x_min, block.x_max];
    let [y1, y2] = [at(x1), at(x2)];
    if (Math.abs(slope) > 1e-9) {
      if (y1 < block.y_min) { y1 = block.y_min; x1 = (block.y_min - intercept) / slope; }
      if (y1 > block.y_max) { y1 = block.y_max; x1 = (block.y_max - intercept) / slope; }
      if (y2 < block.y_min) { y2 = block.y_min; x2 = (block.y_min - intercept) / slope; }
      if (y2 > block.y_max) { y2 = block.y_max; x2 = (block.y_max - intercept) / slope; }
    }
    return { x1, y1, x2, y2 };
  };

  const first = block.lines[0];
  const triangleAt = block.slope_triangle;

  return (
    <svg
      className="board-figure"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      preserveAspectRatio="xMidYMid meet"
    >
      <title>{block.caption}</title>

      {ticksBetween(Math.ceil(block.x_min), block.x_max, 1).map((x) => (
        <line key={`vx${x}`} x1={round(toX(x))} y1={pad} x2={round(toX(x))} y2={height - pad}
          stroke={GRID} strokeWidth={0.75} />
      ))}
      {ticksBetween(Math.ceil(block.y_min), block.y_max, 1).map((y) => (
        <line key={`hy${y}`} x1={pad} y1={round(toY(y))} x2={width - pad} y2={round(toY(y))}
          stroke={GRID} strokeWidth={0.75} />
      ))}

      {block.y_min <= 0 && block.y_max >= 0 && (
        <line x1={pad} y1={round(toY(0))} x2={width - pad} y2={round(toY(0))} stroke={INK} strokeWidth={2} />
      )}
      {block.x_min <= 0 && block.x_max >= 0 && (
        <line x1={round(toX(0))} y1={pad} x2={round(toX(0))} y2={height - pad} stroke={INK} strokeWidth={2} />
      )}

      {first && triangleAt !== null && (() => {
        const y0 = first.slope * triangleAt + first.intercept;
        const y1 = first.slope * (triangleAt + 1) + first.intercept;
        return (
          <g>
            <line x1={round(toX(triangleAt))} y1={round(toY(y0))}
              x2={round(toX(triangleAt + 1))} y2={round(toY(y0))}
              stroke={MUTED} strokeWidth={2} strokeDasharray="4 3" />
            <line x1={round(toX(triangleAt + 1))} y1={round(toY(y0))}
              x2={round(toX(triangleAt + 1))} y2={round(toY(y1))}
              stroke={MUTED} strokeWidth={2} strokeDasharray="4 3" />
            <text x={round(toX(triangleAt + 1)) + 6} y={round(toY((y0 + y1) / 2))}
              fontSize={12} fill={MUTED}>
              {round(first.slope)}
            </text>
          </g>
        );
      })()}

      {block.lines.map((line, index) => {
        const s = segment(line.slope, line.intercept);
        return (
          <g key={index}>
            <line x1={round(toX(s.x1))} y1={round(toY(s.y1))}
              x2={round(toX(s.x2))} y2={round(toY(s.y2))}
              stroke={ACCENT} strokeWidth={2.5} strokeLinecap="round" />
            {line.label && (
              <text x={round(toX(s.x2)) - 6} y={round(toY(s.y2)) - 8}
                fontSize={12} fill={ACCENT} textAnchor="end">
                {line.label}
              </text>
            )}
          </g>
        );
      })}

      {block.points.map((point, index) => (
        <g key={index}>
          <circle cx={round(toX(point.x))} cy={round(toY(point.y))} r={5} fill={ACCENT} />
          {point.label && (
            <text x={round(toX(point.x)) + 8} y={round(toY(point.y)) - 8} fontSize={12} fill={MUTED}>
              {point.label}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

// ---- geometry figure -------------------------------------------------------

export function BoardGeometryFigure({ block }: { block: BoardGeometryFigureBlock }) {
  const width = 360;
  const height = 260;
  const pad = 40;
  const labelFor = (target: string) =>
    block.labels.find((label) => label.target === target)?.text;

  const dims = block.dimensions;
  // Scale the largest declared dimension to fill the frame, so proportions
  // between sides stay faithful to the numbers.
  const largest = Math.max(...Object.values(dims), 1);
  const scale = Math.min(width - pad * 2, height - pad * 2) / largest;

  const shape = () => {
    if (block.shape === "circle") {
      const radius = (dims.radius ?? (dims.diameter ?? 2) / 2) * scale;
      const cx = width / 2;
      const cy = height / 2;
      return (
        <g>
          <circle cx={cx} cy={cy} r={radius} fill={ACCENT} fillOpacity={0.12}
            stroke={ACCENT} strokeWidth={2.5} />
          <line x1={cx} y1={cy} x2={cx + radius} y2={cy} stroke={INK} strokeWidth={2} />
          <circle cx={cx} cy={cy} r={3} fill={INK} />
          {(labelFor("radius") || labelFor("diameter")) && (
            <text x={cx + radius / 2} y={cy - 8} fontSize={13} fill={MUTED} textAnchor="middle">
              {labelFor("radius") ?? labelFor("diameter")}
            </text>
          )}
        </g>
      );
    }

    if (block.shape === "rectangle") {
      const w = (dims.width ?? 1) * scale;
      const h = (dims.height ?? 1) * scale;
      const x = (width - w) / 2;
      const y = (height - h) / 2;
      return (
        <g>
          <rect x={x} y={y} width={w} height={h} fill={ACCENT} fillOpacity={0.12}
            stroke={ACCENT} strokeWidth={2.5} />
          {labelFor("width") && (
            <text x={x + w / 2} y={y + h + 20} fontSize={13} fill={MUTED} textAnchor="middle">
              {labelFor("width")}
            </text>
          )}
          {labelFor("height") && (
            <text x={x - 8} y={y + h / 2} fontSize={13} fill={MUTED} textAnchor="end">
              {labelFor("height")}
            </text>
          )}
        </g>
      );
    }

    const base = (dims.base ?? dims.side_a ?? 1) * scale;
    const h = (dims.height ?? dims.side_b ?? 1) * scale;
    const x = (width - base) / 2;
    const y = (height + h) / 2;
    const apexX = x; // right-angled at the left, so the height is a visible leg
    const apexY = y - h;
    return (
      <g>
        <polygon points={`${x},${y} ${x + base},${y} ${apexX},${apexY}`}
          fill={ACCENT} fillOpacity={0.12} stroke={ACCENT} strokeWidth={2.5} />
        {block.right_angle_at && (
          <path d={`M ${x} ${y - 14} L ${x + 14} ${y - 14} L ${x + 14} ${y}`}
            fill="none" stroke={MUTED} strokeWidth={1.5} />
        )}
        {labelFor("base") && (
          <text x={x + base / 2} y={y + 20} fontSize={13} fill={MUTED} textAnchor="middle">
            {labelFor("base")}
          </text>
        )}
        {labelFor("height") && (
          <text x={x - 8} y={y - h / 2} fontSize={13} fill={MUTED} textAnchor="end">
            {labelFor("height")}
          </text>
        )}
      </g>
    );
  };

  return (
    <svg
      className="board-figure"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      preserveAspectRatio="xMidYMid meet"
    >
      <title>{block.caption}</title>
      {shape()}
    </svg>
  );
}
