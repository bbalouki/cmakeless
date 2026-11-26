#include <array>
#include <cstdlib>
#include <iostream>
#include <thread>

#include "sensor.h"

auto main() -> int
{
    std::array<double, 2> readings{-3.0, 4.0};
    std::thread worker([&readings] {
        for (auto& reading : readings) {
            reading = sensor_calibrate(reading);
        }
    });
    worker.join();
    std::cout << "calibrated: " << readings[0] << ", " << readings[1] << '\n';
    return readings[0] == 3.0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
