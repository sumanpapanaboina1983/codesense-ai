#ifndef SHAPE_H
#define SHAPE_H

#include <string>

/**
 * Abstract base class for geometric shapes.
 */
class Shape {
public:
    virtual ~Shape() = default;

    // Pure virtual methods
    virtual double area() const = 0;
    virtual double perimeter() const = 0;
    virtual std::string getName() const = 0;
    virtual std::string getDescription() const = 0;
};

#endif // SHAPE_H
