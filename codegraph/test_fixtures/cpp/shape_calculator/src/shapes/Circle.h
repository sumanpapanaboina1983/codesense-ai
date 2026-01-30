#ifndef CIRCLE_H
#define CIRCLE_H

#include "Shape.h"
#include <cmath>

/**
 * Circle shape implementation.
 */
class Circle : public Shape {
private:
    double radius_;
    static constexpr double PI = 3.14159265358979323846;

    void validateRadius(double r) const;

public:
    explicit Circle(double radius);
    ~Circle() override = default;

    // Shape interface implementation
    double area() const override;
    double perimeter() const override;
    std::string getName() const override;
    std::string getDescription() const override;

    // Circle-specific methods
    double getRadius() const;
    void setRadius(double radius);
    double getDiameter() const;
};

#endif // CIRCLE_H
