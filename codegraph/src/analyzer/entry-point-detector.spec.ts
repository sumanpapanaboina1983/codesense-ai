// src/analyzer/entry-point-detector.spec.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { EntryPointDetector, createEntryPointDetector } from './entry-point-detector.js';
import { AstNode } from './types.js';
import winston from 'winston';

describe('EntryPointDetector', () => {
    let detector: EntryPointDetector;
    let mockLogger: winston.Logger;

    beforeEach(() => {
        mockLogger = {
            info: vi.fn(),
            debug: vi.fn(),
            warn: vi.fn(),
            error: vi.fn(),
        } as unknown as winston.Logger;

        detector = new EntryPointDetector(mockLogger, []);
    });

    const createMockNode = (overrides: Partial<AstNode>): AstNode => ({
        id: 'test-id',
        entityId: 'test-entity-id',
        kind: 'Method',
        name: 'testMethod',
        filePath: '/test/TestController.java',
        language: 'Java',
        startLine: 10,
        endLine: 20,
        startColumn: 0,
        endColumn: 0,
        createdAt: new Date().toISOString(),
        ...overrides,
    });

    describe('REST Endpoint Detection', () => {
        describe('Spring Framework', () => {
            it('should detect @GetMapping endpoint', () => {
                const node = createMockNode({
                    name: 'getUsers',
                    kind: 'JavaMethod',
                });

                const sourceText = `
@RestController
@RequestMapping("/api")
public class UserController {
    @GetMapping("/users")
    public List<User> getUsers() {
        return userService.findAll();
    }
}
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('GET');
                expect(result.restEndpoints[0].properties.path).toBe('/users');
            });

            it('should detect @PostMapping endpoint', () => {
                const node = createMockNode({
                    name: 'createUser',
                    kind: 'JavaMethod',
                });

                const sourceText = `
@PostMapping("/users")
public User createUser(@RequestBody UserDTO user) {
    return userService.create(user);
}
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('POST');
            });

            it('should detect @PutMapping endpoint', () => {
                const node = createMockNode({
                    name: 'updateUser',
                    kind: 'JavaMethod',
                });

                const sourceText = `
@PutMapping("/users/{id}")
public User updateUser(@PathVariable Long id, @RequestBody UserDTO user) {
    return userService.update(id, user);
}
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('PUT');
                expect(result.restEndpoints[0].properties.pathParameters).toContain('id');
            });

            it('should detect @DeleteMapping endpoint', () => {
                const node = createMockNode({
                    name: 'deleteUser',
                    kind: 'JavaMethod',
                });

                const sourceText = `
@DeleteMapping("/users/{id}")
public void deleteUser(@PathVariable Long id) {
    userService.delete(id);
}
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('DELETE');
            });
        });

        describe('NestJS Framework', () => {
            it('should detect @Get() endpoint', () => {
                const node = createMockNode({
                    name: 'findAll',
                    kind: 'Method',
                    language: 'TypeScript',
                });

                const sourceText = `
@Controller('users')
export class UsersController {
    @Get()
    findAll() {
        return this.usersService.findAll();
    }
}
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('GET');
                expect(result.restEndpoints[0].properties.framework).toBe('NestJS');
            });

            it('should detect @Post() endpoint with path', () => {
                const node = createMockNode({
                    name: 'create',
                    kind: 'Method',
                    language: 'TypeScript',
                });

                const sourceText = `
@Post('create')
async create(@Body() createUserDto: CreateUserDto) {
    return this.usersService.create(createUserDto);
}
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('POST');
            });
        });

        describe('Express Framework', () => {
            it('should detect app.get() endpoint', () => {
                const node = createMockNode({
                    name: 'getUsers',
                    kind: 'Function',
                    language: 'JavaScript',
                });

                const sourceText = `
app.get('/api/users', async (req, res) => {
    const users = await User.find();
    res.json(users);
});
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('GET');
                expect(result.restEndpoints[0].properties.framework).toBe('Express');
            });

            it('should detect router.post() endpoint', () => {
                const node = createMockNode({
                    name: 'createUser',
                    kind: 'Function',
                    language: 'JavaScript',
                });

                const sourceText = `
router.post('/users', async (req, res) => {
    const user = await User.create(req.body);
    res.status(201).json(user);
});
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('POST');
            });
        });

        describe('FastAPI Framework', () => {
            it('should detect @app.get() endpoint', () => {
                const node = createMockNode({
                    name: 'get_users',
                    kind: 'Function',
                    language: 'Python',
                    filePath: '/test/main.py',
                });

                const sourceText = `
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
async def get_users():
    return {"users": []}
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('GET');
                expect(result.restEndpoints[0].properties.framework).toBe('FastAPI');
            });
        });

        describe('Gin Framework', () => {
            it('should detect .GET() endpoint', () => {
                const node = createMockNode({
                    name: 'GetUsers',
                    kind: 'GoFunction',
                    language: 'Go',
                    filePath: '/test/main.go',
                });

                const sourceText = `
func SetupRouter() *gin.Engine {
    r := gin.Default()
    r.GET("/users", GetUsers)
    return r
}
`;
                const sourceTexts = new Map([[node.filePath, sourceText]]);

                const result = detector.detectEntryPoints([node], sourceTexts);

                expect(result.restEndpoints.length).toBe(1);
                expect(result.restEndpoints[0].properties.httpMethod).toBe('GET');
                expect(result.restEndpoints[0].properties.framework).toBe('Gin');
            });
        });
    });

    describe('GraphQL Operation Detection', () => {
        it('should detect @Query() operation', () => {
            const node = createMockNode({
                name: 'users',
                kind: 'Method',
                language: 'TypeScript',
            });

            const sourceText = `
@Resolver()
export class UserResolver {
    @Query()
    async users() {
        return this.userService.findAll();
    }
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.graphqlOperations.length).toBe(1);
            expect(result.graphqlOperations[0].properties.operationType).toBe('Query');
        });

        it('should detect @Mutation() operation', () => {
            const node = createMockNode({
                name: 'createUser',
                kind: 'Method',
                language: 'TypeScript',
            });

            const sourceText = `
@Mutation()
async createUser(@Args('input') input: CreateUserInput) {
    return this.userService.create(input);
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.graphqlOperations.length).toBe(1);
            expect(result.graphqlOperations[0].properties.operationType).toBe('Mutation');
        });

        it('should detect Spring @QueryMapping', () => {
            const node = createMockNode({
                name: 'getUsers',
                kind: 'JavaMethod',
                language: 'Java',
            });

            const sourceText = `
@QueryMapping
public List<User> getUsers() {
    return userService.findAll();
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.graphqlOperations.length).toBe(1);
            expect(result.graphqlOperations[0].properties.operationType).toBe('Query');
            expect(result.graphqlOperations[0].properties.framework).toBe('Spring');
        });
    });

    describe('Event Handler Detection', () => {
        it('should detect @KafkaListener handler', () => {
            const node = createMockNode({
                name: 'handleOrderEvent',
                kind: 'JavaMethod',
                language: 'Java',
            });

            const sourceText = `
@KafkaListener(topics = "order-events")
public void handleOrderEvent(OrderEvent event) {
    orderService.process(event);
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.eventHandlers.length).toBe(1);
            expect(result.eventHandlers[0].properties.eventSource).toBe('Kafka');
            expect(result.eventHandlers[0].properties.eventType).toBe('order-events');
        });

        it('should detect @RabbitListener handler', () => {
            const node = createMockNode({
                name: 'processMessage',
                kind: 'JavaMethod',
                language: 'Java',
            });

            const sourceText = `
@RabbitListener(queues = "notifications")
public void processMessage(Message message) {
    notificationService.send(message);
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.eventHandlers.length).toBe(1);
            expect(result.eventHandlers[0].properties.eventSource).toBe('RabbitMQ');
        });

        it('should detect EventEmitter.on() handler', () => {
            const node = createMockNode({
                name: 'onUserCreated',
                kind: 'Function',
                language: 'JavaScript',
            });

            const sourceText = `
eventEmitter.on('user:created', async (user) => {
    await sendWelcomeEmail(user);
});
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.eventHandlers.length).toBe(1);
            expect(result.eventHandlers[0].properties.eventSource).toBe('EventEmitter');
        });
    });

    describe('Scheduled Task Detection', () => {
        it('should detect @Scheduled with cron expression', () => {
            const node = createMockNode({
                name: 'cleanupOldRecords',
                kind: 'JavaMethod',
                language: 'Java',
            });

            const sourceText = `
@Scheduled(cron = "0 0 * * * *")
public void cleanupOldRecords() {
    recordService.deleteOld();
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.scheduledTasks.length).toBe(1);
            expect(result.scheduledTasks[0].properties.scheduleType).toBe('cron');
            expect(result.scheduledTasks[0].properties.cronExpression).toBe('0 0 * * * *');
        });

        it('should detect @Scheduled with fixedRate', () => {
            const node = createMockNode({
                name: 'sendHeartbeat',
                kind: 'JavaMethod',
                language: 'Java',
            });

            const sourceText = `
@Scheduled(fixedRate = 60000)
public void sendHeartbeat() {
    healthService.ping();
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.scheduledTasks.length).toBe(1);
            expect(result.scheduledTasks[0].properties.scheduleType).toBe('fixedRate');
            expect(result.scheduledTasks[0].properties.fixedRate).toBe(60000);
        });

        it('should detect NestJS @Cron decorator', () => {
            const node = createMockNode({
                name: 'handleCron',
                kind: 'Method',
                language: 'TypeScript',
            });

            const sourceText = `
@Cron('45 * * * * *')
handleCron() {
    this.logger.debug('Called every 45 seconds');
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.scheduledTasks.length).toBe(1);
            expect(result.scheduledTasks[0].properties.framework).toBe('NestJS');
        });
    });

    describe('CLI Command Detection', () => {
        it('should detect Click @command decorator', () => {
            const node = createMockNode({
                name: 'migrate',
                kind: 'Function',
                language: 'Python',
            });

            const sourceText = `
@click.command('migrate')
def migrate():
    """Run database migrations."""
    db.upgrade()
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.cliCommands.length).toBe(1);
            expect(result.cliCommands[0].properties.commandName).toBe('migrate');
            expect(result.cliCommands[0].properties.framework).toBe('Click');
        });

        it('should detect Commander .command()', () => {
            const node = createMockNode({
                name: 'generate',
                kind: 'Function',
                language: 'JavaScript',
            });

            const sourceText = `
program
    .command('generate')
    .description('Generate boilerplate code')
    .action(() => {
        generateCode();
    });
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.cliCommands.length).toBe(1);
            expect(result.cliCommands[0].properties.framework).toBe('Commander');
        });

        it('should detect Cobra command', () => {
            const node = createMockNode({
                name: 'serveCmd',
                kind: 'GoFunction',
                language: 'Go',
            });

            const sourceText = `
var serveCmd = &cobra.Command{
    Use:   "serve",
    Short: "Start the server",
    Run: func(cmd *cobra.Command, args []string) {
        startServer()
    },
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.cliCommands.length).toBe(1);
            expect(result.cliCommands[0].properties.commandName).toBe('serve');
            expect(result.cliCommands[0].properties.framework).toBe('Cobra');
        });
    });

    describe('Relationship Generation', () => {
        it('should generate EXPOSES_ENDPOINT relationship for REST endpoints', () => {
            const node = createMockNode({
                name: 'getUsers',
                kind: 'JavaMethod',
            });

            const sourceText = `
@GetMapping("/users")
public List<User> getUsers() {
    return userService.findAll();
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.relationships.length).toBeGreaterThanOrEqual(1);
            expect(result.relationships[0].type).toBe('EXPOSES_ENDPOINT');
            expect(result.relationships[0].sourceId).toBe(node.entityId);
        });
    });

    describe('Path Parameter Extraction', () => {
        it('should extract path parameters with {param} syntax', () => {
            const node = createMockNode({
                name: 'getUserById',
                kind: 'JavaMethod',
            });

            const sourceText = `
@GetMapping("/users/{userId}/posts/{postId}")
public Post getPost(@PathVariable Long userId, @PathVariable Long postId) {
    return postService.findByUserAndId(userId, postId);
}
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.restEndpoints[0].properties.pathParameters).toContain('userId');
            expect(result.restEndpoints[0].properties.pathParameters).toContain('postId');
        });

        it('should extract path parameters with :param syntax', () => {
            const node = createMockNode({
                name: 'getUser',
                kind: 'Function',
                language: 'JavaScript',
            });

            const sourceText = `
app.get('/users/:id', async (req, res) => {
    const user = await User.findById(req.params.id);
    res.json(user);
});
`;
            const sourceTexts = new Map([[node.filePath, sourceText]]);

            const result = detector.detectEntryPoints([node], sourceTexts);

            expect(result.restEndpoints[0].properties.pathParameters).toContain('id');
        });
    });
});
