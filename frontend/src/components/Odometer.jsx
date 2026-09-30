// Rolling mechanical counter. Each digit is a vertical strip of 0-9 that slides
// to the right number; the last digit gets the red "tenths" styling.

const DIGITS = 6;

export default function Odometer({ value }) {
  const text = String(Math.max(0, Math.floor(value || 0)))
    .padStart(DIGITS, "0")
    .slice(-DIGITS);

  return (
    <div className="dash-odometer" role="img" aria-label={`${Number(text)} calls`}>
      {text.split("").map((ch, i) => (
        <div key={i} className={`dash-digit ${i === DIGITS - 1 ? "dash-digit-tenths" : ""}`}>
          <div className="dash-strip" style={{ transform: `translateY(calc(var(--digit-h) * -${ch}))` }}>
            {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
              <span key={n}>{n}</span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
