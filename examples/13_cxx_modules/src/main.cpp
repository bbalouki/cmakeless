#include <cstdlib>
#include <iomanip>
#include <iostream>

import geometry;
import units;

auto main() -> int
{
    constexpr geometry::Rectangle PANEL{3.5, 2.0};
    const auto doubled = geometry::scaled(PANEL, 2.0);

    std::cout << std::fixed << std::setprecision(2);
    std::cout << "panel area      : " << PANEL.area() << " in^2\n";
    std::cout << "panel perimeter : " << PANEL.perimeter() << " in\n";
    std::cout << "doubled area    : " << doubled.area() << " in^2\n";
    std::cout << "panel width     : " << units::inches_to_millimetres(PANEL.width) << " mm\n";
    return EXIT_SUCCESS;
}
