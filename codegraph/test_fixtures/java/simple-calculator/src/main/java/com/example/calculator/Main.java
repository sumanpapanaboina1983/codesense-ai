package com.example.calculator;

import java.util.InputMismatchException;
import java.util.Scanner;
import java.util.Set;

/**
 * Main entry point for the calculator application.
 */
public class Main {

    public static void main(String[] args) {
        Calculator calc = new Calculator();

        // Register basic operations
        calc.registerOperation("add", (a, b) -> a + b);
        calc.registerOperation("subtract", (a, b) -> a - b);
        calc.registerOperation("multiply", (a, b) -> a * b);
        calc.registerOperation("divide", (a, b) -> {
            if (b == 0) throw new ArithmeticException("Division by zero");
            return a / b;
        });

        Scanner scanner = new Scanner(System.in);

        System.out.println("Simple Calculator");
        System.out.println("Available operations: " + calc.getAvailableOperations());

        try {
            System.out.print("Enter first number: ");
            double a = scanner.nextDouble();

            System.out.print("Enter operation: ");
            String op = scanner.next();

            System.out.print("Enter second number: ");
            double b = scanner.nextDouble();

            double result = calc.performOperation(op, a, b);
            System.out.println("Result: " + result);

        } catch (InputMismatchException e) {
            System.err.println("Invalid input");
        } catch (IllegalArgumentException e) {
            System.err.println(e.getMessage());
        } finally {
            scanner.close();
        }
    }
}
