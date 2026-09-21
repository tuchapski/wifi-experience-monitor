import {
  useEffect,
  useState,
} from "react";

import {
  configureSensor,
  getSensorStatus,
  getWirelessInterfaces,
  startSensor,
  stopSensor,
} from "./api";

import type {
  SensorStatus,
  WirelessInterface,
} from "./types";


interface SensorControlProps {
  onStatusChange?: (
    status: SensorStatus,
  ) => void;
}


function SensorControl({
  onStatusChange,
}: SensorControlProps) {
  const [
    interfaces,
    setInterfaces,
  ] = useState<
    WirelessInterface[]
  >([]);

  const [
    selectedInterface,
    setSelectedInterface,
  ] = useState("");

  const [
    intervalSeconds,
    setIntervalSeconds,
  ] = useState(5);

  const [
    status,
    setStatus,
  ] = useState<
    SensorStatus | null
  >(null);

  const [
    error,
    setError,
  ] = useState<
    string | null
  >(null);

  const [
    loading,
    setLoading,
  ] = useState(false);


  async function refresh() {
    try {
      const [
        interfaceData,
        statusData,
      ] = await Promise.all([
        getWirelessInterfaces(),
        getSensorStatus(),
      ]);

      setInterfaces(
        interfaceData,
      );

      setStatus(
        statusData,
      );

      if (
        statusData.interface !== null
      ) {
        setSelectedInterface(
          statusData.interface,
        );

        setIntervalSeconds(
          statusData.interval_seconds,
        );
      } else if (
        interfaceData.length > 0
      ) {
        setSelectedInterface(
          interfaceData[0].name,
        );
      }

      onStatusChange?.(
        statusData
      );

      setError(
        null
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load sensor configuration.",
      );
    }
  }


  useEffect(() => {
    void refresh();

    const timer = window.setInterval(
      () => {
        void getSensorStatus()
          .then((statusData) => {
            setStatus(
              statusData
            );

            onStatusChange?.(
              statusData
            );
          })
          .catch(() => {
            // Main refresh will expose errors.
          });
      },
      5000,
    );

    return () => {
      window.clearInterval(
        timer
      );
    };
  }, []);


  async function handleStart() {
    if (!selectedInterface) {
      setError(
        "Select a wireless interface."
      );

      return;
    }

    setLoading(
      true
    );

    try {
      await configureSensor(
        selectedInterface,
        intervalSeconds,
      );

      const statusData =
        await startSensor();

      setStatus(
        statusData
      );

      onStatusChange?.(
        statusData
      );

      setError(
        null
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to start sensor.",
      );
    } finally {
      setLoading(
        false
      );
    }
  }


  async function handleStop() {
    setLoading(
      true
    );

    try {
      const statusData =
        await stopSensor();

      setStatus(
        statusData
      );

      onStatusChange?.(
        statusData
      );

      setError(
        null
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to stop sensor.",
      );
    } finally {
      setLoading(
        false
      );
    }
  }


  const selectedDetails =
    interfaces.find(
      (item) =>
        item.name
        === selectedInterface,
    );


  return (
    <section className="sensor-control">

      <div className="sensor-control-header">

        <div>
          <h2>
            Sensor Configuration
          </h2>

          <p>
            Select the Wi-Fi interface
            used for monitoring.
          </p>
        </div>


        <span
          className={
            status?.running
              ? "sensor-state sensor-running"
              : "sensor-state sensor-stopped"
          }
        >
          {status?.running
            ? "RUNNING"
            : "STOPPED"}
        </span>

      </div>


      <div className="sensor-control-grid">

        <label>

          <span>
            Wireless Interface
          </span>

          <select
            value={
              selectedInterface
            }
            disabled={
              status?.running
              || loading
            }
            onChange={(event) => {
              setSelectedInterface(
                event.target.value
              );
            }}
          >

            {interfaces.length === 0 && (
              <option value="">
                No Wi-Fi interfaces detected
              </option>
            )}

            {interfaces.map(
              (item) => (

                <option
                  key={item.name}
                  value={item.name}
                >
                  {item.name}
                </option>

              ),
            )}

          </select>

        </label>


        <label>

          <span>
            Collection Interval
          </span>

          <input
            type="number"
            min={1}
            max={3600}
            value={
              intervalSeconds
            }
            disabled={
              status?.running
              || loading
            }
            onChange={(event) => {
              setIntervalSeconds(
                Number(
                  event.target.value
                )
              );
            }}
          />

          <small>
            seconds
          </small>

        </label>

      </div>


      {selectedDetails && (
        <div className="interface-details">

          <span>
            PHY:{" "}
            <strong>
              {selectedDetails.phy ??
                "N/A"}
            </strong>
          </span>

          <span>
            Type:{" "}
            <strong>
              {selectedDetails.interface_type ??
                "N/A"}
            </strong>
          </span>

          <span>
            MAC:{" "}
            <strong>
              {selectedDetails.mac_address ??
                "N/A"}
            </strong>
          </span>

        </div>
      )}


      {status?.last_error && (
        <div className="error">
          Sensor error:{" "}
          {status.last_error}
        </div>
      )}


      {error && (
        <div className="error">
          {error}
        </div>
      )}


      <div className="sensor-control-actions">

        {!status?.running ? (

          <button
            type="button"
            disabled={
              loading
              || !selectedInterface
            }
            onClick={() => {
              void handleStart();
            }}
          >
            Start Monitoring
          </button>

        ) : (

          <button
            type="button"
            className="stop-button"
            disabled={loading}
            onClick={() => {
              void handleStop();
            }}
          >
            Stop Monitoring
          </button>

        )}

      </div>

    </section>
  );
}


export default SensorControl;
