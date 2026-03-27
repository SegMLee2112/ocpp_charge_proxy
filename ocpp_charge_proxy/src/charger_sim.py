from __future__ import annotations

import logging
import random

logger = logging.getLogger(__name__)

# Valid current settings (amps)
VALID_CURRENT_SETTINGS = [6, 10, 13, 16, 20, 25, 32]

# Power delivery model at 32A (~230V)
# At lower current settings, power scales proportionally
_VOLTAGE_NOMINAL = 230.0
_EFFICIENCY_FACTOR = 0.985  # real delivery is ~98.5% of theoretical


class ChargerSimulator:
    """Simulates realistic power delivery for an OCPP chargepoint.

    Power model:
    - At 32A: steady state ~7.27 kW (230V nominal, 98.5% efficiency)
    - Fluctuation: ±0.08 kW typical, occasionally ±0.15 kW
    - Voltage: ~228-232V (UK grid)
    - Frequency: ~49.95-50.05 Hz

    Current setting supports 6/10/13/16/20/25/32A and power scales
    proportionally.
    """

    def __init__(self, current_amps: int = 32):
        if current_amps not in VALID_CURRENT_SETTINGS:
            logger.warning(
                "Current %dA not in valid settings %s, using closest",
                current_amps, VALID_CURRENT_SETTINGS,
            )
            current_amps = min(VALID_CURRENT_SETTINGS, key=lambda x: abs(x - current_amps))
        self._current_amps = current_amps
        self._charging = False

    @property
    def current_amps(self) -> int:
        return self._current_amps

    @current_amps.setter
    def current_amps(self, value: int) -> None:
        if value not in VALID_CURRENT_SETTINGS:
            raise ValueError(f"Invalid current setting {value}A. Valid: {VALID_CURRENT_SETTINGS}")
        self._current_amps = value
        logger.info("Charger current set to %dA (~%.1f kW)", value, self.rated_power_kw)

    @property
    def rated_power_kw(self) -> float:
        """Theoretical max power at current setting."""
        return round(self._current_amps * _VOLTAGE_NOMINAL / 1000, 1)

    @property
    def expected_power_kw(self) -> float:
        """Expected real-world power delivery (slightly below rated)."""
        return round(self._current_amps * _VOLTAGE_NOMINAL * _EFFICIENCY_FACTOR / 1000, 2)

    def start_charging(self) -> None:
        self._charging = True

    def stop_charging(self) -> None:
        self._charging = False

    @property
    def is_charging(self) -> bool:
        return self._charging

    def sample(self) -> ChargerReading:
        """Generate a realistic instantaneous reading."""
        voltage = round(random.uniform(228.0, 232.0), 1)
        frequency = round(random.uniform(49.95, 50.05), 2)

        if not self._charging:
            return ChargerReading(
                power_kw=0.0,
                voltage=voltage,
                current_a=0.0,
                frequency_hz=frequency,
                power_offered_kw=0.0,
            )

        # Power based on current setting with realistic fluctuation
        mean_power = self.expected_power_kw
        spread = 0.08 * (self._current_amps / 32)  # scale fluctuation with current

        if random.random() < 0.1:
            # Occasional wider swing
            power_kw = round(random.uniform(mean_power - spread * 2, mean_power + spread * 2), 2)
        else:
            power_kw = round(random.gauss(mean_power, spread), 2)

        power_kw = max(0.1, min(self.rated_power_kw, power_kw))
        current_a = round((power_kw * 1000) / voltage, 2)

        return ChargerReading(
            power_kw=power_kw,
            voltage=voltage,
            current_a=current_a,
            frequency_hz=frequency,
            power_offered_kw=self.rated_power_kw,
            current_offered_a=self._current_amps,
        )


class ChargerReading:
    """Instantaneous reading from the simulated charger."""

    __slots__ = ("power_kw", "voltage", "current_a", "frequency_hz", "power_offered_kw", "current_offered_a")

    def __init__(
        self,
        power_kw: float,
        voltage: float,
        current_a: float,
        frequency_hz: float,
        power_offered_kw: float,
        current_offered_a: int = 32,
    ):
        self.power_kw = power_kw
        self.voltage = voltage
        self.current_a = current_a
        self.frequency_hz = frequency_hz
        self.power_offered_kw = power_offered_kw
        self.current_offered_a = current_offered_a
