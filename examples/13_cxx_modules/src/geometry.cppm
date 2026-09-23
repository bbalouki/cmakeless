export module geometry;

export namespace geometry {

struct Rectangle
{
    double width{0.0};
    double height{0.0};

    [[nodiscard]] auto area() const noexcept -> double { return width * height; }

    [[nodiscard]] auto perimeter() const noexcept -> double { return 2.0 * (width + height); }
};

[[nodiscard]] auto scaled(Rectangle shape, double factor) noexcept -> Rectangle
{
    return Rectangle{shape.width * factor, shape.height * factor};
}

}  // namespace geometry
