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

  const applicationTargets = configuration.application_targets ?? [];
  if (applicationTargets.length > 20) {
    errors.push("At most 20 application targets can be configured.");
  }
  const targetNames = new Set<string>();
  for (const target of applicationTargets) {
    const name = target.name.trim();
    const normalizedName = name.toLowerCase();
    if (!name) errors.push("Application target name is required.");
    if (targetNames.has(normalizedName)) {
      errors.push(`Application target name '${name}' must be unique.`);
    }
    targetNames.add(normalizedName);
    if (!target.target.trim()) errors.push(`${name || "Application target"} target is required.`);
    if (target.enabled && (!Number.isFinite(target.interval_seconds)
      || target.interval_seconds < wifiInterval
      || Math.abs(target.interval_seconds / wifiInterval
        - Math.round(target.interval_seconds / wifiInterval)) > 1e-9)) {
      errors.push(`${name || "Application target"} interval must be an integer multiple of the Wi-Fi interval.`);
    }
    if (target.timeout_seconds !== null
      && (!Number.isFinite(target.timeout_seconds)
        || target.timeout_seconds <= 0
        || target.timeout_seconds > 300)) {
      errors.push(`${name || "Application target"} timeout must be greater than 0 and at most 300 seconds.`);
    }
    if (target.kind === "http") {
      try {
        const url = new URL(target.target);
        if (url.protocol !== "http:" && url.protocol !== "https:") {
          errors.push(`${name || "Application target"} URL must use HTTP or HTTPS.`);
        }
      } catch {
        errors.push(`${name || "Application target"} must use an absolute HTTP/HTTPS URL.`);
      }
      if (target.port !== null) errors.push(`${name || "Application target"} HTTP port must be part of the URL.`);
    } else if (target.kind === "tcp") {
      if (target.port === null || !Number.isInteger(target.port) || target.port < 1 || target.port > 65535) {
        errors.push(`${name || "Application target"} TCP port must be between 1 and 65535.`);
      }
      if (target.target.includes("://")) {
        errors.push(`${name || "Application target"} TCP target must be a host name or IP address.`);
      }
    } else if (target.kind === "dns" && target.port !== null) {
      errors.push(`${name || "Application target"} DNS target does not use a port.`);
    }
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
    stages: {
      association: { p95_warning_ms: 1500, p95_critical_ms: 3000 },
      authentication: { p95_warning_ms: 3000, p95_critical_ms: 6000 },
      ipv4: { p95_warning_ms: 5000, p95_critical_ms: 10000 },
      gateway: { p95_warning_ms: 6000, p95_critical_ms: 12000 },
      dns: { p95_warning_ms: 7000, p95_critical_ms: 14000 },
    },
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

  const cycleStages = cycle.stages ?? {
    association: { p95_warning_ms: 1500, p95_critical_ms: 3000 },
    authentication: { p95_warning_ms: 3000, p95_critical_ms: 6000 },
    ipv4: { p95_warning_ms: 5000, p95_critical_ms: 10000 },
    gateway: { p95_warning_ms: 6000, p95_critical_ms: 12000 },
    dns: { p95_warning_ms: 7000, p95_critical_ms: 14000 },
  };
  for (const [name, target] of Object.entries(cycleStages)) {
    if (!Number.isFinite(target.p95_warning_ms)
      || target.p95_warning_ms <= 0
      || target.p95_warning_ms > 300000) {
      errors.push(`${name} connection-cycle stage P95 warning must be between 0 and 300000 ms.`);
    }
    if (!Number.isFinite(target.p95_critical_ms)
      || target.p95_critical_ms <= target.p95_warning_ms
      || target.p95_critical_ms > 300000) {
      errors.push(`${name} connection-cycle stage P95 critical must exceed warning and be at most 300000 ms.`);
    }
  }

  const baseline = configuration.thresholds.adaptive_baseline ?? {
    enabled: true,
    lookback_hours: 24,
    minimum_samples: 30,
    max_samples: 1000,
    warning_sigma: 3.5,
    critical_sigma: 6,
  };
  if (!Number.isInteger(baseline.lookback_hours)
    || baseline.lookback_hours < 1 || baseline.lookback_hours > 168) {
    errors.push("Adaptive-baseline lookback must be an integer between 1 and 168 hours.");
  }
  if (!Number.isInteger(baseline.minimum_samples)
    || baseline.minimum_samples < 10 || baseline.minimum_samples > 5000) {
    errors.push("Adaptive-baseline minimum samples must be an integer between 10 and 5000.");
  }
  if (!Number.isInteger(baseline.max_samples)
    || baseline.max_samples < 30 || baseline.max_samples > 10000
    || baseline.max_samples < baseline.minimum_samples) {
    errors.push("Adaptive-baseline maximum samples must be at least the minimum and at most 10000.");
  }
  if (!Number.isFinite(baseline.warning_sigma)
    || baseline.warning_sigma <= 0 || baseline.warning_sigma > 20) {
    errors.push("Adaptive-baseline warning deviation must be greater than 0 and at most 20 sigma.");
  }
  if (!Number.isFinite(baseline.critical_sigma)
    || baseline.critical_sigma <= baseline.warning_sigma || baseline.critical_sigma > 30) {
    errors.push("Adaptive-baseline critical deviation must exceed warning and be at most 30 sigma.");
  }

  const serviceSlo = configuration.thresholds.service_slo ?? {
    enabled: true,
    window_size: 60,
    minimum_samples: 20,
    gateway: {
      availability_warning_percent: 99, availability_critical_percent: 95,
      latency_p95_warning_ms: 50, latency_p95_critical_ms: 100,
      packet_loss_p95_warning_percent: 5, packet_loss_p95_critical_percent: 20,
    },
    internet: {
      availability_warning_percent: 99, availability_critical_percent: 95,
      latency_p95_warning_ms: 150, latency_p95_critical_ms: 300,
      packet_loss_p95_warning_percent: 5, packet_loss_p95_critical_percent: 20,
    },
    dns: {
      availability_warning_percent: 99, availability_critical_percent: 95,
      latency_p95_warning_ms: 250, latency_p95_critical_ms: 500,
      packet_loss_p95_warning_percent: null, packet_loss_p95_critical_percent: null,
    },
    https: {
      availability_warning_percent: 99, availability_critical_percent: 95,
      latency_p95_warning_ms: 1000, latency_p95_critical_ms: 2000,
      packet_loss_p95_warning_percent: null, packet_loss_p95_critical_percent: null,
    },
  };
  if (!Number.isInteger(serviceSlo.window_size)
    || serviceSlo.window_size < 10 || serviceSlo.window_size > 1000) {
    errors.push("Service-SLO window must be an integer between 10 and 1000 executions.");
  }
  if (!Number.isInteger(serviceSlo.minimum_samples)
    || serviceSlo.minimum_samples < 5
    || serviceSlo.minimum_samples > serviceSlo.window_size) {
    errors.push("Service-SLO minimum samples must be between 5 and the window size.");
  }
  for (const [name, target] of [
    ["Gateway", serviceSlo.gateway],
    ["Internet", serviceSlo.internet],
    ["DNS", serviceSlo.dns],
    ["HTTPS", serviceSlo.https],
  ] as const) {
    if (!Number.isFinite(target.availability_warning_percent)
      || !Number.isFinite(target.availability_critical_percent)
      || target.availability_warning_percent < 0
      || target.availability_warning_percent > 100
      || target.availability_critical_percent < 0
      || target.availability_critical_percent >= target.availability_warning_percent) {
      errors.push(`${name} service-SLO availability critical must be lower than warning.`);
    }
    if (!Number.isFinite(target.latency_p95_warning_ms)
      || target.latency_p95_warning_ms <= 0
      || !Number.isFinite(target.latency_p95_critical_ms)
      || target.latency_p95_critical_ms <= target.latency_p95_warning_ms) {
      errors.push(`${name} service-SLO latency P95 critical must exceed warning.`);
    }
    const lossWarning = target.packet_loss_p95_warning_percent;
    const lossCritical = target.packet_loss_p95_critical_percent;
    if ((lossWarning === null) !== (lossCritical === null)
      || (lossWarning !== null && lossCritical !== null
        && (lossWarning < 0 || lossWarning > 100
          || lossCritical <= lossWarning || lossCritical > 100))) {
      errors.push(`${name} service-SLO packet-loss P95 thresholds are invalid.`);
    }
  }

  return errors;
}
