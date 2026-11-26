#include "sensor.h"

#include <math.h>

double sensor_calibrate(double raw)
{
    return sqrt(raw * raw);
}
