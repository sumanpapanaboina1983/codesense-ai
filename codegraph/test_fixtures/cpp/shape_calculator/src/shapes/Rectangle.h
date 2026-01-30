#ifndef RECTANGLE_H
#define RECTANGLE_H

#include "Shape.h"

/**
 * Rectangle shape implementation.
 */
class Rectangle : public Shape {
private:
    double width_;
    double height_;

public:
    Rectangle(double width, double height);
    ~Rectangle() override = default;

    double area() const override;
    double perimeter() const override;
    std::string getName() const override;
    std::string getDescription() const override;

    double getWidth() const;
    double getHeight() const;
};

#endif // RECTANGLE_H
