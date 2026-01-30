/**
 * Git utilities for cloning repositories.
 */
import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import fs from 'fs/promises';
import os from 'os';
import { createContextLogger } from './logger.js';

const execAsync = promisify(exec);
const logger = createContextLogger('GitUtils');

export interface CloneOptions {
    /** Branch to checkout (optional, defaults to default branch) */
    branch?: string;
    /** Depth for shallow clone (optional, defaults to full clone) */
    depth?: number;
    /** Directory to clone into (optional, auto-generated if not provided) */
    targetDir?: string;
    /** Authentication token for private repos (optional) */
    token?: string;
}

export interface CloneResult {
    /** Absolute path to the cloned repository */
    localPath: string;
    /** Whether this is a temporary directory that should be cleaned up */
    isTemporary: boolean;
    /** The branch that was checked out */
    branch?: string;
    /** The current commit SHA */
    commitSha?: string;
}

/**
 * Parses a GitHub/GitLab URL and extracts owner and repo name.
 */
export function parseGitUrl(url: string): { owner: string; repo: string; host: string } | null {
    // Handle various URL formats:
    // https://github.com/owner/repo
    // https://github.com/owner/repo.git
    // git@github.com:owner/repo.git
    // https://gitlab.com/owner/repo

    const httpsMatch = url.match(/https?:\/\/([^\/]+)\/([^\/]+)\/([^\/\.]+)(\.git)?/);
    if (httpsMatch && httpsMatch[1] && httpsMatch[2] && httpsMatch[3]) {
        return {
            host: httpsMatch[1],
            owner: httpsMatch[2],
            repo: httpsMatch[3],
        };
    }

    const sshMatch = url.match(/git@([^:]+):([^\/]+)\/([^\/\.]+)(\.git)?/);
    if (sshMatch && sshMatch[1] && sshMatch[2] && sshMatch[3]) {
        return {
            host: sshMatch[1],
            owner: sshMatch[2],
            repo: sshMatch[3],
        };
    }

    return null;
}

/**
 * Checks if git is available on the system.
 */
export async function isGitAvailable(): Promise<boolean> {
    try {
        await execAsync('git --version');
        return true;
    } catch {
        return false;
    }
}

/**
 * Clones a git repository to a local directory.
 *
 * @param gitUrl - The URL of the git repository
 * @param options - Clone options
 * @returns CloneResult with the local path and metadata
 */
export async function cloneRepository(gitUrl: string, options: CloneOptions = {}): Promise<CloneResult> {
    // Verify git is available
    if (!(await isGitAvailable())) {
        throw new Error('Git is not installed or not available in PATH');
    }

    // Parse the URL to get repo info
    const repoInfo = parseGitUrl(gitUrl);
    if (!repoInfo) {
        throw new Error(`Invalid git URL: ${gitUrl}`);
    }

    // Determine target directory
    let targetDir = options.targetDir;
    let isTemporary = false;

    if (!targetDir) {
        // Create a temporary directory
        const tempBase = path.join(os.tmpdir(), 'codegraph-repos');
        await fs.mkdir(tempBase, { recursive: true });
        targetDir = path.join(tempBase, `${repoInfo.repo}-${Date.now()}`);
        isTemporary = true;
    }

    // Build the clone URL with authentication if token is provided
    let cloneUrl = gitUrl;
    if (options.token && gitUrl.startsWith('https://')) {
        // Insert token into URL: https://token@github.com/...
        cloneUrl = gitUrl.replace('https://', `https://${options.token}@`);
    }

    // Build git clone command
    const cloneArgs: string[] = ['clone'];

    if (options.depth) {
        cloneArgs.push('--depth', options.depth.toString());
    }

    if (options.branch) {
        cloneArgs.push('--branch', options.branch);
    }

    cloneArgs.push(cloneUrl, targetDir);

    const command = `git ${cloneArgs.join(' ')}`;

    // Mask token in logs
    const logCommand = options.token
        ? command.replace(options.token, '***TOKEN***')
        : command;

    logger.info(`Cloning repository: ${logCommand}`);

    try {
        await execAsync(command, {
            maxBuffer: 50 * 1024 * 1024, // 50MB buffer for large repos
            timeout: 5 * 60 * 1000, // 5 minute timeout
        });
    } catch (error: any) {
        // Clean up on failure
        if (isTemporary) {
            await fs.rm(targetDir, { recursive: true, force: true }).catch(() => {});
        }
        throw new Error(`Failed to clone repository: ${error.message}`);
    }

    // Get commit SHA
    let commitSha: string | undefined;
    let branch: string | undefined;
    try {
        const { stdout: shaOut } = await execAsync('git rev-parse HEAD', { cwd: targetDir });
        commitSha = shaOut.trim();

        const { stdout: branchOut } = await execAsync('git branch --show-current', { cwd: targetDir });
        branch = branchOut.trim() || options.branch;
    } catch {
        // Non-fatal, just log
        logger.warn('Could not get commit info after clone');
    }

    logger.info(`Repository cloned successfully to: ${targetDir}`);

    return {
        localPath: targetDir,
        isTemporary,
        branch,
        commitSha,
    };
}

/**
 * Cleans up a cloned repository directory.
 * Only deletes if it's in the temporary directory.
 */
export async function cleanupRepository(localPath: string, force: boolean = false): Promise<void> {
    const tempBase = path.join(os.tmpdir(), 'codegraph-repos');

    // Safety check: only delete if it's in our temp directory or force is true
    if (!force && !localPath.startsWith(tempBase)) {
        logger.warn(`Refusing to delete non-temporary directory: ${localPath}`);
        return;
    }

    try {
        await fs.rm(localPath, { recursive: true, force: true });
        logger.info(`Cleaned up repository: ${localPath}`);
    } catch (error: any) {
        logger.warn(`Failed to cleanup repository: ${error.message}`);
    }
}

/**
 * Checks if a string is a git URL (vs a local path).
 */
export function isGitUrl(input: string): boolean {
    return (
        input.startsWith('https://github.com') ||
        input.startsWith('https://gitlab.com') ||
        input.startsWith('https://bitbucket.org') ||
        input.startsWith('git@') ||
        input.includes('github.com') ||
        input.includes('gitlab.com') ||
        input.includes('bitbucket.org') ||
        /^https?:\/\/.*\.git$/.test(input)
    );
}
