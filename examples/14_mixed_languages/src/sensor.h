#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/// Calibrates one raw sensor reading; plain C, as vendor HAL code usually is.
double sensor_calibrate(double raw);

#ifdef __cplusplus
}
#endif
