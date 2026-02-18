/**
 * Git change detection utilities for incremental indexing.
 * Detects added, modified, and deleted files using git diff.
 */
import { exec } from 'child_process';
import { promisify } from 'util';
import fs from 'fs/promises';
import path from 'path';
import { createContextLogger } from './logger.js';

const execAsync = promisify(exec);
const logger = createContextLogger('GitChangeDetector');

/**
 * Result of a git diff operation.
 */
export interface GitDiffResult {
    /** Files that were added */
    added: string[];
    /** Files that were modified */
    modified: string[];
    /** Files that were deleted */
    deleted: string[];
    /** Files that were renamed (treated as delete + add) */
    renamed: { oldPath: string; newPath: string }[];
}

/**
 * Checks if a directory is a git repository.
 * @param dirPath - Directory path to check.
 * @returns True if the directory is a git repository.
 */
export async function isGitRepository(dirPath: string): Promise<boolean> {
    try {
        const gitDir = path.join(dirPath, '.git');
        const stat = await fs.stat(gitDir);
        return stat.isDirectory();
    } catch {
        // Also check if we're inside a git repo (subdirectory)
        try {
            await execAsync('git rev-parse --is-inside-work-tree', { cwd: dirPath });
            return true;
        } catch {
            return false;
        }
    }
}

/**
 * Gets the current HEAD commit SHA.
 * @param repoPath - Path to the git repository.
 * @returns The commit SHA or null if not a git repo or no commits.
 */
export async function getCurrentCommitSha(repoPath: string): Promise<string | null> {
    try {
        const { stdout } = await execAsync('git rev-parse HEAD', { cwd: repoPath });
        return stdout.trim();
    } catch (error: any) {
        logger.debug(`Failed to get current commit SHA: ${error.message}`);
        return null;
    }
}

/**
 * Gets the diff between two commits (or from a commit to HEAD).
 * @param repoPath - Path to the git repository.
 * @param fromCommit - Starting commit SHA.
 * @param toCommit - Ending commit SHA (defaults to HEAD).
 * @returns GitDiffResult with added, modified, and deleted files.
 */
export async function getGitDiff(
    repoPath: string,
    fromCommit: string,
    toCommit: string = 'HEAD'
): Promise<GitDiffResult> {
    const result: GitDiffResult = {
        added: [],
        modified: [],
        deleted: [],
        renamed: [],
    };

    try {
        // Use --name-status to get file status
        // -M flag enables rename detection
        const { stdout } = await execAsync(
            `git diff --name-status -M ${fromCommit}..${toCommit}`,
            { cwd: repoPath, maxBuffer: 50 * 1024 * 1024 }
        );

        const lines = stdout.trim().split('\n').filter(line => line.length > 0);

        for (const line of lines) {
            // Format: STATUS<TAB>PATH (or STATUS<TAB>OLDPATH<TAB>NEWPATH for renames)
            const parts = line.split('\t');
            if (parts.length < 2) continue;

            const status = parts[0]!;
            const filePath = parts[1]!;

            // Handle different status codes
            if (status === 'A') {
                // Added
                result.added.push(normalizePath(repoPath, filePath));
            } else if (status === 'M') {
                // Modified
                result.modified.push(normalizePath(repoPath, filePath));
            } else if (status === 'D') {
                // Deleted
                result.deleted.push(normalizePath(repoPath, filePath));
            } else if (status.startsWith('R')) {
                // Renamed (R100 means 100% similar, R050 means 50% similar, etc.)
                const oldPath = parts[1]!;
                const newPath = parts[2]!;
                result.renamed.push({
                    oldPath: normalizePath(repoPath, oldPath),
                    newPath: normalizePath(repoPath, newPath),
                });
                // Treat rename as delete old + add new for indexing purposes
                result.deleted.push(normalizePath(repoPath, oldPath));
                result.added.push(normalizePath(repoPath, newPath));
            } else if (status === 'C') {
                // Copied - treat new file as added
                const newPath = parts[2] || parts[1]!;
                result.added.push(normalizePath(repoPath, newPath));
            } else if (status === 'T') {
                // Type changed (e.g., file -> symlink) - treat as modified
                result.modified.push(normalizePath(repoPath, filePath));
            }
            // U = Unmerged, we skip these as they need manual resolution
        }

        logger.info(`Git diff from ${fromCommit} to ${toCommit}: ${result.added.length} added, ${result.modified.length} modified, ${result.deleted.length} deleted`);
        return result;

    } catch (error: any) {
        logger.error(`Failed to get git diff: ${error.message}`);
        throw new Error(`Failed to get git diff: ${error.message}`);
    }
}

