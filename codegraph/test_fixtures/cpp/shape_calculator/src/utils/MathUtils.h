#ifndef MATHUTILS_H
#define MATHUTILS_H

namespace MathUtils {
    constexpr double PI = 3.14159265358979323846;
    constexpr double E = 2.71828182845904523536;

    inline double square(double x) {
        return x * x;
    }

    inline double cube(double x) {
        return x * x * x;
    }
}

#endif // MATHUTILS_H
