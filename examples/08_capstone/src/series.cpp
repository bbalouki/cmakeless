// The stats library implementation. fmt is a private dependency here: it is
// used only for summary() and never appears in the public header.
#include "stats/series.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <stdexcept>
#include <utility>

#include <fmt/format.h>

namespace stats {

Series::Series(std::vector<double> samples) : m_samples{std::move(samples)}
{
    if (m_samples.empty())
    {
        throw std::invalid_argument{"a Series needs at least one sample"};
    }
}

auto Series::count() const noexcept -> std::size_t
{
    return m_samples.size();
}

auto Series::mean() const noexcept -> double
{
    const double total{std::accumulate(m_samples.begin(), m_samples.end(), 0.0)};
    return total / static_cast<double>(m_samples.size());
}

auto Series::variance() const noexcept -> double
{
    const double average{mean()};
    const double sum_of_squares{std::accumulate(
        m_samples.begin(), m_samples.end(), 0.0,
        [average](double running, double sample) {
            const double deviation{sample - average};
            return running + (deviation * deviation);
        })};
    return sum_of_squares / static_cast<double>(m_samples.size());
}

auto Series::stddev() const noexcept -> double
{
    return std::sqrt(variance());
}

auto Series::minimum() const noexcept -> double
{
    return *std::min_element(m_samples.begin(), m_samples.end());
}

auto Series::maximum() const noexcept -> double
{
    return *std::max_element(m_samples.begin(), m_samples.end());
}

auto Series::median() const -> double
{
    std::vector<double> ordered{m_samples};
    std::sort(ordered.begin(), ordered.end());
    const std::size_t middle{ordered.size() / 2};
    if (ordered.size() % 2 == 1)
    {
        return ordered[middle];
    }
    return (ordered[middle - 1] + ordered[middle]) / 2.0;
}

auto Series::summary() const -> std::string
{
    return fmt::format(
        "n={} mean={:.3f} stddev={:.3f} min={:.3f} median={:.3f} max={:.3f}",
        count(), mean(), stddev(), minimum(), median(), maximum());
}

} // namespace stats
