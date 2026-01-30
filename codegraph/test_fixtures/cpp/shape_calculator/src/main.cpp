#include <iostream>
#include <vector>
#include <memory>
#include <stdexcept>

#include "shapes/Shape.h"
#include "shapes/Rectangle.h"
#include "shapes/Circle.h"
#include "utils/MathUtils.h"

// Print details about a shape

void printShapeDetails(const Shape& shape) {
    std::cout << "Shape: " << shape.getName() << std::endl;
    std::cout << "  Area: " << shape.area() << std::endl;
    std::cout << "  Perimeter: " << shape.perimeter() << std::endl;
    std::cout << "  Description: " << shape.getDescription() << std::endl;
    std::cout << std::endl;
}

// Line 21
int main(int argc, char* argv[]) {
    std::cout << "Shape Calculator v1.0" << std::endl;
    std::cout << "=====================" << std::endl << std::endl;

    // Create shapes using smart pointers
    std::vector<std::unique_ptr<Shape>> shapes;

    try {
        shapes.push_back(std::make_unique<Circle>(5.0));
        shapes.push_back(std::make_unique<Rectangle>(4.0, 6.0));
        shapes.push_back(std::make_unique<Circle>(3.0));

        // Print details for each shape
        for (const auto& shape : shapes) {
            printShapeDetails(*shape);
        }

        // Calculate total area
        double totalArea = 0.0;
        for (const auto& shape : shapes) {
            totalArea += shape->area();
        }
        std::cout << "Total area of all shapes: " << totalArea << std::endl;

    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
