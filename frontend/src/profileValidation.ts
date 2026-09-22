import type { TestProfileConfiguration } from "./types";


export function validateProfileConfiguration(
  configuration: TestProfileConfiguration,
): string[] {
  const errors: string[] = [];
  const wifiInterval = configuration.sampling.wifi_interval_seconds;

  if (!Number.isFinite(wifiInterval) || wifiInterval < 1 || wifiInterval > 3600) {
    errors.push("Wi-Fi sampling interval must be between 1 and 3600 seconds.");
  }

  for (const [name, test] of Object.entries(configuration.tests)) {
    if (!test.enabled) continue;
    if (!Number.isFinite(test.interval_seconds)
      || test.interval_seconds < wifiInterval
      || Math.abs(test.interval_seconds / wifiInterval
        - Math.round(test.interval_seconds / wifiInterval)) > 1e-9) {
      errors.push(`${name} interval must be an integer multiple of the Wi-Fi interval.`);
    }
    if (test.timeout_seconds !== null
      && (!Number.isFinite(test.timeout_seconds)
        || test.timeout_seconds <= 0
        || test.timeout_seconds > 300)) {
      errors.push(`${name} timeout must be greater than 0 and at most 300 seconds.`);
    }
  }

  const gateway = configuration.tests.gateway;
  if (!gateway.automatic_gateway && !gateway.target?.trim()) {
    errors.push("Gateway target is required when automatic gateway detection is disabled.");
  }

  try {
    const url = new URL(configuration.tests.https.url);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      errors.push("HTTPS test URL must use HTTP or HTTPS.");
    }
  } catch {
    errors.push("HTTPS test URL must be an absolute URL.");
  }

  const wifi = configuration.thresholds.wifi;
  if (wifi.rssi_critical_dbm >= wifi.rssi_warning_dbm) {
    errors.push("Critical RSSI must be lower than warning RSSI.");
  }
  if (wifi.retry_critical_percent <= wifi.retry_warning_percent) {
    errors.push("Critical retry threshold must exceed the warning threshold.");
  }

  for (const [name, thresholds] of [
    ["Gateway", configuration.thresholds.gateway],
    ["Internet", configuration.thresholds.internet],
  ] as const) {
    if (thresholds.packet_loss_critical_percent
      <= thresholds.packet_loss_warning_percent) {
      errors.push(`${name} critical packet loss must exceed the warning threshold.`);
    }
  }

  const cycle = configuration.thresholds.connection_cycle ?? {
    window_size: 20,
    minimum_samples: 5,
    p95_warning_ms: 8000,
    p95_critical_ms: 15000,
  };
  if (!Number.isInteger(cycle.window_size) || cycle.window_size < 3 || cycle.window_size > 200) {
    errors.push("Connection-cycle window must be an integer between 3 and 200.");
  }
  if (!Number.isInteger(cycle.minimum_samples)
    || cycle.minimum_samples < 3
    || cycle.minimum_samples > cycle.window_size) {
    errors.push("Connection-cycle minimum samples must be between 3 and the window size.");
  }
  if (!Number.isFinite(cycle.p95_warning_ms)
    || cycle.p95_warning_ms <= 0
    || cycle.p95_warning_ms > 300000) {
    errors.push("Connection-cycle P95 warning must be between 0 and 300000 ms.");
  }
  if (!Number.isFinite(cycle.p95_critical_ms)
    || cycle.p95_critical_ms <= cycle.p95_warning_ms
    || cycle.p95_critical_ms > 300000) {
    errors.push("Connection-cycle P95 critical must exceed warning and be at most 300000 ms.");
  }

  return errors;
}
