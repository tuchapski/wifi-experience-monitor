import type { RfScanBand } from "./recordingRfScanBands";

export default function RecordingRfScanBands({ bands, left, width, top, height }: {
  bands: RfScanBand[];
  left: number;
  width: number;
  top: number;
  height: number;
}) {
  return <g className="recording-rf-scan-bands">
    {bands.map(({ scan, startFraction, endFraction }) => {
      const renderedWidth = Math.min(width, Math.max(0.8, (endFraction - startFraction) * width));
      const x = Math.min(left + startFraction * width, left + width - renderedWidth);
      const label = `Estimated RF scan · ${scan.interface} · ${scan.started_at} → ${scan.ended_at} · ${scan.duration_ms.toFixed(1)} ms`;
      return <rect
        key={scan.scan_id}
        data-scan-id={scan.scan_id}
        x={x}
        y={top}
        width={renderedWidth}
        height={height}
        className="recording-rf-scan-band"
        aria-label={label}
      ><title>{label}</title></rect>;
    })}
  </g>;
}
