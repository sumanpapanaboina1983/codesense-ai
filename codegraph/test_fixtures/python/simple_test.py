# Simple Python test fixture

def greet(name):
    print(f"Hello, {name}!")
    return f"Hello, {name}!"

class SimpleClass:
    def __init__(self, value):
        self.value = value

    def get_value(self):
        return self.value

# Line 14
instance = SimpleClass(42)
greet("World")
