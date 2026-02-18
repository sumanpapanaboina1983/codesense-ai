/**
 * Callback Client for reporting analysis progress to the backend.
 *
 * Sends progress updates, logs, and completion notifications to the
 * Python backend API which persists them in PostgreSQL.
 */

import axios, { AxiosInstance } from 'axios';
import { createContextLogger } from '../utils/logger.js';

const logger = createContextLogger('CallbackClient');

export interface ProgressUpdate {
    phase: string;
    progress_pct: number;
    total_files: number;
    processed_files: number;
    last_processed_file?: string;
    nodes_created: number;
    relationships_created: number;
    message?: string;
}

export interface LogEntry {
    level: 'info' | 'warning' | 'error';
    phase: string;
    message: string;
    details?: Record<string, any>;
    timestamp?: string;
}

export interface CompletionUpdate {
    success: boolean;
    error?: string;
    stats?: Record<string, any>;
}

export interface StartNotification {
    codegraph_job_id: string;
}

/**
 * Client for sending callbacks to the backend API.
 */
export class CallbackClient {
    private client: AxiosInstance;
    private analysisRunId: string;
    private logBuffer: LogEntry[] = [];
    private logFlushInterval: NodeJS.Timeout | null = null;
    private readonly LOG_BUFFER_SIZE = 20;
    private readonly LOG_FLUSH_INTERVAL_MS = 2000;

    constructor(backendUrl: string, analysisRunId: string) {
        this.analysisRunId = analysisRunId;
        this.client = axios.create({
            baseURL: `${backendUrl}/api/v1/analysis/callback/${analysisRunId}`,
            timeout: 10000,
            headers: {
                'Content-Type': 'application/json',
            },
        });

        // Start periodic log flushing
        this.logFlushInterval = setInterval(() => {
            this.flushLogs().catch((err) => {
                logger.warn('Failed to flush logs', { error: err.message });
            });
        }, this.LOG_FLUSH_INTERVAL_MS);
    }

    /**
     * Notify backend that analysis has started.
     */
    async notifyStart(codegraphJobId: string): Promise<void> {
        try {
            const data: StartNotification = { codegraph_job_id: codegraphJobId };
            await this.client.post('/start', data);
            logger.info(`Notified backend: analysis started for ${this.analysisRunId}`);
        } catch (error: any) {
            logger.error('Failed to notify start', { error: error.message });
            // Don't throw - continue analysis even if callback fails
        }
    }

    /**
     * Send progress update to backend.
     */
    async updateProgress(update: ProgressUpdate): Promise<void> {
        try {
            await this.client.post('/progress', update);
        } catch (error: any) {
            logger.warn('Failed to send progress update', { error: error.message });
        }
    }

    /**
     * Add a log entry (buffered for efficiency).
     */
    addLog(entry: LogEntry): void {
        this.logBuffer.push({
            ...entry,
            timestamp: new Date().toISOString(),
        });

        // Flush if buffer is full
        if (this.logBuffer.length >= this.LOG_BUFFER_SIZE) {
            this.flushLogs().catch((err) => {
                logger.warn('Failed to flush logs', { error: err.message });
            });
        }
    }

    /**
     * Flush buffered logs to backend.
     */
    async flushLogs(): Promise<void> {
        if (this.logBuffer.length === 0) return;

        const logs = [...this.logBuffer];
        this.logBuffer = [];

        try {
            await this.client.post('/logs', { logs });
        } catch (error: any) {
            logger.warn(`Failed to send ${logs.length} logs`, { error: error.message });
            // Re-add failed logs to buffer (up to a limit)
            if (this.logBuffer.length < 100) {
                this.logBuffer = [...logs.slice(-50), ...this.logBuffer];
            }
        }
    }

    /**
     * Notify backend that analysis has completed.
     */
    async notifyComplete(update: CompletionUpdate): Promise<void> {
        // Flush any remaining logs first
        await this.flushLogs();

        try {
            await this.client.post('/complete', update);
            logger.info(`Notified backend: analysis ${update.success ? 'completed' : 'failed'}`);
        } catch (error: any) {
            logger.error('Failed to notify completion', { error: error.message });
        }

        // Stop log flushing
        this.cleanup();
    }

    /**
     * Cleanup resources.
     */
    cleanup(): void {
        if (this.logFlushInterval) {
            clearInterval(this.logFlushInterval);
            this.logFlushInterval = null;
        }
    }
}

/**
 * Create a callback client if backend URL is provided.
 */
export function createCallbackClient(
    backendUrl: string | undefined,
    analysisRunId: string | undefined
): CallbackClient | null {
    if (!backendUrl || !analysisRunId) {
        logger.info('No callback URL or analysis run ID - running in standalone mode');
        return null;
    }

    return new CallbackClient(backendUrl, analysisRunId);
}