/**
 * Gets all files that have been modified since a given commit.
 * Includes both tracked changes and untracked files.
 * @param repoPath - Path to the git repository.
 * @param fromCommit - Starting commit SHA.
 * @returns GitDiffResult with changes.
 */
export async function getChangesSinceCommit(
    repoPath: string,
    fromCommit: string
): Promise<GitDiffResult> {
    const result = await getGitDiff(repoPath, fromCommit, 'HEAD');

    // Also check for uncommitted changes (staged + unstaged)
    try {
        const { stdout: uncommittedDiff } = await execAsync(
            'git diff --name-status HEAD',
            { cwd: repoPath, maxBuffer: 50 * 1024 * 1024 }
        );

        const lines = uncommittedDiff.trim().split('\n').filter(line => line.length > 0);
        for (const line of lines) {
            const parts = line.split('\t');
            if (parts.length < 2) continue;

            const status = parts[0]!;
            const filePath = normalizePath(repoPath, parts[1]!);

            // Add to result if not already tracked
            if (status === 'M' && !result.modified.includes(filePath)) {
                result.modified.push(filePath);
            } else if (status === 'A' && !result.added.includes(filePath)) {
                result.added.push(filePath);
            } else if (status === 'D' && !result.deleted.includes(filePath)) {
                result.deleted.push(filePath);
            }
        }
    } catch (error: any) {
        logger.debug(`Failed to get uncommitted changes: ${error.message}`);
    }

    return result;
}

/**
 * Gets the list of untracked files in the repository.
 * @param repoPath - Path to the git repository.
 * @returns Array of untracked file paths (absolute).
 */
export async function getUntrackedFiles(repoPath: string): Promise<string[]> {
    try {
        const { stdout } = await execAsync(
            'git ls-files --others --exclude-standard',
            { cwd: repoPath, maxBuffer: 50 * 1024 * 1024 }
        );

        return stdout
            .trim()
            .split('\n')
            .filter(line => line.length > 0)
            .map(filePath => normalizePath(repoPath, filePath));
    } catch (error: any) {
        logger.debug(`Failed to get untracked files: ${error.message}`);
        return [];
    }
}

/**
 * Normalizes a relative path to an absolute path.
 * @param repoPath - Repository root path.
 * @param relativePath - Relative file path.
 * @returns Absolute normalized path.
 */
function normalizePath(repoPath: string, relativePath: string): string {
    const absolutePath = path.resolve(repoPath, relativePath);
    return absolutePath.replace(/\\/g, '/');
}

/**
 * Checks if a specific file has changed since a commit.
 * @param repoPath - Path to the git repository.
 * @param filePath - Absolute or relative path to the file.
 * @param fromCommit - Commit SHA to compare against.
 * @returns True if the file has changed.
 */
export async function hasFileChanged(
    repoPath: string,
    filePath: string,
    fromCommit: string
): Promise<boolean> {
    try {
        const relativePath = path.relative(repoPath, filePath);
        const { stdout } = await execAsync(
            `git diff --name-only ${fromCommit}..HEAD -- "${relativePath}"`,
            { cwd: repoPath }
        );
        return stdout.trim().length > 0;
    } catch {
        return true; // Assume changed if we can't determine
    }
}

/**
 * Gets the commit SHA when a file was last modified.
 * @param repoPath - Path to the git repository.
 * @param filePath - Absolute or relative path to the file.
 * @returns Commit SHA or null if not tracked.
 */
export async function getFileLastCommit(
    repoPath: string,
    filePath: string
): Promise<string | null> {
    try {
        const relativePath = path.relative(repoPath, filePath);
        const { stdout } = await execAsync(
            `git log -1 --format=%H -- "${relativePath}"`,
            { cwd: repoPath }
        );
        const sha = stdout.trim();
        return sha.length > 0 ? sha : null;
    } catch {
        return null;
    }
}
