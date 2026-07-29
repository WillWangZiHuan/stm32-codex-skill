# Servo PWM pack

Use this pack for SG90-style 50 Hz hobby servos. Configure the timer operation
with `target_hz: 50` and bind the generated timer handle and channel. The
module starts PWM through HAL, so advanced timers enable their main output
through the HAL start path.

The API accepts a pulse width from 1000 to 2000 microseconds or an angle from
0 to 180 degrees. Record the signal pin's board silkscreen and shared network.
Mark the pin as requiring an external supply in the board profile, then
acknowledge that pin in `safety.external_supply_pins` after checking a separate
5 V supply and common ground.
