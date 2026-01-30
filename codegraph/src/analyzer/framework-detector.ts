// src/analyzer/framework-detector.ts
import * as fs from 'fs';
import * as path from 'path';
import winston from 'winston';
import {
    DetectedFramework,
    FrameworkCategory,
    FrameworkDetectionResult,
    TestFramework,
} from './types.js';

/**
 * Framework detection patterns for package files.
 */
interface PackagePattern {
    /** Framework name */
    name: string;
    /** Framework category */
    category: FrameworkCategory;
    /** Package/dependency names to look for */
    packages: string[];
    /** Minimum confidence when found in package file */
    confidence: number;
}

/**
 * Framework detection patterns for imports/annotations.
 */
interface CodePattern {
    /** Framework name */
    name: string;
    /** Category */
    category: FrameworkCategory;
    /** Import patterns (regex) */
    importPatterns?: RegExp[];
    /** Annotation/decorator patterns (regex) */
    annotationPatterns?: RegExp[];
    /** File patterns (regex for file content) */
    contentPatterns?: RegExp[];
    /** Confidence when detected via code */
    confidence: number;
}

// =============================================================================
// Package File Patterns
// =============================================================================

const PACKAGE_JSON_PATTERNS: PackagePattern[] = [
    // Backend frameworks
    { name: 'Express', category: 'backend', packages: ['express'], confidence: 0.95 },
    { name: 'NestJS', category: 'backend', packages: ['@nestjs/core', '@nestjs/common'], confidence: 0.95 },
    { name: 'Fastify', category: 'backend', packages: ['fastify'], confidence: 0.95 },
    { name: 'Koa', category: 'backend', packages: ['koa'], confidence: 0.95 },
    { name: 'Hapi', category: 'backend', packages: ['@hapi/hapi'], confidence: 0.95 },

    // Frontend frameworks
    { name: 'React', category: 'frontend', packages: ['react', 'react-dom'], confidence: 0.95 },
    { name: 'Next.js', category: 'frontend', packages: ['next'], confidence: 0.95 },
    { name: 'Vue', category: 'frontend', packages: ['vue'], confidence: 0.95 },
    { name: 'Nuxt', category: 'frontend', packages: ['nuxt', 'nuxt3'], confidence: 0.95 },
    { name: 'Angular', category: 'frontend', packages: ['@angular/core'], confidence: 0.95 },
    { name: 'Svelte', category: 'frontend', packages: ['svelte'], confidence: 0.95 },
    { name: 'SvelteKit', category: 'frontend', packages: ['@sveltejs/kit'], confidence: 0.95 },

    // Testing frameworks
    { name: 'Jest', category: 'testing', packages: ['jest', '@jest/core'], confidence: 0.95 },
    { name: 'Mocha', category: 'testing', packages: ['mocha'], confidence: 0.95 },
    { name: 'Vitest', category: 'testing', packages: ['vitest'], confidence: 0.95 },
    { name: 'Jasmine', category: 'testing', packages: ['jasmine', 'jasmine-core'], confidence: 0.95 },
    { name: 'Cypress', category: 'testing', packages: ['cypress'], confidence: 0.95 },
    { name: 'Playwright', category: 'testing', packages: ['@playwright/test', 'playwright'], confidence: 0.95 },

    // Database/ORM
    { name: 'Prisma', category: 'database', packages: ['@prisma/client', 'prisma'], confidence: 0.95 },
    { name: 'TypeORM', category: 'database', packages: ['typeorm'], confidence: 0.95 },
    { name: 'Sequelize', category: 'database', packages: ['sequelize'], confidence: 0.95 },
    { name: 'Mongoose', category: 'database', packages: ['mongoose'], confidence: 0.95 },

    // Messaging
    { name: 'Bull', category: 'messaging', packages: ['bull', 'bullmq'], confidence: 0.90 },
    { name: 'KafkaJS', category: 'messaging', packages: ['kafkajs'], confidence: 0.90 },
    { name: 'AMQP', category: 'messaging', packages: ['amqplib'], confidence: 0.90 },
];

