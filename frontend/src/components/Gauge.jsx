// Round dial with a sweeping needle, drawn as declarative SVG. The needle is a
// CSS-transitioned rotation, so React just updates `value` and the browser
// animates it. `value` may be null (no data yet): needle rests at the minimum.

const CX = 150;
const CY = 150;
const R = 118;
const START = -125;
const END = 125;

function polar(r, deg) {
  const rad = ((deg - 90) * Math.PI) / 180;
  return [CX + r * Math.cos(rad), CY + r * Math.sin(rad)];
}

function arc(r, a0, a1) {
  const [x0, y0] = polar(r, a0);
  const [x1, y1] = polar(r, a1);
  return `M${x0} ${y0} A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1} ${y1}`;
}

export default function Gauge({ id, min, max, major, minor, redFrom, value, labelFmt }) {
  const angleFor = (v) => START + ((Math.min(Math.max(v, min), max) - min) / (max - min)) * (END - START);
  const angle = angleFor(value == null ? min : value);

  const steps = Math.round((max - min) / minor);
  const perMajor = Math.round(major / minor);
  const ticks = [];
  for (let i = 0; i <= steps; i++) {
    const v = min + i * minor;
    const isMajor = i % perMajor === 0;
    const a = angleFor(v);
    const isRed = redFrom != null && v >= redFrom;
    const [x0, y0] = polar(R - 2, a);
    const [x1, y1] = polar(R - (isMajor ? 18 : 9), a);
    ticks.push(
      <line
        key={`t${i}`}
        x1={x0}
        y1={y0}
        x2={x1}
        y2={y1}
        stroke={isRed ? "var(--dash-red)" : "var(--dash-tick)"}
        strokeWidth={isMajor ? 3 : 1.4}
      />
    );
    if (isMajor) {
      const [tx, ty] = polar(R - 34, a);
      ticks.push(
        <text
          key={`l${i}`}
          x={tx}
          y={ty + 5}
          textAnchor="middle"
          fill={isRed ? "var(--dash-red)" : "var(--dash-text)"}
          fontFamily="JetBrains Mono, monospace"
          fontSize="15"
          fontWeight="700"
        >
          {labelFmt ? labelFmt(v) : v}
        </text>
      );
    }
  }

  return (
    <svg viewBox="0 0 300 260" className="dash-gauge-svg" role="img" aria-hidden="true">
      <defs>
        <radialGradient id={`${id}-face`}>
          <stop offset="0%" stopColor="#1a1f2b" />
          <stop offset="100%" stopColor="#07080b" />
        </radialGradient>
      </defs>
      <circle cx={CX} cy={CY} r={R + 16} fill={`url(#${id}-face)`} stroke="#2a3040" strokeWidth="3" />
      <path d={arc(R, START, END)} stroke="#262c3a" strokeWidth="6" fill="none" />
      {redFrom != null && (
        <path d={arc(R, angleFor(redFrom), END)} stroke="var(--dash-red)" strokeWidth="6" fill="none" opacity="0.9" />
      )}
      <path
        d={arc(R - 12, START, Math.max(angle, START + 0.01))}
        stroke="var(--dash-glow)"
        strokeWidth="3"
        fill="none"
        opacity="0.55"
        strokeLinecap="round"
        style={{ transition: "d 1.1s ease" }}
      />
      {ticks}
      <g
        style={{
          transformOrigin: `${CX}px ${CY}px`,
          transform: `rotate(${angle}deg)`,
          transition: "transform 1.1s cubic-bezier(.3,1.4,.5,1)",
        }}
      >
        <polygon
          points={`${CX - 4},${CY + 18} ${CX + 4},${CY + 18} ${CX + 1.2},${CY - R + 10} ${CX - 1.2},${CY - R + 10}`}
          fill="var(--dash-needle)"
          style={{ filter: "drop-shadow(0 0 6px rgba(255,77,46,.8))" }}
        />
      </g>
      <circle cx={CX} cy={CY} r="14" fill="#222835" stroke="#3a4254" strokeWidth="2" />
      <circle cx={CX} cy={CY} r="5" fill="var(--dash-needle)" />
    </svg>
  );
}
