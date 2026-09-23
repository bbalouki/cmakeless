export module units;

export namespace units {

// A module interface can be consumed by another module in the same file set:
// CMake scans both and compiles this one first wherever it is imported.
inline constexpr double MILLIMETRES_PER_INCH{25.4};

[[nodiscard]] auto inches_to_millimetres(double inches) noexcept -> double
{
    return inches * MILLIMETRES_PER_INCH;
}

}  // namespace units
