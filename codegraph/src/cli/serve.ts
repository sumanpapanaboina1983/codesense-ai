import { Command } from 'commander';
import { createContextLogger } from '../utils/logger.js';
import { startServer } from '../api/server.js';

const logger = createContextLogger('ServeCmd');

interface ServeOptions {
    port?: number;
}

export function registerServeCommand(program: Command): void {
    program
        .command('serve')
        .description('Start the CodeGraph API server')
        .option('-p, --port <port>', 'Port to run the server on', '3001')
        .action(async (options: ServeOptions) => {
            const port = typeof options.port === 'string'
                ? parseInt(options.port, 10)
                : options.port || 3001;

            logger.info(`Starting API server on port ${port}...`);

            try {
                await startServer(port);
            } catch (error: any) {
                logger.error(`Failed to start server: ${error.message}`);
                process.exitCode = 1;
            }
        });
}
