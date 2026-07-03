// A tiny C++ extension module, exposed to Python by cmakeless.
#include <pybind11/pybind11.h>

namespace python = pybind11;

[[nodiscard]] auto add(int first, int second) -> int
{
    return first + second;
}

PYBIND11_MODULE(mymath, module)
{
    module.doc() = "A tiny C++ extension built by cmakeless.";
    module.def("add", &add, "Add two integers.");
}
