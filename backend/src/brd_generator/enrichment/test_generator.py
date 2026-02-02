"""Test Generator.

Generates test skeletons for untested code entities using LLM.
Supports multiple testing frameworks:
- Jest (JavaScript/TypeScript)
- Mocha (JavaScript)
- JUnit (Java)
- Pytest (Python)
- Go test (Go)
- xUnit (C#)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)


class TestFramework(str, Enum):
    """Supported testing frameworks."""
    JEST = "jest"
    MOCHA = "mocha"
    JUNIT = "junit"
    PYTEST = "pytest"
    GO_TEST = "go_test"
    XUNIT = "xunit"


class TestType(str, Enum):
    """Types of tests to generate."""
    UNIT = "unit"
    INTEGRATION = "integration"


@dataclass
class FunctionContext:
    """Context information for a function to test."""
    entity_id: str
    entity_name: str
    file_path: str
    language: str
    kind: str
    signature: Optional[str] = None
    parameters: list[dict[str, Any]] = None
    return_type: Optional[str] = None
    source_code: Optional[str] = None
    parent_class: Optional[str] = None
    dependencies: list[str] = None
    throws: list[str] = None
    is_async: bool = False
    is_static: bool = False
    visibility: str = "public"

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = []
        if self.dependencies is None:
            self.dependencies = []
        if self.throws is None:
            self.throws = []


@dataclass
class GeneratedTest:
    """Generated test for an entity."""
    entity_id: str
    entity_name: str
    test_file_path: str
    test_code: str
    test_framework: TestFramework
    test_type: TestType
    test_count: int
    mocks: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


class TestGenerator:
    """Generates tests for code entities using LLM."""

    # Test templates by framework
    TEMPLATES = {
        TestFramework.JEST: {
            "imports": '''import {{ {entity} }} from '{import_path}';
{mock_imports}
''',
            "describe": '''describe('{entity_name}', () => {{
{tests}
}});
''',
            "test": '''  it('{test_name}', {async_keyword}() => {{
{setup}
{act}
{assert}
  }});
''',
            "mock": '''jest.mock('{module}', () => ({{
  {mock_impl}
}}));
''',
        },
        TestFramework.PYTEST: {
            "imports": '''import pytest
from {import_path} import {entity}
{mock_imports}
''',
            "class": '''class Test{entity_name}:
{tests}
''',
            "test": '''    {async_keyword}def test_{test_name}(self{fixtures}):
        # Arrange
{setup}
        # Act
{act}
        # Assert
{assert}
''',
            "fixture": '''@pytest.fixture
def {name}():
    {impl}
    return {return_val}
''',
        },
        TestFramework.JUNIT: {
            "imports": '''import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import static org.junit.jupiter.api.Assertions.*;
{mock_imports}
''',
            "class": '''class {entity_name}Test {{
{setup}
{tests}
}}
''',
            "test": '''    @Test
    void {test_name}() {{
        // Arrange
{setup}
        // Act
{act}
        // Assert
{assert}
    }}
''',
        },
        TestFramework.GO_TEST: {
            "imports": '''package {package}

import (
    "testing"
{mock_imports}
)
''',
            "test": '''func Test{entity_name}_{test_name}(t *testing.T) {{
    // Arrange
{setup}
    // Act
{act}
    // Assert
{assert}
}}
''',
        },
        TestFramework.XUNIT: {
            "imports": '''using Xunit;
using Moq;
{mock_imports}
''',
            "class": '''public class {entity_name}Tests
{{
{tests}
}}
''',
            "test": '''    [Fact]
    public {async_keyword}void {test_name}()
    {{
        // Arrange
{setup}
        // Act
{act}
        // Assert
{assert}
    }}
''',
        },
    }

    # LLM prompt for test generation
    TEST_GENERATION_PROMPT = '''Generate {test_type} tests for the following {language} {kind}:

Name: {name}
Signature: {signature}
Source Code:
```{language}
{source_code}
```

Context:
- Parent class/module: {parent}
- Dependencies: {dependencies}
- Is async: {is_async}
- Known exceptions: {throws}

Generate tests using {framework} framework that cover:
1. Normal/happy path scenarios
2. Edge cases (null inputs, empty collections, boundary values)
3. Error handling (if applicable)
{mock_instructions}

Format the tests properly for {framework}.

Generated Tests:'''

    def __init__(self, copilot_session: Any = None):
        """Initialize the test generator.

        Args:
            copilot_session: Optional Copilot session for LLM-based generation.
        """
        self.copilot_session = copilot_session

    async def generate_tests(
        self,
        entity: FunctionContext,
        framework: TestFramework = TestFramework.JEST,
        test_types: list[TestType] = None,
        include_mocks: bool = True,
        include_edge_cases: bool = True,
    ) -> GeneratedTest:
        """Generate tests for a single entity.

        Args:
            entity: Context information about the entity to test.
            framework: Testing framework to use.
            test_types: Types of tests to generate.
            include_mocks: Whether to include mock setup.
            include_edge_cases: Whether to include edge case tests.

        Returns:
            GeneratedTest with the generated test code.
        """
        if test_types is None:
            test_types = [TestType.UNIT]

        logger.info(f"Generating {framework.value} tests for {entity.entity_name}")

        if self.copilot_session:
            test_code, mocks, test_count = await self._generate_with_llm(
                entity, framework, test_types, include_mocks, include_edge_cases
            )
        else:
            test_code, mocks, test_count = self._generate_from_template(
                entity, framework, test_types, include_mocks, include_edge_cases
            )

        # Determine test file path
        test_file_path = self._get_test_file_path(entity.file_path, framework)

        return GeneratedTest(
            entity_id=entity.entity_id,
            entity_name=entity.entity_name,
            test_file_path=test_file_path,
            test_code=test_code,
            test_framework=framework,
            test_type=test_types[0] if test_types else TestType.UNIT,
            test_count=test_count,
            mocks=mocks,
            imports=self._get_required_imports(entity, framework),
        )

    async def generate_batch(
        self,
        entities: list[FunctionContext],
        framework: TestFramework = TestFramework.JEST,
        **options,
    ) -> list[GeneratedTest]:
        """Generate tests for multiple entities.

        Args:
            entities: List of entity contexts to test.
            framework: Testing framework to use.
            **options: Additional options passed to generate_tests.

        Returns:
            List of GeneratedTest objects.
        """
        results = []
        for entity in entities:
            try:
                test = await self.generate_tests(entity, framework, **options)
                results.append(test)
            except Exception as e:
                logger.error(f"Failed to generate tests for {entity.entity_name}: {e}")
        return results

    async def _generate_with_llm(
        self,
        entity: FunctionContext,
        framework: TestFramework,
        test_types: list[TestType],
        include_mocks: bool,
        include_edge_cases: bool,
    ) -> tuple[str, list[str], int]:
        """Generate tests using LLM."""
        mock_instructions = ""
        if include_mocks and entity.dependencies:
            mock_instructions = f"4. Mock these dependencies: {', '.join(entity.dependencies)}"

        prompt = self.TEST_GENERATION_PROMPT.format(
            test_type=", ".join(t.value for t in test_types),
            language=entity.language,
            kind=entity.kind.lower(),
            name=entity.entity_name,
            signature=entity.signature or entity.entity_name,
            source_code=entity.source_code or "// Source code not available",
            parent=entity.parent_class or "None",
            dependencies=", ".join(entity.dependencies) if entity.dependencies else "None",
            is_async=entity.is_async,
            throws=", ".join(entity.throws) if entity.throws else "None",
            framework=framework.value,
            mock_instructions=mock_instructions,
        )

        try:
            response = await self.copilot_session.send_message(prompt)
            return self._extract_tests(response, framework), entity.dependencies if include_mocks else [], self._count_tests(response, framework)
        except Exception as e:
            logger.warning(f"LLM generation failed, falling back to template: {e}")
            return self._generate_from_template(
                entity, framework, test_types, include_mocks, include_edge_cases
            )

    def _generate_from_template(
        self,
        entity: FunctionContext,
        framework: TestFramework,
        test_types: list[TestType],
        include_mocks: bool,
        include_edge_cases: bool,
    ) -> tuple[str, list[str], int]:
        """Generate tests from templates."""
        templates = self.TEMPLATES.get(framework, self.TEMPLATES[TestFramework.JEST])
        tests = []
        test_count = 0

        # Generate basic happy path test
        tests.append(self._create_test(
            entity,
            f"should_work_correctly",
            templates,
            framework,
        ))
        test_count += 1

        # Generate edge case tests if requested
        if include_edge_cases:
            # Null/undefined input test
            if entity.parameters:
                tests.append(self._create_test(
                    entity,
                    f"should_handle_null_input",
                    templates,
                    framework,
                    is_edge_case=True,
                ))
                test_count += 1

            # Empty input test for collections
            for param in entity.parameters:
                if "list" in str(param.get("type", "")).lower() or "array" in str(param.get("type", "")).lower():
                    tests.append(self._create_test(
                        entity,
                        f"should_handle_empty_array",
                        templates,
                        framework,
                        is_edge_case=True,
                    ))
                    test_count += 1
                    break

        # Generate error handling test if the function throws
        if entity.throws:
            tests.append(self._create_test(
                entity,
                f"should_throw_on_error",
                templates,
                framework,
                is_error_case=True,
            ))
            test_count += 1

        # Combine tests into a test suite
        test_code = self._wrap_tests(entity, tests, templates, framework)

        mocks = entity.dependencies if include_mocks else []
        return test_code, mocks, test_count

    def _create_test(
        self,
        entity: FunctionContext,
        test_name: str,
        templates: dict,
        framework: TestFramework,
        is_edge_case: bool = False,
        is_error_case: bool = False,
    ) -> str:
        """Create a single test case."""
        async_keyword = "async " if entity.is_async else ""

        # Setup
        setup = "        // Setup test data"
        if entity.parameters:
            param_setups = []
            for param in entity.parameters:
                pname = param.get("name", "param")
                ptype = param.get("type", "any")
                if is_edge_case:
                    param_setups.append(f"        const {pname} = null;")
                else:
                    param_setups.append(f"        const {pname} = /* test value */;")
            setup = "\n".join(param_setups)

        # Act
        params_str = ", ".join(p.get("name", "param") for p in entity.parameters)
        if entity.parent_class:
            act = f"        const result = instance.{entity.entity_name}({params_str});"
        else:
            act = f"        const result = {entity.entity_name}({params_str});"

        if entity.is_async:
            act = act.replace("const result =", "const result = await")

        # Assert
        if is_error_case:
            assert_stmt = f"        expect(() => {entity.entity_name}({params_str})).toThrow();"
        elif is_edge_case:
            assert_stmt = "        expect(result).toBeDefined();"
        else:
            assert_stmt = "        expect(result).toBeDefined();"

        return templates.get("test", "").format(
            test_name=test_name.replace("_", " "),
            async_keyword=async_keyword,
            setup=setup,
            act=act,
            assert_stmt=assert_stmt,
            fixtures="",
        )

    def _wrap_tests(
        self,
        entity: FunctionContext,
        tests: list[str],
        templates: dict,
        framework: TestFramework,
    ) -> str:
        """Wrap tests in appropriate container (describe block, test class, etc.)."""
        tests_content = "\n".join(tests)

        if framework in [TestFramework.JEST, TestFramework.MOCHA]:
            return templates.get("describe", "").format(
                entity_name=entity.entity_name,
                tests=tests_content,
            )
        elif framework in [TestFramework.JUNIT, TestFramework.XUNIT]:
            return templates.get("class", "").format(
                entity_name=entity.entity_name,
                tests=tests_content,
                setup="",
            )
        elif framework == TestFramework.PYTEST:
            return templates.get("class", "").format(
                entity_name=entity.entity_name,
                tests=tests_content,
            )
        else:
            return tests_content

    def _get_test_file_path(self, source_path: str, framework: TestFramework) -> str:
        """Generate test file path from source file path."""
        import os

        base, ext = os.path.splitext(source_path)
        dir_name = os.path.dirname(source_path)
        file_name = os.path.basename(base)

        if framework in [TestFramework.JEST, TestFramework.MOCHA]:
            return os.path.join(dir_name, "__tests__", f"{file_name}.test{ext}")
        elif framework == TestFramework.PYTEST:
            return os.path.join(dir_name, "tests", f"test_{file_name}.py")
        elif framework == TestFramework.JUNIT:
            # Convert src/main to src/test
            test_path = source_path.replace("/main/", "/test/")
            base, _ = os.path.splitext(test_path)
            return f"{base}Test.java"
        elif framework == TestFramework.XUNIT:
            return os.path.join(dir_name + ".Tests", f"{file_name}Tests.cs")
        elif framework == TestFramework.GO_TEST:
            return base + "_test.go"

        return f"{base}.test{ext}"

    def _get_required_imports(
        self,
        entity: FunctionContext,
        framework: TestFramework,
    ) -> list[str]:
        """Get required imports for the test file."""
        imports = []

        if framework == TestFramework.JEST:
            # Import the entity being tested
            imports.append(f"import {{ {entity.entity_name} }} from '../{entity.file_path}';")
        elif framework == TestFramework.PYTEST:
            imports.append(f"from {entity.file_path.replace('/', '.')} import {entity.entity_name}")
        elif framework == TestFramework.JUNIT:
            imports.append(f"import static org.junit.jupiter.api.Assertions.*;")
            imports.append(f"import org.junit.jupiter.api.Test;")

        return imports

    def _extract_tests(self, response: str, framework: TestFramework) -> str:
        """Extract test code from LLM response."""
        # Look for code blocks
        if "```" in response:
            blocks = response.split("```")
            for i, block in enumerate(blocks):
                if i % 2 == 1:  # Odd indices are code blocks
                    # Remove language identifier if present
                    lines = block.split("\n")
                    if lines[0].strip() in ["javascript", "typescript", "python", "java", "go", "csharp"]:
                        return "\n".join(lines[1:])
                    return block.strip()

        return response.strip()

    def _count_tests(self, code: str, framework: TestFramework) -> int:
        """Count the number of tests in generated code."""
        if framework in [TestFramework.JEST, TestFramework.MOCHA]:
            return code.count("it(") + code.count("test(")
        elif framework == TestFramework.PYTEST:
            return code.count("def test_")
        elif framework == TestFramework.JUNIT:
            return code.count("@Test")
        elif framework == TestFramework.XUNIT:
            return code.count("[Fact]") + code.count("[Theory]")
        elif framework == TestFramework.GO_TEST:
            return code.count("func Test")
        return 1


# Factory function
def create_test_generator(copilot_session: Any = None) -> TestGenerator:
    """Create a test generator instance.

    Args:
        copilot_session: Optional Copilot session for LLM-based generation.

    Returns:
        TestGenerator instance.
    """
    return TestGenerator(copilot_session)