const MAVEN_POM_PATTERNS: PackagePattern[] = [
    // Backend frameworks
    { name: 'Spring Boot', category: 'backend', packages: ['spring-boot-starter', 'spring-boot-starter-web'], confidence: 0.95 },
    { name: 'Spring MVC', category: 'backend', packages: ['spring-webmvc'], confidence: 0.90 },
    { name: 'Spring WebFlux', category: 'backend', packages: ['spring-boot-starter-webflux'], confidence: 0.95 },
    { name: 'Quarkus', category: 'backend', packages: ['quarkus-core', 'io.quarkus'], confidence: 0.95 },
    { name: 'Micronaut', category: 'backend', packages: ['micronaut-core', 'io.micronaut'], confidence: 0.95 },
    { name: 'Jakarta EE', category: 'backend', packages: ['jakarta.platform', 'javax.servlet'], confidence: 0.85 },

    // Testing frameworks
    { name: 'JUnit5', category: 'testing', packages: ['junit-jupiter', 'org.junit.jupiter'], confidence: 0.95 },
    { name: 'JUnit', category: 'testing', packages: ['junit', 'junit:junit'], confidence: 0.95 },
    { name: 'TestNG', category: 'testing', packages: ['testng', 'org.testng'], confidence: 0.95 },
    { name: 'Mockito', category: 'testing', packages: ['mockito-core', 'org.mockito'], confidence: 0.90 },

    // Database/ORM
    { name: 'Hibernate', category: 'database', packages: ['hibernate-core', 'org.hibernate'], confidence: 0.95 },
    { name: 'MyBatis', category: 'database', packages: ['mybatis', 'org.mybatis'], confidence: 0.95 },
    { name: 'Spring Data JPA', category: 'database', packages: ['spring-boot-starter-data-jpa'], confidence: 0.95 },

    // Messaging
    { name: 'Spring Kafka', category: 'messaging', packages: ['spring-kafka'], confidence: 0.90 },
    { name: 'Spring AMQP', category: 'messaging', packages: ['spring-amqp', 'spring-rabbit'], confidence: 0.90 },
];

const GRADLE_PATTERNS: PackagePattern[] = [
    // Same as Maven but for Gradle format
    { name: 'Spring Boot', category: 'backend', packages: ['org.springframework.boot', 'spring-boot-starter'], confidence: 0.95 },
    { name: 'Quarkus', category: 'backend', packages: ['io.quarkus'], confidence: 0.95 },
    { name: 'Micronaut', category: 'backend', packages: ['io.micronaut'], confidence: 0.95 },
    { name: 'JUnit5', category: 'testing', packages: ['org.junit.jupiter', 'junit-jupiter'], confidence: 0.95 },
    { name: 'JUnit', category: 'testing', packages: ['junit:junit'], confidence: 0.95 },
    { name: 'Spock', category: 'testing', packages: ['org.spockframework', 'spock-core'], confidence: 0.95 },
];

const REQUIREMENTS_TXT_PATTERNS: PackagePattern[] = [
    // Backend frameworks
    { name: 'FastAPI', category: 'backend', packages: ['fastapi'], confidence: 0.95 },
    { name: 'Django', category: 'backend', packages: ['django', 'Django'], confidence: 0.95 },
    { name: 'Flask', category: 'backend', packages: ['flask', 'Flask'], confidence: 0.95 },
    { name: 'Tornado', category: 'backend', packages: ['tornado'], confidence: 0.95 },
    { name: 'Sanic', category: 'backend', packages: ['sanic'], confidence: 0.95 },
    { name: 'aiohttp', category: 'backend', packages: ['aiohttp'], confidence: 0.90 },

    // Testing frameworks
    { name: 'pytest', category: 'testing', packages: ['pytest'], confidence: 0.95 },
    { name: 'unittest', category: 'testing', packages: ['unittest2'], confidence: 0.85 },
    { name: 'nose', category: 'testing', packages: ['nose', 'nose2'], confidence: 0.90 },

    // Database/ORM
    { name: 'SQLAlchemy', category: 'database', packages: ['sqlalchemy', 'SQLAlchemy'], confidence: 0.95 },
    { name: 'Django ORM', category: 'database', packages: ['django'], confidence: 0.80 },
    { name: 'Tortoise ORM', category: 'database', packages: ['tortoise-orm'], confidence: 0.95 },

    // Messaging
    { name: 'Celery', category: 'messaging', packages: ['celery'], confidence: 0.95 },
    { name: 'kafka-python', category: 'messaging', packages: ['kafka-python'], confidence: 0.90 },
];

