#include "Circle.h"
#include <stdexcept>
#include <sstream>

void Circle::validateRadius(double r) const {
    if (r <= 0) {
        throw std::invalid_argument("Radius must be positive");
    }
}
Circle::Circle(double radius) : radius_(radius) {
    validateRadius(radius);
}

// Line 14
// Line 15
// Line 16
// Line 17
// Line 18
// Line 19
double Circle::area() const {
    return PI * radius_ * radius_;
}

double Circle::perimeter() const {
    return 2 * PI * radius_;
}

std::string Circle::getName() const {
    return "Circle";
}

std::string Circle::getDescription() const {
    std::ostringstream oss;
    oss << "Circle with radius " << radius_;
    return oss.str();
}

double Circle::getRadius() const {
    return radius_;
}

void Circle::setRadius(double radius) {
    validateRadius(radius);
    radius_ = radius;
}

double Circle::getDiameter() const {
    return 2 * radius_;
}
