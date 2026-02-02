// src/analyzer/test-detector.ts
/**
 * Detects test files and test cases from analyzed code.
 * Creates TestFile and TestCase nodes with appropriate relationships.
 */

import * as path from 'path';
import winston from 'winston';
import {
    AstNode,
    TestFileNode,
    TestCaseNode,
    TestFramework,
    RelationshipInfo,
} from './types.js';

// =============================================================================
// Test File Detection Patterns
// =============================================================================

interface TestFilePattern {
    /** File path pattern (glob-like) */
    pathPattern: RegExp;
    /** Framework detected */
    framework: TestFramework;
    /** Priority (higher = more specific match) */
    priority: number;
}

const TEST_FILE_PATTERNS: TestFilePattern[] = [
    // Java/JUnit
    { pathPattern: /Test\.java$/i, framework: 'JUnit', priority: 2 },
    { pathPattern: /Tests\.java$/i, framework: 'JUnit', priority: 2 },
    { pathPattern: /IT\.java$/i, framework: 'JUnit', priority: 1 }, // Integration tests
    { pathPattern: /Spec\.java$/i, framework: 'JUnit', priority: 1 },
    { pathPattern: /src\/test\/java\//i, framework: 'JUnit', priority: 1 },

    // JavaScript/TypeScript - Jest
    { pathPattern: /\.test\.[jt]sx?$/i, framework: 'Jest', priority: 3 },
    { pathPattern: /\.spec\.[jt]sx?$/i, framework: 'Jest', priority: 3 },
    { pathPattern: /__tests__\/.*\.[jt]sx?$/i, framework: 'Jest', priority: 2 },

    // JavaScript/TypeScript - Mocha
    { pathPattern: /test\/.*\.[jt]sx?$/i, framework: 'Mocha', priority: 1 },
    { pathPattern: /tests\/.*\.[jt]sx?$/i, framework: 'Mocha', priority: 1 },

    // JavaScript/TypeScript - Vitest
    { pathPattern: /\.test\.[jt]sx?$/i, framework: 'Vitest', priority: 2 },

    // Python - pytest
    { pathPattern: /test_.*\.py$/i, framework: 'pytest', priority: 3 },
    { pathPattern: /_test\.py$/i, framework: 'pytest', priority: 3 },
    { pathPattern: /tests\/.*\.py$/i, framework: 'pytest', priority: 2 },
    { pathPattern: /test\/.*\.py$/i, framework: 'pytest', priority: 2 },

    // Go
    { pathPattern: /_test\.go$/i, framework: 'Go testing', priority: 3 },

    // C#
    { pathPattern: /Tests?\.cs$/i, framework: 'xUnit', priority: 2 },
    { pathPattern: /\.Tests?\/.*\.cs$/i, framework: 'xUnit', priority: 2 },
    { pathPattern: /Spec\.cs$/i, framework: 'NUnit', priority: 1 },

    // C++ - GoogleTest
    { pathPattern: /_test\.cpp$/i, framework: 'GoogleTest', priority: 2 },
    { pathPattern: /_test\.cc$/i, framework: 'GoogleTest', priority: 2 },
    { pathPattern: /test_.*\.cpp$/i, framework: 'GoogleTest', priority: 2 },
];

// =============================================================================
// Test Case Detection Patterns
// =============================================================================

interface TestCasePattern {
    /** Framework */
    framework: TestFramework;
    /** Pattern to detect test methods/functions */
    pattern: RegExp;
    /** Test name extraction group */
    nameGroup?: number;
    /** Suite name extraction group */
    suiteGroup?: number;
}

const TEST_CASE_PATTERNS: TestCasePattern[] = [
    // JUnit 5
    { framework: 'JUnit5', pattern: /@Test\s+(?:public\s+)?void\s+(\w+)/i, nameGroup: 1 },
    { framework: 'JUnit5', pattern: /@ParameterizedTest[^@]*@\w+\s+(?:public\s+)?void\s+(\w+)/i, nameGroup: 1 },
    { framework: 'JUnit5', pattern: /@RepeatedTest\s*\([^)]*\)\s+(?:public\s+)?void\s+(\w+)/i, nameGroup: 1 },
    { framework: 'JUnit5', pattern: /@Nested\s+class\s+(\w+)/i, suiteGroup: 1 },

    // JUnit 4
    { framework: 'JUnit', pattern: /@Test\s+public\s+void\s+(\w+)/i, nameGroup: 1 },

    // Jest/Mocha/Vitest
    { framework: 'Jest', pattern: /(?:it|test)\s*\(\s*['"`]([^'"`]+)['"`]/i, nameGroup: 1 },
    { framework: 'Jest', pattern: /describe\s*\(\s*['"`]([^'"`]+)['"`]/i, suiteGroup: 1 },
    { framework: 'Mocha', pattern: /(?:it|test)\s*\(\s*['"`]([^'"`]+)['"`]/i, nameGroup: 1 },
    { framework: 'Mocha', pattern: /describe\s*\(\s*['"`]([^'"`]+)['"`]/i, suiteGroup: 1 },
    { framework: 'Vitest', pattern: /(?:it|test)\s*\(\s*['"`]([^'"`]+)['"`]/i, nameGroup: 1 },

    // pytest
    { framework: 'pytest', pattern: /def\s+(test_\w+)\s*\(/i, nameGroup: 1 },
    { framework: 'pytest', pattern: /class\s+(Test\w+)\s*[:(]/i, suiteGroup: 1 },

    // Go testing
    { framework: 'Go testing', pattern: /func\s+(Test\w+)\s*\(\s*t\s+\*testing\.T\s*\)/i, nameGroup: 1 },
    { framework: 'Go testing', pattern: /func\s+(Benchmark\w+)\s*\(\s*b\s+\*testing\.B\s*\)/i, nameGroup: 1 },

    // xUnit
    { framework: 'xUnit', pattern: /\[Fact\]\s*(?:public\s+)?(?:async\s+)?(?:Task|void)\s+(\w+)/i, nameGroup: 1 },
    { framework: 'xUnit', pattern: /\[Theory\][^[]*\[(?:Inline|Member|Class)Data[^\]]*\]\s*(?:public\s+)?(?:async\s+)?(?:Task|void)\s+(\w+)/i, nameGroup: 1 },

    // NUnit
    { framework: 'NUnit', pattern: /\[Test\]\s*(?:public\s+)?(?:async\s+)?(?:Task|void)\s+(\w+)/i, nameGroup: 1 },
    { framework: 'NUnit', pattern: /\[TestCase[^\]]*\]\s*(?:public\s+)?(?:async\s+)?(?:Task|void)\s+(\w+)/i, nameGroup: 1 },
    { framework: 'NUnit', pattern: /\[TestFixture\]\s*(?:public\s+)?class\s+(\w+)/i, suiteGroup: 1 },

    // GoogleTest
    { framework: 'GoogleTest', pattern: /TEST\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)/i, suiteGroup: 1, nameGroup: 2 },
    { framework: 'GoogleTest', pattern: /TEST_F\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)/i, suiteGroup: 1, nameGroup: 2 },
];

// =============================================================================
// Test Detection Helpers
// =============================================================================

interface TestTypeIndicators {
    integration: RegExp[];
    unit: RegExp[];
    e2e: RegExp[];
}

const TEST_TYPE_INDICATORS: TestTypeIndicators = {
    integration: [
        /integration/i,
        /IT\.java$/i,
        /\.integration\./i,
        /IntegrationTest/i,
        /@SpringBootTest/i,
        /@DataJpaTest/i,
        /@WebMvcTest/i,
    ],
    unit: [
        /unit/i,
        /\.unit\./i,
        /UnitTest/i,
    ],
    e2e: [
        /e2e/i,
        /end-to-end/i,
        /cypress/i,
        /playwright/i,
        /puppeteer/i,
        /selenium/i,
    ],
};

// =============================================================================
// Test Detector Class
// =============================================================================

export class TestDetector {
    private logger: winston.Logger;

    constructor(logger: winston.Logger) {
        this.logger = logger;
    }

    /**
     * Detect test files from file nodes.
     */
    detectTestFiles(
        fileNodes: AstNode[],
        sourceTexts: Map<string, string>
    ): TestDetectionResult {
        const testFiles: TestFileNode[] = [];
        const testCases: TestCaseNode[] = [];
        const relationships: RelationshipInfo[] = [];

        for (const fileNode of fileNodes) {
            if (fileNode.kind !== 'File') continue;

            const detection = this.detectTestFile(fileNode, sourceTexts.get(fileNode.filePath));
            if (detection) {
                testFiles.push(detection.testFile);
                testCases.push(...detection.testCases);
                relationships.push(...detection.relationships);
            }
        }

        this.logger.info('Test detection complete', {
            testFiles: testFiles.length,
            testCases: testCases.length,
        });

        return {
            testFiles,
            testCases,
            relationships,
        };
    }

    /**
     * Detect if a file is a test file and extract test cases.
     */
    private detectTestFile(
        fileNode: AstNode,
        sourceText?: string
    ): { testFile: TestFileNode; testCases: TestCaseNode[]; relationships: RelationshipInfo[] } | null {
        const filePath = fileNode.filePath;

        // Check file path patterns
        let matchedFramework: TestFramework = 'Unknown';
        let highestPriority = 0;

        for (const pattern of TEST_FILE_PATTERNS) {
            if (pattern.pathPattern.test(filePath)) {
                if (pattern.priority > highestPriority) {
                    matchedFramework = pattern.framework;
                    highestPriority = pattern.priority;
                }
            }
        }

        // If no path match, check source content for test patterns
        if (matchedFramework === 'Unknown' && sourceText) {
            matchedFramework = this.detectFrameworkFromContent(sourceText);
        }

        // Not a test file
        if (matchedFramework === 'Unknown') {
            return null;
        }

        // Refine framework detection from content
        if (sourceText) {
            const contentFramework = this.refineFrameworkFromContent(sourceText, matchedFramework);
            if (contentFramework !== 'Unknown') {
                matchedFramework = contentFramework;
            }
        }

        // Detect test cases
        const testCasesResult = sourceText
            ? this.detectTestCases(sourceText, filePath, matchedFramework)
            : { testCases: [], suites: [] };

        // Determine test types
        const testTypes = this.detectTestTypes(filePath, sourceText);

        // Try to find tested file
        const testedFile = this.inferTestedFile(filePath);

        // Create TestFile node
        const testFileId = this.generateEntityId('test_file', filePath);
        const testFile: TestFileNode = {
            id: testFileId,
            entityId: testFileId,
            kind: 'TestFile',
            name: path.basename(filePath),
            filePath,
            language: fileNode.language,
            startLine: 1,
            endLine: fileNode.endLine || 1,
            startColumn: 0,
            endColumn: 0,
            createdAt: new Date().toISOString(),
            properties: {
                testFramework: matchedFramework,
                testCount: testCasesResult.testCases.length,
                testSuiteCount: testCasesResult.suites.length,
                testedFilePath: testedFile,
                hasIntegrationTests: testTypes.integration,
                hasUnitTests: testTypes.unit,
                hasE2ETests: testTypes.e2e,
                hasSetup: this.hasSetup(sourceText),
                hasTeardown: this.hasTeardown(sourceText),
                mockingFrameworks: this.detectMockingFrameworks(sourceText),
            },
        };

        // Create TestCase nodes
        const testCases: TestCaseNode[] = testCasesResult.testCases.map(tc => ({
            id: tc.id,
            entityId: tc.id,
            kind: 'TestCase',
            name: tc.name,
            filePath,
            language: fileNode.language,
            startLine: tc.line,
            endLine: tc.line,
            startColumn: 0,
            endColumn: 0,
            createdAt: new Date().toISOString(),
            properties: {
                testName: tc.name,
                suiteName: tc.suite,
                testFramework: matchedFramework,
                isSkipped: tc.isSkipped,
                isFocused: tc.isFocused,
            },
        }));

        // Create relationships
        const relationships: RelationshipInfo[] = [];

        // TestFile CONTAINS TestCase relationships
        for (const tc of testCases) {
            relationships.push({
                id: this.generateEntityId('contains', `${testFileId}:${tc.entityId}`),
                entityId: this.generateEntityId('contains', `${testFileId}:${tc.entityId}`),
                type: 'CONTAINS',
                sourceId: testFileId,
                targetId: tc.entityId,
                createdAt: new Date().toISOString(),
            });
        }

        return { testFile, testCases, relationships };
    }

    /**
     * Detect test framework from source content.
     */
    private detectFrameworkFromContent(sourceText: string): TestFramework {
        // Check imports/requires
        const frameworkIndicators: Array<{ pattern: RegExp; framework: TestFramework }> = [
            { pattern: /import.*['"]@jest\/globals['"]|from\s+['"]jest['"]|require\(['"]jest['"]\)/i, framework: 'Jest' },
            { pattern: /import.*['"]vitest['"]|from\s+['"]vitest['"]/i, framework: 'Vitest' },
            { pattern: /import.*['"]mocha['"]|require\(['"]mocha['"]\)/i, framework: 'Mocha' },
            { pattern: /import\s+org\.junit/i, framework: 'JUnit' },
            { pattern: /import\s+org\.junit\.jupiter/i, framework: 'JUnit5' },
            { pattern: /import\s+pytest|from\s+pytest/i, framework: 'pytest' },
            { pattern: /import\s+"testing"/i, framework: 'Go testing' },
            { pattern: /using\s+Xunit|using\s+xUnit/i, framework: 'xUnit' },
            { pattern: /using\s+NUnit/i, framework: 'NUnit' },
            { pattern: /using\s+Microsoft\.VisualStudio\.TestTools/i, framework: 'MSTest' },
            { pattern: /#include\s*[<"]gtest\/gtest\.h[>"]/i, framework: 'GoogleTest' },
            { pattern: /#include\s*[<"]catch2/i, framework: 'Catch2' },
        ];

        for (const indicator of frameworkIndicators) {
            if (indicator.pattern.test(sourceText)) {
                return indicator.framework;
            }
        }

        return 'Unknown';
    }

    /**
     * Refine framework detection based on content patterns.
     */
    private refineFrameworkFromContent(sourceText: string, current: TestFramework): TestFramework {
        // Check for JUnit 5 specific annotations
        if (current === 'JUnit' && /@DisplayName|@Nested|@ParameterizedTest|@RepeatedTest/.test(sourceText)) {
            return 'JUnit5';
        }

        // Check for TestNG
        if (current === 'JUnit' && /@Test\s*\([^)]*groups\s*=/.test(sourceText)) {
            return 'TestNG';
        }

        return current;
    }

    /**
     * Detect test cases from source content.
     */
    private detectTestCases(
        sourceText: string,
        filePath: string,
        framework: TestFramework
    ): { testCases: TestCaseInfo[]; suites: string[] } {
        const testCases: TestCaseInfo[] = [];
        const suites = new Set<string>();
        const lines = sourceText.split('\n');

        let currentSuite: string | undefined;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i]!;
            const lineNum = i + 1;

            for (const pattern of TEST_CASE_PATTERNS) {
                // Only use patterns for the detected framework (or compatible ones)
                if (!this.isCompatibleFramework(pattern.framework, framework)) {
                    continue;
                }

                const match = line.match(pattern.pattern);
                if (match) {
                    if (pattern.suiteGroup) {
                        const suiteMatch = match[pattern.suiteGroup];
                        if (suiteMatch) {
                            currentSuite = suiteMatch;
                            suites.add(currentSuite);
                        }
                    }

                    if (pattern.nameGroup) {
                        const testName = match[pattern.nameGroup];
                        if (testName) {
                            testCases.push({
                                id: this.generateEntityId('test_case', `${filePath}:${testName}:${lineNum}`),
                                name: testName,
                                suite: currentSuite,
                                line: lineNum,
                                isSkipped: this.isSkipped(line, lines[i - 1]),
                                isFocused: this.isFocused(line),
                            });
                        }
                    }
                }
            }
        }

        return { testCases, suites: Array.from(suites) };
    }

    /**
     * Check if frameworks are compatible (e.g., Jest patterns work for Vitest).
     */
    private isCompatibleFramework(patternFramework: TestFramework, detectedFramework: TestFramework): boolean {
        const compatibilityMap: Record<TestFramework, TestFramework[]> = {
            'Jest': ['Jest', 'Vitest', 'Mocha'],
            'Mocha': ['Mocha', 'Jest', 'Vitest'],
            'Vitest': ['Vitest', 'Jest'],
            'JUnit': ['JUnit', 'JUnit5'],
            'JUnit5': ['JUnit5', 'JUnit'],
            'pytest': ['pytest'],
            'unittest': ['unittest', 'pytest'],
            'Go testing': ['Go testing'],
            'xUnit': ['xUnit'],
            'NUnit': ['NUnit'],
            'MSTest': ['MSTest'],
            'GoogleTest': ['GoogleTest'],
            'Catch2': ['Catch2'],
            'RSpec': ['RSpec'],
            'TestNG': ['TestNG', 'JUnit'],
            'Unknown': [],
        };

        const compatible = compatibilityMap[patternFramework] || [];
        return compatible.includes(detectedFramework);
    }

    /**
     * Detect test types (unit, integration, e2e).
     */
    private detectTestTypes(filePath: string, sourceText?: string): {
        unit: boolean;
        integration: boolean;
        e2e: boolean;
    } {
        const text = `${filePath}\n${sourceText || ''}`;

        return {
            unit: TEST_TYPE_INDICATORS.unit.some(p => p.test(text)),
            integration: TEST_TYPE_INDICATORS.integration.some(p => p.test(text)),
            e2e: TEST_TYPE_INDICATORS.e2e.some(p => p.test(text)),
        };
    }

    /**
     * Check if a test is skipped.
     */
    private isSkipped(line: string, prevLine?: string): boolean {
        const skipPatterns = [
            /\.skip\s*\(/,
            /xit\s*\(/,
            /xdescribe\s*\(/,
            /xtest\s*\(/,
            /@Ignore/,
            /@Disabled/,
            /\[Ignore\]/,
            /\[Skip\]/,
            /@pytest\.mark\.skip/,
            /t\.Skip\(/,
        ];

        const fullText = `${prevLine || ''}\n${line}`;
        return skipPatterns.some(p => p.test(fullText));
    }

    /**
     * Check if a test is focused (only).
     */
    private isFocused(line: string): boolean {
        const focusPatterns = [
            /\.only\s*\(/,
            /fit\s*\(/,
            /fdescribe\s*\(/,
            /test\.only\s*\(/,
        ];

        return focusPatterns.some(p => p.test(line));
    }

    /**
     * Check if test file has setup (beforeEach, setUp, etc.).
     */
    private hasSetup(sourceText?: string): boolean {
        if (!sourceText) return false;
        const setupPatterns = [
            /beforeEach\s*\(/,
            /beforeAll\s*\(/,
            /@Before/,
            /@BeforeEach/,
            /@BeforeAll/,
            /\[SetUp\]/,
            /\[OneTimeSetUp\]/,
            /def\s+setUp\s*\(/,
            /def\s+setup_method\s*\(/,
            /func\s+SetUp\w*\s*\(/,
        ];

        return setupPatterns.some(p => p.test(sourceText));
    }

    /**
     * Check if test file has teardown (afterEach, tearDown, etc.).
     */
    private hasTeardown(sourceText?: string): boolean {
        if (!sourceText) return false;
        const teardownPatterns = [
            /afterEach\s*\(/,
            /afterAll\s*\(/,
            /@After/,
            /@AfterEach/,
            /@AfterAll/,
            /\[TearDown\]/,
            /\[OneTimeTearDown\]/,
            /def\s+tearDown\s*\(/,
            /def\s+teardown_method\s*\(/,
            /func\s+TearDown\w*\s*\(/,
        ];

        return teardownPatterns.some(p => p.test(sourceText));
    }

    /**
     * Detect mocking frameworks used.
     */
    private detectMockingFrameworks(sourceText?: string): string[] | undefined {
        if (!sourceText) return undefined;

        const mockingPatterns: Array<{ pattern: RegExp; name: string }> = [
            { pattern: /jest\.mock|jest\.fn|jest\.spyOn/i, name: 'Jest' },
            { pattern: /vi\.mock|vi\.fn|vi\.spyOn/i, name: 'Vitest' },
            { pattern: /sinon\.|createStub|createSpy/i, name: 'Sinon' },
            { pattern: /@Mock|@InjectMocks|Mockito\./i, name: 'Mockito' },
            { pattern: /unittest\.mock|@patch|MagicMock/i, name: 'unittest.mock' },
            { pattern: /pytest\.fixture|@pytest\.fixture/i, name: 'pytest fixtures' },
            { pattern: /moq\.|Mock<|It\.Is/i, name: 'Moq' },
            { pattern: /NSubstitute|Substitute\.For/i, name: 'NSubstitute' },
            { pattern: /gomock\.|ctrl\.EXPECT/i, name: 'GoMock' },
        ];

        const detected: string[] = [];
        for (const mp of mockingPatterns) {
            if (mp.pattern.test(sourceText) && !detected.includes(mp.name)) {
                detected.push(mp.name);
            }
        }

        return detected.length > 0 ? detected : undefined;
    }

    /**
     * Try to infer the source file being tested.
     */
    private inferTestedFile(testFilePath: string): string | undefined {
        // Common patterns for test file naming
        const transforms: Array<{ from: RegExp; to: string }> = [
            // Java: UserServiceTest.java -> UserService.java
            { from: /Test\.java$/, to: '.java' },
            { from: /Tests\.java$/, to: '.java' },
            { from: /IT\.java$/, to: '.java' },

            // JS/TS: user.test.ts -> user.ts
            { from: /\.test\.(tsx?)$/, to: '.$1' },
            { from: /\.spec\.(tsx?)$/, to: '.$1' },

            // Python: test_user.py -> user.py
            { from: /test_(.+)\.py$/, to: '$1.py' },
            { from: /(.+)_test\.py$/, to: '$1.py' },

            // Go: user_test.go -> user.go
            { from: /_test\.go$/, to: '.go' },

            // C#: UserTests.cs -> User.cs
            { from: /Tests?\.cs$/, to: '.cs' },
        ];

        let sourcePath: string | undefined;

        for (const transform of transforms) {
            if (transform.from.test(testFilePath)) {
                sourcePath = testFilePath.replace(transform.from, transform.to);
                break;
            }
        }

        // Also try moving from test directory to src
        if (sourcePath) {
            sourcePath = sourcePath
                .replace(/\/test\//, '/main/')
                .replace(/\/__tests__\//, '/')
                .replace(/\/tests\//, '/src/')
                .replace(/\/test\//, '/src/');
        }

        return sourcePath;
    }

    private generateEntityId(prefix: string, identifier: string): string {
        let hash = 0;
        const str = `${prefix}:${identifier}`;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return `${prefix}_${Math.abs(hash).toString(16)}`;
    }
}

// =============================================================================
// Types
// =============================================================================

interface TestCaseInfo {
    id: string;
    name: string;
    suite?: string;
    line: number;
    isSkipped: boolean;
    isFocused: boolean;
}

export interface TestDetectionResult {
    testFiles: TestFileNode[];
    testCases: TestCaseNode[];
    relationships: RelationshipInfo[];
}

// =============================================================================
// Convenience Functions
// =============================================================================

export function createTestDetector(logger: winston.Logger): TestDetector {
    return new TestDetector(logger);
}

/**
 * Check if a file path looks like a test file.
 */
export function isTestFile(filePath: string): boolean {
    return TEST_FILE_PATTERNS.some(p => p.pathPattern.test(filePath));
}

/**
 * Get test coverage statistics.
 */
export function calculateTestCoverage(
    sourceFiles: AstNode[],
    testFiles: TestFileNode[]
): {
    filesWithTests: number;
    filesWithoutTests: number;
    coverage: number;
} {
    const testedPaths = new Set(
        testFiles
            .map(tf => tf.properties.testedFilePath)
            .filter(Boolean) as string[]
    );

    const sourceFilePaths = sourceFiles
        .filter(f => f.kind === 'File' && !isTestFile(f.filePath))
        .map(f => f.filePath);

    let filesWithTests = 0;
    for (const sourcePath of sourceFilePaths) {
        if (testedPaths.has(sourcePath)) {
            filesWithTests++;
        }
    }

    const filesWithoutTests = sourceFilePaths.length - filesWithTests;
    const coverage = sourceFilePaths.length > 0 ? filesWithTests / sourceFilePaths.length : 0;

    return {
        filesWithTests,
        filesWithoutTests,
        coverage,
    };
}