const GO_MOD_PATTERNS: PackagePattern[] = [
    // Backend frameworks
    { name: 'Gin', category: 'backend', packages: ['github.com/gin-gonic/gin'], confidence: 0.95 },
    { name: 'Echo', category: 'backend', packages: ['github.com/labstack/echo'], confidence: 0.95 },
    { name: 'Fiber', category: 'backend', packages: ['github.com/gofiber/fiber'], confidence: 0.95 },
    { name: 'Chi', category: 'backend', packages: ['github.com/go-chi/chi'], confidence: 0.95 },
    { name: 'Gorilla Mux', category: 'backend', packages: ['github.com/gorilla/mux'], confidence: 0.95 },

    // Testing (Go has built-in testing, but these are common additions)
    { name: 'Testify', category: 'testing', packages: ['github.com/stretchr/testify'], confidence: 0.90 },
    { name: 'Ginkgo', category: 'testing', packages: ['github.com/onsi/ginkgo'], confidence: 0.95 },
    { name: 'GoMock', category: 'testing', packages: ['github.com/golang/mock'], confidence: 0.90 },

    // Database/ORM
    { name: 'GORM', category: 'database', packages: ['gorm.io/gorm'], confidence: 0.95 },
    { name: 'sqlx', category: 'database', packages: ['github.com/jmoiron/sqlx'], confidence: 0.90 },
];

const CSPROJ_PATTERNS: PackagePattern[] = [
    // Backend frameworks
    { name: 'ASP.NET Core', category: 'backend', packages: ['Microsoft.AspNetCore', 'Microsoft.AspNetCore.App'], confidence: 0.95 },
    { name: 'ASP.NET Core MVC', category: 'backend', packages: ['Microsoft.AspNetCore.Mvc'], confidence: 0.95 },
    { name: 'Blazor', category: 'frontend', packages: ['Microsoft.AspNetCore.Components'], confidence: 0.95 },

    // Testing frameworks
    { name: 'xUnit', category: 'testing', packages: ['xunit', 'xunit.core'], confidence: 0.95 },
    { name: 'NUnit', category: 'testing', packages: ['NUnit', 'NUnit3TestAdapter'], confidence: 0.95 },
    { name: 'MSTest', category: 'testing', packages: ['MSTest.TestFramework', 'Microsoft.VisualStudio.TestPlatform'], confidence: 0.95 },
    { name: 'Moq', category: 'testing', packages: ['Moq'], confidence: 0.90 },

    // Database/ORM
    { name: 'Entity Framework Core', category: 'database', packages: ['Microsoft.EntityFrameworkCore'], confidence: 0.95 },
    { name: 'Dapper', category: 'database', packages: ['Dapper'], confidence: 0.95 },
];

// =============================================================================
// Code Pattern Detection
// =============================================================================

