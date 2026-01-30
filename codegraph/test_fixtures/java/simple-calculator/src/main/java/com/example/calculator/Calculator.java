package com.example.calculator;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;

import com.example.calculator.operations.Operation;

/**
 * A simple calculator that supports basic operations
 * and memory functionality.
 */
// Line 13
// Line 14
// Line 15
public class Calculator {

    private final Map<String, Operation> operations;

    private double memory;
    private double lastResult;

    // Line 23
    // Line 24
    public Calculator() {
        this.operations = new HashMap<>();
        this.memory = 0.0;
        this.lastResult = 0.0;
    }

    public void registerOperation(String name, Operation operation) {
        operations.put(name, operation);
    }

    public Set<String> getAvailableOperations() {
        return operations.keySet();
    }

    public void storeInMemory(double value) {
        this.memory = value;
    }

    public double recallMemory() {
        return this.memory;
    }

    public void clearMemory() {
        this.memory = 0.0;
    }

    // Line 52
    // Line 53
    // Line 54
    // Line 55
    // Line 56
    // Line 57
    // Line 58
    // Line 59
    // Line 60
    // Line 61
    public double performOperation(String operationName, double a, double b) {
        Operation op = operations.get(operationName);
        if (op == null) {
            throw new IllegalArgumentException("Unknown operation: " + operationName);
        }
        lastResult = op.execute(a, b);
        return lastResult;
    }
}
