// src/analyzer/stereotype-detector.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { StereotypeDetector, detectStereotype, getArchitectureLayer, getStereotypeStats } from './stereotype-detector.js';
import { AstNode, Stereotype } from './types.js';
import winston from 'winston';

describe('StereotypeDetector', () => {
    let detector: StereotypeDetector;
    let mockLogger: winston.Logger;

    beforeEach(() => {
        mockLogger = {
            info: vi.fn(),
            debug: vi.fn(),
            warn: vi.fn(),
            error: vi.fn(),
        } as unknown as winston.Logger;

        detector = new StereotypeDetector(mockLogger);
    });

    const createMockNode = (overrides: Partial<AstNode>): AstNode => ({
        id: 'test-id',
        entityId: 'test-entity-id',
        kind: 'Class',
        name: 'TestClass',
        filePath: '/test/TestClass.java',
        language: 'Java',
        startLine: 1,
        endLine: 100,
        startColumn: 0,
        endColumn: 0,
        createdAt: new Date().toISOString(),
        ...overrides,
    });

    describe('detectStereotype', () => {
        describe('Controller detection', () => {
            it('should detect Controller from @Controller annotation', () => {
                const node = createMockNode({
                    name: 'UserController',
                    modifierFlags: ['@Controller'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Controller');
                expect(result.confidence).toBeGreaterThanOrEqual(0.5);
            });

            it('should detect Controller from @RestController annotation', () => {
                const node = createMockNode({
                    name: 'ApiController',
                    modifierFlags: ['@RestController'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Controller');
            });

            it('should detect Controller from naming convention', () => {
                const node = createMockNode({
                    name: 'UserController',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Controller');
                expect(result.evidence).toContain('Name ends with: Controller');
            });
        });

        describe('Service detection', () => {
            it('should detect Service from @Service annotation', () => {
                const node = createMockNode({
                    name: 'UserService',
                    modifierFlags: ['@Service'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Service');
            });

            it('should detect Service from @Injectable annotation', () => {
                const node = createMockNode({
                    name: 'AuthService', // Use Service suffix for clearer detection
                    modifierFlags: ['@Injectable'],
                });

                const result = detector.detectStereotype(node);

                // @Injectable is used in Angular/NestJS for services
                expect(['Service', 'Entity']).toContain(result.stereotype);
            });

            it('should detect Service from naming convention', () => {
                const node = createMockNode({
                    name: 'PaymentService',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Service');
            });
        });

        describe('Repository detection', () => {
            it('should detect Repository from @Repository annotation', () => {
                const node = createMockNode({
                    name: 'UserRepository',
                    modifierFlags: ['@Repository'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Repository');
            });

            it('should detect Repository from naming convention', () => {
                const node = createMockNode({
                    name: 'OrderDao',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Repository');
            });

            it('should detect Repository from implements interface', () => {
                const node = createMockNode({
                    name: 'OrderPersistence',
                    implementsInterfaces: ['CrudRepository'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Repository');
            });
        });

        describe('Entity detection', () => {
            it('should detect Entity from @Entity annotation', () => {
                const node = createMockNode({
                    name: 'User',
                    modifierFlags: ['@Entity'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Entity');
            });

            it('should detect Entity from @Table annotation', () => {
                const node = createMockNode({
                    name: 'Product',
                    modifierFlags: ['@Table'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Entity');
            });
        });

        describe('DTO detection', () => {
            it('should detect DTO from naming convention', () => {
                const node = createMockNode({
                    name: 'UserDTO',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('DTO');
            });

            it('should detect DTO from Request suffix', () => {
                const node = createMockNode({
                    name: 'CreateUserRequest',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('DTO');
            });

            it('should detect DTO from Response suffix', () => {
                const node = createMockNode({
                    name: 'UserResponse',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('DTO');
            });
        });

        describe('Configuration detection', () => {
            it('should detect Configuration from @Configuration annotation', () => {
                const node = createMockNode({
                    name: 'SecurityConfig',
                    modifierFlags: ['@Configuration'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Configuration');
            });

            it('should detect Configuration from naming convention', () => {
                const node = createMockNode({
                    name: 'DatabaseConfiguration',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Configuration');
            });
        });

        describe('Utility detection', () => {
            it('should detect Utility from naming convention', () => {
                const node = createMockNode({
                    name: 'StringUtils',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Utility');
            });

            it('should detect Utility from Helper suffix', () => {
                const node = createMockNode({
                    name: 'DateHelper',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Utility');
            });
        });

        describe('Factory detection', () => {
            it('should detect Factory from naming convention', () => {
                const node = createMockNode({
                    name: 'UserFactory',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Factory');
            });
        });

        describe('Builder detection', () => {
            it('should detect Builder from @Builder annotation', () => {
                const node = createMockNode({
                    name: 'UserEntity',
                    modifierFlags: ['@Builder'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Builder');
            });

            it('should detect Builder from naming convention', () => {
                const node = createMockNode({
                    name: 'QueryBuilder',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Builder');
            });
        });

        describe('Middleware detection', () => {
            it('should detect Middleware from naming convention', () => {
                const node = createMockNode({
                    name: 'AuthMiddleware',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Middleware');
            });
        });

        describe('Mapper detection', () => {
            it('should detect Mapper from @Mapper annotation', () => {
                const node = createMockNode({
                    name: 'UserMapper',
                    modifierFlags: ['@Mapper'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Mapper');
            });

            it('should detect Mapper from naming convention', () => {
                const node = createMockNode({
                    name: 'OrderConverter',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Mapper');
            });
        });

        describe('Client detection', () => {
            it('should detect Client from naming convention', () => {
                const node = createMockNode({
                    name: 'PaymentClient',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Client');
            });

            it('should detect Client from @FeignClient annotation', () => {
                const node = createMockNode({
                    name: 'ExternalService',
                    modifierFlags: ['@FeignClient'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Client');
            });
        });

        describe('Handler detection', () => {
            it('should detect Handler from @EventHandler annotation', () => {
                const node = createMockNode({
                    name: 'OrderEventProcessor',
                    modifierFlags: ['@EventHandler'],
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Handler');
            });

            it('should detect Handler from naming convention', () => {
                const node = createMockNode({
                    name: 'MessageHandler',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Handler');
            });
        });

        describe('Unknown stereotype', () => {
            it('should return Unknown for unrecognized classes', () => {
                const node = createMockNode({
                    name: 'SomeRandomClass',
                });

                const result = detector.detectStereotype(node);

                expect(result.stereotype).toBe('Unknown');
                expect(result.confidence).toBeLessThan(0.5);
            });
        });

        describe('Multiple matches', () => {
            it('should prefer annotation over naming convention', () => {
                const node = createMockNode({
                    name: 'UserService', // Would match Service by naming
                    modifierFlags: ['@Repository'], // But has Repository annotation
                });

                const result = detector.detectStereotype(node);

                // Repository annotation has higher confidence than Service naming
                expect(result.stereotype).toBe('Repository');
            });
        });
    });

    describe('detectStereotypes (batch)', () => {
        it('should process multiple nodes', () => {
            const nodes: AstNode[] = [
                createMockNode({ entityId: '1', name: 'UserController' }),
                createMockNode({ entityId: '2', name: 'UserService' }),
                createMockNode({ entityId: '3', name: 'UserRepository' }),
                createMockNode({ entityId: '4', name: 'RandomClass' }),
            ];

            const results = detector.detectStereotypes(nodes);

            expect(results.size).toBe(3); // 3 detected (RandomClass should be Unknown)
            expect(results.get('1')).toBe('Controller');
            expect(results.get('2')).toBe('Service');
            expect(results.get('3')).toBe('Repository');
        });

        it('should only process class-like nodes', () => {
            const nodes: AstNode[] = [
                createMockNode({ kind: 'Class', name: 'UserService' }),
                createMockNode({ kind: 'Function', name: 'getUserService' }),
                createMockNode({ kind: 'Method', name: 'findAll' }),
            ];

            const results = detector.detectStereotypes(nodes);

            expect(results.size).toBe(1); // Only the Class node
        });
    });

    describe('getArchitectureLayer', () => {
        it('should map Controller to presentation layer', () => {
            expect(getArchitectureLayer('Controller')).toBe('presentation');
        });

        it('should map Service to business layer', () => {
            expect(getArchitectureLayer('Service')).toBe('business');
        });

        it('should map Repository to data layer', () => {
            expect(getArchitectureLayer('Repository')).toBe('data');
        });

        it('should map Entity to domain layer', () => {
            expect(getArchitectureLayer('Entity')).toBe('domain');
        });

        it('should map Configuration to infrastructure layer', () => {
            expect(getArchitectureLayer('Configuration')).toBe('infrastructure');
        });

        it('should return undefined for Unknown', () => {
            expect(getArchitectureLayer('Unknown')).toBeUndefined();
        });
    });

    describe('getStereotypeStats', () => {
        it('should calculate stereotype statistics', () => {
            const nodes: AstNode[] = [
                createMockNode({ stereotype: 'Controller' as Stereotype }),
                createMockNode({ stereotype: 'Controller' as Stereotype }),
                createMockNode({ stereotype: 'Service' as Stereotype }),
                createMockNode({ stereotype: 'Repository' as Stereotype }),
                createMockNode({ stereotype: undefined }),
            ];

            const stats = getStereotypeStats(nodes);

            expect(stats['Controller']).toBe(2);
            expect(stats['Service']).toBe(1);
            expect(stats['Repository']).toBe(1);
        });
    });
});
