/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 */

// GoogleTest suite for the stats library. cmakeless fetches GoogleTest (the
// default framework), registers each case with CTest, and 'cmakeless test'
// runs them all.
#include <stdexcept>
#include <vector>

#include <gtest/gtest.h>

#include "stats/series.hpp"

namespace {

TEST(SeriesTest, ComputesMeanAndCount)
{
    const stats::Series series{{2.0, 4.0, 6.0}};
    EXPECT_EQ(series.count(), 3U);
    EXPECT_DOUBLE_EQ(series.mean(), 4.0);
}

TEST(SeriesTest, ComputesSpread)
{
    const stats::Series series{{2.0, 4.0, 6.0}};
    EXPECT_DOUBLE_EQ(series.variance(), 8.0 / 3.0);
    EXPECT_DOUBLE_EQ(series.minimum(), 2.0);
    EXPECT_DOUBLE_EQ(series.maximum(), 6.0);
}

TEST(SeriesTest, MedianHandlesEvenAndOddCounts)
{
    // Braced lists with commas are wrapped in named locals so the test macros
    // do not mistake the commas for extra macro arguments.
    const stats::Series odd_count{{5.0, 1.0, 3.0}};
    const stats::Series even_count{{5.0, 1.0, 3.0, 9.0}};
    EXPECT_DOUBLE_EQ(odd_count.median(), 3.0);
    EXPECT_DOUBLE_EQ(even_count.median(), 4.0);
}

TEST(SeriesTest, RejectsAnEmptySeries)
{
    EXPECT_THROW(stats::Series{std::vector<double>{}}, std::invalid_argument);
}

} // namespace
