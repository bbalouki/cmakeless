/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

// The public face of the stats library: a Series of samples you can summarize.
//
// This header is what consumers include; the implementation (and its fmt
// dependency) stays private in series.cpp, so linking against stats does not
// drag fmt into your own translation units.
#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace stats {

/// An immutable collection of samples with summary statistics.
///
/// Construction rejects an empty sample set, so every accessor below is total
/// and never has to signal "undefined for no data" at the call site.
class Series
{
public:
    /// Build a series from at least one sample.
    ///
    /// @param samples The observations to summarize.
    /// @throws std::invalid_argument When @p samples is empty.
    explicit Series(std::vector<double> samples);

    [[nodiscard]] auto count() const noexcept -> std::size_t;
    [[nodiscard]] auto mean() const noexcept -> double;
    [[nodiscard]] auto variance() const noexcept -> double;
    [[nodiscard]] auto stddev() const noexcept -> double;
    [[nodiscard]] auto minimum() const noexcept -> double;
    [[nodiscard]] auto maximum() const noexcept -> double;
    [[nodiscard]] auto median() const -> double;

    /// A one-line, human-readable summary, formatted with fmt internally.
    [[nodiscard]] auto summary() const -> std::string;

private:
    std::vector<double> m_samples;
};

} // namespace stats
