package com.example.calculator.operations;

/**
 * Functional interface for calculator operations.
 */
public interface Operation {
    /**
     * Execute the operation on two operands.
     *
     * @param a First operand
     * @param b Second operand
     * @return Result of the operation
     */
    double execute(double a, double b);
}
