// Expose the stats::Series class to Python with pybind11, so the same C++ that
// powers the CLI is importable as a native module. Building the extension is a
// single add_python_module() call in build.py; no separate binding build.
#include <vector>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h> // enables automatic list <-> std::vector<double> conversion

#include "stats/series.hpp"

namespace python = pybind11;

PYBIND11_MODULE(pystats, module)
{
    module.doc() = "Summary statistics, computed in C++, built by cmakeless.";

    python::class_<stats::Series>(module, "Series", "An immutable series of samples.")
        .def(python::init<std::vector<double>>(), python::arg("samples"),
             "Build a series from a non-empty sequence of numbers.")
        .def("count", &stats::Series::count, "Number of samples.")
        .def("mean", &stats::Series::mean, "Arithmetic mean.")
        .def("variance", &stats::Series::variance, "Population variance.")
        .def("stddev", &stats::Series::stddev, "Population standard deviation.")
        .def("minimum", &stats::Series::minimum, "Smallest sample.")
        .def("maximum", &stats::Series::maximum, "Largest sample.")
        .def("median", &stats::Series::median, "Median sample.")
        .def("summary", &stats::Series::summary, "One-line human-readable summary.")
        .def("__repr__", [](const stats::Series& series) {
            return "<pystats.Series " + series.summary() + ">";
        });
}
