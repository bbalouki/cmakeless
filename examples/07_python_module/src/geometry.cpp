// A real pybind11 module: a 2D vector type with operators, properties, and
// an exception that surfaces in Python as a normal ValueError.
//
// This is what "add_python_module" buys you: a C++ class exposed to Python
// with methods, arithmetic operators, read-only properties, docstrings, and
// automatic C++ to Python exception translation, all built and importable
// straight from the interpreter that ran the build.
#include <cmath>
#include <sstream>
#include <stdexcept>
#include <string>

#include <pybind11/operators.h>
#include <pybind11/pybind11.h>

namespace python = pybind11;

namespace {

// A minimal immutable 2D vector: a small, copyable, comparable value type.
class Vec2
{
public:
    Vec2(double x_component, double y_component) noexcept
        : m_x{x_component}, m_y{y_component}
    {
    }

    [[nodiscard]] auto x() const noexcept -> double { return m_x; }
    [[nodiscard]] auto y() const noexcept -> double { return m_y; }

    [[nodiscard]] auto length() const noexcept -> double
    {
        return std::hypot(m_x, m_y);
    }

    [[nodiscard]] auto dot(const Vec2& other) const noexcept -> double
    {
        return (m_x * other.m_x) + (m_y * other.m_y);
    }

    // Return the unit vector; a zero-length vector has no direction, which
    // is a domain error pybind11 translates into a Python ValueError.
    [[nodiscard]] auto normalized() const -> Vec2
    {
        const double magnitude{length()};
        if (magnitude == 0.0)
        {
            throw std::domain_error{"cannot normalize a zero-length vector"};
        }
        return Vec2{m_x / magnitude, m_y / magnitude};
    }

    [[nodiscard]] auto operator+(const Vec2& other) const noexcept -> Vec2
    {
        return Vec2{m_x + other.m_x, m_y + other.m_y};
    }

    [[nodiscard]] auto operator-(const Vec2& other) const noexcept -> Vec2
    {
        return Vec2{m_x - other.m_x, m_y - other.m_y};
    }

    [[nodiscard]] auto operator*(double scalar) const noexcept -> Vec2
    {
        return Vec2{m_x * scalar, m_y * scalar};
    }

    [[nodiscard]] auto operator==(const Vec2& other) const noexcept -> bool
    {
        return m_x == other.m_x && m_y == other.m_y;
    }

    [[nodiscard]] auto repr() const -> std::string
    {
        std::ostringstream stream;
        stream << "Vec2(" << m_x << ", " << m_y << ")";
        return stream.str();
    }

private:
    double m_x;
    double m_y;
};

} // namespace

PYBIND11_MODULE(geometry, module)
{
    module.doc() = "A tiny 2D geometry library, written in C++, built by cmakeless.";

    python::class_<Vec2>(module, "Vec2", "An immutable 2D vector.")
        .def(python::init<double, double>(), python::arg("x"), python::arg("y"))
        .def_property_readonly("x", &Vec2::x, "The x component.")
        .def_property_readonly("y", &Vec2::y, "The y component.")
        .def("length", &Vec2::length, "Euclidean length of the vector.")
        .def("dot", &Vec2::dot, python::arg("other"), "Dot product with another vector.")
        .def("normalized", &Vec2::normalized,
             "Unit vector in the same direction; raises ValueError when zero-length.")
        .def(python::self + python::self)
        .def(python::self - python::self)
        .def(python::self * double())
        .def(python::self == python::self)
        .def("__repr__", &Vec2::repr);
}
