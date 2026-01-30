// src/analyzer/framework-detector.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { FrameworkDetector } from './framework-detector.js';
import * as fs from 'fs';
import * as path from 'path';
import winston from 'winston';

// Mock fs module
vi.mock('fs', () => ({
    existsSync: vi.fn(),
    readFileSync: vi.fn(),
    readdirSync: vi.fn(),
}));

describe('FrameworkDetector', () => {
    let detector: FrameworkDetector;
    let mockLogger: winston.Logger;

    beforeEach(() => {
        mockLogger = {
            info: vi.fn(),
            debug: vi.fn(),
            warn: vi.fn(),
            error: vi.fn(),
        } as unknown as winston.Logger;

        vi.clearAllMocks();
    });

    describe('detectFromPackageJson', () => {
        it('should detect Express framework', async () => {
            const packageJson = {
                dependencies: {
                    express: '^4.18.0',
                },
            };

            vi.mocked(fs.existsSync).mockReturnValue(true);
            vi.mocked(fs.readFileSync).mockReturnValue(JSON.stringify(packageJson));
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            expect(result.frameworks).toContainEqual(
                expect.objectContaining({
                    name: 'Express',
                    category: 'backend',
                    confidence: expect.any(Number),
                })
            );
        });

        it('should detect React framework', async () => {
            const packageJson = {
                dependencies: {
                    react: '^18.0.0',
                    'react-dom': '^18.0.0',
                },
            };

            vi.mocked(fs.existsSync).mockReturnValue(true);
            vi.mocked(fs.readFileSync).mockReturnValue(JSON.stringify(packageJson));
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            expect(result.frameworks).toContainEqual(
                expect.objectContaining({
                    name: 'React',
                    category: 'frontend',
                })
            );
            expect(result.primaryFrontend?.name).toBe('React');
        });

        it('should detect Jest testing framework', async () => {
            const packageJson = {
                devDependencies: {
                    jest: '^29.0.0',
                },
            };

            vi.mocked(fs.existsSync).mockReturnValue(true);
            vi.mocked(fs.readFileSync).mockReturnValue(JSON.stringify(packageJson));
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            expect(result.testingFrameworks).toContainEqual(
                expect.objectContaining({
                    name: 'Jest',
                    category: 'testing',
                })
            );
        });

        it('should detect NestJS framework', async () => {
            const packageJson = {
                dependencies: {
                    '@nestjs/core': '^10.0.0',
                    '@nestjs/common': '^10.0.0',
                },
            };

            vi.mocked(fs.existsSync).mockReturnValue(true);
            vi.mocked(fs.readFileSync).mockReturnValue(JSON.stringify(packageJson));
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            expect(result.frameworks).toContainEqual(
                expect.objectContaining({
                    name: 'NestJS',
                    category: 'backend',
                })
            );
        });
    });

    describe('detectFromPomXml', () => {
        it('should detect Spring Boot framework', async () => {
            const pomXml = `
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-starter-web</artifactId>
                            <version>3.0.0</version>
                        </dependency>
                    </dependencies>
                </project>
            `;

            vi.mocked(fs.existsSync).mockImplementation((p) => {
                return p === '/test/project/pom.xml';
            });
            vi.mocked(fs.readFileSync).mockReturnValue(pomXml);
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            expect(result.frameworks).toContainEqual(
                expect.objectContaining({
                    name: 'Spring Boot',
                    category: 'backend',
                })
            );
            expect(result.primaryBackend?.name).toBe('Spring Boot');
        });

        it('should detect JUnit5 testing framework', async () => {
            const pomXml = `
                <project>
                    <dependencies>
                        <dependency>
                            <groupId>org.junit.jupiter</groupId>
                            <artifactId>junit-jupiter</artifactId>
                            <version>5.9.0</version>
                            <scope>test</scope>
                        </dependency>
                    </dependencies>
                </project>
            `;

            vi.mocked(fs.existsSync).mockImplementation((p) => {
                return p === '/test/project/pom.xml';
            });
            vi.mocked(fs.readFileSync).mockReturnValue(pomXml);
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            expect(result.testingFrameworks).toContainEqual(
                expect.objectContaining({
                    name: 'JUnit5',
                    category: 'testing',
                })
            );
        });
    });

    describe('detectFromRequirementsTxt', () => {
        it('should detect FastAPI framework', async () => {
            const requirementsTxt = `
fastapi==0.100.0
uvicorn==0.23.0
            `;

            vi.mocked(fs.existsSync).mockImplementation((p) => {
                return p === '/test/project/requirements.txt';
            });
            vi.mocked(fs.readFileSync).mockReturnValue(requirementsTxt);
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            expect(result.frameworks).toContainEqual(
                expect.objectContaining({
                    name: 'FastAPI',
                    category: 'backend',
                })
            );
        });

        it('should detect pytest testing framework', async () => {
            const requirementsTxt = `
pytest==7.4.0
pytest-cov==4.1.0
            `;

            vi.mocked(fs.existsSync).mockImplementation((p) => {
                return p === '/test/project/requirements.txt';
            });
            vi.mocked(fs.readFileSync).mockReturnValue(requirementsTxt);
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            expect(result.testingFrameworks).toContainEqual(
                expect.objectContaining({
                    name: 'pytest',
                    category: 'testing',
                })
            );
        });
    });

    describe('detectFromGoMod', () => {
        it('should detect Gin framework', async () => {
            const goMod = `
module myproject

go 1.21

require github.com/gin-gonic/gin v1.9.0
            `;

            vi.mocked(fs.existsSync).mockImplementation((p) => {
                return p === '/test/project/go.mod';
            });
            vi.mocked(fs.readFileSync).mockReturnValue(goMod);
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            expect(result.frameworks).toContainEqual(
                expect.objectContaining({
                    name: 'Gin',
                    category: 'backend',
                })
            );
        });
    });

    describe('detectFromCode', () => {
        it('should detect Spring annotations in Java code', () => {
            detector = new FrameworkDetector('/test/project', mockLogger);

            const javaCode = `
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.GetMapping;

@RestController
public class UserController {
    @GetMapping("/users")
    public List<User> getUsers() {
        return userService.findAll();
    }
}
            `;

            const result = detector.detectFromCode(javaCode, 'Java');

            expect(result).toContainEqual(
                expect.objectContaining({
                    name: 'Spring Boot',
                    category: 'backend',
                })
            );
        });

        it('should detect NestJS decorators in TypeScript code', () => {
            detector = new FrameworkDetector('/test/project', mockLogger);

            const tsCode = `
import { Controller, Get } from '@nestjs/common';

@Controller('users')
export class UsersController {
    @Get()
    findAll() {
        return this.usersService.findAll();
    }
}
            `;

            const result = detector.detectFromCode(tsCode, 'TypeScript');

            expect(result).toContainEqual(
                expect.objectContaining({
                    name: 'NestJS',
                    category: 'backend',
                })
            );
        });

        it('should detect FastAPI decorators in Python code', () => {
            detector = new FrameworkDetector('/test/project', mockLogger);

            const pythonCode = `
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
async def get_users():
    return {"users": []}
            `;

            const result = detector.detectFromCode(pythonCode, 'Python');

            expect(result).toContainEqual(
                expect.objectContaining({
                    name: 'FastAPI',
                    category: 'backend',
                })
            );
        });

        it('should detect React imports in TypeScript code', () => {
            detector = new FrameworkDetector('/test/project', mockLogger);

            const tsxCode = `
import React, { useState, useEffect } from 'react';

export const UserList: React.FC = () => {
    const [users, setUsers] = useState([]);

    useEffect(() => {
        fetchUsers();
    }, []);

    return <div>{users.map(u => <User key={u.id} {...u} />)}</div>;
};
            `;

            const result = detector.detectFromCode(tsxCode, 'TypeScript');

            expect(result).toContainEqual(
                expect.objectContaining({
                    name: 'React',
                    category: 'frontend',
                })
            );
        });
    });

    describe('mapToTestFramework', () => {
        it('should map framework names to TestFramework type', () => {
            expect(FrameworkDetector.mapToTestFramework('Jest')).toBe('Jest');
            expect(FrameworkDetector.mapToTestFramework('JUnit5')).toBe('JUnit5');
            expect(FrameworkDetector.mapToTestFramework('pytest')).toBe('pytest');
            expect(FrameworkDetector.mapToTestFramework('Go testing')).toBe('Go testing');
            expect(FrameworkDetector.mapToTestFramework('xUnit')).toBe('xUnit');
            expect(FrameworkDetector.mapToTestFramework('Unknown Framework')).toBe('Unknown');
        });
    });

    describe('mergeFrameworks', () => {
        it('should merge duplicate frameworks and keep highest confidence', async () => {
            const packageJson = {
                dependencies: {
                    express: '^4.18.0',
                },
            };

            vi.mocked(fs.existsSync).mockReturnValue(true);
            vi.mocked(fs.readFileSync).mockReturnValue(JSON.stringify(packageJson));
            vi.mocked(fs.readdirSync).mockReturnValue([]);

            detector = new FrameworkDetector('/test/project', mockLogger);
            const result = await detector.detectFrameworks();

            // Should not have duplicates
            const expressFrameworks = result.frameworks.filter(f => f.name === 'Express');
            expect(expressFrameworks.length).toBe(1);
        });
    });
});
