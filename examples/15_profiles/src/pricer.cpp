#include <cmath>
#include <cstdlib>
#include <iostream>

namespace {

/// Discounts one cash flow continuously; the hot loop a pricer lives in.
auto discount(double amount, double rate, double years) -> double
{
    return amount * std::exp(-rate * years);
}

}  // namespace

auto main() -> int
{
    double present_value = 0.0;
    for (int year = 1; year <= 10; ++year) {
        present_value += discount(100.0, 0.05, static_cast<double>(year));
    }
    std::cout << "present value: " << present_value << '\n';
    return present_value > 0.0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