const CODE_PATTERNS: CodePattern[] = [
    // Spring Boot
    {
        name: 'Spring Boot',
        category: 'backend',
        annotationPatterns: [
            /@SpringBootApplication/,
            /@RestController/,
            /@Controller/,
            /@Service/,
            /@Repository/,
            /@Component/,
        ],
        importPatterns: [
            /import\s+org\.springframework/,
        ],
        confidence: 0.90,
    },
    // NestJS
    {
        name: 'NestJS',
        category: 'backend',
        annotationPatterns: [
            /@Controller\s*\(/,
            /@Injectable\s*\(/,
            /@Module\s*\(/,
            /@Get\s*\(/,
            /@Post\s*\(/,
        ],
        importPatterns: [
            /from\s+['"]@nestjs\//,
        ],
        confidence: 0.90,
    },
    // Express
    {
        name: 'Express',
        category: 'backend',
        contentPatterns: [
            /express\s*\(\s*\)/,
            /app\.(get|post|put|delete|patch)\s*\(/,
            /router\.(get|post|put|delete|patch)\s*\(/,
        ],
        importPatterns: [
            /require\s*\(\s*['"]express['"]\s*\)/,
            /from\s+['"]express['"]/,
        ],
        confidence: 0.85,
    },
    // FastAPI
    {
        name: 'FastAPI',
        category: 'backend',
        annotationPatterns: [
            /@app\.(get|post|put|delete|patch)\s*\(/,
            /@router\.(get|post|put|delete|patch)\s*\(/,
        ],
        importPatterns: [
            /from\s+fastapi\s+import/,
            /import\s+fastapi/,
        ],
        confidence: 0.90,
    },
    // Django
    {
        name: 'Django',
        category: 'backend',
        importPatterns: [
            /from\s+django/,
            /import\s+django/,
        ],
        contentPatterns: [
            /urlpatterns\s*=/,
            /class\s+\w+\(.*View\)/,
        ],
        confidence: 0.90,
    },
    // Flask
    {
        name: 'Flask',
        category: 'backend',
        annotationPatterns: [
            /@app\.route\s*\(/,
            /@blueprint\.route\s*\(/,
        ],
        importPatterns: [
            /from\s+flask\s+import/,
            /import\s+flask/,
        ],
        confidence: 0.90,
    },
    // React
    {
        name: 'React',
        category: 'frontend',
        importPatterns: [
            /from\s+['"]react['"]/,
            /import\s+React/,
        ],
        contentPatterns: [
            /React\.createElement/,
            /useState\s*\(/,
            /useEffect\s*\(/,
            /<[A-Z][a-zA-Z]*[\s/>]/,
        ],
        confidence: 0.85,
    },
    // Angular
    {
        name: 'Angular',
        category: 'frontend',
        annotationPatterns: [
            /@Component\s*\(/,
            /@NgModule\s*\(/,
            /@Injectable\s*\(/,
        ],
        importPatterns: [
            /from\s+['"]@angular\//,
        ],
        confidence: 0.90,
    },
    // Vue
    {
        name: 'Vue',
        category: 'frontend',
        importPatterns: [
            /from\s+['"]vue['"]/,
        ],
        contentPatterns: [
            /createApp\s*\(/,
            /defineComponent\s*\(/,
            /<template>/,
            /<script\s+setup/,
        ],
        confidence: 0.85,
    },
    // Gin (Go)
    {
        name: 'Gin',
        category: 'backend',
        importPatterns: [
            /"github\.com\/gin-gonic\/gin"/,
        ],
        contentPatterns: [
            /gin\.Default\s*\(\)/,
            /gin\.New\s*\(\)/,
            /\.GET\s*\(/,
            /\.POST\s*\(/,
        ],
        confidence: 0.90,
    },
    // ASP.NET Core
    {
        name: 'ASP.NET Core',
        category: 'backend',
        annotationPatterns: [
            /\[ApiController\]/,
            /\[Route\s*\(/,
            /\[HttpGet/,
            /\[HttpPost/,
        ],
        importPatterns: [
            /using\s+Microsoft\.AspNetCore/,
        ],
        confidence: 0.90,
    },
];

// =============================================================================
// Framework Detector Class
// =============================================================================

export class FrameworkDetector {
    private logger: winston.Logger;
    private rootPath: string;

    constructor(rootPath: string, logger: winston.Logger) {
        this.rootPath = rootPath;
        this.logger = logger;
    }

    /**
     * Detect all frameworks in the repository.
     */
    async detectFrameworks(): Promise<FrameworkDetectionResult> {
        const frameworks: DetectedFramework[] = [];

        // Detect from package files
        const packageFrameworks = await this.detectFromPackageFiles();
        frameworks.push(...packageFrameworks);

        // Merge duplicates and calculate final confidence
        const mergedFrameworks = this.mergeFrameworks(frameworks);

        // Determine primary frameworks
        const primaryBackend = mergedFrameworks
            .filter(f => f.category === 'backend')
            .sort((a, b) => b.confidence - a.confidence)[0];

        const primaryFrontend = mergedFrameworks
            .filter(f => f.category === 'frontend')
            .sort((a, b) => b.confidence - a.confidence)[0];

        const testingFrameworks = mergedFrameworks
            .filter(f => f.category === 'testing');

        this.logger.info(`Detected ${mergedFrameworks.length} frameworks`, {
            primary: primaryBackend?.name,
            frontend: primaryFrontend?.name,
            testing: testingFrameworks.map(f => f.name),
        });

        return {
            frameworks: mergedFrameworks,
            primaryBackend,
            primaryFrontend,
            testingFrameworks,
        };
    }

    /**
     * Detect frameworks from package/dependency files.
     */
    private async detectFromPackageFiles(): Promise<DetectedFramework[]> {
        const frameworks: DetectedFramework[] = [];

        // Check package.json (Node.js)
        const packageJsonPath = path.join(this.rootPath, 'package.json');
        if (fs.existsSync(packageJsonPath)) {
            const detected = await this.detectFromPackageJson(packageJsonPath);
            frameworks.push(...detected);
        }

        // Check pom.xml (Maven)
        const pomXmlPath = path.join(this.rootPath, 'pom.xml');
        if (fs.existsSync(pomXmlPath)) {
            const detected = await this.detectFromPomXml(pomXmlPath);
            frameworks.push(...detected);
        }

        // Check build.gradle (Gradle)
        const buildGradlePath = path.join(this.rootPath, 'build.gradle');
        const buildGradleKtsPath = path.join(this.rootPath, 'build.gradle.kts');
        if (fs.existsSync(buildGradlePath)) {
            const detected = await this.detectFromGradle(buildGradlePath);
            frameworks.push(...detected);
        } else if (fs.existsSync(buildGradleKtsPath)) {
            const detected = await this.detectFromGradle(buildGradleKtsPath);
            frameworks.push(...detected);
        }

        // Check requirements.txt (Python)
        const requirementsTxtPath = path.join(this.rootPath, 'requirements.txt');
        if (fs.existsSync(requirementsTxtPath)) {
            const detected = await this.detectFromRequirementsTxt(requirementsTxtPath);
            frameworks.push(...detected);
        }

        // Check pyproject.toml (Python)
        const pyprojectPath = path.join(this.rootPath, 'pyproject.toml');
        if (fs.existsSync(pyprojectPath)) {
            const detected = await this.detectFromPyprojectToml(pyprojectPath);
            frameworks.push(...detected);
        }

        // Check go.mod (Go)
        const goModPath = path.join(this.rootPath, 'go.mod');
        if (fs.existsSync(goModPath)) {
            const detected = await this.detectFromGoMod(goModPath);
            frameworks.push(...detected);
        }

        // Check *.csproj (C#)
        const csprojFiles = await this.findFiles('*.csproj');
        for (const csprojPath of csprojFiles) {
            const detected = await this.detectFromCsproj(csprojPath);
            frameworks.push(...detected);
        }

        return frameworks;
    }

    /**
     * Detect frameworks from package.json.
     */
    private async detectFromPackageJson(filePath: string): Promise<DetectedFramework[]> {
        const frameworks: DetectedFramework[] = [];

        try {
            const content = fs.readFileSync(filePath, 'utf-8');
            const pkg = JSON.parse(content);
            const allDeps = {
                ...pkg.dependencies,
                ...pkg.devDependencies,
                ...pkg.peerDependencies,
            };

            for (const pattern of PACKAGE_JSON_PATTERNS) {
                const found = pattern.packages.some(p => p in allDeps);
                if (found) {
                    const matchedPkgs = pattern.packages.filter(p => p in allDeps);
                    const version = allDeps[matchedPkgs[0]];
                    frameworks.push({
                        name: pattern.name,
                        category: pattern.category,
                        version: version?.replace(/[\^~>=<]/g, ''),
                        confidence: pattern.confidence,
                        detectedBy: 'package-file',
                        evidence: [`Found in package.json: ${matchedPkgs.join(', ')}`],
                    });
                }
            }
        } catch (e: any) {
            this.logger.warn(`Failed to parse package.json: ${e.message}`);
        }

        return frameworks;
    }

    /**
     * Detect frameworks from pom.xml.
     */
    private async detectFromPomXml(filePath: string): Promise<DetectedFramework[]> {
        const frameworks: DetectedFramework[] = [];

        try {
            const content = fs.readFileSync(filePath, 'utf-8');

            for (const pattern of MAVEN_POM_PATTERNS) {
                const found = pattern.packages.some(p => content.includes(p));
                if (found) {
                    const matchedPkgs = pattern.packages.filter(p => content.includes(p));
                    // Try to extract version
                    const versionMatch = content.match(new RegExp(`<version>([^<]+)</version>`));
                    frameworks.push({
                        name: pattern.name,
                        category: pattern.category,
                        version: versionMatch?.[1],
                        confidence: pattern.confidence,
                        detectedBy: 'package-file',
                        evidence: [`Found in pom.xml: ${matchedPkgs.join(', ')}`],
                    });
                }
            }
        } catch (e: any) {
            this.logger.warn(`Failed to parse pom.xml: ${e.message}`);
        }

        return frameworks;
    }

    /**
     * Detect frameworks from build.gradle.
     */
    private async detectFromGradle(filePath: string): Promise<DetectedFramework[]> {
        const frameworks: DetectedFramework[] = [];

        try {
            const content = fs.readFileSync(filePath, 'utf-8');

            for (const pattern of GRADLE_PATTERNS) {
                const found = pattern.packages.some(p => content.includes(p));
                if (found) {
                    const matchedPkgs = pattern.packages.filter(p => content.includes(p));
                    frameworks.push({
                        name: pattern.name,
                        category: pattern.category,
                        confidence: pattern.confidence,
                        detectedBy: 'package-file',
                        evidence: [`Found in build.gradle: ${matchedPkgs.join(', ')}`],
                    });
                }
            }
        } catch (e: any) {
            this.logger.warn(`Failed to parse build.gradle: ${e.message}`);
        }

        return frameworks;
    }

    /**
     * Detect frameworks from requirements.txt.
     */
    private async detectFromRequirementsTxt(filePath: string): Promise<DetectedFramework[]> {
        const frameworks: DetectedFramework[] = [];

        try {
            const content = fs.readFileSync(filePath, 'utf-8');
            const lines = content.split('\n').map(l => l.trim().toLowerCase());

            for (const pattern of REQUIREMENTS_TXT_PATTERNS) {
                const found = pattern.packages.some(p =>
                    lines.some(line => line.startsWith(p.toLowerCase()) || line.includes(`${p.toLowerCase()}==`) || line.includes(`${p.toLowerCase()}>=`))
                );
                if (found) {
                    const matchedPkgs = pattern.packages.filter(p =>
                        lines.some(line => line.startsWith(p.toLowerCase()))
                    );
                    // Extract version
                    const versionLine = lines.find(l => matchedPkgs.some(p => l.startsWith(p.toLowerCase())));
                    const versionMatch = versionLine?.match(/[=><]+(.+)/);
                    frameworks.push({
                        name: pattern.name,
                        category: pattern.category,
                        version: versionMatch?.[1],
                        confidence: pattern.confidence,
                        detectedBy: 'package-file',
                        evidence: [`Found in requirements.txt: ${matchedPkgs.join(', ')}`],
                    });
                }
            }
        } catch (e: any) {
            this.logger.warn(`Failed to parse requirements.txt: ${e.message}`);
        }

        return frameworks;
    }

    /**
     * Detect frameworks from pyproject.toml.
     */
    private async detectFromPyprojectToml(filePath: string): Promise<DetectedFramework[]> {
        const frameworks: DetectedFramework[] = [];

        try {
            const content = fs.readFileSync(filePath, 'utf-8');

            for (const pattern of REQUIREMENTS_TXT_PATTERNS) {
                const found = pattern.packages.some(p => content.toLowerCase().includes(p.toLowerCase()));
                if (found) {
                    const matchedPkgs = pattern.packages.filter(p => content.toLowerCase().includes(p.toLowerCase()));
                    frameworks.push({
                        name: pattern.name,
                        category: pattern.category,
                        confidence: pattern.confidence * 0.9, // Slightly lower confidence
                        detectedBy: 'package-file',
                        evidence: [`Found in pyproject.toml: ${matchedPkgs.join(', ')}`],
                    });
                }
            }
        } catch (e: any) {
            this.logger.warn(`Failed to parse pyproject.toml: ${e.message}`);
        }

        return frameworks;
    }

    /**
     * Detect frameworks from go.mod.
     */
    private async detectFromGoMod(filePath: string): Promise<DetectedFramework[]> {
        const frameworks: DetectedFramework[] = [];

        try {
            const content = fs.readFileSync(filePath, 'utf-8');

            // Go has built-in testing
            if (content.includes('module ')) {
                frameworks.push({
                    name: 'Go testing',
                    category: 'testing',
                    confidence: 0.80, // Lower confidence since it's built-in
                    detectedBy: 'package-file',
                    evidence: ['Go module detected - built-in testing assumed'],
                });
            }

            for (const pattern of GO_MOD_PATTERNS) {
                const found = pattern.packages.some(p => content.includes(p));
                if (found) {
                    const matchedPkgs = pattern.packages.filter(p => content.includes(p));
                    // Try to extract version
                    const versionMatch = content.match(new RegExp(`${matchedPkgs[0].replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+v([\\d.]+)`));
                    frameworks.push({
                        name: pattern.name,
                        category: pattern.category,
                        version: versionMatch?.[1],
                        confidence: pattern.confidence,
                        detectedBy: 'package-file',
                        evidence: [`Found in go.mod: ${matchedPkgs.join(', ')}`],
                    });
                }
            }
        } catch (e: any) {
            this.logger.warn(`Failed to parse go.mod: ${e.message}`);
        }

        return frameworks;
    }

    /**
     * Detect frameworks from .csproj file.
     */
    private async detectFromCsproj(filePath: string): Promise<DetectedFramework[]> {
        const frameworks: DetectedFramework[] = [];

        try {
            const content = fs.readFileSync(filePath, 'utf-8');

            for (const pattern of CSPROJ_PATTERNS) {
                const found = pattern.packages.some(p => content.includes(p));
                if (found) {
                    const matchedPkgs = pattern.packages.filter(p => content.includes(p));
                    // Try to extract version
                    const versionMatch = content.match(new RegExp(`Version="([^"]+)"`));
                    frameworks.push({
                        name: pattern.name,
                        category: pattern.category,
                        version: versionMatch?.[1],
                        confidence: pattern.confidence,
                        detectedBy: 'package-file',
                        evidence: [`Found in ${path.basename(filePath)}: ${matchedPkgs.join(', ')}`],
                    });
                }
            }
        } catch (e: any) {
            this.logger.warn(`Failed to parse .csproj: ${e.message}`);
        }

        return frameworks;
    }

    /**
     * Detect frameworks from source code patterns.
     * This is called during file analysis to augment package-file detection.
     */
    detectFromCode(content: string, language: string): DetectedFramework[] {
        const frameworks: DetectedFramework[] = [];

        for (const pattern of CODE_PATTERNS) {
            let matchCount = 0;
            const evidence: string[] = [];

            // Check import patterns
            if (pattern.importPatterns) {
                for (const regex of pattern.importPatterns) {
                    if (regex.test(content)) {
                        matchCount++;
                        evidence.push(`Import pattern: ${regex.source}`);
                    }
                }
            }

            // Check annotation patterns
            if (pattern.annotationPatterns) {
                for (const regex of pattern.annotationPatterns) {
                    if (regex.test(content)) {
                        matchCount++;
                        evidence.push(`Annotation pattern: ${regex.source}`);
                    }
                }
            }

            // Check content patterns
            if (pattern.contentPatterns) {
                for (const regex of pattern.contentPatterns) {
                    if (regex.test(content)) {
                        matchCount++;
                        evidence.push(`Code pattern: ${regex.source}`);
                    }
                }
            }

            if (matchCount > 0) {
                // Adjust confidence based on number of matches
                const adjustedConfidence = Math.min(pattern.confidence + (matchCount - 1) * 0.05, 1.0);
                frameworks.push({
                    name: pattern.name,
                    category: pattern.category,
                    confidence: adjustedConfidence,
                    detectedBy: matchCount > 1 ? 'pattern' : 'import',
                    evidence,
                });
            }
        }

        return frameworks;
    }

    /**
     * Merge duplicate framework detections and combine evidence.
     */
    private mergeFrameworks(frameworks: DetectedFramework[]): DetectedFramework[] {
        const merged = new Map<string, DetectedFramework>();

        for (const fw of frameworks) {
            const existing = merged.get(fw.name);
            if (existing) {
                // Merge: take higher confidence, combine evidence
                existing.confidence = Math.max(existing.confidence, fw.confidence);
                existing.evidence = Array.from(new Set([...existing.evidence, ...fw.evidence]));
                if (fw.version && !existing.version) {
                    existing.version = fw.version;
                }
            } else {
                merged.set(fw.name, { ...fw });
            }
        }

        return Array.from(merged.values()).sort((a, b) => b.confidence - a.confidence);
    }

    /**
     * Find files matching a pattern.
     */
    private async findFiles(pattern: string): Promise<string[]> {
        const files: string[] = [];

        const walkDir = (dir: string) => {
            try {
                const entries = fs.readdirSync(dir, { withFileTypes: true });
                for (const entry of entries) {
                    const fullPath = path.join(dir, entry.name);
                    if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
                        walkDir(fullPath);
                    } else if (entry.isFile()) {
                        // Simple glob matching
                        if (pattern.startsWith('*')) {
                            const ext = pattern.slice(1);
                            if (entry.name.endsWith(ext)) {
                                files.push(fullPath);
                            }
                        } else if (entry.name === pattern) {
                            files.push(fullPath);
                        }
                    }
                }
            } catch (e) {
                // Ignore permission errors
            }
        };

        walkDir(this.rootPath);
        return files;
    }

    /**
     * Map framework name to TestFramework type.
     */
    static mapToTestFramework(frameworkName: string): TestFramework {
        const mapping: Record<string, TestFramework> = {
            'JUnit': 'JUnit',
            'JUnit5': 'JUnit5',
            'TestNG': 'TestNG',
            'Jest': 'Jest',
            'Mocha': 'Mocha',
            'Vitest': 'Vitest',
            'pytest': 'pytest',
            'unittest': 'unittest',
            'Go testing': 'Go testing',
            'Testify': 'Go testing',
            'Ginkgo': 'Go testing',
            'xUnit': 'xUnit',
            'NUnit': 'NUnit',
            'MSTest': 'MSTest',
            'GoogleTest': 'GoogleTest',
            'Catch2': 'Catch2',
            'RSpec': 'RSpec',
        };
        return mapping[frameworkName] || 'Unknown';
    }
}

/**
 * Convenience function to detect frameworks in a repository.
 */
export async function detectFrameworks(
    rootPath: string,
    logger: winston.Logger
): Promise<FrameworkDetectionResult> {
    const detector = new FrameworkDetector(rootPath, logger);
    return detector.detectFrameworks();
}
